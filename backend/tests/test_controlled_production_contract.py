from __future__ import annotations

from copy import deepcopy

import pytest
from libtv_agent.creative.controlled_production import (
    ControlledProductionContractError,
    build_controlled_production_manifest,
    validate_controlled_production,
)

HASH = "a" * 64


def _request(kind: str, task_id: str, package_id: str, shot_id: str) -> dict:
    return {
        "schema_version": "creative-provider-request.v1",
        "request_kind": kind,
        "creative_task_id": task_id,
        "owner_id": "owner-1",
        "package_revision_id": package_id,
        "shot_id": shot_id,
        "source_mapping": {
            "package_revision_id": package_id,
            "candidate_id": f"{kind}-candidate",
            "shot_id": shot_id,
            "batch_id": f"{kind}-batch",
            "item_id": f"{kind}-item",
            "output_id": f"{kind}-output",
        },
        "idempotency_key": f"creative-provider:{kind}:{task_id}",
        "bridge_validity_token": HASH,
        "evidence_hash": HASH,
        "request_hash": HASH,
    }


def _lineage(kind: str, task_id: str, package_id: str, shot_id: str) -> dict:
    source_kind = "REAL_IMAGE_OUTPUT" if kind == "image" else "REAL_VIDEO_OUTPUT"
    output_hash = "b" * 64 if kind == "image" else "c" * 64
    return {
        "adapter": kind,
        "task_id": task_id,
        "product_id": "product-1",
        "product_version_id": "product-version-1",
        "package_revision_id": package_id,
        "shot_id": shot_id,
        "provider_request": _request(kind, task_id, package_id, shot_id),
        "references": [{
            "role": "IMAGE_OUTPUT" if kind == "image" else "VIDEO_STORYBOARD",
            "reference_id": f"{kind}-reference",
            "sha256": output_hash,
            "source_kind": source_kind,
            "order": 1,
        }],
        "input_origin": source_kind,
        "cost_evidence": "NO_PAID_SIDE_EFFECT",
        "resolution_evidence": "KNOWN",
    }


def _sample() -> dict:
    return {
        "sample_id": "sample-1",
        "scope": {
            "product_count": 1,
            "image_task_count": 1,
            "video_task_count": 1,
            "batch": False,
            "loop": False,
            "deploy": False,
            "provider_execution": False,
            "paid": False,
        },
        "product": {
            "product_id": "product-1",
            "product_version_id": "product-version-1",
            "owner_id": "owner-1",
            "source_sha256": HASH,
            "source_ref": "product/front",
        },
        "image_task": _lineage("image", "image-task-1", "image-package-1", "FIRST_FRAME"),
        "video_task": _lineage("video", "video-task-1", "video-package-1", "SHOT_01"),
    }


def test_single_sample_manifest_is_deterministic_and_auditable():
    first = validate_controlled_production(_sample())
    second = build_controlled_production_manifest(_sample())

    assert first == second
    assert first.scope == "SINGLE_SAMPLE"
    assert first.product.product_id == "product-1"
    assert first.image_task.shot_id == "FIRST_FRAME"
    assert first.video_task.shot_id == "SHOT_01"
    assert len(first.manifest_hash) == 64
    assert first.image_task.provider_request.request_kind == "image"
    assert first.video_task.provider_request.request_kind == "video"


def test_missing_required_field_is_blocked():
    payload = _sample()
    del payload["video_task"]

    with pytest.raises(ControlledProductionContractError) as error:
        validate_controlled_production(payload)

    assert error.value.code == "REQUIRED_FIELD_MISSING"


@pytest.mark.parametrize(
    ("field", "code", "value"),
    [
        ("batch", "BATCH_FORBIDDEN", True),
        ("loop", "LOOP_FORBIDDEN", True),
        ("deploy", "DEPLOY_FORBIDDEN", True),
        ("provider", "PROVIDER_EXECUTION_FORBIDDEN", "kling"),
        ("paid", "PAID_SIDE_EFFECT_FORBIDDEN", True),
    ],
)
def test_forbidden_execution_scope_is_blocked(field, code, value):
    payload = _sample()
    payload["scope"][field] = value

    with pytest.raises(ControlledProductionContractError) as error:
        validate_controlled_production(payload)

    assert error.value.code == code


def test_multi_shot_is_blocked():
    payload = _sample()
    payload["video_task"]["shot_id"] = "SHOT_02"
    payload["video_task"]["provider_request"]["shot_id"] = "SHOT_02"
    payload["video_task"]["provider_request"]["source_mapping"]["shot_id"] = "SHOT_02"

    with pytest.raises(ControlledProductionContractError) as error:
        validate_controlled_production(payload)

    assert error.value.code == "CONTRACT_INVALID"


@pytest.mark.parametrize(
    ("field", "value", "code"),
    [
        ("input_origin", "OFFLINE_SYNTHETIC", "SYNTHETIC_OR_UNKNOWN_INPUT"),
        ("input_origin", "UNKNOWN", "SYNTHETIC_OR_UNKNOWN_INPUT"),
        ("cost_evidence", "PAID", "PAID_SIDE_EFFECT_FORBIDDEN"),
        ("cost_evidence", "UNKNOWN", "COST_EVIDENCE_UNKNOWN"),
        ("resolution_evidence", "UNKNOWN", "EXECUTION_EVIDENCE_UNKNOWN"),
    ],
)
def test_synthetic_paid_and_unknown_lineage_is_blocked(field, value, code):
    payload = _sample()
    payload["image_task"][field] = value

    with pytest.raises(ControlledProductionContractError) as error:
        validate_controlled_production(payload)

    assert error.value.code == code


def test_batch_list_is_rejected_without_entering_a_batch_contract():
    payload = _sample()
    payload["tasks"] = [deepcopy(payload["image_task"]), deepcopy(payload["video_task"])]

    with pytest.raises(ControlledProductionContractError) as error:
        validate_controlled_production(payload)

    assert error.value.code == "CONTRACT_INVALID"
