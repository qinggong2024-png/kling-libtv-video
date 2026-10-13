from __future__ import annotations

import io
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient
from libtv_agent.app import create_app
from libtv_agent.config import Settings
from libtv_agent.domain.models import Base, CreativeRecord, CreativeTask, ImageGenerationBatch
from libtv_agent.services.creative_video_bridge import (
    CreativeVideoBridgeRejected,
    assert_creative_video_bridge_current,
    plan_creative_video_bridge,
)
from PIL import Image
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import create_async_engine


@pytest.fixture
async def workflow(tmp_path: Path):
    url = f"sqlite+aiosqlite:///{(tmp_path / 'video-bridge.db').as_posix()}"
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
        first_package = self.result["snapshot"]["package"]
        await self.command(
            "authorize",
            authorization={
                "authorization_id": str(uuid.uuid4()),
                "package_id": first_package["package_id"],
                "locks_hash": first_package["locks_hash"],
                "expires_at": (datetime.now(UTC) + timedelta(hours=1)).isoformat(),
                "max_calls": 6,
                "max_cost_micros": 6,
            },
        )
        await self.command("generate", package_id=first_package["package_id"])
        first_candidate = self.result["snapshot"]["candidates"][0]
        await self.command(
            "review",
            candidate_id=first_candidate["candidate_id"],
            decision="QUALIFIED",
            shot_id="FIRST_FRAME",
        )
        await self.command(
            "select", candidate_id=first_candidate["candidate_id"], shot_id="FIRST_FRAME"
        )
        current_auth = self.result["snapshot"]["authorization"]
        await self.command(
            "authorize",
            authorization={
                "authorization_id": str(uuid.uuid4()),
                "parent_authorization_id": current_auth["authorization_id"],
                "package_id": first_package["package_id"],
                "locks_hash": first_package["locks_hash"],
                "scope": "VIDEO_STORYBOARD",
                "shot_ids": ["SHOT_01"],
                "expires_at": (datetime.now(UTC) + timedelta(hours=1)).isoformat(),
                "max_calls": 6,
                "max_cost_micros": 6,
            },
        )
        storyboard_package = self.result["snapshot"]["storyboard"]["packages"]["SHOT_01"]
        await self.command(
            "generate",
            package_id=storyboard_package["package_id"],
            shot_id="SHOT_01",
        )
        storyboard_candidate = self.result["snapshot"]["storyboard"]["candidates"][0]
        await self.command(
            "review",
            candidate_id=storyboard_candidate["candidate_id"],
            shot_id="SHOT_01",
            decision="QUALIFIED",
        )
        await self.command(
            "select", candidate_id=storyboard_candidate["candidate_id"], shot_id="SHOT_01"
        )


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
            update(CreativeTask)
            .where(CreativeTask.id == task.id)
            .values(
                state_version=task.state_version,
                status=task.status,
                snapshot_json=task.snapshot_json,
            )
        )
        await session.commit()


@pytest.mark.asyncio
async def test_director_fixed_plan_returns_dual_real_mappings_and_is_repeatable(workflow):
    flow = Flow(*workflow)
    await flow.ready()
    task = await _task(flow.app, flow.task_id)
    owner_id = uuid.UUID(flow.settings.dev_user_id)
    async with flow.app.state.database.session_factory() as session:
        before_records = len(list(await session.scalars(select(CreativeRecord))))
        before_batches = len(list(await session.scalars(select(ImageGenerationBatch))))
        plan = await plan_creative_video_bridge(
            session, task, owner_id=owner_id, object_store=flow.app.state.object_store
        )
        repeated = await plan_creative_video_bridge(
            session, task, owner_id=owner_id, object_store=flow.app.state.object_store
        )
        after_records = len(list(await session.scalars(select(CreativeRecord))))
        after_batches = len(list(await session.scalars(select(ImageGenerationBatch))))
    assert plan == repeated
    assert before_records == after_records
    assert before_batches == after_batches
    assert plan.execution_mode == "director_fixed"
    assert plan.shot_id == "SHOT_01"
    assert plan.provider_submission_allowed is False
    assert plan.deliverable_eligible is False
    assert plan.offline_synthetic_only is True
    assert plan.source_image_hashes["canonical_product"] == "f" * 64 or len(
        plan.source_image_hashes["canonical_product"]
    ) == 64
    assert plan.locked_prompt_preservation.prompt
    assert plan.locked_prompt_preservation.preservation_hash
    assert plan.first_frame.purpose == "FIRST_FRAME"
    assert plan.storyboard.purpose == "VIDEO_STORYBOARD"
    assert len(
        {
            plan.first_frame.batch_id,
            plan.storyboard.batch_id,
            plan.first_frame.item_id,
            plan.storyboard.item_id,
            plan.first_frame.output_id,
            plan.storyboard.output_id,
        }
    ) == 6
    assert "fake://" not in plan.model_dump_json()
    assert "url" not in plan.model_dump()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("mutation", "code"),
    [
        ("unknown", "EXECUTION_UNKNOWN"),
        ("stopped", "USER_STOPPED"),
        ("revoked", "ASSET_REVOKED"),
        ("expired", "PACKAGE_EXPIRED"),
        ("wrong_shot", "PACKAGE_SCOPE_INVALID"),
        ("unselected", "SELECTION_REQUIRED"),
        ("mapping", "SOURCE_MAPPING_MISMATCH"),
        ("review", "HUMAN_QUALIFICATION_REQUIRED"),
    ],
)
async def test_director_fixed_plan_rejects_unsafe_states(workflow, mutation, code):
    flow = Flow(*workflow)
    await flow.ready()
    task = await _task(flow.app, flow.task_id)
    if mutation == "unknown":
        task.snapshot_json["execution_state"] = "UNKNOWN"
    elif mutation == "stopped":
        task.snapshot_json["stopped"] = True
    elif mutation == "revoked":
        task.snapshot_json["asset"]["revoked"] = True
    elif mutation == "expired":
        task.snapshot_json["storyboard"]["packages"]["SHOT_01"]["expires_at"] = (
            datetime.now(UTC) - timedelta(seconds=1)
        ).isoformat()
    elif mutation == "wrong_shot":
        task.snapshot_json["storyboard"]["packages"]["SHOT_01"]["shot_id"] = "SHOT_02"
    elif mutation == "unselected":
        task.snapshot_json["storyboard"]["selections"].pop("SHOT_01")
    elif mutation == "mapping":
        task.snapshot_json["storyboard"]["candidates"][0]["sha256"] = "f" * 64
    elif mutation == "review":
        task.snapshot_json["storyboard"]["latest_reviews"]["SHOT_01"]["decision"] = "REJECTED"
    await _save_task(flow.app, task)
    async with flow.app.state.database.session_factory() as session:
        with pytest.raises(CreativeVideoBridgeRejected) as rejected:
            await plan_creative_video_bridge(
                session, task, owner_id=uuid.UUID(flow.settings.dev_user_id),
                object_store=flow.app.state.object_store,
            )
    assert rejected.value.code == code


@pytest.mark.asyncio
async def test_director_fixed_plan_rejects_wrong_owner(workflow):
    flow = Flow(*workflow)
    await flow.ready()
    task = await _task(flow.app, flow.task_id)
    async with flow.app.state.database.session_factory() as session:
        with pytest.raises(CreativeVideoBridgeRejected) as rejected:
            await plan_creative_video_bridge(
                session,
                task,
                owner_id=uuid.uuid4(),
                object_store=flow.app.state.object_store,
            )
    assert rejected.value.code == "OWNER_MISMATCH"


@pytest.mark.asyncio
async def test_plan_is_invalid_after_state_change_and_never_calls_legacy_video_planning(
    workflow, monkeypatch
):
    flow = Flow(*workflow)
    await flow.ready()
    task = await _task(flow.app, flow.task_id)
    owner_id = uuid.UUID(flow.settings.dev_user_id)
    called = []

    def fail(*args, **kwargs):
        called.append(True)
        raise AssertionError("legacy video planner was called")

    monkeypatch.setattr("libtv_agent.services.prompt_compiler.compile_video_plan", fail)
    monkeypatch.setattr("libtv_agent.services.feedback_learning.apply_video_learning", fail)
    async with flow.app.state.database.session_factory() as session:
        plan = await plan_creative_video_bridge(
            session, task, owner_id=owner_id, object_store=flow.app.state.object_store
        )
        task.state_version += 1
        await _save_task(flow.app, task)
        with pytest.raises(CreativeVideoBridgeRejected) as stale:
            await assert_creative_video_bridge_current(
                session, task, plan, owner_id=owner_id,
                object_store=flow.app.state.object_store,
            )
    assert stale.value.code == "BRIDGE_PLAN_STALE"
    assert called == []
