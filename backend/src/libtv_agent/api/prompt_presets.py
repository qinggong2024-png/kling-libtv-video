import uuid
from typing import Literal

from fastapi import APIRouter, HTTPException, Query, Response, status
from libtv_agent.api.dependencies import Actor, Session
from libtv_agent.domain.models import PromptPreset
from libtv_agent.domain.schemas import PromptPresetRead, PromptPresetWrite
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

router = APIRouter(prefix="/prompt-presets", tags=["prompt-presets"])


def _read(value: PromptPreset) -> PromptPresetRead:
    return PromptPresetRead.model_validate(value, from_attributes=True)


@router.get("", response_model=list[PromptPresetRead])
async def list_prompt_presets(
    actor: Actor,
    session: Session,
    scope: Literal["video", "image_fusion", "image_storyboard"] = Query("video"),
) -> list[PromptPresetRead]:
    values = list(
        await session.scalars(
            select(PromptPreset)
            .where(PromptPreset.user_id == actor.id, PromptPreset.scope == scope)
            .order_by(PromptPreset.sort_order, PromptPreset.created_at, PromptPreset.id)
        )
    )
    return [_read(value) for value in values]


async def _save_or_conflict(session: Session) -> None:
    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "a prompt preset with this name already exists in this scope",
        ) from exc


@router.post("", response_model=PromptPresetRead, status_code=status.HTTP_201_CREATED)
async def create_prompt_preset(
    payload: PromptPresetWrite,
    actor: Actor,
    session: Session,
) -> PromptPresetRead:
    value = PromptPreset(user_id=actor.id, **payload.model_dump(by_alias=False))
    session.add(value)
    await _save_or_conflict(session)
    await session.refresh(value)
    return _read(value)


async def _owned_preset(preset_id: uuid.UUID, actor: Actor, session: Session) -> PromptPreset:
    value = await session.scalar(
        select(PromptPreset).where(
            PromptPreset.id == preset_id,
            PromptPreset.user_id == actor.id,
        )
    )
    if value is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "prompt preset was not found")
    return value


@router.put("/{preset_id}", response_model=PromptPresetRead)
async def update_prompt_preset(
    preset_id: uuid.UUID,
    payload: PromptPresetWrite,
    actor: Actor,
    session: Session,
) -> PromptPresetRead:
    value = await _owned_preset(preset_id, actor, session)
    value.scope = payload.scope
    value.name = payload.name
    value.content = payload.content
    value.sort_order = payload.sort_order
    await _save_or_conflict(session)
    await session.refresh(value)
    return _read(value)


@router.delete("/{preset_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_prompt_preset(
    preset_id: uuid.UUID,
    actor: Actor,
    session: Session,
) -> Response:
    value = await _owned_preset(preset_id, actor, session)
    await session.delete(value)
    await session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
