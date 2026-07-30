from fastapi import APIRouter, HTTPException, status
from libtv_agent.api.dependencies import Actor, Session
from libtv_agent.domain.enums import UserRole
from libtv_agent.domain.schemas import SiteStyleProfileWrite
from libtv_agent.services.content_catalog import (
    SITE_STYLE_PROFILE,
    list_merged_site_style_profiles,
    motion_action_library,
    next_patch_version,
    save_catalog_entry,
    site_style_profile_library,
)

router = APIRouter(prefix="/site-style-profiles", tags=["site-style-profiles"])


@router.get("")
async def get_site_style_profiles(actor: Actor, session: Session) -> list[dict[str, object]]:
    del actor
    return [
        profile.to_public_dict()
        for profile in await list_merged_site_style_profiles(session)
    ]


def _require_editor(role: UserRole) -> None:
    if role not in {UserRole.ADMIN, UserRole.OPERATOR}:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "catalog editor role is required")


async def _save(
    payload: SiteStyleProfileWrite,
    actor: Actor,
    session: Session,
    *,
    creating: bool,
) -> dict[str, object]:
    _require_editor(actor.role)
    existing = (await site_style_profile_library(session)).get(payload.id)
    if creating and existing is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "site style profile id already exists")
    if not creating and existing is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "site style profile was not found")
    if payload.status == "active" and payload.evidence_level != "verified_site":
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "active site style profiles require verified site evidence",
        )
    if payload.status == "active" and not payload.source_urls:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "active site style profiles require at least one evidence source URL",
        )
    unknown_actions = sorted(
        set(payload.preferred_actions) - (await motion_action_library(session)).keys()
    )
    if unknown_actions:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            f"unknown preferred action ids: {', '.join(unknown_actions)}",
        )
    value = payload.model_dump(by_alias=True, mode="json")
    value["version"] = "0.1.0" if existing is None else next_patch_version(existing.version)
    await save_catalog_entry(
        session,
        entry_type=SITE_STYLE_PROFILE,
        entry_id=payload.id,
        payload=value,
        actor_id=actor.id,
    )
    await session.commit()
    return (await site_style_profile_library(session))[payload.id].to_public_dict()


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_site_style_profile(
    payload: SiteStyleProfileWrite,
    actor: Actor,
    session: Session,
) -> dict[str, object]:
    return await _save(payload, actor, session, creating=True)


@router.put("/{profile_id}")
async def update_site_style_profile(
    profile_id: str,
    payload: SiteStyleProfileWrite,
    actor: Actor,
    session: Session,
) -> dict[str, object]:
    if profile_id != payload.id:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "site profile id is immutable")
    return await _save(payload, actor, session, creating=False)
