"""Bind immutable Director packages to the existing image/video request records."""
from __future__ import annotations

import uuid
from copy import deepcopy

from libtv_agent.creative.package_contract import project_creative_package
from libtv_agent.creative.workflow import digest
from libtv_agent.domain.enums import ProductLicenseStatus, ProductVersionStatus
from libtv_agent.domain.models import CreativeTask, Product, ProductVersion
from libtv_agent.domain.schemas import CreativePackageInput
from libtv_agent.services.product_versions import version_content
from libtv_agent.services.runtime_control import RuntimeControlBlockedError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession


class CreativeProductionBlockedError(RuntimeControlBlockedError):
    pass


def blocked(code: str, message: str) -> None:
    raise CreativeProductionBlockedError(code, message)


async def resolve_production_package(
    session: AsyncSession, owner_id: uuid.UUID, context: CreativePackageInput,
) -> tuple[dict, dict]:
    task = await session.scalar(
        select(CreativeTask).join(Product, Product.id == CreativeTask.product_id).where(
            CreativeTask.id == context.workflow_id,
            CreativeTask.user_id == owner_id,
            Product.user_id == owner_id,
        ).execution_options(populate_existing=True)
    )
    if task is None:
        blocked("CREATIVE_PACKAGE_NOT_FOUND", "workflow and product must belong to the caller")
    snapshot = task.snapshot_json
    asset = snapshot.get("asset", {})
    if asset.get("owner_id") != str(owner_id) or asset.get("revoked"):
        blocked("CREATIVE_SOURCE_UNAVAILABLE", "canonical source is unavailable")
    if snapshot.get("stopped") or snapshot.get("execution_state") in {"UNKNOWN", "WRITE_UNCERTAIN"}:
        blocked(
            "CREATIVE_WORKFLOW_BLOCKED", "stopped or uncertain workflow cannot start production",
        )
    active = [
        snapshot.get("package", {}),
        *snapshot.get("storyboard", {}).get("packages", {}).values(),
    ]
    package = next((p for p in active if p.get("package_id") == context.package_id), None)
    if package is None or package.get("shot_id") != context.shot_id:
        blocked("CREATIVE_PACKAGE_STALE", "package must be the current package for this shot")
    version = await session.scalar(
        select(ProductVersion).where(ProductVersion.product_id == task.product_id)
        .order_by(ProductVersion.version_number.desc()).limit(1)
        .execution_options(populate_existing=True)
    )
    if version is None or digest(version_content(version)) != digest(
        snapshot.get("product_version", {})
    ):
        blocked("CREATIVE_PRODUCT_VERSION_STALE", "package product version is no longer current")
    if (
        version.status != ProductVersionStatus.APPROVED
        or version.license_status != ProductLicenseStatus.VERIFIED
    ):
        blocked("CREATIVE_PRODUCT_NOT_APPROVED", "production requires approved, licensed product")
    try:
        projection = project_creative_package(snapshot, package_id=context.package_id)
    except (ValueError, TypeError, KeyError) as exc:
        raise CreativeProductionBlockedError(
            "CREATIVE_PACKAGE_INVALID", "frozen package integrity check failed",
        ) from exc
    bound = {
        **context.model_dump(mode="json", by_alias=True),
        "packageRevision": package["revision"],
        "productId": str(task.product_id),
        "productVersionId": str(version.id),
        "sourceHash": asset["sha256"],
        "sourceObjectKey": asset["object_key"],
        "packageHash": digest(package),
        "contractHash": projection["provenance"]["originEvidence"]["packageContract"][
            "text_contract"
        ]["contract_hash"],
        "planningEvidence": snapshot.get("plan", {}).get("evidence"),
    }
    return bound, projection


def production_prompt(prompt: str) -> str:
    # Strip only the legacy planning transport marker; preserve every creative constraint.
    for prefix in ("FAKE ONLY. ", "FAKE SOURCE. "):
        if prompt.startswith(prefix):
            return prompt[len(prefix):]
    return prompt


async def validate_bound_package(
    session: AsyncSession, owner_id: uuid.UUID, bound: dict,
) -> None:
    try:
        context = CreativePackageInput.model_validate({
            key: bound[key] for key in ("workflowId", "packageId", "shotId")
        })
    except (ValueError, TypeError, KeyError) as exc:
        raise CreativeProductionBlockedError(
            "CREATIVE_PACKAGE_INVALID", "production package binding is invalid",
        ) from exc
    current, _ = await resolve_production_package(
        session, owner_id, context,
    )
    if any(current[key] != bound.get(key) for key in current):
        blocked("CREATIVE_PACKAGE_CHANGED", "production package binding no longer matches")


def source_lineage(output, item, batch) -> dict:
    context = (item.request_json or {}).get("creativePackage") or (
        batch.request_json or {}
    ).get("creativePackage")
    return {
        "sourceImageOutputId": str(output.id),
        "imageItemId": str(item.id),
        "imageBatchId": str(batch.id),
        "sourceImageHash": output.sha256,
        **({"creativePackage": deepcopy(context)} if context else {}),
    }
