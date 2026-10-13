"""Pure runtime gate for the bounded Creative Reality loop.

The gate consumes immutable evidence snapshots and returns one next-step
decision.  It deliberately does not call a model or Provider, persist a
record, reserve budget, write qualification, or mutate production state.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from hashlib import sha256
from typing import Literal

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
REALITY_ORDER = (
    "Camera",
    "Lighting",
    "Composition",
    "Human Behavior",
    "Environment",
    "Imperfection",
)
CALL_STAGES = frozenset({"DNA_REALITY", "TEXT_PACKAGE", "E1", "CRITIC"})
REVISION_MODULES = frozenset({"Scene", "Reality", "Composition"})
EVIDENCE_STATUSES = frozenset(
    {"OBSERVED", "USER_LOCKED", "LIBRARY_SNAPSHOT", "PROPOSED", "USER_ASSUMED", "NOT_APPLICABLE"}
)

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
EvidenceStatus = Literal[
    "OBSERVED",
    "USER_LOCKED",
    "LIBRARY_SNAPSHOT",
    "PROPOSED",
    "USER_ASSUMED",
    "NOT_APPLICABLE",
]
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
    "HUMAN_AUTHORIZATION_REQUIRED",
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
    "MODULE_NOT_AUTHORIZED",
    "PROMPT_PRESERVATION_FAILED",
]


def _require_text(value: str, name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a non-empty string")


def _require_aware(value: datetime, name: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must include timezone")


def _tuple(values: tuple[str, ...] | list[str]) -> tuple[str, ...]:
    return tuple(values)


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
class ProductBrandLock:
    """Canonical Product and explicitly selected brand evidence."""

    product_id: str
    product_revision: str
    product_source_hash: str
    brand_id: str | None = None
    brand_revision: str | None = None
    brand_source: Literal["USER_SELECTED", "USER_SELECTED_GENERIC", "LIBRARY_SNAPSHOT"] = (
        "USER_SELECTED_GENERIC"
    )
    locked_fields: tuple[str, ...] = ("product_identity", "brand_identity")

    def __post_init__(self) -> None:
        for value, name in (
            (self.product_id, "product_id"),
            (self.product_revision, "product_revision"),
            (self.product_source_hash, "product_source_hash"),
        ):
            _require_text(value, name)
        if self.brand_id is None and self.brand_source != "USER_SELECTED_GENERIC":
            raise ValueError("brand_source must be USER_SELECTED_GENERIC when brand_id is absent")
        if self.brand_id is not None:
            _require_text(self.brand_id, "brand_id")
            _require_text(self.brand_revision or "", "brand_revision")
        fields = _tuple(self.locked_fields)
        if not fields or any(not value.strip() for value in fields):
            raise ValueError("locked_fields must contain non-empty names")
        object.__setattr__(self, "locked_fields", fields)

    @property
    def product_lock_digest(self) -> str:
        return _digest(
            {
                "product_id": self.product_id,
                "product_revision": self.product_revision,
                "product_source_hash": self.product_source_hash,
            }
        )

    @property
    def brand_lock_digest(self) -> str:
        return _digest(
            {
                "brand_id": self.brand_id,
                "brand_revision": self.brand_revision,
                "brand_source": self.brand_source,
            }
        )


@dataclass(frozen=True, slots=True)
class DirectionEvidence:
    direction_id: str
    direction_revision: str
    selected_by_human: bool = True
    difference_axes: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        _require_text(self.direction_id, "direction_id")
        _require_text(self.direction_revision, "direction_revision")
        axes = _tuple(self.difference_axes)
        if any(not value.strip() for value in axes):
            raise ValueError("difference_axes must contain non-empty names")
        object.__setattr__(self, "difference_axes", axes)


@dataclass(frozen=True, slots=True)
class RealityDimensionEvidence:
    dimension: str
    decision: str
    evidence_status: EvidenceStatus
    evidence: str
    na_reason: str | None = None
    rule_id: str | None = None
    rules_version: str | None = None
    rules_hash: str | None = None
    required_context: str | None = None
    generation_constraint: str | None = None
    judgment_standard: str | None = None
    review_axis: str | None = None
    revision_module: str | None = None
    causal_variable: str | None = None

    def __post_init__(self) -> None:
        if self.dimension not in REALITY_ORDER:
            raise ValueError("unsupported Reality dimension")
        _require_text(self.decision, "decision")
        if self.evidence_status not in EVIDENCE_STATUSES:
            raise ValueError("unsupported evidence_status")
        _require_text(self.evidence, "evidence")
        if self.decision.strip().upper() in {"N/A", "NA"}:
            _require_text(self.na_reason or "", "na_reason")
        rule_values = (
            self.rule_id, self.rules_version, self.rules_hash, self.required_context,
            self.generation_constraint, self.judgment_standard, self.review_axis,
            self.revision_module, self.causal_variable,
        )
        if any(value is not None for value in rule_values):
            for value in rule_values:
                _require_text(value or "", "Reality rule field")
            if self.revision_module not in REVISION_MODULES:
                raise ValueError("Reality rule revision module is unsupported")


@dataclass(frozen=True, slots=True)
class RealityEvidence:
    dimensions: tuple[RealityDimensionEvidence, ...]

    def __post_init__(self) -> None:
        dimensions = tuple(self.dimensions)
        if tuple(item.dimension for item in dimensions) != REALITY_ORDER:
            raise ValueError("Reality evidence must contain all six dimensions in fixed order")
        object.__setattr__(self, "dimensions", dimensions)

    @property
    def evidence_digest(self) -> str:
        return _digest(
            [
                {
                    "dimension": item.dimension,
                    "decision": item.decision,
                    "evidence_status": item.evidence_status,
                    "evidence": item.evidence,
                    "na_reason": item.na_reason,
                    **{
                        key: getattr(item, key) for key in (
                            "rule_id", "rules_version", "rules_hash", "required_context",
                            "generation_constraint", "judgment_standard", "review_axis",
                            "revision_module", "causal_variable",
                        ) if getattr(item, key) is not None
                    },
                }
                for item in self.dimensions
            ]
        )


@dataclass(frozen=True, slots=True)
class LayerEvidence:
    layer: Literal["Scene", "Composition"]
    revision: str
    source_hash: str
    evidence_status: EvidenceStatus
    summary: str
    shot_id: str = "FIRST_FRAME"

    def __post_init__(self) -> None:
        _require_text(self.revision, "revision")
        _require_text(self.source_hash, "source_hash")
        _require_text(self.summary, "summary")
        _require_text(self.shot_id, "shot_id")
        if self.evidence_status not in EVIDENCE_STATUSES:
            raise ValueError("unsupported evidence_status")

    @property
    def evidence_digest(self) -> str:
        return _digest(
            {
                "layer": self.layer,
                "revision": self.revision,
                "source_hash": self.source_hash,
                "evidence_status": self.evidence_status,
                "summary": self.summary,
                "shot_id": self.shot_id,
            }
        )


@dataclass(frozen=True, slots=True)
class PromptPreservationEvidence:
    """Evidence that the locked prompt still preserves upstream contracts."""

    prompt_revision_id: str
    prompt_hash: str
    product_lock_digest: str
    brand_lock_digest: str
    preserved_fields: tuple[str, ...] = (
        "product_lock",
        "brand_lock",
        "reality",
        "scene",
        "composition",
    )
    verified: bool = True
    drift_fields: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        for value, name in (
            (self.prompt_revision_id, "prompt_revision_id"),
            (self.prompt_hash, "prompt_hash"),
            (self.product_lock_digest, "product_lock_digest"),
            (self.brand_lock_digest, "brand_lock_digest"),
        ):
            _require_text(value, name)
        preserved = _tuple(self.preserved_fields)
        drift = _tuple(self.drift_fields)
        if not preserved:
            raise ValueError("preserved_fields must not be empty")
        if any(not value.strip() for value in (*preserved, *drift)):
            raise ValueError("prompt preservation fields must be non-empty")
        object.__setattr__(self, "preserved_fields", preserved)
        object.__setattr__(self, "drift_fields", drift)

    @property
    def evidence_digest(self) -> str:
        return _digest(
            {
                "prompt_revision_id": self.prompt_revision_id,
                "prompt_hash": self.prompt_hash,
                "product_lock_digest": self.product_lock_digest,
                "brand_lock_digest": self.brand_lock_digest,
                "preserved_fields": self.preserved_fields,
                "verified": self.verified,
                "drift_fields": self.drift_fields,
            }
        )


@dataclass(frozen=True, slots=True)
class PromptRevisionSummary:
    prompt_revision_id: str
    revision_index: int
    parent_prompt_revision_id: str
    content_hash: str
    preservation_hash: str
    immutable: Literal[True] = True

    def __post_init__(self) -> None:
        _require_text(self.prompt_revision_id, "prompt_revision_id")
        _require_text(self.parent_prompt_revision_id, "parent_prompt_revision_id")
        _require_text(self.content_hash, "content_hash")
        _require_text(self.preservation_hash, "preservation_hash")
        if self.revision_index < 0:
            raise ValueError("revision_index must be non-negative for a revision summary")
        if self.immutable is not True:
            raise ValueError("prompt revision summary must be immutable")


@dataclass(frozen=True, slots=True)
class PackageRevisionSummary:
    package_revision_id: str
    prompt_revision_id: str
    revision_index: int
    parent_package_revision_id: str
    parent_prompt_revision_id: str
    product_lock_digest: str
    brand_lock_digest: str
    reality_digest: str
    scene_digest: str
    composition_digest: str
    prompt_preservation_digest: str
    changed_module: str
    causal_variable: str
    immutable: Literal[True] = True
    human_qualification: Literal["PENDING_HUMAN_REVIEW"] = "PENDING_HUMAN_REVIEW"

    def __post_init__(self) -> None:
        for value, name in (
            (self.package_revision_id, "package_revision_id"),
            (self.prompt_revision_id, "prompt_revision_id"),
            (self.parent_package_revision_id, "parent_package_revision_id"),
            (self.parent_prompt_revision_id, "parent_prompt_revision_id"),
            (self.product_lock_digest, "product_lock_digest"),
            (self.brand_lock_digest, "brand_lock_digest"),
            (self.reality_digest, "reality_digest"),
            (self.scene_digest, "scene_digest"),
            (self.composition_digest, "composition_digest"),
            (self.prompt_preservation_digest, "prompt_preservation_digest"),
            (self.changed_module, "changed_module"),
            (self.causal_variable, "causal_variable"),
        ):
            _require_text(value, name)
        if self.revision_index < 0:
            raise ValueError("revision_index must be non-negative for a package revision")
        if self.immutable is not True:
            raise ValueError("package revision summary must be immutable")
        if self.human_qualification != "PENDING_HUMAN_REVIEW":
            raise ValueError("AI loop output cannot assign human qualification")


@dataclass(frozen=True, slots=True)
class LoopAuthorization:
    """The already-confirmed authorization envelope for this loop."""

    enabled: bool = False
    human_confirmed: bool = False
    max_revisions: int = 1
    max_calls: int = 4
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
        if any(not value.strip() for value in (*allowed, *locked_modules, *locked_variables)):
            raise ValueError("module and variable names must be non-empty strings")
        if any(value not in REVISION_MODULES for value in allowed):
            raise ValueError("allowed_modules must be Scene, Reality, or Composition")
        object.__setattr__(self, "allowed_modules", allowed)
        object.__setattr__(self, "locked_modules", locked_modules)
        object.__setattr__(self, "locked_variables", locked_variables)


@dataclass(frozen=True, slots=True)
class CriticFinding:
    """One causal observation, never a human qualification decision."""

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
    """Structured critic evidence; pixels_verified is a capability assertion only."""

    iteration_index: int
    decision: CriticDecision
    findings: tuple[CriticFinding, ...] = ()
    pixels_verified: bool = True
    human_qualification: Literal["PENDING_HUMAN_REVIEW"] = "PENDING_HUMAN_REVIEW"

    def __post_init__(self) -> None:
        if self.iteration_index < 0:
            raise ValueError("iteration_index must be non-negative")
        if self.decision not in {"NEEDS_REVISION", "NO_ACTION", "UNVERIFIED"}:
            raise ValueError("critic decision is not an allowed AI conclusion")
        findings = tuple(self.findings)
        if self.decision == "NEEDS_REVISION" and not findings:
            raise ValueError("NEEDS_REVISION requires at least one finding")
        if self.decision == "NO_ACTION" and findings:
            raise ValueError("NO_ACTION cannot contain revision findings")
        if self.human_qualification != "PENDING_HUMAN_REVIEW":
            raise ValueError("AI critic cannot assign human qualification")
        object.__setattr__(self, "findings", findings)


@dataclass(frozen=True, slots=True)
class GateSnapshot:
    """Immutable caller-owned state used to make one gate decision."""

    loop_id: str
    now: datetime
    authorization: LoopAuthorization
    product_lock: ProductBrandLock | None = None
    direction: DirectionEvidence | None = None
    reality: RealityEvidence | None = None
    scene: LayerEvidence | None = None
    composition: LayerEvidence | None = None
    prompt: PromptPreservationEvidence | None = None
    current_package: PackageRevisionSummary | None = None
    current_prompt: PromptRevisionSummary | None = None
    trace: tuple[Stage, ...] = ()
    calls_used: int = 0
    total_cost_micros: int = 0
    planned_call_cost_micros: int = 0
    revision_index: int = 0
    stopped: bool = False
    last_call_status: CallStatus | None = None
    critic: CriticReport | None = None
    critic_history: tuple[CriticReport, ...] = ()
    revision_history: tuple[PackageRevisionSummary, ...] = ()

    def __post_init__(self) -> None:
        _require_text(self.loop_id, "loop_id")
        _require_aware(self.now, "now")
        for value, name in (
            (self.calls_used, "calls_used"),
            (self.total_cost_micros, "total_cost_micros"),
            (self.planned_call_cost_micros, "planned_call_cost_micros"),
            (self.revision_index, "revision_index"),
        ):
            if not isinstance(value, int) or value < 0:
                raise ValueError(f"{name} must be non-negative")
        if self.last_call_status not in {None, "SUCCEEDED", "UNKNOWN", "WRITE_UNCERTAIN"}:
            raise ValueError("unsupported call status")
        trace = tuple(self.trace)
        if any(stage not in PIPELINE for stage in trace):
            raise ValueError("trace contains an unknown stage")
        object.__setattr__(self, "trace", trace)
        object.__setattr__(self, "critic_history", tuple(self.critic_history))
        object.__setattr__(self, "revision_history", tuple(self.revision_history))


@dataclass(frozen=True, slots=True)
class StopReason:
    code: StopCode
    detail: str
    recoverable: bool = False

    def __post_init__(self) -> None:
        _require_text(self.detail, "detail")


@dataclass(frozen=True, slots=True)
class AuditSummary:
    loop_id: str
    trace: tuple[Stage, ...]
    calls_used: int
    total_cost_micros: int
    revision_index: int
    product_lock_digest: str | None
    brand_lock_digest: str | None
    package_revision_ids: tuple[str, ...]
    prompt_revision_ids: tuple[str, ...]
    ai_qualification: Literal["UNVERIFIED"] = "UNVERIFIED"
    provider_called: Literal[False] = False
    production_write: Literal[False] = False


@dataclass(frozen=True, slots=True)
class GateDecision:
    """The only output: one action, optional revision summary, and audit facts."""

    loop_id: str
    iteration_index: int
    action: DecisionAction
    stage: Stage | None
    changed_module: str | None
    causal_variable: str | None
    expected_call_count: int
    expected_cost_micros: int
    stop_reason: StopReason | None
    human_review_required: bool
    new_prompt_revision: PromptRevisionSummary | None
    new_package_revision: PackageRevisionSummary | None
    audit: AuditSummary

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
        if self.action == "WAIT_RECONCILIATION" and self.stop_reason is None:
            raise ValueError("WAIT_RECONCILIATION requires a reason")
        if self.action == "PROPOSE_REVISION":
            if not self.changed_module or not self.causal_variable:
                raise ValueError("revision requires one module and causal variable")
            if self.new_prompt_revision is None or self.new_package_revision is None:
                raise ValueError("revision requires new immutable summaries")
        elif self.new_prompt_revision is not None or self.new_package_revision is not None:
            raise ValueError("only revision decisions carry new summaries")


def _audit(
    snapshot: GateSnapshot, *, package: PackageRevisionSummary | None = None
) -> AuditSummary:
    packages = [item.package_revision_id for item in snapshot.revision_history]
    prompts = [item.prompt_revision_id for item in snapshot.revision_history]
    if snapshot.current_package is not None:
        packages.insert(0, snapshot.current_package.package_revision_id)
    if snapshot.current_prompt is not None:
        prompts.insert(0, snapshot.current_prompt.prompt_revision_id)
    if package is not None:
        packages.append(package.package_revision_id)
        prompts.append(package.prompt_revision_id)
    return AuditSummary(
        loop_id=snapshot.loop_id,
        trace=snapshot.trace,
        calls_used=snapshot.calls_used,
        total_cost_micros=snapshot.total_cost_micros,
        revision_index=snapshot.revision_index,
        product_lock_digest=(
            snapshot.product_lock.product_lock_digest if snapshot.product_lock else None
        ),
        brand_lock_digest=(
            snapshot.product_lock.brand_lock_digest if snapshot.product_lock else None
        ),
        package_revision_ids=tuple(dict.fromkeys(packages)),
        prompt_revision_ids=tuple(dict.fromkeys(prompts)),
    )


def _stop(
    snapshot: GateSnapshot,
    code: StopCode,
    detail: str,
    *,
    recoverable: bool = False,
    human_review_required: bool = False,
) -> GateDecision:
    return GateDecision(
        loop_id=snapshot.loop_id,
        iteration_index=snapshot.revision_index,
        action="STOP",
        stage=None,
        changed_module=None,
        causal_variable=None,
        expected_call_count=0,
        expected_cost_micros=0,
        stop_reason=StopReason(code, detail, recoverable),
        human_review_required=human_review_required,
        new_prompt_revision=None,
        new_package_revision=None,
        audit=_audit(snapshot),
    )


def _wait_reconciliation(snapshot: GateSnapshot) -> GateDecision:
    status = snapshot.last_call_status
    return GateDecision(
        loop_id=snapshot.loop_id,
        iteration_index=snapshot.revision_index,
        action="WAIT_RECONCILIATION",
        stage=None,
        changed_module=None,
        causal_variable=None,
        expected_call_count=0,
        expected_cost_micros=0,
        stop_reason=StopReason(
            "EXECUTION_UNKNOWN",
            (
                f"last execution status is {status}; reconcile before any retry "
                "or alternative generation"
            ),
            True,
        ),
        human_review_required=True,
        new_prompt_revision=None,
        new_package_revision=None,
        audit=_audit(snapshot),
    )


def _validate_trace(trace: tuple[Stage, ...]) -> None:
    base = PIPELINE[:5]
    prefix_length = min(len(trace), len(base))
    if trace[:prefix_length] != base[:prefix_length]:
        raise ValueError("trace must start with Product through Authorization in order")
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


def _preflight(snapshot: GateSnapshot) -> GateDecision | None:
    if snapshot.stopped:
        return _stop(snapshot, "USER_STOPPED", "user stopped the loop")
    if not snapshot.authorization.enabled:
        return _stop(snapshot, "LOOP_DISABLED", "truthfulness loop authorization is disabled")
    if not snapshot.authorization.human_confirmed:
        return _stop(
            snapshot,
            "HUMAN_AUTHORIZATION_REQUIRED",
            "explicit human authorization is required before the loop can run",
            recoverable=True,
            human_review_required=True,
        )
    expires_at = snapshot.authorization.expires_at
    if expires_at is None:
        return _stop(
            snapshot,
            "HUMAN_AUTHORIZATION_REQUIRED",
            "enabled loop authorization must include an expiry",
            recoverable=True,
            human_review_required=True,
        )
    if snapshot.now >= expires_at:
        return _stop(snapshot, "AUTH_EXPIRED", "loop authorization has expired")
    if snapshot.last_call_status in {"UNKNOWN", "WRITE_UNCERTAIN"}:
        return _wait_reconciliation(snapshot)
    return None


def _stage_dependency(snapshot: GateSnapshot, stage: Stage) -> GateDecision | None:
    if stage in {"Product", "Direction", "DNA_REALITY", "TEXT_PACKAGE", "AUTHORIZATION"}:
        if snapshot.product_lock is None:
            return _stop(
                snapshot,
                "DEPENDENCY_BLOCKED",
                "canonical Product and brand lock evidence is required before this stage",
                recoverable=True,
            )
    if stage in {"Direction", "DNA_REALITY", "TEXT_PACKAGE", "AUTHORIZATION"}:
        if snapshot.direction is None or not snapshot.direction.selected_by_human:
            return _stop(
                snapshot,
                "DEPENDENCY_BLOCKED",
                "a human-selected direction is required before downstream stages",
                recoverable=True,
                human_review_required=True,
            )
    if stage in {"DNA_REALITY", "TEXT_PACKAGE", "AUTHORIZATION"} and snapshot.reality is None:
        return _stop(
            snapshot,
            "DEPENDENCY_BLOCKED",
            "six-dimension Reality evidence is required before this stage",
            recoverable=True,
        )
    if stage in {"TEXT_PACKAGE", "AUTHORIZATION"} and (
        snapshot.scene is None or snapshot.composition is None
    ):
        return _stop(
            snapshot,
            "DEPENDENCY_BLOCKED",
            "Scene and Composition layer evidence is required before the text package",
            recoverable=True,
        )
    if stage == "AUTHORIZATION" and (
        snapshot.current_package is None or snapshot.current_prompt is None
    ):
        return _stop(
            snapshot,
            "DEPENDENCY_BLOCKED",
            "an immutable package and Prompt revision summary are required before authorization",
            recoverable=True,
        )
    if stage in {"E1", "CRITIC"}:
        if snapshot.current_package is None or snapshot.current_prompt is None:
            return _stop(
                snapshot,
                "DEPENDENCY_BLOCKED",
                "E1 and Critic require an immutable package and Prompt revision summary",
                recoverable=True,
            )
        if snapshot.prompt is None or not snapshot.prompt.verified or snapshot.prompt.drift_fields:
            return _stop(
                snapshot,
                "PROMPT_PRESERVATION_FAILED",
                "Prompt Preservation evidence is missing, unverified, or reports drift",
                recoverable=True,
            )
        if snapshot.product_lock is None:
            return _stop(
                snapshot,
                "DEPENDENCY_BLOCKED",
                "current Product and brand locks are required for Prompt Preservation",
                recoverable=True,
            )
        if (
            snapshot.prompt.product_lock_digest != snapshot.product_lock.product_lock_digest
            or snapshot.prompt.brand_lock_digest != snapshot.product_lock.brand_lock_digest
            or snapshot.current_package.product_lock_digest
            != snapshot.product_lock.product_lock_digest
            or snapshot.current_package.brand_lock_digest
            != snapshot.product_lock.brand_lock_digest
        ):
            return _stop(
                snapshot,
                "PROMPT_PRESERVATION_FAILED",
                "Prompt or package revision is bound to a different Product or brand lock",
                recoverable=True,
            )
    return None


def _budget_gate(snapshot: GateSnapshot, stage: Stage) -> GateDecision | None:
    if stage not in CALL_STAGES:
        return None
    authorization = snapshot.authorization
    if snapshot.calls_used >= authorization.max_calls:
        return _stop(snapshot, "CALL_LIMIT", "authorized model call limit is exhausted")
    projected = snapshot.total_cost_micros + snapshot.planned_call_cost_micros
    if projected > authorization.max_total_cost_micros:
        return _stop(snapshot, "BUDGET_EXHAUSTED", "authorized total cost would be exceeded")
    return None


def _stage_decision(snapshot: GateSnapshot, stage: Stage) -> GateDecision:
    dependency = _stage_dependency(snapshot, stage)
    if dependency is not None:
        return dependency
    budget = _budget_gate(snapshot, stage)
    if budget is not None:
        return budget
    is_call = stage in CALL_STAGES
    action: DecisionAction = {
        "E1": "CALL_E1",
        "CRITIC": "CALL_CRITIC",
    }.get(stage, "RUN_STAGE")
    return GateDecision(
        loop_id=snapshot.loop_id,
        iteration_index=snapshot.revision_index,
        action=action,
        stage=stage,
        changed_module=None,
        causal_variable=None,
        expected_call_count=int(is_call),
        expected_cost_micros=snapshot.planned_call_cost_micros if is_call else 0,
        stop_reason=None,
        human_review_required=False,
        new_prompt_revision=None,
        new_package_revision=None,
        audit=_audit(snapshot),
    )


def _revision_target(
    snapshot: GateSnapshot, report: CriticReport
) -> tuple[CriticFinding | None, StopCode | None]:
    locked_or_product = any(
        finding.locked
        or finding.module in {"Product", "Brand"}
        or finding.module in snapshot.authorization.locked_modules
        or finding.causal_variable in snapshot.authorization.locked_variables
        for finding in report.findings
    )
    eligible = tuple(
        finding
        for finding in report.findings
        if (
            finding.module in REVISION_MODULES
            and finding.module in snapshot.authorization.allowed_modules
            and not finding.locked
            and finding.module not in snapshot.authorization.locked_modules
            and finding.causal_variable not in snapshot.authorization.locked_variables
        )
    )
    if not eligible:
        if locked_or_product:
            return None, "LOCK_CONFLICT"
        if any(
            finding.module not in snapshot.authorization.allowed_modules
            for finding in report.findings
        ):
            return None, "MODULE_NOT_AUTHORIZED"
        return None, "DEPENDENCY_BLOCKED"
    return max(
        enumerate(eligible),
        key=lambda item: (item[1].severity, -item[0]),
    )[1], None


def _has_two_non_improvements(
    report: CriticReport, history: tuple[CriticReport, ...], target: CriticFinding
) -> bool:
    reports = (*history, report)
    matching = [
        finding
        for prior in reports
        for finding in prior.findings
        if finding.module == target.module
        and finding.causal_variable == target.causal_variable
    ]
    return len(matching) >= 2 and all(item.progress != "IMPROVED" for item in matching[-2:])


def _new_revision(
    snapshot: GateSnapshot, target: CriticFinding
) -> tuple[PromptRevisionSummary, PackageRevisionSummary]:
    if (
        snapshot.product_lock is None
        or snapshot.reality is None
        or snapshot.scene is None
        or snapshot.composition is None
        or snapshot.prompt is None
        or snapshot.current_package is None
        or snapshot.current_prompt is None
    ):
        raise ValueError("revision evidence is incomplete")
    revision_index = snapshot.revision_index + 1
    basis = {
        "loop_id": snapshot.loop_id,
        "revision_index": revision_index,
        "parent_package_revision_id": snapshot.current_package.package_revision_id,
        "parent_prompt_revision_id": snapshot.current_prompt.prompt_revision_id,
        "module": target.module,
        "causal_variable": target.causal_variable,
        "evidence": target.evidence,
        "product_lock": snapshot.product_lock.product_lock_digest,
        "brand_lock": snapshot.product_lock.brand_lock_digest,
        "reality": snapshot.reality.evidence_digest,
        "scene": snapshot.scene.evidence_digest,
        "composition": snapshot.composition.evidence_digest,
        "preservation": snapshot.prompt.evidence_digest,
    }
    suffix = _digest(basis)[:16]
    prompt = PromptRevisionSummary(
        prompt_revision_id=f"{snapshot.loop_id}:prompt:r{revision_index}:{suffix}",
        revision_index=revision_index,
        parent_prompt_revision_id=snapshot.current_prompt.prompt_revision_id,
        content_hash=_digest({**basis, "kind": "prompt"}),
        preservation_hash=snapshot.prompt.evidence_digest,
    )
    package = PackageRevisionSummary(
        package_revision_id=f"{snapshot.loop_id}:package:r{revision_index}:{suffix}",
        prompt_revision_id=prompt.prompt_revision_id,
        revision_index=revision_index,
        parent_package_revision_id=snapshot.current_package.package_revision_id,
        parent_prompt_revision_id=snapshot.current_prompt.prompt_revision_id,
        product_lock_digest=snapshot.product_lock.product_lock_digest,
        brand_lock_digest=snapshot.product_lock.brand_lock_digest,
        reality_digest=snapshot.reality.evidence_digest,
        scene_digest=snapshot.scene.evidence_digest,
        composition_digest=snapshot.composition.evidence_digest,
        prompt_preservation_digest=snapshot.prompt.evidence_digest,
        changed_module=target.module,
        causal_variable=target.causal_variable,
    )
    return prompt, package


def _after_critic(snapshot: GateSnapshot) -> GateDecision:
    report = snapshot.critic
    if report is None:
        return _stop(
            snapshot,
            "DEPENDENCY_BLOCKED",
            "Critic must produce structured evidence before a revision decision",
            recoverable=True,
        )
    if not report.pixels_verified or report.decision == "UNVERIFIED":
        return _stop(
            snapshot,
            "UNVERIFIED_PIXELS",
            "pixel evidence is unavailable or the Critic cannot verify the output",
            recoverable=True,
            human_review_required=True,
        )
    if report.decision == "NO_ACTION":
        return _stop(
            snapshot,
            "QUALITY_TARGET_MET",
            "Critic found no actionable issue; human review is still required",
            human_review_required=True,
        )
    target, blocked_code = _revision_target(snapshot, report)
    if target is None:
        return _stop(
            snapshot,
            blocked_code or "DEPENDENCY_BLOCKED",
            "no critic finding is both unlocked and inside the authorized module set",
            recoverable=True,
            human_review_required=blocked_code == "LOCK_CONFLICT",
        )
    if _has_two_non_improvements(report, snapshot.critic_history, target):
        return _stop(
            snapshot,
            "NO_PROGRESS",
            f"causal variable {target.causal_variable!r} did not improve in two reviews",
            recoverable=True,
            human_review_required=True,
        )
    if snapshot.revision_index >= snapshot.authorization.max_revisions:
        return _stop(snapshot, "LIMIT_REACHED", "authorized revision limit is exhausted")
    try:
        new_prompt, new_package = _new_revision(snapshot, target)
    except ValueError as exc:
        return _stop(snapshot, "PROMPT_PRESERVATION_FAILED", str(exc), recoverable=True)
    return GateDecision(
        loop_id=snapshot.loop_id,
        iteration_index=snapshot.revision_index + 1,
        action="PROPOSE_REVISION",
        stage="TARGETED_REVISION",
        changed_module=target.module,
        causal_variable=target.causal_variable,
        expected_call_count=0,
        expected_cost_micros=0,
        stop_reason=None,
        human_review_required=False,
        new_prompt_revision=new_prompt,
        new_package_revision=new_package,
        audit=_audit(snapshot, package=new_package),
    )


def decide(snapshot: GateSnapshot) -> GateDecision:
    """Return exactly one bounded next-step decision without performing it."""

    _validate_trace(snapshot.trace)
    preflight = _preflight(snapshot)
    if preflight is not None:
        return preflight
    stage = _next_stage(snapshot.trace)
    if stage is not None:
        return _stage_decision(snapshot, stage)
    return _after_critic(snapshot)
