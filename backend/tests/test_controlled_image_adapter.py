from __future__ import annotations

from copy import deepcopy

import pytest
from libtv_agent.creative.brand_dna import project_brand_dna
from libtv_agent.creative.workflow import digest
from libtv_agent.services.controlled_image_adapter import (
    ControlledImageAdapterRejected,
    compile_controlled_image_batch_input,
)
from libtv_agent.services.creative_provider_requests import (
    CanonicalProduct,
    CreativeImageProviderRequest,
    ImagePredictionParameters,
    ImageProviderOptions,
    LockedProviderPrompt,
    ProviderReference,
    SourceMapping,
)

OWNER = "owner-1"
TASK = "task-1"
PACKAGE_ID = "package-first-frame"
PRODUCT_HASH = "a" * 64


def _brand() -> dict:
    return project_brand_dna({
        "id": "brand-1",
        "version": "v3",
        "name": "Brand",
        "status": "active",
        "audience": "adults",
        "tone": "quiet and precise",
        "palette": ["black"],
    })


def _request() -> CreativeImageProviderRequest:
    prompt = "Preserve the canonical product and create one FIRST_FRAME image."
    options = ImageProviderOptions()
    request = CreativeImageProviderRequest(
        creative_task_id=TASK,
        owner_id=OWNER,
        state_version=12,
        package_revision_id=PACKAGE_ID,
        shot_id="FIRST_FRAME",
        source_mapping=SourceMapping(
            package_revision_id=PACKAGE_ID,
            candidate_id="candidate-real",
            shot_id="FIRST_FRAME",
            batch_id="batch-1",
            item_id="item-1",
            output_id="output-1",
        ),
        canonical_product=CanonicalProduct(
            product_id="product-1",
            product_version_id="version-1",
            owner_id=OWNER,
            object_key="products/product-1/front.png",
            sha256=PRODUCT_HASH,
        ),
        locked_prompt=LockedProviderPrompt(
            prompt=prompt,
            prompt_hash=digest(prompt),
            preservation_hash="b" * 64,
            locks_hash="c" * 64,
            text_contract_hash="d" * 64,
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
        idempotency_key=f"creative-provider:image:{TASK}:{PACKAGE_ID}:FIRST_FRAME",
        bridge_validity_token="e" * 64,
        evidence_hash="f" * 64,
        request_hash="0" * 64,
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
    return request.model_copy(
        update={
            "request_hash": digest(
                request.model_dump(mode="json", exclude={"request_hash"})
            )
        }
    )


def _package(*, brand: dict | None = None) -> dict:
    prompt = _request().locked_prompt.prompt
    provenance = {
        "schemaVersion": "creative-package.v1",
        "packageId": PACKAGE_ID,
        "revision": 4,
        "shotId": "FIRST_FRAME",
        "purpose": "FIRST_FRAME",
        "creativeStateRevision": 12,
        "creativeTaskId": TASK,
        "productId": "product-1",
        "sourceHash": PRODUCT_HASH,
        "sourceAssets": [{
            "object_key": "products/product-1/front.png",
            "sha256": PRODUCT_HASH,
        }],
        "productFacts": {"name": "Jersey", "sku": "SKU-1"},
        "synthetic": False,
        "qualificationScope": "REAL_INPUT_UNVERIFIED",
        "sourcePackage": {
            "package_id": PACKAGE_ID,
            "shot_id": "FIRST_FRAME",
            "purpose": "FIRST_FRAME",
        },
    }
    if brand is not None:
        provenance["brandDNA"] = brand
    return {
        "imagePrompt": prompt,
        "shotPlan": [{"shotId": "FIRST_FRAME", "packageId": PACKAGE_ID}],
        "provenance": provenance,
    }


def _compile(package: dict | None = None, request=None, **kwargs):
    return compile_controlled_image_batch_input(
        package or _package(),
        request or _request(),
        owner_id=OWNER,
        creative_task_id=TASK,
        **kwargs,
    )


def _updated_request(request: CreativeImageProviderRequest, **updates):
    updated = request.model_copy(update=updates)
    return updated.model_copy(
        update={
            "request_hash": digest(
                updated.model_dump(mode="json", exclude={"request_hash"})
            )
        }
    )


def test_compiles_single_package_to_existing_batch_manifest_and_preserves_contract_fields():
    result = _compile()

    assert result["creativeStateRevision"] == 12
    assert result["packageId"] == PACKAGE_ID
    assert result["productAssetHash"] == PRODUCT_HASH
    assert result["promptSnapshot"] == _request().locked_prompt.prompt
    assert result["brandDNA"]["status"] == "UNRESOLVED"
    assert result["brandDNA"]["profileId"] is None
    assert result["brandDNA"]["version"] is None
    assert result["idempotencyKey"].endswith(":FIRST_FRAME")
    assert result["manifest"]["resultCount"] == 1
    assert result["manifest"]["expectedGenerationCount"] == 1
    assert result["manifest"]["items"][0]["referenceRoles"] == [
        {"fileIndex": 0, "role": "product.front"}
    ]
    assert result["manifest"]["items"][0]["prompts"]["fusion"] == result["promptSnapshot"]
    assert result["sourceInputs"] == [{
        "fileIndex": 0,
        "role": "product.front",
        "objectKey": "products/product-1/front.png",
        "sha256": PRODUCT_HASH,
    }]
    assert result["providerSubmissionAllowed"] is False
    assert result["ordinaryOutputQualified"] is False
    assert result["deliverableEligible"] is False


def test_preserves_brand_profile_id_and_version_when_snapshot_is_valid():
    result = _compile(_package(brand=_brand()))

    assert result["brandDNA"]["status"] == "PRESENT"
    assert result["brandDNA"]["profileId"] == "brand-1"
    assert result["brandDNA"]["version"] == "v3"
    assert result["brandDNA"]["snapshot"]["contentHash"] == _brand()["contentHash"]


@pytest.mark.parametrize(
    ("mutation", "code"),
    [
        ("owner", "OWNER_OR_TASK_MISMATCH"),
        ("task", "OWNER_OR_TASK_MISMATCH"),
        ("package", "PACKAGE_ID_MISMATCH"),
        ("source", "SOURCE_HASH_MISMATCH"),
        ("prompt", "PROMPT_SNAPSHOT_MISMATCH"),
        ("brand", "BRAND_DNA_TAMPERED"),
    ],
)
def test_identity_source_prompt_and_brand_tampering_is_rejected(mutation, code):
    package = _package(brand=_brand())
    request = _request()
    if mutation == "owner":
        request = _updated_request(request, owner_id="other-owner")
    elif mutation == "task":
        request = _updated_request(request, creative_task_id="other-task")
    elif mutation == "package":
        request = _updated_request(request, package_revision_id="other-package")
    elif mutation == "source":
        package["provenance"]["sourceHash"] = "f" * 64
    elif mutation == "prompt":
        package["imagePrompt"] = "rewritten prompt"
    else:
        package["provenance"]["brandDNA"]["audience"] = "tampered"
    with pytest.raises(ControlledImageAdapterRejected) as rejected:
        _compile(package, request)
    assert rejected.value.code == code


@pytest.mark.parametrize(
    "mutation",
    ["multiple_shots", "storyboard_shot", "multiple_references", "fake_package", "fake_request"],
)
def test_batch_multi_shot_and_fake_boundaries_are_rejected(mutation):
    package = _package()
    request = _request()
    if mutation == "multiple_shots":
        package["shotPlan"].append({"shotId": "SHOT_01", "packageId": "package-shot-01"})
    elif mutation == "storyboard_shot":
        package["provenance"]["sourcePackage"]["shot_id"] = "SHOT_01"
    elif mutation == "multiple_references":
        request = _updated_request(request, **{
            "references": (
                *request.references,
                request.references[0].model_copy(update={"order": 2}),
            )
        })
    elif mutation == "fake_package":
        package["provenance"]["synthetic"] = True
    else:
        request = _updated_request(request, provider="fake")
    with pytest.raises(ControlledImageAdapterRejected) as rejected:
        _compile(package, request)
    assert rejected.value.code in {
        "BATCH_NOT_SUPPORTED",
            "PACKAGE_SOURCE_MISMATCH",
        "SINGLE_SAMPLE_SCOPE_REQUIRED",
        "FAKE_SOURCE_FORBIDDEN",
    }


def test_compiler_is_detached_and_does_not_mutate_package_or_request():
    package = _package(brand=_brand())
    before = deepcopy(package)
    result = _compile(package)

    result["manifest"]["items"][0]["prompts"]["fusion"] = "changed"
    result["brandDNA"]["snapshot"]["audience"] = "changed"
    assert package == before


def test_missing_or_changed_creative_state_revision_is_rejected():
    package = _package()
    package["provenance"].pop("creativeStateRevision")
    assert _compile(package)["creativeStateRevision"] == 12
    with pytest.raises(ControlledImageAdapterRejected) as rejected:
        _compile(_package(), creative_state_revision=13)
    assert rejected.value.code == "CREATIVE_STATE_REVISION_MISMATCH"


def test_provider_request_hash_tampering_is_rejected():
    request = _request().model_copy(update={"request_hash": "0" * 64})

    with pytest.raises(ControlledImageAdapterRejected) as rejected:
        _compile(_package(), request)

    assert rejected.value.code == "PROVIDER_REQUEST_HASH_MISMATCH"
