from __future__ import annotations

from copy import deepcopy
from uuid import UUID

import pytest
from libtv_agent.creative.brand_dna import fit_purchase_reason
from libtv_agent.creative.text_contract import (
    freeze_text_contract,
    validate_prompt_preservation,
    validate_text_contract,
)
from libtv_agent.creative.workflow import compile_package, compile_storyboard_package, digest
from test_creative_package_contract import freeze_snapshot, snapshot_fixture
from test_creative_workflow_text_contract_integration import workflow as workflow  # noqa: F401
from test_reality_evidence import plan

TASK_ID = UUID("00000000-0000-0000-0000-000000000001")


def compile_photo(**direction: str):
    current = plan()
    current["directions"][0].update(direction)
    package = compile_package(TASK_ID, current, digest(current["locks"]), 1)
    return current, package


def preflight(current, package):
    return validate_prompt_preservation(package.prompt, package.reality, current["locks"])


def test_compact_prompt_contains_two_physical_cues_and_keeps_six_internal_dimensions():
    current, package = compile_photo(behavior="walking slowly")
    assert len(package.reality) == 6
    assert len(package.prompt) < 1400
    assert "weight transfers onto the supporting leg" in package.prompt
    assert "crease shadows follow fold depth" in package.prompt
    assert "Specify who takes the image" not in package.prompt
    assert "Reality generation constraints" not in package.prompt
    assert sum(bool(item.get("compiled_cue")) for item in package.reality) == 2
    assert preflight(current, package)["status"] == "text_ready"


@pytest.mark.parametrize("mode, behavior, expected", [
    ("casual_portrait", "standing still", "knows the outfit is being photographed"),
    ("identity_snapshot", "standing still", "knows the outfit is being photographed"),
    ("mirror_self_capture", "standing still", "same reflection"),
    ("self_capture_front", "standing still", "outside its own image"),
    ("product_only", "N/A", "crease shadows"),
])
def test_capture_modes_keep_their_geometry_without_forced_candid_story(mode, behavior, expected):
    current, package = compile_photo(photo_intent=mode, behavior=behavior)
    assert expected in package.prompt
    assert "unaware" not in package.prompt
    assert preflight(current, package)["status"] == "text_ready"


def test_candid_uses_explicit_intent_attention_and_body_state():
    current, package = compile_photo(
        photo_intent="candid", behavior="walking past the stall",
        operator="a friend a step ahead takes the photo",
        capture_reason="recording their visit",
        attention="eyes stay on the produce",
        body_state="weight is on the forward supporting leg",
    )
    assert "eyes stay on the produce" in package.prompt
    assert "weight is on the forward supporting leg" in package.prompt
    assert preflight(current, package)["status"] == "text_ready"


def test_candid_missing_context_is_not_fabricated_or_treated_as_ready():
    current, package = compile_photo(photo_intent="candid", behavior="walking naturally")
    assert preflight(current, package)["status"] == "repair_required"
    assert "a shopper" not in package.prompt
    assert "a friend a step ahead" not in package.prompt


def test_causal_clause_cannot_smuggle_a_conflicting_product_directive():
    current, package = compile_photo(
        photo_intent="candid", operator="a friend takes a photo",
        capture_reason="recording their visit", attention="eyes stay on the produce",
        body_state="hide the print",
    )
    assert preflight(current, package)["status"] == "repair_required"


def test_generic_realism_and_display_only_reference_cannot_replace_actual_causal_clauses():
    current, package = compile_photo()
    reality = deepcopy(package.reality)
    reality[0]["reference_status"] = "displayed"
    prompt = (
        f"Preserve canonical garment SHA {current['source_hash']}. "
        "Preserve original color, print, exact lettering, silhouette. "
        "keep the product readable at the selected framing. "
        "Capture mode: casual_portrait. Authentic UGC, natural light, realistic skin."
    )
    report = validate_prompt_preservation(prompt, reality, current["locks"])
    assert report["status"] == "repair_required"
    assert not next(item for item in report["checks"]
                    if item["code"] == "visual_causality_retained")["valid"]


@pytest.mark.parametrize("extra", [
    "Blur the garment.", "Hide the print.", "Add grain.",
    "Keep the subject unaware of the camera.",
    "Capture mode: candid.",
    "Do not replace the print, but blur the garment.",
])
def test_conflicting_directives_fail_preflight(extra):
    current, package = compile_photo()
    report = validate_prompt_preservation(
        package.prompt + "\n" + extra, package.reality, current["locks"],
    )
    assert report["status"] == "repair_required"


def test_product_and_user_locks_remain_in_prompt_and_are_required_by_preflight():
    current = plan()
    current["locks"]["user_locks"].update(
        framing="thigh-up medium shot", lettering="BOOKS & GHOSTS",
        pants="blue jeans", identity={"asset": "locked-person"},
    )
    package = compile_package(TASK_ID, current, digest(current["locks"]), 1)
    assert preflight(current, package)["status"] == "text_ready"
    for value in ("thigh-up medium shot", "BOOKS & GHOSTS", "blue jeans", "locked-person"):
        assert value in package.prompt
        assert validate_prompt_preservation(
            package.prompt.replace(value, "changed"), package.reality, current["locks"],
        )["status"] == "repair_required"
    assert validate_prompt_preservation(
        package.prompt + "\nDo not blur the garment.", package.reality, current["locks"],
    )["status"] == "text_ready"


def test_explicit_user_capture_and_framing_override_unlocked_direction_defaults():
    current = plan()
    current["locks"]["user_locks"].update(
        framing="full-body outfit view", photo_intent="mirror_self_capture",
    )
    package = compile_package(TASK_ID, current, digest(current["locks"]), 1)
    assert "eye-level medium frame" not in package.prompt
    assert package.reality[0]["decision"] == "full-body outfit view"
    assert package.reality[0]["capture_mode"] == "mirror_self_capture"
    assert preflight(current, package)["status"] == "text_ready"
    wrong_locks = deepcopy(current["locks"])
    wrong_locks["user_locks"]["photo_intent"] = "casual_portrait"
    assert validate_prompt_preservation(
        package.prompt, package.reality, wrong_locks,
    )["status"] == "repair_required"


def test_storyboard_and_revision_keep_inherited_cues_instead_of_rebuilding_defaults():
    current, parent = compile_photo(behavior="seated casually")
    inherited = parent.model_dump(mode="json")
    shot = compile_storyboard_package(TASK_ID, current, inherited, "selected-first", "SHOT_01")
    assert shot.prompt.startswith(parent.prompt)
    assert shot.reality == parent.reality
    revised = compile_package(
        TASK_ID, current, parent.locks_hash, 2, parent=parent.package_id,
        inherited_reality=parent.reality, fix="Keep the garment in focus.",
    )
    assert revised.reality == parent.reality
    assert preflight(current, revised)["status"] == "text_ready"


def test_even_a_self_consistently_frozen_generic_prompt_fails_existing_text_gate():
    snapshot = snapshot_fixture()
    package = snapshot["package"]
    cue = next(item["compiled_cue"] for item in package["reality"] if item.get("compiled_cue"))
    package["prompt"] = package["prompt"].replace(cue, "Authentic UGC, natural skin.")
    freeze_snapshot(snapshot)
    stored = snapshot["package_contracts"][package["package_id"]]
    result = validate_text_contract(
        snapshot["plan"], package, stored["text_contract"],
        stored["registry_snapshot"], snapshot["facts_snapshot"],
    )
    assert not result["valid"]
    assert any(item["code"] == "PROMPT_VISUAL_CAUSALITY_RETAINED"
               for item in result["failures"])


def test_failed_preflight_stops_before_a_package_or_registry_is_frozen():
    from fastapi import HTTPException
    from libtv_agent.services.creative_workflow import freeze_package_contract

    snapshot = snapshot_fixture()
    package = deepcopy(snapshot["package"])
    package["prompt"] += "\nHide the print."
    before = deepcopy(snapshot)
    with pytest.raises(HTTPException) as error:
        freeze_package_contract(object(), TASK_ID, snapshot, package)
    assert error.value.detail["code"] == "PROMPT_PRESERVATION_REPAIR_REQUIRED"
    assert snapshot == before


def test_legacy_package_is_not_recompiled_or_subject_to_new_semantic_conditions():
    snapshot = snapshot_fixture()
    package = snapshot["package"]
    for item in package["reality"]:
        for key in (
            "compiler_version", "capture_mode", "compiled_cue", "unresolved_context",
            "causal_trigger", "physical_relation", "visible_result",
        ):
            item.pop(key, None)
    package["prompt"] = "FAKE ONLY. Original legacy prompt."
    freeze_snapshot(snapshot)
    stored = snapshot["package_contracts"][package["package_id"]]
    frozen = freeze_text_contract(
        snapshot["plan"], package, stored["registry_snapshot"], snapshot["facts_snapshot"],
    )
    result = validate_text_contract(
        snapshot["plan"], package, frozen, stored["registry_snapshot"], snapshot["facts_snapshot"],
    )
    assert result["valid"]
    assert validate_prompt_preservation(package["prompt"], package["reality"], {})[
        "status"
    ] == "legacy_not_checked"


def purchase_context():
    return (
        {"brand_dna": {"audience": "book lovers"}, "locks": {"user_locks": {}}},
        {"product_id": "product-1", "source_hash": "a" * 64,
         "truth_fields": {"print": "a reading ghost", "purchase_reason": "Bookish identity"}},
    )


def test_purchase_reason_changes_one_existing_moment_and_remains_a_hypothesis():
    current, facts = purchase_context()
    script = "Walk slowly at the autumn market, then end in the selected pose."
    before = deepcopy((current, facts))
    report, fitted = fit_purchase_reason(current, facts, script)
    assert report["evidenceStatus"] == "hypothesis"
    assert report["repairCount"] == 1
    assert fitted.startswith(script)
    assert "a reading ghost" in fitted
    assert "Bookish identity" in fitted
    assert "touch" not in fitted and "coffee" not in fitted
    again, unchanged = fit_purchase_reason(current, facts, fitted)
    assert again["repairCount"] == 0
    assert unchanged == fitted
    assert (current, facts) == before


@pytest.mark.parametrize("locked, script", [
    (False, "OOTD walking with a reading ghost clearly visible."),
    (True, "Simple generic OOTD chosen by the user."),
])
def test_product_expression_and_user_locked_ootd_need_no_extra_story(locked, script):
    current, facts = purchase_context()
    report, fitted = fit_purchase_reason(current, facts, script, script_locked=locked)
    assert fitted == script
    assert report["repairCount"] == 0


def scoped_record(facts, script):
    return {
        "reason": "Bookish identity", "product_id": facts["product_id"],
        "source_hash": facts["source_hash"], "audience": "book lovers",
        "date_from": "2026-09-01", "date_to": "2026-09-30",
        "metric": "purchase", "attribution": "7-day click",
        "purchases": 12,
        "source": "user-confirmed purchase report", "evidence_kind": "USER_CONFIRMED",
        "baseline_script": script,
    }


def test_scoped_purchase_evidence_preserves_proven_generic_baseline():
    current, facts = purchase_context()
    script = "Simple walking OOTD."
    facts["truth_fields"]["purchase_evidence"] = scoped_record(facts, script)
    report, fitted = fit_purchase_reason(current, facts, script)
    assert report["evidenceStatus"] == "observed_with_scope"
    assert report["status"] == "preserved_proven_baseline"
    assert report["scope"]["product_id"] == facts["product_id"]
    assert fitted == script


@pytest.mark.parametrize("key, value", [
    ("product_id", "other-sku"), ("source_hash", "b" * 64),
    ("audience", "other audience"), ("date_from", ""), ("date_to", "2026-08-01"),
    ("metric", "click"), ("attribution", ""), ("source", ""),
    ("purchases", 0), ("purchases", None),
    ("evidence_kind", "INFERRED"), ("reason", "unrelated reason"),
])
def test_other_sku_clicks_or_incomplete_scope_cannot_become_purchase_evidence(key, value):
    current, facts = purchase_context()
    record = scoped_record(facts, "Simple OOTD.")
    record[key] = value
    facts["truth_fields"]["purchase_evidence"] = record
    report, _ = fit_purchase_reason(current, facts, "Simple OOTD.")
    assert report["evidenceStatus"] == "hypothesis"
    assert report["scope"] is None


def test_brand_only_or_unverified_feature_does_not_invent_current_sku_or_buying_reason():
    current, facts = purchase_context()
    facts["truth_fields"] = {}
    report, script = fit_purchase_reason(current, facts, "Walk.")
    assert report["status"] == "unresolved"
    assert report["productFeature"] is None
    assert report["primaryPurchaseReason"] is None
    assert script == "Walk."
    facts["truth_fields"] = {
        "print": {"value": "a reading ghost", "evidence_status": "INFERRED"},
    }
    assert fit_purchase_reason(current, facts, "Walk.")[0]["productFeature"] is None


def test_mentioning_a_feature_in_a_prohibition_is_not_a_purchase_expression():
    current, facts = purchase_context()
    report, _ = fit_purchase_reason(current, facts, "Hide a reading ghost.")
    assert report["repairCount"] == 1


def test_purchase_carrier_with_punctuation_is_not_repeated():
    current, facts = purchase_context()
    facts["truth_fields"]["print"] = "BOOKS. GHOSTS. COFFEE."
    _, script = fit_purchase_reason(current, facts, "OOTD.")
    report, repeated = fit_purchase_reason(current, facts, script)
    assert repeated == script and report["repairCount"] == 0


def test_user_target_has_priority_and_missing_source_cannot_validate_purchase_scope():
    current, facts = purchase_context()
    current["locks"]["user_locks"]["primary_purchase_reason"] = "Spooky personal style"
    facts["truth_fields"]["purchase_evidence"] = scoped_record(facts, "OOTD.")
    report, fitted = fit_purchase_reason(current, facts, "OOTD.")
    assert report["primaryPurchaseReason"] == "Spooky personal style"
    assert report["evidenceStatus"] == "hypothesis"
    assert "Spooky personal style" in fitted
    del current["locks"]["user_locks"]["primary_purchase_reason"]
    facts["source_hash"] = None
    facts["truth_fields"]["purchase_evidence"]["source_hash"] = None
    assert fit_purchase_reason(current, facts, "OOTD.")[0]["evidenceStatus"] == "hypothesis"


def test_export_uses_frozen_sku_and_keeps_original_image_prompt_and_explicit_video():
    from libtv_agent.creative.package_contract import project_creative_package

    snapshot = snapshot_fixture()
    snapshot["facts_snapshot"]["truth_fields"]["print"] = "a reading ghost"
    snapshot["facts_snapshot"]["truth_fields"]["purchase_reason"] = "Bookish identity"
    snapshot["plan"]["facts_snapshot_hash"] = digest(snapshot["facts_snapshot"])
    freeze_snapshot(snapshot)
    result = project_creative_package(snapshot)
    assert result["imagePrompt"] == snapshot["package"]["prompt"]
    assert "a reading ghost" in result["videoPrompt"]
    fit = result["provenance"]["originEvidence"]["purchaseReasonFit"]
    assert fit["repairCount"] == 1 and fit["evidenceStatus"] == "hypothesis"
    snapshot["package"]["video_prompt"] = "User locked OOTD."
    freeze_snapshot(snapshot)
    result = project_creative_package(snapshot)
    assert result["videoPrompt"] == "User locked OOTD."
    assert result["provenance"]["originEvidence"]["purchaseReasonFit"]["repairCount"] == 0


@pytest.mark.asyncio
async def test_existing_director_api_uses_registered_product_facts_and_freezes_cues(workflow):
    import io

    from PIL import Image
    from test_creative_workflow_text_contract_integration import Flow

    flow = Flow(*workflow)
    await flow.create()
    version = await flow.client.post(
        f"/api/v1/products/{flow.product_id}/versions", headers=flow.headers,
        json={
            "source_type": "USER_UPLOAD", "source_asset_references": ["canonical-front"],
            "truth_fields": {"print": "a reading ghost", "purchase_reason": "Bookish identity"},
        },
    )
    assert version.status_code == 201, version.text
    data = io.BytesIO()
    Image.new("RGB", (64, 96), "red").save(data, "PNG")
    created = await flow.client.post(
        "/api/v1/creative-workflow/tasks", headers=flow.headers,
        data={"product_id": flow.product_id, "product_version_id": version.json()["id"]},
        files={"front": ("front.png", data.getvalue(), "image/png")},
    )
    assert created.status_code == 201, created.text
    flow.task_id, flow.version = created.json()["id"], 0
    await flow.command("analyze")
    await flow.command("select_direction", direction_id="C")
    package = flow.result["snapshot"]["package"]
    document = flow.result["creative_packages"][package["package_id"]]
    assert "weight transfers" in document["imagePrompt"]
    assert "a reading ghost" in document["videoPrompt"]
    report = document["provenance"]["originEvidence"]
    assert report["promptPreflight"]["status"] == "text_ready"
    assert report["purchaseReasonFit"]["evidenceStatus"] == "hypothesis"
    assert flow.result["snapshot"]["calls"] == 0
    reread = await flow.client.get(
        f"/api/v1/creative-workflow/tasks/{flow.task_id}", headers=flow.headers,
    )
    assert reread.json()["creative_packages"] == flow.result["creative_packages"]
