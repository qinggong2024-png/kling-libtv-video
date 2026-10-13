from __future__ import annotations

from libtv_agent.creative.image_generation_adapter import (
    compile_image_generation_request,
)
from libtv_agent.services.canonical_provider_adapter import (
    ProviderRequestCompilationContext,
    compile_provider_request_preview,
)
from libtv_agent.services.creative_provider_requests import SourceMapping
from test_creative_image_generation_adapter import _revision


def _context(shot_id: str) -> ProviderRequestCompilationContext:
    return ProviderRequestCompilationContext(
        creative_task_id="creative-task-1",
        package_revision_id="package-shot_01",
        source_mapping=SourceMapping(
            package_revision_id="package-shot_01",
            candidate_id="candidate-1",
            shot_id=shot_id,
            batch_id="batch-1",
            item_id="item-1",
            output_id="output-1",
        ),
        idempotency_key=f"creative-provider:image:creative-task-1:{shot_id}",
        bridge_validity_token="d" * 64,
        evidence_hash="e" * 64,
        text_contract_hash="f" * 64,
        text_contract_json="{}",
    )


def test_canonical_request_previews_and_compiles_existing_provider_contract() -> None:
    revision = _revision()

    canonical = compile_image_generation_request(revision, revision.shots[0])
    assert canonical.request is not None

    result = compile_provider_request_preview(
        canonical.request,
        provider="gpt",
        context=_context(canonical.request.shot_id),
    )

    assert result.status == "READY"
    assert result.preview is not None
    assert result.preview.provider == "gpt"
    assert result.preview.provider_contract_ready is True
    assert result.preview.provider_submission_allowed is False
    assert result.preview.creative_state_id == revision.creative_state_id
    assert result.preview.revision == revision.revision
    assert result.preview.content_hash == revision.content_hash
    assert result.preview.shot_id == "SHOT_01"
    assert result.preview.prompt == canonical.request.prompt
    assert result.preview.prompt_hash
    assert result.preview.preservation_hash == canonical.request.preservation_hash
    assert {item.role for item in result.preview.references} == {
        "PRODUCT",
        "CHARACTER",
        "SCENE",
        "SPATIAL",
        "CAMERA",
    }
    assert result.preview.provider_request is not None
    assert result.preview.provider_request.shot_id == "SHOT_01"
    assert result.preview.provider_request.canonical_product.product_id == "product-1"
    assert result.preview.provider_request.locked_prompt.prompt == canonical.request.prompt
    assert result.preview.provider_request.provider_submission_allowed is False


def test_preview_without_context_stays_dry_run_and_does_not_invent_contract_fields() -> None:
    revision = _revision()

    canonical = compile_image_generation_request(revision, revision.shots[0])
    assert canonical.request is not None

    result = compile_provider_request_preview(canonical.request)

    assert result.status == "READY"
    assert result.preview is not None
    assert result.preview.provider_contract_ready is False
    assert result.preview.provider_request is None
    assert result.executable is False


def test_blocked_spatial_state_rejects_provider_preview() -> None:
    revision = _revision()

    canonical = compile_image_generation_request(revision, revision.shots[0])
    assert canonical.request is not None
    blocked_request = canonical.request.model_copy(
        update={
            "spatial_constraints": canonical.request.spatial_constraints.model_copy(
                update={"provider_submission_allowed": False}
            )
        }
    )

    result = compile_provider_request_preview(blocked_request)

    assert result.status == "BLOCKED"
    assert result.preview is None
    assert any(item.code == "SPATIAL_STATE_BLOCKED" for item in result.diagnostics)


def test_missing_camera_state_is_explicitly_unresolved() -> None:
    revision = _revision()
    canonical = compile_image_generation_request(revision, revision.shots[0])
    assert canonical.request is not None
    missing_camera = canonical.request.model_copy(update={"camera_intent": None})

    result = compile_provider_request_preview(missing_camera)

    assert result.status == "UNRESOLVED"
    assert result.preview is None
    assert any(
        item.code == "CAMERA_REFERENCE_UNRESOLVED" for item in result.diagnostics
    )


def test_missing_character_or_scene_reference_stays_unresolved() -> None:
    revision = _revision()

    canonical = compile_image_generation_request(revision, revision.shots[0])
    assert canonical.request is not None
    manifest = canonical.request.source_manifest
    for missing_role in ("CHARACTER", "SCENE"):
        manifest_without_role = manifest.model_copy(
            update={
                "source_references": tuple(
                    item
                    for item in manifest.source_references
                    if item.role != missing_role
                )
            }
        )
        unresolved_request = canonical.request.model_copy(
            update={"source_manifest": manifest_without_role}
        )

        result = compile_provider_request_preview(unresolved_request)

        assert result.status == "UNRESOLVED"
        assert result.preview is None
        assert any(
            item.code == "CANONICAL_REFERENCE_UNRESOLVED"
            for item in result.diagnostics
        )
