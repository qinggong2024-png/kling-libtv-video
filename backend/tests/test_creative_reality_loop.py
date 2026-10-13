from __future__ import annotations

import random
from dataclasses import FrozenInstanceError, replace
from datetime import UTC, datetime, timedelta

import pytest
from libtv_agent.creative.reality_loop import (
    PIPELINE,
    REALITY_ORDER,
    CriticFinding,
    CriticReport,
    LoopAuthorization,
    LoopSnapshot,
    decide,
)

NOW = datetime(2026, 10, 11, 12, tzinfo=UTC)


def authorization(**overrides):
    values = {
        "enabled": True,
        "max_revisions": 2,
        "max_calls": 8,
        "max_total_cost_micros": 80,
        "expires_at": NOW + timedelta(hours=1),
        "allowed_modules": ("Reality", "Scene", "Composition"),
    }
    values.update(overrides)
    return LoopAuthorization(**values)


def snapshot(**overrides):
    values = {
        "loop_id": "loop-1",
        "now": NOW,
        "authorization": authorization(),
        "planned_call_cost_micros": 10,
    }
    values.update(overrides)
    return LoopSnapshot(**values)


def finding(
    variable="exposure", module="Reality", severity=2, progress="UNKNOWN", **kwargs,
):
    return CriticFinding(
        module=module,
        causal_variable=variable,
        severity=severity,
        evidence="bounded region evidence",
        progress=progress,
        **kwargs,
    )


def report(*findings, decision="NEEDS_REVISION", pixels_verified=True, iteration_index=0):
    return CriticReport(
        iteration_index=iteration_index,
        decision=decision,
        findings=findings,
        pixels_verified=pixels_verified,
    )


def test_default_closed_loop_stops_without_a_call():
    result = decide(
        snapshot(authorization=LoopAuthorization(max_total_cost_micros=0)),
    )
    assert result.action == "STOP"
    assert result.stop_reason.code == "LOOP_DISABLED"
    assert result.expected_call_count == 0


def test_fixed_order_and_reality_dimension_order_are_explicit():
    trace = ()
    observed = []
    for _ in range(5):
        result = decide(snapshot(trace=trace))
        observed.append(result.stage)
        trace = (*trace, result.stage)
    assert observed == list(PIPELINE[:5])
    assert REALITY_ORDER == (
        "Camera", "Lighting", "Composition", "Human Behavior",
        "Environment", "Imperfection",
    )
    assert decide(snapshot(trace=trace)).action == "CALL_E1"
    trace = (*trace, "E1")
    assert decide(snapshot(trace=trace)).action == "CALL_CRITIC"


@pytest.mark.parametrize("trace", [
    ("Direction",),
    ("Product", "DNA_REALITY"),
    PIPELINE[:5] + ("CRITIC",),
    PIPELINE[:5] + ("E1", "TARGETED_REVISION"),
])
def test_invalid_or_skipped_stage_trace_is_rejected(trace):
    with pytest.raises(ValueError):
        decide(snapshot(trace=trace))


@pytest.mark.parametrize(
    "authorization_kwargs,code",
    [
        ({"max_revisions": -1}, "max_revisions"),
        ({"max_revisions": 3}, "max_revisions"),
        ({"max_calls": 0}, "max_calls"),
        ({"max_total_cost_micros": -1}, "max_total_cost_micros"),
        ({"enabled": True, "expires_at": None}, "expires_at"),
    ],
)
def test_authorization_bounds_are_closed(authorization_kwargs, code):
    with pytest.raises(ValueError, match=code):
        authorization(**authorization_kwargs)


@pytest.mark.parametrize("status", ["UNKNOWN", "WRITE_UNCERTAIN"])
def test_uncertain_execution_waits_for_reconciliation_without_retry(status):
    result = decide(snapshot(last_call_status=status))
    assert result.action == "WAIT_RECONCILIATION"
    assert result.stop_reason.code == "EXECUTION_UNKNOWN"
    assert result.stop_reason.recoverable


def test_stop_expiry_and_budget_precede_a_new_call():
    base_trace = PIPELINE[:5]
    stopped = decide(snapshot(trace=base_trace, stopped=True))
    assert stopped.stop_reason.code == "USER_STOPPED"
    expired = decide(snapshot(
        trace=base_trace,
        now=NOW + timedelta(hours=2),
    ))
    assert expired.stop_reason.code == "AUTH_EXPIRED"
    call_limited = decide(snapshot(
        trace=base_trace,
        calls_used=8,
    ))
    assert call_limited.stop_reason.code == "CALL_LIMIT"
    budget_limited = decide(snapshot(
        trace=base_trace,
        total_cost_micros=75,
        planned_call_cost_micros=10,
    ))
    assert budget_limited.stop_reason.code == "BUDGET_EXHAUSTED"


def test_critic_never_returns_a_human_qualification_and_no_action_routes_to_review():
    with pytest.raises(ValueError, match="critic decision"):
        CriticReport(iteration_index=0, decision="QUALIFIED")
    trace = PIPELINE[:5] + ("E1", "CRITIC")
    result = decide(snapshot(trace=trace, critic=report(decision="NO_ACTION")))
    assert result.stop_reason.code == "QUALITY_TARGET_MET"
    assert result.human_review_required


def test_unverified_pixels_and_missing_critic_stop_safely():
    trace = PIPELINE[:5] + ("E1", "CRITIC")
    missing = decide(snapshot(trace=trace))
    assert missing.stop_reason.code == "DEPENDENCY_BLOCKED"
    unverified = decide(snapshot(
        trace=trace,
        critic=report(decision="UNVERIFIED"),
    ))
    assert unverified.stop_reason.code == "UNVERIFIED_PIXELS"
    pixels = decide(snapshot(
        trace=trace,
        critic=report(finding(), pixels_verified=False),
    ))
    assert pixels.stop_reason.code == "UNVERIFIED_PIXELS"


def test_one_most_important_allowed_unlocked_variable_is_selected():
    trace = PIPELINE[:5] + ("E1", "CRITIC")
    result = decide(snapshot(
        trace=trace,
        critic=report(
            finding("locked-high", severity=3, locked=True),
            finding("not-allowed", module="Scene", severity=3),
            finding("focus", module="Reality", severity=2),
            finding("composition", module="Composition", severity=2),
        ),
        authorization=authorization(allowed_modules=("Reality",)),
    ))
    assert result.action == "PROPOSE_REVISION"
    assert result.changed_module == "Reality"
    assert result.causal_variable == "focus"
    assert result.iteration_index == 1


def test_locked_or_disallowed_findings_stop_with_lock_conflict():
    trace = PIPELINE[:5] + ("E1", "CRITIC")
    result = decide(snapshot(
        trace=trace,
        critic=report(finding("locked", locked=True)),
    ))
    assert result.stop_reason.code == "LOCK_CONFLICT"


def test_two_non_improvements_stop_but_an_improvement_can_continue():
    trace = PIPELINE[:5] + ("E1", "CRITIC")
    prior = report(finding("exposure", progress="UNCHANGED"), iteration_index=0)
    current = report(finding("exposure", progress="UNCHANGED"), iteration_index=1)
    no_progress = decide(snapshot(
        trace=trace,
        revision_index=1,
        critic=current,
        critic_history=(prior,),
    ))
    assert no_progress.stop_reason.code == "NO_PROGRESS"
    improved = decide(snapshot(
        trace=trace,
        revision_index=1,
        critic=report(finding("exposure", progress="IMPROVED"), iteration_index=1),
        critic_history=(prior,),
    ))
    assert improved.action == "PROPOSE_REVISION"


def test_revision_limit_is_checked_after_critic_before_proposing():
    trace = PIPELINE[:5] + ("E1", "CRITIC")
    result = decide(snapshot(
        trace=trace,
        revision_index=2,
        critic=report(finding()),
        authorization=authorization(max_revisions=2),
    ))
    assert result.stop_reason.code == "LIMIT_REACHED"


def test_revision_trace_repeats_only_after_the_single_targeted_decision():
    trace = PIPELINE[:5] + ("E1", "CRITIC", "TARGETED_REVISION")
    result = decide(snapshot(trace=trace))
    assert result.action == "CALL_E1"
    assert result.stage == "E1"


def test_inputs_and_decisions_are_immutable_and_history_is_detached():
    findings = [finding()]
    critic = report(*findings)
    trace = list(PIPELINE[:5]) + ["E1", "CRITIC"]
    state = snapshot(trace=trace, critic=critic)
    result = decide(state)
    findings.append(finding("another"))
    trace.append("TARGETED_REVISION")
    assert len(state.critic.findings) == 1
    assert len(state.trace) == 7
    with pytest.raises(FrozenInstanceError):
        result.action = "STOP"
    assert result.changed_module == "Reality"


def test_property_style_random_finding_orders_always_choose_one_deterministic_target():
    rng = random.Random(20261011)
    trace = PIPELINE[:5] + ("E1", "CRITIC")
    original = [
        finding("camera", module="Reality", severity=2),
        finding("pose", module="Scene", severity=3),
        finding("focus", module="Reality", severity=3),
        finding("cloth", module="Composition", severity=1),
    ]
    chosen = set()
    for _ in range(40):
        shuffled = original[:]
        rng.shuffle(shuffled)
        result = decide(snapshot(
            trace=trace,
            critic=report(*shuffled),
        ))
        assert result.action == "PROPOSE_REVISION"
        assert result.causal_variable in {"pose", "focus"}
        assert result.changed_module in {"Scene", "Reality"}
        chosen.add((result.changed_module, result.causal_variable))
    assert chosen == {("Scene", "pose"), ("Reality", "focus")}


def test_revision_decision_has_no_second_variable_payload():
    trace = PIPELINE[:5] + ("E1", "CRITIC")
    result = decide(snapshot(trace=trace, critic=report(finding())))
    assert result.changed_module == "Reality"
    assert result.causal_variable == "exposure"
    assert not hasattr(result, "changed_modules")
    assert replace(result).causal_variable == "exposure"


def test_call_cost_is_only_proposed_for_call_stages():
    product = decide(snapshot())
    assert product.expected_call_count == 0
    assert product.expected_cost_micros == 0
    e1 = decide(snapshot(trace=PIPELINE[:5]))
    assert e1.expected_call_count == 1
    assert e1.expected_cost_micros == 10
