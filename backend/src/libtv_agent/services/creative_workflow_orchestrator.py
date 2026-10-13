"""Provider-free Creative Workflow orchestration facade.

This service adapts immutable stage snapshots to the MVP-6A reality-loop
gate. It emits one bounded command and audit facts; it never executes a
command, calls a model or Provider, persists state, or writes qualification.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime
from hashlib import sha256
from typing import Any, Literal

from libtv_agent.services.creative_reality_loop_gate import (
    CallStatus,
    CriticReport,
    DirectionEvidence,
    GateSnapshot,
    LayerEvidence,
    LoopAuthorization,
    PackageRevisionSummary,
    ProductBrandLock,
    PromptPreservationEvidence,
    PromptRevisionSummary,
    RealityEvidence,
    Stage,
    StopReason,
)
from libtv_agent.services.creative_reality_loop_gate import decide as decide_reality_loop

CommandKind = Literal[
    "RUN_STAGE",
    "CALL_E1",
    "CALL_CRITIC",
    "PROPOSE_REVISION",
    "WAIT_RECONCILIATION",
    "STOP",
]


def _digest(value: object) -> str:
    return sha256(
        json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        ).encode("utf-8")
    ).hexdigest()


@dataclass(frozen=True, slots=True)
class TextPackageSnapshot:
    """The immutable D4/TEXT_PACKAGE evidence needed by the gate."""

    preservation: PromptPreservationEvidence
    prompt_revision: PromptRevisionSummary
    package_revision: PackageRevisionSummary
    scene: LayerEvidence
    composition: LayerEvidence


@dataclass(frozen=True, slots=True)
class E1Snapshot:
    """Caller-owned E1 accounting/result snapshot; no execution is performed here."""

    calls_used: int = 0
    total_cost_micros: int = 0
    planned_call_cost_micros: int = 0
    last_call_status: CallStatus | None = None


@dataclass(frozen=True, slots=True)
class CreativeWorkflowSnapshot:
    """All evidence required for one provider-free orchestration decision."""

    loop_id: str
    now: datetime
    authorization: LoopAuthorization
    product: ProductBrandLock | None = None
    direction: DirectionEvidence | None = None
    dna_reality: RealityEvidence | None = None
    text_package: TextPackageSnapshot | None = None
    e1: E1Snapshot = E1Snapshot()
    critic: CriticReport | None = None
    critic_history: tuple[CriticReport, ...] = ()
    trace: tuple[Stage, ...] = ()
    revision_index: int = 0
    stopped: bool = False
    revision_history: tuple[PackageRevisionSummary, ...] = ()

    def to_gate_snapshot(self) -> GateSnapshot:
        package = self.text_package
        return GateSnapshot(
            loop_id=self.loop_id,
            now=self.now,
            authorization=self.authorization,
            product_lock=self.product,
            direction=self.direction,
            reality=self.dna_reality,
            scene=package.scene if package else None,
            composition=package.composition if package else None,
            prompt=package.preservation if package else None,
            current_package=package.package_revision if package else None,
            current_prompt=package.prompt_revision if package else None,
            trace=self.trace,
            calls_used=self.e1.calls_used,
            total_cost_micros=self.e1.total_cost_micros,
            planned_call_cost_micros=self.e1.planned_call_cost_micros,
            revision_index=self.revision_index,
            stopped=self.stopped,
            last_call_status=self.e1.last_call_status,
            critic=self.critic,
            critic_history=self.critic_history,
            revision_history=self.revision_history,
        )


@dataclass(frozen=True, slots=True)
class NextStageCommand:
    """An inert command description for a future executor."""

    command_id: str
    kind: CommandKind
    stage: Stage | None
    expected_call_count: int
    expected_cost_micros: int
    requires_human_review: bool
    execution_mode: Literal["AUDIT_ONLY"] = "AUDIT_ONLY"
    provider_execution_allowed: Literal[False] = False


@dataclass(frozen=True, slots=True)
class RevisionSummary:
    """Immutable revision metadata; it intentionally contains no Prompt text."""

    revision_index: int
    changed_module: str
    causal_variable: str
    parent_prompt_revision_id: str
    prompt_revision_id: str
    parent_package_revision_id: str
    package_revision_id: str
    prompt_content_hash: str
    preservation_hash: str
    human_qualification: Literal["PENDING_HUMAN_REVIEW"] = "PENDING_HUMAN_REVIEW"

    @classmethod
    def from_gate(
        cls,
        prompt: PromptRevisionSummary,
        package: PackageRevisionSummary,
    ) -> RevisionSummary:
        return cls(
            revision_index=package.revision_index,
            changed_module=package.changed_module,
            causal_variable=package.causal_variable,
            parent_prompt_revision_id=prompt.parent_prompt_revision_id,
            prompt_revision_id=prompt.prompt_revision_id,
            parent_package_revision_id=package.parent_package_revision_id,
            package_revision_id=package.package_revision_id,
            prompt_content_hash=prompt.content_hash,
            preservation_hash=prompt.preservation_hash,
        )


@dataclass(frozen=True, slots=True)
class AuditEvent:
    """Append-only-shaped event emitted to the caller, not persisted by this service."""

    event_id: str
    event_type: Literal["CREATIVE_ORCHESTRATOR_DECISION"]
    loop_id: str
    iteration_index: int
    action: CommandKind
    stage: Stage | None
    trace: tuple[Stage, ...]
    stop_reason_code: str | None
    human_review_required: bool
    ai_qualification: Literal["UNVERIFIED"] = "UNVERIFIED"
    provider_called: Literal[False] = False
    production_write: Literal[False] = False


@dataclass(frozen=True, slots=True)
class OrchestrationResult:
    """The complete output contract for one autonomous decision step."""

    command: NextStageCommand
    revision_summary: RevisionSummary | None
    stop_wait_reason: StopReason | None
    audit_event: AuditEvent

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class CreativeWorkflowOrchestrator:
    """Provider-free facade around the MVP-6A gate."""

    def decide(self, snapshot: CreativeWorkflowSnapshot) -> OrchestrationResult:
        decision = decide_reality_loop(snapshot.to_gate_snapshot())
        kind = decision.action
        command_id = _digest(
            {
                "loop_id": decision.loop_id,
                "iteration_index": decision.iteration_index,
                "action": decision.action,
                "stage": decision.stage,
                "changed_module": decision.changed_module,
                "causal_variable": decision.causal_variable,
            }
        )[:24]
        command = NextStageCommand(
            command_id=f"{decision.loop_id}:{command_id}",
            kind=kind,
            stage=decision.stage,
            expected_call_count=decision.expected_call_count,
            expected_cost_micros=decision.expected_cost_micros,
            requires_human_review=decision.human_review_required,
        )
        revision = None
        if decision.new_prompt_revision is not None and decision.new_package_revision is not None:
            revision = RevisionSummary.from_gate(
                decision.new_prompt_revision,
                decision.new_package_revision,
            )
        reason = decision.stop_reason
        event_basis = {
            "loop_id": decision.loop_id,
            "iteration_index": decision.iteration_index,
            "action": decision.action,
            "stage": decision.stage,
            "trace": decision.audit.trace,
            "revision": asdict(revision) if revision else None,
            "reason": asdict(reason) if reason else None,
        }
        audit = AuditEvent(
            event_id=f"creative-orchestrator:{_digest(event_basis)[:24]}",
            event_type="CREATIVE_ORCHESTRATOR_DECISION",
            loop_id=decision.loop_id,
            iteration_index=decision.iteration_index,
            action=kind,
            stage=decision.stage,
            trace=decision.audit.trace,
            stop_reason_code=reason.code if reason else None,
            human_review_required=decision.human_review_required,
        )
        return OrchestrationResult(
            command=command,
            revision_summary=revision,
            stop_wait_reason=reason,
            audit_event=audit,
        )


def decide(snapshot: CreativeWorkflowSnapshot) -> OrchestrationResult:
    """Convenience entry point for one bounded orchestration decision."""

    return CreativeWorkflowOrchestrator().decide(snapshot)

