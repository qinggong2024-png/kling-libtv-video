from __future__ import annotations

import io
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient
from libtv_agent.app import create_app
from libtv_agent.config import Settings
from libtv_agent.domain.models import Base, CreativeTask
from libtv_agent.services.creative_image_bridge import (
    CreativeImageBridgeRejected,
    assert_creative_image_bridge_current,
    plan_creative_image_bridge,
)
from PIL import Image
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import create_async_engine


@pytest.fixture
async def workflow(tmp_path: Path):
    url = f"sqlite+aiosqlite:///{(tmp_path / 'bridge.db').as_posix()}"
    engine = create_async_engine(url)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    await engine.dispose()
    settings = Settings(
        app_env="test",
        database_url=url,
        object_store_mode="local",
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


class Flow:
    def __init__(self, client: AsyncClient, app, settings: Settings):
        self.client = client
        self.app = app
        self.settings = settings
        self.headers = {"X-User-Id": settings.dev_user_id}
        self.version = 0
        self.result: dict | None = None

    async def command(self, action: str, expected_status: int = 200, **payload):
        response = await self.client.post(
            f"/api/v1/creative-workflow/tasks/{self.task_id}/commands",
            headers=self.headers,
            json={
                "command_key": str(uuid.uuid4()),
                "expected_version": self.version,
                "action": action,
                **payload,
            },
        )
        assert response.status_code == expected_status, response.text
        if response.status_code == 200:
            self.result = response.json()
            self.version = self.result["state_version"]
        return response

    async def ready(self) -> None:
        product = await self.client.post(
            "/api/v1/products",
            headers=self.headers,
            json={"internalSkuId": str(uuid.uuid4())},
        )
        assert product.status_code == 201, product.text
        image = io.BytesIO()
        Image.new("RGB", (64, 96), "red").save(image, "PNG")
        task = await self.client.post(
            "/api/v1/creative-workflow/tasks",
            headers=self.headers,
            data={"product_id": product.json()["id"]},
            files={"front": ("front.png", image.getvalue(), "image/png")},
        )
        assert task.status_code == 201, task.text
        self.task_id = task.json()["id"]
        await self.command("analyze")
        await self.command("select_direction", direction_id="A")
        package = self.result["snapshot"]["package"]
        authorization = {
            "authorization_id": str(uuid.uuid4()),
            "package_id": package["package_id"],
            "locks_hash": package["locks_hash"],
            "expires_at": (datetime.now(UTC) + timedelta(hours=1)).isoformat(),
            "max_calls": 6,
            "max_cost_micros": 6,
        }
        await self.command("authorize", authorization=authorization)
        await self.command("generate", package_id=package["package_id"])
        candidate = self.result["snapshot"]["candidates"][0]
        await self.command(
            "review", candidate_id=candidate["candidate_id"], decision="QUALIFIED"
        )
        await self.command("select", candidate_id=candidate["candidate_id"])


async def _task(app, task_id: str) -> CreativeTask:
    async with app.state.database.session_factory() as session:
        task = await session.scalar(
            select(CreativeTask).where(CreativeTask.id == uuid.UUID(task_id))
        )
        assert task is not None
        return task


async def _save_task(app, task: CreativeTask) -> None:
    async with app.state.database.session_factory() as session:
        await session.execute(
            update(CreativeTask).where(CreativeTask.id == task.id).values(
                state_version=task.state_version, snapshot_json=task.snapshot_json,
            )
        )
        await session.commit()


@pytest.mark.asyncio
async def test_selected_human_qualified_fake_frame_returns_non_deliverable_plan(workflow):
    flow = Flow(*workflow)
    await flow.ready()
    task = await _task(flow.app, flow.task_id)

    async with flow.app.state.database.session_factory() as session:
        plan = await plan_creative_image_bridge(
            session, task, owner_id=uuid.UUID(flow.settings.dev_user_id),
            object_store=flow.app.state.object_store,
        )
        repeated = await plan_creative_image_bridge(
            session, task, owner_id=uuid.UUID(flow.settings.dev_user_id),
            object_store=flow.app.state.object_store,
        )

    assert plan == repeated
    assert plan.idempotency_key.endswith(
        f":{plan.package_revision_id}:{plan.candidate_id}"
    )
    assert plan.qualification_scope == "OFFLINE_SYNTHETIC_ONLY"
    assert plan.human_qualification == "QUALIFIED"
    assert plan.provider_submission_allowed is False
    assert plan.ordinary_image_output_qualified is False
    assert plan.deliverable_eligible is False
    assert plan.next_steps == [
        "REAL_PROVIDER_ADAPTER_REQUIRED",
        "HUMAN_PROVIDER_AUTHORIZATION_REQUIRED",
    ]
    assert "url" not in plan.model_dump()
    assert "fake://" not in plan.model_dump_json()
    assert all(
        uuid.UUID(value)
        for value in plan.source_mapping.model_dump().values()
    )


@pytest.mark.asyncio
async def test_bridge_rejects_missing_or_nonqualified_first_frame(workflow):
    flow = Flow(*workflow)
    await flow.ready()
    task = await _task(flow.app, flow.task_id)

    async with flow.app.state.database.session_factory() as session:
        task.snapshot_json.pop("selection")
        await _save_task(flow.app, task)
        with pytest.raises(CreativeImageBridgeRejected) as missing:
            await plan_creative_image_bridge(
                session, task, owner_id=uuid.UUID(flow.settings.dev_user_id),
                object_store=flow.app.state.object_store,
            )
        assert missing.value.code == "FIRST_FRAME_SELECTION_REQUIRED"

        task.snapshot_json["selection"] = {
            "purpose": "FIRST_FRAME",
            "shot_id": "FIRST_FRAME",
            "package_id": task.snapshot_json["package"]["package_id"],
            "candidate_id": task.snapshot_json["candidates"][0]["candidate_id"],
            "selected_by": flow.settings.dev_user_id,
        }
        task.snapshot_json["latest_review"]["decision"] = "REJECTED"
        await _save_task(flow.app, task)
        with pytest.raises(CreativeImageBridgeRejected) as unqualified:
            await plan_creative_image_bridge(
                session, task, owner_id=uuid.UUID(flow.settings.dev_user_id),
                object_store=flow.app.state.object_store,
            )
        assert unqualified.value.code == "HUMAN_QUALIFICATION_REQUIRED"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("mutation", "code"),
    [
        ("unknown", "EXECUTION_UNKNOWN"),
        ("stopped", "USER_STOPPED"),
        ("revoked", "ASSET_REVOKED"),
        ("expired", "PACKAGE_EXPIRED"),
        ("hash", "SOURCE_HASH_MISMATCH"),
    ],
)
async def test_bridge_rejects_stale_or_unsafe_state(workflow, mutation, code):
    flow = Flow(*workflow)
    await flow.ready()
    task = await _task(flow.app, flow.task_id)
    snapshot = task.snapshot_json
    if mutation == "unknown":
        snapshot["execution_state"] = "UNKNOWN"
    elif mutation == "stopped":
        snapshot["stopped"] = True
    elif mutation == "revoked":
        snapshot["asset"]["revoked"] = True
    elif mutation == "expired":
        snapshot["package"]["expires_at"] = (datetime.now(UTC) - timedelta(seconds=1)).isoformat()
    else:
        snapshot["candidates"][0]["sha256"] = "f" * 64
    await _save_task(flow.app, task)

    async with flow.app.state.database.session_factory() as session:
        with pytest.raises(CreativeImageBridgeRejected) as rejected:
            await plan_creative_image_bridge(
                session, task, owner_id=uuid.UUID(flow.settings.dev_user_id),
                object_store=flow.app.state.object_store,
            )
    assert rejected.value.code == code


@pytest.mark.asyncio
async def test_old_plan_is_invalid_after_task_state_changes(workflow):
    flow = Flow(*workflow)
    await flow.ready()
    task = await _task(flow.app, flow.task_id)
    owner_id = uuid.UUID(flow.settings.dev_user_id)
    async with flow.app.state.database.session_factory() as session:
        plan = await plan_creative_image_bridge(
            session, task, owner_id=owner_id, object_store=flow.app.state.object_store,
        )
        task.state_version += 1
        await _save_task(flow.app, task)
        with pytest.raises(CreativeImageBridgeRejected) as stale:
            await assert_creative_image_bridge_current(
                session, task, plan, owner_id=owner_id,
                object_store=flow.app.state.object_store,
            )
    assert stale.value.code == "BRIDGE_PLAN_STALE"


@pytest.mark.asyncio
async def test_bridge_rejects_owner_and_source_hash_mismatch(workflow):
    flow = Flow(*workflow)
    await flow.ready()
    task = await _task(flow.app, flow.task_id)
    async with flow.app.state.database.session_factory() as session:
        with pytest.raises(CreativeImageBridgeRejected) as owner:
            await plan_creative_image_bridge(
                session, task, owner_id=uuid.uuid4(), object_store=flow.app.state.object_store,
            )
        assert owner.value.code == "OWNER_MISMATCH"

        task.snapshot_json["asset"]["sha256"] = "a" * 64
        await _save_task(flow.app, task)
        with pytest.raises(CreativeImageBridgeRejected) as source:
            await plan_creative_image_bridge(
                session, task, owner_id=uuid.UUID(flow.settings.dev_user_id),
                object_store=flow.app.state.object_store,
            )
        assert source.value.code == "ASSET_HASH_MISMATCH"
