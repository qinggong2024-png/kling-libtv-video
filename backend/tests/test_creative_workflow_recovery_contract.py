from __future__ import annotations

import io
import uuid
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient
from libtv_agent.app import create_app
from libtv_agent.config import Settings
from libtv_agent.domain.models import (
    Base,
    CreativeCommand,
    CreativeRecord,
    ImageGenerationBatch,
)
from PIL import Image
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import create_async_engine


@pytest.fixture
async def recovery_env(tmp_path: Path):
    database_url = f"sqlite+aiosqlite:///{(tmp_path / 'recovery.db').as_posix()}"
    engine = create_async_engine(database_url)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    await engine.dispose()
    yield Settings(
        app_env="test",
        database_url=database_url,
        object_store_mode="local",
        ai_adapter_mode="fake",
        paid_generation_enabled=False,
        artifact_root=tmp_path / "artifacts",
        runner_root=tmp_path / "runner",
        _env_file=None,
    )


@asynccontextmanager
async def running_app(settings: Settings):
    app = create_app(settings)
    async with app.router.lifespan_context(app):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            yield app, client


def headers(settings: Settings) -> dict[str, str]:
    return {"X-User-Id": settings.dev_user_id}


async def create_task(client: AsyncClient, settings: Settings) -> tuple[str, str]:
    request_headers = headers(settings)
    product = await client.post(
        "/api/v1/products",
        headers=request_headers,
        json={"internalSkuId": str(uuid.uuid4())},
    )
    assert product.status_code == 201, product.text
    product_id = product.json()["id"]

    image = io.BytesIO()
    Image.new("RGB", (64, 96), "red").save(image, "PNG")
    task = await client.post(
        "/api/v1/creative-workflow/tasks",
        headers=request_headers,
        data={"product_id": product_id},
        files={"front": ("front.png", image.getvalue(), "image/png")},
    )
    assert task.status_code == 201, task.text
    return task.json()["id"], product_id


async def command(
    client: AsyncClient,
    settings: Settings,
    task_id: str,
    expected_version: int,
    action: str,
    *,
    command_key: str,
    **payload: object,
):
    return await client.post(
        f"/api/v1/creative-workflow/tasks/{task_id}/commands",
        headers=headers(settings),
        json={
            "command_key": command_key,
            "expected_version": expected_version,
            "action": action,
            **payload,
        },
    )


async def planned_and_authorized(
    client: AsyncClient, settings: Settings
) -> tuple[str, int, dict, dict]:
    task_id, _ = await create_task(client, settings)
    response = await command(
        client, settings, task_id, 0, "analyze", command_key="cw4c-analyze"
    )
    assert response.status_code == 200, response.text
    response = await command(
        client,
        settings,
        task_id,
        1,
        "select_direction",
        command_key="cw4c-select-direction",
        direction_id="A",
    )
    assert response.status_code == 200, response.text
    package = response.json()["snapshot"]["package"]
    authorization = {
        "authorization_id": str(uuid.uuid4()),
        "package_id": package["package_id"],
        "locks_hash": package["locks_hash"],
        "expires_at": (datetime.now(UTC) + timedelta(hours=1)).isoformat(),
        "max_calls": 6,
        "max_cost_micros": 6,
        "shot_ids": ["FIRST_FRAME"],
    }
    response = await command(
        client,
        settings,
        task_id,
        2,
        "authorize",
        command_key="cw4c-authorize",
        authorization=authorization,
    )
    assert response.status_code == 200, response.text
    return task_id, response.json()["state_version"], package, authorization


async def count_rows(app, model) -> int:
    async with app.state.database.session_factory() as session:
        return int(await session.scalar(select(func.count()).select_from(model)))


async def records_for(app, task_id: str) -> list[CreativeRecord]:
    async with app.state.database.session_factory() as session:
        return list(
            await session.scalars(
                select(CreativeRecord).where(CreativeRecord.task_id == uuid.UUID(task_id))
            )
        )


@pytest.mark.asyncio
async def test_same_command_replay_does_not_recharge_or_create_candidate(recovery_env):
    settings = recovery_env
    async with running_app(settings) as (app, client):
        task_id, version, package, _ = await planned_and_authorized(client, settings)
        payload = {
            "package_id": package["package_id"],
            "fake_outcome": "SUCCEEDED",
        }
        first = await command(
            client,
            settings,
            task_id,
            version,
            "generate",
            command_key="cw4c-generate-once",
            **payload,
        )
        assert first.status_code == 200, first.text
        original = first.json()
        repeated = await command(
            client,
            settings,
            task_id,
            version,
            "generate",
            command_key="cw4c-generate-once",
            **payload,
        )
        assert repeated.status_code == 200, repeated.text
        assert repeated.json() == original

        current = await client.get(
            f"/api/v1/creative-workflow/tasks/{task_id}", headers=headers(settings)
        )
        assert current.status_code == 200, current.text
        snapshot = current.json()["snapshot"]
        assert snapshot["candidates"] == original["snapshot"]["candidates"]
        assert snapshot["cost_micros"] == 2
        assert snapshot["total_cost_micros"] == 2
        assert await count_rows(app, ImageGenerationBatch) == 1
        assert await count_rows(app, CreativeCommand) == 4


@pytest.mark.asyncio
@pytest.mark.parametrize("outcome", ["UNKNOWN", "WRITE_UNCERTAIN"])
async def test_unknown_execution_can_only_clear_for_resume_by_reconcile(
    recovery_env, outcome
):
    settings = recovery_env
    async with running_app(settings) as (app, client):
        task_id, version, package, authorization = await planned_and_authorized(
            client, settings
        )
        unknown = await command(
            client,
            settings,
            task_id,
            version,
            "generate",
            command_key=f"cw4c-unknown-{outcome}",
            package_id=package["package_id"],
            fake_outcome=outcome,
        )
        assert unknown.status_code == 200, unknown.text
        version = unknown.json()["state_version"]
        assert unknown.json()["status"] == "ACTION_REQUIRED"
        assert unknown.json()["snapshot"]["execution_state"] == outcome
        assert unknown.json()["snapshot"]["cost_micros"] == 2
        assert unknown.json()["snapshot"]["total_cost_micros"] == 2

        for action, payload in (
            ("generate", {"package_id": package["package_id"]}),
            ("revise", {"package_id": package["package_id"]}),
            ("authorize", {"authorization": authorization}),
        ):
            blocked = await command(
                client,
                settings,
                task_id,
                version,
                action,
                command_key=f"cw4c-blocked-{outcome}-{action}",
                **payload,
            )
            assert blocked.status_code == 409, blocked.text
            assert blocked.json()["detail"]["code"] == "EXECUTION_UNKNOWN"

        missing_evidence = await command(
            client,
            settings,
            task_id,
            version,
            "reconcile",
            command_key=f"cw4c-reconcile-missing-{outcome}",
        )
        assert missing_evidence.status_code == 409, missing_evidence.text
        assert missing_evidence.json()["detail"]["code"] == "RECONCILIATION_REQUIRED"

        reconciled = await command(
            client,
            settings,
            task_id,
            version,
            "reconcile",
            command_key=f"cw4c-reconcile-{outcome}",
            reconcile_not_submitted=True,
        )
        assert reconciled.status_code == 200, reconciled.text
        assert reconciled.json()["snapshot"]["execution_state"] == "RECONCILED_NOT_SUBMITTED"
        assert reconciled.json()["snapshot"]["cost_micros"] == 0
        assert reconciled.json()["snapshot"]["total_cost_micros"] == 0
        assert "uncertain_attempt" not in reconciled.json()["snapshot"]

        resumed = await command(
            client,
            settings,
            task_id,
            reconciled.json()["state_version"],
            "generate",
            command_key=f"cw4c-resume-{outcome}",
            package_id=package["package_id"],
        )
        assert resumed.status_code == 200, resumed.text
        assert len(resumed.json()["snapshot"]["candidates"]) == 1
        assert await count_rows(app, ImageGenerationBatch) == 1


@pytest.mark.asyncio
async def test_stop_blocks_new_round_without_erasing_append_only_audit(recovery_env):
    settings = recovery_env
    async with running_app(settings) as (app, client):
        task_id, version, package, _ = await planned_and_authorized(client, settings)
        generated = await command(
            client,
            settings,
            task_id,
            version,
            "generate",
            command_key="cw4c-stop-existing-candidate",
            package_id=package["package_id"],
        )
        assert generated.status_code == 200, generated.text
        version = generated.json()["state_version"]
        before = records_for(app, task_id)
        before_keys = {(row.kind, row.record_key) for row in await before}

        stopped = await command(
            client,
            settings,
            task_id,
            version,
            "stop",
            command_key="cw4c-stop",
        )
        assert stopped.status_code == 200, stopped.text
        assert stopped.json()["snapshot"]["stopped"] is True
        assert stopped.json()["snapshot"]["stop_reason"] == "USER_STOPPED"
        assert len(stopped.json()["snapshot"]["candidates"]) == 1

        blocked = await command(
            client,
            settings,
            task_id,
            stopped.json()["state_version"],
            "revise",
            command_key="cw4c-stop-blocks-revise",
            package_id=package["package_id"],
            candidate_id=stopped.json()["snapshot"]["candidates"][0]["candidate_id"],
            changed_modules=["Reality"],
            fix="change light",
            failure_region="shirt",
        )
        assert blocked.status_code == 409, blocked.text
        assert blocked.json()["detail"]["code"] == "USER_STOPPED"

        after_keys = {(row.kind, row.record_key) for row in await records_for(app, task_id)}
        assert before_keys <= after_keys


@pytest.mark.asyncio
async def test_rebuilt_app_and_engine_resume_from_persistent_snapshot(recovery_env):
    settings = recovery_env
    task_id: str
    version: int
    package: dict

    async with running_app(settings) as (app, client):
        task_id, version, package, _ = await planned_and_authorized(client, settings)
        unknown = await command(
            client,
            settings,
            task_id,
            version,
            "generate",
            command_key="cw4c-persisted-unknown",
            package_id=package["package_id"],
            fake_outcome="UNKNOWN",
        )
        assert unknown.status_code == 200, unknown.text
        version = unknown.json()["state_version"]
        persisted = await client.get(
            f"/api/v1/creative-workflow/tasks/{task_id}", headers=headers(settings)
        )
        assert persisted.status_code == 200, persisted.text
        assert persisted.json()["snapshot"]["execution_state"] == "UNKNOWN"

    async with running_app(settings) as (app, client):
        recovered = await client.get(
            f"/api/v1/creative-workflow/tasks/{task_id}", headers=headers(settings)
        )
        assert recovered.status_code == 200, recovered.text
        assert recovered.json()["state_version"] == version
        assert recovered.json()["status"] == "ACTION_REQUIRED"
        assert recovered.json()["snapshot"]["execution_state"] == "UNKNOWN"
        assert recovered.json()["snapshot"]["cost_micros"] == 2

        reconciled = await command(
            client,
            settings,
            task_id,
            version,
            "reconcile",
            command_key="cw4c-persisted-reconcile",
            reconcile_not_submitted=True,
        )
        assert reconciled.status_code == 200, reconciled.text
        resumed = await command(
            client,
            settings,
            task_id,
            reconciled.json()["state_version"],
            "generate",
            command_key="cw4c-persisted-resume",
            package_id=package["package_id"],
        )
        assert resumed.status_code == 200, resumed.text
        assert resumed.json()["snapshot"]["execution_state"] == "SUCCEEDED"
        assert len(resumed.json()["snapshot"]["candidates"]) == 1
        assert await count_rows(app, ImageGenerationBatch) == 1
