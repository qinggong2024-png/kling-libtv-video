from __future__ import annotations

from uuid import UUID, uuid4

import pytest
from libtv_agent.services.controlled_video_adapter import (
    ControlledVideoAdapterRejected,
    ControlledVideoPackageLineage,
    QualifiedVideoImageSource,
    compile_controlled_video_task_input,
)
from libtv_agent.services.creative_provider_requests import (
    CreativeVideoProviderRequest,
    LockedProviderPrompt,
    ProviderReference,
    SourceMapping,
    VideoProviderOptions,
    VideoRequestParameters,
)

HASH = "a" * 64
OTHER_HASH = "b" * 64
TASK_ID = "creative-task-1"
PACKAGE_ID = "task:storyboard:SHOT_01:1"
PARENT_PACKAGE_ID = "task:package:1"
OUTPUT_ID = UUID("00000000-0000-0000-0000-000000000101")
BATCH_ID = UUID("00000000-0000-0000-0000-000000000102")
ITEM_ID = UUID("00000000-0000-0000-0000-000000000103")
UPLOAD_ID = UUID("00000000-0000-0000-0000-000000000104")


def _mapping(package_id: str, candidate_id: str, shot_id: str, output_id: UUID) -> SourceMapping:
    return SourceMapping(
        package_revision_id=package_id,
        candidate_id=candidate_id,
        shot_id=shot_id,
        batch_id=str(BATCH_ID),
        item_id=str(ITEM_ID),
        output_id=str(output_id),
    )


def _request() -> CreativeVideoProviderRequest:
    first = _mapping(PARENT_PACKAGE_ID, "first-frame-candidate", "FIRST_FRAME", uuid4())
    storyboard = _mapping(PACKAGE_ID, "storyboard-candidate", "SHOT_01", OUTPUT_ID)
    locked = LockedProviderPrompt(
        prompt="Preserve the approved image and make one controlled video shot.",
        prompt_hash=HASH,
        preservation_hash=HASH,
        locks_hash=HASH,
        text_contract_hash=HASH,
        text_contract_json="{}",
    )
    return CreativeVideoProviderRequest(
        creative_task_id=TASK_ID,
        owner_id="owner-1",
        state_version=3,
        package_revision_id=PACKAGE_ID,
        shot_id="SHOT_01",
        source_mapping=storyboard,
        canonical_product={
            "product_id": "product-1",
            "product_version_id": "product-version-1",
            "owner_id": "owner-1",
            "object_key": "products/source.jpg",
            "sha256": HASH,
        },
        locked_prompt=locked,
        references=(
            ProviderReference(
                role="FIRST_FRAME",
                order=1,
                adapter_field="first_frame_path",
                object_key="images/first-frame.jpg",
                sha256=HASH,
                source_mapping=first,
            ),
            ProviderReference(
                role="STORYBOARD",
                order=2,
                adapter_field="refer_image_paths",
                object_key="images/storyboard.jpg",
                sha256=HASH,
                source_mapping=storyboard,
            ),
            ProviderReference(
                role="PRODUCT",
                order=3,
                adapter_field="product_reference_paths",
                object_key="products/source.jpg",
                sha256=HASH,
            ),
        ),
        idempotency_key="creative-provider:video:creative-task-1:SHOT_01",
        bridge_validity_token=HASH,
        evidence_hash=HASH,
        request_hash=HASH,
        provider="kling_official_api",
        model="kling-test",
        options=VideoProviderOptions(provider="kling_official_api", model="kling-test"),
        adapter_parameters=VideoRequestParameters(
            prompt=locked.prompt,
            model="kling-test",
            duration=5,
            aspect_ratio="9:16",
            resolution=None,
            audio="off",
            task_trace_id=TASK_ID,
            external_task_id="creative-video-external-1",
        ),
    )


def _source(**overrides) -> QualifiedVideoImageSource:
    values = {
        "upload_id": UPLOAD_ID,
        "source_image_output_id": OUTPUT_ID,
        "source_image_hash": HASH,
        "output_image_hash": HASH,
        "creative_task_id": TASK_ID,
        "candidate_id": "storyboard-candidate",
        "batch_id": BATCH_ID,
        "item_id": ITEM_ID,
        "package_lineage": {
            "package_revision_id": PACKAGE_ID,
            "parent_package_revision_id": PARENT_PACKAGE_ID,
        },
        "revision_lineage": {"revision": 2, "parent_revision": 1},
    }
    values.update(overrides)
    return QualifiedVideoImageSource.model_validate(values)


def test_maps_one_qualified_image_to_existing_video_task_shape() -> None:
    result = compile_controlled_video_task_input(_request(), _source())

    assert result.payload.storyboards[0].upload_id == UPLOAD_ID
    assert result.payload.storyboards[0].order == 1
    assert result.payload.generation_mode == "custom"
    assert result.payload.custom_prompt == _request().locked_prompt.prompt
    assert result.payload.paid_submission_consent is False
    assert result.provider_submission_allowed is False
    assert result.source_image_output_id == OUTPUT_ID
    assert result.source_image_hash == result.output_image_hash == HASH
    assert result.shot_id == "SHOT_01"
    assert result.creative_task_id == TASK_ID


@pytest.mark.parametrize(
    ("field", "value", "code"),
    [
        ("source_image_hash", OTHER_HASH, "SOURCE_OUTPUT_HASH_MISMATCH"),
        ("output_image_hash", OTHER_HASH, "OUTPUT_HASH_MISMATCH"),
        ("source_image_output_id", uuid4(), "SOURCE_IMAGE_OUTPUT_ID_MISMATCH"),
        ("shot_id", "FIRST_FRAME", "SHOT_ID_INVALID"),
        ("creative_task_id", "other-task", "CREATIVE_TASK_ID_MISMATCH"),
    ],
)
def test_rejects_hash_qualification_and_shot_mismatches(field, value, code) -> None:
    with pytest.raises(ControlledVideoAdapterRejected) as rejected:
        compile_controlled_video_task_input(
            _request(),
            _source().model_copy(update={field: value}),
        )
    assert rejected.value.code == code


def test_rejects_non_production_or_synthetic_sources() -> None:
    with pytest.raises(ControlledVideoAdapterRejected, match="QUALIFICATION_SCOPE_INVALID"):
        compile_controlled_video_task_input(
            _request(),
            _source().model_copy(update={"qualification_scope": "OFFLINE_SYNTHETIC_ONLY"}),
        )
    with pytest.raises(ControlledVideoAdapterRejected, match="QUALIFICATION_SCOPE_INVALID"):
        compile_controlled_video_task_input(
            _request(),
            _source().model_copy(update={"synthetic": True}),
        )


@pytest.mark.parametrize(
    ("field", "value", "code"),
    [
        ("package_lineage", {
            "package_revision_id": "other-package",
            "parent_package_revision_id": PARENT_PACKAGE_ID,
        }, "PACKAGE_REVISION_MISMATCH"),
        ("package_lineage", {
            "package_revision_id": PACKAGE_ID,
            "parent_package_revision_id": "other-parent",
        }, "PACKAGE_PARENT_MISMATCH"),
        ("revision_lineage", {"revision": 1, "parent_revision": 1}, None),
    ],
)
def test_rejects_package_and_revision_lineage_mismatches(field, value, code) -> None:
    if code is None:
        with pytest.raises(ValueError):
            QualifiedVideoImageSource.model_validate(
                _source().model_dump(mode="json") | {field: value}
            )
        return
    if field == "package_lineage":
        value = ControlledVideoPackageLineage.model_validate(value)
    with pytest.raises(ControlledVideoAdapterRejected) as rejected:
        compile_controlled_video_task_input(
            _request(),
            _source().model_copy(update={field: value}),
        )
    assert rejected.value.code == code


def test_rejects_batch_and_multi_shot_inputs() -> None:
    with pytest.raises(ControlledVideoAdapterRejected, match="BATCH_INPUT_NOT_ALLOWED"):
        compile_controlled_video_task_input(_request(), [_source()])

    request = _request()
    request = request.model_copy(update={
        "options": request.options.model_copy(update={"multi_shot": True}),
    })
    with pytest.raises(ControlledVideoAdapterRejected, match="MULTI_SHOT_NOT_ALLOWED"):
        compile_controlled_video_task_input(request, _source())

    request = _request().model_copy(update={
        "references": _request().references + (
            ProviderReference(
                role="STORYBOARD",
                order=4,
                adapter_field="refer_image_paths",
                object_key="images/second.jpg",
                sha256=HASH,
                source_mapping=_request().source_mapping,
            ),
        ),
    })
    with pytest.raises(ControlledVideoAdapterRejected, match="STORYBOARD_REFERENCE_COUNT_INVALID"):
        compile_controlled_video_task_input(request, _source())


def test_fake_boundary_never_becomes_a_real_video_input() -> None:
    with pytest.raises(ControlledVideoAdapterRejected, match="QUALIFICATION_SCOPE_INVALID"):
        compile_controlled_video_task_input(
            _request(),
            _source().model_copy(update={"qualification_scope": "OFFLINE_SYNTHETIC_ONLY"}),
        )
