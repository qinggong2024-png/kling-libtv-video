from __future__ import annotations

from copy import deepcopy

import pytest
from libtv_agent.creative.state_adapters import adapt_storyboard_state
from libtv_agent.creative.state_projection import project_creative_state
from libtv_agent.creative.state_revision import validate_revision_integrity
from test_creative_state_foundation import creative_snapshot, product_payload


def selected_snapshot() -> dict:
    snapshot = creative_snapshot()
    snapshot["package"]["revision"] = 3
    snapshot["selection"] = {
        "shot_id": "FIRST_FRAME",
        "purpose": "FIRST_FRAME",
        "package_id": "package-first-frame",
        "candidate_id": "shared-candidate",
        "batch_id": "first-batch",
        "item_id": "first-item",
        "output_id": "first-output",
    }
    snapshot["candidates"] = [{
        **snapshot["selection"],
        "sha256": "e" * 64,
    }]
    snapshot["latest_review"] = {
        "candidate_id": "shared-candidate",
        "shot_id": "FIRST_FRAME",
        "scope": "FIRST_FRAME",
        "reviewer_kind": "HUMAN",
        "decision": "QUALIFIED",
        "qualification_scope": "OFFLINE_SYNTHETIC_ONLY",
        "axes": {"product_fidelity": "unverified"},
    }
    storyboard = snapshot["storyboard"]
    storyboard["shot_order"] = ["SHOT_01"]
    storyboard["candidates"][0].update({
        "candidate_id": "shared-candidate",
        "package_id": "package-shot-01",
        "purpose": "VIDEO_STORYBOARD",
    })
    storyboard["selections"]["SHOT_01"].update({
        "candidate_id": "shared-candidate",
        "shot_id": "SHOT_01",
        "package_id": "package-shot-01",
        "purpose": "VIDEO_STORYBOARD",
    })
    storyboard["latest_reviews"] = {"SHOT_01": {
        "candidate_id": "shared-candidate",
        "shot_id": "SHOT_01",
        "scope": "VIDEO_STORYBOARD",
        "reviewer_kind": "HUMAN",
        "decision": "REJECTED",
        "qualification_scope": "OFFLINE_SYNTHETIC_ONLY",
        "reason": "garment detail is unclear",
    }}
    return snapshot


def project(snapshot: dict):
    return project_creative_state(
        creative_task={
            "id": "creative-task-1",
            "user_id": "owner-1",
            "current_revision": 9,
            "state_version": 11,
            "updated_at": "2026-10-13T00:00:00Z",
            "snapshot_json": snapshot,
        },
        product_version=product_payload(),
        owner_id="owner-1",
    )


def test_first_frame_and_storyboard_keep_independent_source_review_and_package() -> None:
    snapshot = selected_snapshot()
    before = deepcopy(snapshot)
    result = project(snapshot)
    assert result.valid
    assert result.revision is not None
    first, video = result.revision.shots
    assert result.revision.revision == 9
    assert result.revision.state_version == 11
    assert result.revision.facts_revision == 3
    assert result.revision.storyboard.shot_order == ("FIRST_FRAME", "SHOT_01")
    assert result.revision.storyboard.package_revision_id == "package-first-frame"
    assert result.revision.storyboard.selected_direction_id == "A"
    assert first.source_bindings.source_sha256 == "e" * 64
    assert video.source_bindings.source_sha256 == "d" * 64
    assert first.source_bindings.output_id == "first-output"
    assert video.source_bindings.output_id == "output-1"
    assert first.review["decision"] == "QUALIFIED"
    assert video.review["decision"] == "REJECTED"
    assert first.prompt_refs.package_revision == 3
    assert video.prompt_refs.package_revision == 1
    assert first.prompt_refs.preservation_hash == "b" * 64
    assert video.prompt_refs.preservation_hash == "c" * 64
    assert first.prompt_refs.video_prompt_revision is None
    assert video.prompt_refs.video_prompt_revision == "package-shot-01"
    assert result.revision.quality.delivery_eligibility == "NOT_ELIGIBLE"
    validate_revision_integrity(result.revision)
    assert snapshot == before
    first.review["axes"]["product_fidelity"] = "changed locally"
    assert snapshot == before


@pytest.mark.parametrize("foreign_field,foreign_value", [
    ("shot_id", "SHOT_02"),
    ("package_id", "old-package"),
    ("package_id", None),
    ("shot_id", None),
])
def test_candidate_hash_requires_explicit_matching_shot_and_package(
    foreign_field: str, foreign_value: str | None,
) -> None:
    snapshot = selected_snapshot()
    snapshot["storyboard"]["candidates"][0][foreign_field] = foreign_value
    snapshot["storyboard"]["shot_mappings"] = {}
    result = project(snapshot)
    assert result.state is not None
    first, video = result.state.shots
    assert first.source_bindings.source_sha256 == "e" * 64
    assert video.source_bindings.source_sha256 is None
    assert video.source_bindings.selected_candidate_id == "shared-candidate"
    assert "selected_source_candidate" in video.unresolved_references
    assert any(item.code == "SELECTED_SOURCE_UNRESOLVED" for item in result.diagnostics)
    assert result.state.status == "BLOCKED"


@pytest.mark.parametrize("record,field,value,code", [
    ("package", "shot_id", "SHOT_02", "SHOT_SOURCE_CONFLICT"),
    ("selection", "shot_id", "FIRST_FRAME", "SHOT_SOURCE_CONFLICT"),
    ("selection", "package_id", "old-package", "SHOT_SOURCE_CONFLICT"),
    ("selection", "package_revision", 2, "SHOT_SOURCE_CONFLICT"),
    ("selection", "purpose", "FIRST_FRAME", "SHOT_SOURCE_CONFLICT"),
    ("mapping", "candidate_id", "other-candidate", "CANDIDATE_SOURCE_CONFLICT"),
    ("mapping", "output_id", "other-output", "OUTPUT_SOURCE_CONFLICT"),
    ("mapping", "source_image_hash", "f" * 64, "SOURCE_HASH_CONFLICT"),
    ("review", "shot_id", "FIRST_FRAME", "SHOT_SOURCE_CONFLICT"),
    ("review", "scope", "FIRST_FRAME", "SHOT_SOURCE_CONFLICT"),
])
def test_conflicting_source_returns_diagnostic_without_fabricated_revision(
    record: str, field: str, value: object, code: str,
) -> None:
    snapshot = selected_snapshot()
    storyboard = snapshot["storyboard"]
    target = {
        "package": storyboard["packages"]["SHOT_01"],
        "selection": storyboard["selections"]["SHOT_01"],
        "mapping": storyboard["shot_mappings"]["SHOT_01"],
        "review": storyboard["latest_reviews"]["SHOT_01"],
    }[record]
    target[field] = value
    result = project(snapshot)
    assert not result.valid
    assert result.state is None
    assert result.revision is None
    assert any(
        item.code == code and item.source_refs == ("SHOT_01",)
        for item in result.diagnostics
    )


def test_reordering_does_not_change_package_or_source_identity() -> None:
    snapshot = selected_snapshot()
    snapshot["storyboard"]["packages"]["SHOT_02"] = {
        "package_id": "package-shot-02",
        "revision": 2,
        "purpose": "VIDEO_STORYBOARD",
        "shot_id": "SHOT_02",
    }
    snapshot["storyboard"]["shot_order"] = ["SHOT_02", "SHOT_01"]
    state, shots = adapt_storyboard_state(snapshot, product_version_id="version-1")
    assert state.shot_order == ("FIRST_FRAME", "SHOT_02", "SHOT_01")
    assert state.package_revision_id == "package-first-frame"
    assert shots[1].source_bindings is None
    assert shots[2].source_bindings.output_id == "output-1"
    assert shots[2].prompt_refs.package_revision == 1


def test_sequence_packages_project_without_using_position_for_identity() -> None:
    snapshot = selected_snapshot()
    snapshot["storyboard"]["packages"] = list(snapshot["storyboard"]["packages"].values())
    result = project(snapshot)
    assert result.revision is not None
    assert result.revision.shots[1].shot_id == "SHOT_01"
    assert result.revision.shots[1].source_bindings.source_sha256 == "d" * 64


@pytest.mark.parametrize("change", ["package_revision", "review", "source_hash", "direction"])
def test_each_existing_creative_change_is_covered_by_revision_hash(change: str) -> None:
    snapshot = selected_snapshot()
    original = project(snapshot).revision
    if change == "package_revision":
        snapshot["package"]["revision"] += 1
    elif change == "review":
        snapshot["latest_review"]["decision"] = "UNVERIFIED"
    elif change == "source_hash":
        snapshot["candidates"][0]["sha256"] = "f" * 64
    else:
        snapshot["plan"]["directions"].append({"id": "B", "summary": "another direction"})
        snapshot["plan"]["selected_direction"] = "B"
    changed = project(snapshot).revision
    assert original is not None and changed is not None
    assert changed.content_hash != original.content_hash
    assert changed.locks_hash == original.locks_hash
    assert changed.source_snapshot_hash == original.source_snapshot_hash


@pytest.mark.parametrize("field", ["selections", "latest_reviews"])
def test_first_frame_root_conflict_is_not_silently_overridden(field: str) -> None:
    snapshot = selected_snapshot()
    root_field = "selection" if field == "selections" else "latest_review"
    snapshot["storyboard"].setdefault(field, {})["FIRST_FRAME"] = {
        **snapshot[root_field],
        "candidate_id": "another-first-frame",
    }
    result = project(snapshot)
    assert result.revision is None
    assert any(item.code == "FIRST_FRAME_SOURCE_CONFLICT" for item in result.diagnostics)


@pytest.mark.parametrize("mode", ["automatic", "custom"])
def test_legacy_video_snapshot_does_not_invent_shots_or_rewrite_mode(mode: str) -> None:
    snapshot = {"execution_mode": mode, "assets": [{"order": 1, "output_id": "legacy"}]}
    before = deepcopy(snapshot)
    result = project(snapshot)
    assert result.revision is not None
    assert result.revision.shots == ()
    assert result.revision.storyboard.package_revision_id is None
    assert snapshot == before
