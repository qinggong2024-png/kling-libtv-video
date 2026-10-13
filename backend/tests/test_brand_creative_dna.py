from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from dataclasses import replace

import pytest
from libtv_agent.creative.brand_dna import project_brand_dna, validate_brand_dna
from libtv_agent.creative.text_contract import canonical_hash as contract_hash
from libtv_agent.creative.workflow import digest
from libtv_agent.templates.site_style_profiles import SITE_STYLE_PROFILES


def canonical_hash(value: object) -> str:
    serialized = json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False,
    )
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def test_builtin_dataclass_and_api_json_have_identical_verifiable_snapshots() -> None:
    for profile in SITE_STYLE_PROFILES.values():
        source = json.loads(json.dumps(profile.to_public_dict()))
        projected = project_brand_dna(profile)
        assert projected == project_brand_dna(source)
        assert validate_brand_dna(projected)
        assert projected["profileId"] == profile.id
        assert projected["profileVersion"] == profile.version
        assert projected["provenance"]["sourceProfile"] == source
        assert projected["provenance"]["sourceHash"] == canonical_hash(source)
        assert projected["provenance"]["sourceUrls"] == list(profile.source_urls)
        assert projected["characterDNA"]["identity"] is None
        body = {key: value for key, value in projected.items() if key != "contentHash"}
        assert projected["contentHash"] == canonical_hash(body)
        assert projected["contentHash"] == contract_hash(body) == digest(body)


def test_custom_configuration_maps_exact_fields_without_inventing_identity() -> None:
    source = {
        "id": "custom-dark", "version": "0.1.7", "name": "Custom Dark",
        "status": "draft", "libraryScope": "brand", "audience": "Alternative clothing fans",
        "tone": "dark street", "palette": ["black", "red"],
        "expressionLanguage": "natural expression", "expressionPool": ["neutral gaze"],
        "preferredEnvironment": ["bedroom mirror", "concert"],
        "cameraLanguage": "eye level", "cameraPool": ["fixed"],
        "preferredShots": ["medium"],
        "forbiddenMismatches": ["AI beauty"], "forbiddenMotion": ["fast spin"],
        "productPriorities": ["readable print"], "productRiskRules": ["no garment deformation"],
        "sourceUrls": ["https://example.invalid/style"], "retrievedAt": "2026-10-13",
        "evidenceLevel": "restricted_site", "identity": "must not become a character lock",
    }
    before = deepcopy(source)
    result = project_brand_dna(source)
    assert source == before
    assert set(result) == {
        "profileId", "profileVersion", "name", "audience", "visualDNA", "characterDNA",
        "sceneDNA", "cameraDNA", "avoid", "productConstraints", "provenance", "contentHash",
    }
    assert result["name"] == "Custom Dark"
    assert result["audience"] == source["audience"]
    assert result["visualDNA"] == {"tone": "dark street", "palette": ["black", "red"]}
    assert result["characterDNA"] == {
        "expressionLanguage": "natural expression", "expressionPool": ["neutral gaze"],
        "identity": None,
    }
    assert result["sceneDNA"] == {"preferredEnvironment": ["bedroom mirror", "concert"]}
    assert result["cameraDNA"] == {
        "language": "eye level", "pool": ["fixed"], "preferredShots": ["medium"],
    }
    assert result["avoid"] == {"mismatches": ["AI beauty"], "motion": ["fast spin"]}
    assert result["productConstraints"] == {
        "priorities": ["readable print"], "riskRules": ["no garment deformation"],
    }
    assert result["provenance"] == {
        "schemaVersion": "brand-dna.v1", "status": "draft", "libraryScope": "brand",
        "sourceUrls": source["sourceUrls"], "retrievedAt": "2026-10-13",
        "evidenceLevel": "restricted_site", "sourceProfile": source,
        "sourceHash": canonical_hash(source),
    }
    assert validate_brand_dna(result)


def test_unknown_id_and_missing_content_stay_unresolved_without_catalog_lookup() -> None:
    result = project_brand_dna({"id": "unknown-brand", "version": "unknown"})
    assert result["profileId"] == "unknown-brand"
    assert result["profileVersion"] == "unknown"
    assert result["name"] == ""
    assert result["audience"] is None
    assert result["visualDNA"] == {"tone": "", "palette": []}
    assert result["characterDNA"] == {
        "expressionLanguage": "", "expressionPool": [], "identity": None,
    }
    assert result["sceneDNA"] == {"preferredEnvironment": []}
    assert result["cameraDNA"] == {"language": "", "pool": [], "preferredShots": []}
    assert result["avoid"] == {"mismatches": [], "motion": []}
    assert result["productConstraints"] == {"priorities": [], "riskRules": []}
    assert result["provenance"]["status"] is None
    assert result["provenance"]["libraryScope"] is None
    assert result["provenance"]["sourceUrls"] == []
    assert result["provenance"]["retrievedAt"] is None
    assert result["provenance"]["evidenceLevel"] is None
    assert validate_brand_dna(result)
    explicit_empty = project_brand_dna({
        "id": "unknown-brand", "version": "unknown", "tone": None,
        "palette": None, "audience": "", "preferredEnvironment": None,
    })
    assert explicit_empty["visualDNA"] == result["visualDNA"]
    assert explicit_empty["sceneDNA"] == result["sceneDNA"]
    assert explicit_empty["audience"] == ""
    assert explicit_empty["provenance"]["sourceProfile"]["tone"] is None
    assert explicit_empty["contentHash"] != result["contentHash"]


def test_retired_and_general_sources_are_preserved_without_selection_policy() -> None:
    profile = next(iter(SITE_STYLE_PROFILES.values()))
    historical = replace(profile, status="retired", library_scope="general", brand_id=None)
    result = project_brand_dna(historical)
    assert result["provenance"]["status"] == "retired"
    assert result["provenance"]["libraryScope"] == "general"
    assert result["provenance"]["sourceProfile"]["brandId"] is None
    assert result["provenance"]["sourceUrls"] == list(profile.source_urls)
    assert result["provenance"]["evidenceLevel"] == profile.evidence_level
    assert validate_brand_dna(result)
    active = project_brand_dna(profile)
    assert active["contentHash"] != result["contentHash"]


def test_hash_is_order_stable_version_sensitive_and_snapshots_are_detached() -> None:
    source = next(iter(SITE_STYLE_PROFILES.values())).to_public_dict()
    first = project_brand_dna(source)
    second = project_brand_dna(dict(reversed(list(source.items()))))
    assert first == second
    revised = project_brand_dna({**source, "version": "new-version"})
    assert revised["profileVersion"] == "new-version"
    assert revised["provenance"]["sourceHash"] != first["provenance"]["sourceHash"]
    assert revised["contentHash"] != first["contentHash"]
    source["palette"] = ["changed"]
    source["sourceUrls"] = ["https://example.invalid/changed"]
    assert validate_brand_dna(first)
    assert first == second
    first["visualDNA"]["palette"].append("local mutation")
    assert "local mutation" not in first["provenance"]["sourceProfile"]["palette"]
    assert first != second
    assert validate_brand_dna(second)
    source_list = {
        "id": "custom", "version": "1", "palette": ["original"],
        "sourceUrls": ["https://example.invalid/original"],
    }
    detached = project_brand_dna(source_list)
    source_list["palette"].append("later")
    source_list["sourceUrls"].clear()
    assert detached["visualDNA"]["palette"] == ["original"]
    assert detached["provenance"]["sourceUrls"] == ["https://example.invalid/original"]
    assert validate_brand_dna(detached)


@pytest.mark.parametrize("target", [
    "audience", "version", "scene", "source", "source_hash", "schema", "content_hash",
])
def test_hash_tampering_is_rejected_without_mutating_snapshot(target: str) -> None:
    snapshot = project_brand_dna(next(iter(SITE_STYLE_PROFILES.values())))
    if target == "audience":
        snapshot["audience"] = "changed"
    elif target == "version":
        snapshot["profileVersion"] = "changed"
    elif target == "scene":
        snapshot["sceneDNA"]["preferredEnvironment"].append("changed")
    elif target == "source":
        snapshot["provenance"]["sourceProfile"]["tone"] = "changed"
    elif target == "source_hash":
        snapshot["provenance"]["sourceHash"] = "0" * 64
    elif target == "schema":
        snapshot["provenance"]["schemaVersion"] = "brand-dna.v2"
    else:
        snapshot["contentHash"] = "0" * 64
    before = deepcopy(snapshot)
    assert validate_brand_dna(snapshot) is False
    assert snapshot == before


@pytest.mark.parametrize("profile", [
    None, "unknown-brand", {}, {"id": "custom"}, {"id": "", "version": "1"},
    {"id": "custom", "version": " "}, {"id": "custom", "version": 1},
    {"id": "custom", "version": "1", "palette": "black"},
    {"id": "custom", "version": "1", "audience": 42},
    {"id": "custom", "version": "1", "sourceUrls": [42]},
    {"id": "custom", "version": "1", "tone": {"text": "unknown"}},
    {"id": "custom", "version": "1", "extra": float("nan")},
    {"id": "custom", "version": "1", "extra": object()},
])
def test_invalid_source_fails_instead_of_coercing_or_looking_up(profile: object) -> None:
    with pytest.raises((TypeError, ValueError)):
        project_brand_dna(profile)


@pytest.mark.parametrize("snapshot", [
    None, {}, {"contentHash": "x" * 64}, {"contentHash": "\N{SNOWMAN}" * 64},
    {"contentHash": "0" * 64, "provenance": None},
    {
        "contentHash": "0" * 64, "provenance": {"schemaVersion": "brand-dna.v1"},
        "invalid": float("nan"),
    },
])
def test_validation_returns_false_for_malformed_snapshots(snapshot: object) -> None:
    assert validate_brand_dna(snapshot) is False
