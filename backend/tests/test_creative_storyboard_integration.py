from __future__ import annotations

from libtv_agent.creative.state import CharacterIdentity, CreativeStateRevision
from libtv_agent.creative.state_adapters import (
    compile_storyboard_state,
    validate_storyboard_state,
)
from libtv_agent.creative.state_projection import project_creative_state
from libtv_agent.creative.state_revision import (
    calculate_locks_hash,
    calculate_source_snapshot_hash,
    seal_revision,
)


def product_payload() -> dict:
    return {
        "product_id": "product-1",
        "product_version_id": "version-1",
        "internal_sku_id": "sku-1",
        "facts_revision": 3,
        "truth_fields": {"color": "black"},
        "immutable_fields": {"logo": "preserve exactly"},
        "source_asset_references": ["asset-front"],
    }


def storyboard_snapshot() -> dict:
    return {
        "creative_task_id": "task-1",
        "plan": {
            "intent": "Make the garment feel useful in a real morning routine.",
            "hook": "A quick turn reveals the front graphic.",
            "emotional_progression": ["curiosity", "confidence"],
            "product_evidence": ["front graphic", "oversized silhouette"],
            "cta_purpose": "Invite the viewer to explore the product.",
            "selected_direction": "A",
            "directions": [
                {
                    "id": "A",
                    "summary": "A grounded morning routine.",
                    "behavior": "turn naturally",
                    "camera": "eye-level medium frame",
                }
            ],
        },
        "storyboard": {
            "shot_order": ["SHOT_01", "SHOT_02"],
            "packages": {
                "SHOT_02": {
                    "package_id": "package-2",
                    "purpose": "VIDEO_STORYBOARD",
                    "shot_purpose": "CTA",
                    "order": 2,
                    "durationSeconds": 2.5,
                    "entryState": "standing by the door",
                    "action": "take one step toward the exit",
                    "exitState": "hold on the garment",
                    "cameraLanguage": "slow lateral follow",
                    "requiredCapabilities": ["forward_step_space"],
                    "actionCapabilities": {
                        "confirmed": ["forward_step_space"],
                        "status": "VALIDATED",
                    },
                },
                "SHOT_01": {
                    "package_id": "package-1",
                    "purpose": "VIDEO_STORYBOARD",
                    "shot_purpose": "Hook",
                    "order": 1,
                    "duration_seconds": 1.5,
                    "entry_state": "neutral stance",
                    "action": "turn naturally",
                    "exit_state": "front graphic readable",
                    "camera": "eye-level medium frame",
                    "product_evidence": ["front graphic"],
                },
            },
        },
    }


def resolved_refs() -> dict[str, str]:
    return {
        "character_revision": "character-1:r2",
        "scene_revision": "scene-1:r1",
        "spatial_revision": "spatial-1:r3",
        "camera_revision": "camera-1:r4",
    }


def test_director_package_compiles_campaign_and_multiple_canonical_shots() -> None:
    storyboard, shots = compile_storyboard_state(
        storyboard_snapshot(),
        product_version_id="version-1",
        **resolved_refs(),
    )

    assert storyboard.campaign.intent.startswith("Make the garment")
    assert storyboard.campaign.hook.startswith("A quick turn")
    assert storyboard.shot_order == ("SHOT_01", "SHOT_02")
    assert [shot.shot_id for shot in shots] == ["SHOT_01", "SHOT_02"]
    assert shots[0].purpose == "Hook"
    assert shots[1].duration_seconds == 2.5
    assert shots[1].camera_language == "slow lateral follow"
    assert shots[1].entry_state == "standing by the door"
    assert shots[1].exit_state == "hold on the garment"
    assert shots[1].inherited_spatial_revision == "spatial-1:r3"
    assert shots[1].action_capabilities.status == "VALIDATED"


def test_continuity_rules_survive_revision_sealing() -> None:
    storyboard, shots = compile_storyboard_state(
        storyboard_snapshot(),
        product_version_id="version-1",
        **resolved_refs(),
    )
    storyboard = storyboard.model_copy(
        update={
            "continuity_rules": (
                "pose, expression, movement and framing may change",
                "identity, environment and product locks may not change",
            )
        }
    )
    from libtv_agent.creative.state_adapters import adapt_product_state

    product = adapt_product_state(product_payload(), owner_id="owner-1")
    revision = seal_revision(
        CreativeStateRevision(
            creative_state_id="state-1",
            revision=1,
            state_version=0,
            facts_revision=product.truth.facts_revision,
            content_hash="0" * 64,
            locks_hash=calculate_locks_hash(product),
            source_snapshot_hash=calculate_source_snapshot_hash(product),
            created_by="owner-1",
            created_at="2026-10-13T00:00:00Z",
            reason="storyboard integration test",
            product=product,
            storyboard=storyboard,
            shots=tuple(shots),
        )
    )

    assert revision.storyboard.continuity_rules[0].startswith("pose")
    assert revision.shots[0].forbidden_changes == (
        "IDENTITY_DRIFT",
        "ENVIRONMENT_REDESIGN",
        "PRODUCT_REDESIGN",
        "LOCK_BREAK",
    )


def test_missing_spatial_is_explicit_and_blocks_execution() -> None:
    task = {
        "id": "task-1",
        "user_id": "owner-1",
        "snapshot_json": storyboard_snapshot(),
    }
    projection = project_creative_state(
        creative_task=task,
        product_version=product_payload(),
        owner_id="owner-1",
        intelligence_snapshot={
            "characterDNA": {
                "id": "character-1",
                "revision": 2,
                "origin": "USER_CONFIRMED",
                "identity": CharacterIdentity(face_structure=("oval face",)).model_dump(
                    mode="json"
                ),
            },
            "sceneDNA": {
                "id": "scene-1",
                "revision": 1,
                "origin": "PROPOSED",
            },
        },
    )

    assert projection.state is not None
    assert projection.state.spatial is None
    assert projection.state.status == "BLOCKED"
    assert not projection.executable
    assert any(
        item.code == "SPATIAL_SUBMISSION_BLOCKED" for item in projection.diagnostics
    )
    assert "spatial" in projection.state.storyboard.unresolved_references


def test_validation_requires_inherited_references_without_inventing_them() -> None:
    storyboard, shots = compile_storyboard_state(
        storyboard_snapshot(),
        product_version_id="version-1",
    )
    result = validate_storyboard_state(
        storyboard,
        shots,
        product_revision="version-1",
        character_revision=None,
        scene_revision=None,
        spatial=None,
        camera_revision=None,
    )

    assert not result.executable
    assert {"character", "scene", "spatial", "camera"} <= set(
        result.unresolved_references
    )
    assert any(item.code == "SPATIAL_SUBMISSION_BLOCKED" for item in result.issues)
