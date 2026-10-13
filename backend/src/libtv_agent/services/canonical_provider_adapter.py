"""Read-only adapter from canonical image truth to the existing Provider boundary.

The canonical request owns creative identity and shot intent. The existing
Provider contract still owns execution evidence, task identity, source
mapping, and lifecycle fields. This module keeps those responsibilities
separate while providing a deterministic dry-run preview.
"""
from __future__ import annotations

import hashlib
from typing import Literal

from libtv_agent.creative.image_generation_adapter import (
    ImageGenerationRequest,
    ImageSourceReference,
)
from libtv_agent.creative.workflow import digest
from libtv_agent.services.creative_provider_requests import (
    CanonicalProduct,
    CreativeImageProviderRequest,
    ImagePredictionParameters,
    ImageProviderOptions,
    LockedProviderPrompt,
    ProviderReference,
    RunMode,
    SourceMapping,
)
from pydantic import BaseModel, ConfigDict, Field

SHA256 = str


class ProviderAdapterDiagnostic(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    severity: Literal["BLOCKED", "UNRESOLVED"]
    code: str = Field(min_length=1, max_length=120)
    message: str = Field(min_length=1, max_length=1000)


class ProviderReferencePreview(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    role: Literal["PRODUCT", "CHARACTER", "SCENE", "SPATIAL", "CAMERA"]
    reference_id: str = Field(min_length=1, max_length=240)
    revision: str = Field(min_length=1, max_length=240)
    source_refs: tuple[str, ...] = ()
    object_key: str | None = Field(default=None, max_length=500)
    sha256: SHA256 | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    adapter_field: str | None = None
    materialization_required: bool = True


class ProviderRequestCompilationContext(BaseModel):
    """Execution-owned values required to instantiate the old Provider contract."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    creative_task_id: str = Field(min_length=1, max_length=160)
    package_revision_id: str = Field(min_length=1, max_length=160)
    source_mapping: SourceMapping
    idempotency_key: str = Field(min_length=1, max_length=500)
    bridge_validity_token: SHA256 = Field(pattern=r"^[0-9a-f]{64}$")
    evidence_hash: SHA256 = Field(pattern=r"^[0-9a-f]{64}$")
    text_contract_hash: SHA256 = Field(pattern=r"^[0-9a-f]{64}$")
    text_contract_json: str = Field(min_length=2, max_length=50000)
    run_mode: RunMode = "dry-run"


class ProviderRequestPreview(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["creative-provider-preview.v1"] = (
        "creative-provider-preview.v1"
    )
    provider: Literal["gpt", "nanobanana"]
    model: str = Field(min_length=1, max_length=240)
    creative_state_id: str = Field(min_length=1, max_length=160)
    revision: int = Field(ge=1)
    content_hash: SHA256 = Field(pattern=r"^[0-9a-f]{64}$")
    shot_id: str = Field(min_length=1, max_length=160)
    prompt: str = Field(min_length=1, max_length=12000)
    prompt_hash: SHA256 = Field(pattern=r"^[0-9a-f]{64}$")
    preservation_hash: SHA256 = Field(pattern=r"^[0-9a-f]{64}$")
    locks_hash: SHA256 = Field(pattern=r"^[0-9a-f]{64}$")
    references: tuple[ProviderReferencePreview, ...]
    lock_constraints: tuple[str, ...] = ()
    forbidden_changes: tuple[str, ...] = ()
    validation: Literal["READY", "BLOCKED", "UNRESOLVED"]
    provider_contract_ready: bool = False
    provider_submission_allowed: Literal[False] = False
    provider_request: CreativeImageProviderRequest | None = None


class ProviderAdapterResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    status: Literal["READY", "BLOCKED", "UNRESOLVED"]
    preview: ProviderRequestPreview | None = None
    diagnostics: tuple[ProviderAdapterDiagnostic, ...] = ()

    @property
    def executable(self) -> bool:
        return False


def _diagnostic(
    diagnostics: list[ProviderAdapterDiagnostic],
    severity: Literal["BLOCKED", "UNRESOLVED"],
    code: str,
    message: str,
) -> None:
    diagnostics.append(
        ProviderAdapterDiagnostic(severity=severity, code=code, message=message)
    )


def _preview_reference(
    reference: ImageSourceReference,
) -> ProviderReferencePreview:
    return ProviderReferencePreview(
        role=reference.role,
        reference_id=reference.reference_id,
        revision=reference.revision,
        source_refs=reference.source_refs,
        object_key=reference.object_key,
        sha256=reference.sha256,
        adapter_field="images" if reference.role == "PRODUCT" else None,
    )


def _prediction_options(
    request: ImageGenerationRequest,
    provider: Literal["gpt", "nanobanana"],
) -> tuple[ImageProviderOptions, str, ImagePredictionParameters]:
    options = ImageProviderOptions(provider=provider)
    product_objects = [
        reference.object_key
        for reference in request.product_references
        if reference.object_key is not None
    ]
    if len(product_objects) != len(request.product_references):
        raise ValueError("product references require object keys")
    from libtv_agent.services.image_generations import build_prediction_payload

    model, parameters = build_prediction_payload(
        provider=provider,
        prompt=request.prompt,
        image_urls=product_objects,
        aspect_ratio=options.aspect_ratio,
        resolution=options.resolution,
        quality=options.quality,
        output_format=options.output_format,
    )
    parameters.pop("images", None)
    return options, model, ImagePredictionParameters.model_validate(parameters)


def _compile_existing_contract(
    request: ImageGenerationRequest,
    *,
    provider: Literal["gpt", "nanobanana"],
    context: ProviderRequestCompilationContext,
) -> CreativeImageProviderRequest:
    if request.shot_id not in {"FIRST_FRAME", "SHOT_01"}:
        raise ValueError("existing Provider contract does not support this shot ID")
    if context.source_mapping.shot_id != request.shot_id:
        raise ValueError("source mapping shot ID does not match canonical shot ID")
    product_references = tuple(
        reference
        for reference in request.product_references
        if reference.role == "PRODUCT"
    )
    if len(product_references) != 1:
        raise ValueError(
            "existing image Provider contract requires exactly one product reference"
        )
    product = product_references[0]
    if product.object_key is None or product.sha256 is None:
        raise ValueError("product reference is missing materialization identity")
    options, model, parameters = _prediction_options(request, provider)
    locked_prompt = LockedProviderPrompt(
        prompt=request.prompt,
        prompt_hash=hashlib.sha256(request.prompt.encode("utf-8")).hexdigest(),
        preservation_hash=request.preservation_hash,
        locks_hash=request.locks_hash,
        text_contract_hash=context.text_contract_hash,
        text_contract_json=context.text_contract_json,
    )
    compiled = CreativeImageProviderRequest(
        creative_task_id=context.creative_task_id,
        owner_id=request.owner_id,
        state_version=request.state_version,
        package_revision_id=context.package_revision_id,
        shot_id=request.shot_id,
        source_mapping=context.source_mapping,
        canonical_product=CanonicalProduct(
            product_id=request.product_id,
            product_version_id=request.product_version_id,
            owner_id=request.owner_id,
            object_key=product.object_key,
            sha256=product.sha256,
        ),
        locked_prompt=locked_prompt,
        references=(
            ProviderReference(
                role="PRODUCT",
                order=1,
                adapter_field="images",
                object_key=product.object_key,
                sha256=product.sha256,
            ),
        ),
        idempotency_key=context.idempotency_key,
        bridge_validity_token=context.bridge_validity_token,
        evidence_hash=context.evidence_hash,
        request_hash="0" * 64,
        run_mode=context.run_mode,
        provider=provider,
        model=model,
        options=options,
        adapter_parameters=parameters,
    )
    return compiled.model_copy(
        update={
            "request_hash": digest(
                compiled.model_dump(mode="json", exclude={"request_hash"})
            )
        }
    )


def compile_provider_request_preview(
    request: ImageGenerationRequest,
    *,
    provider: Literal["gpt", "nanobanana"] = "gpt",
    context: ProviderRequestCompilationContext | None = None,
) -> ProviderAdapterResult:
    """Validate and preview the canonical request at the existing Provider boundary."""
    diagnostics: list[ProviderAdapterDiagnostic] = []
    manifest = request.source_manifest
    if (
        manifest.creative_state_id != request.creative_state_id
        or manifest.revision != request.revision
        or manifest.shot_id != request.shot_id
        or manifest.preservation_hash != request.preservation_hash
    ):
        _diagnostic(
            diagnostics,
            "BLOCKED",
            "CANONICAL_MANIFEST_MISMATCH",
            "source manifest identity does not match the canonical image request",
        )
    role_map = {reference.role: reference for reference in manifest.source_references}
    required_roles = {"PRODUCT", "CHARACTER", "SCENE", "SPATIAL", "CAMERA"}
    missing_roles = sorted(required_roles - role_map.keys())
    if missing_roles:
        _diagnostic(
            diagnostics,
            "UNRESOLVED",
            "CANONICAL_REFERENCE_UNRESOLVED",
            f"canonical request is missing references: {', '.join(missing_roles)}",
        )
    if (
        request.spatial_constraints is None
        or not request.spatial_constraints.provider_submission_allowed
    ):
        _diagnostic(
            diagnostics,
            "BLOCKED",
            "SPATIAL_STATE_BLOCKED",
            "SpatialState is blocked and cannot cross the Provider boundary",
        )
    if (
        request.camera_intent is None
        or not request.camera_intent.camera_id
        or "CAMERA" not in role_map
    ):
        _diagnostic(
            diagnostics,
            "UNRESOLVED",
            "CAMERA_REFERENCE_UNRESOLVED",
            "camera reference is missing; no camera intent was invented",
        )
    if not request.shot_id.strip():
        _diagnostic(
            diagnostics,
            "BLOCKED",
            "SHOT_ID_INVALID",
            "canonical request has no valid shot ID",
        )
    product_refs = [
        reference for reference in request.product_references if reference.role == "PRODUCT"
    ]
    if not product_refs:
        _diagnostic(
            diagnostics,
            "BLOCKED",
            "PRODUCT_REFERENCE_UNAVAILABLE",
            "canonical request has no product source reference",
        )
    elif any(
        role_map.get("PRODUCT") is None
        or reference.reference_id != role_map["PRODUCT"].reference_id
        or reference.object_key != role_map["PRODUCT"].object_key
        or reference.sha256 != role_map["PRODUCT"].sha256
        for reference in product_refs
    ):
        _diagnostic(
            diagnostics,
            "BLOCKED",
            "PRODUCT_MANIFEST_MISMATCH",
            "ProductState reference does not match the manifest source reference",
        )
    status: Literal["READY", "BLOCKED", "UNRESOLVED"] = (
        "BLOCKED"
        if any(item.severity == "BLOCKED" for item in diagnostics)
        else "UNRESOLVED"
        if diagnostics
        else "READY"
    )
    if diagnostics:
        return ProviderAdapterResult(status=status, diagnostics=tuple(diagnostics))

    options, model, _ = _prediction_options(request, provider)
    references = tuple(
        _preview_reference(reference) for reference in manifest.source_references
    )
    preview = ProviderRequestPreview(
        provider=options.provider,
        model=model,
        creative_state_id=request.creative_state_id,
        revision=request.revision,
        content_hash=request.content_hash,
        shot_id=request.shot_id,
        prompt=request.prompt,
        prompt_hash=hashlib.sha256(request.prompt.encode("utf-8")).hexdigest(),
        preservation_hash=request.preservation_hash,
        locks_hash=request.locks_hash,
        references=references,
        lock_constraints=request.product_preservation_constraints,
        forbidden_changes=request.forbidden_changes,
        validation=status,
    )
    if context is not None:
        try:
            provider_request = _compile_existing_contract(
                request, provider=provider, context=context
            )
        except ValueError as exc:
            _diagnostic(
                diagnostics,
                "UNRESOLVED",
                "EXISTING_PROVIDER_CONTRACT_UNRESOLVED",
                str(exc),
            )
            return ProviderAdapterResult(
                status="UNRESOLVED",
                preview=preview,
                diagnostics=tuple(diagnostics),
            )
        preview = preview.model_copy(
            update={
                "provider_contract_ready": True,
                "provider_request": provider_request,
            }
        )
    return ProviderAdapterResult(status="READY", preview=preview)
