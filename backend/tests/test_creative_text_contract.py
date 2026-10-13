from __future__ import annotations

import uuid
from copy import deepcopy

import pytest
from libtv_agent.creative.text_contract import (
    REALITY_ORDER,
    canonical_hash,
    freeze_text_contract,
    validate_text_contract,
)
from libtv_agent.creative.workflow import PlanRevision, compile_package, digest


def fixture():
    facts = {
        "facts_revision": 2, "product_id": "product-1", "product_version_id": "version-2",
        "source_asset_references": [{"object_key": "front", "sha256": "a" * 64}],
        "front_color": "red",
    }
    locks = {
        "product_id": "product-1", "source_hash": "a" * 64,
        "user_locks": {"brand": "generic", "character": "locked-person"},
    }
    plan = {
        "facts_revision": 2, "facts_snapshot_hash": digest(facts),
        "product_id": "product-1", "product_version_id": "version-2",
        "source_hash": "a" * 64, "locks": locks, "selected_direction": "A",
        "claims": [{
            "claim_id": "front", "value": "front image available",
            "source_fact_keys": ["source_asset_references"], "facts_revision": 2,
            "confidence_basis": "source image and upload record",
        }],
    }
    package = {
        "package_id": "package-1", "revision": 2, "facts_revision": 2,
        "shot_id": "FIRST_FRAME", "locks_hash": digest(locks),
        "prompt": "Preserve the canonical product.",
        "reality": [
            {"dimension": dimension,
             "decision": "none" if dimension == "Imperfection" else f"{dimension} decision"}
            for dimension in REALITY_ORDER
        ],
    }
    manifest = {"ruleset": "creative.v2", "rules": ["preserve product"]}
    registry = {
        "prompt_key": "creative.prompt", "version": 2, "content_hash": digest(package["prompt"]),
        "payload_json": {
            "package_id": package["package_id"], "prompt": package["prompt"],
            "manifest": manifest, "manifest_hash": digest(manifest),
        },
    }
    return plan, package, registry, facts


def validate(plan, package, registry, facts, frozen=None):
    return validate_text_contract(
        plan,
        package,
        frozen or freeze_text_contract(plan, package, registry, facts),
        registry,
        facts,
    )


def codes(result):
    return {item["code"] for item in result["failures"]}


def test_revision_two_complete_static_contract_and_boundary():
    result = validate(*fixture())
    assert result["valid"] and result["status"] == "static_rule_validated"
    assert set(result["boundary"].values()) == {"unverified"}


@pytest.mark.parametrize("target", [
    "facts", "plan_revision", "package_revision", "claim_revision", "product_id", "source",
    "product_lock", "user_lock", "opaque_lock", "reality", "prompt", "package_id",
    "registry_version", "registry_identity", "registry_hash", "registry_body", "registry_manifest",
])
def test_actual_identity_changes_rejected_even_with_recomputed_mutable_hash(target):
    plan, package, registry, facts = fixture()
    frozen = freeze_text_contract(plan, package, registry, facts)
    if target == "facts":
        facts["front_color"] = "blue"
        plan["facts_snapshot_hash"] = digest(facts)
    elif target == "plan_revision":
        plan["facts_revision"] = 3
    elif target == "package_revision":
        package["facts_revision"] = 3
    elif target == "claim_revision":
        plan["claims"][0]["facts_revision"] = 3
    elif target == "product_id":
        plan["product_id"] = "other"
    elif target == "source":
        plan["source_hash"] = "c" * 64
    elif target in {"product_lock", "user_lock"}:
        if target == "product_lock":
            plan["locks"]["product_id"] = "other"
        else:
            plan["locks"]["user_locks"]["character"] = "other"
        package["locks_hash"] = digest(plan["locks"])
    elif target == "opaque_lock":
        package["locks_hash"] = "c" * 64
    elif target == "reality":
        package["reality"][0]["decision"] = "changed"
    elif target in {"prompt", "package_id"}:
        package[target] = "changed"
    elif target == "registry_version":
        registry["version"] = 3
    elif target == "registry_identity":
        registry["prompt_key"] = "other"
    elif target == "registry_hash":
        registry["content_hash"] = "c" * 64
    elif target == "registry_body":
        registry["payload_json"]["prompt"] = "changed"
        registry["content_hash"] = digest("changed")
    elif target == "registry_manifest":
        registry["payload_json"]["manifest"]["rules"] = ["other"]
        registry["payload_json"]["manifest_hash"] = digest(registry["payload_json"]["manifest"])
    result = validate(plan, package, registry, facts, frozen)
    assert result["status"] == "rejected"
    assert any(code.startswith("FROZEN_") for code in codes(result))
    package["preservation_hash"] = canonical_hash(package)
    result = validate(plan, package, registry, facts, frozen)
    assert result["status"] == "rejected"
    assert "FROZEN_PACKAGE" in codes(result)


@pytest.mark.parametrize("key,basis", [
    (["missing"], "source"), ([], "source"), (["front_color"], ""),
    (["front_color"], "   "), (["source_asset_references"], None), ("front_color", "source"),
])
def test_wrong_fact_keys_and_empty_basis(key, basis):
    plan, package, registry, facts = fixture()
    plan["claims"][0].update(source_fact_keys=key, confidence_basis=basis)
    assert validate(plan, package, registry, facts)["status"] == "rejected"


def test_empty_fact_value_is_not_evidence():
    plan, package, registry, facts = fixture()
    facts["source_asset_references"] = []
    plan["facts_snapshot_hash"] = digest(facts)
    assert "CLAIM_SOURCE_KEYS" in codes(validate(plan, package, registry, facts))


@pytest.mark.parametrize("owner", ["plan", "package", "claim"])
def test_inconsistent_revisions_rejected_at_compile_gate(owner):
    plan, package, registry, facts = fixture()
    target = {"plan": plan, "package": package, "claim": plan["claims"][0]}[owner]
    target["facts_revision"] = 1
    assert validate(plan, package, registry, facts)["status"] == "rejected"


@pytest.mark.parametrize("kind", ["missing", "reordered", "duplicate", "empty", "na"])
def test_actual_reality_rules_without_reconstructed_decisions(kind):
    plan, package, registry, facts = fixture()
    if kind == "missing":
        package["reality"].pop()
    elif kind == "reordered":
        package["reality"].reverse()
    elif kind == "duplicate":
        package["reality"][1] = deepcopy(package["reality"][0])
    elif kind == "empty":
        package["reality"][0]["decision"] = ""
    else:
        package["reality"][4]["decision"] = "N/A"
    assert validate(plan, package, registry, facts)["status"] == "rejected"


def test_na_reason_and_imperfection_none_are_legal():
    plan, package, registry, facts = fixture()
    package["reality"][4].update(decision="N/A", reason="isolated product has no environment")
    assert package["reality"][5]["decision"] == "none"
    assert validate(plan, package, registry, facts)["valid"]


def test_hash_covers_actual_fact_content_and_legacy_digest_encoding():
    assert canonical_hash({"label": "\u670d\u88c5", "items": [2, 1]}) == digest({
        "items": [2, 1], "label": "\u670d\u88c5",
    })
    plan, package, registry, facts = fixture()
    facts["facts_snapshot_hash"] = plan["facts_snapshot_hash"]
    assert "FACTS_SNAPSHOT_HASH" in codes(validate(plan, package, registry, facts))


@pytest.mark.parametrize("missing", ["prompt", "manifest"])
def test_legacy_registry_cannot_fake_complete_version_proof(missing):
    plan, package, registry, facts = fixture()
    registry["payload_json"].pop(missing)
    result = validate(plan, package, registry, facts)
    assert result["status"] == "unverified" and not result["valid"]


def test_frozen_context_and_function_inputs_are_not_mutated():
    values = fixture()
    frozen = freeze_text_contract(*values)
    before = deepcopy((values, frozen))
    validate(*values, frozen)
    assert (values, frozen) == before
    values[1]["prompt"] = "later"
    assert frozen["package"]["prompt"] != values[1]["prompt"]


def test_frozen_hash_corruption_rejected():
    plan, package, registry, facts = fixture()
    frozen = freeze_text_contract(plan, package, registry, facts)
    frozen["contract_hash"] = "0" * 64
    assert "FROZEN_RECORD_HASH" in codes(validate(plan, package, registry, facts, frozen))


def test_bare_frozen_package_rejects_modified_prompt_and_self_hash():
    plan, package, registry, facts = fixture()
    frozen = deepcopy(package)
    package["prompt"] = "modified"
    package["preservation_hash"] = canonical_hash(package)
    assert "FROZEN_PACKAGE" in codes(validate(plan, package, registry, facts, frozen))


def test_existing_plan_package_and_registry_shape_is_adapted_but_unproven():
    facts = {
        "product_id": str(uuid.uuid4()), "product_version_id": str(uuid.uuid4()),
        "facts_revision": 2, "source_asset_references": ["front.png"],
    }
    plan = PlanRevision(
        revision=2, facts_revision=2, product_id=uuid.UUID(facts["product_id"]),
        product_version_id=uuid.UUID(facts["product_version_id"]),
        source_hash="a" * 64, facts_snapshot_hash=digest(facts),
        directions=[{"id": "A", "scene": "studio", "behavior": "standing"}],
        selected_direction="A", claims=[{
            "claim_id": "front", "value": "front image available",
            "source_fact_keys": ["source_asset_references"], "facts_revision": 2,
            "evidence_kind": "OBSERVED_REFERENCE", "confidence_basis": "source",
            "unknown_or_assumption": "back not observed",
        }],
    )
    package = compile_package(uuid.uuid4(), plan.model_dump(mode="json"), "b" * 64, 1)
    registry = {
        "prompt_key": "legacy", "version": 1, "content_hash": digest(package.prompt),
        "payload_json": {"package_id": package.package_id, "ruleset_version": package.ruleset},
    }
    result = validate_text_contract(plan, package, package, registry, facts)
    assert not result["failures"]
    assert result["status"] == "unverified"
    assert {"FROZEN_CONTEXT_MISSING", "REGISTRY_BODY_MISSING", "REGISTRY_MANIFEST_MISSING"} \
        <= {item["code"] for item in result["unverified"]}


@pytest.mark.parametrize("malformed", [None, [], {"reality": 1}])
def test_malformed_input_returns_structured_rejection(malformed):
    plan, _, registry, facts = fixture()
    result = validate_text_contract(plan, malformed, {}, registry, facts)
    assert result["status"] == "rejected"
