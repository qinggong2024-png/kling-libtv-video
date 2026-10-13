"""Preflight-only bridge from a qualified Creative first frame to image production.

This module intentionally stops before the ordinary image submission boundary.  It
validates that the Creative Workflow selection is still usable as an input to a
future real Provider adapter, but it never submits, qualifies, or delivers media.
"""

from __future__ import annotations

import uuid
from copy import deepcopy
from datetime import UTC, datetime
from typing import Any, Literal, NoReturn

from fastapi import HTTPException
from libtv_agent.creative.media_qualification import OFFLINE_SCOPE, is_offline_synthetic_output
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
    validate_package_contract,
    validate_product_version,
)
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

BRIDGE_KIND = "CREATIVE_IMAGE_PROVIDER_PREFLIGHT"


class CreativeImageBridgeRejected(ValueError):
    """Stable service-layer rejection that an API adapter can map to HTTP 409."""

    def __init__(self, code: str, message: str | None = None) -> None:
        self.code = code
        self.message = message or code
        super().__init__(self.message)


class BridgeSourceMapping(BaseModel):
    model_config = ConfigDict(extra="forbid")

    batch_id: str
    item_id: str
    output_id: str


class CreativeImageBridgePlan(BaseModel):
    model_config = ConfigDict(extra="forbid")

    bridge_kind: Literal["CREATIVE_IMAGE_PROVIDER_PREFLIGHT"] = BRIDGE_KIND
    bridge_status: Literal["PREFLIGHT_READY"] = "PREFLIGHT_READY"
    idempotency_key: str
    validity_token: str
    state_version: int
    creative_task_id: str
    owner_id: str
    package_revision_id: str
    candidate_id: str
    purpose: Literal["FIRST_FRAME"] = "FIRST_FRAME"
    shot_id: Literal["FIRST_FRAME"] = "FIRST_FRAME"
    source_type: Literal["CREATIVE_FIRST_FRAME"] = "CREATIVE_FIRST_FRAME"
    qualification_scope: Literal["OFFLINE_SYNTHETIC_ONLY"] = OFFLINE_SCOPE
    human_qualification: Literal["QUALIFIED"] = "QUALIFIED"
    source_mapping: BridgeSourceMapping
    provider_submission_allowed: Literal[False] = False
    ordinary_image_output_qualified: Literal[False] = False
    deliverable_eligible: Literal[False] = False
    next_steps: list[
        Literal["REAL_PROVIDER_ADAPTER_REQUIRED", "HUMAN_PROVIDER_AUTHORIZATION_REQUIRED"]
    ]


def _reject(code: str) -> NoReturn:
    raise CreativeImageBridgeRejected(code)


def _as_uuid(value: Any, code: str) -> uuid.UUID:
    try:
        return uuid.UUID(str(value))
    except (TypeError, ValueError, AttributeError):
        raise CreativeImageBridgeRejected(code) from None


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


def _current_package(snapshot: dict[str, Any]) -> dict[str, Any]:
    package = snapshot.get("package")
    if not isinstance(package, dict):
        _reject("PACKAGE_REQUIRED")
    if package.get("purpose", "FIRST_FRAME") != "FIRST_FRAME":
        _reject("PACKAGE_SCOPE_INVALID")
    if package.get("shot_id", "FIRST_FRAME") != "FIRST_FRAME":
        _reject("PACKAGE_SCOPE_INVALID")
    package_id = package.get("package_id")
    if not isinstance(package_id, str) or not package_id:
        _reject("PACKAGE_REQUIRED")
    contracts = snapshot.get("package_contracts")
    contract = contracts.get(package_id) if isinstance(contracts, dict) else None
    if not isinstance(contract, dict) or not isinstance(contract.get("text_contract"), dict):
        _reject("PACKAGE_EXPIRED")
    if package.get("expired") or package.get("status") in {"EXPIRED", "REVOKED"}:
        _reject("PACKAGE_EXPIRED")
    if contract.get("expired") or contract.get("status") in {"EXPIRED", "REVOKED"}:
        _reject("PACKAGE_EXPIRED")
    return package


def _current_first_frame(
    snapshot: dict[str, Any], package: dict[str, Any], owner_id: uuid.UUID
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    selection = snapshot.get("selection")
    if not isinstance(selection, dict) or selection.get("purpose", "FIRST_FRAME") != "FIRST_FRAME":
        _reject("FIRST_FRAME_SELECTION_REQUIRED")
    if selection.get("shot_id") != "FIRST_FRAME":
        _reject("FIRST_FRAME_SELECTION_REQUIRED")

    candidate_id = selection.get("candidate_id")
    candidates = snapshot.get("candidates")
    candidate = next(
        (
            value
            for value in candidates
            if isinstance(value, dict) and value.get("candidate_id") == candidate_id
        ),
        None,
    ) if isinstance(candidates, list) else None
    if candidate is None:
        _reject("CANDIDATE_NOT_FOUND")
    if (
        candidate.get("purpose", "FIRST_FRAME") != "FIRST_FRAME"
        or candidate.get("shot_id") != "FIRST_FRAME"
        or candidate.get("package_id") != package.get("package_id")
        or selection.get("package_id") != package.get("package_id")
    ):
        _reject("STALE_CANDIDATE_PACKAGE")
    if candidate.get("synthetic") is not True:
        _reject("CREATIVE_SOURCE_REQUIRED")

    review = snapshot.get("latest_review")
    if not isinstance(review, dict) or review.get("candidate_id") != candidate_id:
        _reject("HUMAN_QUALIFICATION_REQUIRED")
    if (
        review.get("reviewer_kind") != "HUMAN"
        or review.get("decision") != "QUALIFIED"
        or review.get("qualification_scope") != OFFLINE_SCOPE
        or candidate.get("qualified") is not True
        or review.get("scope", "FIRST_FRAME") != "FIRST_FRAME"
        or review.get("shot_id") != "FIRST_FRAME"
        or review.get("reviewer_id") != str(owner_id)
    ):
        _reject("HUMAN_QUALIFICATION_REQUIRED")
    if selection.get("selected_by") != str(owner_id):
        _reject("SELECTION_OWNER_MISMATCH")
    return selection, candidate, review


def _validate_snapshot(
    task: CreativeTask,
    *,
    owner_id: uuid.UUID,
    now: datetime,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any]]:
    if task.user_id != owner_id:
        _reject("OWNER_MISMATCH")
    snapshot = task.snapshot_json if isinstance(task.snapshot_json, dict) else {}
    snapshot_owner = snapshot.get("owner_id")
    if snapshot_owner is not None and str(snapshot_owner) != str(owner_id):
        _reject("OWNER_MISMATCH")
    if task.status in UNCERTAIN or snapshot.get("execution_state") in UNCERTAIN:
        _reject("EXECUTION_UNKNOWN")
    if snapshot.get("stopped"):
        _reject("USER_STOPPED")
    asset = snapshot.get("asset")
    if not isinstance(asset, dict):
        _reject("CANONICAL_SOURCE_REQUIRED")
    if asset.get("revoked"):
        _reject("ASSET_REVOKED")
    if str(asset.get("owner_id")) != str(owner_id):
        _reject("OWNER_MISMATCH")
    if task.status != "IMAGE_REVIEW":
        _reject("TASK_STAGE_INVALID")
    source_hash = asset.get("sha256")
    if not isinstance(source_hash, str) or len(source_hash) != 64:
        _reject("SOURCE_HASH_REQUIRED")

    package = _current_package(snapshot)
    expiry_value = package.get("expires_at", package.get("expiresAt"))
    if expiry_value is not None and _parse_expiry(expiry_value) <= now:
        _reject("PACKAGE_EXPIRED")
    selection, candidate, review = _current_first_frame(snapshot, package, owner_id)
    return snapshot, asset, package, candidate, {"selection": selection, "review": review}


def _source_fingerprint(
    task: CreativeTask,
    snapshot: dict[str, Any],
    package: dict[str, Any],
    candidate: dict[str, Any],
    selection: dict[str, Any],
    review: dict[str, Any],
    batch: ImageGenerationBatch,
    item: ImageGenerationItem,
    output: ImageGenerationOutput,
) -> str:
    return digest(
        {
            "task_id": str(task.id),
            "state_version": task.state_version,
            "task_status": task.status,
            "snapshot_hash": digest(snapshot),
            "package": package,
            "candidate": candidate,
            "selection": selection,
            "review": review,
            "batch_id": str(batch.id),
            "batch_status": batch.status,
            "batch_provider": batch.provider,
            "batch_request": batch.request_json,
            "batch_request_hash": batch.request_hash,
            "item_id": str(item.id),
            "item_status": item.status,
            "item_request": item.request_json,
            "provider_task_id": item.provider_task_id,
            "item_prompt": item.prompt,
            "output_id": str(output.id),
            "output_status": output.qualification_status.value,
            "output_sha256": output.sha256,
            "output_object_key": output.object_key,
            "output_remote_url": output.remote_url,
            "output_quality_gates": output.quality_gates_json,
        }
    )


async def plan_creative_image_bridge(
    session: AsyncSession,
    task: CreativeTask,
    *,
    owner_id: uuid.UUID,
    object_store: Any,
    now: datetime | None = None,
) -> CreativeImageBridgePlan:
    """Validate a selected Fake first frame without crossing the Provider boundary."""

    current_time = now or datetime.now(UTC)
    if current_time.tzinfo is None:
        current_time = current_time.replace(tzinfo=UTC)
    task = await session.scalar(
        select(CreativeTask).where(
            CreativeTask.id == task.id, CreativeTask.user_id == owner_id,
        ).execution_options(populate_existing=True)
    )
    if task is None:
        _reject("OWNER_MISMATCH")
    snapshot, asset, package, candidate, state = _validate_snapshot(
        task, owner_id=owner_id, now=current_time
    )
    selection = state["selection"]
    review = state["review"]
    product = await session.scalar(select(Product.id).where(
        Product.id == task.product_id, Product.user_id == owner_id,
    ))
    if product is None:
        _reject("OWNER_MISMATCH")
    try:
        await validate_asset(snapshot, object_store)
        await validate_product_version(session, task, snapshot)
        validate_package_contract(deepcopy(snapshot), package, "image-bridge-preflight")
    except HTTPException as exc:
        raise CreativeImageBridgeRejected(exc.detail["code"]) from exc

    records = list(await session.scalars(
        select(CreativeRecord).where(CreativeRecord.task_id == task.id)
    ))
    for kind, payload in (("package", package), ("review", review), ("selection", selection)):
        if not any(
            record.kind == kind and record.content_hash == digest(payload)
            and record.payload_json == payload for record in records
        ):
            _reject("CREATIVE_EVIDENCE_MISMATCH")
    attempts = [
        record.payload_json for record in records
        if record.kind == "attempt" and record.record_key == candidate["candidate_id"]
        and record.content_hash == digest(record.payload_json)
    ]
    if len(attempts) != 1 or attempts[0].get("status") != "SUCCEEDED":
        _reject("EXECUTION_UNKNOWN")
    attempt = attempts[0]
    if attempt.get("package_id") != package["package_id"] or attempt.get("input_hash") != digest(
        package
    ):
        _reject("SOURCE_MAPPING_MISMATCH")
    authorizations = [
        record.payload_json for record in records
        if record.kind == "authorization"
        and record.record_key == attempt.get("authorization_id")
        and record.content_hash == digest(record.payload_json)
    ]
    if len(authorizations) != 1:
        _reject("AUTHORIZATION_REQUIRED")
    authorization = authorizations[0]
    if (
        authorization.get("scope", "FIRST_FRAME") != "FIRST_FRAME"
        or authorization.get("locks_hash") != package["locks_hash"]
        or candidate.get("authorization_id") != attempt.get("authorization_id")
    ):
        _reject("AUTHORIZATION_SCOPE_INVALID")
    if _parse_expiry(authorization.get("expires_at")) <= current_time:
        _reject("AUTH_EXPIRED")
    mapping = {
        key: candidate.get(key)
        for key in ("batch_id", "item_id", "output_id")
    }
    ids = {
        key: _as_uuid(value, "SOURCE_MAPPING_INVALID")
        for key, value in mapping.items()
    }
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
            ).execution_options(populate_existing=True)
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
        or not is_offline_synthetic_output(output, item=item, batch=batch)
    ):
        _reject("SOURCE_MAPPING_MISMATCH")
    if batch.status in UNCERTAIN or item.status in UNCERTAIN:
        _reject("EXECUTION_UNKNOWN")
    if batch.status != "COMPLETED" or item.status != "COMPLETED":
        _reject("SOURCE_EXECUTION_NOT_COMPLETED")
    for source in (batch.request_json, item.request_json):
        if (
            source.get("creativeTaskId") != str(task.id)
            or source.get("packageId") != package["package_id"]
            or source.get("purpose") != "FIRST_FRAME"
            or source.get("shotId") != "FIRST_FRAME"
        ):
            _reject("SOURCE_MAPPING_MISMATCH")
    if (
        item.kind != "CREATIVE_FIRST_FRAME"
        or item.provider_task_id != candidate["candidate_id"]
        or item.prompt != package["prompt"]
        or batch.request_hash != digest(package)
    ):
        _reject("SOURCE_MAPPING_MISMATCH")
    if output.qualification_status is not QualityDecisionStatus.PENDING:
        _reject("CREATIVE_OUTPUT_ORDINARY_QUALIFICATION_FORBIDDEN")
    if (
        output.sha256 != asset["sha256"]
        or attempt.get("output_hash") != asset["sha256"]
        or candidate.get("sha256") != asset["sha256"]
        or not output.object_key
        or candidate.get("object_key") != output.object_key
        or output.object_key != asset.get("object_key")
        or snapshot.get("plan", {}).get("source_hash") != asset["sha256"]
        or snapshot.get("facts_snapshot", {}).get("source_hash", asset["sha256"])
        != asset["sha256"]
    ):
        _reject("SOURCE_HASH_MISMATCH")
    if selection.get("batch_id") != str(batch.id) or selection.get("item_id") != str(item.id):
        _reject("SOURCE_MAPPING_MISMATCH")
    if selection.get("output_id") != str(output.id):
        _reject("SOURCE_MAPPING_MISMATCH")

    source_mapping = BridgeSourceMapping(
        batch_id=str(batch.id), item_id=str(item.id), output_id=str(output.id)
    )
    bridge_key = (
        f"creative-image-bridge:{task.id}:{package['package_id']}:{candidate['candidate_id']}"
    )
    validity_token = _source_fingerprint(
        task, snapshot, package, candidate, selection, review, batch, item, output
    )
    return CreativeImageBridgePlan(
        idempotency_key=bridge_key,
        validity_token=validity_token,
        state_version=task.state_version,
        creative_task_id=str(task.id),
        owner_id=str(owner_id),
        package_revision_id=package["package_id"],
        candidate_id=candidate["candidate_id"],
        source_mapping=source_mapping,
        next_steps=[
            "REAL_PROVIDER_ADAPTER_REQUIRED",
            "HUMAN_PROVIDER_AUTHORIZATION_REQUIRED",
        ],
    )


async def assert_creative_image_bridge_current(
    session: AsyncSession,
    task: CreativeTask,
    plan: CreativeImageBridgePlan,
    *,
    owner_id: uuid.UUID,
    object_store: Any,
    now: datetime | None = None,
) -> CreativeImageBridgePlan:
    """Revalidate a plan so a stale task/source cannot be reused."""

    if plan.creative_task_id != str(task.id) or plan.owner_id != str(owner_id):
        _reject("BRIDGE_PLAN_STALE")
    current = await plan_creative_image_bridge(
        session, task, owner_id=owner_id, object_store=object_store, now=now
    )
    if current != plan:
        _reject("BRIDGE_PLAN_STALE")
    return current
