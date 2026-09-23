import asyncio
import io
import json
import os
import uuid
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from libtv_agent.api import image_generations as routes
from libtv_agent.config import Settings
from libtv_agent.db import Database
from libtv_agent.domain.models import Base, ImageGenerationBatch, User
from libtv_agent.services.runtime_control import get_runtime_config
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine


def manifest():
    return {
        "clientBatchId": "concurrent",
        "name": "quota test",
        "provider": "nanobanana",
        "modes": ["fusion"],
        "resultCount": 1,
        "aspectRatio": "9:16",
        "resolution": "2k",
        "outputFormat": "png",
        "paidSubmissionConsent": True,
        "expectedGenerationCount": 1,
        "items": [
            {
                "clientTaskId": "item",
                "outfitId": "outfit",
                "outfitName": "synthetic",
                "prompts": {"fusion": "Keep the garment.", "storyboard": ""},
                "referenceFileIndexes": [0, 1],
                "referenceRoles": [
                    {"fileIndex": 0, "role": "model.front"},
                    {"fileIndex": 1, "role": "product.front"},
                ],
            }
        ],
    }


class FakeProvider:
    def __init__(self):
        self.submissions = []
        self.uploads = 0

    async def upload_media(self, path):
        self.uploads += 1
        return "https://synthetic.example.test/reference.png"

    async def submit_prediction(self, model, payload):
        self.submissions.append((model, payload))
        return {"data": {"id": str(uuid.uuid4()), "status": "created"}}


@pytest.fixture(params=["sqlite", "postgresql"])
async def world(request, tmp_path):
    schema = None
    admin = None
    if request.param == "postgresql":
        url = os.environ.get("G1_TEST_POSTGRES_URL")
        if not url:
            pytest.skip("requires an isolated G1 PostgreSQL instance")
        from sqlalchemy.engine import make_url

        parsed = make_url(url)
        assert parsed.host == "127.0.0.1" and parsed.database == "g1_safety"
        assert parsed.port == 15439
        schema = "test_" + uuid.uuid4().hex
        admin = create_async_engine(url)
        async with admin.begin() as connection:
            await connection.execute(text(f'CREATE SCHEMA "{schema}"'))
        engine = create_async_engine(url, connect_args={"server_settings": {"search_path": schema}})
    else:
        engine = Database(f"sqlite+aiosqlite:///{tmp_path / 'quota.db'}").engine
    factory = async_sessionmaker(engine, expire_on_commit=False)
    settings = Settings(
        _env_file=None,
        app_env="test",
        object_store_mode="local",
        runner_root=tmp_path / "runner",
        artifact_root=tmp_path / "artifacts",
        wavespeed_enabled=True,
        wavespeed_api_key="synthetic-test-only",
        paid_submissions_paused=False,
        daily_user_image_limit=1,
    )
    users = [uuid.uuid4(), uuid.uuid4()]
    try:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        async with factory() as session:
            session.add_all(
                [User(id=user, username=str(user), password_hash="disabled") for user in users]
            )
            await get_runtime_config(session, settings)
            await session.commit()
        app = FastAPI()
        app.include_router(routes.router, prefix="/api/v1")
        app.state.database = SimpleNamespace(session_factory=factory)
        app.state.settings = settings
        provider = FakeProvider()
        app.state.wavespeed_adapter = provider
        yield app, factory, provider, users
    finally:
        await engine.dispose()
        if admin is not None:
            async with admin.begin() as connection:
                await connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
            await admin.dispose()


async def post(client, user, key, *, name="quota test"):
    from PIL import Image

    buffer = io.BytesIO()
    Image.new("RGB", (128, 128), "white").save(buffer, format="PNG")
    payload = manifest()
    payload["name"] = name
    return await client.post(
        "/api/v1/image-generation-batches",
        headers={"X-User-Id": str(user), "Idempotency-Key": key},
        data={"clientManifest": json.dumps(payload)},
        files=[("files", (f"source-{i}.png", buffer.getvalue(), "image/png")) for i in range(2)],
    )


async def test_last_image_is_reserved_once(world, monkeypatch):
    app, factory, provider, users = world
    original = routes.assert_image_quota_available

    async def slow_check(*args, **kwargs):
        result = await original(*args, **kwargs)
        # Keep the vulnerable read/insert window open across independent DB sessions.
        await asyncio.sleep(0.15)
        return result

    monkeypatch.setattr(routes, "assert_image_quota_available", slow_check)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        results = await asyncio.gather(post(client, users[0], "a"), post(client, users[0], "b"))
    codes = sorted(r.status_code for r in results)
    assert codes == [201, 429], (codes, len(provider.submissions))
    assert len(provider.submissions) == 1
    assert provider.uploads == 2
    async with factory() as session:
        assert await session.scalar(select(func.count()).select_from(ImageGenerationBatch)) == 1


async def test_concurrent_replay_and_conflict_do_not_consume_quota(world):
    app, factory, provider, users = world
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        results = await asyncio.gather(
            post(client, users[0], "same"), post(client, users[0], "same")
        )
        assert [r.status_code for r in results] == [201, 201]
        assert results[0].json()["id"] == results[1].json()["id"]
        conflict = await post(client, users[0], "same", name="different")
        assert conflict.status_code == 409
        assert (await post(client, users[0], "new")).status_code == 429
        assert (await post(client, users[1], "same")).status_code == 201
    assert len(provider.submissions) == 2
    async with factory() as session:
        assert await session.scalar(select(func.count()).select_from(ImageGenerationBatch)) == 2


async def test_quota_lock_is_released_before_provider_io(world):
    app, _, provider, users = world
    entered, release = asyncio.Event(), asyncio.Event()
    original = provider.submit_prediction

    async def blocked_submit(*args):
        entered.set()
        await release.wait()
        return await original(*args)

    provider.submit_prediction = blocked_submit
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        first = asyncio.create_task(post(client, users[0], "first"))
        try:
            await asyncio.wait_for(entered.wait(), 5)
            second = await asyncio.wait_for(post(client, users[0], "second"), 3)
            assert second.status_code == 429
        finally:
            release.set()
            result = await first
        assert result.status_code == 201
    assert len(provider.submissions) == 1


async def test_failed_transaction_releases_quota_lock(world, monkeypatch):
    app, _, provider, users = world
    original = routes.create_batch_record

    def fail(**kwargs):
        raise RuntimeError("injected before persistence")

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        monkeypatch.setattr(routes, "create_batch_record", fail)
        with pytest.raises(RuntimeError, match="injected"):
            await post(client, users[0], "failed")
        monkeypatch.setattr(routes, "create_batch_record", original)
        result = await asyncio.wait_for(post(client, users[0], "replacement"), 3)
        assert result.status_code == 201
    assert len(provider.submissions) == 1
