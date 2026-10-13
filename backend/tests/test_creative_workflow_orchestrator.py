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
    LayerEvidence,
    LoopAuthorization,
    PackageRevisionSummary,
    ProductBrandLock,
    PromptPreservationEvidence,
    PromptRevisionSummary,
    RealityDimensionEvidence,
    RealityEvidence,
)
from libtv_agent.services.creative_workflow_orchestrator import (
    CreativeWorkflowOrchestrator,
    CreativeWorkflowSnapshot,
    E1Snapshot,
    TextPackageSnapshot,
    decide,
)

NOW = datetime(2026, 10, 12, 12, tzinfo=UTC)


def product() -> ProductBrandLock:
    return ProductBrandLock(
        product_id="product-1",
        product_revision="product-r1",
        product_source_hash="front-sha",
        brand_id="brand-1",
        brand_revision="brand-r1",
        brand_source="USER_SELECTED",
    )


def reality() -> RealityEvidence:
    return RealityEvidence(
        tuple(
            RealityDimensionEvidence(
                dimension=dimension,
                decision=f"fixed {dimension}",
                evidence_status="PROPOSED",
                evidence=f"evidence for {dimension}",
            )
            for dimension in REALITY_ORDER
        )
    )


def text_package() -> TextPackageSnapshot:
    lock = product()
    preservation = PromptPreservationEvidence(
        prompt_revision_id="prompt-r0",
        prompt_hash="prompt-hash-r0",
        product_lock_digest=lock.product_lock_digest,
        brand_lock_digest=lock.brand_lock_digest,
    )
    prompt = PromptRevisionSummary(
        prompt_revision_id="prompt-r0",
        revision_index=0,
        parent_prompt_revision_id="prompt-root",
        content_hash="prompt-content-r0",
        preservation_hash=preservation.evidence_digest,
    )
    package = PackageRevisionSummary(
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
        prompt_preservation_digest=preservation.evidence_digest,
        changed_module="initial",
        causal_variable="initial",
    )
    return TextPackageSnapshot(
        preservation=preservation,
        prompt_revision=prompt,
        package_revision=package,
        scene=LayerEvidence("Scene", "scene-r0", "scene-sha", "PROPOSED", "studio"),
        composition=LayerEvidence(
            "Composition", "composition-r0", "composition-sha", "PROPOSED", "medium shot"
        ),
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


def snapshot(**overrides) -> CreativeWorkflowSnapshot:
    values = {
        "loop_id": "loop-1",
        "now": NOW,
        "authorization": authorization(),
        "product": product(),
        "direction": DirectionEvidence("direction-A", "direction-r1"),
        "dna_reality": reality(),
        "text_package": text_package(),
        "e1": E1Snapshot(planned_call_cost_micros=10),
    }
    values.update(overrides)
    return CreativeWorkflowSnapshot(**values)


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


def test_orchestrator_follows_plugin_module_order_and_emits_inert_commands():
    service = CreativeWorkflowOrchestrator()
    trace = ()
    observed = []
    for _ in range(5):
        result = service.decide(snapshot(trace=trace))
        observed.append(result.command.stage)
        assert result.command.execution_mode == "AUDIT_ONLY"
        assert result.command.provider_execution_allowed is False
        assert result.audit_event.provider_called is False
        assert result.audit_event.production_write is False
        trace = (*trace, result.command.stage)

    assert observed == list(PIPELINE[:5])
    assert service.decide(snapshot(trace=trace)).command.kind == "CALL_E1"


def test_failure_evidence_routes_to_one_corresponding_revision_module():
    trace = PIPELINE[:5] + ("E1", "CRITIC")
    result = decide(
        snapshot(
            trace=trace,
            critic=report(
                finding("exposure", module="Reality", severity=2),
                finding("motion", module="Scene", severity=3),
                finding("framing", module="Composition", severity=3),
            ),
        )
    )
    assert result.command.kind == "PROPOSE_REVISION"
    assert result.command.stage == "TARGETED_REVISION"
    assert result.revision_summary is not None
    assert result.revision_summary.changed_module == "Scene"
    assert result.revision_summary.causal_variable == "motion"


def test_lock_conflict_stops_and_marks_human_boundary():
    trace = PIPELINE[:5] + ("E1", "CRITIC")
    result = decide(
        snapshot(trace=trace, critic=report(finding("logo", module="Product", locked=True)))
    )
    assert result.command.kind == "STOP"
    assert result.stop_wait_reason is not None
    assert result.stop_wait_reason.code == "LOCK_CONFLICT"
    assert result.command.requires_human_review
    assert result.audit_event.ai_qualification == "UNVERIFIED"


@pytest.mark.parametrize("status", ["UNKNOWN", "WRITE_UNCERTAIN"])
def test_unknown_execution_only_emits_reconciliation_wait(status):
    result = decide(snapshot(e1=E1Snapshot(last_call_status=status)))
    assert result.command.kind == "WAIT_RECONCILIATION"
    assert result.stop_wait_reason is not None
    assert result.stop_wait_reason.code == "EXECUTION_UNKNOWN"
    assert result.command.expected_call_count == 0


def test_ai_no_action_stops_for_human_review_without_qualification():
    trace = PIPELINE[:5] + ("E1", "CRITIC")
    result = decide(snapshot(trace=trace, critic=report(decision="NO_ACTION")))
    assert result.command.kind == "STOP"
    assert result.stop_wait_reason.code == "QUALITY_TARGET_MET"
    assert result.command.requires_human_review
    assert result.audit_event.ai_qualification == "UNVERIFIED"


def test_revision_output_is_immutable_summary_without_prompt_text():
    trace = PIPELINE[:5] + ("E1", "CRITIC")
    result = decide(snapshot(trace=trace, critic=report(finding())))
    summary = result.revision_summary
    assert summary is not None
    assert summary.human_qualification == "PENDING_HUMAN_REVIEW"
    assert not hasattr(summary, "prompt")
    with pytest.raises(FrozenInstanceError):
        summary.changed_module = "Product"


def test_default_closed_and_revision_cap_are_enforced_by_orchestrator_contract():
    disabled = decide(snapshot(authorization=LoopAuthorization()))
    assert disabled.command.kind == "STOP"
    assert disabled.stop_wait_reason.code == "LOOP_DISABLED"
    with pytest.raises(ValueError, match="max_revisions"):
        authorization(max_revisions=3)


def test_audit_event_is_deterministic_and_serializable():
    first = decide(snapshot())
    second = decide(snapshot())
    assert first.audit_event == second.audit_event
    payload = first.to_dict()
    assert payload["audit_event"]["event_type"] == "CREATIVE_ORCHESTRATOR_DECISION"
    assert payload["audit_event"]["provider_called"] is False


def test_orchestrator_does_not_turn_ai_pass_into_qualified():
    trace = PIPELINE[:5] + ("E1", "CRITIC")
    result = decide(snapshot(trace=trace, critic=report(decision="NO_ACTION")))
    assert result.audit_event.ai_qualification == "UNVERIFIED"
    assert "QUALIFIED" not in str(result.to_dict())
