import asyncio
from types import SimpleNamespace

from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from libtv_agent.api import tasks as routes
from libtv_agent.domain.models import (
    ApiIdempotencyRecord,
    GenerationAttempt,
    ParentTask,
    PointsReservation,
    StagedUpload,
)
from sqlalchemy import func, select
from test_image_quota_concurrency import world  # noqa: F401


async def test_video_create_concurrent_replay_conflict_and_fresh_app(world):  # noqa: F811
    image_app, factory, provider, users = world

    def fresh_app():
        app = FastAPI()
        app.include_router(routes.router, prefix="/api/v1")
        app.state.database = SimpleNamespace(session_factory=factory)
        app.state.settings = image_app.state.settings
        return app

    async with factory() as session:
        upload = StagedUpload(
            user_id=users[0], original_filename="synthetic.png", sha256="a" * 64,
            mime_type="image/png", size_bytes=100, width=128, height=128,
            object_key="synthetic/source.png", thumbnail_key="synthetic/thumb.png",
        )
        session.add(upload)
        await session.commit()
        upload_id = str(upload.id)

    payload = {
        "clientTaskId": "video-idempotency", "title": "synthetic video",
        "storyboards": [{"uploadId": upload_id, "order": 1}],
        "generationProvider": "kling", "variants": ["STABLE"],
    }
    headers = {"X-User-Id": str(users[0]), "Idempotency-Key": "video-create"}
    async with AsyncClient(transport=ASGITransport(app=fresh_app()), base_url="http://test") as client:
        responses = await asyncio.gather(*[
            client.post("/api/v1/tasks", headers=headers, json=payload) for _ in range(2)
        ])
        assert [response.status_code for response in responses] == [201, 201], [
            response.text for response in responses
        ]
        assert responses[0].json() == responses[1].json()
        original = responses[0].json()

    # A new application/client has no request-local replay state; the DB owns the result.
    async with AsyncClient(transport=ASGITransport(app=fresh_app()), base_url="http://test") as client:
        replay = await client.post("/api/v1/tasks", headers=headers, json=payload)
        assert replay.status_code == 201
        assert replay.json() == original
        conflict = await client.post(
            "/api/v1/tasks", headers=headers, json={**payload, "title": "changed"}
        )
        assert conflict.status_code == 409
        assert conflict.json()["detail"]["code"] == "IDEMPOTENCY_KEY_REUSED"

    async with factory() as session:
        assert await session.scalar(select(func.count()).select_from(ParentTask)) == 1
        assert await session.scalar(select(func.count()).select_from(ApiIdempotencyRecord)) == 1
        assert await session.scalar(select(func.count()).select_from(GenerationAttempt)) == 0
        assert await session.scalar(select(func.count()).select_from(PointsReservation)) == 0
    assert provider.submissions == []
