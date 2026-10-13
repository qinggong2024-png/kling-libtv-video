from __future__ import annotations

from dataclasses import FrozenInstanceError
from datetime import UTC, datetime, timedelta

import pytest
from libtv_agent.services.creative_reality_loop_gate import (
    PIPELINE,
    REALITY_ORDER,
    CriticFinding,
    CriticReport,
    DirectionEvidence,
    GateSnapshot,
    LayerEvidence,
    LoopAuthorization,
    PackageRevisionSummary,
    ProductBrandLock,
    PromptPreservationEvidence,
    PromptRevisionSummary,
    RealityDimensionEvidence,
    RealityEvidence,
    decide,
)

NOW = datetime(2026, 10, 12, 12, tzinfo=UTC)


def product_lock() -> ProductBrandLock:
    return ProductBrandLock(
        product_id="product-1",
        product_revision="product-r1",
        product_source_hash="front-sha",
        brand_id="brand-1",
        brand_revision="brand-r3",
        brand_source="USER_SELECTED",
    )


def reality() -> RealityEvidence:
    return RealityEvidence(
        tuple(
            RealityDimensionEvidence(
                dimension=dimension,
                decision=f"fixed {dimension}",
                evidence_status="USER_LOCKED" if dimension == "Composition" else "PROPOSED",
                evidence=f"evidence for {dimension}",
            )
            for dimension in REALITY_ORDER
        )
    )


def prompt() -> PromptPreservationEvidence:
    lock = product_lock()
    return PromptPreservationEvidence(
        prompt_revision_id="prompt-r0",
        prompt_hash="prompt-hash-r0",
        product_lock_digest=lock.product_lock_digest,
        brand_lock_digest=lock.brand_lock_digest,
    )


def package() -> PackageRevisionSummary:
    lock = product_lock()
    return PackageRevisionSummary(
        package_revision_id="package-r0",
        prompt_revision_id="prompt-r0",
        revision_index=0,
        parent_package_revision_id="package-root",
        parent_prompt_revision_id="prompt-root",
        product_lock_digest=lock.product_lock_digest,
        brand_lock_digest=lock.brand_lock_digest,
        reality_digest=reality().evidence_digest,
        scene_digest="scene-r0",
        composition_digest="composition-r0",
        prompt_preservation_digest=prompt().evidence_digest,
        changed_module="initial",
        causal_variable="initial",
    )


def current_prompt() -> PromptRevisionSummary:
    return PromptRevisionSummary(
        prompt_revision_id="prompt-r0",
        revision_index=0,
        parent_prompt_revision_id="prompt-root",
        content_hash="content-r0",
        preservation_hash=prompt().evidence_digest,
    )


def authorization(**overrides) -> LoopAuthorization:
    values = {
        "enabled": True,
        "human_confirmed": True,
        "max_revisions": 2,
        "max_calls": 8,
        "max_total_cost_micros": 80,
        "expires_at": NOW + timedelta(hours=1),
        "allowed_modules": ("Reality", "Scene", "Composition"),
    }
    values.update(overrides)
    return LoopAuthorization(**values)


def snapshot(**overrides) -> GateSnapshot:
    values = {
        "loop_id": "loop-1",
        "now": NOW,
        "authorization": authorization(),
        "product_lock": product_lock(),
        "direction": DirectionEvidence("direction-A", "direction-r1"),
        "reality": reality(),
        "scene": LayerEvidence("Scene", "scene-r1", "scene-sha", "PROPOSED", "studio"),
        "composition": LayerEvidence(
            "Composition", "composition-r1", "composition-sha", "PROPOSED", "medium shot"
        ),
        "prompt": prompt(),
        "current_package": package(),
        "current_prompt": current_prompt(),
        "planned_call_cost_micros": 10,
    }
    values.update(overrides)
    return GateSnapshot(**values)


def finding(variable="exposure", module="Reality", severity=2, progress="UNKNOWN", **kwargs):
    return CriticFinding(
        module=module,
        causal_variable=variable,
        severity=severity,
        evidence="bounded pixel region evidence",
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


def test_default_closed_and_human_authorization_gates_stop_before_any_stage():
    disabled = decide(snapshot(authorization=LoopAuthorization()))
    assert disabled.action == "STOP"
    assert disabled.stop_reason.code == "LOOP_DISABLED"
    assert disabled.expected_call_count == 0

    unauthorised = decide(
        snapshot(authorization=authorization(human_confirmed=False)),
    )
    assert unauthorised.stop_reason.code == "HUMAN_AUTHORIZATION_REQUIRED"


def test_pipeline_and_reality_order_are_fixed():
    trace = ()
    observed = []
    for _ in range(5):
        result = decide(snapshot(trace=trace))
        observed.append(result.stage)
        trace = (*trace, result.stage)
    assert observed == list(PIPELINE[:5])
    assert REALITY_ORDER == (
        "Camera",
        "Lighting",
        "Composition",
        "Human Behavior",
        "Environment",
        "Imperfection",
    )
    assert decide(snapshot(trace=trace)).action == "CALL_E1"


@pytest.mark.parametrize(
    "trace",
    [
        ("Direction",),
        ("Product", "DNA_REALITY"),
        PIPELINE[:5] + ("CRITIC",),
        PIPELINE[:5] + ("E1", "TARGETED_REVISION"),
    ],
)
def test_invalid_trace_cannot_skip_or_reorder_modules(trace):
    with pytest.raises(ValueError):
        decide(snapshot(trace=trace))


@pytest.mark.parametrize(
    "kwargs,code",
    [
        ({"max_revisions": -1}, "max_revisions"),
        ({"max_revisions": 3}, "max_revisions"),
        ({"max_calls": 0}, "max_calls"),
        ({"allowed_modules": ("Product",)}, "allowed_modules"),
        ({"enabled": True, "human_confirmed": True, "expires_at": None}, "expiry"),
    ],
)
def test_authorization_bounds_are_closed(kwargs, code):
    if code == "expiry":
        with pytest.raises(ValueError, match="expiry|expires_at"):
            authorization(**kwargs)
    else:
        with pytest.raises(ValueError, match=code):
            authorization(**kwargs)


@pytest.mark.parametrize("status", ["UNKNOWN", "WRITE_UNCERTAIN"])
def test_uncertain_execution_waits_without_retry_or_alternative_generation(status):
    result = decide(snapshot(last_call_status=status))
    assert result.action == "WAIT_RECONCILIATION"
    assert result.stop_reason.code == "EXECUTION_UNKNOWN"
    assert result.stop_reason.recoverable
    assert "alternative" in result.stop_reason.detail
    assert result.expected_call_count == 0


def test_expiry_call_limit_and_cost_gate_precede_e1():
    base_trace = PIPELINE[:5]
    assert decide(snapshot(trace=base_trace, now=NOW + timedelta(hours=2))).stop_reason.code == (
        "AUTH_EXPIRED"
    )
    assert decide(snapshot(trace=base_trace, calls_used=8)).stop_reason.code == "CALL_LIMIT"
    assert decide(
        snapshot(trace=base_trace, total_cost_micros=75, planned_call_cost_micros=10)
    ).stop_reason.code == "BUDGET_EXHAUSTED"


def test_product_brand_reality_scene_composition_and_preservation_evidence_is_required():
    assert decide(snapshot(product_lock=None)).stop_reason.code == "DEPENDENCY_BLOCKED"
    assert decide(
        snapshot(trace=PIPELINE[:1], direction=DirectionEvidence("direction-A", "r1"))
    ).stage == "Direction"
    assert decide(snapshot(trace=PIPELINE[:2], reality=None)).stop_reason.code == (
        "DEPENDENCY_BLOCKED"
    )
    assert decide(snapshot(trace=PIPELINE[:5], prompt=None)).stop_reason.code == (
        "PROMPT_PRESERVATION_FAILED"
    )
    assert decide(
        snapshot(trace=PIPELINE[:5], prompt=PromptPreservationEvidence(
            prompt_revision_id="prompt-r0",
            prompt_hash="prompt-hash",
            product_lock_digest=product_lock().product_lock_digest,
            brand_lock_digest=product_lock().brand_lock_digest,
            verified=False,
        ))
    ).stop_reason.code == "PROMPT_PRESERVATION_FAILED"


def test_prompt_and_package_lock_drift_stops_before_e1():
    trace = PIPELINE[:5]
    mismatched_prompt = PromptPreservationEvidence(
        prompt_revision_id="prompt-r0",
        prompt_hash="prompt-hash",
        product_lock_digest="stale-product-lock",
        brand_lock_digest=product_lock().brand_lock_digest,
    )
    assert decide(snapshot(trace=trace, prompt=mismatched_prompt)).stop_reason.code == (
        "PROMPT_PRESERVATION_FAILED"
    )

    lock = product_lock()
    mismatched_package = PackageRevisionSummary(
        package_revision_id="package-stale",
        prompt_revision_id="prompt-r0",
        revision_index=0,
        parent_package_revision_id="package-root",
        parent_prompt_revision_id="prompt-root",
        product_lock_digest="stale-product-lock",
        brand_lock_digest=lock.brand_lock_digest,
        reality_digest=reality().evidence_digest,
        scene_digest="scene-r0",
        composition_digest="composition-r0",
        prompt_preservation_digest=prompt().evidence_digest,
        changed_module="initial",
        causal_variable="initial",
    )
    assert decide(
        snapshot(trace=trace, current_package=mismatched_package)
    ).stop_reason.code == "PROMPT_PRESERVATION_FAILED"


def test_critic_no_action_stops_for_human_review_without_qualification():
    trace = PIPELINE[:5] + ("E1", "CRITIC")
    result = decide(snapshot(trace=trace, critic=report(decision="NO_ACTION")))
    assert result.stop_reason.code == "QUALITY_TARGET_MET"
    assert result.human_review_required
    assert result.audit.ai_qualification == "UNVERIFIED"
    assert result.audit.provider_called is False
    assert result.audit.production_write is False


def test_unverified_pixels_and_missing_critic_stop_safely():
    trace = PIPELINE[:5] + ("E1", "CRITIC")
    assert decide(snapshot(trace=trace)).stop_reason.code == "DEPENDENCY_BLOCKED"
    assert decide(
        snapshot(trace=trace, critic=report(decision="UNVERIFIED"))
    ).stop_reason.code == "UNVERIFIED_PIXELS"
    assert decide(
        snapshot(trace=trace, critic=report(finding(), pixels_verified=False))
    ).stop_reason.code == "UNVERIFIED_PIXELS"


def test_revision_targets_one_allowed_failure_and_creates_two_new_immutable_summaries():
    trace = PIPELINE[:5] + ("E1", "CRITIC")
    result = decide(
        snapshot(
            trace=trace,
            critic=report(
                finding("locked-high", severity=3, locked=True),
                finding("exposure", module="Reality", severity=2),
                finding("composition", module="Composition", severity=2),
            ),
        )
    )
    assert result.action == "PROPOSE_REVISION"
    assert result.stage == "TARGETED_REVISION"
    assert result.changed_module == "Reality"
    assert result.causal_variable == "exposure"
    assert result.new_prompt_revision.revision_index == 1
    assert result.new_package_revision.revision_index == 1
    assert result.new_package_revision.prompt_revision_id == (
        result.new_prompt_revision.prompt_revision_id
    )
    assert result.new_package_revision.parent_package_revision_id == "package-r0"
    assert result.new_package_revision.immutable is True
    assert result.new_package_revision.human_qualification == "PENDING_HUMAN_REVIEW"
    assert result.audit.package_revision_ids[-1] == result.new_package_revision.package_revision_id


def test_locked_product_and_disallowed_module_never_become_revision_targets():
    trace = PIPELINE[:5] + ("E1", "CRITIC")
    product_conflict = decide(
        snapshot(trace=trace, critic=report(finding("logo", module="Product")))
    )
    assert product_conflict.stop_reason.code == "LOCK_CONFLICT"

    disallowed = decide(
        snapshot(
            trace=trace,
            critic=report(finding("motion", module="Scene")),
            authorization=authorization(allowed_modules=("Reality",)),
        )
    )
    assert disallowed.stop_reason.code == "MODULE_NOT_AUTHORIZED"


def test_two_non_improvements_and_revision_limit_stop():
    trace = PIPELINE[:5] + ("E1", "CRITIC")
    prior = report(finding("exposure", progress="UNCHANGED"), iteration_index=0)
    current = report(finding("exposure", progress="UNCHANGED"), iteration_index=1)
    assert decide(
        snapshot(trace=trace, revision_index=1, critic=current, critic_history=(prior,))
    ).stop_reason.code == "NO_PROGRESS"
    assert decide(
        snapshot(
            trace=trace,
            revision_index=2,
            critic=report(finding()),
            authorization=authorization(max_revisions=2),
        )
    ).stop_reason.code == "LIMIT_REACHED"


def test_revisions_are_bounded_and_history_is_not_mutated():
    trace = PIPELINE[:5] + ("E1", "CRITIC")
    state = snapshot(trace=trace, critic=report(finding()))
    result = decide(state)
    assert result.iteration_index == 1
    assert state.revision_index == 0
    with pytest.raises(FrozenInstanceError):
        result.action = "STOP"


def test_reality_requires_fixed_six_dimension_order_and_na_reason():
    with pytest.raises(ValueError, match="fixed order"):
        RealityEvidence(tuple(
            RealityDimensionEvidence(
                dimension=dimension,
                decision="visible",
                evidence_status="PROPOSED",
                evidence="observed",
            )
            for dimension in reversed(REALITY_ORDER)
        ))
    with pytest.raises(ValueError, match="na_reason"):
        RealityDimensionEvidence(
            dimension="Camera",
            decision="N/A",
            evidence_status="NOT_APPLICABLE",
            evidence="not applicable",
        )


def test_ai_qualification_cannot_be_qualified():
    with pytest.raises(ValueError, match="human qualification"):
        CriticReport(
            iteration_index=0,
            decision="NO_ACTION",
            human_qualification="QUALIFIED",
        )
