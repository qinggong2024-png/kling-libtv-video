from __future__ import annotations

import base64
import hashlib
import io
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from httpx import ASGITransport, AsyncClient
from libtv_agent.api.image_generations import ImageBatchManifest, _expand_manifest
from libtv_agent.app import create_app
from libtv_agent.config import Settings
from libtv_agent.domain.models import Base, ImageGenerationBatch, ImageGenerationItem
from libtv_agent.services.image_generations import (
    ImageBatchSubmissionError,
    _prediction_result,
    _submission_result,
    _validate_public_https_url,
)
from PIL import Image
from sqlalchemy import select
from sqlalchemy.ext.asyncio import create_async_engine


class FakeWaveSpeedAdapter:
    def __init__(self, *, submit_error: Exception | None = None) -> None:
        self.submit_error = submit_error
        self.uploads: list[Path] = []
        self.submissions: list[tuple[str, dict[str, Any]]] = []
        self.queries: list[str] = []

    async def upload_media(self, path: Path) -> str:
        self.uploads.append(path)
        return f"https://media.example.test/{path.name}"

    async def submit_prediction(self, model_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        self.submissions.append((model_id, payload))
        if self.submit_error is not None:
            raise self.submit_error
        return {
            "data": {
                "id": f"prediction-{len(self.submissions)}",
                "status": "created",
                "urls": {"get": "https://api.example.test/prediction/result"},
            }
        }

    async def get_prediction(self, task_id: str) -> dict[str, Any]:
        self.queries.append(task_id)
        return {"data": {"id": task_id, "status": "processing", "outputs": []}}

    def availability_snapshot(self) -> SimpleNamespace:
        return SimpleNamespace(available=True, status="WAVESPEED_READY", reason=None)

    async def verify_credentials(self) -> SimpleNamespace:
        return self.availability_snapshot()


async def _app(tmp_path: Path) -> tuple[Any, Settings]:
    database_url = f"sqlite+aiosqlite:///{(tmp_path / 'images.db').as_posix()}"
    engine = create_async_engine(database_url)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    await engine.dispose()
    settings = Settings(
        app_env="test",
        database_url=database_url,
        object_store_mode="local",
        artifact_root=tmp_path / "artifacts",
        runner_root=tmp_path / "runner",
        wavespeed_enabled=True,
        wavespeed_api_key="test-only-key",
        global_paused=False,
        paid_submissions_paused=False,
        _env_file=None,
    )
    settings.runner_root.mkdir(parents=True)
    return create_app(settings), settings


def _manifest(*, name: str = "catalog", expected: int = 1) -> dict[str, Any]:
    return {
        "clientBatchId": "client-batch-1",
        "name": name,
        "provider": "nanobanana",
        "modes": ["fusion"],
        "resultCount": 1,
        "aspectRatio": "9:16",
        "resolution": "2k",
        "outputFormat": "png",
        "allowBackInference": True,
        "paidSubmissionConsent": True,
        "expectedGenerationCount": expected,
        "items": [
            {
                "clientTaskId": "client-item-1",
                "outfitId": "outfit-1",
                "outfitName": "Look 1",
                "sku": "SKU-1",
                "prompts": {"fusion": "Keep the garment exact.", "storyboard": ""},
                "referenceFileIndexes": [0, 1],
                "referenceRoles": [
                    {"fileIndex": 0, "role": "model.front"},
                    {"fileIndex": 1, "role": "product.front"},
                ],
            }
        ],
    }


def _multipart(manifest: dict[str, Any]) -> tuple[dict[str, str], list[tuple[str, Any]]]:
    import json

    png = base64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
    )
    file_count = (
        max(
            reference["fileIndex"]
            for item in manifest["items"]
            for reference in item.get("referenceRoles", [])
        )
        + 1
    )
    return (
        {"clientManifest": json.dumps(manifest)},
        [("files", (f"reference-{index}.png", png, "image/png")) for index in range(file_count)],
    )


def test_manifest_rejects_multiple_generation_modes() -> None:
    manifest = _manifest()
    manifest["modes"] = ["fusion", "storyboard"]

    with pytest.raises(ValueError, match="at most 1 item"):
        ImageBatchManifest.model_validate(manifest)


def test_single_image_storyboard_prompt_keeps_fixed_reference_roles() -> None:
    manifest = ImageBatchManifest.model_validate(
        {
            "clientBatchId": "storyboard-batch",
            "name": "storyboard",
            "provider": "nanobanana",
            "modes": ["storyboard"],
            "resultCount": 1,
            "paidSubmissionConsent": True,
            "expectedGenerationCount": 1,
            "items": [
                {
                    "clientTaskId": "storyboard-item",
                    "outfitId": "outfit-1",
                    "outfitName": "Look 1",
                    "prompts": {
                        "fusion": "",
                        "storyboard": (
                            "根据图一的人物和环境，生成一张新姿势图片，"
                            "正面与图二一致，背面与图三一致"
                        ),
                    },
                    "referenceFileIndexes": [0, 1, 2],
                    "referenceRoles": [
                        {"fileIndex": 0, "role": "model.front"},
                        {"fileIndex": 1, "role": "product.front"},
                        {"fileIndex": 2, "role": "product.back"},
                    ],
                }
            ],
        }
    )

    specs = _expand_manifest(manifest, file_count=3)

    assert len(specs) == 1
    assert "Shot 1" in specs[0].prompt

    manifest.items[0].referenceRoles.pop()
    manifest.items[0].referenceFileIndexes.pop()
    with pytest.raises(ValueError, match="no product back image"):
        _expand_manifest(manifest, file_count=2)


def test_manifest_rejects_negative_and_excess_nano_references() -> None:
    invalid_index = _manifest()
    invalid_index["items"][0]["referenceFileIndexes"][0] = -1
    invalid_index["items"][0]["referenceRoles"][0]["fileIndex"] = -1
    with pytest.raises(ValueError, match="greater than or equal to 0"):
        ImageBatchManifest.model_validate(invalid_index)

    too_many = _manifest()
    too_many["items"][0]["referenceFileIndexes"] = list(range(5))
    too_many["items"][0]["referenceRoles"] = [
        {"fileIndex": index, "role": role}
        for index, role in enumerate(
            [
                "model.front",
                "product.front",
                "product.back",
                "model.back",
                "product.side",
            ]
        )
    ]
    manifest = ImageBatchManifest.model_validate(too_many)
    with pytest.raises(ValueError, match="at most 4"):
        _expand_manifest(manifest, file_count=5)


def test_provider_status_parsing_fails_closed() -> None:
    with pytest.raises(ImageBatchSubmissionError) as captured:
        _submission_result({"data": {"id": "prediction-1"}})
    assert captured.value.uncertain is True

    status, outputs, _raw, error = _prediction_result(
        {"data": {"id": "prediction-1", "outputs": []}}
    )
    assert status == "FAILED"
    assert outputs == []
    assert error is not None
    assert error["code"] == "WAVESPEED_RESPONSE_INVALID"


def test_output_urls_must_be_public_https() -> None:
    with pytest.raises(ValueError, match="public HTTPS"):
        _validate_public_https_url("http://cdn.example.test/output.png")
    with pytest.raises(ValueError, match="public addresses"):
        _validate_public_https_url("https://127.0.0.1/output.png")


def test_fusion_outputs_pair_front_and_back_references_independently() -> None:
    manifest = ImageBatchManifest.model_validate(
        {
            "clientBatchId": "fusion-batch",
            "name": "fusion",
            "provider": "nanobanana",
            "modes": ["fusion"],
            "resultCount": 1,
            "paidSubmissionConsent": True,
            "expectedGenerationCount": 2,
            "items": [
                {
                    "clientTaskId": "fusion-item",
                    "outfitId": "outfit-1",
                    "outfitName": "Look 1",
                    "prompts": {"fusion": "编辑图一，图一人物穿上图二的球衣", "storyboard": ""},
                    "referenceFileIndexes": [0, 1, 2, 3],
                    "referenceRoles": [
                        {"fileIndex": 0, "role": "model.front"},
                        {"fileIndex": 1, "role": "product.front"},
                        {"fileIndex": 2, "role": "product.back"},
                        {"fileIndex": 3, "role": "model.back"},
                    ],
                }
            ],
        }
    )

    specs = _expand_manifest(manifest, file_count=4)

    assert [(spec.view, spec.reference_file_indexes) for spec in specs] == [
        ("front", (0, 1)),
        ("back", (3, 2)),
    ]
    assert "图一为人物正面，图二为球衣正面" in specs[0].prompt
    assert "图一为人物背面参考，图二为球衣背面参考" in specs[1].prompt
    assert "必须完整保留图一原始背景与环境" in specs[0].prompt
    assert "只允许在球衣覆盖区域做必要修改" in specs[0].prompt
    assert "必须完整保留图一原始背景与环境" in specs[1].prompt
    assert "禁止生成纯色、白色、灰色、透明或摄影棚背景" in specs[1].prompt


def test_inferred_back_keeps_the_source_scene_without_locking_the_front_pose() -> None:
    manifest = ImageBatchManifest.model_validate(
        {
            "clientBatchId": "inferred-back-batch",
            "name": "inferred-back",
            "provider": "nanobanana",
            "modes": ["fusion"],
            "resultCount": 1,
            "paidSubmissionConsent": True,
            "expectedGenerationCount": 2,
            "items": [
                {
                    "clientTaskId": "inferred-back-item",
                    "outfitId": "outfit-1",
                    "outfitName": "Look 1",
                    "prompts": {"fusion": "自然换装", "storyboard": ""},
                    "referenceFileIndexes": [0, 1, 2],
                    "referenceRoles": [
                        {"fileIndex": 0, "role": "model.front"},
                        {"fileIndex": 1, "role": "product.front"},
                        {"fileIndex": 2, "role": "product.back"},
                    ],
                }
            ],
        }
    )

    specs = _expand_manifest(manifest, file_count=3)

    assert specs[1].reference_file_indexes == (0, 2)
    assert "只为呈现背面而自然调整人物朝向" in specs[1].prompt
    assert "必须保留图一背景环境的内容、空间关系" in specs[1].prompt
    assert "身体姿态、手部" not in specs[1].prompt


@pytest.mark.asyncio
async def test_batch_submission_is_idempotent_owned_and_provider_specific(tmp_path: Path) -> None:
    app, settings = await _app(tmp_path)
    adapter = FakeWaveSpeedAdapter()
    headers = {"X-User-Id": settings.dev_user_id, "Idempotency-Key": "image-key-1"}
    data, files = _multipart(_manifest())

    async with app.router.lifespan_context(app):
        app.state.wavespeed_adapter = adapter
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            created = await client.post(
                "/api/v1/image-generation-batches", headers=headers, data=data, files=files
            )
            assert created.status_code == 201, created.text
            body = created.json()
            batch_id = body["id"]
            assert body["status"] == "running"
            assert len(body["items"]) == 1
            assert adapter.submissions == [
                (
                    "google/nano-banana-2/edit",
                    {
                        "prompt": (
                            "Keep the garment exact.\n\n"
                            "当前生成正面融合图：图一为人物正面，图二为球衣正面。"
                            "以图一为唯一底图进行局部换装编辑，只替换人物身上的上衣为图二球衣。"
                            "必须完整保留图一原始背景与环境，不得抠出人物，不得移除、替换、虚化、"
                            "扩展或重构背景；保持图一人物身份、脸部、发型、身体姿态、手部、下装、"
                            "配饰、构图、机位、透视、光线、色调和画面尺寸不变。禁止生成纯色、白色、"
                            "灰色、透明或摄影棚背景。只允许在球衣覆盖区域做必要修改。"
                        ),
                        "aspect_ratio": "9:16",
                        "resolution": "2k",
                        "output_format": "png",
                        "images": [
                            "https://media.example.test/0.png",
                            "https://media.example.test/1.png",
                        ],
                        "enable_web_search": False,
                        "enable_image_search": False,
                    },
                )
            ]

            repeated = await client.post(
                "/api/v1/image-generation-batches", headers=headers, data=data, files=files
            )
            assert repeated.status_code == 201
            assert repeated.json()["id"] == batch_id
            assert len(adapter.submissions) == 1

            fetched = await client.get(
                f"/api/v1/image-generation-batches/{batch_id}",
                headers={"X-User-Id": settings.dev_user_id},
            )
            assert fetched.status_code == 200
            assert adapter.queries == ["prediction-1"]

            hidden = await client.get(
                f"/api/v1/image-generation-batches/{batch_id}",
                headers={"X-User-Id": settings.dev_admin_id},
            )
            assert hidden.status_code == 404


@pytest.mark.asyncio
async def test_batch_rejects_mismatched_count_and_idempotency_reuse(tmp_path: Path) -> None:
    app, settings = await _app(tmp_path)
    adapter = FakeWaveSpeedAdapter()
    headers = {"X-User-Id": settings.dev_user_id, "Idempotency-Key": "image-key-2"}
    invalid_data, invalid_files = _multipart(_manifest(expected=2))

    async with app.router.lifespan_context(app):
        app.state.wavespeed_adapter = adapter
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            invalid = await client.post(
                "/api/v1/image-generation-batches",
                headers=headers,
                data=invalid_data,
                files=invalid_files,
            )
            assert invalid.status_code == 422
            assert "expectedGenerationCount" in invalid.text

            data, files = _multipart(_manifest())
            created = await client.post(
                "/api/v1/image-generation-batches", headers=headers, data=data, files=files
            )
            assert created.status_code == 201
            changed_data, changed_files = _multipart(_manifest(name="different"))
            conflict = await client.post(
                "/api/v1/image-generation-batches",
                headers=headers,
                data=changed_data,
                files=changed_files,
            )
            assert conflict.status_code == 409
            assert conflict.json()["detail"]["code"] == "IDEMPOTENCY_KEY_REUSED"


@pytest.mark.asyncio
async def test_unknown_submit_outcome_is_persisted_and_never_retried(tmp_path: Path) -> None:
    app, settings = await _app(tmp_path)
    adapter = FakeWaveSpeedAdapter(submit_error=TimeoutError("socket timed out"))
    headers = {"X-User-Id": settings.dev_user_id, "Idempotency-Key": "image-key-3"}
    data, files = _multipart(_manifest())

    async with app.router.lifespan_context(app):
        app.state.wavespeed_adapter = adapter
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            created = await client.post(
                "/api/v1/image-generation-batches", headers=headers, data=data, files=files
            )
            assert created.status_code == 201
            assert created.json()["status"] == "write_uncertain"
            assert created.json()["items"][0]["error"]["code"] == ("WAVESPEED_SUBMISSION_UNCERTAIN")
            repeated = await client.post(
                "/api/v1/image-generation-batches", headers=headers, data=data, files=files
            )
            assert repeated.status_code == 201
            assert len(adapter.submissions) == 1


@pytest.mark.asyncio
async def test_unverified_adapter_is_rejected_before_upload_or_submission(tmp_path: Path) -> None:
    app, settings = await _app(tmp_path)
    adapter = FakeWaveSpeedAdapter()
    adapter.availability_snapshot = lambda: SimpleNamespace(
        available=False,
        status="WAVESPEED_CONFIGURED_UNVERIFIED",
        reason="administrator verification is required",
    )
    data, files = _multipart(_manifest())

    async with app.router.lifespan_context(app):
        app.state.wavespeed_adapter = adapter
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post(
                "/api/v1/image-generation-batches",
                headers={
                    "X-User-Id": settings.dev_user_id,
                    "Idempotency-Key": "unverified-key",
                },
                data=data,
                files=files,
            )
    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "WAVESPEED_CONFIGURED_UNVERIFIED"
    assert adapter.uploads == []
    assert adapter.submissions == []


@pytest.mark.asyncio
async def test_idempotent_recovery_only_resumes_unclaimed_pending_items(tmp_path: Path) -> None:
    app, settings = await _app(tmp_path)
    adapter = FakeWaveSpeedAdapter()
    headers = {"X-User-Id": settings.dev_user_id, "Idempotency-Key": "recovery-key"}
    data, files = _multipart(_manifest())

    async with app.router.lifespan_context(app):
        app.state.wavespeed_adapter = adapter
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            created = await client.post(
                "/api/v1/image-generation-batches", headers=headers, data=data, files=files
            )
            assert created.status_code == 201
            assert len(adapter.submissions) == 1

            # A prediction with a durable provider ID is never submitted again.
            repeated = await client.post(
                "/api/v1/image-generation-batches", headers=headers, data=data, files=files
            )
            assert repeated.status_code == 201
            assert len(adapter.uploads) == 2
            assert len(adapter.submissions) == 1

            async with app.state.database.session_factory() as session:
                item = await session.scalar(select(ImageGenerationItem))
                assert item is not None
                item.status = "PENDING"
                item.provider_task_id = None
                item.request_json = {"referenceFileIndexes": [0]}
                await session.commit()

            resumed = await client.post(
                "/api/v1/image-generation-batches", headers=headers, data=data, files=files
            )
            assert resumed.status_code == 201
            assert len(adapter.submissions) == 2

            async with app.state.database.session_factory() as session:
                item = await session.scalar(select(ImageGenerationItem))
                assert item is not None
                item.status = "SUBMITTING"
                item.provider_task_id = None
                item.request_json = {"referenceFileIndexes": [0]}
                await session.commit()

            uncertain = await client.post(
                "/api/v1/image-generation-batches", headers=headers, data=data, files=files
            )
            assert uncertain.status_code == 201
            assert uncertain.json()["status"] == "write_uncertain"
            assert len(adapter.submissions) == 2


@pytest.mark.asyncio
async def test_output_materialization_retries_without_exposing_remote_url(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    app, settings = await _app(tmp_path)
    adapter = FakeWaveSpeedAdapter()

    async def completed_prediction(task_id: str) -> dict[str, Any]:
        adapter.queries.append(task_id)
        return {
            "data": {
                "id": task_id,
                "status": "completed",
                "outputs": ["https://cdn.example.test/private-signed-output.webp?token=secret"],
            }
        }

    materialize_attempts = 0
    materialized_stream = io.BytesIO()
    Image.new("RGB", (360, 640), "#315f41").save(materialized_stream, format="PNG")
    materialized_bytes = materialized_stream.getvalue()

    async def flaky_materialize(_app: Any, output: Any) -> None:
        nonlocal materialize_attempts
        materialize_attempts += 1
        if materialize_attempts == 1:
            raise OSError("temporary CDN failure")
        local = tmp_path / f"{output.id}.png"
        local.write_bytes(materialized_bytes)
        output.object_key = await _app.state.object_store.put_file(
            local, f"image-generations/{output.id}.png", "image/png"
        )
        output.content_type = "image/png"
        output.size_bytes = len(materialized_bytes)
        output.sha256 = hashlib.sha256(materialized_bytes).hexdigest()

    adapter.get_prediction = completed_prediction  # type: ignore[method-assign]
    monkeypatch.setattr(
        "libtv_agent.services.image_generations._materialize_output", flaky_materialize
    )
    headers = {"X-User-Id": settings.dev_user_id, "Idempotency-Key": "materialize-key"}
    data, files = _multipart(_manifest())

    async with app.router.lifespan_context(app):
        app.state.wavespeed_adapter = adapter
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            created = await client.post(
                "/api/v1/image-generation-batches", headers=headers, data=data, files=files
            )
            batch_id = created.json()["id"]

            first_poll = await client.get(
                f"/api/v1/image-generation-batches/{batch_id}",
                headers={"X-User-Id": settings.dev_user_id},
            )
            assert first_poll.json()["status"] == "running"
            assert first_poll.json()["items"][0]["outputs"] == []
            assert "private-signed-output" not in first_poll.text

            second_poll = await client.get(
                f"/api/v1/image-generation-batches/{batch_id}",
                headers={"X-User-Id": settings.dev_user_id},
            )
            assert second_poll.json()["status"] == "completed"
            output = second_poll.json()["items"][0]["outputs"][0]
            assert output["url"].startswith("/api/v1/image-generation-outputs/")
            assert output["qualificationStatus"] == "PENDING"
            assert "private-signed-output" not in second_poll.text
            assert materialize_attempts == 2

            blocked_upload = await client.post(
                "/api/v1/uploads",
                headers={
                    "X-User-Id": settings.dev_user_id,
                    "Idempotency-Key": "unqualified-source-upload",
                    "X-Source-Image-Output-Id": output["id"],
                },
                files={"file": ("candidate.png", materialized_bytes, "image/png")},
            )
            assert blocked_upload.status_code == 409
            assert blocked_upload.json()["detail"]["code"] == "SOURCE_IMAGE_NOT_QUALIFIED"

            qualified = await client.put(
                f"/api/v1/image-generation-outputs/{output['id']}/quality-decision",
                headers={"X-User-Id": settings.dev_user_id},
                json={
                    "decision": "QUALIFIED",
                    "productFidelityPass": True,
                    "humanCriticalPass": True,
                    "humanReviewSeconds": 8,
                    "notes": "pilot candidate ground truth",
                },
            )
            assert qualified.status_code == 200, qualified.text
            assert qualified.json()["qualificationStatus"] == "QUALIFIED"
            assert qualified.json()["qualityGates"]["PRODUCT_FIDELITY"]["outcome"] == "PASS"

            traced_upload = await client.post(
                "/api/v1/uploads",
                headers={
                    "X-User-Id": settings.dev_user_id,
                    "Idempotency-Key": "qualified-source-upload",
                    "X-Source-Image-Output-Id": output["id"],
                },
                files={"file": ("candidate.png", materialized_bytes, "image/png")},
            )
            assert traced_upload.status_code == 201, traced_upload.text
            assert traced_upload.json()["sourceImageOutputId"] == output["id"]


@pytest.mark.asyncio
async def test_startup_recovers_active_image_batches_without_browser_polling(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    app, settings = await _app(tmp_path)
    adapter = FakeWaveSpeedAdapter()
    app.state.wavespeed_adapter = adapter
    headers = {"X-User-Id": settings.dev_user_id, "Idempotency-Key": "startup-recovery"}
    data, files = _multipart(_manifest())

    async with app.router.lifespan_context(app):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            created = await client.post(
                "/api/v1/image-generation-batches", headers=headers, data=data, files=files
            )
            assert created.status_code == 201
            assert created.json()["status"] == "running"

    async def completed_prediction(task_id: str) -> dict[str, Any]:
        adapter.queries.append(task_id)
        return {
            "data": {
                "id": task_id,
                "status": "completed",
                "outputs": ["https://cdn.example.test/recovered.png"],
            }
        }

    async def materialize(_app: Any, output: Any) -> None:
        output.object_key = f"image-generations/{output.id}.png"
        output.content_type = "image/png"
        output.size_bytes = 10
        output.sha256 = "0" * 64

    adapter.get_prediction = completed_prediction  # type: ignore[method-assign]
    monkeypatch.setattr("libtv_agent.services.image_generations._materialize_output", materialize)

    async with app.router.lifespan_context(app):
        async with app.state.database.session_factory() as session:
            batch = await session.scalar(select(ImageGenerationBatch))
            item = await session.scalar(select(ImageGenerationItem))
            assert batch is not None
            assert item is not None
            assert batch.status == "COMPLETED"
            assert item.status == "COMPLETED"
            assert item.outputs[0].object_key is not None

    assert adapter.queries == ["prediction-1"]
