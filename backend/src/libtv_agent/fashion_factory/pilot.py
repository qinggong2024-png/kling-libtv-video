from __future__ import annotations

from collections import Counter
from dataclasses import dataclass

from .contracts import PilotRun


@dataclass(frozen=True)
class PilotMetrics:
    technical_qualified_yield: float
    editorial_qualified_yield: float
    cost_per_editorial_qualified_second: float | None
    cost_per_qualified_final_video: float | None
    regeneration_rate: float
    zero_touch_rate: float
    final_ground_truth_pass_rate: float
    product_fidelity_pass_rate: float
    qa_false_negative_rate: float
    qa_false_positive_rate: float
    system_ground_truth_pass_gap: float
    failure_pareto: tuple[tuple[str, int], ...]


def calculate_pilot_metrics(runs: list[PilotRun]) -> PilotMetrics:
    if not runs:
        raise ValueError("at least one pilot run is required")
    total_generated = sum(run.generated_seconds for run in runs)
    technical = sum(run.technical_qualified_seconds for run in runs)
    editorial = sum(run.editorial_qualified_seconds for run in runs)
    cost = sum(run.actual_api_cost for run in runs)
    gt_pass = sum(run.ground_truth_pass for run in runs)
    system_pass = sum(run.system_pass for run in runs)
    false_negative = sum(run.system_pass and not run.ground_truth_pass for run in runs)
    false_positive = sum(not run.system_pass and run.ground_truth_pass for run in runs)
    actual_fail = sum(not run.ground_truth_pass for run in runs)
    actual_pass = gt_pass
    failures = Counter(code for run in runs for code in run.failure_codes)
    return PilotMetrics(
        technical_qualified_yield=technical / total_generated,
        editorial_qualified_yield=editorial / total_generated,
        cost_per_editorial_qualified_second=cost / editorial if editorial else None,
        cost_per_qualified_final_video=cost / gt_pass if gt_pass else None,
        regeneration_rate=sum(run.video_attempts > 1 for run in runs) / len(runs),
        zero_touch_rate=sum(not run.human_intervention for run in runs) / len(runs),
        final_ground_truth_pass_rate=gt_pass / len(runs),
        product_fidelity_pass_rate=sum(run.product_fidelity_pass for run in runs) / len(runs),
        qa_false_negative_rate=false_negative / actual_fail if actual_fail else 0,
        qa_false_positive_rate=false_positive / actual_pass if actual_pass else 0,
        system_ground_truth_pass_gap=system_pass / len(runs) - gt_pass / len(runs),
        failure_pareto=tuple(failures.most_common()),
    )

