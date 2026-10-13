import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from libtv_agent.creative.handoff import CreativeHandoffManifest


def valid_payload() -> dict:
    return json.loads(
        (Path(__file__).parent / "fixtures" / "creative-handoff.v1.json").read_text(
            encoding="utf-8"
        )
    )


def test_accepts_approved_handoff_and_serializes_stable_contract():
    manifest = CreativeHandoffManifest.model_validate(valid_payload())
    assert manifest.schema_version == "creative-handoff.v1"
    assert manifest.shots[0].asset_id == "asset-001"
    assert manifest.model_dump(mode="json")["product"]["product_version"] == 3


@pytest.mark.parametrize(
    ("change", "message"),
    [
        (
            lambda value: value["assets"][0]["approval"].update({"status": "PENDING"}),
            "Input should be 'APPROVED'",
        ),
        (
            lambda value: value["assets"][0]["license"].update({"status": "PENDING"}),
            "Input should be 'VERIFIED'",
        ),
        (lambda value: value["shots"][0].update({"asset_id": "missing"}), "reference"),
        (lambda value: value["shots"][0].update({"order": 2}), "contiguous"),
        (lambda value: value["assets"][0].update({"sha256": "not-a-hash"}), "sha256"),
    ],
)
def test_rejects_unsafe_handoff(change, message):
    payload = valid_payload()
    change(payload)
    with pytest.raises(ValidationError, match=message):
        CreativeHandoffManifest.model_validate(payload)


def test_rejects_unknown_fields_and_duplicate_asset_ids():
    payload = valid_payload()
    payload["unexpected"] = True
    with pytest.raises(ValidationError, match="extra"):
        CreativeHandoffManifest.model_validate(payload)

    payload = valid_payload()
    payload["assets"].append(dict(payload["assets"][0]))
    with pytest.raises(ValidationError, match="unique"):
        CreativeHandoffManifest.model_validate(payload)
