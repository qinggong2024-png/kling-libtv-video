from __future__ import annotations

import base64
import json
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from httpx import ASGITransport, AsyncClient
from libtv_agent.app import create_app
from libtv_agent.config import Settings
from libtv_agent.domain.models import Base, ImageGenerationBatch
from libtv_agent.services.image_quota import (
    ImageQuotaExceededError,
    assert_image_quota_available,
    business_day_window,
    images_submitted_on,
)
from libtv_agent.services.points import business_date
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

PNG_BYTES = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
)


class FakeWaveSpeedAdapter:
    """Minimal stand-in that records every paid call the quota is supposed to prevent."""

    def __init__(self) -> None:
        self.submissions: list[tuple[str, dict[str, Any]]] = []

    async def upload_media(self, path: Path) -> str:
        return f"https://media.example.test/{path.name}"

    async def submit_prediction(self, model_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        self.submissions.append((model_id, payload))
        return {
            "data": {
                "id": f"prediction-{len(self.submissions)}",
                "status": "created",
                "urls": {"get": "https://api.example.test/prediction/result"},
            }
        }

    async def get_prediction(self, task_id: str) -> dict[str, Any]:
        return {"data": {"id": task_id, "status": "processing", "outputs": []}}

    def availability_snapshot(self) -> SimpleNamespace:
        return SimpleNamespace(available=True, status="WAVESPEED_READY", reason=None)

    async def verify_credentials(self) -> SimpleNamespace:
        return self.availability_snapshot()


def _manifest(*, expected: int = 1) -> dict[str, Any]:
    return {
        "clientBatchId": "client-batch-1",
        "name": "quota-probe",
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
    return (
        {"clientManifest": json.dumps(manifest)},
        [("files", (f"reference-{index}.png", PNG_BYTES, "image/png")) for index in range(2)],
    )


async def _session_factory(tmp_path: Path):
    url = f"sqlite+aiosqlite:///{(tmp_path / 'quota.db').as_posix()}"
    engine = create_async_engine(url)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    return engine, async_sessionmaker(engine, expire_on_commit=False)


async def _app(tmp_path: Path, *, daily_image_limit: int) -> tuple[Any, Settings]:
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
        daily_user_image_limit=daily_image_limit,
        _env_file=None,
    )
    settings.runner_root.mkdir(parents=True)
    app = create_app(settings)
    app.state.wavespeed_adapter = FakeWaveSpeedAdapter()
    return app, settings


async def _add_batch(session, *, user_id: uuid.UUID, images: int, created_at: datetime) -> None:
    session.add(
        ImageGenerationBatch(
            user_id=user_id,
            client_batch_id=str(uuid.uuid4()),
            idempotency_key=str(uuid.uuid4()),
            request_hash="0" * 64,
            name="quota-probe",
            provider="nanobanana",
            expected_generation_count=images,
            paid_submission_consent_at=created_at,
            request_json={},
            created_at=created_at,
        )
    )
    await session.commit()


def _window() -> tuple[datetime, datetime]:
    """Today's Asia/Shanghai business day expressed as a UTC window."""
    return business_day_window(business_date())


@pytest.mark.asyncio
async def test_usage_counts_only_this_user_and_this_shanghai_day(tmp_path: Path) -> None:
    engine, factory = await _session_factory(tmp_path)
    subject, other_user = uuid.uuid4(), uuid.uuid4()
    start, _ = _window()
    inside = start + timedelta(seconds=1)
    before = start - timedelta(seconds=1)

    async with factory() as session:
        await _add_batch(session, user_id=subject, images=7, created_at=inside)
        await _add_batch(session, user_id=subject, images=100, created_at=before)
        await _add_batch(session, user_id=other_user, images=50, created_at=inside)

        assert await images_submitted_on(session, user_id=subject) == 7
        assert await images_submitted_on(session, user_id=other_user) == 50
    await engine.dispose()


@pytest.mark.asyncio
async def test_remaining_images_are_usable_then_rejected(tmp_path: Path) -> None:
    engine, factory = await _session_factory(tmp_path)
    subject = uuid.uuid4()
    start, _ = _window()

    async with factory() as session:
        await _add_batch(
            session, user_id=subject, images=490, created_at=start + timedelta(seconds=1)
        )

        used = await assert_image_quota_available(
            session, user_id=subject, requested_images=10, daily_limit=500
        )
        assert used == 490

        with pytest.raises(ImageQuotaExceededError) as error:
            await assert_image_quota_available(
                session, user_id=subject, requested_images=11, daily_limit=500
            )
        assert (error.value.limit, error.value.used, error.value.requested) == (500, 490, 11)
        assert error.value.remaining == 10
    await engine.dispose()


@pytest.mark.asyncio
async def test_empty_ledger_and_negative_request_are_handled(tmp_path: Path) -> None:
    engine, factory = await _session_factory(tmp_path)
    subject = uuid.uuid4()

    async with factory() as session:
        assert await images_submitted_on(session, user_id=subject) == 0
        assert (
            await assert_image_quota_available(
                session, user_id=subject, requested_images=500, daily_limit=500
            )
            == 0
        )
        with pytest.raises(ValueError, match="must not be negative"):
            await assert_image_quota_available(
                session, user_id=subject, requested_images=-1, daily_limit=500
            )
    await engine.dispose()


@pytest.mark.asyncio
async def test_api_blocks_over_quota_before_any_paid_call(tmp_path: Path) -> None:
    app, settings = await _app(tmp_path, daily_image_limit=1)
    adapter = FakeWaveSpeedAdapter()
    data, files = _multipart(_manifest())

    async with app.router.lifespan_context(app):
        app.state.wavespeed_adapter = adapter
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            first = await client.post(
                "/api/v1/image-generation-batches",
                headers={"X-User-Id": settings.dev_user_id, "Idempotency-Key": "quota-key-1"},
                data=data,
                files=files,
            )
            assert first.status_code == 201, first.text

            second_data, second_files = _multipart(_manifest())
            second = await client.post(
                "/api/v1/image-generation-batches",
                headers={"X-User-Id": settings.dev_user_id, "Idempotency-Key": "quota-key-2"},
                data=second_data,
                files=second_files,
            )
            assert second.status_code == 429, second.text
            detail = second.json()["detail"]
            assert detail["code"] == "IMAGE_DAILY_LIMIT_EXCEEDED"
            assert detail["details"] == {"limit": 1, "used": 1, "requested": 1, "remaining": 0}
            assert detail["retryable"] is False

        async with app.state.database.session_factory() as session:
            stored = list(await session.scalars(select(ImageGenerationBatch)))
        assert len(stored) == 1

        # The blocked request never reached the paid provider.
        assert len(adapter.submissions) == 1


@pytest.mark.asyncio
async def test_idempotent_replay_still_works_when_quota_is_spent(tmp_path: Path) -> None:
    app, settings = await _app(tmp_path, daily_image_limit=1)
    adapter = FakeWaveSpeedAdapter()
    headers = {"X-User-Id": settings.dev_user_id, "Idempotency-Key": "replay-key"}
    data, files = _multipart(_manifest())

    async with app.router.lifespan_context(app):
        app.state.wavespeed_adapter = adapter
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            first = await client.post(
                "/api/v1/image-generation-batches", headers=headers, data=data, files=files
            )
            assert first.status_code == 201, first.text

            replay_data, replay_files = _multipart(_manifest())
            replay = await client.post(
                "/api/v1/image-generation-batches",
                headers=headers,
                data=replay_data,
                files=replay_files,
            )
            # A replayed batch was already counted, so the spent quota must not block it.
            assert replay.status_code == 201, replay.text
            assert replay.json()["id"] == first.json()["id"]

        async with app.state.database.session_factory() as session:
            stored = list(await session.scalars(select(ImageGenerationBatch)))
        assert len(stored) == 1
