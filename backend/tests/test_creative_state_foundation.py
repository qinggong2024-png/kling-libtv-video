from __future__ import annotations

import pytest
from libtv_agent.creative.state import (
    CreativeStateRevision,
    QualityState,
    ShotState,
    StoryboardState,
)
from libtv_agent.creative.state_adapters import (
    adapt_product_state,
    adapt_storyboard_state,
)
from libtv_agent.creative.state_projection import project_creative_state
from libtv_agent.creative.state_revision import (
    calculate_locks_hash,
    calculate_revision_hash,
    calculate_source_snapshot_hash,
    seal_revision,
    validate_revision_integrity,
)
from pydantic import ValidationError


def product_payload() -> dict:
    return {
        "product_id": "product-1",
        "product_version_id": "version-1",
        "internal_sku_id": "sku-1",
        "facts_revision": 3,
        "truth_fields": {"color": "black", "shape": "oversized"},
        "immutable_fields": {"logo": "preserve exactly"},
        "allowed_variation": ["pose", "camera"],
        "source_asset_references": ["asset-front"],
        "license_status": "UNKNOWN",
    }


def creative_snapshot() -> dict:
    return {
        "product_version": product_payload(),
        "asset": {
            "asset_id": "asset-front",
            "object_key": "products/product-1/front.png",
            "sha256": "a" * 64,
            "materialized": True,
        },
        "plan": {
            "facts_revision": 3,
            "selected_direction": "A",
            "directions": [
                {
                    "id": "A",
                    "title": "Quiet product moment",
                    "summary": "A clear garment first frame",
                    "scene": "bright studio",
                    "behavior": "turn naturally",
                    "camera": "eye level",
                    "emotion": "calm",
                },
            ],
        },
        "package": {
            "package_id": "package-first-frame",
            "revision": 1,
            "purpose": "FIRST_FRAME",
            "shot_id": "FIRST_FRAME",
            "preservation_hash": "b" * 64,
            "prompt": "Preserve the product and show the garment clearly.",
        },
        "storyboard": {
            "packages": {
                "SHOT_01": {
                    "package_id": "package-shot-01",
                    "revision": 1,
                    "purpose": "VIDEO_STORYBOARD",
                    "shot_id": "SHOT_01",
                    "preservation_hash": "c" * 64,
                    "prompt": "Continue the approved first frame.",
                    "action": "turn naturally",
                },
            },
            "candidates": [
                {
                    "candidate_id": "candidate-1",
                    "shot_id": "SHOT_01",
                    "sha256": "d" * 64,
                },
            ],
            "selections": {
                "SHOT_01": {
                    "candidate_id": "candidate-1",
                    "batch_id": "batch-1",
                    "item_id": "item-1",
                    "output_id": "output-1",
                },
            },
            "shot_mappings": {
                "SHOT_01": {
                    "source_image_hash": "d" * 64,
                },
            },
        },
    }


def test_product_adapter_preserves_unknowns_and_facts_revision() -> None:
    state = adapt_product_state(product_payload(), owner_id="owner-1")

    assert state.product_version_id == "version-1"
    assert state.truth.facts_revision == 3
    assert state.truth.known_attributes["color"] == "black"
    assert "asset-front" in state.truth.source_fact_keys
    assert state.locks.immutable_attributes["logo"] == "preserve exactly"


def test_storyboard_adapter_creates_explicit_shot_binding() -> None:
    snapshot = creative_snapshot()
    storyboard, shots = adapt_storyboard_state(
        snapshot,
        product_version_id="version-1",
    )

    assert storyboard.shot_order == ("FIRST_FRAME", "SHOT_01")
    assert storyboard.selected_direction_id == "A"
    assert shots[1].shot_id == "SHOT_01"
    assert shots[1].source_bindings is not None
    assert shots[1].source_bindings.output_id == "output-1"
    assert shots[1].prompt_refs.preservation_hash == "c" * 64


def test_projection_is_read_only_and_reports_owner_conflicts() -> None:
    task = {
        "id": "creative-task-1",
        "user_id": "owner-2",
        "state_version": 4,
        "snapshot_json": creative_snapshot(),
    }
    projection = project_creative_state(
        creative_task=task,
        product_version=product_payload(),
        owner_id="owner-1",
    )

    assert projection.state is not None
    assert projection.state.status == "BLOCKED"
    assert any(item.code == "OWNER_MISMATCH" for item in projection.diagnostics)
    assert task["snapshot_json"]["storyboard"]["packages"]["SHOT_01"]["package_id"] == (
        "package-shot-01"
    )


def test_projection_maps_legacy_director_snapshot_without_provider_state() -> None:
    task = {
        "id": "creative-task-1",
        "user_id": "owner-1",
        "state_version": 4,
        "snapshot_json": creative_snapshot(),
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
                "identity": {
                    "faceStructure": ["oval face"],
                    "ageRange": "adult",
                },
            },
            "sceneDNA": {
                "id": "scene-1",
                "revision": 1,
                "origin": "PROPOSED",
                "environment": {"description": "bright studio"},
            },
        },
    )

    assert projection.valid
    assert projection.state is not None
    assert projection.state.character is not None
    assert projection.state.character.character_id == "character-1"
    assert projection.state.scene is not None
    assert projection.state.quality.delivery_eligibility == "NOT_ELIGIBLE"
    assert projection.state.provenance.legacy_snapshot is True
    assert projection.state.product.source_assets[0].sha256 == "a" * 64


def test_revision_hashes_are_stable_and_detect_tampering() -> None:
    product = adapt_product_state(product_payload(), owner_id="owner-1")
    storyboard = StoryboardState(
        storyboard_id="storyboard-1",
        revision=1,
        shot_order=("SHOT_01",),
    )
    revision = CreativeStateRevision(
        creative_state_id="state-1",
        revision=1,
        state_version=0,
        facts_revision=product.truth.facts_revision,
        content_hash="0" * 64,
        locks_hash=calculate_locks_hash(product),
        source_snapshot_hash=calculate_source_snapshot_hash(product),
        created_by="owner-1",
        created_at="2026-10-13T00:00:00Z",
        reason="test",
        product=product,
        storyboard=storyboard,
        shots=(
            ShotState(
                shot_id="SHOT_01",
                order=1,
                inherited_product_revision=product.product_version_id,
            ),
        ),
        quality=QualityState(),
    )
    sealed = seal_revision(revision)

    validate_revision_integrity(sealed)
    assert sealed.content_hash == calculate_revision_hash(sealed)

    tampered = sealed.model_copy(
        update={
            "storyboard": sealed.storyboard.model_copy(
                update={"continuity_rules": ("do not redesign the room",)}
            )
        }
    )
    with pytest.raises(ValueError, match="content_hash"):
        validate_revision_integrity(tampered)


def test_revision_rejects_positional_shot_order_mismatch() -> None:
    product = adapt_product_state(product_payload(), owner_id="owner-1")
    with pytest.raises(ValidationError, match="shot_order"):
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
            reason="test",
            product=product,
            storyboard=StoryboardState(
                storyboard_id="storyboard-1",
                revision=1,
                shot_order=("SHOT_02",),
            ),
            shots=(
                ShotState(
                    shot_id="SHOT_01",
                    order=1,
                    inherited_product_revision=product.product_version_id,
                ),
            ),
        )


def test_quality_state_cannot_promote_offline_evidence_to_delivery() -> None:
    with pytest.raises(ValidationError, match="delivery eligible"):
        QualityState(
            qualification_scope="OFFLINE_SYNTHETIC_ONLY",
            current_decision="QUALIFIED",
            delivery_eligibility="ELIGIBLE",
        )
