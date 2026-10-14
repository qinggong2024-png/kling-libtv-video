"""Read-only preflight for an authorized future Provider submission.

MVP-3A keeps media as object keys.  This module verifies that immutable request
contract again, checks explicit offline capability and budget declarations, and
materializes each reference into a short-lived adapter input directory.  It
does not discover capabilities, call a Provider, reserve quota, or write a
production record.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import re
import shutil
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Literal, NoReturn

from libtv_agent.config import Settings
from libtv_agent.creative.workflow import digest
from libtv_agent.domain.enums import ProductLicenseStatus, ProductVersionStatus, UserRole
from libtv_agent.domain.models import (
    CreativeTask,
    ProductVersion,
    RuntimeConfigVersion,
    User,
    UserDailyPointsSummary,
)
from libtv_agent.services.creative_provider_requests import (
    CreativeImageProviderRequest,
    CreativeProviderRequestRejected,
    CreativeVideoProviderRequest,
    ExecutionSlot,
    FrozenContract,
    ProviderRequestContract,
    RunMode,
    assert_creative_provider_request_current,
)
from libtv_agent.services.generation_safety import paid_generation_authorized
from libtv_agent.services.image_quota import images_submitted_on
from libtv_agent.services.points import business_date
from PIL import Image, UnidentifiedImageError
from pydantic import Field, ValidationError, model_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

ProviderRequest = CreativeImageProviderRequest | CreativeVideoProviderRequest


class CreativeProviderPreflightRejected(ValueError):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


class ProviderCapabilityDeclaration(FrozenContract):
    """A static capability snapshot supplied by configuration or an operator."""

    declaration_id: str = Field(min_length=1)
    status: Literal["VERIFIED", "UNKNOWN", "UNSUPPORTED"]
    request_kind: Literal["image", "video"]
    provider: str = Field(min_length=1)
    model: str = Field(min_length=1)
    max_reference_count: int = Field(ge=1, le=32)
    reference_roles: tuple[str, ...] = Field(min_length=1)
    prompt_max_length: int = Field(ge=1, le=100_000)
    aspect_ratios: tuple[str, ...] = Field(min_length=1)
    resolutions: tuple[str | None, ...] = Field(min_length=1)
    audio_modes: tuple[str, ...] = ()
    output_formats: tuple[str, ...] = ()
    qualities: tuple[str | None, ...] = ()
    duration_min: int | None = Field(default=None, ge=1, le=86_400)
    duration_max: int | None = Field(default=None, ge=1, le=86_400)
    supports_multi_shot: bool = False

    @model_validator(mode="after")
    def validate_duration_range(self) -> ProviderCapabilityDeclaration:
        if self.duration_min is None and self.duration_max is not None:
            raise ValueError("duration_min is required when duration_max is set")
        if (
            self.duration_min is not None
            and self.duration_max is not None
            and self.duration_min > self.duration_max
        ):
            raise ValueError("duration_min cannot exceed duration_max")
        return self


class ProviderHumanAuthorization(FrozenContract):
    """A human confirmation bound to one exact immutable request contract."""

    authorization_id: str = Field(min_length=1)
    status: Literal["AUTHORIZED"] = "AUTHORIZED"
    owner_id: str
    creative_task_id: str
    package_revision_id: str
    shot_id: ExecutionSlot
    provider: str
    model: str
    request_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    evidence_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    confirmed_at: datetime
    expires_at: datetime
    max_cost_micros: int = Field(ge=0)
    currency: str = Field(min_length=1, max_length=16)
    human_confirmed: Literal[True]


class ProviderCostEstimate(FrozenContract):
    """An explicit, non-discovering price and quota input for this request."""

    quote_id: str = Field(min_length=1)
    provider: str
    model: str
    request_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    evidence_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    estimated_cost_micros: int = Field(ge=0)
    currency: str = Field(min_length=1, max_length=16)
    quota_units: int = Field(ge=1)
    quota_remaining_units: int = Field(ge=0)
    expires_at: datetime
    includes_upload_cost: Literal[True]
    submit_retries: Literal[0]


class ProviderReferenceLicense(FrozenContract):
    """Independent human rights confirmation; does not qualify synthetic pixels."""

    license_id: str = Field(min_length=1)
    owner_id: str
    creative_task_id: str
    role: Literal["PRODUCT", "FIRST_FRAME", "STORYBOARD"]
    object_key: str
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    provider: str
    status: Literal["VERIFIED"] = "VERIFIED"
    scope: Literal["PROVIDER_INPUT"] = "PROVIDER_INPUT"
    evidence_id: str = Field(min_length=1)
    confirmed_by: str
    expires_at: datetime


class ProviderApprovalManifest(FrozenContract):
    """Server-owned independent approval truth, never a request-side override.

    Keeping this separate from CreativeTask avoids a circular request hash:
    MVP-3A hashes every task record, while approvals bind to that request hash.
    No API accepts this path; a future submission service must supply its trusted
    manifest location or replace this reader with an independent approval store.
    """

    schema_version: Literal["creative-provider-approval.v1"] = "creative-provider-approval.v1"
    approval_id: str = Field(min_length=1)
    revision: int = Field(ge=1)
    status: Literal["ACTIVE", "REVOKED"]
    authorization: ProviderHumanAuthorization | None = None
    estimate: ProviderCostEstimate | None = None
    licenses: tuple[ProviderReferenceLicense, ...] = ()


class MaterializedProviderInput(FrozenContract):
    role: str
    order: int = Field(ge=1)
    adapter_field: str
    object_key: str = Field(min_length=1)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    path: Path


class CreativeProviderPreflightResult(FrozenContract):
    schema_version: Literal["creative-provider-preflight.v1"] = "creative-provider-preflight.v1"
    status: Literal["READY_FOR_HUMAN_SUBMIT"] = "READY_FOR_HUMAN_SUBMIT"
    request_kind: Literal["image", "video"]
    run_mode: RunMode
    creative_task_id: str
    owner_id: str
    package_revision_id: str
    shot_id: ExecutionSlot
    provider: str
    model: str
    idempotency_key: str
    request_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    evidence_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    preflight_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    expires_at: datetime
    capability_declaration_verified: Literal[True] = True
    provider_capabilities_verified: Literal[False] = False
    materialized_inputs: tuple[MaterializedProviderInput, ...]
    manifest_path: Path
    temporary_file_lifetime: Literal["UNTIL_LEASE_CLOSE"] = "UNTIL_LEASE_CLOSE"
    actual_submitted: Literal[False] = False
    provider_submission_allowed: Literal[False] = False
    qualification_scope: Literal["OFFLINE_SYNTHETIC_ONLY"] = "OFFLINE_SYNTHETIC_ONLY"
    ordinary_output_qualified: Literal[False] = False
    deliverable_eligible: Literal[False] = False
    next_action: Literal["HUMAN_PROVIDER_SUBMIT"] = "HUMAN_PROVIDER_SUBMIT"


@dataclass
class CreativeProviderPreflight:
    """A result plus the temporary directory lease holding its local inputs."""

    result: CreativeProviderPreflightResult
    _temporary_directory: TemporaryDirectory[str]

    def close(self) -> None:
        self._temporary_directory.cleanup()

    def __enter__(self) -> CreativeProviderPreflight:
        return self

    def __exit__(self, exc_type, exc, traceback) -> None:
        self.close()

    async def __aenter__(self) -> CreativeProviderPreflight:
        return self

    async def __aexit__(self, exc_type, exc, traceback) -> None:
        self.close()

    def __getattr__(self, name: str):
        return getattr(self.result, name)


def _reject(code: str) -> NoReturn:
    raise CreativeProviderPreflightRejected(code)


def _now(value: datetime | None) -> datetime:
    current = value or datetime.now(UTC)
    if current.tzinfo is None:
        _reject("TIMEZONE_REQUIRED")
    return current


def _request_kind(request: ProviderRequestContract) -> Literal["image", "video"]:
    if isinstance(request, CreativeImageProviderRequest):
        return "image"
    if isinstance(request, CreativeVideoProviderRequest):
        return "video"
    _reject("REQUEST_KIND_UNSUPPORTED")


def _provider_model(request: ProviderRequestContract) -> tuple[str, str]:
    if isinstance(request, CreativeImageProviderRequest):
        return request.provider, request.model
    if isinstance(request, CreativeVideoProviderRequest):
        return request.provider, request.model
    _reject("REQUEST_KIND_UNSUPPORTED")


def _assert_request_hash(request: ProviderRequestContract) -> None:
    expected = digest(request.model_dump(mode="json", exclude={"request_hash"}))
    if request.request_hash != expected:
        _reject("REQUEST_HASH_MISMATCH")
    if request.run_mode not in {"dry-run", "replay"}:
        _reject("RUN_MODE_INVALID")
    if (
        request.actual_submitted
        or request.provider_submission_allowed
        or request.ordinary_output_qualified
        or request.deliverable_eligible
        or request.qualification_scope != "OFFLINE_SYNTHETIC_ONLY"
    ):
        _reject("OFFLINE_SUBMISSION_CONTRACT_INVALID")


def _assert_capability(
    request: ProviderRequest,
    capability: ProviderCapabilityDeclaration | None,
) -> None:
    if capability is None:
        _reject("CAPABILITY_UNKNOWN")
    if capability.status != "VERIFIED":
        _reject("CAPABILITY_UNKNOWN")
    kind = _request_kind(request)
    expected_roles = tuple(reference.role for reference in request.references)
    if (
        capability.request_kind != kind
        or capability.provider != request.provider
        or capability.model != request.model
    ):
        _reject("CAPABILITY_MISMATCH")
    if len(request.references) > capability.max_reference_count:
        _reject("REFERENCE_COUNT_UNSUPPORTED")
    if expected_roles != capability.reference_roles:
        _reject("REFERENCE_ROLES_UNSUPPORTED")
    product_count = sum(r.role == "PRODUCT" for r in request.references)
    storyboard_count = sum(r.role == "STORYBOARD" for r in request.references)
    expected = (
        (("PRODUCT", "images"),) * product_count
        + (("FIRST_FRAME", "images"),) * (request.shot_id != "FIRST_FRAME")
        if kind == "image" else (
            (("FIRST_FRAME", "first_frame_path"),)
            + (("STORYBOARD", "refer_image_paths"),) * storyboard_count
            + (("PRODUCT", "product_reference_paths"),) * product_count
        )
    )
    if product_count < 1:
        _reject("REFERENCE_BINDINGS_INVALID")
    if tuple((ref.role, ref.adapter_field) for ref in request.references) != expected or (
        tuple(ref.order for ref in request.references) != tuple(range(1, len(expected) + 1))
    ):
        _reject("REFERENCE_BINDINGS_INVALID")
    if len(request.adapter_parameters.prompt) > capability.prompt_max_length:
        _reject("PROMPT_TOO_LONG")
    if request.options.resolution not in capability.resolutions:
        _reject("RESOLUTION_UNSUPPORTED")
    if kind == "image":
        aspect = request.options.aspect_ratio
        if aspect not in capability.aspect_ratios:
            _reject("ASPECT_RATIO_UNSUPPORTED")
        if request.adapter_parameters.output_format not in capability.output_formats:
            _reject("OUTPUT_FORMAT_UNSUPPORTED")
        if request.adapter_parameters.quality not in capability.qualities:
            _reject("QUALITY_UNSUPPORTED")
        return
    video = request.options
    if video.multi_shot and (
        not capability.supports_multi_shot or request.provider != "kling_official_api"
    ):
        _reject("MULTI_SHOT_CAPABILITY_REQUIRED")
    if capability.duration_min is None or capability.duration_max is None:
        _reject("CAPABILITY_UNKNOWN")
    if not capability.duration_min <= video.duration <= capability.duration_max:
        _reject("DURATION_UNSUPPORTED")
    if video.aspect_ratio not in capability.aspect_ratios:
        _reject("ASPECT_RATIO_UNSUPPORTED")
    if video.audio not in capability.audio_modes:
        _reject("AUDIO_UNSUPPORTED")
    # Declarations may narrow adapter limits, but cannot contradict local code.
    if request.provider == "kling_official_api":
        if request.model != "kling-3.0-omni":
            _reject("MODEL_UNSUPPORTED")
        if video.audio not in {"off"} or video.resolution not in {"720p", "1080p", "4k"}:
            _reject("ADAPTER_OPTIONS_UNSUPPORTED")
        if not 3 <= video.duration <= 15 or len(request.references) > 7:
            _reject("ADAPTER_OPTIONS_UNSUPPORTED")
    elif request.provider == "wavespeed_video":
        if not request.model.endswith("/reference-to-video"):
            _reject("MODEL_UNSUPPORTED")
        if video.audio != "off" or video.resolution is not None or not 3 <= video.duration <= 15:
            _reject("ADAPTER_OPTIONS_UNSUPPORTED")
    elif request.provider == "bach":
        # Bach accepts one input (or a first/last pair), never this three-role contract.
        _reject("REFERENCE_ROLES_UNSUPPORTED")


async def _controls_and_quota(
    session: AsyncSession,
    settings: Settings,
    request: ProviderRequest,
    *,
    now: datetime,
) -> dict:
    if not settings.paid_generation_enabled:
        _reject("PAID_GENERATION_DISABLED")
    if not paid_generation_authorized(settings):
        _reject("PAID_GENERATION_BLOCKED")
    enabled = (
        settings.wavespeed_enabled and bool(settings.effective_wavespeed_api_key)
        if isinstance(request, CreativeImageProviderRequest)
        else settings.kling_provider_submission_enabled(request.provider)
    )
    if not enabled:
        _reject("PROVIDER_SUBMISSION_DISABLED")
    runtime = await session.scalar(
        select(RuntimeConfigVersion)
        .order_by(RuntimeConfigVersion.version.desc())
        .limit(1)
        .execution_options(populate_existing=True)
    )
    if runtime is None:
        _reject("RUNTIME_CONFIG_MISSING")
    if (
        settings.global_paused
        or settings.paid_submissions_paused
        or runtime.config_json.get("globalPaused") is not False
        or runtime.config_json.get("paidSubmissionsPaused") is not False
    ):
        _reject("PAID_SUBMISSIONS_PAUSED")
    owner_id = uuid.UUID(request.owner_id)
    user = await session.scalar(
        select(User).where(User.id == owner_id).execution_options(populate_existing=True)
    )
    if user is None or not user.is_active or user.role is UserRole.AUDITOR:
        _reject("OWNER_PERMISSION_DENIED")
    day = business_date(now)
    if isinstance(request, CreativeImageProviderRequest):
        used = await images_submitted_on(session, user_id=owner_id, day=day)
        limit = settings.daily_user_image_limit
    else:
        summary = await session.scalar(
            select(UserDailyPointsSummary)
            .where(
                UserDailyPointsSummary.user_id == owner_id,
                UserDailyPointsSummary.business_date == day,
            )
            .execution_options(populate_existing=True)
        )
        used = (
            summary.consumed_points + summary.reserved_points + summary.uncertain_points
            if summary
            else 0
        )
        limit = settings.daily_user_points_limit
    units = (
        1
        if isinstance(request, CreativeImageProviderRequest)
        else (settings.generation_estimated_points)
    )
    if used < 0 or used + units > limit:
        _reject("QUOTA_EXCEEDED")
    return {
        "runtime_id": str(runtime.id),
        "runtime_version": runtime.version,
        "runtime": runtime.config_json,
        "day": day.isoformat(),
        "limit": limit,
        "used": used,
        "units": units,
    }


def _assert_human_authorization(
    request: ProviderRequestContract,
    authorization: ProviderHumanAuthorization | None,
    *,
    now: datetime,
) -> None:
    if authorization is None:
        _reject("HUMAN_PROVIDER_AUTHORIZATION_REQUIRED")
    if authorization.expires_at.tzinfo is None or authorization.expires_at <= now:
        _reject("HUMAN_PROVIDER_AUTHORIZATION_EXPIRED")
    if (
        authorization.confirmed_at.tzinfo is None
        or authorization.confirmed_at > now
        or authorization.confirmed_at >= authorization.expires_at
    ):
        _reject("HUMAN_PROVIDER_AUTHORIZATION_INVALID")
    if (
        authorization.owner_id != request.owner_id
        or authorization.creative_task_id != request.creative_task_id
        or authorization.package_revision_id != request.package_revision_id
        or authorization.shot_id != request.shot_id
        or authorization.provider != _provider_model(request)[0]
        or authorization.model != _provider_model(request)[1]
        or authorization.request_hash != request.request_hash
        or authorization.evidence_hash != request.evidence_hash
        or authorization.status != "AUTHORIZED"
        or not authorization.human_confirmed
    ):
        _reject("HUMAN_PROVIDER_AUTHORIZATION_MISMATCH")


def _assert_cost_estimate(
    request: ProviderRequestContract,
    authorization: ProviderHumanAuthorization,
    estimate: ProviderCostEstimate | None,
    *,
    now: datetime,
) -> None:
    if estimate is None:
        _reject("COST_ESTIMATE_REQUIRED")
    if estimate.expires_at.tzinfo is None or estimate.expires_at <= now:
        _reject("COST_ESTIMATE_EXPIRED")
    if (
        estimate.provider != _provider_model(request)[0]
        or estimate.model != _provider_model(request)[1]
        or estimate.request_hash != request.request_hash
        or estimate.evidence_hash != request.evidence_hash
    ):
        _reject("COST_ESTIMATE_MISMATCH")
    if estimate.estimated_cost_micros > authorization.max_cost_micros:
        _reject("BUDGET_EXCEEDED")
    if estimate.currency != authorization.currency:
        _reject("BUDGET_CURRENCY_MISMATCH")
    if estimate.quota_units > estimate.quota_remaining_units:
        _reject("QUOTA_EXCEEDED")


async def _assert_product_license(
    session: AsyncSession,
    request: ProviderRequestContract,
) -> None:
    version = await session.scalar(
        select(ProductVersion)
        .where(
            ProductVersion.id == uuid.UUID(request.canonical_product.product_version_id),
            ProductVersion.product_id == uuid.UUID(request.canonical_product.product_id),
        )
        .execution_options(populate_existing=True)
    )
    if version is None:
        _reject("PRODUCT_VERSION_NOT_FOUND")
    if version.license_status is not ProductLicenseStatus.VERIFIED:
        _reject("PRODUCT_LICENSE_UNCONFIRMED")
    if getattr(version.status, "value", version.status) == "BLOCKED":
        _reject("PRODUCT_VERSION_BLOCKED")
    if version.status is not ProductVersionStatus.APPROVED:
        _reject("PRODUCT_VERSION_UNAPPROVED")


def _read_approval(path: Path | None) -> ProviderApprovalManifest:
    if path is None:
        _reject("HUMAN_PROVIDER_AUTHORIZATION_REQUIRED")
    try:
        approval = ProviderApprovalManifest.model_validate_json(path.read_bytes())
    except (OSError, ValidationError):
        _reject("PROVIDER_APPROVAL_INVALID")
    if approval.status != "ACTIVE":
        _reject("PROVIDER_APPROVAL_REVOKED")
    return approval


def _approval_licenses(
    request: ProviderRequest,
    approval: ProviderApprovalManifest,
    *,
    now: datetime,
) -> tuple[ProviderReferenceLicense, ...]:
    if len(approval.licenses) != len(request.references):
        _reject("REFERENCE_LICENSE_UNCONFIRMED")
    licenses = []
    for reference, grant in zip(request.references, approval.licenses, strict=True):
        if (
            grant.owner_id != request.owner_id
            or grant.confirmed_by != request.owner_id
            or grant.creative_task_id != request.creative_task_id
            or grant.role != reference.role
            or grant.object_key != reference.object_key
            or grant.sha256 != reference.sha256
            or grant.provider != request.provider
            or grant.expires_at.tzinfo is None
            or grant.expires_at <= now
        ):
            _reject("REFERENCE_LICENSE_UNCONFIRMED")
        licenses.append(grant)
    return tuple(licenses)


async def _materialize(
    request: ProviderRequestContract,
    object_store,
) -> tuple[TemporaryDirectory[str], tuple[MaterializedProviderInput, ...], Path]:
    lease = TemporaryDirectory(prefix="creative-provider-preflight-")
    root = Path(lease.name)
    entries: list[MaterializedProviderInput] = []
    try:
        for reference in request.references:
            suffix = Path(reference.object_key).suffix.lower()
            if suffix not in {".jpg", ".jpeg", ".png", ".webp"}:
                suffix = ".bin"
            target = root / f"{reference.order:03d}-{reference.role.lower()}{suffix}"
            localized = await object_store.localize(reference.object_key, target)
            actual = await asyncio.to_thread(_copy_and_hash, Path(localized), target)
            if actual != reference.sha256:
                _reject("REFERENCE_HASH_MISMATCH")
            image_suffix = await asyncio.to_thread(_image_suffix, target)
            if target.suffix != image_suffix:
                target = await asyncio.to_thread(target.rename, target.with_suffix(image_suffix))
            entries.append(
                MaterializedProviderInput(
                    role=reference.role,
                    order=reference.order,
                    adapter_field=reference.adapter_field,
                    object_key=reference.object_key,
                    sha256=reference.sha256,
                    path=target,
                )
            )
        manifest = root / "adapter-input-manifest.json"
        await asyncio.to_thread(
            manifest.write_text,
            json.dumps(
                {
                    "schema_version": "creative-provider-input-manifest.v1",
                    "request_kind": _request_kind(request),
                    "references": [entry.model_dump(mode="json") for entry in entries],
                },
                sort_keys=True,
                separators=(",", ":"),
            ),
            encoding="utf-8",
        )
        return lease, tuple(entries), manifest
    except BaseException:
        lease.cleanup()
        raise


def _copy_and_hash(source: Path, target: Path) -> str:
    if not source.is_file() or source.is_symlink() or target.is_symlink():
        raise FileNotFoundError(source)
    if source.resolve() != target.resolve():
        shutil.copyfile(source, target)
    return hashlib.sha256(target.read_bytes()).hexdigest()


def _image_suffix(path: Path) -> str:
    try:
        with Image.open(path) as image:
            suffix = {"PNG": ".png", "JPEG": ".jpg", "WEBP": ".webp"}.get(image.format)
            image.verify()
        if suffix is None:
            _reject("REFERENCE_IMAGE_INVALID")
        return suffix
    except (OSError, UnidentifiedImageError):
        _reject("REFERENCE_IMAGE_INVALID")


def _preflight_hash(
    request: ProviderRequestContract,
    capability: ProviderCapabilityDeclaration,
    authorization: ProviderHumanAuthorization,
    estimate: ProviderCostEstimate,
    entries: tuple[MaterializedProviderInput, ...],
    controls: dict,
    licenses: tuple[ProviderReferenceLicense, ...],
    approval: ProviderApprovalManifest,
) -> str:
    semantic_inputs = [entry.model_dump(mode="json", exclude={"path"}) for entry in entries]
    return digest(
        {
            "request_hash": request.request_hash,
            "evidence_hash": request.evidence_hash,
            "capability": capability.model_dump(mode="json"),
            "authorization": authorization.model_dump(mode="json"),
            "estimate": estimate.model_dump(mode="json"),
            "inputs": semantic_inputs,
            "controls": controls,
            "licenses": [grant.model_dump(mode="json") for grant in licenses],
            "approval": approval.model_dump(mode="json"),
        }
    )


async def _preflight_creative_provider_request(
    session: AsyncSession,
    task: CreativeTask,
    request: ProviderRequest,
    *,
    owner_id: uuid.UUID,
    object_store,
    settings: Settings,
    capability: ProviderCapabilityDeclaration | None,
    approval_manifest_path: Path | None,
    now: datetime | None = None,
) -> CreativeProviderPreflight:
    current_time = _now(now)
    if not isinstance(request, (CreativeImageProviderRequest, CreativeVideoProviderRequest)):
        _reject("REQUEST_KIND_UNSUPPORTED")
    try:
        request = type(request).model_validate(request.model_dump(mode="json"))
    except ValidationError:
        _reject("REQUEST_CONTRACT_INVALID")
    _assert_request_hash(request)
    for reference in request.references:
        key = reference.object_key
        if (
            key.startswith(("/", "\\"))
            or "\\" in key
            or ":" in key
            or any(part in {"", ".", ".."} for part in key.split("/"))
            or re.search(r"[\x00-\x1f]", key)
        ):
            _reject("OBJECT_KEY_UNSAFE")
    _assert_capability(request, capability)
    try:
        current = await assert_creative_provider_request_current(
            session,
            task,
            request,
            owner_id=owner_id,
            object_store=object_store,
            now=current_time,
        )
    except CreativeProviderRequestRejected as exc:
        raise CreativeProviderPreflightRejected(exc.code) from exc
    if current.evidence_hash != request.evidence_hash:
        _reject("EVIDENCE_HASH_MISMATCH")
    await _assert_product_license(session, current)
    approval = await asyncio.to_thread(_read_approval, approval_manifest_path)
    authorization, estimate = approval.authorization, approval.estimate
    _assert_human_authorization(request, authorization, now=current_time)
    _assert_cost_estimate(request, authorization, estimate, now=current_time)
    controls = await _controls_and_quota(session, settings, current, now=current_time)
    if estimate.quota_units != controls["units"]:
        _reject("COST_ESTIMATE_QUOTA_MISMATCH")
    licenses = _approval_licenses(current, approval, now=current_time)
    lease, entries, manifest = await _materialize(current, object_store)
    try:
        final_time = _now(now)
        latest = await asyncio.to_thread(_read_approval, approval_manifest_path)
        if latest != approval:
            _reject("PROVIDER_APPROVAL_STALE")
        _assert_human_authorization(request, authorization, now=final_time)
        _assert_cost_estimate(request, authorization, estimate, now=final_time)
        _approval_licenses(request, latest, now=final_time)
        await assert_creative_provider_request_current(
            session,
            task,
            request,
            owner_id=owner_id,
            object_store=object_store,
            now=final_time,
        )
        if await _controls_and_quota(session, settings, request, now=final_time) != controls:
            _reject("PROVIDER_CONTROLS_STALE")
    except CreativeProviderRequestRejected as exc:
        lease.cleanup()
        raise CreativeProviderPreflightRejected(exc.code) from exc
    except BaseException:
        lease.cleanup()
        raise
    result = CreativeProviderPreflightResult(
        request_kind=_request_kind(current),
        run_mode=current.run_mode,
        creative_task_id=current.creative_task_id,
        owner_id=current.owner_id,
        package_revision_id=current.package_revision_id,
        shot_id=current.shot_id,
        provider=current.provider,
        model=current.model,
        idempotency_key=current.idempotency_key,
        request_hash=current.request_hash,
        evidence_hash=current.evidence_hash,
        preflight_hash=_preflight_hash(
            current,
            capability,
            authorization,
            estimate,
            entries,
            controls,
            licenses,
            approval,
        ),
        expires_at=min(
            authorization.expires_at, estimate.expires_at, *(grant.expires_at for grant in licenses)
        ),
        materialized_inputs=entries,
        manifest_path=manifest,
    )
    return CreativeProviderPreflight(result=result, _temporary_directory=lease)


async def preflight_creative_provider_request(
    session: AsyncSession,
    task: CreativeTask,
    request: ProviderRequest,
    *,
    owner_id: uuid.UUID,
    object_store,
    settings: Settings,
    capability: ProviderCapabilityDeclaration | None,
    approval_manifest_path: Path | None,
    now: datetime | None = None,
) -> CreativeProviderPreflight:
    """Validate and materialize without flushing the caller's pending changes.

    Always close the returned lease, preferably using ``with`` or ``async with``.
    Its manifest identifies local files; it is not a Provider payload or URL.
    Approval files and capability declarations are trusted server inputs, not
    client-submitted authorizations. This service creates or edits neither.
    """
    with session.no_autoflush:
        return await _preflight_creative_provider_request(
            session,
            task,
            request,
            owner_id=owner_id,
            object_store=object_store,
            settings=settings,
            capability=capability,
            approval_manifest_path=approval_manifest_path,
            now=now,
        )


async def assert_creative_provider_preflight_current(
    session: AsyncSession,
    task: CreativeTask,
    preflight: CreativeProviderPreflightResult,
    request: ProviderRequest,
    *,
    owner_id: uuid.UUID,
    object_store,
    settings: Settings,
    capability: ProviderCapabilityDeclaration | None,
    approval_manifest_path: Path | None,
    now: datetime | None = None,
) -> CreativeProviderPreflight:
    if (
        preflight.request_hash != request.request_hash
        or preflight.evidence_hash != request.evidence_hash
        or preflight.creative_task_id != str(task.id)
    ):
        _reject("PREFLIGHT_STALE")
    current = await preflight_creative_provider_request(
        session,
        task,
        request,
        owner_id=owner_id,
        object_store=object_store,
        settings=settings,
        capability=capability,
        approval_manifest_path=approval_manifest_path,
        now=now,
    )
    if current.preflight_hash != preflight.preflight_hash:
        current.close()
        _reject("PREFLIGHT_STALE")
    excluded = {"materialized_inputs", "manifest_path"}
    if current.result.model_dump(exclude=excluded) != preflight.model_dump(exclude=excluded):
        current.close()
        _reject("PREFLIGHT_STALE")
    old_inputs = [entry.model_dump(exclude={"path"}) for entry in preflight.materialized_inputs]
    if old_inputs != [entry.model_dump(exclude={"path"}) for entry in current.materialized_inputs]:
        current.close()
        _reject("PREFLIGHT_STALE")
    return current
