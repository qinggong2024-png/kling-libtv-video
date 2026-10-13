"""MVP-7A durable Creative image execution orchestration.

This is the service-level bridge between the MVP-4B ticket, MVP-5B durable
input lease, and MVP-5A image executor. It intentionally supports only one
Creative FIRST_FRAME/image_edit sample and never turns an offline result into
a qualified or deliverable asset.
"""

from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from libtv_agent.config import Settings
from libtv_agent.creative.workflow import digest
from libtv_agent.domain.models import CreativeTask
from libtv_agent.services.creative_provider_executor import (
    CreativeExecutionControls,
    CreativeImageExecutionResult,
    CreativeProviderExecutionRejected,
    execute_creative_image,
)
from libtv_agent.services.creative_provider_input_lease import (
    DurableProviderInputLeaseStore,
    MaterializedProviderInputLease,
    ProviderInputLeaseRejected,
)
from libtv_agent.services.creative_provider_preflight import (
    CreativeProviderPreflightResult,
    MaterializedProviderInput,
    ProviderApprovalManifest,
    ProviderCapabilityDeclaration,
)
from libtv_agent.services.creative_provider_requests import (
    CreativeImageProviderRequest,
)
from libtv_agent.services.creative_provider_submission import ProviderSubmissionTicket
from libtv_agent.services.creative_provider_submission_persistence import (
    DurableSubmissionTicketStore,
)
from sqlalchemy.ext.asyncio import AsyncSession

ExecutionMode = Literal["dry-run", "replay", "test-double", "live"]
WorkflowStatus = Literal[
    "PREPARED",
    "REPLAYED",
    "TEST_DOUBLE",
    "SUBMITTED",
    "UNKNOWN",
    "FAILED",
]


class CreativeImageWorkflowRejected(ValueError):
    """A fail-closed orchestration rejection with an auditable code."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


@dataclass(frozen=True)
class CreativeImageWorkflowControls:
    """Caller controls for this service-level boundary.

    ``live_feature_enabled`` is deliberately separate from the executor's
    existing admin switch. MVP-7A requires both switches, then still stops
    before any real Provider adapter call.
    """

    mode: ExecutionMode = "dry-run"
    live_feature_enabled: bool = False
    admin_live_enabled: bool = False
    human_confirmed: bool = False


@dataclass(frozen=True)
class CreativeImageWorkflowAudit:
    """Stable, path-free execution evidence suitable for logs or API wrapping."""

    schema_version: str
    status: WorkflowStatus
    execution_mode: ExecutionMode
    ticket_id: str
    lease_id: str
    idempotency_key: str
    request_hash: str
    evidence_hash: str
    preflight_hash: str
    ticket_state: str
    lease_state: str
    actual_submitted: bool | None
    provider_task_id: str | None
    response_digest: str | None
    error_code: str | None
    retry_policy: Literal["NONE", "RECONCILE_ONLY", "EXPLICIT_NEW_IDEMPOTENCY_KEY"]
    qualification_scope: Literal["OFFLINE_SYNTHETIC_ONLY"]
    deliverable_eligible: Literal[False]
    input_manifest: tuple[dict[str, object], ...]
    input_manifest_hash: str
    stage_audit: tuple[dict[str, str], ...]
    summary_hash: str

    def model_dump(self) -> dict[str, object]:
        payload = {
            "schema_version": self.schema_version,
            "status": self.status,
            "execution_mode": self.execution_mode,
            "ticket_id": self.ticket_id,
            "lease_id": self.lease_id,
            "idempotency_key": self.idempotency_key,
            "request_hash": self.request_hash,
            "evidence_hash": self.evidence_hash,
            "preflight_hash": self.preflight_hash,
            "ticket_state": self.ticket_state,
            "lease_state": self.lease_state,
            "actual_submitted": self.actual_submitted,
            "provider_task_id": self.provider_task_id,
            "response_digest": self.response_digest,
            "error_code": self.error_code,
            "retry_policy": self.retry_policy,
            "qualification_scope": self.qualification_scope,
            "deliverable_eligible": self.deliverable_eligible,
            "input_manifest": list(self.input_manifest),
            "input_manifest_hash": self.input_manifest_hash,
            "stage_audit": list(self.stage_audit),
            "summary_hash": self.summary_hash,
        }
        return payload


@dataclass(frozen=True)
class CreativeImageWorkflowResult:
    """Executor result plus the durable input/ticket audit summary."""

    execution: CreativeImageExecutionResult
    audit: CreativeImageWorkflowAudit

    @property
    def status(self) -> WorkflowStatus:
        return self.audit.status

    @property
    def actual_submitted(self) -> bool | None:
        return self.audit.actual_submitted

    @property
    def deliverable_eligible(self) -> Literal[False]:
        return False

    def model_dump(self) -> dict[str, object]:
        return {
            "execution": self.execution.model_dump(),
            "audit": self.audit.model_dump(),
        }


def _now(value: datetime | None) -> datetime:
    current = value or datetime.now(UTC)
    if current.tzinfo is None:
        raise CreativeImageWorkflowRejected("TIMEZONE_REQUIRED")
    return current.astimezone(UTC)


def _reject(code: str) -> None:
    raise CreativeImageWorkflowRejected(code)


def _assert_single_image_contract(
    request: CreativeImageProviderRequest,
    ticket: ProviderSubmissionTicket,
    preflight: CreativeProviderPreflightResult,
) -> None:
    if (
        request.request_kind != "image"
        or request.shot_id != "FIRST_FRAME"
        or ticket.request_kind != "image"
        or ticket.execution_mode != "image_edit"
        or ticket.shot_id != "FIRST_FRAME"
        or ticket.future_adapter_action != "IMAGE_PROVIDER_ADAPTER_SUBMIT"
        or preflight.request_kind != "image"
        or preflight.shot_id != "FIRST_FRAME"
    ):
        _reject("CREATIVE_FIRST_FRAME_IMAGE_ONLY")
    if ticket.idempotency_key != request.idempotency_key:
        _reject("EXECUTION_CONTRACT_MISMATCH")
    if ticket.preflight_hash != preflight.preflight_hash:
        _reject("PREFLIGHT_TICKET_MISMATCH")


def _assert_task_not_stopped(task: CreativeTask) -> None:
    snapshot = task.snapshot_json or {}
    if snapshot.get("stopped") is True or snapshot.get("stop_reason") == "USER_STOPPED":
        _reject("USER_STOPPED")


def _assert_ticket_is_replay_safe(state, *, requested_mode: ExecutionMode) -> None:
    if state is None:
        _reject("DURABLE_TICKET_REQUIRED")
    if state.state == "UNKNOWN":
        _reject("UNKNOWN_RECONCILE_ONLY")
    if state.state == "FAILED":
        _reject("FAILED_NEW_IDEMPOTENCY_KEY_REQUIRED")
    if state.state == "INVALIDATED":
        if state.invalidation_reason == "USER_STOPPED":
            _reject("USER_STOPPED")
        _reject("TICKET_NOT_SUBMITTABLE")
    if state.state != "READY_TO_SUBMIT":
        _reject("TICKET_NOT_SUBMITTABLE")
    if requested_mode == "live" and state.ticket.actual_submitted:
        _reject("TICKET_NOT_SUBMITTABLE")


def _assert_live_admission(
    settings: Settings,
    controls: CreativeImageWorkflowControls,
    *,
    approval: ProviderApprovalManifest | None,
    capability: ProviderCapabilityDeclaration | None,
    approval_manifest_path: Path | None,
) -> None:
    if not controls.live_feature_enabled:
        _reject("CREATIVE_LIVE_FEATURE_DISABLED")
    if settings.app_env not in {"staging", "production"}:
        _reject("LIVE_APP_ENV_REQUIRED")
    if not controls.admin_live_enabled:
        _reject("ADMIN_LIVE_APPROVAL_REQUIRED")
    if not controls.human_confirmed:
        _reject("HUMAN_PROVIDER_CONFIRMATION_REQUIRED")
    if approval is None or approval.status != "ACTIVE":
        _reject("PROVIDER_APPROVAL_REQUIRED")
    if approval.authorization is None or not approval.authorization.human_confirmed:
        _reject("HUMAN_PROVIDER_CONFIRMATION_REQUIRED")
    if approval.estimate is None:
        _reject("COST_ESTIMATE_REQUIRED")
    if capability is None or approval_manifest_path is None:
        _reject("LIVE_REVALIDATION_INPUTS_REQUIRED")
    if not settings.paid_generation_enabled:
        _reject("PAID_GENERATION_DISABLED")
    if settings.global_paused or settings.paid_submissions_paused:
        _reject("PAID_SUBMISSIONS_PAUSED")


def _executor_materialization(
    ticket: ProviderSubmissionTicket,
    materialized: MaterializedProviderInputLease,
) -> tuple[list[MaterializedProviderInput], Path]:
    """Rebuild the executor's path-bearing view from durable lease bytes.

    The ticket manifest path/hash is immutable. The durable lease therefore
    repopulates that exact temporary manifest contract instead of creating a
    second ticket or mutating the persisted ticket snapshot.
    """

    if len(ticket.materialized_inputs) != len(materialized.inputs):
        _reject("MATERIALIZED_INPUTS_STALE")
    if ticket.manifest_path.is_symlink():
        _reject("MATERIAL_MANIFEST_INVALID")

    executor_inputs: list[MaterializedProviderInput] = []
    for ticket_entry, lease_entry in zip(
        ticket.materialized_inputs,
        materialized.inputs,
        strict=True,
    ):
        if (
            ticket_entry.role != lease_entry.role
            or ticket_entry.order != lease_entry.order
            or ticket_entry.adapter_field != lease_entry.adapter_field
            or ticket_entry.object_key != lease_entry.object_key
            or ticket_entry.sha256 != lease_entry.sha256
        ):
            _reject("MATERIALIZED_INPUTS_STALE")
        target = ticket_entry.path
        if target.is_symlink() or materialized.manifest_path.is_symlink():
            _reject("MATERIAL_MANIFEST_INVALID")
        target.parent.mkdir(parents=True, exist_ok=True)
        if lease_entry.path.resolve() != target.resolve():
            shutil.copyfile(lease_entry.path, target)
        executor_inputs.append(
            MaterializedProviderInput(
                role=lease_entry.role,
                order=lease_entry.order,
                adapter_field=lease_entry.adapter_field,
                object_key=lease_entry.object_key,
                sha256=lease_entry.sha256,
                path=target,
            )
        )

    payload = {
        "schema_version": "creative-provider-input-manifest.v1",
        "request_kind": "image",
        "references": [entry.model_dump(mode="json") for entry in executor_inputs],
    }
    expected_hash = digest(
        {
            "schema_version": payload["schema_version"],
            "request_kind": payload["request_kind"],
            "references": payload["references"],
        }
    )
    if expected_hash != ticket.manifest_hash:
        _reject("TICKET_MANIFEST_HASH_MISMATCH")
    ticket.manifest_path.write_text(
        json.dumps(payload, sort_keys=True, separators=(",", ":")),
        encoding="utf-8",
    )
    return executor_inputs, ticket.manifest_path


def _input_manifest(materialized: MaterializedProviderInputLease) -> tuple[dict[str, object], ...]:
    return tuple(entry.model_dump(mode="json") for entry in materialized.state.lease.inputs)


def _retry_policy(result: CreativeImageExecutionResult) -> Literal[
    "NONE", "RECONCILE_ONLY", "EXPLICIT_NEW_IDEMPOTENCY_KEY"
]:
    if result.status == "UNKNOWN":
        return "RECONCILE_ONLY"
    if result.status == "FAILED":
        return "EXPLICIT_NEW_IDEMPOTENCY_KEY"
    return "NONE"


def _audit(
    result: CreativeImageExecutionResult,
    *,
    lease: MaterializedProviderInputLease,
    ticket_state: str,
    execution_mode: ExecutionMode,
) -> CreativeImageWorkflowAudit:
    input_manifest = _input_manifest(lease)
    stage_audit = (
        {"stage": "DURABLE_TICKET", "status": ticket_state, "error_code": ""},
        {"stage": "DURABLE_INPUT_LEASE", "status": lease.state.status, "error_code": ""},
        {"stage": "IMAGE_EXECUTOR", "status": result.status, "error_code": result.error_code or ""},
    )
    payload = {
        "schema_version": "creative-image-workflow-audit.v1",
        "status": result.status,
        "execution_mode": execution_mode,
        "ticket_id": result.ticket_id,
        "lease_id": lease.state.lease.lease_id,
        "idempotency_key": result.idempotency_key,
        "request_hash": lease.state.lease.request_hash,
        "evidence_hash": lease.state.lease.evidence_hash,
        "preflight_hash": lease.state.lease.preflight_hash,
        "ticket_state": ticket_state,
        "lease_state": lease.state.status,
        "actual_submitted": result.actual_submitted,
        "provider_task_id": result.provider_task_id,
        "response_digest": result.response_digest,
        "error_code": result.error_code,
        "retry_policy": _retry_policy(result),
        "qualification_scope": "OFFLINE_SYNTHETIC_ONLY",
        "deliverable_eligible": False,
        "input_manifest": input_manifest,
        "input_manifest_hash": digest(input_manifest),
        "stage_audit": stage_audit,
    }
    return CreativeImageWorkflowAudit(
        schema_version="creative-image-workflow-audit.v1",
        status=result.status,
        execution_mode=execution_mode,
        ticket_id=result.ticket_id,
        lease_id=lease.state.lease.lease_id,
        idempotency_key=result.idempotency_key,
        request_hash=lease.state.lease.request_hash,
        evidence_hash=lease.state.lease.evidence_hash,
        preflight_hash=lease.state.lease.preflight_hash,
        ticket_state=ticket_state,
        lease_state=lease.state.status,
        actual_submitted=result.actual_submitted,
        provider_task_id=result.provider_task_id,
        response_digest=result.response_digest,
        error_code=result.error_code,
        retry_policy=_retry_policy(result),
        qualification_scope="OFFLINE_SYNTHETIC_ONLY",
        deliverable_eligible=False,
        input_manifest=input_manifest,
        input_manifest_hash=payload["input_manifest_hash"],
        stage_audit=stage_audit,
        summary_hash=digest(payload),
    )


async def execute_creative_image_workflow(
    session: AsyncSession,
    *,
    task: CreativeTask,
    request: CreativeImageProviderRequest,
    ticket: ProviderSubmissionTicket,
    preflight: CreativeProviderPreflightResult,
    owner_id,
    object_store,
    settings: Settings,
    capability: ProviderCapabilityDeclaration,
    approval_manifest_path: Path,
    controls: CreativeImageWorkflowControls | None = None,
    adapter=None,
    approval: ProviderApprovalManifest | None = None,
    ticket_store: DurableSubmissionTicketStore | None = None,
    lease_store: DurableProviderInputLeaseStore | None = None,
    now: datetime | None = None,
) -> CreativeImageWorkflowResult:
    """Run the auditable ticket → durable lease → image executor chain."""

    controls = controls or CreativeImageWorkflowControls()
    current_time = _now(now)
    _assert_single_image_contract(request, ticket, preflight)
    _assert_task_not_stopped(task)

    ticket_store = ticket_store or DurableSubmissionTicketStore()
    lease_store = lease_store or DurableProviderInputLeaseStore()
    saved = await ticket_store.get(session, ticket.idempotency_key)
    _assert_ticket_is_replay_safe(saved, requested_mode=controls.mode)
    if saved.ticket != ticket:
        _reject("TICKET_STALE")

    if controls.mode == "live":
        _assert_live_admission(
            settings,
            controls,
            approval=approval,
            capability=capability,
            approval_manifest_path=approval_manifest_path,
        )

    try:
        await lease_store.create(
            session,
            task,
            request,
            ticket,
            owner_id=owner_id,
            object_store=object_store,
            settings=settings,
            capability=capability,
            approval_manifest_path=approval_manifest_path,
            now=current_time,
        )
        async with await lease_store.materialize(
            session,
            task,
            request,
            ticket,
            owner_id=owner_id,
            object_store=object_store,
            settings=settings,
            capability=capability,
            approval_manifest_path=approval_manifest_path,
            now=current_time,
        ) as materialized:
            executor_inputs, manifest_path = _executor_materialization(ticket, materialized)
            executor_preflight = preflight.model_copy(
                update={
                    "materialized_inputs": tuple(executor_inputs),
                    "manifest_path": manifest_path,
                }
            )

            # MVP-7A proves the service chain and audit shape, but never opens
            # the real Provider branch. All admission checks above still run.
            if controls.mode == "live":
                _reject("LIVE_EXECUTION_DISABLED_MVP7A")

            try:
                execution = await execute_creative_image(
                    session,
                    task=task,
                    request=request,
                    ticket=ticket,
                    preflight=executor_preflight,
                    owner_id=owner_id,
                    object_store=object_store,
                    settings=settings,
                    controls=CreativeExecutionControls(
                        mode=controls.mode,
                        admin_live_enabled=controls.admin_live_enabled,
                        human_confirmed=controls.human_confirmed,
                    ),
                    adapter=adapter,
                    approval=approval,
                    capability=capability,
                    approval_manifest_path=approval_manifest_path,
                    now=current_time,
                )
            except CreativeProviderExecutionRejected as exc:
                raise CreativeImageWorkflowRejected(exc.code) from exc
            audit = _audit(
                execution,
                lease=materialized,
                ticket_state=saved.state,
                execution_mode=controls.mode,
            )
            return CreativeImageWorkflowResult(execution=execution, audit=audit)
    except ProviderInputLeaseRejected as exc:
        raise CreativeImageWorkflowRejected(exc.code) from exc
