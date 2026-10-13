from __future__ import annotations

import hashlib
from copy import deepcopy
from datetime import UTC, datetime
from uuid import UUID

import pytest
from libtv_agent.creative.brand_dna import validate_brand_dna
from libtv_agent.creative.human_review import HumanReviewRecord, HumanReviewSubject
from libtv_agent.services.controlled_image_adapter import (
    ControlledImageAdapterRejected,
    compile_controlled_image_batch_input,
)
from libtv_agent.services.controlled_video_adapter import (
    QualifiedVideoImageSource,
    compile_controlled_video_task_input,
)
from test_controlled_image_adapter import (
    OWNER,
    TASK,
    _brand,
    _package,
)
from test_controlled_image_adapter import (
    PACKAGE_ID as IMAGE_PACKAGE_ID,
)
from test_controlled_image_adapter import (
    _request as image_request,
)
from test_controlled_video_adapter import (
    BATCH_ID,
    ITEM_ID,
    OUTPUT_ID,
)
from test_controlled_video_adapter import (
    HASH as VIDEO_SOURCE_HASH,
)
from test_controlled_video_adapter import (
    PACKAGE_ID as VIDEO_PACKAGE_ID,
)
from test_controlled_video_adapter import (
    _request as video_request,
)

PRODUCT_HASH = "a" * 64
REVIEWER_ID = UUID("00000000-0000-0000-0000-000000000201")
REVIEW_ID = UUID("00000000-0000-0000-0000-000000000202")


def _video_request_with_image_parent():
    request = video_request()
    request = request.model_copy(update={
        "creative_task_id": TASK,
        "idempotency_key": request.idempotency_key.replace(
            "creative-task-1", TASK,
        ),
        "adapter_parameters": request.adapter_parameters.model_copy(update={
            "task_trace_id": TASK,
        }),
    })
    first_frame = request.references[0]
    assert first_frame.source_mapping is not None
    first_frame = first_frame.model_copy(update={
        "source_mapping": first_frame.source_mapping.model_copy(update={
            "package_revision_id": IMAGE_PACKAGE_ID,
        }),
    })
    return request.model_copy(update={
        "references": (first_frame, *request.references[1:]),
    })


def _qualified_image_source() -> QualifiedVideoImageSource:
    return QualifiedVideoImageSource(
        upload_id=UUID("00000000-0000-0000-0000-000000000203"),
        source_image_output_id=OUTPUT_ID,
        source_image_hash=VIDEO_SOURCE_HASH,
        output_image_hash=VIDEO_SOURCE_HASH,
        creative_task_id=TASK,
        candidate_id="storyboard-candidate",
        batch_id=BATCH_ID,
        item_id=ITEM_ID,
        package_lineage={
            "package_revision_id": VIDEO_PACKAGE_ID,
            "parent_package_revision_id": IMAGE_PACKAGE_ID,
        },
        revision_lineage={"revision": 2, "parent_revision": 1},
    )


def _workflow():
    product = {
        "productId": "product-1",
        "productVersionId": "version-1",
        "assetHash": PRODUCT_HASH,
        "objectKey": "products/product-1/front.png",
    }
    brand = _brand()
    assert validate_brand_dna(brand)

    package = _package(brand=brand)
    image = compile_controlled_image_batch_input(
        package,
        image_request(),
        owner_id=OWNER,
        creative_task_id=TASK,
    )

    video = compile_controlled_video_task_input(
        _video_request_with_image_parent(),
        _qualified_image_source(),
    )
    return product, brand, package, image, video


def test_product_to_brand_package_adapters_and_human_review_keep_lineage():
    product, brand, package, image, video = _workflow()
    video_prompt_hash = hashlib.sha256(
        _video_request_with_image_parent().locked_prompt.prompt.encode("utf-8")
    ).hexdigest()

    review = HumanReviewRecord(
        id=REVIEW_ID,
        review_key="runtime-stability-video-pass",
        reviewer_id=REVIEWER_ID,
        reviewed_at=datetime(2026, 10, 13, tzinfo=UTC),
        verdict="PASS",
        reason_codes=[],
        note=None,
        subject=HumanReviewSubject(
            subject_type="VIDEO_VARIANT",
            subject_id=str(video.source_image_output_id),
            task_id=None,
            output_hash=video.output_image_hash,
            synthetic=False,
            package_id=VIDEO_PACKAGE_ID,
            package_revision=2,
            input_hash=video.output_image_hash,
            prompt_hash=video_prompt_hash,
        ),
    )

    assert product["assetHash"] == package["provenance"]["sourceHash"]
    assert image["productAssetHash"] == product["assetHash"]
    assert image["creativeStateRevision"] == image_request().state_version
    assert image["packageId"] == IMAGE_PACKAGE_ID
    assert image["promptSnapshot"] == package["imagePrompt"]
    assert image["brandDNA"]["profileId"] == brand["profileId"]
    assert image["brandDNA"]["version"] == brand["profileVersion"]
    assert image["providerSubmissionAllowed"] is False
    assert image["ordinaryOutputQualified"] is False

    assert video.creative_task_id == TASK
    assert video.shot_id == "SHOT_01"
    assert video.package_lineage.package_revision_id == VIDEO_PACKAGE_ID
    assert video.package_lineage.parent_package_revision_id == image["packageId"]
    assert video.revision_lineage.revision == 2
    assert video.revision_lineage.parent_revision == 1
    assert video.source_image_hash == image["productAssetHash"]
    assert video.output_image_hash == video.source_image_hash
    assert video.payload.paid_submission_consent is False
    assert video.provider_submission_allowed is False

    assert review.subject.package_id == video.package_lineage.package_revision_id
    assert review.subject.package_revision == video.revision_lineage.revision
    assert review.subject.input_hash == video.output_image_hash
    assert review.subject.synthetic is False
    assert review.verdict == "PASS"


def test_lineage_failure_does_not_mutate_snapshot_and_retry_recovers():
    package = _package(brand=_brand())
    before = deepcopy(package)
    tampered = deepcopy(package)
    tampered["imagePrompt"] = "tampered prompt"

    with pytest.raises(ControlledImageAdapterRejected) as rejected:
        compile_controlled_image_batch_input(
            tampered,
            image_request(),
            owner_id=OWNER,
            creative_task_id=TASK,
        )

    assert rejected.value.code == "PROMPT_SNAPSHOT_MISMATCH"
    assert package == before

    recovered = compile_controlled_image_batch_input(
        package,
        image_request(),
        owner_id=OWNER,
        creative_task_id=TASK,
    )
    assert recovered["promptSnapshot"] == package["imagePrompt"]
    assert recovered["brandDNA"]["version"] == _brand()["profileVersion"]


@pytest.mark.parametrize(
    ("mutation", "code"),
    [
        ("state", "CREATIVE_STATE_REVISION_MISMATCH"),
        ("asset", "SOURCE_HASH_MISMATCH"),
        ("brand", "BRAND_DNA_TAMPERED"),
    ],
)
def test_runtime_lineage_tampering_is_blocked_before_adapter_output(mutation, code):
    package = _package(brand=_brand())
    request = image_request()
    if mutation == "state":
        package["provenance"]["creativeStateRevision"] += 1
    elif mutation == "asset":
        package["provenance"]["sourceHash"] = "f" * 64
    else:
        package["provenance"]["brandDNA"]["audience"] = "tampered"

    with pytest.raises(ControlledImageAdapterRejected) as rejected:
        compile_controlled_image_batch_input(
            package,
            request,
            owner_id=OWNER,
            creative_task_id=TASK,
        )
    assert rejected.value.code == code
