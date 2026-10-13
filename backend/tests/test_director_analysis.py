from __future__ import annotations

import pytest
from libtv_agent.creative.director_analysis import (
    ANALYSIS_PIPELINE,
    build_director_analysis,
    select_director_direction,
    validate_director_analysis,
)


def analysis():
    return build_director_analysis(
        source_hash="front-sha",
        facts_revision=3,
        directions=[
            {"id": "A", "scene": "street", "behavior": "walk"},
            {"id": "B", "scene": "room", "behavior": "turn"},
            {"id": "C", "scene": "studio", "behavior": "stand"},
        ],
        brand_selected=False,
    )


def test_analysis_contains_the_plugin_order_and_conservative_video_strategy():
    value = analysis()

    assert value.schema_version == "director-analysis.v1"
    assert value.trace == ANALYSIS_PIPELINE
    assert tuple(stage.key for stage in value.stages) == ANALYSIS_PIPELINE
    assert value.stages[0].depends_on == ()
    assert value.stages[-1].depends_on == ANALYSIS_PIPELINE[:-1]
    assert value.video_strategy.strategy == "strategy_unresolved"
    assert value.video_strategy.generation_authorized is False
    assert value.stages[5].status == "UNRESOLVED"
    assert value.stages[7].status == "UNVERIFIED"


def test_direction_selection_is_a_new_analysis_snapshot():
    original = analysis()
    selected = select_director_direction(original, "B")

    assert original.selected_direction is None
    assert selected.selected_direction == "B"
    assert selected.planning_status == "READY_FOR_PACKAGE"
    assert selected.trace == original.trace


def test_tampered_or_reordered_analysis_is_rejected():
    payload = analysis().model_dump(mode="json")
    payload["trace"] = list(reversed(payload["trace"]))

    with pytest.raises(ValueError):
        validate_director_analysis(payload)


@pytest.mark.parametrize("change", [
    "missing_stage", "reordered_stages", "wrong_order", "missing_dependency",
    "empty_evidence", "blank_output", "duplicate_directions", "invalid_selection",
    "false_ready_status",
])
def test_incomplete_or_inconsistent_contract_is_rejected(change):
    payload = analysis().model_dump(mode="json")
    if change == "missing_stage":
        payload["stages"].pop()
    elif change == "reordered_stages":
        payload["stages"].reverse()
    elif change == "wrong_order":
        payload["stages"][1]["order"] = 1
    elif change == "missing_dependency":
        payload["stages"][1]["depends_on"] = []
    elif change == "empty_evidence":
        payload["stages"][0]["evidence"] = []
    elif change == "blank_output":
        payload["stages"][0]["outputs"] = [" "]
    elif change == "duplicate_directions":
        payload["direction_ids"] = ["A", "A"]
    elif change == "invalid_selection":
        payload["selected_direction"] = "foreign"
    else:
        payload["planning_status"] = "READY_FOR_PACKAGE"
    with pytest.raises(ValueError):
        validate_director_analysis(payload)


def test_model_instance_is_revalidated_and_does_not_bypass_pipeline():
    corrupt = analysis().model_copy(update={"trace": ()})
    with pytest.raises(ValueError):
        validate_director_analysis(corrupt)
