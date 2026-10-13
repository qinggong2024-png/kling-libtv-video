from __future__ import annotations

import json
import uuid
from copy import deepcopy

import pytest
from libtv_agent.creative.package_contract import (
    CONTENT_FIELDS,
    project_creative_package,
    render_creative_package_text,
    serialize_creative_package,
)
from libtv_agent.creative.reality_evidence import registry_evidence_rules
from libtv_agent.creative.text_contract import freeze_text_contract
from libtv_agent.creative.workflow import compile_package, compile_storyboard_package, digest


def freeze_snapshot(snapshot: dict) -> None:
    """Freeze a newly authored test context with the existing D4 Registry shape."""
    packages = [snapshot["package"], *snapshot["storyboard"]["packages"].values()]
    contracts = {}
    for item in packages:
        manifest = {
            "ruleset": item["ruleset"],
            "preservation": "canonical-product-prompt-and-reality",
        }
        rules = registry_evidence_rules(item["reality"])
        if rules is not None:
            manifest["reality_evidence_rules"] = rules
        registry = {
            "prompt_key": f"creative.fake:{item['package_id']}",
            "version": item["revision"],
            "content_hash": digest(item["prompt"]),
            "payload_json": {
                "package_id": item["package_id"], "prompt": item["prompt"],
                "content_hash": digest(item["prompt"]),
                "manifest": manifest, "manifest_hash": digest(manifest),
            },
        }
        contracts[item["package_id"]] = {
            "registry_snapshot": registry,
            "text_contract": freeze_text_contract(
                snapshot["plan"], item, registry, snapshot["facts_snapshot"],
            ),
        }
    snapshot["package_contracts"] = contracts
    snapshot.update(deepcopy(contracts[snapshot["package"]["package_id"]]))


def snapshot_fixture() -> dict:
    task_id = uuid.UUID("00000000-0000-0000-0000-000000000001")
    facts = {
        "product_id": "product-1",
        "product_version_id": "version-3",
        "facts_revision": 3,
        "truth_fields": {"front_color": "black", "name": "Jersey"},
        "unknown_attributes": ["back print"],
        "user_assumptions": ["back is plain"],
        "source_hash": "a" * 64,
        "source_asset_references": ["product/front.png"],
    }
    locks = {
        "product_id": "product-1", "source_hash": "a" * 64,
        "user_locks": {"selected_direction": "B", "shot_id": "FIRST_FRAME"},
    }
    plan = {
        "product_id": "product-1", "product_version_id": "version-3",
        "source_hash": "a" * 64, "facts_revision": 3,
        "facts_snapshot_hash": digest(facts), "locks": locks,
        "evidence": "FAKE_NOT_IMAGE_ANALYSIS",
        "selected_direction": "B",
        "directions": [
            {"id": "A", "scene": "night street", "behavior": "walk"},
            {
                "id": "B", "title": "Mirror jersey", "human": "natural adult",
                "scene": "bedroom", "behavior": "check jersey", "camera": "mirror selfie",
            },
        ],
        "claims": [{
            "claim_id": "front-source", "value": "front image available",
            "source_fact_keys": ["source_asset_references"], "facts_revision": 3,
            "evidence_kind": "OBSERVED_REFERENCE",
            "confidence_basis": "asset_sha256_and_source_fact",
            "unknown_or_assumption": "back view not observed",
        }],
    }
    package = compile_package(task_id, plan, digest(locks), 2).model_dump(mode="json")
    shot = compile_storyboard_package(
        task_id, plan, package, "first-frame-candidate", "SHOT_01",
    ).model_dump(mode="json")
    snapshot = {
        "plan": plan, "package": package, "facts_snapshot": facts,
        "product_version": facts,
        "asset": {"object_key": "product/front.png", "sha256": "a" * 64,
                  "license_status": "UNVERIFIED", "evidence_status": "OBSERVED_REFERENCE"},
        "storyboard": {"packages": {"SHOT_01": shot}, "shot_order": ["SHOT_01"]},
    }
    freeze_snapshot(snapshot)
    return snapshot


def test_complete_contract_preserves_frozen_package_facts_and_evidence() -> None:
    snapshot = snapshot_fixture()
    package = snapshot["package"]
    result = project_creative_package(snapshot)
    assert set(result) == {*CONTENT_FIELDS, "provenance", "fieldStatus"}
    assert set(result["fieldStatus"]) == set(CONTENT_FIELDS)
    assert result["direction"]["id"] == "B"
    assert result["imagePrompt"] == package["prompt"]
    assert result["sceneDNA"] == {"description": "bedroom", "origin": "PROPOSED"}
    assert result["cameraDNA"]["description"] == "mirror selfie"
    provenance = result["provenance"]
    assert provenance["packageId"] == package["package_id"]
    assert provenance["revision"] == 2
    assert provenance["shotId"] == "FIRST_FRAME"
    assert provenance["sourcePackage"] == package
    assert provenance["productFacts"] == snapshot["facts_snapshot"]
    assert provenance["sourceAssets"] == [snapshot["asset"]]
    assert provenance["locks"] == snapshot["plan"]["locks"]
    assert provenance["locksHash"] == package["locks_hash"]
    assert provenance["preservationHash"] == package["preservation_hash"]
    assert provenance["originEvidence"]["packageContract"] == (
        snapshot["package_contracts"][package["package_id"]]
    )
    assert provenance["originEvidence"]["planEvidence"] == "FAKE_NOT_IMAGE_ANALYSIS"
    assert provenance["originEvidence"]["claims"] == snapshot["plan"]["claims"]
    assert provenance["originEvidence"]["reality"] == package["reality"]
    assert provenance["synthetic"] is True
    assert provenance["qualificationScope"] == "OFFLINE_SYNTHETIC_ONLY"
    assert provenance["qualified"] is False
    assert provenance["deliverable"] is False
    assert provenance["providerSubmissionAllowed"] is False
    assert {item["status"] for item in result["qualityChecklist"]} == {"UNVERIFIED"}


def test_unknown_audience_and_video_draft_are_distinct_from_execution_prompt() -> None:
    snapshot = snapshot_fixture()
    for package_id in (
        snapshot["package"]["package_id"],
        snapshot["storyboard"]["packages"]["SHOT_01"]["package_id"],
    ):
        result = project_creative_package(snapshot, package_id)
        assert result["audience"] is None
        assert "PROPOSED HUMAN HANDOFF" in result["videoPrompt"]
        assert result["videoPrompt"] != result["imagePrompt"]
        assert "FAKE SOURCE" in result["videoPrompt"]
        assert result["fieldStatus"]["audience"] == "UNRESOLVED"
        assert result["fieldStatus"]["videoPrompt"] == "PROPOSED"
        assert "UNRESOLVED" in render_creative_package_text(result)


def test_explicit_fields_remain_verbatim_and_record_their_sources() -> None:
    snapshot = snapshot_fixture()
    snapshot["package"].update({
        "audience": "25-35 US alternative female",
        "video_prompt": "  Keep jersey fixed.\nTurn slowly.  ",
        "quality_checklist": ["Inspect garment print", "Inspect face"],
    })
    snapshot["plan"].update({
        "characterDNA": {"origin": "USER_CONFIRMED", "identity": {"age": "adult"}},
        "scene_dna": {"origin": "OBSERVED_REFERENCE", "evidence_refs": ["scene-1"]},
        "cameraDNA": {"origin": "PROPOSED", "position": "eye level"},
    })
    freeze_snapshot(snapshot)
    result = project_creative_package(snapshot)
    assert result["audience"] == snapshot["package"]["audience"]
    assert result["videoPrompt"] == snapshot["package"]["video_prompt"]
    assert result["qualityChecklist"] == snapshot["package"]["quality_checklist"]
    assert result["sceneDNA"] == snapshot["plan"]["scene_dna"]
    assert result["fieldStatus"]["sceneDNA"] == "PRESENT"
    assert result["provenance"]["originEvidence"]["fieldSources"]["sceneDNA"] == (
        "plan.scene_dna"
    )


def test_projection_and_mutable_exports_are_detached_from_snapshot() -> None:
    snapshot = snapshot_fixture()
    before = deepcopy(snapshot)
    result = project_creative_package(snapshot)
    serialize_creative_package(result)
    render_creative_package_text(result)
    assert snapshot == before
    result["provenance"]["sourcePackage"]["reality"][0]["decision"] = "changed"
    result["shotPlan"][0]["sourcePackage"]["prompt"] = "changed"
    result["direction"]["scene"] = "changed"
    assert snapshot == before


def test_json_and_text_are_stable_with_unicode_newlines_and_different_key_order() -> None:
    snapshot = snapshot_fixture()
    snapshot["package"] = compile_package(
        uuid.UUID("00000000-0000-0000-0000-000000000001"),
        snapshot["plan"], digest(snapshot["plan"]["locks"]), 2,
        fix="\nPreserve jersey \u7403\u8863.  ",
    ).model_dump(mode="json")
    freeze_snapshot(snapshot)
    reversed_snapshot = {
        key: value for key, value in reversed(list(snapshot.items()))
    }
    first = project_creative_package(snapshot)
    second = project_creative_package(reversed_snapshot)
    serialized = serialize_creative_package(first)
    assert serialized == serialize_creative_package(second)
    assert serialized == serialize_creative_package(json.loads(serialized))
    assert json.loads(serialized)["imagePrompt"] == snapshot["package"]["prompt"]
    assert render_creative_package_text(first) == render_creative_package_text(second)
    assert snapshot["package"]["prompt"] in render_creative_package_text(first)
    assert snapshot["package"]["preservation_hash"] in render_creative_package_text(first)
    assert "FAKE" in render_creative_package_text(first)


def test_explicit_shot_order_and_package_selection_survive_collection_reordering() -> None:
    snapshot = snapshot_fixture()
    shot_one = snapshot["storyboard"]["packages"]["SHOT_01"]
    shot_two = {
        **deepcopy(shot_one), "shot_id": "SHOT_02", "package_id": "package-shot-02",
        "revision": 4, "prompt": "FAKE ONLY. Second explicit shot.",
    }
    snapshot["storyboard"]["packages"] = [shot_one, shot_two]
    snapshot["storyboard"]["shot_order"] = ["SHOT_02", "SHOT_01"]
    first = project_creative_package(snapshot, shot_one["package_id"])
    snapshot["storyboard"]["packages"].reverse()
    second = project_creative_package(snapshot, shot_one["package_id"])
    assert serialize_creative_package(first) == serialize_creative_package(second)
    assert [item["shotId"] for item in first["shotPlan"]] == ["FIRST_FRAME", "SHOT_01"]
    assert "SHOT_02" not in serialize_creative_package(first)
    assert first["provenance"]["shotId"] == "SHOT_01"
    assert first["imagePrompt"] == shot_one["prompt"]
    assert first["fieldStatus"]["videoPrompt"] == "PROPOSED"


@pytest.mark.parametrize("change", [
    "missing_package", "missing_shot", "wrong_root_shot", "wrong_key",
    "duplicate_package", "duplicate_shot",
    "invalid_revision", "missing_prompt", "conflicting_prompt", "unknown_direction",
    "conflicting_alias",
])
def test_invalid_identity_or_contract_fails_without_mutating_snapshot(change: str) -> None:
    snapshot = snapshot_fixture()
    storyboard = snapshot["storyboard"]
    shot = storyboard["packages"]["SHOT_01"]
    package_id = None
    if change == "missing_package":
        package_id = "does-not-exist"
    elif change == "missing_shot":
        del shot["shot_id"]
    elif change == "wrong_root_shot":
        snapshot["package"]["shot_id"] = "SHOT_01"
    elif change == "wrong_key":
        shot["shot_id"] = "SHOT_02"
    elif change == "duplicate_package":
        shot["package_id"] = snapshot["package"]["package_id"]
    elif change == "duplicate_shot":
        storyboard["packages"] = [shot, deepcopy(shot)]
    elif change == "invalid_revision":
        snapshot["package"]["revision"] = True
    elif change == "missing_prompt":
        snapshot["package"]["prompt"] = ""
    elif change == "conflicting_prompt":
        snapshot["package"]["imagePrompt"] = "replacement"
    elif change == "unknown_direction":
        snapshot["plan"]["selected_direction"] = "C"
    else:
        snapshot["package"].update(videoPrompt="first", video_prompt="second")
    before = deepcopy(snapshot)
    with pytest.raises((ValueError, TypeError)):
        project_creative_package(snapshot, package_id)
    assert snapshot == before


@pytest.mark.parametrize("value", [float("nan"), float("inf"), object(), {1, 2}])
def test_non_json_input_is_controlled_failure(value: object) -> None:
    snapshot = snapshot_fixture()
    snapshot["package"]["extra_evidence"] = value
    with pytest.raises((ValueError, TypeError)):
        project_creative_package(snapshot)


def test_legacy_contract_pointer_is_bound_by_package_id_not_current_position() -> None:
    snapshot = snapshot_fixture()
    contracts = snapshot.pop("package_contracts")
    shot = snapshot["storyboard"]["packages"]["SHOT_01"]
    snapshot.update(contracts[shot["package_id"]])
    with pytest.raises(ValueError, match="frozen text contract required"):
        project_creative_package(snapshot)
    with pytest.raises(ValueError, match="frozen text contract required"):
        project_creative_package(snapshot, shot["package_id"])
    root_id = snapshot["package"]["package_id"]
    snapshot["package_contracts"] = {root_id: contracts[root_id]}
    second = project_creative_package(snapshot, shot["package_id"])
    assert second["provenance"]["originEvidence"]["packageContract"] == (
        contracts[shot["package_id"]]
    )


def test_export_never_upgrades_fake_review_or_claims_provider_success() -> None:
    snapshot = snapshot_fixture()
    snapshot["latest_review"] = {
        "decision": "QUALIFIED", "qualification_scope": "OFFLINE_SYNTHETIC_ONLY",
    }
    snapshot["qualified"] = True
    snapshot["deliverable"] = True
    snapshot["provider_submission_allowed"] = True
    provenance = project_creative_package(snapshot)["provenance"]
    assert provenance["qualified"] is False
    assert provenance["deliverable"] is False
    assert provenance["providerSubmissionAllowed"] is False
    assert "providerStatus" not in provenance


def test_missing_dna_is_unresolved_and_does_not_invent_an_identity() -> None:
    snapshot = snapshot_fixture()
    snapshot["plan"]["directions"] = [{"id": "B", "title": "Only a title"}]
    freeze_snapshot(snapshot)
    result = project_creative_package(snapshot)
    for field in ("characterDNA", "sceneDNA", "videoPrompt"):
        assert result[field] is None
        assert result["fieldStatus"][field] == "UNRESOLVED"
    assert result["cameraDNA"]["description"] == snapshot["package"]["reality"][0]["decision"]
    assert result["fieldStatus"]["cameraDNA"] == "PROPOSED"


def test_proposed_handoff_uses_frozen_behavior_and_does_not_invent_person_facts() -> None:
    snapshot = snapshot_fixture()
    del snapshot["plan"]["directions"][1]["human"]
    del snapshot["plan"]["directions"][1]["camera"]
    freeze_snapshot(snapshot)
    before = deepcopy(snapshot)
    result = project_creative_package(snapshot)
    assert result["characterDNA"] == {
        "behavior": "check jersey", "identity": None, "appearance": None, "origin": "PROPOSED",
    }
    assert result["fieldStatus"]["characterDNA"] == "PROPOSED"
    assert result["cameraDNA"]["description"] == snapshot["package"]["reality"][0]["decision"]
    assert snapshot["plan"]["source_hash"] in result["videoPrompt"]
    assert result["imagePrompt"] == snapshot["package"]["prompt"]
    assert snapshot == before


@pytest.mark.parametrize("target", [
    "prompt", "facts", "locks", "registry", "reality", "frozen_hash",
    "stored_registry", "missing_contract", "asset_hash",
])
def test_tampered_current_package_cannot_export(target: str) -> None:
    snapshot = snapshot_fixture()
    if target == "prompt":
        snapshot["package"]["prompt"] = "tampered"
    elif target == "facts":
        snapshot["facts_snapshot"]["truth_fields"]["front_color"] = "red"
    elif target == "locks":
        snapshot["plan"]["locks"]["user_locks"]["selected_direction"] = "A"
    elif target == "registry":
        snapshot["registry_snapshot"]["payload_json"]["prompt"] = "tampered"
    elif target == "reality":
        snapshot["package"]["reality"][0]["decision"] = "tampered"
    elif target == "frozen_hash":
        snapshot["package_contracts"][snapshot["package"]["package_id"]][
            "text_contract"
        ]["contract_hash"] = "0" * 64
    elif target == "stored_registry":
        snapshot["package_contracts"][snapshot["package"]["package_id"]][
            "registry_snapshot"
        ]["payload_json"]["prompt"] = "tampered"
    elif target == "asset_hash":
        snapshot["asset"]["sha256"] = "b" * 64
    else:
        del snapshot["package_contracts"]
        del snapshot["text_contract"]
    with pytest.raises((ValueError, TypeError)):
        project_creative_package(snapshot)


def test_historical_package_uses_original_frozen_plan_facts_and_parent_chain() -> None:
    snapshot = snapshot_fixture()
    old_package = deepcopy(snapshot["package"])
    old_contracts = deepcopy(snapshot["package_contracts"])
    snapshot["plan"]["selected_direction"] = "A"
    snapshot["plan"]["locks"]["user_locks"]["selected_direction"] = "A"
    snapshot["facts_snapshot"]["truth_fields"]["front_color"] = "red"
    snapshot["facts_snapshot"]["source_hash"] = "b" * 64
    snapshot["plan"]["source_hash"] = "b" * 64
    snapshot["plan"]["locks"]["source_hash"] = "b" * 64
    snapshot["plan"]["facts_snapshot_hash"] = digest(snapshot["facts_snapshot"])
    snapshot["asset"]["sha256"] = "b" * 64
    snapshot["package"] = compile_package(
        uuid.UUID("00000000-0000-0000-0000-000000000001"),
        snapshot["plan"], digest(snapshot["plan"]["locks"]), 3,
        parent=old_package["package_id"],
    ).model_dump(mode="json")
    snapshot["storyboard"]["packages"] = {}
    freeze_snapshot(snapshot)
    snapshot["package_contracts"].update(old_contracts)
    result = project_creative_package(snapshot, old_package["package_id"])
    assert result["imagePrompt"] == old_package["prompt"]
    assert result["direction"]["id"] == "B"
    assert result["provenance"]["productFacts"]["truth_fields"]["front_color"] == "black"
    assert result["provenance"]["sourceHash"] == "a" * 64
    assert result["provenance"]["sourceAssets"] == []
    assert [item["packageId"] for item in result["shotPlan"]] == [old_package["package_id"]]
    assert snapshot["package"]["package_id"] not in serialize_creative_package(result)


def test_unfrozen_intelligence_does_not_enter_export() -> None:
    snapshot = snapshot_fixture()
    snapshot["intelligence_snapshot"] = {
        "audience": "invented audience", "videoPrompt": "invented video",
        "characterDNA": {"origin": "USER_CONFIRMED", "identity": "invented identity"},
    }
    serialized = serialize_creative_package(project_creative_package(snapshot))
    assert "invented" not in serialized


def test_last_storyboard_registry_pointer_does_not_replace_root_evidence() -> None:
    snapshot = snapshot_fixture()
    shot = snapshot["storyboard"]["packages"]["SHOT_01"]
    snapshot.update(deepcopy(snapshot["package_contracts"][shot["package_id"]]))
    result = project_creative_package(snapshot)
    assert result["provenance"]["originEvidence"]["packageContract"] == (
        snapshot["package_contracts"][snapshot["package"]["package_id"]]
    )
    assert result["videoPrompt"] != shot["prompt"]
    assert result["fieldStatus"]["videoPrompt"] == "PROPOSED"
