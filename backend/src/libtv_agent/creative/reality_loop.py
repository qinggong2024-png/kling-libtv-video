"""Pure, bounded strategy for an authorized reality-improvement loop.

This module plans the next step only. It does not call a Provider, persist a
record, run a worker, or assign an AI result a human qualification status.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Literal

REALITY_ORDER = (
    "Camera",
    "Lighting",
    "Composition",
    "Human Behavior",
    "Environment",
    "Imperfection",
)

PIPELINE = (
    "Product",
    "Direction",
    "DNA_REALITY",
    "TEXT_PACKAGE",
    "AUTHORIZATION",
    "E1",
    "CRITIC",
    "TARGETED_REVISION",
)

CALL_STAGES = frozenset({"DNA_REALITY", "TEXT_PACKAGE", "E1", "CRITIC"})
REVISION_MODULES = frozenset({"Scene", "Reality", "Composition"})

Stage = Literal[
    "Product",
    "Direction",
    "DNA_REALITY",
    "TEXT_PACKAGE",
    "AUTHORIZATION",
    "E1",
    "CRITIC",
    "TARGETED_REVISION",
]
CallStatus = Literal["SUCCEEDED", "UNKNOWN", "WRITE_UNCERTAIN"]
CriticDecision = Literal["NEEDS_REVISION", "NO_ACTION", "UNVERIFIED"]
Progress = Literal["IMPROVED", "UNCHANGED", "WORSE", "UNKNOWN"]
DecisionAction = Literal[
    "RUN_STAGE",
    "CALL_E1",
    "CALL_CRITIC",
    "PROPOSE_REVISION",
    "WAIT_RECONCILIATION",
    "STOP",
]
StopCode = Literal[
    "LOOP_DISABLED",
    "CALL_LIMIT",
    "BUDGET_EXHAUSTED",
    "AUTH_EXPIRED",
    "USER_STOPPED",
    "NO_PROGRESS",
    "LOCK_CONFLICT",
    "UNVERIFIED_PIXELS",
    "EXECUTION_UNKNOWN",
    "DEPENDENCY_BLOCKED",
    "QUALITY_TARGET_MET",
    "LIMIT_REACHED",
]


def _tuple(value: tuple[str, ...] | list[str]) -> tuple[str, ...]:
    return tuple(value)


def _require_text(value: str, name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a non-empty string")


def _require_aware(value: datetime, name: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must include timezone")


@dataclass(frozen=True, slots=True)
class StopReason:
    code: StopCode
    detail: str
    recoverable: bool = False

    def __post_init__(self) -> None:
        _require_text(self.detail, "detail")


@dataclass(frozen=True, slots=True)
class LoopAuthorization:
    """The already-confirmed authorization envelope for this loop."""

    enabled: bool = False
    max_revisions: int = 1
    max_calls: int = 6
    max_total_cost_micros: int = 0
    expires_at: datetime | None = None
    allowed_modules: tuple[str, ...] = ("Reality",)
    locked_modules: tuple[str, ...] = ()
    locked_variables: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.max_revisions, int) or not 0 <= self.max_revisions <= 2:
            raise ValueError("max_revisions must be between 0 and 2")
        if not isinstance(self.max_calls, int) or self.max_calls < 1:
            raise ValueError("max_calls must be at least 1")
        if not isinstance(self.max_total_cost_micros, int) or self.max_total_cost_micros < 0:
            raise ValueError("max_total_cost_micros must be non-negative")
        if self.expires_at is not None:
            _require_aware(self.expires_at, "expires_at")
        if self.enabled and self.expires_at is None:
            raise ValueError("enabled authorization requires expires_at")
        allowed = _tuple(self.allowed_modules)
        locked_modules = _tuple(self.locked_modules)
        locked_variables = _tuple(self.locked_variables)
        if any(not isinstance(value, str) or not value.strip() for value in (
            *allowed,
            *locked_modules,
            *locked_variables,
        )):
            raise ValueError("module and variable names must be non-empty strings")
        object.__setattr__(self, "allowed_modules", allowed)
        object.__setattr__(self, "locked_modules", locked_modules)
        object.__setattr__(self, "locked_variables", locked_variables)


@dataclass(frozen=True, slots=True)
class CriticFinding:
    """One causal observation; it is not a qualification decision."""

    module: str
    causal_variable: str
    severity: int
    evidence: str
    locked: bool = False
    progress: Progress = "UNKNOWN"

    def __post_init__(self) -> None:
        _require_text(self.module, "module")
        _require_text(self.causal_variable, "causal_variable")
        _require_text(self.evidence, "evidence")
        if not isinstance(self.severity, int) or not 1 <= self.severity <= 3:
            raise ValueError("severity must be between 1 and 3")
        if self.progress not in {"IMPROVED", "UNCHANGED", "WORSE", "UNKNOWN"}:
            raise ValueError("unsupported progress value")


@dataclass(frozen=True, slots=True)
class CriticReport:
    """A structured critic result with only non-qualification conclusions."""

    iteration_index: int
    decision: CriticDecision
    findings: tuple[CriticFinding, ...] = ()
    pixels_verified: bool = True

    def __post_init__(self) -> None:
        if not isinstance(self.iteration_index, int) or self.iteration_index < 0:
            raise ValueError("iteration_index must be non-negative")
        if self.decision not in {"NEEDS_REVISION", "NO_ACTION", "UNVERIFIED"}:
            raise ValueError("critic decision is not an allowed AI conclusion")
        findings = tuple(self.findings)
        if self.decision == "NEEDS_REVISION" and not findings:
            raise ValueError("NEEDS_REVISION requires at least one finding")
        if self.decision == "NO_ACTION" and findings:
            raise ValueError("NO_ACTION cannot contain revision findings")
        object.__setattr__(self, "findings", findings)


@dataclass(frozen=True, slots=True)
class LoopSnapshot:
    """Immutable caller-owned snapshot used to make one strategy decision."""

    loop_id: str
    now: datetime
    authorization: LoopAuthorization
    trace: tuple[Stage, ...] = ()
    calls_used: int = 0
    total_cost_micros: int = 0
    planned_call_cost_micros: int = 0
    revision_index: int = 0
    stopped: bool = False
    last_call_status: CallStatus | None = None
    critic: CriticReport | None = None
    critic_history: tuple[CriticReport, ...] = ()

    def __post_init__(self) -> None:
        _require_text(self.loop_id, "loop_id")
        _require_aware(self.now, "now")
        if not isinstance(self.calls_used, int) or self.calls_used < 0:
            raise ValueError("calls_used must be non-negative")
        if not isinstance(self.total_cost_micros, int) or self.total_cost_micros < 0:
            raise ValueError("total_cost_micros must be non-negative")
        if not isinstance(self.planned_call_cost_micros, int) \
                or self.planned_call_cost_micros < 0:
            raise ValueError("planned_call_cost_micros must be non-negative")
        if not isinstance(self.revision_index, int) or self.revision_index < 0:
            raise ValueError("revision_index must be non-negative")
        trace = tuple(self.trace)
        history = tuple(self.critic_history)
        if any(stage not in PIPELINE for stage in trace):
            raise ValueError("trace contains an unknown stage")
        if self.last_call_status not in {None, "SUCCEEDED", "UNKNOWN", "WRITE_UNCERTAIN"}:
            raise ValueError("unsupported call status")
        object.__setattr__(self, "trace", trace)
        object.__setattr__(self, "critic_history", history)


@dataclass(frozen=True, slots=True)
class IterationDecision:
    """The append-only decision payload returned by :func:`decide`."""

    loop_id: str
    iteration_index: int
    action: DecisionAction
    stage: Stage | None = None
    changed_module: str | None = None
    causal_variable: str | None = None
    expected_call_count: int = 0
    expected_cost_micros: int = 0
    stop_reason: StopReason | None = None
    human_review_required: bool = False

    def __post_init__(self) -> None:
        _require_text(self.loop_id, "loop_id")
        if self.iteration_index < 0:
            raise ValueError("iteration_index must be non-negative")
        if self.expected_call_count not in {0, 1}:
            raise ValueError("expected_call_count must be 0 or 1")
        if self.expected_cost_micros < 0:
            raise ValueError("expected_cost_micros must be non-negative")
        if self.action == "STOP" and self.stop_reason is None:
            raise ValueError("STOP requires stop_reason")
        if self.action not in {"STOP", "WAIT_RECONCILIATION"} and self.stop_reason is not None:
            raise ValueError("only STOP may carry stop_reason")
        if self.action == "PROPOSE_REVISION":
            if not self.changed_module or not self.causal_variable:
                raise ValueError("revision requires one module and causal variable")
        if self.action != "PROPOSE_REVISION" and (
            self.changed_module is not None or self.causal_variable is not None
        ):
            raise ValueError("only revision decisions carry a target variable")


def _stop(snapshot: LoopSnapshot, code: StopCode, detail: str, *,
          recoverable: bool = False, human_review_required: bool = False) -> IterationDecision:
    return IterationDecision(
        loop_id=snapshot.loop_id,
        iteration_index=snapshot.revision_index,
        action="STOP",
        stop_reason=StopReason(code, detail, recoverable),
        human_review_required=human_review_required,
    )


def _validate_trace(trace: tuple[Stage, ...]) -> None:
    base = PIPELINE[:5]
    if trace[: min(len(trace), len(base))] != base[: min(len(trace), len(base))]:
        raise ValueError("trace must start with Product through Authorization in order")
    if len(trace) <= len(base):
        return
    tail = trace[len(base):]
    expected_cycle = ("E1", "CRITIC", "TARGETED_REVISION")
    for index, stage in enumerate(tail):
        if stage != expected_cycle[index % len(expected_cycle)]:
            raise ValueError("trace must repeat E1 -> CRITIC -> TARGETED_REVISION")


def _next_stage(trace: tuple[Stage, ...]) -> Stage | None:
    base_length = 5
    if len(trace) < base_length:
        return PIPELINE[len(trace)]
    if len(trace) == base_length or trace[-1] == "TARGETED_REVISION":
        return "E1"
    if trace[-1] == "E1":
        return "CRITIC"
    return None


def _preflight(snapshot: LoopSnapshot) -> IterationDecision | None:
    if snapshot.stopped:
        return _stop(snapshot, "USER_STOPPED", "user stopped the loop")
    if not snapshot.authorization.enabled:
        return _stop(snapshot, "LOOP_DISABLED", "truthfulness loop authorization is disabled")
    expires_at = snapshot.authorization.expires_at
    if expires_at is not None and snapshot.now >= expires_at:
        return _stop(snapshot, "AUTH_EXPIRED", "loop authorization has expired")
    if snapshot.last_call_status in {"UNKNOWN", "WRITE_UNCERTAIN"}:
        return IterationDecision(
            loop_id=snapshot.loop_id,
            iteration_index=snapshot.revision_index,
            action="WAIT_RECONCILIATION",
            stop_reason=StopReason(
                "EXECUTION_UNKNOWN",
                f"last execution status is {snapshot.last_call_status}; reconcile before retry",
                True,
            ),
        )
    return None


def _budget_gate(snapshot: LoopSnapshot, stage: Stage) -> IterationDecision | None:
    if stage not in CALL_STAGES:
        return None
    authorization = snapshot.authorization
    if snapshot.calls_used >= authorization.max_calls:
        return _stop(snapshot, "CALL_LIMIT", "authorized model call limit is exhausted")
    projected = snapshot.total_cost_micros + snapshot.planned_call_cost_micros
    if projected > authorization.max_total_cost_micros:
        return _stop(snapshot, "BUDGET_EXHAUSTED", "authorized total cost would be exceeded")
    return None


def _stage_decision(snapshot: LoopSnapshot, stage: Stage) -> IterationDecision:
    budget = _budget_gate(snapshot, stage)
    if budget is not None:
        return budget
    action: DecisionAction = {
        "E1": "CALL_E1",
        "CRITIC": "CALL_CRITIC",
    }.get(stage, "RUN_STAGE")
    is_call = stage in CALL_STAGES
    return IterationDecision(
        loop_id=snapshot.loop_id,
        iteration_index=snapshot.revision_index,
        action=action,
        stage=stage,
        expected_call_count=int(is_call),
        expected_cost_micros=snapshot.planned_call_cost_micros if is_call else 0,
    )


def _revision_target(
    snapshot: LoopSnapshot, report: CriticReport,
) -> tuple[CriticFinding | None, bool]:
    authorization = snapshot.authorization
    eligible = tuple(
        finding for finding in report.findings
        if not finding.locked
        and finding.module in authorization.allowed_modules
        and finding.module not in authorization.locked_modules
        and finding.causal_variable not in authorization.locked_variables
    )
    if not eligible:
        return None, bool(report.findings)
    # Stable order keeps a critic from smuggling in a second simultaneous edit.
    return max(
        enumerate(eligible),
        key=lambda item: (item[1].severity, -item[0]),
    )[1], False


def _has_two_non_improvements(
    report: CriticReport, history: tuple[CriticReport, ...], target: CriticFinding,
) -> bool:
    reports = (*history, report)
    matching = [
        finding
        for prior in reports
        for finding in prior.findings
        if finding.module == target.module
        and finding.causal_variable == target.causal_variable
    ]
    if len(matching) < 2:
        return False
    return all(item.progress != "IMPROVED" for item in matching[-2:])


def _after_critic(snapshot: LoopSnapshot) -> IterationDecision:
    report = snapshot.critic
    if report is None:
        return _stop(
            snapshot,
            "DEPENDENCY_BLOCKED",
            "E1 must produce a critic report before revision",
        )
    if not report.pixels_verified or report.decision == "UNVERIFIED":
        return _stop(
            snapshot,
            "UNVERIFIED_PIXELS",
            "pixel evidence is unavailable or the critic cannot verify the output",
            recoverable=True,
        )
    if report.decision == "NO_ACTION":
        return _stop(
            snapshot,
            "QUALITY_TARGET_MET",
            "critic found no actionable issue; human review is still required",
            human_review_required=True,
        )
    target, blocked = _revision_target(snapshot, report)
    if target is None:
        return _stop(
            snapshot,
            "LOCK_CONFLICT" if blocked else "DEPENDENCY_BLOCKED",
            "no critic finding is both unlocked and inside the authorized module set",
            recoverable=True,
        )
    if _has_two_non_improvements(report, snapshot.critic_history, target):
        return _stop(
            snapshot,
            "NO_PROGRESS",
            f"causal variable {target.causal_variable!r} did not improve in two reviews",
            recoverable=True,
        )
    if snapshot.revision_index >= snapshot.authorization.max_revisions:
        return _stop(snapshot, "LIMIT_REACHED", "authorized revision limit is exhausted")
    return IterationDecision(
        loop_id=snapshot.loop_id,
        iteration_index=snapshot.revision_index + 1,
        action="PROPOSE_REVISION",
        stage="TARGETED_REVISION",
        changed_module=target.module,
        causal_variable=target.causal_variable,
    )


def decide(snapshot: LoopSnapshot) -> IterationDecision:
    """Return exactly one bounded next-step decision without performing it."""
    _validate_trace(snapshot.trace)
    preflight = _preflight(snapshot)
    if preflight is not None:
        return preflight
    stage = _next_stage(snapshot.trace)
    if stage is not None:
        return _stage_decision(snapshot, stage)
    return _after_critic(snapshot)
