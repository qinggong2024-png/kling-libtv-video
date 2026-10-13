"""Preflight-only bridge for the director_fixed video execution boundary.

This module builds a read-only plan from the selected Creative Workflow
first-frame and storyboard sources. It deliberately stops before the legacy
video task service, Provider submission, billing, or production attempt.
"""

from __future__ import annotations

import uuid
from copy import deepcopy
from datetime import UTC, datetime
from typing import Any, Literal, NoReturn

from fastapi import HTTPException
from libtv_agent.creative.media_qualification import OFFLINE_SCOPE, is_offline_synthetic_output
from libtv_agent.creative.text_contract import validate_text_contract
from libtv_agent.creative.workflow import UNCERTAIN, digest
from libtv_agent.domain.enums import QualityDecisionStatus
from libtv_agent.domain.models import (
    CreativeRecord,
    CreativeTask,
    ImageGenerationBatch,
    ImageGenerationItem,
    ImageGenerationOutput,
    Product,
)
from libtv_agent.services.creative_workflow import (
    validate_asset,
    validate_product_version,
)
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

BRIDGE_KIND = "CREATIVE_DIRECTOR_FIXED_VIDEO_PREFLIGHT"
DIRECTOR_FIXED = "director_fixed"
SHOT_ID = "SHOT_01"


class CreativeVideoBridgeRejected(ValueError):
    """Stable service-layer rejection for a future API adapter."""

    def __init__(self, code: str, message: str | None = None) -> None:
        self.code = code
        self.message = message or code
        super().__init__(self.message)


class DirectorFixedSourceMapping(BaseModel):
    model_config = ConfigDict(extra="forbid")

    purpose: Literal["FIRST_FRAME", "VIDEO_STORYBOARD"]
    shot_id: str
    package_revision_id: str
    candidate_id: str
    batch_id: str
    item_id: str
    output_id: str
    source_sha256: str
    output_sha256: str
    object_key: str
    qualification_scope: Literal["OFFLINE_SYNTHETIC_ONLY"] = OFFLINE_SCOPE


class LockedPromptPreservation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    package_revision_id: str
    prompt: str
    prompt_hash: str
    preservation_hash: str
    text_contract_hash: str
    locks_hash: str
    text_contract: dict[str, Any]


class CreativeVideoBridgePlan(BaseModel):
    model_config = ConfigDict(extra="forbid")

    bridge_kind: Literal["CREATIVE_DIRECTOR_FIXED_VIDEO_PREFLIGHT"] = BRIDGE_KIND
    bridge_status: Literal["PREFLIGHT_READY"] = "PREFLIGHT_READY"
    execution_mode: Literal["director_fixed"] = DIRECTOR_FIXED
    idempotency_key: str
    validity_token: str
    state_version: int
    creative_task_id: str
    owner_id: str
    package_revision_id: str
    shot_id: Literal["SHOT_01"] = SHOT_ID
    first_frame: DirectorFixedSourceMapping
    storyboard: DirectorFixedSourceMapping
    source_image_hashes: dict[str, str]
    locked_prompt_preservation: LockedPromptPreservation
    provider_submission_allowed: Literal[False] = False
    deliverable_eligible: Literal[False] = False
    offline_synthetic_only: Literal[True] = True
    next_steps: list[
        Literal["REAL_VIDEO_PROVIDER_ADAPTER_REQUIRED", "HUMAN_PROVIDER_AUTHORIZATION_REQUIRED"]
    ]


def _reject(code: str) -> NoReturn:
    raise CreativeVideoBridgeRejected(code)


def _as_uuid(value: Any, code: str) -> uuid.UUID:
    try:
        return uuid.UUID(str(value))
    except (TypeError, ValueError, AttributeError):
        raise CreativeVideoBridgeRejected(code) from None


def _parse_expiry(value: Any) -> datetime:
    if not isinstance(value, str) or not value.strip():
        _reject("EXPIRY_INVALID")
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        _reject("EXPIRY_INVALID")
    if parsed.tzinfo is None:
        _reject("EXPIRY_INVALID")
    return parsed


def _active_package(
    snapshot: dict[str, Any],
    package: Any,
    *,
    purpose: str,
    shot_id: str,
    now: datetime,
) -> dict[str, Any]:
    if not isinstance(package, dict):
        _reject("PACKAGE_REQUIRED")
    if package.get("purpose", "FIRST_FRAME") != purpose or package.get("shot_id") != shot_id:
        _reject("PACKAGE_SCOPE_INVALID")
    package_id = package.get("package_id")
    if not isinstance(package_id, str) or not package_id:
        _reject("PACKAGE_REQUIRED")
    if package.get("expired") or package.get("status") in {"EXPIRED", "REVOKED"}:
        _reject("PACKAGE_EXPIRED")
    expires_at = package.get("expires_at", package.get("expiresAt"))
    if expires_at is not None and _parse_expiry(expires_at) <= now:
        _reject("PACKAGE_EXPIRED")
    contracts = snapshot.get("package_contracts")
    contract = contracts.get(package_id) if isinstance(contracts, dict) else None
    if (
        not isinstance(contract, dict)
        or not isinstance(contract.get("text_contract"), dict)
        or contract.get("text_contract", {}).get("package") != package
    ):
        _reject("PACKAGE_EXPIRED")
    return package


def _selected_source(
    snapshot: dict[str, Any],
    *,
    purpose: str,
    shot_id: str,
    owner_id: uuid.UUID,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    if purpose == "FIRST_FRAME":
        selection = snapshot.get("selection")
        candidates = snapshot.get("candidates")
        review = snapshot.get("latest_review")
    else:
        storyboard = snapshot.get("storyboard")
        if not isinstance(storyboard, dict):
            _reject("STORYBOARD_REQUIRED")
        selection = storyboard.get("selections", {}).get(shot_id)
        candidates = storyboard.get("candidates")
        review = storyboard.get("latest_reviews", {}).get(shot_id)
    if (
        not isinstance(selection, dict)
        or selection.get("purpose", "FIRST_FRAME") != purpose
        or selection.get("shot_id") != shot_id
        or selection.get("selected_by") != str(owner_id)
    ):
        _reject("SELECTION_REQUIRED")
    candidate = next(
        (
            value
            for value in candidates
            if (
                isinstance(value, dict)
                and value.get("candidate_id") == selection.get("candidate_id")
            )
        ),
        None,
    ) if isinstance(candidates, list) else None
    if candidate is None:
        _reject("CANDIDATE_NOT_FOUND")
    if (
        candidate.get("purpose", "FIRST_FRAME") != purpose
        or candidate.get("shot_id") != shot_id
        or candidate.get("package_id") != selection.get("package_id")
        or candidate.get("synthetic") is not True
        or candidate.get("qualified") is not True
    ):
        _reject("SOURCE_SELECTION_INVALID")
    if (
        not isinstance(review, dict)
        or review.get("candidate_id") != candidate.get("candidate_id")
        or review.get("scope", "FIRST_FRAME") != purpose
        or review.get("shot_id") != shot_id
        or review.get("reviewer_kind") != "HUMAN"
        or review.get("reviewer_id") != str(owner_id)
        or review.get("decision") != "QUALIFIED"
        or review.get("qualification_scope") != OFFLINE_SCOPE
    ):
        _reject("HUMAN_QUALIFICATION_REQUIRED")
    return selection, candidate, review


def _record_matches(
    records: list[CreativeRecord],
    *,
    kind: str,
    payload: dict[str, Any],
    record_key: str | None = None,
) -> bool:
    expected_hash = digest(payload)
    return any(
        row.kind == kind
        and (record_key is None or row.record_key == record_key)
        and row.content_hash == expected_hash
        and row.payload_json == payload
        for row in records
    )


def _get_authorization(
    records: list[CreativeRecord],
    authorization_id: Any,
    *,
    scope: str,
    package: dict[str, Any],
    now: datetime,
) -> dict[str, Any]:
    if not isinstance(authorization_id, str) or not authorization_id:
        _reject("AUTHORIZATION_REQUIRED")
    matches = [
        row.payload_json
        for row in records
        if row.kind == "authorization"
        and row.record_key == authorization_id
        and row.content_hash == digest(row.payload_json)
    ]
    if len(matches) != 1:
        _reject("AUTHORIZATION_REQUIRED")
    authorization = matches[0]
    if (
        authorization.get("scope", "FIRST_FRAME") != scope
        or authorization.get("package_id") != package["package_id"]
        or authorization.get("locks_hash") != package.get("locks_hash")
        or _parse_expiry(authorization.get("expires_at")) <= now
    ):
        _reject("AUTHORIZATION_SCOPE_INVALID")
    if scope == "VIDEO_STORYBOARD" and authorization.get("shot_ids") != [SHOT_ID]:
        _reject("AUTHORIZATION_SCOPE_INVALID")
    return authorization


async def _load_media_source(
    session: AsyncSession,
    *,
    owner_id: uuid.UUID,
    task: CreativeTask,
    package: dict[str, Any],
    candidate: dict[str, Any],
    selection: dict[str, Any],
    purpose: str,
    shot_id: str,
    asset_sha256: str,
) -> tuple[DirectorFixedSourceMapping, ImageGenerationOutput]:
    mapping = {
        key: candidate.get(key)
        for key in ("batch_id", "item_id", "output_id")
    }
    ids = {key: _as_uuid(value, "SOURCE_MAPPING_INVALID") for key, value in mapping.items()}
    row = (
        await session.execute(
            select(ImageGenerationOutput, ImageGenerationItem, ImageGenerationBatch)
            .join(ImageGenerationItem, ImageGenerationItem.id == ImageGenerationOutput.item_id)
            .join(ImageGenerationBatch, ImageGenerationBatch.id == ImageGenerationItem.batch_id)
            .where(
                ImageGenerationOutput.id == ids["output_id"],
                ImageGenerationItem.id == ids["item_id"],
                ImageGenerationBatch.id == ids["batch_id"],
                ImageGenerationBatch.user_id == owner_id,
            )
            .execution_options(populate_existing=True)
        )
    ).first()
    output = row[0] if row else None
    item = row[1] if row else None
    batch = row[2] if row else None
    if output is None or item is None or batch is None:
        _reject("SOURCE_MAPPING_NOT_FOUND")
    if (
        output.item_id != item.id
        or item.batch_id != batch.id
        or batch.user_id != task.user_id
        or batch.status in UNCERTAIN
        or item.status in UNCERTAIN
    ):
        _reject("SOURCE_MAPPING_MISMATCH")
    if batch.status != "COMPLETED" or item.status != "COMPLETED":
        _reject("SOURCE_EXECUTION_NOT_COMPLETED")
    if not is_offline_synthetic_output(output, item=item, batch=batch):
        _reject("OFFLINE_SOURCE_REQUIRED")
    for source in (batch.request_json, item.request_json):
        if (
            source.get("creativeTaskId") != str(task.id)
            or source.get("packageId") != package["package_id"]
            or source.get("purpose") != purpose
            or source.get("shotId") != shot_id
        ):
            _reject("SOURCE_MAPPING_MISMATCH")
    expected_kind = (
        "CREATIVE_STORYBOARD"
        if purpose == "VIDEO_STORYBOARD"
        else "CREATIVE_FIRST_FRAME"
    )
    if (
        item.kind != expected_kind
        or item.provider_task_id != candidate.get("candidate_id")
        or item.prompt != package.get("prompt")
        or batch.request_hash != digest(package)
        or output.qualification_status is not QualityDecisionStatus.PENDING
        or output.sha256 != asset_sha256
        or candidate.get("sha256") != asset_sha256
        or not output.object_key
        or candidate.get("object_key") != output.object_key
        or output.remote_url.lower().startswith("fake://") is False
    ):
        _reject("SOURCE_MAPPING_MISMATCH")
    if selection.get("batch_id") != str(batch.id) or selection.get("item_id") != str(item.id):
        _reject("SOURCE_MAPPING_MISMATCH")
    if selection.get("output_id") != str(output.id):
        _reject("SOURCE_MAPPING_MISMATCH")
    return (
        DirectorFixedSourceMapping(
            purpose=purpose,
            shot_id=shot_id,
            package_revision_id=package["package_id"],
            candidate_id=candidate["candidate_id"],
            batch_id=str(batch.id),
            item_id=str(item.id),
            output_id=str(output.id),
            source_sha256=asset_sha256,
            output_sha256=output.sha256,
            object_key=output.object_key,
        ),
        output,
    )


def _attempt(
    records: list[CreativeRecord],
    candidate: dict[str, Any],
    *,
    package: dict[str, Any],
    purpose: str,
    shot_id: str,
) -> dict[str, Any]:
    matches = [
        row.payload_json
        for row in records
        if row.kind == "attempt"
        and row.record_key == candidate.get("candidate_id")
        and row.content_hash == digest(row.payload_json)
    ]
    if len(matches) != 1:
        _reject("EXECUTION_UNKNOWN")
    attempt = matches[0]
    if (
        attempt.get("status") != "SUCCEEDED"
        or attempt.get("scope", "FIRST_FRAME") != purpose
        or attempt.get("shot_id") != shot_id
        or attempt.get("package_id") != package["package_id"]
        or attempt.get("input_hash") != digest(package)
        or attempt.get("authorization_id") != candidate.get("authorization_id")
        or attempt.get("synthetic") is not True
    ):
        _reject("SOURCE_MAPPING_MISMATCH")
    return attempt


def _locked_prompt_preservation(
    snapshot: dict[str, Any], package: dict[str, Any]
) -> LockedPromptPreservation:
    package_id = package["package_id"]
    contract = snapshot["package_contracts"][package_id]["text_contract"]
    if contract.get("package") != package or not contract.get("contract_hash"):
        _reject("CREATIVE_EVIDENCE_MISMATCH")
    return LockedPromptPreservation(
        package_revision_id=package_id,
        prompt=package["prompt"],
        prompt_hash=digest(package["prompt"]),
        preservation_hash=package["preservation_hash"],
        text_contract_hash=contract["contract_hash"],
        locks_hash=package["locks_hash"],
        text_contract=deepcopy(contract),
    )


def _validate_locked_package(snapshot: dict[str, Any], package: dict[str, Any]) -> None:
    package_id = package.get("package_id")
    contracts = snapshot.get("package_contracts")
    stored = contracts.get(package_id) if isinstance(contracts, dict) else None
    if not isinstance(stored, dict):
        _reject("TEXT_CONTRACT_MISSING")
    frozen = stored.get("text_contract")
    registry = stored.get("registry_snapshot")
    if not isinstance(frozen, dict) or not isinstance(registry, dict):
        _reject("TEXT_CONTRACT_MISSING")
    result = validate_text_contract(
        snapshot.get("plan", {}),
        package,
        frozen,
        registry,
        snapshot.get("facts_snapshot", {}),
    )
    if not result["valid"]:
        _reject("TEXT_CONTRACT_REJECTED")


def _source_fingerprint(
    task: CreativeTask,
    snapshot: dict[str, Any],
    first_frame: DirectorFixedSourceMapping,
    storyboard: DirectorFixedSourceMapping,
    locked: LockedPromptPreservation,
) -> str:
    return digest(
        {
            "task_id": str(task.id),
            "state_version": task.state_version,
            "status": task.status,
            "snapshot_hash": digest(snapshot),
            "first_frame": first_frame.model_dump(mode="json"),
            "storyboard": storyboard.model_dump(mode="json"),
            "locked": locked.model_dump(mode="json"),
        }
    )


async def plan_creative_video_bridge(
    session: AsyncSession,
    task: CreativeTask,
    *,
    owner_id: uuid.UUID,
    object_store: Any,
    now: datetime | None = None,
) -> CreativeVideoBridgePlan:
    """Validate director_fixed inputs without creating a video task or attempt."""

    current_time = now or datetime.now(UTC)
    if current_time.tzinfo is None:
        current_time = current_time.replace(tzinfo=UTC)
    current = await session.scalar(
        select(CreativeTask)
        .where(CreativeTask.id == task.id, CreativeTask.user_id == owner_id)
        .execution_options(populate_existing=True)
    )
    if current is None:
        _reject("OWNER_MISMATCH")
    task = current
    if task.status in UNCERTAIN or task.snapshot_json.get("execution_state") in UNCERTAIN:
        _reject("EXECUTION_UNKNOWN")
    snapshot = task.snapshot_json if isinstance(task.snapshot_json, dict) else {}
    if snapshot.get("stopped"):
        _reject("USER_STOPPED")
    if task.status != "STORYBOARD_REVIEW":
        _reject("TASK_STAGE_INVALID")
    asset = snapshot.get("asset")
    if not isinstance(asset, dict):
        _reject("CANONICAL_SOURCE_REQUIRED")
    if asset.get("revoked"):
        _reject("ASSET_REVOKED")
    if str(asset.get("owner_id")) != str(owner_id):
        _reject("OWNER_MISMATCH")
    source_sha256 = asset.get("sha256")
    if not isinstance(source_sha256, str) or len(source_sha256) != 64:
        _reject("SOURCE_HASH_REQUIRED")
    if snapshot.get("owner_id") is not None and str(snapshot["owner_id"]) != str(owner_id):
        _reject("OWNER_MISMATCH")

    first_package = _active_package(
        snapshot,
        snapshot.get("package"),
        purpose="FIRST_FRAME",
        shot_id="FIRST_FRAME",
        now=current_time,
    )
    storyboard_state = snapshot.get("storyboard")
    storyboard_package = (
        storyboard_state.get("packages", {}).get(SHOT_ID)
        if isinstance(storyboard_state, dict)
        else None
    )
    storyboard_package = _active_package(
        snapshot,
        storyboard_package,
        purpose="VIDEO_STORYBOARD",
        shot_id=SHOT_ID,
        now=current_time,
    )
    first_selection, first_candidate, first_review = _selected_source(
        snapshot, purpose="FIRST_FRAME", shot_id="FIRST_FRAME", owner_id=owner_id
    )
    storyboard_selection, storyboard_candidate, storyboard_review = _selected_source(
        snapshot, purpose="VIDEO_STORYBOARD", shot_id=SHOT_ID, owner_id=owner_id
    )
    if (
        storyboard_package.get("source_first_frame_candidate_id")
        != first_candidate.get("candidate_id")
        or storyboard_candidate.get(
            "source_first_frame_candidate_id",
            first_candidate.get("candidate_id"),
        )
        != first_candidate.get("candidate_id")
    ):
        _reject("FIRST_FRAME_SOURCE_MISMATCH")
    try:
        await validate_asset(snapshot, object_store)
        await validate_product_version(session, task, snapshot)
        _validate_locked_package(deepcopy(snapshot), first_package)
        _validate_locked_package(deepcopy(snapshot), storyboard_package)
    except HTTPException as exc:
        raise CreativeVideoBridgeRejected(exc.detail["code"]) from exc
    product = await session.scalar(
        select(Product.id).where(Product.id == task.product_id, Product.user_id == owner_id)
    )
    if product is None:
        _reject("OWNER_MISMATCH")

    records = list(
        await session.scalars(
            select(CreativeRecord).where(CreativeRecord.task_id == task.id)
        )
    )
    for package in (first_package, storyboard_package):
        if not _record_matches(records, kind="package", payload=package):
            _reject("CREATIVE_EVIDENCE_MISMATCH")
    for review in (first_review, storyboard_review):
        if not _record_matches(records, kind="review", payload=review):
            _reject("CREATIVE_EVIDENCE_MISMATCH")
    for selection in (first_selection, storyboard_selection):
        if not _record_matches(records, kind="selection", payload=selection):
            _reject("CREATIVE_EVIDENCE_MISMATCH")
    first_auth = _get_authorization(
        records,
        first_candidate.get("authorization_id"),
        scope="FIRST_FRAME",
        package=first_package,
        now=current_time,
    )
    storyboard_auth = _get_authorization(
        records,
        storyboard_candidate.get("authorization_id"),
        scope="VIDEO_STORYBOARD",
        package=storyboard_package,
        now=current_time,
    )
    if storyboard_auth.get("parent_authorization_id") != first_auth.get("authorization_id"):
        _reject("AUTHORIZATION_CHAIN_INVALID")
    _attempt(
        records,
        first_candidate,
        package=first_package,
        purpose="FIRST_FRAME",
        shot_id="FIRST_FRAME",
    )
    _attempt(
        records,
        storyboard_candidate,
        package=storyboard_package,
        purpose="VIDEO_STORYBOARD",
        shot_id=SHOT_ID,
    )
    first_mapping, first_output = await _load_media_source(
        session,
        owner_id=owner_id,
        task=task,
        package=first_package,
        candidate=first_candidate,
        selection=first_selection,
        purpose="FIRST_FRAME",
        shot_id="FIRST_FRAME",
        asset_sha256=source_sha256,
    )
    storyboard_mapping, storyboard_output = await _load_media_source(
        session,
        owner_id=owner_id,
        task=task,
        package=storyboard_package,
        candidate=storyboard_candidate,
        selection=storyboard_selection,
        purpose="VIDEO_STORYBOARD",
        shot_id=SHOT_ID,
        asset_sha256=source_sha256,
    )
    if (
        len(
            {
                first_mapping.candidate_id,
                storyboard_mapping.candidate_id,
                first_mapping.batch_id,
                storyboard_mapping.batch_id,
                first_mapping.item_id,
                storyboard_mapping.item_id,
                first_mapping.output_id,
                storyboard_mapping.output_id,
            }
        )
        != 8
    ):
        _reject("SOURCE_MAPPING_COLLISION")
    locked = _locked_prompt_preservation(snapshot, storyboard_package)
    bridge_key = f"creative-video-bridge:{task.id}:{storyboard_package['package_id']}:{SHOT_ID}"
    plan = CreativeVideoBridgePlan(
        idempotency_key=bridge_key,
        validity_token="pending",
        state_version=task.state_version,
        creative_task_id=str(task.id),
        owner_id=str(owner_id),
        package_revision_id=storyboard_package["package_id"],
        first_frame=first_mapping,
        storyboard=storyboard_mapping,
        source_image_hashes={
            "canonical_product": source_sha256,
            "first_frame_output": first_output.sha256,
            "storyboard_output": storyboard_output.sha256,
        },
        locked_prompt_preservation=locked,
        next_steps=[
            "REAL_VIDEO_PROVIDER_ADAPTER_REQUIRED",
            "HUMAN_PROVIDER_AUTHORIZATION_REQUIRED",
        ],
    )
    plan.validity_token = _source_fingerprint(
        task, snapshot, first_mapping, storyboard_mapping, locked
    )
    return plan


async def assert_creative_video_bridge_current(
    session: AsyncSession,
    task: CreativeTask,
    plan: CreativeVideoBridgePlan,
    *,
    owner_id: uuid.UUID,
    object_store: Any,
    now: datetime | None = None,
) -> CreativeVideoBridgePlan:
    """Revalidate a plan so a stale source cannot be submitted later."""

    if plan.creative_task_id != str(task.id) or plan.owner_id != str(owner_id):
        _reject("BRIDGE_PLAN_STALE")
    current = await plan_creative_video_bridge(
        session, task, owner_id=owner_id, object_store=object_store, now=now
    )
    if current != plan:
        _reject("BRIDGE_PLAN_STALE")
    return current
