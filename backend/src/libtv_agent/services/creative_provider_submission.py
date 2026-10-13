"""Minimal, write-free boundary for a future Provider submission.

MVP-4A turns an already validated MVP-3B preflight into an immutable
execution ticket.  The store below is deliberately process-local: it prevents
duplicate claims within one process, but it is not a PostgreSQL transaction or
a multi-worker lease.
"""

from __future__ import annotations

import hashlib
import json
import threading
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from libtv_agent.creative.workflow import digest
from libtv_agent.services.creative_provider_preflight import (
    CreativeProviderPreflight,
    CreativeProviderPreflightResult,
    ProviderApprovalManifest,
    ProviderCostEstimate,
    ProviderHumanAuthorization,
)
from libtv_agent.services.creative_provider_requests import FrozenContract
from pydantic import Field, ValidationError


class ProviderSubmissionAdmissionRejected(ValueError):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


class SubmissionManifestEntry(FrozenContract):
    role: Literal["PRODUCT", "FIRST_FRAME", "STORYBOARD"]
    order: int = Field(ge=1)
    adapter_field: str = Field(min_length=1)
    object_key: str = Field(min_length=1)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    path: Path


class ProviderSubmissionTicket(FrozenContract):
    """An immutable, auditable permission to reach a future adapter boundary."""

    schema_version: Literal["creative-provider-submission-ticket.v1"] = (
        "creative-provider-submission-ticket.v1"
    )
    ticket_id: str = Field(min_length=1)
    status: Literal["READY_TO_SUBMIT"] = "READY_TO_SUBMIT"
    request_kind: Literal["image", "video"]
    execution_mode: Literal["image_edit", "director_fixed"]
    future_adapter_action: Literal[
        "IMAGE_PROVIDER_ADAPTER_SUBMIT", "VIDEO_PROVIDER_ADAPTER_SUBMIT"
    ]
    owner_id: str
    creative_task_id: str
    package_revision_id: str
    shot_id: Literal["FIRST_FRAME", "SHOT_01"]
    provider: str
    model: str
    idempotency_key: str
    request_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    evidence_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    preflight_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    expires_at: datetime
    estimated_cost_micros: int = Field(ge=0)
    currency: str = Field(min_length=1, max_length=16)
    quota_units: int = Field(ge=1)
    materialized_inputs: tuple[SubmissionManifestEntry, ...]
    manifest_path: Path
    manifest_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    quota_reserved: Literal[False] = False
    charge_recorded: Literal[False] = False
    ledger_attempt_id: None = None
    actual_submitted: Literal[False] = False
    qualification_scope: Literal["OFFLINE_SYNTHETIC_ONLY"] = "OFFLINE_SYNTHETIC_ONLY"
    ordinary_output_qualified: Literal[False] = False
    deliverable_eligible: Literal[False] = False


class ProviderSubmissionResult(FrozenContract):
    """The smallest normalized receipt returned after a future adapter call."""

    schema_version: Literal["provider-submission-result.v1"] = (
        "provider-submission-result.v1"
    )
    ticket_id: str
    idempotency_key: str
    status: Literal["SUBMITTED", "UNKNOWN", "FAILED"]
    provider_task_id: str | None = None
    provider_status: str | None = None
    response_digest: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    error_code: str | None = None
    error_message: str | None = None
    actual_submitted: Literal[True, False, None]
    retry_policy: Literal["NONE", "RECONCILE_ONLY", "EXPLICIT_NEW_IDEMPOTENCY_KEY"]


class ProviderSubmissionTicketState(FrozenContract):
    """Mutable store state represented as a new immutable snapshot per change."""

    ticket: ProviderSubmissionTicket
    state: Literal["READY_TO_SUBMIT", "SUBMITTED", "UNKNOWN", "FAILED", "INVALIDATED"]
    invalidation_reason: str | None = None
    result: ProviderSubmissionResult | None = None


class SubmissionClaim(FrozenContract):
    ticket: ProviderSubmissionTicket
    state: ProviderSubmissionTicketState
    created: bool


def _now(value: datetime | None) -> datetime:
    current = value or datetime.now(UTC)
    if current.tzinfo is None:
        raise ProviderSubmissionAdmissionRejected("TIMEZONE_REQUIRED")
    return current


def _reject(code: str) -> None:
    raise ProviderSubmissionAdmissionRejected(code)


def _result(preflight: CreativeProviderPreflight | CreativeProviderPreflightResult):
    return preflight.result if isinstance(preflight, CreativeProviderPreflight) else preflight


def _semantic_preflight(
    preflight: CreativeProviderPreflightResult,
) -> dict:
    payload = preflight.model_dump(mode="json")
    payload.pop("manifest_path", None)
    for entry in payload.get("materialized_inputs", []):
        entry.pop("path", None)
    return payload


def _assert_current_preflight(
    preflight: CreativeProviderPreflightResult,
    current: CreativeProviderPreflightResult,
    *,
    now: datetime,
) -> None:
    if _semantic_preflight(preflight) != _semantic_preflight(current):
        _reject("PREFLIGHT_STALE")
    if current.status != "READY_FOR_HUMAN_SUBMIT":
        _reject("PREFLIGHT_NOT_READY")
    if current.expires_at.tzinfo is None or current.expires_at <= now:
        _reject("PREFLIGHT_EXPIRED")
    if (
        current.actual_submitted
        or current.provider_submission_allowed
        or current.ordinary_output_qualified
        or current.deliverable_eligible
        or current.qualification_scope != "OFFLINE_SYNTHETIC_ONLY"
        or current.provider_capabilities_verified
    ):
        _reject("PREFLIGHT_CONTRACT_INVALID")


def _assert_authorization(
    preflight: CreativeProviderPreflightResult,
    approval: ProviderApprovalManifest,
    *,
    now: datetime,
) -> tuple[ProviderHumanAuthorization, ProviderCostEstimate]:
    if approval.status != "ACTIVE":
        _reject("PROVIDER_APPROVAL_REVOKED")
    authorization = approval.authorization
    estimate = approval.estimate
    if authorization is None:
        _reject("HUMAN_PROVIDER_AUTHORIZATION_REQUIRED")
    if estimate is None:
        _reject("COST_ESTIMATE_REQUIRED")
    if authorization.expires_at.tzinfo is None or authorization.expires_at <= now:
        _reject("HUMAN_PROVIDER_AUTHORIZATION_EXPIRED")
    if (
        authorization.confirmed_at.tzinfo is None
        or authorization.confirmed_at > now
        or authorization.confirmed_at >= authorization.expires_at
    ):
        _reject("HUMAN_PROVIDER_AUTHORIZATION_INVALID")
    if (
        authorization.owner_id != preflight.owner_id
        or authorization.creative_task_id != preflight.creative_task_id
        or authorization.package_revision_id != preflight.package_revision_id
        or authorization.shot_id != preflight.shot_id
        or authorization.provider != preflight.provider
        or authorization.model != preflight.model
        or authorization.request_hash != preflight.request_hash
        or authorization.evidence_hash != preflight.evidence_hash
        or authorization.status != "AUTHORIZED"
        or not authorization.human_confirmed
    ):
        _reject("HUMAN_PROVIDER_AUTHORIZATION_MISMATCH")
    if estimate.expires_at.tzinfo is None or estimate.expires_at <= now:
        _reject("COST_ESTIMATE_EXPIRED")
    if (
        estimate.provider != preflight.provider
        or estimate.model != preflight.model
        or estimate.request_hash != preflight.request_hash
        or estimate.evidence_hash != preflight.evidence_hash
    ):
        _reject("COST_ESTIMATE_MISMATCH")
    if estimate.estimated_cost_micros > authorization.max_cost_micros:
        _reject("BUDGET_EXCEEDED")
    if estimate.currency != authorization.currency:
        _reject("BUDGET_CURRENCY_MISMATCH")
    if estimate.quota_units > estimate.quota_remaining_units:
        _reject("QUOTA_EXCEEDED")
    return authorization, estimate


def _assert_manifest(
    preflight: CreativeProviderPreflightResult,
) -> tuple[tuple[SubmissionManifestEntry, ...], str]:
    if not preflight.manifest_path.is_file():
        _reject("MATERIAL_MANIFEST_MISSING")
    try:
        payload = json.loads(preflight.manifest_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        _reject("MATERIAL_MANIFEST_INVALID")
    raw_entries = payload.get("references") if isinstance(payload, dict) else None
    if not isinstance(raw_entries, list):
        _reject("MATERIAL_MANIFEST_INVALID")
    try:
        entries = tuple(
            SubmissionManifestEntry.model_validate(entry.model_dump(mode="python"))
            for entry in preflight.materialized_inputs
        )
    except ValidationError:
        _reject("MATERIAL_MANIFEST_INVALID")
    expected = [entry.model_dump(mode="json") for entry in entries]
    if raw_entries != expected:
        _reject("MATERIAL_MANIFEST_MISMATCH")
    for entry in entries:
        if not entry.path.is_file() or entry.path.is_symlink():
            _reject("MATERIAL_INPUT_MISSING")
        if hashlib.sha256(entry.path.read_bytes()).hexdigest() != entry.sha256:
            _reject("MATERIAL_INPUT_HASH_MISMATCH")
    manifest_hash = digest(
        {
            "schema_version": payload.get("schema_version"),
            "request_kind": payload.get("request_kind"),
            "references": expected,
        }
    )
    return entries, manifest_hash


def _ticket_from(
    preflight: CreativeProviderPreflightResult,
    estimate: ProviderCostEstimate,
    entries: tuple[SubmissionManifestEntry, ...],
    manifest_hash: str,
) -> ProviderSubmissionTicket:
    is_video = preflight.request_kind == "video"
    identity = {
        "idempotency_key": preflight.idempotency_key,
        "request_hash": preflight.request_hash,
        "evidence_hash": preflight.evidence_hash,
        "preflight_hash": preflight.preflight_hash,
    }
    return ProviderSubmissionTicket(
        ticket_id=f"pst:{digest(identity)}",
        request_kind=preflight.request_kind,
        execution_mode="director_fixed" if is_video else "image_edit",
        future_adapter_action=(
            "VIDEO_PROVIDER_ADAPTER_SUBMIT"
            if is_video
            else "IMAGE_PROVIDER_ADAPTER_SUBMIT"
        ),
        owner_id=preflight.owner_id,
        creative_task_id=preflight.creative_task_id,
        package_revision_id=preflight.package_revision_id,
        shot_id=preflight.shot_id,
        provider=preflight.provider,
        model=preflight.model,
        idempotency_key=preflight.idempotency_key,
        request_hash=preflight.request_hash,
        evidence_hash=preflight.evidence_hash,
        preflight_hash=preflight.preflight_hash,
        expires_at=preflight.expires_at,
        estimated_cost_micros=estimate.estimated_cost_micros,
        currency=estimate.currency,
        quota_units=estimate.quota_units,
        materialized_inputs=entries,
        manifest_path=preflight.manifest_path,
        manifest_hash=manifest_hash,
    )


class SubmissionTicketStore:
    """Process-local idempotent ticket and outcome registry."""

    def __init__(self) -> None:
        self._by_key: dict[str, ProviderSubmissionTicketState] = {}
        self._lock = threading.Lock()

    def get(self, idempotency_key: str) -> ProviderSubmissionTicketState | None:
        with self._lock:
            return self._by_key.get(idempotency_key)

    def claim_submission(
        self,
        ticket: ProviderSubmissionTicket,
        *,
        now: datetime | None = None,
    ) -> SubmissionClaim:
        current_time = _now(now)
        with self._lock:
            existing = self._by_key.get(ticket.idempotency_key)
            if existing is not None:
                if existing.ticket != ticket:
                    _reject("IDEMPOTENCY_KEY_CONFLICT")
                if (
                    existing.state == "READY_TO_SUBMIT"
                    and ticket.expires_at.tzinfo is not None
                    and ticket.expires_at <= current_time
                ):
                    existing = existing.model_copy(
                        update={
                            "state": "INVALIDATED",
                            "invalidation_reason": "TICKET_EXPIRED",
                        }
                    )
                    self._by_key[ticket.idempotency_key] = existing
                return SubmissionClaim(ticket=existing.ticket, state=existing, created=False)
            if ticket.expires_at.tzinfo is None or ticket.expires_at <= current_time:
                _reject("TICKET_EXPIRED")
            state = ProviderSubmissionTicketState(
                ticket=ticket,
                state="READY_TO_SUBMIT",
            )
            self._by_key[ticket.idempotency_key] = state
            return SubmissionClaim(ticket=ticket, state=state, created=True)

    def invalidate(self, idempotency_key: str, reason: str) -> ProviderSubmissionTicketState:
        with self._lock:
            existing = self._by_key.get(idempotency_key)
            if existing is None:
                _reject("TICKET_NOT_FOUND")
            if existing.state in {"SUBMITTED", "UNKNOWN", "FAILED"}:
                return existing
            updated = existing.model_copy(
                update={"state": "INVALIDATED", "invalidation_reason": reason}
            )
            self._by_key[idempotency_key] = updated
            return updated

    def record_provider_result(
        self,
        idempotency_key: str,
        result: ProviderSubmissionResult,
    ) -> ProviderSubmissionTicketState:
        with self._lock:
            existing = self._by_key.get(idempotency_key)
            if existing is None:
                _reject("TICKET_NOT_FOUND")
            if (
                result.ticket_id != existing.ticket.ticket_id
                or result.idempotency_key != existing.ticket.idempotency_key
            ):
                _reject("SUBMISSION_RESULT_MISMATCH")
            if existing.result is not None:
                if existing.result == result:
                    return existing
                _reject("SUBMISSION_RESULT_CONFLICT")
            if existing.state != "READY_TO_SUBMIT":
                _reject("TICKET_NOT_SUBMITTABLE")
            updated = existing.model_copy(
                update={
                    "state": result.status,
                    "result": result,
                    "invalidation_reason": (
                        "EXECUTION_UNKNOWN"
                        if result.status == "UNKNOWN"
                        else "PROVIDER_SUBMISSION_FAILED"
                        if result.status == "FAILED"
                        else None
                    ),
                }
            )
            self._by_key[idempotency_key] = updated
            return updated


def claim_submission(
    store: SubmissionTicketStore,
    ticket: ProviderSubmissionTicket,
    *,
    now: datetime | None = None,
) -> SubmissionClaim:
    return store.claim_submission(ticket, now=now)


def admit_provider_submission(
    preflight: CreativeProviderPreflight | CreativeProviderPreflightResult,
    *,
    current_preflight: CreativeProviderPreflight | CreativeProviderPreflightResult,
    approval: ProviderApprovalManifest,
    store: SubmissionTicketStore,
    now: datetime | None = None,
) -> SubmissionClaim:
    """Admit a current, explicitly authorized preflight without executing it."""

    candidate = _result(preflight)
    current = _result(current_preflight)
    try:
        current_time = _now(now)
        _assert_current_preflight(candidate, current, now=current_time)
        _, estimate = _assert_authorization(current, approval, now=current_time)
        entries, manifest_hash = _assert_manifest(current)
        ticket = _ticket_from(current, estimate, entries, manifest_hash)
        return store.claim_submission(ticket, now=current_time)
    except ProviderSubmissionAdmissionRejected as exc:
        existing = store.get(candidate.idempotency_key)
        if existing is not None and existing.state == "READY_TO_SUBMIT":
            reason = {
                "PREFLIGHT_EXPIRED": "TICKET_EXPIRED",
                "PREFLIGHT_STALE": "SOURCE_CHANGED",
                "PROVIDER_APPROVAL_REVOKED": "AUTHORIZATION_REVOKED",
                "HUMAN_PROVIDER_AUTHORIZATION_EXPIRED": "AUTHORIZATION_REVOKED",
            }.get(exc.code, "ADMISSION_REJECTED")
            store.invalidate(candidate.idempotency_key, reason)
        raise


def provider_submission_result(
    ticket: ProviderSubmissionTicket,
    *,
    status: Literal["SUBMITTED", "UNKNOWN", "FAILED"],
    provider_task_id: str | None = None,
    provider_status: str | None = None,
    response_digest: str | None = None,
    error_code: str | None = None,
    error_message: str | None = None,
) -> ProviderSubmissionResult:
    if status == "SUBMITTED":
        if not provider_task_id:
            _reject("PROVIDER_TASK_ID_REQUIRED")
        retry_policy = "NONE"
        actual_submitted = True
    elif status == "UNKNOWN":
        retry_policy = "RECONCILE_ONLY"
        actual_submitted = None
    else:
        retry_policy = "EXPLICIT_NEW_IDEMPOTENCY_KEY"
        actual_submitted = False
    return ProviderSubmissionResult(
        ticket_id=ticket.ticket_id,
        idempotency_key=ticket.idempotency_key,
        status=status,
        provider_task_id=provider_task_id,
        provider_status=provider_status,
        response_digest=response_digest,
        error_code=error_code,
        error_message=error_message,
        actual_submitted=actual_submitted,
        retry_policy=retry_policy,
    )


def record_provider_submission_result(
    store: SubmissionTicketStore,
    ticket: ProviderSubmissionTicket,
    result: ProviderSubmissionResult,
) -> ProviderSubmissionTicketState:
    return store.record_provider_result(ticket.idempotency_key, result)


def invalidate_submission(
    store: SubmissionTicketStore,
    ticket: ProviderSubmissionTicket,
    *,
    reason: Literal[
        "TICKET_EXPIRED",
        "AUTHORIZATION_REVOKED",
        "SOURCE_CHANGED",
        "EXECUTION_UNKNOWN",
        "USER_STOPPED",
    ],
) -> ProviderSubmissionTicketState:
    return store.invalidate(ticket.idempotency_key, reason)
