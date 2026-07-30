from fastapi import APIRouter, HTTPException, status
from libtv_agent.api.dependencies import Actor, Session
from libtv_agent.domain.enums import UserRole
from libtv_agent.domain.schemas import MotionActionWrite
from libtv_agent.services.content_catalog import (
    MOTION_ACTION,
    list_merged_motion_actions,
    motion_action_library,
    save_catalog_entry,
)
from libtv_agent.templates.video_templates import VIDEO_TEMPLATES

router = APIRouter(prefix="/motion-actions", tags=["motion-actions"])


@router.get("")
async def get_motion_actions(actor: Actor, session: Session) -> list[dict[str, object]]:
    del actor
    return [action.to_public_dict() for action in await list_merged_motion_actions(session)]


def _require_editor(role: UserRole) -> None:
    if role not in {UserRole.ADMIN, UserRole.OPERATOR}:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "catalog editor role is required")


async def _save(
    payload: MotionActionWrite,
    actor: Actor,
    session: Session,
    *,
    creating: bool,
) -> dict[str, object]:
    _require_editor(actor.role)
    existing = (await motion_action_library(session)).get(payload.id)
    if creating and existing is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "motion action id already exists")
    if not creating and existing is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "motion action was not found")
    unknown_templates = sorted(set(payload.compatible_templates) - VIDEO_TEMPLATES.keys())
    if unknown_templates:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            f"unknown compatible template ids: {', '.join(unknown_templates)}",
        )
    value = payload.model_dump(by_alias=True, mode="json")
    if payload.required_capabilities is None:
        value["requiredCapabilities"] = (
            [capability.value for capability in existing.required_capabilities]
            if existing is not None
            else []
        )
    await save_catalog_entry(
        session,
        entry_type=MOTION_ACTION,
        entry_id=payload.id,
        payload=value,
        actor_id=actor.id,
    )
    await session.commit()
    return (await motion_action_library(session))[payload.id].to_public_dict()


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_motion_action(
    payload: MotionActionWrite,
    actor: Actor,
    session: Session,
) -> dict[str, object]:
    return await _save(payload, actor, session, creating=True)


@router.put("/{action_id}")
async def update_motion_action(
    action_id: str,
    payload: MotionActionWrite,
    actor: Actor,
    session: Session,
) -> dict[str, object]:
    if action_id != payload.id:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "motion action id is immutable")
    return await _save(payload, actor, session, creating=False)
