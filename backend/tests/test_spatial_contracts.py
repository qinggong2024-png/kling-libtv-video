import json
from pathlib import Path

CONTRACTS = Path(__file__).parents[1] / "contracts"


def load_contract(name: str) -> dict:
    return json.loads((CONTRACTS / name).read_text(encoding="utf-8"))


def test_spatial_contracts_are_versioned_and_non_executable() -> None:
    expectations = {
        "spatial-dna.schema.json": "spatial-dna.v1",
        "depth-reference-contract.schema.json": "depth-reference.v1",
        "camera-relationship.schema.json": "camera-relationship.v1",
        "motion-reference-placeholder.schema.json": "motion-reference-placeholder.v1",
    }

    for filename, schema_version in expectations.items():
        schema = load_contract(filename)
        assert schema["properties"]["schemaVersion"]["const"] == schema_version

    for filename in ("spatial-dna.schema.json", "motion-reference-placeholder.schema.json"):
        properties = load_contract(filename)["properties"]
        assert properties["mode"]["const"] == "OFFLINE_SYNTHETIC_ONLY"
        assert properties["preflightStatus"]["const"] == "PREFLIGHT_REQUIRED"
        assert properties["providerSubmissionAllowed"]["const"] is False


def test_spatial_dna_references_only_planning_contracts() -> None:
    schema = load_contract("spatial-dna.schema.json")

    assert schema["properties"]["depthReferences"]["items"]["$ref"] == (
        "depth-reference-contract.schema.json"
    )
    assert schema["properties"]["cameraRelationships"]["items"]["$ref"] == (
        "camera-relationship.schema.json"
    )
