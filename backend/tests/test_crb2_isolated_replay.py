from __future__ import annotations

import io
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient
from libtv_agent.app import create_app
from libtv_agent.config import Settings
from libtv_agent.domain.enums import QualityDecisionStatus
from libtv_agent.domain.models import (
    Base,
    ImageGenerationBatch,
    ImageQuotaReservation,
    PointsLedger,
    PointsReservation,
)
from PIL import Image
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import create_async_engine


@pytest.fixture
async def isolated_workflow(tmp_path: Path):
    database_url = f"sqlite+aiosqlite:///{(tmp_path / 'crb2.db').as_posix()}"
    engine = create_async_engine(database_url)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    await engine.dispose()
    settings = Settings(
        app_env="test",
        database_url=database_url,
        object_store_mode="local",
        ai_adapter_mode="fake",
        paid_generation_enabled=False,
        artifact_root=tmp_path / "artifacts",
        runner_root=tmp_path / "runner",
        _env_file=None,
    )
    app = create_app(settings)
    async with app.router.lifespan_context(app):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            yield client, app, settings


async def _create_planned_task(client: AsyncClient, settings: Settings) -> tuple[str, str, dict]:
    headers = {"X-User-Id": settings.dev_user_id}
    product = await client.post(
        "/api/v1/products",
        headers=headers,
        json={"internalSkuId": str(uuid.uuid4())},
    )
    assert product.status_code == 201, product.text
    product_id = product.json()["id"]

    image = io.BytesIO()
    Image.new("RGB", (64, 96), "red").save(image, "PNG")
    task = await client.post(
        "/api/v1/creative-workflow/tasks",
        headers=headers,
        data={"product_id": product_id},
        files={"front": ("front.png", image.getvalue(), "image/png")},
    )
    assert task.status_code == 201, task.text
    task_id = task.json()["id"]

    async def command(version: int, action: str, key: str, **payload: object):
        response = await client.post(
            f"/api/v1/creative-workflow/tasks/{task_id}/commands",
            headers=headers,
            json={
                "command_key": key,
                "expected_version": version,
                "action": action,
                **payload,
            },
        )
        assert response.status_code == 200, response.text
        return response.json()

    await command(0, "analyze", "crb2-analyze")
    selected = await command(1, "select_direction", "crb2-select", direction_id="A")
    package = selected["snapshot"]["package"]
    authorization = {
        "authorization_id": str(uuid.uuid4()),
        "package_id": package["package_id"],
        "locks_hash": package["locks_hash"],
        "expires_at": (datetime.now(UTC) + timedelta(hours=1)).isoformat(),
        "max_calls": 6,
        "max_cost_micros": 6,
        "shot_ids": ["FIRST_FRAME"],
    }
    authorized = await command(2, "authorize", "crb2-authorize", authorization=authorization)
    return task_id, product_id, {
        "headers": headers,
        "version": authorized["state_version"],
        "package": package,
        "command": command,
    }


async def _count(session, model) -> int:
    return int(await session.scalar(select(func.count()).select_from(model)))


@pytest.mark.asyncio
async def test_first_frame_replay_maps_traceable_synthetic_output_and_local_recovery(
    isolated_workflow, monkeypatch
):
    client, app, settings = isolated_workflow
    task_id, _product_id, state = await _create_planned_task(client, settings)

    def forbidden(*args, **kwargs):
        del args, kwargs
        raise AssertionError("CRB-2 isolated replay reached a provider or network path")

    monkeypatch.setattr("libtv_agent.adapters.wavespeed.WaveSpeedAdapter.upload_media", forbidden)
    monkeypatch.setattr(
        "libtv_agent.adapters.wavespeed.WaveSpeedAdapter.submit_prediction", forbidden
    )
    monkeypatch.setattr("urllib.request.urlopen", forbidden)

    payload = {
        "command_key": "crb2-generate-once",
        "expected_version": state["version"],
        "action": "generate",
        "package_id": state["package"]["package_id"],
        "fake_outcome": "SUCCEEDED",
    }
    first = await client.post(
        f"/api/v1/creative-workflow/tasks/{task_id}/commands",
        headers=state["headers"],
        json=payload,
    )
    assert first.status_code == 200, first.text
    repeated = await client.post(
        f"/api/v1/creative-workflow/tasks/{task_id}/commands",
        headers=state["headers"],
        json=payload,
    )
    assert repeated.status_code == 200, repeated.text
    assert repeated.json() == first.json()

    candidate = first.json()["snapshot"]["candidates"][0]
    async with app.state.database.session_factory() as session:
        batches = list(await session.scalars(select(ImageGenerationBatch)))
        assert len(batches) == 1
        batch = batches[0]
        item = batch.items[0]
        output = item.outputs[0]
        assert batch.provider == "fake"
        assert batch.status == "COMPLETED"
        assert item.provider_task_id == candidate["candidate_id"]
        assert output.remote_url == f"fake://{candidate['candidate_id']}"
        assert output.qualification_status is QualityDecisionStatus.PENDING
        assert output.quality_gates_json == {
            "synthetic": True,
            "qualification": "OFFLINE_SYNTHETIC_ONLY",
            "qualificationScope": "OFFLINE_SYNTHETIC_ONLY",
            "qualified": False,
            "deliverableEligible": False,
            "packageRevision": state["package"]["revision"],
            "productVersionId": batch.request_json["productVersionId"],
            "sourceHash": batch.request_json["sourceHash"],
        }
        assert batch.request_json["packageId"] == state["package"]["package_id"]
        assert batch.request_json["shotId"] == "FIRST_FRAME"
        assert batch.request_json["qualificationScope"] == "OFFLINE_SYNTHETIC_ONLY"
        assert await _count(session, ImageQuotaReservation) == 0
        assert await _count(session, PointsReservation) == 0
        assert await _count(session, PointsLedger) == 0
        batch_id = str(batch.id)

    recovery = await client.post(
        "/api/v1/submission-recovery/query",
        headers=state["headers"],
        json={"kind": "image", "idempotencyKey": candidate["candidate_id"]},
    )
    assert recovery.status_code == 200, recovery.text
    assert recovery.json()["state"] == "submitted"
    assert recovery.json()["resourceId"] == batch_id
    assert recovery.json()["retryAllowed"] is False
    assert recovery.json()["requiresAdminReview"] is False


@pytest.mark.asyncio
async def test_source_hash_change_fails_closed_without_creating_a_batch(isolated_workflow):
    client, app, settings = isolated_workflow
    task_id, _product_id, state = await _create_planned_task(client, settings)
    task = await client.get(
        f"/api/v1/creative-workflow/tasks/{task_id}",
        headers=state["headers"],
    )
    assert task.status_code == 200, task.text
    object_key = task.json()["snapshot"]["asset"]["object_key"]
    source = await app.state.object_store.localize(object_key, Path("crb2-source"))
    original = source.read_bytes()
    source.write_bytes(b"changed-after-package-freeze")
    try:
        response = await client.post(
            f"/api/v1/creative-workflow/tasks/{task_id}/commands",
            headers=state["headers"],
            json={
                "command_key": "crb2-source-hash-change",
                "expected_version": state["version"],
                "action": "generate",
                "package_id": state["package"]["package_id"],
            },
        )
    finally:
        source.write_bytes(original)
    assert response.status_code == 409, response.text
    assert response.json()["detail"]["code"] == "ASSET_HASH_MISMATCH"
    async with app.state.database.session_factory() as session:
        assert await _count(session, ImageGenerationBatch) == 0


@pytest.mark.asyncio
async def test_package_change_and_product_version_change_do_not_reuse_old_authorization(
    isolated_workflow
):
    client, app, settings = isolated_workflow
    task_id, product_id, state = await _create_planned_task(client, settings)

    wrong_package = await client.post(
        f"/api/v1/creative-workflow/tasks/{task_id}/commands",
        headers=state["headers"],
        json={
            "command_key": "crb2-package-change",
            "expected_version": state["version"],
            "action": "generate",
            "package_id": "stale-package",
        },
    )
    assert wrong_package.status_code == 409, wrong_package.text
    assert wrong_package.json()["detail"]["code"] == "PACKAGE_MISMATCH"

    changed_version = await client.post(
        f"/api/v1/products/{product_id}/versions",
        headers=state["headers"],
        json={
            "sourceType": "USER_UPLOAD",
            "sourceAssetReferences": ["creative-offline/replacement"],
            "truthFields": {"color": "blue"},
        },
    )
    assert changed_version.status_code == 201, changed_version.text
    stale_source = await client.post(
        f"/api/v1/creative-workflow/tasks/{task_id}/commands",
        headers=state["headers"],
        json={
            "command_key": "crb2-product-version-change",
            "expected_version": state["version"],
            "action": "generate",
            "package_id": state["package"]["package_id"],
        },
    )
    assert stale_source.status_code == 409, stale_source.text
    assert stale_source.json()["detail"]["code"] == "PRODUCT_VERSION_STALE"
    async with app.state.database.session_factory() as session:
        assert await _count(session, ImageGenerationBatch) == 0
