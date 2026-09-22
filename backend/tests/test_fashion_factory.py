from datetime import UTC, datetime

import pytest
from pydantic import ValidationError
from libtv_agent.config import Settings
from libtv_agent.fashion_factory.contracts import (
    CONTRACT_SCHEMA_VERSION,
    DifficultyTier,
    EditShot,
    MusicTrack,
    PilotRun,
    ProductTruthSnapshot,
    PropagationRisk,
    Route,
    SemanticEditSkeleton,
    Severity,
    TemporalError,
)
from libtv_agent.fashion_factory.editing import (
    IneligibleMusicError,
    create_render_plan,
    micro_align_cuts,
)
from libtv_agent.fashion_factory.orchestrator import (
    FactoryState,
    assert_factory_transition,
    resume_state,
)
from libtv_agent.fashion_factory.pilot import calculate_pilot_metrics
from libtv_agent.fashion_factory.policies import RetryBudget, decide_temporal_error


def snapshot() -> ProductTruthSnapshot:
    return ProductTruthSnapshot(
        snapshot_id="snapshot-1",
        product_id="sku-1",
        source_images=("front.png",),
        source_image_hashes=("a" * 64,),
        product_type="T_SHIRT",
        must_preserve_features=("front logo",),
        unknown_views=("back",),
        created_at=datetime(2026, 8, 13, tzinfo=UTC),
    )


def music(*, licensed: bool = True, beats: tuple[int, ...] = (975, 2100)) -> MusicTrack:
    return MusicTrack(
        track_id="track-1",
        source="licensed-library",
        license_status="AUTHORIZED" if licensed else "UNKNOWN",
        license_scope="commercial ads",
        duration_ms=10_000,
        bpm=120,
        beats_ms=beats,
        usable_range_ms=(0, 10_000),
        genre="pop",
        mood="bright",
    )


def skeleton() -> SemanticEditSkeleton:
    return SemanticEditSkeleton(
        skeleton_id="skeleton-1",
        shots=(
            EditShot(
                segment_id="segment-1",
                semantic_cut_ms=1000,
                minimum_cut_ms=900,
                maximum_cut_ms=1200,
                product_fidelity="PASS",
                segment_validity="PASS",
                semantic_continuity="PASS",
                product_visibility="PASS",
                shot_completeness="PASS",
            ),
        ),
    )


def test_product_truth_is_frozen_and_hash_is_stable() -> None:
    truth = snapshot()
    assert truth.immutable is True
    assert truth.schema_version == CONTRACT_SCHEMA_VERSION
    assert truth.content_hash() == snapshot().content_hash()
    with pytest.raises(ValidationError):
        truth.product_type = "DRESS"


def test_product_truth_requires_one_hash_per_source_image() -> None:
    with pytest.raises(ValueError, match="one-to-one"):
        ProductTruthSnapshot(
            snapshot_id="snapshot-1",
            product_id="sku-1",
            source_images=("front.png", "back.png"),
            source_image_hashes=("a" * 64,),
            product_type="T_SHIRT",
            created_at=datetime.now(UTC),
        )


def test_transient_error_gets_safe_margin_outside_error_interval() -> None:
    decision = decide_temporal_error(
        TemporalError(
            reason_code="TRANSIENT_HAND_ARTIFACT",
            severity=Severity.MEDIUM,
            confidence=0.9,
            start_ms=2000,
            end_ms=2300,
            propagation_risk=PropagationRisk.LOW,
        ),
        RetryBudget(),
    )
    assert decision.action == "CUT"
    assert decision.safe_cut_before_ms == 1750
    assert decision.safe_cut_after_ms == 2550


def test_hard_product_error_is_never_salvaged_and_retry_is_targeted() -> None:
    decision = decide_temporal_error(
        TemporalError(
            reason_code="GRAPHIC_LOGO_DRIFT",
            severity=Severity.CRITICAL,
            confidence=0.99,
            start_ms=1000,
            end_ms=8000,
            propagation_risk=PropagationRisk.HIGH,
        ),
        RetryBudget(),
    )
    assert decision.action == "REGENERATE"
    assert decision.salvageable is False
    assert "reference" in (decision.retry_strategy or "")


def test_retry_budget_escalates_instead_of_repeating_blindly() -> None:
    decision = decide_temporal_error(
        TemporalError(
            reason_code="SCENE_GEOMETRY_BREAK",
            severity=Severity.HIGH,
            confidence=0.9,
            start_ms=0,
            end_ms=5000,
            propagation_risk=PropagationRisk.HIGH,
        ),
        RetryBudget(retry_count=2, total_attempts=3),
    )
    assert decision.retry_strategy == "escalate_to_human_review_or_terminal_failure"


def test_beat_alignment_snaps_only_inside_semantic_window_and_tolerance() -> None:
    assert micro_align_cuts(skeleton(), music()) == (975,)
    assert micro_align_cuts(skeleton(), music(beats=(1399,))) == (1000,)


def test_unlicensed_bgm_is_blocked() -> None:
    with pytest.raises(IneligibleMusicError):
        micro_align_cuts(skeleton(), music(licensed=False))


def test_render_plan_is_reproducible_and_carries_lineage() -> None:
    first = create_render_plan("plan-1", "snapshot-1", ("clip-1",), skeleton(), music())
    second = create_render_plan("plan-1", "snapshot-1", ("clip-1",), skeleton(), music())
    assert first.deterministic_fingerprint == second.deterministic_fingerprint
    assert first.product_snapshot_id == "snapshot-1"
    assert first.source_clip_ids == ("clip-1",)


def test_factory_state_resume_does_not_restart_and_rejects_illegal_transition() -> None:
    assert resume_state("TEMPORAL_QA_RUNNING") == FactoryState.TEMPORAL_QA_RUNNING
    assert_factory_transition(FactoryState.VIDEO_READY, FactoryState.TEMPORAL_QA_RUNNING)
    with pytest.raises(ValueError, match="illegal"):
        assert_factory_transition(FactoryState.VIDEO_READY, FactoryState.DELIVERED)


def test_pilot_metrics_keep_system_qa_separate_from_ground_truth() -> None:
    runs = [
        PilotRun(
            run_id="run-1",
            sku="sku-1",
            difficulty_tier=DifficultyTier.LOW,
            route=Route.LONG_CLIP,
            provider="fake",
            model="fake",
            generated_seconds=10,
            actual_api_cost=2,
            image_attempts=1,
            video_attempts=1,
            technical_qualified_seconds=8,
            editorial_qualified_seconds=6,
            final_duration_seconds=6,
            lead_time_seconds=30,
            system_pass=True,
            ground_truth_pass=False,
            product_fidelity_pass=False,
            human_intervention=False,
            failure_codes=("GRAPHIC_LOGO_DRIFT",),
        ),
        PilotRun(
            run_id="run-2",
            sku="sku-2",
            difficulty_tier=DifficultyTier.HIGH,
            route=Route.SHORT_SHOT,
            provider="fake",
            model="fake",
            generated_seconds=4,
            actual_api_cost=1,
            image_attempts=1,
            video_attempts=2,
            technical_qualified_seconds=4,
            editorial_qualified_seconds=4,
            final_duration_seconds=4,
            lead_time_seconds=20,
            system_pass=False,
            ground_truth_pass=True,
            product_fidelity_pass=True,
            human_intervention=True,
        ),
    ]
    metrics = calculate_pilot_metrics(runs)
    assert metrics.qa_false_negative_rate == 1
    assert metrics.qa_false_positive_rate == 1
    assert metrics.failure_pareto[0] == ("GRAPHIC_LOGO_DRIFT", 1)


def test_factory_flags_are_disabled_by_default() -> None:
    settings = Settings(_env_file=None)
    assert settings.fashion_video_factory_v1 is False
    assert settings.long_clip_salvage is False
    assert settings.short_shot_control is False
    assert settings.beat_aware_editing is False
    assert settings.product_to_model is False
    assert settings.reference_guided_route is False
    assert settings.independent_pilot_review is False
