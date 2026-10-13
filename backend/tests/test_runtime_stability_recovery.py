from __future__ import annotations

# The test can be pointed at a newer isolated runtime source tree without
# changing the package under test.
# ruff: noqa: E402
import os
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID

import pytest

_runtime_source = os.environ.get("SPRINT6_RUNTIME_SOURCE")
if _runtime_source:
    sys.path.insert(0, _runtime_source)
    for _module in tuple(sys.modules):
        if _module == "libtv_agent" or _module.startswith("libtv_agent."):
            del sys.modules[_module]

from libtv_agent.creative.brand_dna import project_brand_dna
from libtv_agent.creative.controlled_production import (
    AdapterLineage,
    ControlledProductionSample,
    ProductLineage,
    provider_request_lineage,
    validate_controlled_production,
)
from libtv_agent.creative.workflow import digest
from libtv_agent.services.controlled_image_adapter import (
    ControlledImageAdapterRejected,
    compile_controlled_image_batch_input,
)
from libtv_agent.services.controlled_video_adapter import (
    ControlledVideoAdapterRejected,
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
from libtv_agent.services.creative_provider_submission import (
    ProviderSubmissionTicket,
    SubmissionManifestEntry,
    SubmissionTicketStore,
    provider_submission_result,
    record_provider_submission_result,
)
from libtv_agent.services.creative_reality_loop_gate import (
    DirectionEvidence,
    LayerEvidence,
    LoopAuthorization,
    PackageRevisionSummary,
    ProductBrandLock,
    PromptPreservationEvidence,
    PromptRevisionSummary,
    RealityDimensionEvidence,
    RealityEvidence,
)
from libtv_agent.services.creative_workflow_orchestrator import (
    CreativeWorkflowOrchestrator,
    CreativeWorkflowSnapshot,
    E1Snapshot,
    TextPackageSnapshot,
)

OWNER = "owner-1"
TASK = "creative-task-1"
PRODUCT_ID = "product-1"
PRODUCT_VERSION_ID = "product-version-1"
PRODUCT_HASH = "a" * 64
IMAGE_HASH = "b" * 64
VIDEO_HASH = "c" * 64
IMAGE_PACKAGE = "image-package-r4"
VIDEO_PACKAGE = "video-package-r5"
OUTPUT_ID = UUID("00000000-0000-0000-0000-000000000101")
BATCH_ID = UUID("00000000-0000-0000-0000-000000000102")
ITEM_ID = UUID("00000000-0000-0000-0000-000000000103")
UPLOAD_ID = UUID("00000000-0000-0000-0000-000000000104")


def _brand() -> dict:
    return project_brand_dna(
        {
            "id": "brand-1",
            "version": "v3",
            "name": "Dark Brand",
            "status": "active",
            "audience": "adults",
            "tone": "quiet and precise",
            "palette": ["black"],
        }
    )


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
            product_id=PRODUCT_ID,
            product_version_id=PRODUCT_VERSION_ID,
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
    return request.model_copy(
        update={
            "request_hash": digest(
                request.model_dump(mode="json", exclude={"request_hash"})
            )
        }
    )


def _image_package(*, brand: dict | None = None) -> dict:
    request = _image_request()
    provenance = {
        "schemaVersion": "creative-package.v1",
        "packageId": IMAGE_PACKAGE,
        "revision": 4,
        "shotId": "FIRST_FRAME",
        "purpose": "FIRST_FRAME",
        "creativeStateRevision": request.state_version,
        "creativeTaskId": TASK,
        "productId": PRODUCT_ID,
        "sourceHash": PRODUCT_HASH,
        "sourceAssets": [
            {
                "object_key": "products/product-1/front.png",
                "sha256": PRODUCT_HASH,
            }
        ],
        "synthetic": False,
        "qualificationScope": "REAL_INPUT_UNVERIFIED",
        "sourcePackage": {
            "package_id": IMAGE_PACKAGE,
            "shot_id": "FIRST_FRAME",
            "purpose": "FIRST_FRAME",
        },
    }
    if brand is not None:
        provenance["brandDNA"] = brand
    return {
        "imagePrompt": request.locked_prompt.prompt,
        "shotPlan": [{"shotId": "FIRST_FRAME", "packageId": IMAGE_PACKAGE}],
        "provenance": provenance,
    }


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
        prompt_hash=digest(prompt),
        preservation_hash=VIDEO_HASH,
        locks_hash=VIDEO_HASH,
        text_contract_hash=VIDEO_HASH,
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
            product_id=PRODUCT_ID,
            product_version_id=PRODUCT_VERSION_ID,
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
        bridge_validity_token=VIDEO_HASH,
        evidence_hash=VIDEO_HASH,
        request_hash=VIDEO_HASH,
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


def _qualified_source(**overrides) -> QualifiedVideoImageSource:
    values = {
        "upload_id": UPLOAD_ID,
        "source_image_output_id": OUTPUT_ID,
        "source_image_hash": VIDEO_HASH,
        "output_image_hash": VIDEO_HASH,
        "creative_task_id": TASK,
        "candidate_id": "storyboard-candidate",
        "batch_id": BATCH_ID,
        "item_id": ITEM_ID,
        "package_lineage": {
            "package_revision_id": VIDEO_PACKAGE,
            "parent_package_revision_id": IMAGE_PACKAGE,
        },
        "revision_lineage": {"revision": 5, "parent_revision": 4},
    }
    values.update(overrides)
    return QualifiedVideoImageSource.model_validate(values)


def _reality() -> RealityEvidence:
    return RealityEvidence(
        tuple(
            RealityDimensionEvidence(
                dimension=dimension,
                decision=f"fixed {dimension}",
                evidence_status="PROPOSED",
                evidence=f"evidence for {dimension}",
            )
            for dimension in (
                "Camera",
                "Lighting",
                "Composition",
                "Human Behavior",
                "Environment",
                "Imperfection",
            )
        )
    )


def _workflow_snapshot(*, call_status: str | None = None) -> CreativeWorkflowSnapshot:
    product = ProductBrandLock(
        product_id=PRODUCT_ID,
        product_revision=PRODUCT_VERSION_ID,
        product_source_hash=PRODUCT_HASH,
        brand_id="brand-1",
        brand_revision="v3",
        brand_source="USER_SELECTED",
    )
    preservation = PromptPreservationEvidence(
        prompt_revision_id="prompt-r4",
        prompt_hash=IMAGE_HASH,
        product_lock_digest=product.product_lock_digest,
        brand_lock_digest=product.brand_lock_digest,
    )
    prompt = PromptRevisionSummary(
        prompt_revision_id="prompt-r4",
        revision_index=4,
        parent_prompt_revision_id="prompt-r3",
        content_hash=IMAGE_HASH,
        preservation_hash=preservation.evidence_digest,
    )
    package = PackageRevisionSummary(
        package_revision_id=IMAGE_PACKAGE,
        prompt_revision_id="prompt-r4",
        revision_index=4,
        parent_package_revision_id="image-package-r3",
        parent_prompt_revision_id="prompt-r3",
        product_lock_digest=product.product_lock_digest,
        brand_lock_digest=product.brand_lock_digest,
        reality_digest=_reality().evidence_digest,
        scene_digest=IMAGE_HASH,
        composition_digest=IMAGE_HASH,
        prompt_preservation_digest=preservation.evidence_digest,
        changed_module="initial",
        causal_variable="initial",
    )
    authorization = LoopAuthorization(
        enabled=True,
        human_confirmed=True,
        max_revisions=2,
        max_calls=4,
        max_total_cost_micros=40,
        expires_at=datetime.now(UTC) + timedelta(hours=1),
        allowed_modules=("Reality", "Scene", "Composition"),
    )
    return CreativeWorkflowSnapshot(
        loop_id="recovery-loop",
        now=datetime.now(UTC),
        authorization=authorization,
        product=product,
        direction=DirectionEvidence("direction-A", "direction-r1"),
        dna_reality=_reality(),
        text_package=TextPackageSnapshot(
            preservation=preservation,
            prompt_revision=prompt,
            package_revision=package,
            scene=LayerEvidence("Scene", "scene-r4", IMAGE_HASH, "PROPOSED", "street"),
            composition=LayerEvidence(
                "Composition", "composition-r4", IMAGE_HASH, "PROPOSED", "medium"
            ),
        ),
        trace=("Product", "Direction", "DNA_REALITY", "TEXT_PACKAGE", "AUTHORIZATION"),
        e1=E1Snapshot(
            calls_used=1,
            total_cost_micros=10,
            planned_call_cost_micros=10,
            last_call_status=call_status,
        ),
    )


def _ticket(tmp_path: Path) -> ProviderSubmissionTicket:
    input_path = tmp_path / "product.png"
    input_path.write_bytes(b"offline fixture")
    entry = SubmissionManifestEntry(
        role="PRODUCT",
        order=1,
        adapter_field="images",
        object_key="products/product-1/front.png",
        sha256=PRODUCT_HASH,
        path=input_path,
    )
    now = datetime.now(UTC)
    return ProviderSubmissionTicket(
        ticket_id="pst:recovery",
        request_kind="image",
        execution_mode="image_edit",
        future_adapter_action="IMAGE_PROVIDER_ADAPTER_SUBMIT",
        owner_id=OWNER,
        creative_task_id=TASK,
        package_revision_id=IMAGE_PACKAGE,
        shot_id="FIRST_FRAME",
        provider="gpt",
        model="gpt-image-test",
        idempotency_key="recovery-idempotency-key",
        request_hash=IMAGE_HASH,
        evidence_hash=IMAGE_HASH,
        preflight_hash=VIDEO_HASH,
        expires_at=now + timedelta(hours=1),
        estimated_cost_micros=0,
        currency="FAKE",
        quota_units=1,
        materialized_inputs=(entry,),
        manifest_path=tmp_path / "manifest.json",
        manifest_hash=IMAGE_HASH,
    )


def test_mid_workflow_unknown_failure_waits_for_reconciliation_and_human_review() -> None:
    snapshot = _workflow_snapshot(call_status="UNKNOWN")
    result = CreativeWorkflowOrchestrator().decide(snapshot)
    repeated = CreativeWorkflowOrchestrator().decide(snapshot)

    assert result == repeated
    assert result.command.kind == "WAIT_RECONCILIATION"
    assert result.command.requires_human_review is True
    assert result.command.provider_execution_allowed is False
    assert result.audit_event.provider_called is False
    assert result.audit_event.production_write is False
    assert result.stop_wait_reason is not None
    assert result.stop_wait_reason.code == "EXECUTION_UNKNOWN"
    assert result.command.expected_call_count == 0
    assert result.command.expected_cost_micros == 0
    assert result.audit_event.trace == snapshot.trace


def test_adapter_retry_preserves_lineage_hash_prompt_and_brand_version() -> None:
    package = _image_package(brand=_brand())
    request = _image_request()
    first = compile_controlled_image_batch_input(
        package, request, owner_id=OWNER, creative_task_id=TASK
    )
    retry = compile_controlled_image_batch_input(
        package, request, owner_id=OWNER, creative_task_id=TASK
    )

    for field in (
        "creativeStateRevision",
        "packageId",
        "productAssetHash",
        "promptSnapshot",
        "promptSnapshotHash",
        "brandDNA",
        "idempotencyKey",
        "requestHash",
        "providerRequestHash",
    ):
        assert retry[field] == first[field]
    assert first["providerSubmissionAllowed"] is False
    assert first["ordinaryOutputQualified"] is False
    assert first["deliverableEligible"] is False
    assert first["manifest"]["expectedGenerationCount"] == 1

    drifted = _image_package(brand=_brand())
    drifted["provenance"]["creativeStateRevision"] = 13
    with pytest.raises(ControlledImageAdapterRejected) as rejected:
        compile_controlled_image_batch_input(
            drifted, request, owner_id=OWNER, creative_task_id=TASK
        )
    assert rejected.value.code == "CREATIVE_STATE_REVISION_MISMATCH"

    drifted = _image_package(brand=_brand())
    drifted["imagePrompt"] = "rewritten after failure"
    with pytest.raises(ControlledImageAdapterRejected) as rejected:
        compile_controlled_image_batch_input(
            drifted, request, owner_id=OWNER, creative_task_id=TASK
        )
    assert rejected.value.code == "PROMPT_SNAPSHOT_MISMATCH"

    drifted = _image_package(brand=_brand())
    drifted["provenance"]["brandDNA"]["audience"] = "tampered"
    with pytest.raises(ControlledImageAdapterRejected) as rejected:
        compile_controlled_image_batch_input(
            drifted, request, owner_id=OWNER, creative_task_id=TASK
        )
    assert rejected.value.code == "BRAND_DNA_TAMPERED"


def test_video_retry_and_single_sample_manifest_keep_package_and_revision_lineage() -> None:
    request = _video_request()
    source = _qualified_source()
    first = compile_controlled_video_task_input(request, source)
    retry = compile_controlled_video_task_input(request, source)

    assert retry == first
    assert first.source_image_output_id == OUTPUT_ID
    assert first.source_image_hash == first.output_image_hash == VIDEO_HASH
    assert first.package_lineage.package_revision_id == VIDEO_PACKAGE
    assert first.package_lineage.parent_package_revision_id == IMAGE_PACKAGE
    assert first.revision_lineage.revision == 5
    assert first.revision_lineage.parent_revision == 4
    assert first.provider_submission_allowed is False
    assert first.payload.paid_submission_consent is False

    image_request = _image_request()
    image_input = compile_controlled_image_batch_input(
        _image_package(), image_request, owner_id=OWNER, creative_task_id=TASK
    )
    image_lineage = AdapterLineage(
        adapter="image",
        task_id=TASK,
        product_id=PRODUCT_ID,
        product_version_id=PRODUCT_VERSION_ID,
        package_revision_id=IMAGE_PACKAGE,
        shot_id="FIRST_FRAME",
        provider_request=provider_request_lineage(image_request),
        references=(
            {
                "role": "PRODUCT",
                "reference_id": image_input["productAssetHash"],
                "sha256": PRODUCT_HASH,
                "source_kind": "REAL_PRODUCT",
                "order": 1,
            },
        ),
        input_origin="REAL_PRODUCT",
        cost_evidence="NO_PAID_SIDE_EFFECT",
        resolution_evidence="KNOWN",
    )
    video_lineage = AdapterLineage(
        adapter="video",
        task_id=TASK,
        product_id=PRODUCT_ID,
        product_version_id=PRODUCT_VERSION_ID,
        package_revision_id=VIDEO_PACKAGE,
        shot_id="SHOT_01",
        provider_request=provider_request_lineage(request),
        references=(
            {
                "role": "IMAGE_OUTPUT",
                "reference_id": str(OUTPUT_ID),
                "sha256": VIDEO_HASH,
                "source_kind": "REAL_IMAGE_OUTPUT",
                "order": 1,
            },
        ),
        input_origin="REAL_IMAGE_OUTPUT",
        cost_evidence="NO_PAID_SIDE_EFFECT",
        resolution_evidence="KNOWN",
    )
    manifest = validate_controlled_production(
        ControlledProductionSample(
            sample_id="recovery-sample",
            product=ProductLineage(
                product_id=PRODUCT_ID,
                product_version_id=PRODUCT_VERSION_ID,
                owner_id=OWNER,
                source_sha256=PRODUCT_HASH,
                source_ref="products/product-1/front.png",
            ),
            image_task=image_lineage,
            video_task=video_lineage,
        )
    )
    assert validate_controlled_production(
        ControlledProductionSample.model_validate(
            {
                "sample_id": "recovery-sample",
                "product": manifest.product.model_dump(mode="json"),
                "image_task": manifest.image_task.model_dump(mode="json"),
                "video_task": manifest.video_task.model_dump(mode="json"),
            }
        )
    ).manifest_hash == manifest.manifest_hash
    assert manifest.image_task.provider_request.package_revision_id == IMAGE_PACKAGE
    assert manifest.video_task.provider_request.package_revision_id == VIDEO_PACKAGE

    with pytest.raises(ControlledVideoAdapterRejected) as rejected:
        compile_controlled_video_task_input(
            request,
            source.model_copy(update={"qualification_scope": "OFFLINE_SYNTHETIC_ONLY"}),
        )
    assert rejected.value.code == "QUALIFICATION_SCOPE_INVALID"


def test_submission_unknown_recovery_is_idempotent_and_never_retries_provider(
    tmp_path: Path,
) -> None:
    store = SubmissionTicketStore()
    ticket = _ticket(tmp_path)
    first_claim = store.claim_submission(ticket)
    replay_claim = store.claim_submission(ticket)
    assert first_claim.created is True
    assert replay_claim.created is False
    assert replay_claim.state == first_claim.state

    unknown = provider_submission_result(
        ticket,
        status="UNKNOWN",
        provider_status="timeout",
        error_code="RESPONSE_LOST",
    )
    first_recovery = record_provider_submission_result(store, ticket, unknown)
    repeated_recovery = record_provider_submission_result(store, ticket, unknown)

    assert repeated_recovery == first_recovery
    assert repeated_recovery.state == "UNKNOWN"
    assert repeated_recovery.result is not None
    assert repeated_recovery.result.retry_policy == "RECONCILE_ONLY"
    assert repeated_recovery.result.actual_submitted is None
    assert store.claim_submission(ticket).created is False
    assert store.claim_submission(ticket).state.state == "UNKNOWN"

    with pytest.raises(ValueError):
        record_provider_submission_result(
            store,
            ticket,
            provider_submission_result(
                ticket,
                status="FAILED",
                error_code="different-outcome",
            ),
        )

