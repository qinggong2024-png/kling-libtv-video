"""MVP-5A image Provider executor boundary.

This module owns only the Creative FIRST_FRAME/image_edit edge. It consumes
the existing MVP-3B temporary materialization lease and MVP-4B durable ticket.
It does not create image batches, attempts, quota reservations, ledger rows, or
deliverables.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal, Protocol

from libtv_agent.config import Settings
from libtv_agent.creative.workflow import digest
from libtv_agent.domain.models import CreativeTask
from libtv_agent.services.creative_provider_preflight import (
    CreativeProviderPreflight,
    CreativeProviderPreflightRejected,
    CreativeProviderPreflightResult,
    ProviderApprovalManifest,
    ProviderCapabilityDeclaration,
    assert_creative_provider_preflight_current,
)
from libtv_agent.services.creative_provider_requests import (
    CreativeImageProviderRequest,
    CreativeProviderRequestRejected,
    assert_creative_provider_request_current,
)
from libtv_agent.services.creative_provider_submission import (
    ProviderSubmissionTicket,
    provider_submission_result,
)
from libtv_agent.services.creative_provider_submission_persistence import (
    DurableSubmissionTicketStore,
)
from libtv_agent.services.image_generations import _provider_data
from sqlalchemy.ext.asyncio import AsyncSession

ExecutionMode = Literal["dry-run", "replay", "test-double", "live"]


class CreativeProviderExecutionRejected(ValueError):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


class CreativeImageProviderAdapter(Protocol):
    async def upload_media(
        self,
        source: str | Path | bytes,
        *,
        filename: str | None = None,
        content_type: str | None = None,
    ) -> str: ...

    async def submit_prediction(
        self,
        model_id: str,
        payload: Mapping[str, object],
        *,
        validate_model: bool = True,
    ) -> Any: ...


class CreativeExecutionControls:
    """Independent runtime controls for the executor."""

    def __init__(
        self,
        *,
        mode: ExecutionMode = "dry-run",
        admin_live_enabled: bool = False,
        human_confirmed: bool = False,
    ) -> None:
        self.mode = mode
        self.admin_live_enabled = admin_live_enabled
        self.human_confirmed = human_confirmed


class CreativeImageExecutionResult:
    """Explicit execution outcome; it never implies qualification or delivery."""

    schema_version = "creative-image-execution-result.v1"

    def __init__(
        self,
        *,
        status: Literal[
            "PREPARED", "REPLAYED", "TEST_DOUBLE", "SUBMITTED", "UNKNOWN", "FAILED"
        ],
        ticket: ProviderSubmissionTicket,
        provider_task_id: str | None,
        actual_submitted: bool | None,
        response_digest: str | None,
        error_code: str | None = None,
        qualification_scope: str = "OFFLINE_SYNTHETIC_ONLY",
        deliverable_eligible: bool = False,
    ) -> None:
        self.status = status
        self.ticket_id = ticket.ticket_id
        self.idempotency_key = ticket.idempotency_key
        self.provider_task_id = provider_task_id
        self.actual_submitted = actual_submitted
        self.response_digest = response_digest
        self.error_code = error_code
        self.qualification_scope = qualification_scope
        self.deliverable_eligible = deliverable_eligible

    def model_dump(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "status": self.status,
            "ticket_id": self.ticket_id,
            "idempotency_key": self.idempotency_key,
            "provider_task_id": self.provider_task_id,
            "actual_submitted": self.actual_submitted,
            "response_digest": self.response_digest,
            "error_code": self.error_code,
            "qualification_scope": self.qualification_scope,
            "deliverable_eligible": self.deliverable_eligible,
        }


def _reject(code: str) -> None:
    raise CreativeProviderExecutionRejected(code)


def _now(value: datetime | None) -> datetime:
    current = value or datetime.now(UTC)
    if current.tzinfo is None:
        _reject("TIMEZONE_REQUIRED")
    return current


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _provider_error_code(exc: BaseException) -> str:
    return str(getattr(exc, "code", type(exc).__name__))[:120]


def _provider_task_id(value: Any) -> str | None:
    data = _provider_data(value)
    candidate = data.get("id") or data.get("task_id") or data.get("taskId")
    return candidate if isinstance(candidate, str) and candidate.strip() else None


def _response_digest(value: Any) -> str:
    if isinstance(value, Mapping):
        payload: Any = dict(value)
    elif hasattr(value, "raw_response"):
        payload = value.raw_response
    else:
        payload = repr(value)
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, default=str, separators=(",", ":")).encode()
    ).hexdigest()


def _upload_url(value: Any) -> str:
    if isinstance(value, str) and value.strip():
        return value
    data = _provider_data(value)
    for key in ("download_url", "downloadUrl", "url"):
        candidate = data.get(key)
        if isinstance(candidate, str) and candidate.strip():
            return candidate
    _reject("ADAPTER_UPLOAD_RESPONSE_INVALID")


def _semantic_inputs(value: Any) -> list[dict[str, Any]]:
    result = []
    for entry in value:
        result.append(entry.model_dump(mode="json", exclude={"path"}))
    return result


def _ticket_identity(ticket: ProviderSubmissionTicket) -> str:
    identity = {
        "idempotency_key": ticket.idempotency_key,
        "request_hash": ticket.request_hash,
        "evidence_hash": ticket.evidence_hash,
        "preflight_hash": ticket.preflight_hash,
    }
    return f"pst:{digest(identity)}"


def _assert_image_contract(
    ticket: ProviderSubmissionTicket,
    request: CreativeImageProviderRequest,
    preflight: CreativeProviderPreflightResult,
    *,
    now: datetime,
) -> None:
    if ticket.request_kind != "image" or ticket.execution_mode != "image_edit":
        _reject("IMAGE_EXECUTION_ONLY")
    if ticket.shot_id != "FIRST_FRAME" or request.shot_id != "FIRST_FRAME":
        _reject("FIRST_FRAME_REQUIRED")
    if preflight.request_kind != "image" or preflight.shot_id != "FIRST_FRAME":
        _reject("FIRST_FRAME_PREFLIGHT_REQUIRED")
    if preflight.status != "READY_FOR_HUMAN_SUBMIT":
        _reject("PREFLIGHT_NOT_READY")
    if _as_utc(ticket.expires_at) <= _as_utc(now):
        _reject("TICKET_EXPIRED")
    if _as_utc(preflight.expires_at) <= _as_utc(now):
        _reject("PREFLIGHT_EXPIRED")
    if ticket.ticket_id != _ticket_identity(ticket):
        _reject("TICKET_ID_INVALID")
    if (
        ticket.idempotency_key != request.idempotency_key
        or ticket.request_hash != request.request_hash
        or ticket.evidence_hash != request.evidence_hash
        or ticket.preflight_hash != preflight.preflight_hash
        or ticket.owner_id != request.owner_id
        or ticket.creative_task_id != request.creative_task_id
        or ticket.package_revision_id != request.package_revision_id
        or ticket.provider != request.provider
        or ticket.model != request.model
        or preflight.request_hash != request.request_hash
        or preflight.evidence_hash != request.evidence_hash
        or preflight.actual_submitted
        or preflight.provider_submission_allowed
        or preflight.ordinary_output_qualified
        or preflight.deliverable_eligible
        or preflight.qualification_scope != "OFFLINE_SYNTHETIC_ONLY"
    ):
        _reject("EXECUTION_CONTRACT_MISMATCH")


def _assert_materialized_inputs(
    ticket: ProviderSubmissionTicket,
    preflight: CreativeProviderPreflightResult,
    *,
    verify_manifest: bool = True,
) -> None:
    if _semantic_inputs(ticket.materialized_inputs) != _semantic_inputs(
        preflight.materialized_inputs
    ):
        _reject("MATERIALIZED_INPUTS_STALE")
    if verify_manifest:
        if not ticket.manifest_path.is_file() or ticket.manifest_path.is_symlink():
            _reject("MATERIAL_MANIFEST_MISSING")
        try:
            manifest = json.loads(ticket.manifest_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError):
            _reject("MATERIAL_MANIFEST_INVALID")
        expected = [
            entry.model_dump(mode="json")
            for entry in preflight.materialized_inputs
        ]
        if not isinstance(manifest, dict) or manifest.get("references") != expected:
            _reject("MATERIAL_MANIFEST_MISMATCH")
        if digest(
            {
                "schema_version": manifest.get("schema_version"),
                "request_kind": manifest.get("request_kind"),
                "references": expected,
            }
        ) != ticket.manifest_hash:
            _reject("MATERIAL_MANIFEST_HASH_MISMATCH")
    for entry in preflight.materialized_inputs:
        if not entry.path.is_file() or entry.path.is_symlink():
            _reject("MATERIAL_INPUT_MISSING")
        if hashlib.sha256(entry.path.read_bytes()).hexdigest() != entry.sha256:
            _reject("MATERIAL_INPUT_HASH_MISMATCH")


def _assert_live_controls(
    settings: Settings,
    controls: CreativeExecutionControls,
    approval: ProviderApprovalManifest | None,
) -> None:
    if controls.mode != "live":
        return
    if settings.app_env == "test":
        _reject("LIVE_EXECUTION_BLOCKED_IN_TEST")
    if not controls.admin_live_enabled:
        _reject("CREATIVE_LIVE_FEATURE_DISABLED")
    if not controls.human_confirmed:
        _reject("HUMAN_PROVIDER_CONFIRMATION_REQUIRED")
    if approval is None or approval.status != "ACTIVE":
        _reject("PROVIDER_APPROVAL_REQUIRED")
    if approval.authorization is None or not approval.authorization.human_confirmed:
        _reject("HUMAN_PROVIDER_CONFIRMATION_REQUIRED")
    if not settings.paid_generation_enabled:
        _reject("PAID_GENERATION_DISABLED")
    if settings.paid_submissions_paused or settings.global_paused:
        _reject("PAID_SUBMISSIONS_PAUSED")
    if not settings.wavespeed_enabled or not settings.effective_wavespeed_api_key:
        _reject("PROVIDER_SUBMISSION_DISABLED")


class _ExecutionInputs:
    def __init__(self, preflight: CreativeProviderPreflightResult) -> None:
        self.preflight = preflight

    async def __aenter__(self):
        return tuple(
            (entry, entry.path) for entry in self.preflight.materialized_inputs
        )

    async def __aexit__(self, exc_type, exc, traceback) -> None:
        return None


def _execution_inputs(preflight: CreativeProviderPreflightResult) -> _ExecutionInputs:
    """Keep the existing preflight materialization alive during adapter I/O."""

    return _ExecutionInputs(preflight)


async def execute_creative_image(
    session: AsyncSession,
    *,
    task: CreativeTask,
    request: CreativeImageProviderRequest,
    ticket: ProviderSubmissionTicket,
    preflight: CreativeProviderPreflightResult,
    owner_id,
    object_store: Any,
    settings: Settings,
    controls: CreativeExecutionControls | None = None,
    adapter: CreativeImageProviderAdapter | None = None,
    approval: ProviderApprovalManifest | None = None,
    capability: ProviderCapabilityDeclaration | None = None,
    approval_manifest_path: Path | None = None,
    now: datetime | None = None,
) -> CreativeImageExecutionResult:
    controls = controls or CreativeExecutionControls()
    current_time = _now(now)
    _assert_image_contract(ticket, request, preflight, now=current_time)
    _assert_materialized_inputs(ticket, preflight)

    state = await DurableSubmissionTicketStore().get(session, ticket.idempotency_key)
    if state is None:
        _reject("TICKET_NOT_FOUND")
    if state.ticket != ticket:
        _reject("TICKET_STALE")
    if state.state != "READY_TO_SUBMIT":
        _reject("TICKET_NOT_SUBMITTABLE")

    try:
        await assert_creative_provider_request_current(
            session,
            task,
            request,
            owner_id=owner_id,
            object_store=object_store,
            now=current_time,
        )
    except CreativeProviderRequestRejected as exc:
        _reject(exc.code)

    if controls.mode in {"dry-run", "replay"}:
        return CreativeImageExecutionResult(
            status="PREPARED" if controls.mode == "dry-run" else "REPLAYED",
            ticket=ticket,
            provider_task_id=None,
            actual_submitted=False,
            response_digest=None,
        )

    checked_preflight: CreativeProviderPreflight | None = None
    if controls.mode == "live":
        _assert_live_controls(settings, controls, approval)
        if capability is None or approval_manifest_path is None:
            _reject("LIVE_REVALIDATION_INPUTS_REQUIRED")
        try:
            checked_preflight = await assert_creative_provider_preflight_current(
                session,
                task,
                preflight,
                request,
                owner_id=owner_id,
                object_store=object_store,
                settings=settings,
                capability=capability,
                approval_manifest_path=approval_manifest_path,
                now=current_time,
            )
        except CreativeProviderPreflightRejected as exc:
            _reject(exc.code)
        if not isinstance(checked_preflight, CreativeProviderPreflight):
            _reject("LIVE_REVALIDATION_LEASE_REQUIRED")
        preflight = checked_preflight.result
        _assert_image_contract(ticket, request, preflight, now=current_time)
        _assert_materialized_inputs(ticket, preflight, verify_manifest=False)
    elif controls.mode == "test-double":
        if adapter is None or not bool(getattr(adapter, "is_test_double", False)):
            _reject("EXPLICIT_TEST_DOUBLE_REQUIRED")
    else:
        _reject("EXECUTION_MODE_INVALID")

    if adapter is None:
        _reject("IMAGE_PROVIDER_ADAPTER_REQUIRED")

    try:
        async with (
            checked_preflight
            if checked_preflight is not None
            else _ExecutionInputs(preflight)
        ):
            async with _execution_inputs(preflight) as inputs:
                uploaded_urls: list[str] = []
                try:
                    for _entry, path in inputs:
                        uploaded_urls.append(
                            _upload_url(
                                await adapter.upload_media(
                                    path,
                                    filename=path.name,
                                    content_type="image/png",
                                )
                            )
                        )
                    payload = request.adapter_parameters.model_dump(
                        mode="json", exclude_none=True
                    )
                    payload["images"] = uploaded_urls
                    response = await adapter.submit_prediction(
                        request.model,
                        payload,
                        validate_model=controls.mode == "live",
                    )
                except BaseException as exc:
                    if controls.mode == "test-double":
                        return CreativeImageExecutionResult(
                            status="TEST_DOUBLE",
                            ticket=ticket,
                            provider_task_id=None,
                            actual_submitted=False,
                            response_digest=None,
                            error_code=_provider_error_code(exc),
                        )
                    uncertain = bool(
                        getattr(exc, "uncertain", False)
                        or getattr(exc, "submitted", False)
                    )
                    receipt = provider_submission_result(
                        ticket,
                        status="UNKNOWN" if uncertain else "FAILED",
                        provider_status="unknown" if uncertain else "failed",
                        error_code=_provider_error_code(exc),
                        error_message=str(exc)[:4000],
                    )
                    await DurableSubmissionTicketStore().record_provider_result(
                        session, ticket.idempotency_key, receipt
                    )
                    return CreativeImageExecutionResult(
                        status=receipt.status,
                        ticket=ticket,
                        provider_task_id=None,
                        actual_submitted=receipt.actual_submitted,
                        response_digest=None,
                        error_code=receipt.error_code,
                        qualification_scope="REAL_PROVIDER_SUBMITTED_UNQUALIFIED",
                    )
    finally:
        if checked_preflight is None:
            pass

    provider_task_id = _provider_task_id(response)
    response_digest = _response_digest(response)
    if not provider_task_id:
        receipt = provider_submission_result(
            ticket,
            status="UNKNOWN",
            provider_status="unknown",
            response_digest=response_digest,
            error_code="ADAPTER_RESPONSE_INVALID",
        )
        await DurableSubmissionTicketStore().record_provider_result(
            session, ticket.idempotency_key, receipt
        )
        return CreativeImageExecutionResult(
            status="UNKNOWN",
            ticket=ticket,
            provider_task_id=None,
            actual_submitted=None,
            response_digest=response_digest,
            error_code=receipt.error_code,
            qualification_scope="REAL_PROVIDER_SUBMITTED_UNQUALIFIED",
        )

    receipt = provider_submission_result(
        ticket,
        status="SUBMITTED",
        provider_task_id=provider_task_id,
        provider_status=str(getattr(response, "status", "created")),
        response_digest=response_digest,
    )
    if controls.mode == "test-double":
        return CreativeImageExecutionResult(
            status="TEST_DOUBLE",
            ticket=ticket,
            provider_task_id=None,
            actual_submitted=False,
            response_digest=None,
        )
    await DurableSubmissionTicketStore().record_provider_result(
        session, ticket.idempotency_key, receipt
    )
    return CreativeImageExecutionResult(
        status="SUBMITTED",
        ticket=ticket,
        provider_task_id=provider_task_id,
        actual_submitted=True,
        response_digest=response_digest,
        qualification_scope="REAL_PROVIDER_SUBMITTED_UNQUALIFIED",
    )
