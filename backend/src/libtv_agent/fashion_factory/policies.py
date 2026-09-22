from __future__ import annotations

from dataclasses import dataclass

from .contracts import (
    DecisionAction,
    ErrorDecision,
    PropagationRisk,
    Severity,
    TemporalError,
)

HARD_REJECT_CODES = frozenset(
    {
        "PRODUCT_IDENTITY_DRIFT",
        "GRAPHIC_LOGO_DRIFT",
        "GARMENT_TOPOLOGY_CHANGE",
        "MAJOR_COLOR_DRIFT",
        "CHARACTER_IDENTITY_DRIFT",
        "SCENE_GEOMETRY_BREAK",
        "PERSISTENT_BODY_TOPOLOGY_ERROR",
        "PERSISTENT_PRODUCT_OCCLUSION",
        "UNKNOWN_PRODUCT_FACT_HALLUCINATION",
    }
)
SALVAGEABLE_CODES = frozenset(
    {
        "TRANSIENT_HAND_ARTIFACT",
        "TRANSIENT_FACE_ARTIFACT",
        "SHORT_MOTION_STUTTER",
        "SHORT_OCCLUSION",
        "SHORT_FRAME_GLITCH",
        "LOCAL_BODY_ARTIFACT",
    }
)

RETRY_STRATEGIES = {
    "PRODUCT_IDENTITY_DRIFT": "lower_motion_and_strengthen_product_reference",
    "GRAPHIC_LOGO_DRIFT": "lower_motion_and_upgrade_reference_route",
    "GARMENT_TOPOLOGY_CHANGE": "upgrade_to_vton_or_stronger_reference",
    "MAJOR_COLOR_DRIFT": "strengthen_color_reference_and_change_provider_if_needed",
    "CHARACTER_IDENTITY_DRIFT": "lock_character_reference_and_reduce_motion",
    "SCENE_GEOMETRY_BREAK": "simplify_scene_instantiation",
    "PERSISTENT_BODY_TOPOLOGY_ERROR": "use_safe_pose_and_regenerate_storyboard",
    "PERSISTENT_PRODUCT_OCCLUSION": "reduce_occlusion_and_motion",
    "UNKNOWN_PRODUCT_FACT_HALLUCINATION": "restrict_prompt_to_product_truth_snapshot",
}


@dataclass(frozen=True)
class RetryBudget:
    retry_count: int = 0
    max_retry_per_asset: int = 2
    total_attempts: int = 1
    max_total_attempts: int = 3
    cumulative_cost: float = 0
    expected_route_cost: float = 1
    max_cost_multiplier: float = 2

    @property
    def exhausted(self) -> bool:
        return (
            self.retry_count >= self.max_retry_per_asset
            or self.total_attempts >= self.max_total_attempts
            or self.cumulative_cost >= self.expected_route_cost * self.max_cost_multiplier
        )


def decide_temporal_error(error: TemporalError, budget: RetryBudget) -> ErrorDecision:
    common = dict(
        reason_code=error.reason_code,
        severity=error.severity,
        confidence=error.confidence,
        target="source_clip",
        retry_count=budget.retry_count,
        retry_budget=budget.max_retry_per_asset,
        propagation_risk=error.propagation_risk,
        start_ms=error.start_ms,
        end_ms=error.end_ms,
    )
    if error.reason_code in HARD_REJECT_CODES or error.propagation_risk == PropagationRisk.HIGH:
        if budget.exhausted:
            return ErrorDecision(
                **common,
                action=DecisionAction.REGENERATE,
                retry_strategy="escalate_to_human_review_or_terminal_failure",
                salvageable=False,
            )
        return ErrorDecision(
            **common,
            action=DecisionAction.REGENERATE,
            retry_strategy=RETRY_STRATEGIES.get(error.reason_code, "targeted_regeneration"),
            salvageable=False,
        )
    if error.reason_code in SALVAGEABLE_CODES:
        margin = 250 if error.propagation_risk == PropagationRisk.LOW else 500
        return ErrorDecision(
            **common,
            action=DecisionAction.CUT,
            safe_cut_before_ms=max(0, error.start_ms - margin),
            safe_cut_after_ms=error.end_ms + margin,
            salvageable=True,
        )
    return ErrorDecision(
        **common,
        action=DecisionAction.REGENERATE,
        retry_strategy="classify_unknown_error_before_retry",
        salvageable=False,
    )


def decision_for_clean_clip(duration_ms: int) -> ErrorDecision:
    return ErrorDecision(
        action=DecisionAction.KEEP,
        reason_code="NO_TEMPORAL_ERROR",
        severity=Severity.LOW,
        confidence=1,
        target="source_clip",
        propagation_risk=PropagationRisk.LOW,
        start_ms=0,
        end_ms=duration_ms,
        salvageable=False,
    )

