from fastapi import APIRouter, HTTPException, status
from libtv_agent.api.dependencies import Actor, Session
from libtv_agent.domain.enums import UserRole
from libtv_agent.domain.schemas import MotionActionWrite
from libtv_agent.services.content_catalog import (
    MOTION_ACTION,
    list_merged_motion_actions,
    motion_action_library,
    save_catalog_entry,
    site_style_profile_library,
)
from libtv_agent.templates.motion_actions import canonical_action_id
from libtv_agent.templates.video_templates import VIDEO_TEMPLATES

router = APIRouter(prefix="/motion-actions", tags=["motion-actions"])


@router.get("")
async def get_motion_actions(actor: Actor, session: Session) -> list[dict[str, object]]:
    del actor
    return [action.to_public_dict() for action in await list_merged_motion_actions(session)]


def _require_editor(role: UserRole) -> None:
    if role is UserRole.AUDITOR:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "auditor role is read-only")


async def _save(
    payload: MotionActionWrite,
    actor: Actor,
    session: Session,
    *,
    creating: bool,
) -> dict[str, object]:
    _require_editor(actor.role)
    canonical_id = canonical_action_id(payload.id)
    existing = (await motion_action_library(session)).get(canonical_id)
    if creating and existing is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "motion action id already exists")
    if not creating and existing is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "motion action was not found")
    if payload.library_scope == "general" and (
        payload.brand_id is not None or payload.base_action_id is not None
    ):
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "general motion actions cannot have brand inheritance fields",
        )
    if payload.library_scope == "brand":
        if payload.brand_id is None:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_CONTENT,
                "brand motion actions require a brand id",
            )
        brand = (await site_style_profile_library(session)).get(payload.brand_id)
        if brand is None or brand.library_scope != "brand":
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_CONTENT,
                "brand motion actions must reference an existing brand style",
            )
        if payload.base_action_id is None:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_CONTENT,
                "brand motion actions require a general base action id",
            )
        base_action = (await motion_action_library(session)).get(payload.base_action_id)
        if base_action is None or base_action.library_scope != "general":
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_CONTENT,
                "brand motion actions must inherit from an existing general action",
            )
    unknown_templates = sorted(set(payload.compatible_templates) - VIDEO_TEMPLATES.keys())
    if unknown_templates:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            f"unknown compatible template ids: {', '.join(unknown_templates)}",
        )
    if payload.risk_level == "conditional" and payload.required_capabilities is None:
        inherited_capabilities = (
            base_action.required_capabilities
            if payload.library_scope == "brand" and base_action is not None
            else existing.required_capabilities if existing is not None else ()
        )
        if not inherited_capabilities:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_CONTENT,
                "conditional motion actions require capability prerequisites",
            )
    value = payload.model_dump(by_alias=True, mode="json")
    value["id"] = canonical_id
    if payload.required_capabilities is None:
        value["requiredCapabilities"] = (
            [capability.value for capability in existing.required_capabilities]
            if existing is not None
            else []
        )
    await save_catalog_entry(
        session,
        entry_type=MOTION_ACTION,
        entry_id=canonical_id,
        payload=value,
        actor_id=actor.id,
    )
    await session.commit()
    return (await motion_action_library(session))[canonical_id].to_public_dict()


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
    if canonical_action_id(action_id) != canonical_action_id(payload.id):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "motion action id is immutable")
    return await _save(payload, actor, session, creating=False)
