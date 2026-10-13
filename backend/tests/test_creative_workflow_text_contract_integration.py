from __future__ import annotations

import io
import uuid
from copy import deepcopy
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient
from libtv_agent.app import create_app
from libtv_agent.config import Settings
from libtv_agent.domain.models import (
    Base,
    CreativePromptRegistry,
    CreativeRecord,
    CreativeTask,
)
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
    def __init__(self, client, app, settings):
        self.client, self.app, self.settings = client, app, settings
        self.headers = {"X-User-Id": settings.dev_user_id}
        self.result = None

    async def create(self):
        product = await self.client.post(
            "/api/v1/products",
            headers=self.headers,
            json={"internalSkuId": str(uuid.uuid4())},
        )
        assert product.status_code == 201, product.text
        self.product_id = product.json()["id"]
        data = io.BytesIO()
        Image.new("RGB", (64, 96), "red").save(data, "PNG")
        response = await self.client.post(
            "/api/v1/creative-workflow/tasks",
            headers=self.headers,
            data={"product_id": self.product_id},
            files={"front": ("front.png", data.getvalue(), "image/png")},
        )
        assert response.status_code == 201, response.text
        self.task_id = response.json()["id"]
        self.version = 0

    async def command(self, action, expected_status=200, **kwargs):
        response = await self.client.post(
            f"/api/v1/creative-workflow/tasks/{self.task_id}/commands",
            headers=self.headers,
            json={
                "command_key": str(uuid.uuid4()),
                "expected_version": self.version,
                "action": action,
                **kwargs,
            },
        )
        assert response.status_code == expected_status, response.text
        if response.status_code == 200:
            self.result = response.json()
            self.version = self.result["state_version"]
        return response

    async def plan(self):
        await self.create()
        await self.command("analyze")
        await self.command("select_direction", direction_id="A")
        self.package = self.result["snapshot"]["package"]

    async def authorize(self, **kwargs):
        prior = self.result["snapshot"].get("authorization") if self.result else None
        if "parent_authorization_id" not in kwargs and prior:
            kwargs["parent_authorization_id"] = prior["authorization_id"]
        auth = {
            "authorization_id": str(uuid.uuid4()),
            "package_id": self.package["package_id"],
            "locks_hash": self.package["locks_hash"],
            "expires_at": (datetime.now(UTC) + timedelta(hours=1)).isoformat(),
            "max_calls": 6,
            "max_cost_micros": 6,
            **kwargs,
        }
        return await self.command("authorize", authorization=auth)

    async def generate(self):
        response = await self.command(
            "generate", package_id=self.package["package_id"]
        )
        self.package = self.result["snapshot"]["package"]
        return response


async def tamper_snapshot(flow: Flow, kind: str) -> dict:
    async with flow.app.state.database.session_factory() as session:
        task = await session.scalar(
            select(CreativeTask).where(CreativeTask.id == uuid.UUID(flow.task_id))
        )
        snapshot = deepcopy(task.snapshot_json)
        if kind == "prompt":
            snapshot["package"]["prompt"] = "tampered prompt"
        elif kind == "facts":
            snapshot["facts_snapshot"]["truth_fields"] = {"color": "blue"}
        elif kind == "locks":
            snapshot["plan"]["locks"]["user_locks"]["selected_direction"] = "B"
        elif kind == "registry":
            snapshot["registry_snapshot"]["payload_json"]["prompt"] = "tampered prompt"
        elif kind == "reality":
            snapshot["package"]["reality"][0]["decision"] = "tampered camera"
        else:
            raise AssertionError(f"unsupported tamper kind: {kind}")
        task.snapshot_json = snapshot
        await session.commit()
        return snapshot


@pytest.mark.asyncio
async def test_d4_freezes_contract_and_e1_validates_generate_and_revise(workflow):
    flow = Flow(*workflow)
    await flow.plan()
    snapshot = flow.result["snapshot"]
    frozen = snapshot["text_contract"]
    assert set(frozen) == {
        "schema_version",
        "plan",
        "package",
        "registry_snapshot",
        "facts_snapshot",
        "contract_hash",
    }
    assert frozen["package"] == snapshot["package"]
    assert frozen["registry_snapshot"]["payload_json"]["prompt"] == snapshot["package"]["prompt"]
    assert frozen["facts_snapshot"]["source_hash"] == snapshot["asset"]["sha256"]

    async with flow.app.state.database.session_factory() as session:
        records = list(
            await session.scalars(
                select(CreativeRecord).where(
                    CreativeRecord.task_id == uuid.UUID(flow.task_id),
                    CreativeRecord.kind == "text_contract",
                )
            )
        )
        registries = list(await session.scalars(select(CreativePromptRegistry)))
    assert len(records) == 1
    assert registries[0].payload_json["manifest"]["reality_order"] == [
        "Camera",
        "Lighting",
        "Composition",
        "Human Behavior",
        "Environment",
        "Imperfection",
    ]

    await flow.authorize()
    await flow.generate()
    assert flow.result["snapshot"]["text_contract_validation"]["valid"] is True
    assert flow.result["snapshot"]["text_contract_validation"]["package_id"] == (
        flow.package["package_id"]
    )

    parent = flow.result["snapshot"]["candidates"][-1]["candidate_id"]
    await flow.authorize(loop_enabled=True, max_revisions=1)
    revised = await flow.command(
        "revise",
        candidate_id=parent,
        package_id=flow.package["package_id"],
        changed_modules=["Reality"],
        fix="change light angle",
        failure_region="shirt",
    )
    flow.package = revised.json()["snapshot"]["package"]
    revised_snapshot = revised.json()["snapshot"]
    assert revised_snapshot["text_contract"]["package"] == flow.package
    assert revised_snapshot["text_contract_validation"]["valid"] is True
    async with flow.app.state.database.session_factory() as session:
        records = list(
            await session.scalars(
                select(CreativeRecord).where(
                    CreativeRecord.task_id == uuid.UUID(flow.task_id),
                    CreativeRecord.kind == "text_contract",
                )
            )
        )
    assert len(records) == 2


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["prompt", "facts", "locks", "registry", "reality"])
async def test_e1_contract_tampering_blocks_without_prompt_rewrite(workflow, kind):
    flow = Flow(*workflow)
    await flow.plan()
    await flow.authorize()
    tampered = await tamper_snapshot(flow, kind)
    response = await flow.command(
        "generate",
        package_id=flow.package["package_id"],
        expected_status=409,
    )
    detail = response.json()["detail"]
    assert detail["code"] == "TEXT_CONTRACT_REJECTED"
    assert detail["contract_failures"]

    read = await flow.client.get(
        f"/api/v1/creative-workflow/tasks/{flow.task_id}",
        headers=flow.headers,
    )
    stored = read.json()["snapshot"]
    assert stored["calls"] == 0
    assert stored["candidates"] == []
    assert stored["package"]["prompt"] == tampered["package"]["prompt"]
