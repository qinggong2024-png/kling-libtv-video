from __future__ import annotations

import hashlib
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from httpx import ASGITransport, AsyncClient
from libtv_agent.app import create_app
from libtv_agent.config import Settings
from libtv_agent.creative.media_qualification import is_offline_synthetic_output
from libtv_agent.domain.enums import QualityDecisionStatus
from libtv_agent.domain.models import (
    Base,
    ImageGenerationBatch,
    ImageGenerationItem,
    ImageGenerationOutput,
)
from libtv_agent.services.image_generations import refresh_active_batches
from sqlalchemy import select
from sqlalchemy.ext.asyncio import create_async_engine


class CountingWaveSpeed:
    def __init__(self) -> None:
        self.queries: list[str] = []

    async def get_prediction(self, task_id: str) -> dict[str, Any]:
        self.queries.append(task_id)
        return {"data": {"id": task_id, "status": "processing", "outputs": []}}


async def _app(tmp_path: Path) -> tuple[Any, Settings]:
    database_url = f"sqlite+aiosqlite:///{(tmp_path / 'media.db').as_posix()}"
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
        _env_file=None,
    )
    settings.runner_root.mkdir(parents=True)
    app = create_app(settings)
    return app, settings


def _payload(decision: str) -> dict[str, Any]:
    return {
        "decision": decision,
        "productFidelityPass": decision == "QUALIFIED",
        "humanCriticalPass": decision == "QUALIFIED",
        "humanReviewSeconds": 5,
        "notes": "offline review" if decision == "REJECTED" else "real review",
    }


async def _add_output(
    app: Any,
    *,
    provider: str,
    provider_task_id: str,
    qualification: QualityDecisionStatus,
    quality_gates: dict[str, Any],
) -> tuple[ImageGenerationBatch, ImageGenerationOutput]:
    user_id = uuid.UUID(app.state.settings.dev_user_id)
    now = datetime.now(UTC)
    batch = ImageGenerationBatch(
        user_id=user_id,
        client_batch_id=str(uuid.uuid4()),
        idempotency_key=str(uuid.uuid4()),
        request_hash="a" * 64,
        name="media-isolation",
        provider=provider,
        status="PROCESSING",
        expected_generation_count=1,
        paid_submission_consent_at=now,
        request_json={"offlineSynthetic": provider == "fake"},
    )
    item = ImageGenerationItem(
        order_no=1,
        client_task_id=str(uuid.uuid4()),
        outfit_id="outfit",
        outfit_name="outfit",
        sku="sku",
        kind="fusion",
        view="front",
        label="front",
        prompt="prompt",
        model_id="model",
        status="PROCESSING",
        provider_task_id=provider_task_id,
        request_json={"offlineSynthetic": provider == "fake"},
    )
    raw = b"source-bytes"
    output = ImageGenerationOutput(
        order_no=1,
        remote_url=f"fake://{provider_task_id}" if provider == "fake" else "https://cdn.test/image.png",
        object_key="users/test/image.png",
        content_type="image/png",
        sha256=hashlib.sha256(raw).hexdigest(),
        qualification_status=qualification,
        quality_gates_json=quality_gates,
    )
    item.outputs.append(output)
    batch.items.append(item)
    async with app.state.database.session_factory() as session:
        session.add(batch)
        await session.commit()
        await session.refresh(batch)
        await session.refresh(output)
    return batch, output


@pytest.mark.asyncio
async def test_offline_review_cannot_upgrade_and_rejection_preserves_source_evidence(
    tmp_path: Path,
) -> None:
    app, settings = await _app(tmp_path)
    async with app.router.lifespan_context(app):
        batch, output = await _add_output(
            app,
            provider="fake",
            provider_task_id="fake:creative",
            qualification=QualityDecisionStatus.QUALIFIED,
            quality_gates={"synthetic": True, "qualification": "OFFLINE_SYNTHETIC_ONLY"},
        )
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            qualified = await client.put(
                f"/api/v1/image-generation-outputs/{output.id}/quality-decision",
                headers={"X-User-Id": settings.dev_user_id},
                json=_payload("QUALIFIED"),
            )
            assert qualified.status_code == 409
            assert qualified.json()["detail"]["code"] == "OFFLINE_SYNTHETIC_ONLY"

            rejected = await client.put(
                f"/api/v1/image-generation-outputs/{output.id}/quality-decision",
                headers={"X-User-Id": settings.dev_user_id},
                json=_payload("REJECTED"),
            )
            assert rejected.status_code == 200
            assert rejected.json()["qualificationStatus"] == "REJECTED"
            assert rejected.json()["qualityGates"]["synthetic"] is True
            assert rejected.json()["qualityGates"]["qualification"] == "OFFLINE_SYNTHETIC_ONLY"
            assert "offlineReview" in rejected.json()["qualityGates"]

        async with app.state.database.session_factory() as session:
            stored = await session.scalar(
                select(ImageGenerationOutput).where(ImageGenerationOutput.id == output.id)
            )
            assert stored is not None
            assert stored.qualification_status is QualityDecisionStatus.REJECTED
            assert stored.quality_gates_json["qualification"] == "OFFLINE_SYNTHETIC_ONLY"


@pytest.mark.asyncio
async def test_source_header_rejects_historically_misqualified_offline_output(
    tmp_path: Path,
) -> None:
    app, settings = await _app(tmp_path)
    async with app.router.lifespan_context(app):
        _batch, output = await _add_output(
            app,
            provider="fake",
            provider_task_id="fake:creative",
            qualification=QualityDecisionStatus.QUALIFIED,
            quality_gates={"synthetic": True},
        )
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post(
                "/api/v1/uploads",
                headers={
                    "X-User-Id": settings.dev_user_id,
                    "Idempotency-Key": "offline-source",
                    "X-Source-Image-Output-Id": str(output.id),
                },
                files={"file": ("source.png", b"source-bytes", "image/png")},
            )
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "SOURCE_IMAGE_OFFLINE_SYNTHETIC"


@pytest.mark.asyncio
async def test_output_offline_marker_blocks_wavespeed_review_and_source_upload(
    tmp_path: Path,
) -> None:
    app, settings = await _app(tmp_path)
    async with app.router.lifespan_context(app):
        _batch, output = await _add_output(
            app,
            provider="wavespeed",
            provider_task_id="historical-provider-id",
            qualification=QualityDecisionStatus.PENDING,
            quality_gates={"synthetic": True, "qualification": "OFFLINE_SYNTHETIC_ONLY"},
        )
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            qualified = await client.put(
                f"/api/v1/image-generation-outputs/{output.id}/quality-decision",
                headers={"X-User-Id": settings.dev_user_id},
                json=_payload("QUALIFIED"),
            )
            assert qualified.status_code == 409
            assert qualified.json()["detail"]["code"] == "OFFLINE_SYNTHETIC_ONLY"

            rejected = await client.put(
                f"/api/v1/image-generation-outputs/{output.id}/quality-decision",
                headers={"X-User-Id": settings.dev_user_id},
                json=_payload("REJECTED"),
            )
            assert rejected.status_code == 200
            assert rejected.json()["qualityGates"]["synthetic"] is True
            assert rejected.json()["qualityGates"]["qualification"] == "OFFLINE_SYNTHETIC_ONLY"

        _batch, historical = await _add_output(
            app,
            provider="wavespeed",
            provider_task_id="historical-provider-id-2",
            qualification=QualityDecisionStatus.QUALIFIED,
            quality_gates={
                "qualification_scope": "OFFLINE_SYNTHETIC_ONLY",
                "verification": "HUMAN_REQUIRED",
            },
        )
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            uploaded = await client.post(
                "/api/v1/uploads",
                headers={
                    "X-User-Id": settings.dev_user_id,
                    "Idempotency-Key": "offline-wavespeed-source",
                    "X-Source-Image-Output-Id": str(historical.id),
                },
                files={"file": ("source.png", b"source-bytes", "image/png")},
            )
        assert uploaded.status_code == 409
        assert uploaded.json()["detail"]["code"] == "SOURCE_IMAGE_OFFLINE_SYNTHETIC"


def test_offline_scope_alias_is_recognized_from_persisted_item() -> None:
    batch = ImageGenerationBatch(
        provider="wavespeed",
        request_json={},
    )
    item = ImageGenerationItem(
        provider_task_id="historical-provider-id",
        request_json={"qualification_scope": "OFFLINE_SYNTHETIC_ONLY"},
    )
    output = ImageGenerationOutput(
        remote_url="https://example.invalid/candidate.png",
        quality_gates_json={},
    )
    assert is_offline_synthetic_output(output, item=item, batch=batch)


@pytest.mark.asyncio
async def test_refresh_skips_offline_batch_but_keeps_real_wavespeed_refresh(
    tmp_path: Path,
) -> None:
    app, _settings = await _app(tmp_path)
    async with app.router.lifespan_context(app):
        fake_batch, _fake_output = await _add_output(
            app,
            provider="fake",
            provider_task_id="fake:creative",
            qualification=QualityDecisionStatus.PENDING,
            quality_gates={"synthetic": True},
        )
        real_batch, _real_output = await _add_output(
            app,
            provider="wavespeed",
            provider_task_id="wavespeed:real",
            qualification=QualityDecisionStatus.PENDING,
            quality_gates={},
        )
        adapter = CountingWaveSpeed()
        app.state.wavespeed_adapter = adapter
        async with app.state.database.session_factory() as session:
            refreshed = await refresh_active_batches(session, app=app)
        assert refreshed == 1
        assert adapter.queries == ["wavespeed:real"]
        assert fake_batch.id != real_batch.id
