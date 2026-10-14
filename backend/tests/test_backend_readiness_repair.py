from __future__ import annotations

import hashlib
import io
import json
import uuid
from types import SimpleNamespace

import pytest
from httpx import ASGITransport, AsyncClient
from libtv_agent.domain.contracts import sha256_json
from libtv_agent.domain.enums import (
    AttemptStatus,
    CommandStatus,
    DownloadStatus,
    GenerationStatus,
    ParentTaskPhase,
    ProductLicenseStatus,
    ProductVersionStatus,
    ValidationStatus,
    VariantKind,
)
from libtv_agent.domain.models import (
    ApiIdempotencyRecord,
    AuditEvent,
    CreativeCreation,
    CreativeTask,
    GenerationAttempt,
    GenerationCommand,
    GenerationVariant,
    ImageGenerationBatch,
    ImageGenerationOutput,
    ParentTask,
    Product,
    ProductVersion,
)
from libtv_agent.runner.supervisor import RunnerSupervisor
from libtv_agent.services.creative_production_context import production_prompt
from libtv_agent.services.runtime_control import get_runtime_config, update_runtime_config
from PIL import Image
from sqlalchemy import func, select
from test_image_generation_batches import _app


def png(color="red"):
    stream = io.BytesIO()
    Image.new("RGB", (360, 640), color).save(stream, "PNG")
    return stream.getvalue()


@pytest.fixture
async def backend(tmp_path):
    app, settings = await _app(tmp_path)
    settings.director_workflow_mode = "live_director"
    async with app.router.lifespan_context(app):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            headers = {"X-User-Id": settings.dev_user_id}
            await client.get("/api/v1/tasks", headers=headers)
            async with app.state.database.session_factory() as session:
                current = await get_runtime_config(session, settings)
                await update_runtime_config(
                    session, settings, config={
                        **current.config_json, "internalPilotEnabled": True,
                        "pilotUserIds": [settings.dev_user_id], "pilotBudgetLimit": 100,
                    }, actor_id=None, reason="isolated test-double admission",
                    expected_version=current.version,
                )
                await session.commit()
            yield client, app, settings, headers


async def planned(backend, *, client_key="repair-workflow"):
    client, app, _, headers = backend
    product = await client.post(
        "/api/v1/products", headers=headers, json={"internalSkuId": str(uuid.uuid4())},
    )
    assert product.status_code == 201, product.text
    data = {"product_id": product.json()["id"], "client_key": client_key}
    created = await client.post(
        "/api/v1/creative-workflow/tasks", headers=headers, data=data,
        files={"front": ("front.png", png(), "image/png")},
    )
    assert created.status_code == 201, created.text
    task_id = created.json()["id"]
    for version, (action, extra) in enumerate([
        ("analyze", {}), ("select_direction", {"direction_id": "A"}),
    ]):
        result = await client.post(
            f"/api/v1/creative-workflow/tasks/{task_id}/commands", headers=headers,
            json={
                "command_key": f"plan-{version}", "expected_version": version,
                "action": action, **extra,
            },
        )
        assert result.status_code == 200, result.text
    snapshot = result.json()["snapshot"]
    async with app.state.database.session_factory() as session:
        version = await session.get(
            ProductVersion, uuid.UUID(snapshot["product_version"]["product_version_id"]),
        )
        version.status = ProductVersionStatus.APPROVED
        version.license_status = ProductLicenseStatus.VERIFIED
        await session.commit()
    context = {
        "workflowId": task_id, "packageId": snapshot["package"]["package_id"],
        "shotId": "FIRST_FRAME",
    }
    return context, result.json(), data


async def generate_image(backend, context, *, key="repair-image", source=None, headers=None):
    client, _, _, owner_headers = backend
    headers = headers or owner_headers
    manifest = {
        "clientBatchId": key, "name": key, "provider": "gpt", "modes": ["fusion"],
        "resultCount": 1, "aspectRatio": "9:16", "resolution": "2k", "quality": "medium",
        "outputFormat": "png", "paidSubmissionConsent": True, "expectedGenerationCount": 1,
        "creativePackage": context, "items": [{
            "clientTaskId": key, "outfitId": "ignored-client-product", "outfitName": "Product",
            "prompts": {"fusion": "must never replace frozen package prompt"},
            "referenceFileIndexes": [0],
        }],
    }
    return await client.post(
        "/api/v1/image-generation-batches", headers={**headers, "Idempotency-Key": key},
        data={"clientManifest": json.dumps(manifest)},
        files={"files": ("front.png", source or png(), "image/png")},
    )


async def qualified_image(backend, context):
    client, app, settings, headers = backend
    generated = await generate_image(backend, context)
    assert generated.status_code == 201, generated.text
    media = png("blue")
    path = settings.artifact_root / "test-output.png"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(media)
    key = await app.state.object_store.put_file(path, "outputs/test.png", "image/png")
    async with app.state.database.session_factory() as session:
        batch = await session.get(ImageGenerationBatch, uuid.UUID(generated.json()["id"]))
        item = batch.items[0]
        item.status = "COMPLETED"
        output = ImageGenerationOutput(
            item_id=item.id, order_no=1, remote_url="https://test.invalid/generated.png",
            object_key=key, sha256=hashlib.sha256(media).hexdigest(), content_type="image/png",
        )
        session.add(output)
        await session.commit()
        output_id = str(output.id)
    approved = await client.put(
        f"/api/v1/image-generation-outputs/{output_id}/quality-decision", headers=headers,
        json={
            "decision": "QUALIFIED", "productFidelityPass": True,
            "humanCriticalPass": True, "humanReviewSeconds": 5,
        },
    )
    assert approved.status_code == 200, approved.text
    uploaded = await client.post(
        "/api/v1/uploads",
        headers={
            **headers, "Idempotency-Key": "repair-upload", "X-Source-Image-Output-Id": output_id,
        }, files={"file": ("generated.png", media, "image/png")},
    )
    assert uploaded.status_code == 201, uploaded.text
    return output_id, uploaded.json()["id"]


def video_request(context, upload_id):
    return {
        "clientTaskId": "repair-video", "title": "Package video",
        "storyboards": [{"uploadId": upload_id, "order": 1}],
        "generationMode": "director_fixed", "creativePackage": context,
        "templateId": "ootd_walk", "durationSeconds": 10, "paidSubmissionConsent": True,
    }


def install_preparation_double(monkeypatch):
    async def allow(*args, **kwargs):
        pass

    async def prepare(session, adapter, object_store, task, settings):
        attempts = []
        for variant in task.variants:
            attempt = GenerationAttempt(
                variant_id=variant.id, provider=settings.active_kling_provider_name,
                provider_model="test-video", provider_status="queued",
                intent_hash=str(uuid.uuid4()), status=AttemptStatus.PREPARED,
            )
            session.add(attempt)
            attempts.append(attempt)
        await session.flush()
        return attempts

    def forbidden(*args, **kwargs):
        raise AssertionError("director_fixed must not re-plan or inject learning")

    monkeypatch.setattr(
        "libtv_agent.services.fixed_video_tasks.ensure_provider_submission_allowed", allow,
    )
    monkeypatch.setattr("libtv_agent.services.fixed_video_tasks.prepare_kling_task", prepare)
    monkeypatch.setattr("libtv_agent.services.fixed_video_tasks.compile_video_plan", forbidden)
    monkeypatch.setattr("libtv_agent.services.fixed_video_tasks.apply_video_learning", forbidden)


async def create_video(backend, context, upload_id):
    client, _, _, headers = backend
    return await client.post(
        "/api/v1/video-tasks", headers={**headers, "Idempotency-Key": "repair-video"},
        json=video_request(context, upload_id),
    )


class VideoExecutorDouble:
    def __init__(self):
        self.requests = []

    def get_provider_name(self):
        return "kling_official_api"

    async def submit(self, request):
        self.requests.append(request)
        return SimpleNamespace(
            provider_task_id="test-video-1", provider_model="test-video", raw_status="queued",
            credits_consumed=0, raw_response={},
        )


@pytest.mark.asyncio
async def test_package_reaches_existing_executors_and_video_lineage(backend, monkeypatch):
    client, app, settings, headers = backend
    context, plan, _ = await planned(backend)
    output_id, upload_id = await qualified_image(backend, context)
    assert app.state.wavespeed_adapter.submissions[0][1]["prompt"] == production_prompt(
        plan["creative_packages"][context["packageId"]]["imagePrompt"],
    )
    assert "creativePackage" not in app.state.wavespeed_adapter.submissions[0][1]
    install_preparation_double(monkeypatch)
    created = await create_video(backend, context, upload_id)
    assert created.status_code == 201, created.text
    video = created.json()
    bound = video["variants"][0]["productionContext"]["creativePackage"]
    assert bound["workflowId"] == context["workflowId"]
    assert bound["packageId"] == context["packageId"]
    lineage = video["variants"][0]["productionContext"]["sourceLineage"][0]
    assert lineage["sourceImageOutputId"] == output_id
    assert lineage["creativePackage"]["shotId"] == "FIRST_FRAME"
    assert lineage["storyboardOrder"] == 1
    executor = VideoExecutorDouble()
    supervisor = RunnerSupervisor(
        app.state.libtv_adapter, app.state.object_store, settings, kling_adapter=executor,
    )
    monkeypatch.setattr("libtv_agent.runner.supervisor.real_provider_submission_authorized",
                        lambda _: True)
    monkeypatch.setattr(type(settings), "kling_provider_submission_enabled", lambda *_: True)
    async with app.state.database.session_factory() as session:
        command = await session.scalar(select(GenerationCommand))
        assert await supervisor._execute(session, command.id) is False
    assert len(executor.requests) == 1
    image_replay = await generate_image(backend, context)
    assert image_replay.status_code == 201, image_replay.text
    assert len(app.state.wavespeed_adapter.submissions) == 1
    assert image_replay.json()["productionContext"]["packageId"] == context["packageId"]
    assert executor.requests[0].prompt == video["variants"][0]["promptText"]
    recovered = await client.get(f"/api/v1/tasks/{video['id']}", headers=headers)
    assert recovered.json()["variants"][0]["productionContext"] == video["variants"][0][
        "productionContext"
    ]
    replay = await create_video(backend, context, upload_id)
    assert replay.status_code == 201
    assert replay.json()["id"] == video["id"]
    assert len(executor.requests) == 1


@pytest.mark.parametrize("boundary", ["create", "worker", "submit"])
@pytest.mark.asyncio
async def test_rejected_source_blocks_video_at_every_boundary(backend, monkeypatch, boundary):
    client, app, settings, headers = backend
    context, _, _ = await planned(backend)
    output_id, upload_id = await qualified_image(backend, context)
    install_preparation_double(monkeypatch)
    if boundary != "create":
        created = await create_video(backend, context, upload_id)
        assert created.status_code == 201, created.text
    async def revoke():
        response = await client.put(
            f"/api/v1/image-generation-outputs/{output_id}/quality-decision", headers=headers,
            json={
                "decision": "REJECTED", "productFidelityPass": False,
                "humanCriticalPass": True, "humanReviewSeconds": 5, "notes": "revoked",
            },
        )
        assert response.status_code == 200
    if boundary != "submit":
        await revoke()
    if boundary == "create":
        rejected = await create_video(backend, context, upload_id)
        assert rejected.status_code == 422, rejected.text
        assert rejected.json()["detail"]["code"] == "SOURCE_IMAGE_NOT_QUALIFIED"
        return
    executor = VideoExecutorDouble()
    supervisor = RunnerSupervisor(
        app.state.libtv_adapter, app.state.object_store, settings, kling_adapter=executor,
    )
    monkeypatch.setattr("libtv_agent.runner.supervisor.real_provider_submission_authorized",
                        lambda _: True)
    monkeypatch.setattr(type(settings), "kling_provider_submission_enabled", lambda *_: True)
    if boundary == "submit":
        original = app.state.object_store.localize
        async def revoke_during_materialization(*args, **kwargs):
            await revoke()
            return await original(*args, **kwargs)
        monkeypatch.setattr(app.state.object_store, "localize", revoke_during_materialization)
    async with app.state.database.session_factory() as session:
        command = await session.scalar(select(GenerationCommand))
        assert await supervisor._execute(session, command.id) is True
        attempt = await session.get(GenerationAttempt, command.attempt_id)
        assert attempt.status == AttemptStatus.FAILED_BEFORE_SUBMIT
        assert attempt.last_error_code == "SOURCE_IMAGE_NOT_QUALIFIED"
        task = await session.get(ParentTask, uuid.UUID(created.json()["id"]))
        assert task.phase_reason_code == "SOURCE_IMAGE_NOT_QUALIFIED"
        assert await session.scalar(select(func.count()).select_from(AuditEvent).where(
            AuditEvent.action == "VIDEO_SOURCE_BLOCKED",
        )) >= 1
    assert executor.requests == []


@pytest.mark.asyncio
async def test_package_binding_rejects_tampering_and_foreign_owner(backend):
    client, app, settings, headers = backend
    context, _, _ = await planned(backend)
    wrong = await generate_image(backend, context, source=png("black"))
    assert wrong.status_code == 409
    assert wrong.json()["detail"]["code"] == "CREATIVE_SOURCE_HASH_MISMATCH"
    invalid = await generate_image(backend, {**context, "shotId": "SHOT_99"}, key="bad-shot")
    assert invalid.status_code == 409
    foreign = {**headers, "X-User-Id": settings.dev_admin_id}
    for url in (
        f"/api/v1/creative-workflow/tasks/{context['workflowId']}",
        "/api/v1/creative-workflow/recovery/repair-workflow",
    ):
        assert (await client.get(url, headers=foreign)).status_code == 404
    foreign_image = await generate_image(backend, context, key="foreign", headers=foreign)
    assert foreign_image.status_code == 409, foreign_image.text
    assert foreign_image.json()["detail"]["code"] == "CREATIVE_PACKAGE_NOT_FOUND"
    async with app.state.database.session_factory() as session:
        task = await session.get(CreativeTask, uuid.UUID(context["workflowId"]))
        snapshot = dict(task.snapshot_json)
        package = dict(snapshot["package"])
        package["prompt"] += "altered"
        snapshot["package"] = package
        task.snapshot_json = snapshot
        await session.commit()
    tampered = await generate_image(backend, context, key="tampered")
    assert tampered.status_code == 409
    assert tampered.json()["detail"]["code"] == "CREATIVE_PACKAGE_INVALID"
    assert app.state.wavespeed_adapter.submissions == []


@pytest.mark.asyncio
async def test_analysis_failure_recovers_same_product_workflow_and_creation_key(
    backend, monkeypatch,
):
    client, app, _, headers = backend
    product = await client.post(
        "/api/v1/products", headers=headers, json={"internalSkuId": "recovery"},
    )
    data = {"product_id": product.json()["id"], "client_key": "recover-me"}
    created = await client.post(
        "/api/v1/creative-workflow/tasks", headers=headers, data=data,
        files={"front": ("front.png", png(), "image/png")},
    )
    workflow_id = created.json()["id"]
    from libtv_agent.services import creative_workflow
    original = creative_workflow.build_director_analysis
    def fail(**kwargs):
        raise RuntimeError("injected analysis interruption")
    monkeypatch.setattr(creative_workflow, "build_director_analysis", fail)
    failed = await client.post(
        f"/api/v1/creative-workflow/tasks/{workflow_id}/commands", headers=headers,
        json={"command_key": "failed-analysis", "action": "analyze", "expected_version": 0},
    )
    assert failed.status_code == 503, failed.text
    failure_replay = await client.post(
        f"/api/v1/creative-workflow/tasks/{workflow_id}/commands", headers=headers,
        json={"command_key": "failed-analysis", "action": "analyze", "expected_version": 0},
    )
    assert failure_replay.status_code == 409
    assert failure_replay.json()["detail"]["code"] == "STALE_VERSION"
    recovered = await client.get(
        "/api/v1/creative-workflow/recovery/recover-me", headers=headers,
    )
    assert recovered.json()["status"] == "ANALYSIS_FAILED"
    assert recovered.json()["recovery"]["can_retry_analysis"] is True
    repeated = await client.post(
        "/api/v1/creative-workflow/tasks", headers=headers, data=data,
        files={"front": ("front.png", png(), "image/png")},
    )
    assert repeated.json()["id"] == workflow_id
    assert repeated.json() == created.json()
    monkeypatch.setattr(creative_workflow, "build_director_analysis", original)
    command = {
        "command_key": "retry-analysis", "action": "retry_analysis", "expected_version": 1,
    }
    url = f"/api/v1/creative-workflow/tasks/{workflow_id}/commands"
    retried = await client.post(url, headers=headers, json=command)
    assert retried.status_code == 200, retried.text
    assert retried.json()["status"] == "AWAITING_DIRECTION"
    replay = await client.post(url, headers=headers, json=command)
    assert replay.json() == retried.json()
    async with app.state.database.session_factory() as session:
        for model in (Product, CreativeTask, CreativeCreation):
            assert await session.scalar(select(func.count()).select_from(model)) == 1


@pytest.mark.asyncio
async def test_review_queue_ignores_parent_phase_and_approval_retains_quality_gate(
    backend, monkeypatch,
):
    client, app, settings, headers = backend
    context, _, _ = await planned(backend)
    _, upload_id = await qualified_image(backend, context)
    install_preparation_double(monkeypatch)
    created = await create_video(backend, context, upload_id)
    task_id = uuid.UUID(created.json()["id"])
    async with app.state.database.session_factory() as session:
        task = await session.get(ParentTask, task_id)
        variant = task.variants[0]
        variant.generation_status = GenerationStatus.PARTIAL
        variant.download_status = DownloadStatus.READY
        variant.validation_status = ValidationStatus.PASSED
        task.phase = ParentTaskPhase.ACTION_REQUIRED
        variant_id = str(variant.id)
        version = task.state_version
        await session.commit()
    queue = await client.get("/api/v1/tasks/review-required", headers=headers)
    assert queue.status_code == 200, queue.text
    assert len(queue.json()) == 1
    result = queue.json()[0]["variants"][0]
    assert result["technicalSuccess"] is True
    assert result["reviewRequired"] is True
    assert result["finalApprovalStatus"] == "PENDING"
    assert result["deliveryState"] == "REVIEW_REQUIRED"
    foreign = {**headers, "X-User-Id": settings.dev_admin_id}
    assert (await client.get("/api/v1/tasks/review-required", headers=foreign)).json() == []
    approved = await client.put(
        f"/api/v1/tasks/{task_id}/variants/{variant_id}/final-approval", headers=headers,
        json={
            "decision": "APPROVED", "productFidelityPass": True, "editingAssemblyPass": True,
            "humanCriticalPass": True, "humanReviewSeconds": 5, "expectedStateVersion": version,
        },
    )
    assert approved.status_code == 200, approved.text
    assert approved.json()["phase"] == "DELIVERABLE"
    assert approved.json()["variants"][0]["reviewRequired"] is False
    assert approved.json()["variants"][0]["finalApprovalStatus"] == "APPROVED"
    assert approved.json()["variants"][0]["deliveryState"] == "DELIVERABLE"
    assert (await client.get("/api/v1/tasks/review-required", headers=headers)).json() == []


@pytest.mark.asyncio
async def test_ordinary_video_inherits_package_lineage_without_director_mode(backend, monkeypatch):
    client, _, _, headers = backend
    context, _, _ = await planned(backend)
    output_id, upload_id = await qualified_image(backend, context)
    install_preparation_double(monkeypatch)
    request = video_request(context, upload_id)
    request.update(generationMode="custom", customPrompt="Keep the approved garment unchanged.")
    request.pop("creativePackage")
    result = await client.post(
        "/api/v1/video-tasks", headers={**headers, "Idempotency-Key": "ordinary-video"},
        json=request,
    )
    assert result.status_code == 201, result.text
    source = result.json()["variants"][0]["productionContext"]["sourceLineage"][0]
    assert source["sourceImageOutputId"] == output_id
    assert source["creativePackage"]["packageId"] == context["packageId"]
    from libtv_agent.domain.schemas import VideoTaskCreate
    legacy_request = VideoTaskCreate.model_validate(request).model_dump(mode="json", by_alias=True)
    legacy_request.pop("creativePackage")
    async with backend[1].state.database.session_factory() as session:
        record = await session.scalar(select(ApiIdempotencyRecord).where(
            ApiIdempotencyRecord.idempotency_key == "ordinary-video",
        ))
        assert record.payload_hash == sha256_json(legacy_request)
    replay = await client.post(
        "/api/v1/video-tasks", headers={**headers, "Idempotency-Key": "ordinary-video"},
        json=request,
    )
    assert replay.status_code == 201
    assert replay.json()["id"] == result.json()["id"]


@pytest.mark.asyncio
async def test_package_revoked_during_image_upload_blocks_provider_submit(backend, monkeypatch):
    _, app, _, _ = backend
    context, _, _ = await planned(backend)
    original = app.state.wavespeed_adapter.upload_media
    async def revoke(*args, **kwargs):
        async with app.state.database.session_factory() as session:
            task = await session.get(CreativeTask, uuid.UUID(context["workflowId"]))
            task.snapshot_json = {**task.snapshot_json, "stopped": True}
            await session.commit()
        return await original(*args, **kwargs)
    monkeypatch.setattr(app.state.wavespeed_adapter, "upload_media", revoke)
    result = await generate_image(backend, context)
    assert result.status_code == 201, result.text
    assert result.json()["status"] == "failed"
    assert result.json()["items"][0]["error"]["code"] == "CREATIVE_WORKFLOW_BLOCKED"
    assert app.state.wavespeed_adapter.submissions == []


@pytest.mark.asyncio
async def test_review_queue_paginates_all_successful_unapproved_results(backend):
    client, app, settings, headers = backend
    expected_ids = set()
    async with app.state.database.session_factory() as session:
        for index in range(8):
            task = ParentTask(
                id=uuid.uuid4(), user_id=uuid.UUID(settings.dev_user_id),
                client_task_id=f"queue-{index}", title="Pending review", asset_count=0,
                phase=ParentTaskPhase.ACTION_REQUIRED,
            )
            task.variants = [GenerationVariant(
                variant_type=VariantKind.STABLE, generation_status=GenerationStatus.SUCCEEDED,
                download_status=DownloadStatus.READY,
                validation_status=ValidationStatus.WARNING,
            )]
            expected_ids.add(str(task.id))
            session.add(task)
        await session.commit()
    seen = set()
    cursor = None
    while True:
        params = {"limit": 3, **({"cursor": cursor} if cursor else {})}
        page = await client.get("/api/v1/tasks/review-required", headers=headers, params=params)
        assert page.status_code == 200, page.text
        page_ids = {task["id"] for task in page.json()}
        assert not seen & page_ids
        seen.update(page_ids)
        cursor = page.headers.get("X-Next-Cursor")
        if not cursor:
            break
    assert seen == expected_ids


@pytest.mark.asyncio
async def test_legacy_frozen_package_can_be_bound_without_new_contract_index(backend):
    _, app, _, _ = backend
    context, _, _ = await planned(backend)
    async with app.state.database.session_factory() as session:
        task = await session.get(CreativeTask, uuid.UUID(context["workflowId"]))
        task.snapshot_json = {
            key: value for key, value in task.snapshot_json.items() if key != "package_contracts"
        }
        await session.commit()
    result = await generate_image(backend, context)
    assert result.status_code == 201, result.text
    assert result.json()["productionContext"]["contractHash"]
    assert len(app.state.wavespeed_adapter.submissions) == 1


@pytest.mark.parametrize("revoked", ["approval", "license"])
@pytest.mark.asyncio
async def test_package_production_rechecks_product_approval_and_license(backend, revoked):
    _, app, _, _ = backend
    context, plan, _ = await planned(backend)
    async with app.state.database.session_factory() as session:
        version = await session.get(
            ProductVersion, uuid.UUID(plan["snapshot"]["product_version"]["product_version_id"]),
        )
        if revoked == "approval":
            version.status = ProductVersionStatus.DRAFT
        else:
            version.license_status = ProductLicenseStatus.UNKNOWN
        await session.commit()
    result = await generate_image(backend, context)
    assert result.status_code == 409, result.text
    assert result.json()["detail"]["code"] == "CREATIVE_PRODUCT_NOT_APPROVED"
    assert app.state.wavespeed_adapter.submissions == []


@pytest.mark.asyncio
async def test_worker_losing_its_claim_during_localization_cannot_submit(backend, monkeypatch):
    _, app, settings, _ = backend
    context, _, _ = await planned(backend)
    _, upload_id = await qualified_image(backend, context)
    install_preparation_double(monkeypatch)
    created = await create_video(backend, context, upload_id)
    assert created.status_code == 201, created.text
    executor = VideoExecutorDouble()
    supervisor = RunnerSupervisor(
        app.state.libtv_adapter, app.state.object_store, settings, kling_adapter=executor,
    )
    monkeypatch.setattr("libtv_agent.runner.supervisor.real_provider_submission_authorized",
                        lambda _: True)
    monkeypatch.setattr(type(settings), "kling_provider_submission_enabled", lambda *_: True)
    original = app.state.object_store.localize
    async def reclaim(*args, **kwargs):
        async with app.state.database.session_factory() as session:
            command = await session.scalar(select(GenerationCommand))
            command.status = CommandStatus.CLAIMED
            command.claim_owner = "another-worker"
            await session.commit()
        return await original(*args, **kwargs)
    monkeypatch.setattr(app.state.object_store, "localize", reclaim)
    async with app.state.database.session_factory() as session:
        command = await session.scalar(select(GenerationCommand))
        assert await supervisor._execute(session, command.id) is None
    assert executor.requests == []


@pytest.mark.asyncio
async def test_preexisting_image_batch_without_package_field_replays_unchanged(backend):
    from libtv_agent.api.image_generations import ImageBatchManifest, _expand_manifest
    from libtv_agent.services.image_generations import create_batch_record, request_fingerprint
    from test_image_generation_batches import _manifest, _multipart
    client, app, settings, headers = backend
    manifest = _manifest()
    data, files = _multipart(manifest)
    normalized = ImageBatchManifest.model_validate(manifest)
    legacy_manifest = normalized.model_dump(mode="json")
    legacy_manifest.pop("creativePackage")
    hashes = [hashlib.sha256(upload[1][1]).hexdigest() for upload in files]
    async with app.state.database.session_factory() as session:
        batch = create_batch_record(
            user_id=uuid.UUID(settings.dev_user_id), idempotency_key="legacy-image",
            request_hash=request_fingerprint(legacy_manifest, hashes),
            manifest=legacy_manifest,
            item_specs=_expand_manifest(normalized, len(files)),
        )
        for item in batch.items:
            item.status = "PROCESSING"
            item.provider_task_id = "already-submitted"
        session.add(batch)
        await session.commit()
        batch_id = str(batch.id)
    result = await client.post(
        "/api/v1/image-generation-batches",
        headers={**headers, "Idempotency-Key": "legacy-image"}, data=data, files=files,
    )
    assert result.status_code == 201, result.text
    assert result.json()["id"] == batch_id
    assert result.json()["productionContext"] is None
    assert app.state.wavespeed_adapter.submissions == []
