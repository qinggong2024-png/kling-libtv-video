from __future__ import annotations

import pytest
from libtv_agent.creative.image_generation_adapter import (
    compile_image_generation_request,
)
from libtv_agent.creative.state import (
    ActionCapabilityState,
    CameraFraming,
    CameraState,
    CharacterContinuity,
    CharacterIdentity,
    CharacterState,
    CreativeStateRevision,
    ProductLocks,
    ProductSourceAsset,
    ProductState,
    ProductTruth,
    SceneEnvironment,
    SceneLighting,
    SceneState,
    ShotPromptRefs,
    ShotState,
    SpatialState,
    StoryboardState,
)
from libtv_agent.creative.state_revision import (
    calculate_locks_hash,
    calculate_source_snapshot_hash,
    seal_revision,
)

_UNSET = object()


def _product() -> ProductState:
    return ProductState(
        product_id="product-1",
        product_version_id="version-1",
        owner_id="owner-1",
        source_assets=(
            ProductSourceAsset(
                asset_id="asset-front",
                object_key="products/product-1/front.png",
                sha256="a" * 64,
                view="front",
                evidence_status="USER_CONFIRMED",
                materialized=True,
            ),
        ),
        truth=ProductTruth(
            known_attributes={"color": "black", "shape": "oversized"},
            source_fact_keys=("asset-front", "front graphic"),
            facts_revision=3,
        ),
        locks=ProductLocks(
            immutable_attributes={"logo": "preserve exactly"},
            color_constraints=("preserve black color",),
            garment_shape_constraints=("preserve oversized silhouette",),
            forbidden_changes=("do not redesign the garment",),
        ),
    )


def _character() -> CharacterState:
    return CharacterState(
        character_id="character-1",
        revision=2,
        origin="USER_CONFIRMED",
        identity=CharacterIdentity(
            face_structure=("oval face",),
            age_appearance="adult",
        ),
        continuity=CharacterContinuity(
            wardrobe=("approved black garment",),
            recurring_traits=("calm expression",),
        ),
        evidence_refs=("character-reference-1",),
    )


def _scene() -> SceneState:
    return SceneState(
        scene_id="scene-1",
        revision=1,
        origin="PROPOSED",
        environment=SceneEnvironment(
            location="bright studio",
            description="A quiet studio corner with a clear background.",
        ),
        lighting=SceneLighting(source="large window", quality="soft"),
        evidence_refs=("scene-reference-1",),
    )


def _spatial(*, provider_submission_allowed: bool = True) -> SpatialState:
    return SpatialState(
        spatial_id="spatial-1",
        revision=3,
        coordinate_system="IMAGE_NORMALIZED_2D",
        subject_depth="midground",
        camera_relationship=("keep the subject centered in frame",),
        evidence_refs=("spatial-reference-1",),
        provider_submission_allowed=provider_submission_allowed,
    )


def _camera() -> CameraState:
    return CameraState(
        camera_id="camera-1",
        revision=4,
        position="eye level",
        framing=CameraFraming(
            shot_size="medium",
            aspect_ratio="9:16",
            subject_placement="center",
        ),
        evidence_refs=("camera-reference-1",),
    )


def _shot(shot_id: str = "SHOT_01", order: int = 1) -> ShotState:
    return ShotState(
        shot_id=shot_id,
        order=order,
        purpose="Hook" if order == 1 else "Product proof",
        action="turn naturally" if order == 1 else "hold on the front graphic",
        product_evidence=("front graphic",),
        inherited_product_revision="version-1",
        inherited_character_revision="character-1:r2",
        inherited_scene_revision="scene-1:r1",
        inherited_spatial_revision="spatial-1:r3",
        inherited_camera_revision="camera-1:r4",
        action_capabilities=ActionCapabilityState(status="VALIDATED"),
        prompt_refs=ShotPromptRefs(
            image_prompt_revision=f"package-{shot_id.lower()}",
            preservation_hash=("b" if order == 1 else "c") * 64,
        ),
    )


def _revision(
    *,
    shots: tuple[ShotState, ...] | None = None,
    character: CharacterState | None | object = _UNSET,
    scene: SceneState | None | object = _UNSET,
    spatial: SpatialState | None | object = _UNSET,
) -> CreativeStateRevision:
    product = _product()
    selected_shots = shots or (_shot(),)
    storyboard = StoryboardState(
        storyboard_id="storyboard-1",
        revision=1,
        campaign={
            "intent": "Show the garment clearly in a real moment.",
            "hook": "A quick turn reveals the front graphic.",
            "product_evidence": ("front graphic",),
        },
        shot_order=tuple(shot.shot_id for shot in selected_shots),
        continuity_rules=(
            "pose, expression, movement and framing may change",
            "identity, environment and product locks may not change",
        ),
    )
    return seal_revision(
        CreativeStateRevision(
            creative_state_id="creative-state-1",
            revision=7,
            state_version=12,
            facts_revision=product.truth.facts_revision,
            content_hash="0" * 64,
            locks_hash=calculate_locks_hash(product),
            source_snapshot_hash=calculate_source_snapshot_hash(product),
            created_by="owner-1",
            created_at="2026-10-13T00:00:00Z",
            reason="image adapter test",
            product=product,
            character=_character() if character is _UNSET else character,
            scene=_scene() if scene is _UNSET else scene,
            spatial=_spatial() if spatial is _UNSET else spatial,
            camera=_camera(),
            storyboard=storyboard,
            shots=selected_shots,
        )
    )


def test_compiles_revision_and_shot_into_provider_neutral_image_request() -> None:
    revision = _revision()

    result = compile_image_generation_request(revision, revision.shots[0])

    assert result.status == "READY"
    assert result.executable
    assert result.request is not None
    assert result.request.creative_state_id == "creative-state-1"
    assert result.request.revision == 7
    assert result.request.shot_id == "SHOT_01"
    assert result.request.provider_submission_allowed is False
    assert result.request.prompt_revision == "package-shot_01"
    assert "Shot purpose: Hook" in result.request.prompt
    assert "Motion context for the later video only: turn naturally" in result.request.prompt
    assert "one still at the approved entry pose" in result.request.prompt
    assert "Exit state:" not in result.request.prompt


def test_preserves_state_references_and_manifest_identity() -> None:
    first = _shot("SHOT_01", 1)
    second = _shot("SHOT_02", 2)
    revision = _revision(shots=(first, second))

    result = compile_image_generation_request(revision, revision.shots[1])

    assert result.request is not None
    request = result.request
    assert request.shot_id == "SHOT_02"
    assert request.product_references[0].reference_id == "asset-front"
    assert request.character_identity.face_structure == ("oval face",)
    assert request.scene_environment.location == "bright studio"
    assert request.spatial_constraints.spatial_id == "spatial-1"
    assert request.camera_intent.camera_id == "camera-1"
    assert request.source_manifest.creative_state_id == "creative-state-1"
    assert request.source_manifest.revision == 7
    assert request.source_manifest.shot_id == "SHOT_02"
    assert {
        reference.role for reference in request.source_manifest.source_references
    } == {"PRODUCT", "CHARACTER", "SCENE", "SPATIAL", "CAMERA"}
    assert request.source_manifest.preservation_hash == "c" * 64
    assert request.preservation_hash == "c" * 64


def test_blocked_spatial_state_prevents_image_request() -> None:
    revision = _revision(spatial=_spatial(provider_submission_allowed=False))

    result = compile_image_generation_request(revision, revision.shots[0])

    assert result.status == "BLOCKED"
    assert not result.executable
    assert result.request is None
    assert any(item.code == "SPATIAL_STATE_BLOCKED" for item in result.diagnostics)


@pytest.mark.parametrize(
    ("field", "code"),
    (
        ("character", "CHARACTER_REFERENCE_UNRESOLVED"),
        ("scene", "SCENE_REFERENCE_UNRESOLVED"),
    ),
)
def test_missing_identity_or_scene_is_explicitly_unresolved(
    field: str,
    code: str,
) -> None:
    kwargs = {field: None}
    revision = _revision(**kwargs)
    shot = revision.shots[0]

    result = compile_image_generation_request(revision, shot)

    assert result.status == "UNRESOLVED"
    assert result.request is None
    assert any(item.code == code for item in result.diagnostics)


def test_foreign_shot_cannot_be_compiled_against_revision() -> None:
    revision = _revision()
    foreign_shot = revision.shots[0].model_copy(update={"action": "invented action"})

    result = compile_image_generation_request(revision, foreign_shot)

    assert result.status == "BLOCKED"
    assert any(item.code == "SHOT_NOT_IN_REVISION" for item in result.diagnostics)
