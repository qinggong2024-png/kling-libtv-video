from __future__ import annotations

import io
import uuid
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient
from libtv_agent.app import create_app
from libtv_agent.config import Settings
from libtv_agent.domain.models import Base, CreativeRecord, CreativeTask
from PIL import Image
from sqlalchemy import select
from sqlalchemy.ext.asyncio import create_async_engine


@pytest.fixture
async def workflow(tmp_path: Path):
    url = f"sqlite+aiosqlite:///{(tmp_path / 'workflow.db').as_posix()}"
    engine = create_async_engine(url)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    await engine.dispose()
    settings = Settings(
        app_env="test", database_url=url, object_store_mode="local",
        artifact_root=tmp_path / "artifacts", runner_root=tmp_path / "runner", _env_file=None,
    )
    app = create_app(settings)
    async with app.router.lifespan_context(app):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test",
        ) as client:
            yield client, app, settings


class Flow:
    def __init__(self, client, settings):
        self.client = client
        self.settings = settings
        self.headers = {"X-User-Id": settings.dev_user_id}
        self.version = 0

    async def create(self):
        product = await self.client.post(
            "/api/v1/products", headers=self.headers,
            json={"internalSkuId": str(uuid.uuid4())},
        )
        assert product.status_code == 201, product.text
        data = io.BytesIO()
        Image.new("RGB", (64, 96), "red").save(data, "PNG")
        response = await self.client.post(
            "/api/v1/creative-workflow/tasks", headers=self.headers,
            data={"product_id": product.json()["id"]},
            files={"front": ("front.png", data.getvalue(), "image/png")},
        )
        assert response.status_code == 201, response.text
        self.task_id = response.json()["id"]

    async def command(self, action, expected_status=200, **kwargs):
        response = await self.client.post(
            f"/api/v1/creative-workflow/tasks/{self.task_id}/commands",
            headers=self.headers,
            json={
                "command_key": str(uuid.uuid4()), "expected_version": self.version,
                "action": action, **kwargs,
            },
        )
        assert response.status_code == expected_status, response.text
        if response.status_code == 200:
            self.version = response.json()["state_version"]
        return response


@pytest.mark.asyncio
async def test_stop_writes_auditable_event_and_blocks_new_execution(workflow):
    client, app, settings = workflow
    flow = Flow(client, settings)
    await flow.create()
    await flow.command("stop", reason="用户暂停当前任务", impact_scope="new-execution")

    async with app.state.database.session_factory() as session:
        task = await session.scalar(select(CreativeTask).where(
            CreativeTask.id == uuid.UUID(flow.task_id),
        ))
        rows = list(await session.scalars(select(CreativeRecord).where(
            CreativeRecord.task_id == uuid.UUID(flow.task_id),
            CreativeRecord.kind == "stop",
        )))
    assert task.snapshot_json["stop_event"]["reason"] == "用户暂停当前任务"
    assert len(rows) == 1
    assert rows[0].payload_json["command_key"]
    assert rows[0].payload_json["impact_scope"] == "new-execution"

    blocked = await flow.command("analyze", expected_status=409)
    assert blocked.json()["detail"]["code"] == "USER_STOPPED"


@pytest.mark.asyncio
async def test_repeated_stop_is_idempotent_and_keeps_one_event(workflow):
    client, app, settings = workflow
    flow = Flow(client, settings)
    await flow.create()
    first = await flow.command("stop", reason="暂停", impact_scope="new-execution")
    first_result = first.json()
    replay = await client.post(
        f"/api/v1/creative-workflow/tasks/{flow.task_id}/commands",
        headers=flow.headers,
        json={
            "command_key": first_result["snapshot"]["stop_event"]["command_key"],
            "expected_version": 0,
            "action": "stop", "reason": "暂停", "impact_scope": "new-execution",
        },
    )
    assert replay.status_code == 200
    assert replay.json() == first_result
    async with app.state.database.session_factory() as session:
        rows = list(await session.scalars(select(CreativeRecord).where(
            CreativeRecord.task_id == uuid.UUID(flow.task_id),
            CreativeRecord.kind == "stop",
        )))
    assert len(rows) == 1
