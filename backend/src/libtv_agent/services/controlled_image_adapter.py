"""Pure Creative Package to ordinary image-batch input compiler.

This adapter only compiles an already validated, provider-neutral image request
into the existing ``image-generation-batches`` manifest shape. It never calls a
Provider, materializes files, writes a database row, reserves quota, or changes
offline qualification rules.

The existing ``creative_provider_requests`` compiler remains the source of truth
for owner, task, package, prompt, source mapping, bytes, and Provider-request
integrity. This module adds the ordinary API envelope around that contract.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from collections.abc import Mapping
from copy import deepcopy
from typing import Any

from libtv_agent.api.image_generations import (
    ImageBatchManifest,
    ImageBatchManifestItem,
    ImageBatchPrompts,
    ReferenceRole,
)
from libtv_agent.creative.brand_dna import validate_brand_dna
from libtv_agent.creative.workflow import digest
from libtv_agent.services.creative_provider_requests import (
    CreativeImageProviderRequest,
)
from libtv_agent.services.image_generations import request_fingerprint
from pydantic import ValidationError

SHA256 = "^[0-9a-f]{64}$"


class ControlledImageAdapterRejected(ValueError):
    """Stable service-layer rejection for an invalid single-sample envelope."""

    def __init__(self, code: str, message: str | None = None) -> None:
        self.code = code
        self.message = message or code
        super().__init__(self.message)


def _reject(code: str, message: str | None = None) -> None:
    raise ControlledImageAdapterRejected(code, message)


def _object(value: Any, name: str) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        _reject("PACKAGE_INVALID", f"{name} must be an object")
    return dict(value)


def _text(value: Any, name: str, *, required: bool = True) -> str | None:
    if value is None and not required:
        return None
    if not isinstance(value, str) or not value.strip():
        _reject("PACKAGE_INVALID", f"{name} must be a non-empty string")
    return value


def _sha256(value: Any, name: str) -> str:
    text = _text(value, name)
    assert text is not None
    if len(text) != 64 or any(character not in "0123456789abcdef" for character in text):
        _reject("SOURCE_HASH_INVALID", f"{name} must be a lowercase SHA-256")
    return text


def _canonical_json(value: Any) -> str:
    try:
        return json.dumps(
            value,
            ensure_ascii=True,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
    except (TypeError, ValueError, OverflowError) as exc:
        _reject("PACKAGE_INVALID", "Creative Package must be JSON-serializable")
        raise AssertionError from exc


def _as_string(value: str | uuid.UUID) -> str:
    return str(value)


def _package_provenance(package: Mapping[str, Any]) -> dict[str, Any]:
    provenance = _object(package.get("provenance"), "provenance")
    package_id = _text(provenance.get("packageId"), "provenance.packageId")
    shot_id = _text(provenance.get("shotId"), "provenance.shotId")
    purpose = _text(provenance.get("purpose"), "provenance.purpose", required=False)
    if shot_id != "FIRST_FRAME" or purpose not in {None, "FIRST_FRAME"}:
        _reject("SINGLE_SAMPLE_SCOPE_REQUIRED", "only one FIRST_FRAME package is supported")
    if provenance.get("revision") is not None and (
        type(provenance["revision"]) is not int or provenance["revision"] < 1
    ):
        _reject("PACKAGE_REVISION_INVALID")
    return {
        **provenance,
        "packageId": package_id,
        "shotId": shot_id,
        "purpose": purpose or "FIRST_FRAME",
    }


def _assert_single_first_frame(package: Mapping[str, Any], provenance: Mapping[str, Any]) -> None:
    shot_plan = package.get("shotPlan")
    if shot_plan is not None:
        if not isinstance(shot_plan, list) or len(shot_plan) != 1:
            _reject("BATCH_NOT_SUPPORTED", "the adapter accepts exactly one FIRST_FRAME")
        shot = _object(shot_plan[0], "shotPlan[0]")
        if shot.get("shotId") != "FIRST_FRAME" or shot.get("packageId") != provenance["packageId"]:
            _reject("SINGLE_SAMPLE_SCOPE_REQUIRED")
    source_package = provenance.get("sourcePackage")
    if source_package is not None:
        source = _object(source_package, "provenance.sourcePackage")
        if (
            source.get("shot_id") != "FIRST_FRAME"
            or source.get("package_id") != provenance["packageId"]
        ):
            _reject("PACKAGE_SOURCE_MISMATCH")
        if source.get("purpose", "FIRST_FRAME") != "FIRST_FRAME":
            _reject("SINGLE_SAMPLE_SCOPE_REQUIRED")


def _assert_not_fake(package: Mapping[str, Any], request: CreativeImageProviderRequest) -> None:
    provenance = _object(package["provenance"], "provenance")
    if provenance.get("synthetic") is True:
        _reject("FAKE_SOURCE_FORBIDDEN")
    if provenance.get("qualificationScope") == "OFFLINE_SYNTHETIC_ONLY":
        _reject("FAKE_SOURCE_FORBIDDEN")
    origin = _object(provenance.get("originEvidence") or {}, "provenance.originEvidence")
    if str(origin.get("planEvidence") or "").upper().startswith("FAKE"):
        _reject("FAKE_SOURCE_FORBIDDEN")
    serialized = _canonical_json(package).upper()
    if "FAKE://" in serialized or '"FAKE":TRUE' in serialized or "OFFLINE_SYNTHETIC" in serialized:
        _reject("FAKE_SOURCE_FORBIDDEN")
    if request.provider.lower() in {"fake", "replay", "offline", "synthetic"}:
        _reject("FAKE_SOURCE_FORBIDDEN")
    request_json = request.model_dump_json().upper()
    if "FAKE://" in request_json or '"FAKE":TRUE' in request_json:
        _reject("FAKE_SOURCE_FORBIDDEN")


def _brand_snapshot(package: Mapping[str, Any]) -> dict[str, Any]:
    provenance = _object(package["provenance"], "provenance")
    brand = provenance.get("brandDNA")
    if brand is None:
        return {
            "profileId": None,
            "version": None,
            "status": "UNRESOLVED",
            "snapshot": None,
        }
    brand_object = _object(brand, "provenance.brandDNA")
    if not validate_brand_dna(brand_object):
        _reject("BRAND_DNA_TAMPERED")
    profile_id = _text(brand_object.get("profileId"), "brandDNA.profileId")
    profile_version = _text(brand_object.get("profileVersion"), "brandDNA.profileVersion")
    return {
        "profileId": profile_id,
        "version": profile_version,
        "status": "PRESENT",
        "snapshot": deepcopy(brand_object),
    }


def _source_asset(
    package: Mapping[str, Any],
    request: CreativeImageProviderRequest,
) -> dict[str, Any]:
    provenance = _object(package["provenance"], "provenance")
    source_hash = _sha256(provenance.get("sourceHash"), "provenance.sourceHash")
    canonical = request.canonical_product
    if canonical.sha256 != source_hash:
        _reject("SOURCE_HASH_MISMATCH")
    source_assets = provenance.get("sourceAssets")
    if not isinstance(source_assets, list) or len(source_assets) != 1:
        _reject("SOURCE_ASSET_REQUIRED", "exactly one canonical product asset is required")
    asset = _object(source_assets[0], "provenance.sourceAssets[0]")
    asset_hash = _sha256(asset.get("sha256"), "source asset sha256")
    object_key = _text(asset.get("object_key", asset.get("objectKey")), "source asset object key")
    if asset_hash != source_hash or object_key != canonical.object_key:
        _reject("SOURCE_HASH_MISMATCH")
    if asset.get("revoked") is True or canonical.materialized is not True:
        _reject("SOURCE_ASSET_INVALID")
    if object_key.startswith(("http://", "https://", "fake://")):
        _reject("SOURCE_OBJECT_KEY_INVALID")
    return {
        "fileIndex": 0,
        "role": "product.front",
        "objectKey": object_key,
        "sha256": asset_hash,
    }


def _creative_state_revision(
    package: Mapping[str, Any],
    request: CreativeImageProviderRequest,
    supplied: int | None,
) -> int:
    if supplied is not None and (type(supplied) is not int or supplied < 0):
        _reject("CREATIVE_STATE_REVISION_INVALID")
    provenance = _object(package["provenance"], "provenance")
    declared = provenance.get("creativeStateRevision", provenance.get("stateVersion"))
    if declared is not None and (type(declared) is not int or declared < 0):
        _reject("CREATIVE_STATE_REVISION_INVALID")
    result = supplied if supplied is not None else declared
    if result is None:
        result = request.state_version
    if result != request.state_version:
        _reject("CREATIVE_STATE_REVISION_MISMATCH")
    return result


def _assert_identity(
    package: Mapping[str, Any],
    request: CreativeImageProviderRequest,
    *,
    owner_id: str,
    creative_task_id: str,
) -> dict[str, Any]:
    provenance = _package_provenance(package)
    if request.owner_id != owner_id or request.creative_task_id != creative_task_id:
        _reject("OWNER_OR_TASK_MISMATCH")
    if request.shot_id != "FIRST_FRAME" or request.source_mapping.shot_id != "FIRST_FRAME":
        _reject("SINGLE_SAMPLE_SCOPE_REQUIRED")
    if request.package_revision_id != provenance["packageId"]:
        _reject("PACKAGE_ID_MISMATCH")
    if (
        provenance.get("creativeTaskId") is not None
        and str(provenance["creativeTaskId"]) != creative_task_id
    ):
        _reject("TASK_ID_MISMATCH")
    if provenance.get("ownerId") is not None and str(provenance["ownerId"]) != owner_id:
        _reject("OWNER_MISMATCH")
    product_id = provenance.get("productId")
    if product_id is not None and str(product_id) != request.canonical_product.product_id:
        _reject("PRODUCT_ID_MISMATCH")
    return provenance


def _assert_provider_request_integrity(request: CreativeImageProviderRequest) -> None:
    if request.request_hash != digest(
        request.model_dump(mode="json", exclude={"request_hash"})
    ):
        _reject("PROVIDER_REQUEST_HASH_MISMATCH")


def compile_controlled_image_batch_input(
    package: Mapping[str, Any],
    provider_request: CreativeImageProviderRequest | Mapping[str, Any],
    *,
    owner_id: str | uuid.UUID,
    creative_task_id: str | uuid.UUID,
    creative_state_revision: int | None = None,
    paid_submission_consent: bool = True,
) -> dict[str, Any]:
    """Compile one real Creative Package into the existing image batch envelope.

    ``provider_request`` must already be produced by
    ``compile_creative_image_request``. Re-validating that existing contract
    here prevents this thin adapter from becoming a second source of truth.
    The return value contains only JSON-compatible input data; the caller still
    has to materialize ``sourceInputs`` and invoke the ordinary API explicitly.
    """
    if not isinstance(package, Mapping):
        _reject("PACKAGE_INVALID")
    try:
        request = (
            provider_request
            if isinstance(provider_request, CreativeImageProviderRequest)
            else CreativeImageProviderRequest.model_validate(provider_request)
        )
    except ValidationError as exc:
        _reject("PROVIDER_REQUEST_INVALID", str(exc))
    owner = _as_string(owner_id)
    task_id = _as_string(creative_task_id)
    _assert_provider_request_integrity(request)
    provenance = _assert_identity(package, request, owner_id=owner, creative_task_id=task_id)
    _assert_single_first_frame(package, provenance)
    _assert_not_fake(package, request)
    source = _source_asset(package, request)
    state_revision = _creative_state_revision(
        package, request, creative_state_revision
    )
    prompt = _text(package.get("imagePrompt"), "imagePrompt")
    assert prompt is not None
    if (
        prompt != request.locked_prompt.prompt
        or prompt != request.adapter_parameters.prompt
        or digest(prompt) != request.locked_prompt.prompt_hash
    ):
        _reject("PROMPT_SNAPSHOT_MISMATCH")
    if not request.references or len(request.references) != 1:
        _reject("BATCH_NOT_SUPPORTED", "exactly one product reference is required")
    reference = request.references[0]
    if (
        reference.role != "PRODUCT"
        or reference.order != 1
        or reference.adapter_field != "images"
        or reference.object_key != source["objectKey"]
        or reference.sha256 != source["sha256"]
    ):
        _reject("SOURCE_MAPPING_MISMATCH")
    if request.provider_submission_allowed is not False:
        _reject("PROVIDER_SUBMISSION_CONTRACT_INVALID")
    if request.ordinary_output_qualified is not False or request.deliverable_eligible is not False:
        _reject("OFFLINE_SAFETY_CONTRACT_INVALID")
    if paid_submission_consent is not True:
        _reject("PAID_SUBMISSION_CONSENT_REQUIRED")

    brand = _brand_snapshot(package)
    package_revision = provenance.get("revision")
    client_batch_id = (
        _text(
            package.get("clientBatchId", package.get("client_batch_id")),
            "clientBatchId",
            required=False,
        )
        or f"creative-image:{task_id}:{provenance['packageId']}:FIRST_FRAME"
    )
    outfit_name = (
        _object(provenance.get("productFacts") or {}, "provenance.productFacts").get("name")
        or request.canonical_product.product_id
    )
    item = ImageBatchManifestItem(
        clientTaskId=f"{task_id}:FIRST_FRAME",
        outfitId=request.canonical_product.product_id,
        outfitName=str(outfit_name),
        sku=str(
            _object(provenance.get("productFacts") or {}, "provenance.productFacts").get("sku")
            or ""
        ),
        prompts=ImageBatchPrompts(fusion=prompt, storyboard=""),
        referenceFileIndexes=[0],
        referenceRoles=[ReferenceRole(fileIndex=0, role="product.front")],
        storyboardShots=[],
        generateBack=False,
    )
    manifest = ImageBatchManifest(
        clientBatchId=client_batch_id,
        name=f"Creative Package {provenance['packageId']} FIRST_FRAME",
        provider=request.provider,
        modes=["fusion"],
        resultCount=1,
        aspectRatio=request.options.aspect_ratio,
        resolution=request.options.resolution,
        quality=request.options.quality,
        outputFormat=request.options.output_format,
        allowBackInference=False,
        paidSubmissionConsent=True,
        expectedGenerationCount=1,
        items=[item],
    )
    manifest_json = manifest.model_dump(mode="json")
    request_hash = request_fingerprint(manifest_json, [source["sha256"]])
    return {
        "schemaVersion": "controlled-image-batch-input.v1",
        "manifest": manifest_json,
        "idempotencyKey": request.idempotency_key,
        "requestHash": request_hash,
        "providerRequestHash": request.request_hash,
        "sourceInputs": [source],
        "creativeStateRevision": state_revision,
        "packageId": provenance["packageId"],
        "packageRevision": package_revision,
        "productAssetHash": source["sha256"],
        "promptSnapshot": prompt,
        "promptSnapshotHash": hashlib.sha256(prompt.encode("utf-8")).hexdigest(),
        "brandDNA": brand,
        "ownerId": owner,
        "creativeTaskId": task_id,
        "shotId": "FIRST_FRAME",
        "providerSubmissionAllowed": False,
        "ordinaryOutputQualified": False,
        "deliverableEligible": False,
        "sourceQualificationScope": "REAL_INPUT_UNVERIFIED",
    }


compile_creative_package_image_batch = compile_controlled_image_batch_input
compile_controlled_image_adapter = compile_controlled_image_batch_input
