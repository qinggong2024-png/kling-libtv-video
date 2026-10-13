from __future__ import annotations

import io
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient
from libtv_agent.app import create_app
from libtv_agent.config import Settings
from libtv_agent.domain.models import Base, CreativeRecord, ImageGenerationBatch
from PIL import Image
from sqlalchemy import select
from sqlalchemy.ext.asyncio import create_async_engine


@pytest.fixture
async def workflow(tmp_path: Path):
    url = f"sqlite+aiosqlite:///{(tmp_path / 'storyboard.db').as_posix()}"
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

    async def create_and_generate_first_frame(self) -> dict:
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
        self.first_frame_package = self.result["snapshot"]["package"]
        await self.authorize_first_frame()
        await self.command(
            "generate", package_id=self.first_frame_package["package_id"],
        )
        candidate = self.result["snapshot"]["candidates"][0]
        return candidate

    async def create_and_select_first_frame(self) -> None:
        candidate = await self.create_and_generate_first_frame()
        await self.command("review", candidate_id=candidate["candidate_id"],
                           decision="QUALIFIED", shot_id="FIRST_FRAME")
        await self.command("select", candidate_id=candidate["candidate_id"],
                           shot_id="FIRST_FRAME")

    async def authorize_first_frame(self) -> None:
        auth = {
            "authorization_id": str(uuid.uuid4()),
            "package_id": self.first_frame_package["package_id"],
            "locks_hash": self.first_frame_package["locks_hash"],
            "expires_at": (datetime.now(UTC) + timedelta(hours=1)).isoformat(),
            "max_calls": 6,
            "max_cost_micros": 6,
        }
        await self.command("authorize", authorization=auth)

    async def authorize_storyboard(
        self, *, expires_at: datetime | None = None, shot_ids: list[str] | None = None,
        expected_status: int = 200,
    ):
        current_auth = self.result["snapshot"]["authorization"]
        auth = {
            "authorization_id": str(uuid.uuid4()),
            "parent_authorization_id": current_auth["authorization_id"],
            "package_id": self.first_frame_package["package_id"],
            "locks_hash": self.first_frame_package["locks_hash"],
            "scope": "VIDEO_STORYBOARD",
            "shot_ids": shot_ids or ["SHOT_01"],
            "expires_at": (expires_at or datetime.now(UTC) + timedelta(hours=1)).isoformat(),
            "max_calls": 6,
            "max_cost_micros": 6,
        }
        return await self.command(
            "authorize", expected_status=expected_status, authorization=auth,
        )

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


@pytest.mark.asyncio
async def test_single_shot_storyboard_closes_mapping_and_review_loop(workflow):
    flow = Flow(*workflow)
    await flow.create_and_select_first_frame()
    await flow.authorize_storyboard()

    snapshot = flow.result["snapshot"]
    package = snapshot["storyboard"]["packages"]["SHOT_01"]
    assert snapshot["authorization"]["scope"] == "VIDEO_STORYBOARD"
    assert snapshot["authorization"]["shot_ids"] == ["SHOT_01"]
    assert package["purpose"] == "VIDEO_STORYBOARD"
    assert package["shot_id"] == "SHOT_01"
    assert package["source_first_frame_candidate_id"] == snapshot["selection"]["candidate_id"]

    await flow.command(
        "generate",
        package_id=package["package_id"],
        shot_id="SHOT_01",
    )
    assert flow.result["status"] == "STORYBOARD_REVIEW"
    storyboard = flow.result["snapshot"]["storyboard"]
    candidate = storyboard["candidates"][0]
    assert flow.result["snapshot"]["candidates"][0]["shot_id"] == "FIRST_FRAME"
    assert candidate["purpose"] == "VIDEO_STORYBOARD"
    assert candidate["shot_id"] == "SHOT_01"
    assert candidate["synthetic"] is True

    mapping = storyboard["shot_mappings"]["SHOT_01"]
    assert mapping["candidate_id"] == candidate["candidate_id"]
    assert mapping["batch_id"] == candidate["batch_id"]
    assert mapping["item_id"] == candidate["item_id"]
    assert mapping["output_id"] == candidate["output_id"]

    await flow.command(
        "review",
        candidate_id=candidate["candidate_id"],
        shot_id="SHOT_01",
        decision="QUALIFIED",
    )
    await flow.command(
        "select",
        candidate_id=candidate["candidate_id"],
        shot_id="SHOT_01",
    )
    selection = flow.result["snapshot"]["storyboard"]["selections"]["SHOT_01"]
    assert selection["purpose"] == "VIDEO_STORYBOARD"
    assert selection["shot_id"] == "SHOT_01"
    assert selection["output_id"] == candidate["output_id"]

    async with flow.app.state.database.session_factory() as session:
        records = list(await session.scalars(select(CreativeRecord)))
        batches = list(await session.scalars(select(ImageGenerationBatch)))
    storyboard_records = [
        row.payload_json for row in records
        if row.payload_json.get("shot_id") == "SHOT_01"
    ]
    assert any(
        row.get("candidate_id") == candidate["candidate_id"] for row in storyboard_records
    )
    assert any(
        batch.items[0].request_json["shotId"] == "SHOT_01"
        and batch.items[0].kind == "CREATIVE_STORYBOARD"
        for batch in batches
    )


@pytest.mark.asyncio
async def test_storyboard_requires_selected_first_frame_and_single_supported_shot(workflow):
    flow = Flow(*workflow)
    await flow.create_and_generate_first_frame()
    response = await flow.authorize_storyboard(expected_status=409)
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "FIRST_FRAME_SELECTION_REQUIRED"

    flow = Flow(*workflow)
    await flow.create_and_select_first_frame()
    invalid = await flow.authorize_storyboard(shot_ids=["SHOT_02"], expected_status=422)
    assert invalid.status_code == 422


@pytest.mark.asyncio
async def test_storyboard_rejects_expired_and_unknown_execution(workflow):
    flow = Flow(*workflow)
    await flow.create_and_select_first_frame()
    expired = await flow.authorize_storyboard(
        expires_at=datetime.now(UTC) - timedelta(seconds=1),
        expected_status=409,
    )
    assert expired.status_code == 409
    assert expired.json()["detail"]["code"] == "AUTHORIZATION_SCOPE_INVALID"

    await flow.authorize_storyboard()
    package = flow.result["snapshot"]["storyboard"]["packages"]["SHOT_01"]
    wrong_shot = await flow.command(
        "generate",
        package_id=package["package_id"],
        shot_id="SHOT_02",
        expected_status=409,
    )
    assert wrong_shot.json()["detail"]["code"] == "SHOT_ID_MISMATCH"
    unknown = await flow.command(
        "generate",
        package_id=package["package_id"],
        shot_id="SHOT_01",
        fake_outcome="UNKNOWN",
    )
    assert unknown.status_code == 200
    assert unknown.json()["status"] == "ACTION_REQUIRED"
    blocked = await flow.command(
        "generate",
        package_id=package["package_id"],
        shot_id="SHOT_01",
        expected_status=409,
    )
    assert blocked.json()["detail"]["code"] == "EXECUTION_UNKNOWN"
