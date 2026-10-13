from __future__ import annotations

from uuid import UUID

from libtv_agent.creative.controlled_production import (
    AdapterLineage,
    ControlledProductionSample,
    ProductLineage,
    provider_request_lineage,
    validate_controlled_production,
)
from libtv_agent.creative.workflow import digest
from libtv_agent.services.controlled_image_adapter import (
    compile_controlled_image_batch_input,
)
from libtv_agent.services.controlled_video_adapter import (
    QualifiedVideoImageSource,
    compile_controlled_video_task_input,
)
from libtv_agent.services.creative_provider_requests import (
    CanonicalProduct,
    CreativeImageProviderRequest,
    CreativeVideoProviderRequest,
    ImagePredictionParameters,
    ImageProviderOptions,
    LockedProviderPrompt,
    ProviderReference,
    SourceMapping,
    VideoProviderOptions,
    VideoRequestParameters,
)

OWNER = "owner-1"
TASK = "creative-task-1"
PRODUCT_HASH = "a" * 64
IMAGE_HASH = "b" * 64
VIDEO_HASH = "c" * 64
IMAGE_PACKAGE = "image-package-1"
VIDEO_PACKAGE = "video-package-1"
OUTPUT_ID = UUID("00000000-0000-0000-0000-000000000101")
BATCH_ID = UUID("00000000-0000-0000-0000-000000000102")
ITEM_ID = UUID("00000000-0000-0000-0000-000000000103")
UPLOAD_ID = UUID("00000000-0000-0000-0000-000000000104")


def _image_request() -> CreativeImageProviderRequest:
    prompt = "Preserve the canonical product and create one FIRST_FRAME image."
    options = ImageProviderOptions()
    request = CreativeImageProviderRequest(
        creative_task_id=TASK,
        owner_id=OWNER,
        state_version=12,
        package_revision_id=IMAGE_PACKAGE,
        shot_id="FIRST_FRAME",
        source_mapping=SourceMapping(
            package_revision_id=IMAGE_PACKAGE,
            candidate_id="image-candidate",
            shot_id="FIRST_FRAME",
            batch_id="image-batch",
            item_id="image-item",
            output_id="image-output",
        ),
        canonical_product=CanonicalProduct(
            product_id="product-1",
            product_version_id="product-version-1",
            owner_id=OWNER,
            object_key="products/product-1/front.png",
            sha256=PRODUCT_HASH,
        ),
        locked_prompt=LockedProviderPrompt(
            prompt=prompt,
            prompt_hash=digest(prompt),
            preservation_hash=IMAGE_HASH,
            locks_hash=IMAGE_HASH,
            text_contract_hash=IMAGE_HASH,
            text_contract_json="{}",
        ),
        references=(
            ProviderReference(
                role="PRODUCT",
                order=1,
                adapter_field="images",
                object_key="products/product-1/front.png",
                sha256=PRODUCT_HASH,
            ),
        ),
        idempotency_key=f"creative-provider:image:{TASK}:{IMAGE_PACKAGE}:FIRST_FRAME",
        bridge_validity_token=IMAGE_HASH,
        evidence_hash=IMAGE_HASH,
        request_hash=IMAGE_HASH,
        provider=options.provider,
        model="openai/gpt-image-2/edit",
        options=options,
        adapter_parameters=ImagePredictionParameters(
            prompt=prompt,
            aspect_ratio=options.aspect_ratio,
            resolution=options.resolution,
            output_format=options.output_format,
            quality=options.quality,
        ),
    )
    return request.model_copy(update={
        "request_hash": digest(request.model_dump(mode="json", exclude={"request_hash"})),
    })


def _video_request() -> CreativeVideoProviderRequest:
    first_mapping = SourceMapping(
        package_revision_id=IMAGE_PACKAGE,
        candidate_id="first-frame-candidate",
        shot_id="FIRST_FRAME",
        batch_id=str(BATCH_ID),
        item_id=str(ITEM_ID),
        output_id=str(UUID("00000000-0000-0000-0000-000000000105")),
    )
    storyboard_mapping = SourceMapping(
        package_revision_id=VIDEO_PACKAGE,
        candidate_id="storyboard-candidate",
        shot_id="SHOT_01",
        batch_id=str(BATCH_ID),
        item_id=str(ITEM_ID),
        output_id=str(OUTPUT_ID),
    )
    prompt = "Preserve the approved image and make one controlled video shot."
    locked = LockedProviderPrompt(
        prompt=prompt,
        prompt_hash=IMAGE_HASH,
        preservation_hash=IMAGE_HASH,
        locks_hash=IMAGE_HASH,
        text_contract_hash=IMAGE_HASH,
        text_contract_json="{}",
    )
    options = VideoProviderOptions(provider="kling_official_api", model="kling-test")
    return CreativeVideoProviderRequest(
        creative_task_id=TASK,
        owner_id=OWNER,
        state_version=12,
        package_revision_id=VIDEO_PACKAGE,
        shot_id="SHOT_01",
        source_mapping=storyboard_mapping,
        canonical_product=CanonicalProduct(
            product_id="product-1",
            product_version_id="product-version-1",
            owner_id=OWNER,
            object_key="products/product-1/front.png",
            sha256=PRODUCT_HASH,
        ),
        locked_prompt=locked,
        references=(
            ProviderReference(
                role="FIRST_FRAME",
                order=1,
                adapter_field="first_frame_path",
                object_key="images/first-frame.jpg",
                sha256=IMAGE_HASH,
                source_mapping=first_mapping,
            ),
            ProviderReference(
                role="STORYBOARD",
                order=2,
                adapter_field="refer_image_paths",
                object_key="images/storyboard.jpg",
                sha256=VIDEO_HASH,
                source_mapping=storyboard_mapping,
            ),
            ProviderReference(
                role="PRODUCT",
                order=3,
                adapter_field="product_reference_paths",
                object_key="products/product-1/front.png",
                sha256=PRODUCT_HASH,
            ),
        ),
        idempotency_key=f"creative-provider:video:{TASK}:{VIDEO_PACKAGE}:SHOT_01",
        bridge_validity_token=IMAGE_HASH,
        evidence_hash=IMAGE_HASH,
        request_hash=IMAGE_HASH,
        provider=options.provider,
        model=options.model,
        options=options,
        adapter_parameters=VideoRequestParameters(
            prompt=prompt,
            model=options.model,
            duration=options.duration,
            aspect_ratio=options.aspect_ratio,
            resolution=options.resolution,
            audio=options.audio,
            task_trace_id=TASK,
            external_task_id="creative-video-external-1",
        ),
    )


def test_package_image_video_and_single_sample_contract_compose_without_side_effects():
    image_request = _image_request()
    image_package = {
        "imagePrompt": image_request.locked_prompt.prompt,
        "shotPlan": [{"shotId": "FIRST_FRAME", "packageId": IMAGE_PACKAGE}],
        "provenance": {
            "packageId": IMAGE_PACKAGE,
            "revision": 1,
            "shotId": "FIRST_FRAME",
            "purpose": "FIRST_FRAME",
            "creativeStateRevision": image_request.state_version,
            "creativeTaskId": TASK,
            "productId": "product-1",
            "sourceHash": PRODUCT_HASH,
            "sourceAssets": [{
                "object_key": "products/product-1/front.png",
                "sha256": PRODUCT_HASH,
            }],
            "synthetic": False,
            "qualificationScope": "REAL_INPUT_UNVERIFIED",
            "sourcePackage": {
                "package_id": IMAGE_PACKAGE,
                "shot_id": "FIRST_FRAME",
                "purpose": "FIRST_FRAME",
            },
        },
    }
    image_input = compile_controlled_image_batch_input(
        image_package,
        image_request,
        owner_id=OWNER,
        creative_task_id=TASK,
    )

    video_request = _video_request()
    video_source = QualifiedVideoImageSource(
        upload_id=UPLOAD_ID,
        source_image_output_id=OUTPUT_ID,
        source_image_hash=VIDEO_HASH,
        output_image_hash=VIDEO_HASH,
        creative_task_id=TASK,
        candidate_id="storyboard-candidate",
        batch_id=BATCH_ID,
        item_id=ITEM_ID,
        package_lineage={
            "package_revision_id": VIDEO_PACKAGE,
            "parent_package_revision_id": IMAGE_PACKAGE,
        },
        revision_lineage={"revision": 2, "parent_revision": 1},
    )
    video_input = compile_controlled_video_task_input(video_request, video_source)

    image_lineage = AdapterLineage(
        adapter="image",
        task_id=TASK,
        product_id="product-1",
        product_version_id="product-version-1",
        package_revision_id=IMAGE_PACKAGE,
        shot_id="FIRST_FRAME",
        provider_request=provider_request_lineage(image_request),
        references=[{
            "role": "PRODUCT",
            "reference_id": image_input["productAssetHash"],
            "sha256": PRODUCT_HASH,
            "source_kind": "REAL_PRODUCT",
            "order": 1,
        }],
        input_origin="REAL_PRODUCT",
        cost_evidence="NO_PAID_SIDE_EFFECT",
        resolution_evidence="KNOWN",
    )
    video_lineage = AdapterLineage(
        adapter="video",
        task_id=TASK,
        product_id="product-1",
        product_version_id="product-version-1",
        package_revision_id=VIDEO_PACKAGE,
        shot_id="SHOT_01",
        provider_request=provider_request_lineage(video_request),
        references=[{
            "role": "IMAGE_OUTPUT",
            "reference_id": str(video_input.source_image_output_id),
            "sha256": video_input.output_image_hash,
            "source_kind": "REAL_IMAGE_OUTPUT",
            "order": 1,
        }],
        input_origin="REAL_IMAGE_OUTPUT",
        cost_evidence="NO_PAID_SIDE_EFFECT",
        resolution_evidence="KNOWN",
    )
    manifest = validate_controlled_production(ControlledProductionSample(
        sample_id="sample-1",
        product=ProductLineage(
            product_id="product-1",
            product_version_id="product-version-1",
            owner_id=OWNER,
            source_sha256=PRODUCT_HASH,
            source_ref="products/product-1/front.png",
        ),
        image_task=image_lineage,
        video_task=video_lineage,
    ))

    assert image_input["manifest"]["expectedGenerationCount"] == 1
    assert video_input.payload.result_count == 1
    assert manifest.scope == "SINGLE_SAMPLE"
    assert manifest.image_task.shot_id == "FIRST_FRAME"
    assert manifest.video_task.shot_id == "SHOT_01"
