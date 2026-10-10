from __future__ import annotations

import uuid
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any

from libtv_agent.domain.models import CatalogEntry
from libtv_agent.templates.motion_actions import (
    ACTION_LIBRARY,
    ActionCapability,
    MotionAction,
    canonical_action_id,
)
from libtv_agent.templates.site_style_profiles import (
    SITE_STYLE_PROFILES,
    SiteStyleProfile,
)
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

MOTION_ACTION = "motion_action"
SITE_STYLE_PROFILE = "site_style_profile"


def _motion_action(payload: Mapping[str, Any]) -> MotionAction:
    return MotionAction(
        id=str(payload["id"]),
        label=str(payload["label"]),
        category=payload["category"],
        instruction=str(payload["instruction"]),
        purpose=str(payload["purpose"]),
        compatible_templates=tuple(payload["compatibleTemplates"]),
        requirements=tuple(payload.get("requirements", ())),
        required_capabilities=tuple(
            ActionCapability(value) for value in payload.get("requiredCapabilities", ())
        ),
        avoid=tuple(payload.get("avoid", ())),
        risk_level=payload.get("riskLevel", "low"),
        library_scope=payload.get("libraryScope", "general"),
        brand_id=payload.get("brandId"),
        base_action_id=payload.get("baseActionId"),
        product_focus=payload.get("productFocus") or (
            ACTION_LIBRARY[str(payload["id"])].product_focus
            if str(payload["id"]) in ACTION_LIBRARY else "upper_garment"
        ),
    )


def _site_style_profile(payload: Mapping[str, Any]) -> SiteStyleProfile:
    library_scope = payload.get("libraryScope", "brand")
    return SiteStyleProfile(
        id=str(payload["id"]),
        version=str(payload["version"]),
        status=payload["status"],
        name=str(payload["name"]),
        site_url=str(payload.get("siteUrl", "")),
        source_urls=tuple(payload.get("sourceUrls", ())),
        retrieved_at=str(payload["retrievedAt"]),
        evidence_level=payload["evidenceLevel"],
        tone=str(payload["tone"]),
        audience=str(payload["audience"]),
        palette=tuple(payload.get("palette", ())),
        typography=str(payload["typography"]),
        camera_language=str(payload["cameraLanguage"]),
        opening_rule=str(payload["openingRule"]),
        middle_rule=str(payload["middleRule"]),
        ending_rule=str(payload["endingRule"]),
        preferred_shots=tuple(payload.get("preferredShots", ())),
        preferred_actions=tuple(payload.get("preferredActions", ())),
        pacing=str(payload["pacing"]),
        product_priorities=tuple(payload.get("productPriorities", ())),
        forbidden_mismatches=tuple(payload.get("forbiddenMismatches", ())),
        research_note=str(payload["researchNote"]),
        expression_language=str(payload.get("expressionLanguage") or payload["tone"]),
        library_scope=library_scope,
        brand_id=(payload.get("brandId") or str(payload["id"]))
        if library_scope == "brand"
        else None,
        motion_energy=str(payload.get("motionEnergy", "standard")),
        primary_motion_pool=tuple(payload.get("primaryMotionPool", ())),
        micro_motion_pool=tuple(payload.get("microMotionPool", ())),
        expression_pool=tuple(payload.get("expressionPool", ())),
        camera_pool=tuple(payload.get("cameraPool", ())),
        forbidden_motion=tuple(payload.get("forbiddenMotion", ())),
        preferred_environment=tuple(payload.get("preferredEnvironment", ())),
        product_risk_rules=tuple(payload.get("productRiskRules", ())),
        dedupe_recent_count=int(payload.get("dedupeRecentCount", 5)),
        dedupe_combo_window=int(payload.get("dedupeComboWindow", 8)),
        dedupe_family_window=int(payload.get("dedupeFamilyWindow", 10)),
        dedupe_family_limit=int(payload.get("dedupeFamilyLimit", 3)),
    )


async def _overrides(session: AsyncSession, entry_type: str) -> list[CatalogEntry]:
    return list(
        await session.scalars(
            select(CatalogEntry)
            .where(CatalogEntry.entry_type == entry_type)
            .order_by(CatalogEntry.created_at, CatalogEntry.entry_id)
        )
    )


async def motion_action_library(session: AsyncSession) -> dict[str, MotionAction]:
    merged = dict(ACTION_LIBRARY)
    for entry in await _overrides(session, MOTION_ACTION):
        canonical_id = canonical_action_id(entry.entry_id)
        payload = dict(entry.payload_json)
        payload["id"] = canonical_id
        merged[canonical_id] = _motion_action(payload)
    return merged


async def list_merged_motion_actions(session: AsyncSession) -> tuple[MotionAction, ...]:
    return tuple((await motion_action_library(session)).values())


async def site_style_profile_library(session: AsyncSession) -> dict[str, SiteStyleProfile]:
    merged = dict(SITE_STYLE_PROFILES)
    for entry in await _overrides(session, SITE_STYLE_PROFILE):
        merged[entry.entry_id] = _site_style_profile(entry.payload_json)
    return merged


async def list_merged_site_style_profiles(
    session: AsyncSession,
    *,
    include_retired: bool = False,
) -> tuple[SiteStyleProfile, ...]:
    profiles = (await site_style_profile_library(session)).values()
    return tuple(profile for profile in profiles if include_retired or profile.status != "retired")


async def get_merged_site_style_profile(
    session: AsyncSession,
    profile_id: str,
    *,
    require_active: bool = False,
) -> SiteStyleProfile:
    profile = (await site_style_profile_library(session)).get(profile_id)
    if profile is None:
        raise ValueError(f"unknown site style profile: {profile_id}")
    if require_active and profile.status != "active":
        raise ValueError(f"site style profile is not active: {profile_id}")
    return profile


def next_patch_version(version: str) -> str:
    try:
        major, minor, patch = (
            int(part.split("-", 1)[0]) for part in version.split(".", maxsplit=2)
        )
    except (TypeError, ValueError):
        return "0.1.1"
    return f"{major}.{minor}.{patch + 1}"


async def save_catalog_entry(
    session: AsyncSession,
    *,
    entry_type: str,
    entry_id: str,
    payload: dict[str, Any],
    actor_id: uuid.UUID,
) -> None:
    entry = await session.scalar(
        select(CatalogEntry).where(
            CatalogEntry.entry_type == entry_type,
            CatalogEntry.entry_id == entry_id,
        )
    )
    now = datetime.now(UTC)
    if entry is None:
        entry = CatalogEntry(
            entry_type=entry_type,
            entry_id=entry_id,
            payload_json=payload,
            updated_by=actor_id,
            updated_at=now,
        )
        session.add(entry)
    else:
        entry.payload_json = payload
        entry.updated_by = actor_id
        entry.updated_at = now
