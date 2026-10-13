"""Pure single-sample controlled-production contract.

This module composes identity fields from the existing provider request
contracts. It does not compile requests, submit media, persist state, or
redefine provider, billing, task, or qualification state.
"""
from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from libtv_agent.services.creative_provider_requests import SourceMapping

SHA256 = str
SHA256_PATTERN = r"^[0-9a-f]{64}$"


class ControlledProductionContractError(ValueError):
    """Stable pure-contract rejection with no API or persistence semantics."""

    def __init__(self, code: str, message: str | None = None) -> None:
        self.code = code
        super().__init__(message or code)


class ContractModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)


class ProductLineage(ContractModel):
    product_id: str = Field(min_length=1, max_length=160)
    product_version_id: str = Field(min_length=1, max_length=160)
    owner_id: str = Field(min_length=1, max_length=160)
    source_sha256: SHA256 = Field(pattern=SHA256_PATTERN)
    source_ref: str = Field(min_length=1, max_length=500)


class LineageReference(ContractModel):
    role: Literal["PRODUCT", "IMAGE_OUTPUT", "VIDEO_STORYBOARD"]
    reference_id: str = Field(min_length=1, max_length=240)
    sha256: SHA256 = Field(pattern=SHA256_PATTERN)
    source_kind: Literal["REAL_PRODUCT", "REAL_IMAGE_OUTPUT", "REAL_VIDEO_OUTPUT"]
    order: int = Field(ge=1)


class ProviderRequestLineage(ContractModel):
    """Identity projection of an existing Creative Provider request.

    The full request remains owned by creative_provider_requests.py. This
    projection carries only the immutable identifiers needed to join the
    request to a single-sample audit manifest.
    """

    schema_version: Literal["creative-provider-request.v1"] = (
        "creative-provider-request.v1"
    )
    request_kind: Literal["image", "video"]
    creative_task_id: str = Field(min_length=1, max_length=160)
    owner_id: str = Field(min_length=1, max_length=160)
    package_revision_id: str = Field(min_length=1, max_length=240)
    shot_id: Literal["FIRST_FRAME", "SHOT_01"]
    source_mapping: SourceMapping
    idempotency_key: str = Field(min_length=1, max_length=500)
    bridge_validity_token: SHA256 = Field(pattern=SHA256_PATTERN)
    evidence_hash: SHA256 = Field(pattern=SHA256_PATTERN)
    request_hash: SHA256 = Field(pattern=SHA256_PATTERN)


class AdapterLineage(ContractModel):
    adapter: Literal["image", "video"]
    task_id: str = Field(min_length=1, max_length=160)
    product_id: str = Field(min_length=1, max_length=160)
    product_version_id: str = Field(min_length=1, max_length=160)
    package_revision_id: str = Field(min_length=1, max_length=240)
    shot_id: Literal["FIRST_FRAME", "SHOT_01"]
    provider_request: ProviderRequestLineage
    references: tuple[LineageReference, ...] = Field(min_length=1, max_length=8)
    input_origin: Literal["REAL_PRODUCT", "REAL_IMAGE_OUTPUT", "REAL_VIDEO_OUTPUT",
                          "OFFLINE_SYNTHETIC", "UNKNOWN"]
    cost_evidence: Literal["NO_PAID_SIDE_EFFECT", "PAID", "UNKNOWN"]
    resolution_evidence: Literal["KNOWN", "UNKNOWN"]
    loop_count: Literal[0] = 0
    deployment_target: Literal["NONE"] = "NONE"

    @model_validator(mode="after")
    def validate_identity(self) -> AdapterLineage:
        if self.adapter != self.provider_request.request_kind:
            raise ValueError("adapter does not match provider request kind")
        if self.task_id != self.provider_request.creative_task_id:
            raise ValueError("task_id does not match provider request")
        if self.package_revision_id != self.provider_request.package_revision_id:
            raise ValueError("package revision does not match provider request")
        if self.shot_id != self.provider_request.shot_id:
            raise ValueError("shot_id does not match provider request")
        if self.product_id == self.provider_request.source_mapping.candidate_id:
            raise ValueError("product and candidate identities must remain distinct")
        reference_ids = [reference.reference_id for reference in self.references]
        if len(reference_ids) != len(set(reference_ids)):
            raise ValueError("lineage references must be unique")
        return self


class SingleSampleScope(ContractModel):
    product_count: Literal[1] = 1
    image_task_count: Literal[1] = 1
    video_task_count: Literal[1] = 1
    batch: Literal[False] = False
    loop: Literal[False] = False
    deploy: Literal[False] = False
    provider_execution: Literal[False] = False
    paid: Literal[False] = False


class ControlledProductionSample(ContractModel):
    schema_version: Literal["controlled-production-single-sample.v1"] = (
        "controlled-production-single-sample.v1"
    )
    sample_id: str = Field(min_length=1, max_length=160)
    scope: SingleSampleScope = SingleSampleScope()
    product: ProductLineage
    image_task: AdapterLineage
    video_task: AdapterLineage

    @model_validator(mode="after")
    def validate_single_sample(self) -> ControlledProductionSample:
        if self.image_task.adapter != "image" or self.image_task.shot_id != "FIRST_FRAME":
            raise ValueError("single sample requires one FIRST_FRAME image task")
        if self.video_task.adapter != "video" or self.video_task.shot_id != "SHOT_01":
            raise ValueError("single sample requires one SHOT_01 video task")
        if self.image_task.product_id != self.product.product_id:
            raise ValueError("image task product does not match the single product")
        if self.video_task.product_id != self.product.product_id:
            raise ValueError("video task product does not match the single product")
        if self.image_task.product_version_id != self.product.product_version_id:
            raise ValueError("image task product version does not match the product")
        if self.video_task.product_version_id != self.product.product_version_id:
            raise ValueError("video task product version does not match the product")
        if (
            self.image_task.provider_request.idempotency_key
            == self.video_task.provider_request.idempotency_key
        ):
            raise ValueError("image and video adapter requests must be distinct")
        if self.image_task.provider_request.owner_id != self.product.owner_id:
            raise ValueError("image request owner does not match the product")
        if self.video_task.provider_request.owner_id != self.product.owner_id:
            raise ValueError("video request owner does not match the product")
        return self


class ControlledProductionManifest(ContractModel):
    schema_version: Literal["controlled-production-manifest.v1"] = (
        "controlled-production-manifest.v1"
    )
    sample_id: str
    scope: Literal["SINGLE_SAMPLE"] = "SINGLE_SAMPLE"
    product: ProductLineage
    image_task: AdapterLineage
    video_task: AdapterLineage
    manifest_hash: SHA256 = Field(pattern=SHA256_PATTERN)


_FORBIDDEN_TOP_LEVEL = {
    "batch", "batches", "batch_count", "loop", "loops", "loop_count",
    "deploy", "deployment", "deployment_target", "provider", "provider_name",
    "paid", "payment", "paid_generation", "provider_execution",
}


def _reject_forbidden_input(value: Mapping[str, Any]) -> None:
    scope = value.get("scope")
    candidates = [value, scope] if isinstance(scope, Mapping) else [value]
    for candidate in candidates:
        for key in _FORBIDDEN_TOP_LEVEL:
            if key not in candidate:
                continue
            item = candidate[key]
            if key == "deployment_target" and item == "NONE":
                continue
            if item in (False, 0, None, "NONE", "NO_PAID_SIDE_EFFECT"):
                continue
            code = {
                "batch": "BATCH_FORBIDDEN",
                "batches": "BATCH_FORBIDDEN",
                "batch_count": "BATCH_FORBIDDEN",
                "loop": "LOOP_FORBIDDEN",
                "loops": "LOOP_FORBIDDEN",
                "loop_count": "LOOP_FORBIDDEN",
                "deploy": "DEPLOY_FORBIDDEN",
                "deployment": "DEPLOY_FORBIDDEN",
                "deployment_target": "DEPLOY_FORBIDDEN",
                "provider": "PROVIDER_EXECUTION_FORBIDDEN",
                "provider_name": "PROVIDER_EXECUTION_FORBIDDEN",
                "provider_execution": "PROVIDER_EXECUTION_FORBIDDEN",
                "paid": "PAID_SIDE_EFFECT_FORBIDDEN",
                "payment": "PAID_SIDE_EFFECT_FORBIDDEN",
                "paid_generation": "PAID_SIDE_EFFECT_FORBIDDEN",
            }.get(key, "FORBIDDEN_SCOPE")
            raise ControlledProductionContractError(code)


def _validate_lineage_evidence(sample: ControlledProductionSample) -> None:
    for lineage in (sample.image_task, sample.video_task):
        if lineage.input_origin in {"OFFLINE_SYNTHETIC", "UNKNOWN"}:
            raise ControlledProductionContractError("SYNTHETIC_OR_UNKNOWN_INPUT")
        if lineage.cost_evidence == "PAID":
            raise ControlledProductionContractError("PAID_SIDE_EFFECT_FORBIDDEN")
        if lineage.cost_evidence == "UNKNOWN":
            raise ControlledProductionContractError("COST_EVIDENCE_UNKNOWN")
        if lineage.resolution_evidence == "UNKNOWN":
            raise ControlledProductionContractError("EXECUTION_EVIDENCE_UNKNOWN")
        if lineage.loop_count != 0:
            raise ControlledProductionContractError("LOOP_FORBIDDEN")
        if lineage.deployment_target != "NONE":
            raise ControlledProductionContractError("DEPLOY_FORBIDDEN")
        if any(reference.sha256 == sample.product.source_sha256
               and reference.source_kind != "REAL_PRODUCT"
               for reference in lineage.references):
            raise ControlledProductionContractError("SOURCE_ORIGIN_MISMATCH")


def _canonical_payload(sample: ControlledProductionSample) -> dict[str, Any]:
    return sample.model_dump(mode="json", exclude_none=True)


def _manifest_hash(payload: Mapping[str, Any]) -> str:
    return hashlib.sha256(
        json.dumps(
            payload,
            ensure_ascii=True,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()


def validate_controlled_production(
    value: ControlledProductionSample | Mapping[str, Any],
) -> ControlledProductionManifest:
    """Validate and build a deterministic, read-only single-sample manifest."""
    if isinstance(value, ControlledProductionSample):
        sample = value
    else:
        if not isinstance(value, Mapping):
            raise ControlledProductionContractError("CONTRACT_INPUT_INVALID")
        _reject_forbidden_input(value)
        try:
            sample = ControlledProductionSample.model_validate(value)
        except ValidationError as exc:
            missing = next(
                (error for error in exc.errors() if error.get("type") == "missing"),
                None,
            )
            code = "REQUIRED_FIELD_MISSING" if missing else "CONTRACT_INVALID"
            raise ControlledProductionContractError(code) from exc
    _validate_lineage_evidence(sample)
    payload = {
        "schema_version": "controlled-production-manifest.v1",
        "sample_id": sample.sample_id,
        "scope": "SINGLE_SAMPLE",
        "product": sample.product.model_dump(mode="json"),
        "image_task": sample.image_task.model_dump(mode="json"),
        "video_task": sample.video_task.model_dump(mode="json"),
    }
    return ControlledProductionManifest(
        **payload,
        manifest_hash=_manifest_hash(payload),
    )


def provider_request_lineage(
    request: Any,
) -> ProviderRequestLineage:
    """Project an existing image/video provider request into lineage identity."""
    try:
        return ProviderRequestLineage(
            request_kind=request.request_kind,
            creative_task_id=request.creative_task_id,
            owner_id=request.owner_id,
            package_revision_id=request.package_revision_id,
            shot_id=request.shot_id,
            source_mapping=request.source_mapping,
            idempotency_key=request.idempotency_key,
            bridge_validity_token=request.bridge_validity_token,
            evidence_hash=request.evidence_hash,
            request_hash=request.request_hash,
        )
    except (AttributeError, ValidationError) as exc:
        raise ControlledProductionContractError("PROVIDER_REQUEST_LINEAGE_INVALID") from exc


def build_controlled_production_manifest(
    value: ControlledProductionSample | Mapping[str, Any],
) -> ControlledProductionManifest:
    """Named manifest builder for callers that need an explicit audit artifact."""
    return validate_controlled_production(value)
