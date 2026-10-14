"""Compile a validated canonical creative revision into an image request.

This module owns the creative-to-image boundary only. It does not materialize
media, call a Provider, reserve quota, write task records, or change the
existing image execution contract.
"""
from __future__ import annotations

import json
from collections.abc import Sequence
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from libtv_agent.creative.state import (
    CameraState,
    CharacterContinuity,
    CharacterIdentity,
    CreativeStateRevision,
    ProductLocks,
    ProductSourceAsset,
    SceneEnvironment,
    SceneLighting,
    ShotState,
    SpatialState,
)
from libtv_agent.creative.state_revision import validate_revision_integrity

SHA256 = str


class ImageGenerationDiagnostic(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    severity: Literal["BLOCKED", "UNRESOLVED"]
    code: str = Field(min_length=1, max_length=120)
    message: str = Field(min_length=1, max_length=1000)
    shot_id: str | None = None


class ImageSourceReference(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    role: Literal["PRODUCT", "CHARACTER", "SCENE", "SPATIAL", "CAMERA"]
    reference_id: str = Field(min_length=1, max_length=240)
    revision: str = Field(min_length=1, max_length=240)
    source_refs: tuple[str, ...] = ()
    object_key: str | None = Field(default=None, max_length=500)
    sha256: SHA256 | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    evidence_refs: tuple[str, ...] = ()


class ImageReferenceManifest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    creative_state_id: str = Field(min_length=1, max_length=160)
    revision: int = Field(ge=1)
    shot_id: str = Field(min_length=1, max_length=160)
    source_references: tuple[ImageSourceReference, ...] = ()
    preservation_hash: SHA256 = Field(pattern=r"^[0-9a-f]{64}$")


class ImageGenerationRequest(BaseModel):
    """Provider-neutral image request consumed by a later execution adapter."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["creative-image-request.v1"] = "creative-image-request.v1"
    creative_state_id: str = Field(min_length=1, max_length=160)
    revision: int = Field(ge=1)
    content_hash: SHA256 = Field(pattern=r"^[0-9a-f]{64}$")
    locks_hash: SHA256 = Field(pattern=r"^[0-9a-f]{64}$")
    state_version: int = Field(ge=0)
    owner_id: str = Field(min_length=1, max_length=160)
    product_id: str = Field(min_length=1, max_length=160)
    product_version_id: str = Field(min_length=1, max_length=160)
    shot_id: str = Field(min_length=1, max_length=160)
    prompt_revision: str = Field(min_length=1, max_length=160)
    prompt: str = Field(min_length=1, max_length=12000)
    purpose: str = Field(min_length=1, max_length=500)
    action: str = Field(min_length=1, max_length=2000)
    entry_state: str | None = None
    exit_state: str | None = None
    product_references: tuple[ImageSourceReference, ...] = ()
    source_manifest: ImageReferenceManifest
    product_locks: ProductLocks
    product_preservation_constraints: tuple[str, ...] = ()
    character_identity: CharacterIdentity
    character_continuity: CharacterContinuity
    character_constraints: tuple[str, ...] = ()
    scene_environment: SceneEnvironment
    scene_lighting: SceneLighting
    scene_continuity: tuple[str, ...] = ()
    scene_constraints: tuple[str, ...] = ()
    spatial_constraints: SpatialState
    camera_intent: CameraState
    evidence_requirements: tuple[str, ...] = ()
    product_evidence: tuple[str, ...] = ()
    allowed_changes: tuple[str, ...] = ()
    forbidden_changes: tuple[str, ...] = ()
    idempotency_key: str = Field(min_length=1, max_length=500)
    preservation_hash: SHA256 = Field(pattern=r"^[0-9a-f]{64}$")
    provider_submission_allowed: Literal[False] = False


class ImageGenerationAdapterResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    status: Literal["READY", "BLOCKED", "UNRESOLVED"]
    request: ImageGenerationRequest | None = None
    diagnostics: tuple[ImageGenerationDiagnostic, ...] = ()

    @property
    def executable(self) -> bool:
        return self.status == "READY" and self.request is not None


def _revision_ref(identifier: str, revision: int) -> str:
    return f"{identifier}:r{revision}"


def _json(value: object) -> str:
    return json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":"))


def _product_preservation_constraints(
    locks: ProductLocks,
    source_assets: Sequence[ProductSourceAsset],
) -> tuple[str, ...]:
    constraints = [
        *locks.print_logo_text_constraints,
        *locks.color_constraints,
        *locks.garment_shape_constraints,
        *locks.forbidden_changes,
    ]
    constraints.extend(
        f"preserve source asset {asset.asset_id} exactly"
        for asset in source_assets
    )
    return tuple(dict.fromkeys(item for item in constraints if item.strip()))


def _compile_prompt(
    revision: CreativeStateRevision,
    shot: ShotState,
    *,
    product_assets: Sequence[ProductSourceAsset],
) -> str:
    character = revision.character
    scene = revision.scene
    spatial = revision.spatial
    camera = revision.camera
    assert character is not None
    assert scene is not None
    assert spatial is not None
    assert camera is not None

    sections = [
        f"Shot purpose: {shot.purpose}",
        "Render one still at the approved entry pose, with one hand-contact state. "
        "No before/after montage or action sequence.",
        f"Motion context for the later video only: {shot.action}",
        f"Product evidence: {', '.join(shot.product_evidence) or 'none specified'}",
        f"Product references: {', '.join(asset.object_key for asset in product_assets)}",
        f"Product locks: {_json(revision.product.locks.model_dump(mode='json'))}",
        f"Character identity: {_json(character.identity.model_dump(mode='json'))}",
        f"Character continuity: {_json(character.continuity.model_dump(mode='json'))}",
        f"Scene environment: {_json(scene.environment.model_dump(mode='json'))}",
        f"Scene lighting: {_json(scene.lighting.model_dump(mode='json'))}",
        f"Spatial relationships: {_json(spatial.relationships)}",
        (
            "Spatial camera relationship: "
            f"{', '.join(spatial.camera_relationship) or 'none specified'}"
        ),
        f"Camera intent: {_json(camera.model_dump(mode='json'))}",
        f"Allowed changes: {', '.join(shot.allowed_changes)}",
        f"Forbidden changes: {', '.join(shot.forbidden_changes)}",
    ]
    if shot.entry_state:
        sections.insert(1, f"Entry state: {shot.entry_state}")
    return "\n".join(sections)


def _diagnostic(
    diagnostics: list[ImageGenerationDiagnostic],
    severity: Literal["BLOCKED", "UNRESOLVED"],
    code: str,
    message: str,
    shot_id: str | None = None,
) -> None:
    diagnostics.append(
        ImageGenerationDiagnostic(
            severity=severity,
            code=code,
            message=message,
            shot_id=shot_id,
        )
    )


def compile_image_generation_request(
    revision: CreativeStateRevision,
    shot: ShotState,
) -> ImageGenerationAdapterResult:
    """Compile canonical creative truth without crossing the execution boundary."""
    diagnostics: list[ImageGenerationDiagnostic] = []
    try:
        validate_revision_integrity(revision)
    except ValueError as exc:
        _diagnostic(diagnostics, "BLOCKED", "REVISION_INTEGRITY_INVALID", str(exc), shot.shot_id)
        return ImageGenerationAdapterResult(status="BLOCKED", diagnostics=tuple(diagnostics))

    revision_shot = next(
        (candidate for candidate in revision.shots if candidate.shot_id == shot.shot_id),
        None,
    )
    if revision_shot is None or revision_shot != shot:
        _diagnostic(
            diagnostics,
            "BLOCKED",
            "SHOT_NOT_IN_REVISION",
            "selected ShotState is not the immutable shot stored in the revision",
            shot.shot_id,
        )
        return ImageGenerationAdapterResult(status="BLOCKED", diagnostics=tuple(diagnostics))

    product_assets = tuple(
        asset
        for asset in revision.product.source_assets
        if asset.materialized and not asset.revoked
    )
    if not product_assets:
        _diagnostic(
            diagnostics,
            "BLOCKED",
            "PRODUCT_REFERENCE_UNAVAILABLE",
            "ProductState has no materialized, non-revoked source reference",
            shot.shot_id,
        )
    if not shot.purpose.strip():
        _diagnostic(
            diagnostics,
            "UNRESOLVED",
            "SHOT_PURPOSE_MISSING",
            "shot purpose is missing; no shot intent was invented",
            shot.shot_id,
        )
    if not shot.action.strip():
        _diagnostic(
            diagnostics,
            "UNRESOLVED",
            "SHOT_ACTION_MISSING",
            "shot action is missing; no shot action was invented",
            shot.shot_id,
        )

    if revision.character is None or revision.character.origin == "UNRESOLVED":
        _diagnostic(
            diagnostics,
            "UNRESOLVED",
            "CHARACTER_REFERENCE_UNRESOLVED",
            "character identity is missing or unresolved; no identity was invented",
            shot.shot_id,
        )
    if revision.scene is None or revision.scene.origin == "UNRESOLVED":
        _diagnostic(
            diagnostics,
            "UNRESOLVED",
            "SCENE_REFERENCE_UNRESOLVED",
            "scene environment is missing or unresolved; no scene was invented",
            shot.shot_id,
        )
    if revision.camera is None:
        _diagnostic(
            diagnostics,
            "UNRESOLVED",
            "CAMERA_REFERENCE_UNRESOLVED",
            "camera intent is missing; no camera rule was invented",
            shot.shot_id,
        )
    expected_inherited_revisions = {
        "product": revision.product.product_version_id,
        "character": (
            _revision_ref(revision.character.character_id, revision.character.revision)
            if revision.character is not None
            else None
        ),
        "scene": (
            _revision_ref(revision.scene.scene_id, revision.scene.revision)
            if revision.scene is not None
            else None
        ),
        "spatial": (
            _revision_ref(revision.spatial.spatial_id, revision.spatial.revision)
            if revision.spatial is not None
            else None
        ),
        "camera": (
            _revision_ref(revision.camera.camera_id, revision.camera.revision)
            if revision.camera is not None
            else None
        ),
    }
    actual_inherited_revisions = {
        "product": shot.inherited_product_revision,
        "character": shot.inherited_character_revision,
        "scene": shot.inherited_scene_revision,
        "spatial": shot.inherited_spatial_revision,
        "camera": shot.inherited_camera_revision,
    }
    for state_name, expected_revision in expected_inherited_revisions.items():
        actual_revision = actual_inherited_revisions[state_name]
        if expected_revision != actual_revision:
            _diagnostic(
                diagnostics,
                "UNRESOLVED",
                f"{state_name.upper()}_INHERITANCE_MISMATCH",
                (
                    f"shot inherited {state_name} revision "
                    f"{actual_revision!r}, expected {expected_revision!r}"
                ),
                shot.shot_id,
            )
    if revision.spatial is None or not revision.spatial.provider_submission_allowed:
        _diagnostic(
            diagnostics,
            "BLOCKED",
            "SPATIAL_STATE_BLOCKED",
            "SpatialState is missing or provider submission is not validated",
            shot.shot_id,
        )
    if shot.action_capabilities.status in {"UNRESOLVED", "BLOCKED"}:
        _diagnostic(
            diagnostics,
            "BLOCKED",
            "ACTION_CAPABILITIES_UNRESOLVED",
            "shot action capabilities are not validated",
            shot.shot_id,
        )
    if not shot.prompt_refs.image_prompt_revision:
        _diagnostic(
            diagnostics,
            "UNRESOLVED",
            "IMAGE_PROMPT_REVISION_MISSING",
            "shot has no immutable image prompt revision",
            shot.shot_id,
        )
    preservation_hash = shot.prompt_refs.preservation_hash
    if not preservation_hash:
        _diagnostic(
            diagnostics,
            "UNRESOLVED",
            "PRESERVATION_HASH_MISSING",
            "shot has no preservation hash",
            shot.shot_id,
        )

    if diagnostics:
        status: Literal["BLOCKED", "UNRESOLVED"] = (
            "BLOCKED"
            if any(item.severity == "BLOCKED" for item in diagnostics)
            else "UNRESOLVED"
        )
        return ImageGenerationAdapterResult(status=status, diagnostics=tuple(diagnostics))

    assert revision.character is not None
    assert revision.scene is not None
    assert revision.spatial is not None
    assert revision.camera is not None
    assert preservation_hash is not None
    assert shot.prompt_refs.image_prompt_revision is not None

    product_refs = tuple(
        ImageSourceReference(
            role="PRODUCT",
            reference_id=asset.asset_id,
            revision=revision.product.product_version_id,
            source_refs=(asset.asset_id, asset.object_key),
            object_key=asset.object_key,
            sha256=asset.sha256,
            evidence_refs=(asset.evidence_status,),
        )
        for asset in product_assets
    )
    source_references = (
        *product_refs,
        ImageSourceReference(
            role="CHARACTER",
            reference_id=revision.character.character_id,
            revision=_revision_ref(
                revision.character.character_id, revision.character.revision
            ),
            source_refs=(
                revision.character.character_id,
                *revision.character.evidence_refs,
            ),
            evidence_refs=revision.character.evidence_refs,
        ),
        ImageSourceReference(
            role="SCENE",
            reference_id=revision.scene.scene_id,
            revision=_revision_ref(revision.scene.scene_id, revision.scene.revision),
            source_refs=(revision.scene.scene_id, *revision.scene.evidence_refs),
            evidence_refs=revision.scene.evidence_refs,
        ),
        ImageSourceReference(
            role="SPATIAL",
            reference_id=revision.spatial.spatial_id,
            revision=_revision_ref(
                revision.spatial.spatial_id, revision.spatial.revision
            ),
            source_refs=(revision.spatial.spatial_id, *revision.spatial.evidence_refs),
            evidence_refs=revision.spatial.evidence_refs,
        ),
        ImageSourceReference(
            role="CAMERA",
            reference_id=revision.camera.camera_id,
            revision=_revision_ref(
                revision.camera.camera_id, revision.camera.revision
            ),
            source_refs=(
                revision.camera.camera_id,
                *revision.camera.scene_geometry_refs,
                *revision.camera.evidence_refs,
            ),
            evidence_refs=revision.camera.evidence_refs,
        ),
    )
    manifest = ImageReferenceManifest(
        creative_state_id=revision.creative_state_id,
        revision=revision.revision,
        shot_id=shot.shot_id,
        source_references=source_references,
        preservation_hash=preservation_hash,
    )
    prompt = _compile_prompt(revision, shot, product_assets=product_assets)
    request = ImageGenerationRequest(
        creative_state_id=revision.creative_state_id,
        revision=revision.revision,
        content_hash=revision.content_hash,
        locks_hash=revision.locks_hash,
        state_version=revision.state_version,
        owner_id=revision.product.owner_id,
        product_id=revision.product.product_id,
        product_version_id=revision.product.product_version_id,
        shot_id=shot.shot_id,
        prompt_revision=shot.prompt_refs.image_prompt_revision,
        prompt=prompt,
        purpose=shot.purpose,
        action=shot.action,
        entry_state=shot.entry_state,
        exit_state=shot.exit_state,
        product_references=product_refs,
        source_manifest=manifest,
        product_locks=revision.product.locks,
        product_preservation_constraints=_product_preservation_constraints(
            revision.product.locks, product_assets
        ),
        character_identity=revision.character.identity,
        character_continuity=revision.character.continuity,
        character_constraints=revision.character.constraints,
        scene_environment=revision.scene.environment,
        scene_lighting=revision.scene.lighting,
        scene_continuity=revision.scene.continuity,
        scene_constraints=revision.scene.constraints,
        spatial_constraints=revision.spatial,
        camera_intent=revision.camera,
        evidence_requirements=(
            *revision.product.truth.source_fact_keys,
            *shot.product_evidence,
        ),
        product_evidence=shot.product_evidence,
        allowed_changes=shot.allowed_changes,
        forbidden_changes=shot.forbidden_changes,
        idempotency_key=(
            f"creative-image:{revision.creative_state_id}:"
            f"r{revision.revision}:{shot.shot_id}"
        ),
        preservation_hash=preservation_hash,
    )
    return ImageGenerationAdapterResult(status="READY", request=request)
