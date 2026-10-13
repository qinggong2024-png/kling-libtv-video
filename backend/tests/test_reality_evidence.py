from __future__ import annotations

from copy import deepcopy
from uuid import UUID

import pytest
from libtv_agent.creative.reality_evidence import (
    REALITY_ORDER,
    RULES_VERSION,
    compile_reality_decisions,
    evidence_rules_snapshot,
    registry_evidence_rules,
    render_reality_constraints,
)
from libtv_agent.creative.text_contract import freeze_text_contract, validate_text_contract
from libtv_agent.creative.workflow import compile_package, digest


def plan() -> dict:
    facts = {
        "product_id": "product-1",
        "product_version_id": "version-1",
        "facts_revision": 1,
        "source_hash": "a" * 64,
        "source_asset_references": ["front.png"],
    }
    return {
        "product_id": "product-1",
        "product_version_id": "version-1",
        "source_hash": "a" * 64,
        "facts_revision": 1,
        "facts_snapshot_hash": digest(facts),
        "locks": {
            "product_id": "product-1", "source_hash": "a" * 64,
            "user_locks": {"selected_direction": "A"},
        },
        "selected_direction": "A",
        "directions": [{
            "id": "A",
            "scene": "flea market",
            "behavior": "lean forward to read an old book",
            "camera": "a friend casually took this while walking nearby",
        }],
        "claims": [{
            "claim_id": "front",
            "value": "front image available",
            "source_fact_keys": ["source_asset_references"],
            "facts_revision": 1,
            "evidence_kind": "OBSERVED_REFERENCE",
            "confidence_basis": "source hash",
            "unknown_or_assumption": "back view not observed",
        }],
    }


def test_rules_are_versioned_and_preserve_the_six_dimension_order() -> None:
    snapshot = evidence_rules_snapshot()
    assert snapshot["schema_version"] == RULES_VERSION
    assert [rule["dimension"] for rule in snapshot["rules"]] == list(REALITY_ORDER)
    assert snapshot["content_hash"] == evidence_rules_snapshot()["content_hash"]

    reality = compile_reality_decisions(plan()["directions"][0])
    assert [item["dimension"] for item in reality] == list(REALITY_ORDER)
    assert reality[0]["decision"] == "a friend casually took this while walking nearby"
    assert reality[3]["required_context"] == (
        "identity, current_action, previous_moment, reason, attention, body_state"
    )
    assert "Do not add blur or grain" in reality[-1]["generation_constraint"]
    assert render_reality_constraints(reality).count("Camera:") == 1


def test_registry_snapshot_binds_rules_and_rejects_drift() -> None:
    reality = compile_reality_decisions(plan()["directions"][0])
    bound = registry_evidence_rules(reality)
    assert bound is not None
    changed = deepcopy(reality)
    changed[0]["rules_hash"] = "b" * 64
    with pytest.raises(ValueError, match="knowledge version"):
        registry_evidence_rules(changed)


def test_frozen_text_contract_requires_registry_rules_for_enriched_packages() -> None:
    task_id = UUID("00000000-0000-0000-0000-000000000001")
    current_plan = plan()
    package = compile_package(task_id, current_plan, digest(current_plan["locks"]), 1)
    package_dict = package.model_dump(mode="json")
    registry = {
        "prompt_key": "creative.fake:first-frame:FIRST_FRAME",
        "version": 1,
        "content_hash": digest(package.prompt),
        "payload_json": {
            "package_id": package.package_id,
            "prompt": package.prompt,
            "content_hash": digest(package.prompt),
            "manifest": {
                "ruleset": package.ruleset,
                "reality_order": list(REALITY_ORDER),
                "reality_evidence_rules": evidence_rules_snapshot(),
            },
        },
    }
    registry["payload_json"]["manifest_hash"] = digest(registry["payload_json"]["manifest"])
    frozen = freeze_text_contract(
        current_plan,
        package_dict,
        registry,
        {
            "product_id": "product-1",
            "product_version_id": "version-1",
            "facts_revision": 1,
            "source_hash": "a" * 64,
            "source_asset_references": ["front.png"],
        },
    )
    result = validate_text_contract(
        current_plan,
        package_dict,
        frozen,
        registry,
        frozen["facts_snapshot"],
    )
    assert result["valid"] is True

    registry["payload_json"]["manifest"].pop("reality_evidence_rules")
    result = validate_text_contract(
        current_plan,
        package_dict,
        frozen,
        registry,
        frozen["facts_snapshot"],
    )
    assert result["valid"] is False
    assert any(item["code"] == "REGISTRY_REALITY_RULES" for item in result["failures"])
