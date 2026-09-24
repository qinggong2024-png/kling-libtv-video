import json
import uuid

from httpx import ASGITransport, AsyncClient
from libtv_agent.api.events import router as events_router
from libtv_agent.api.tasks import router as tasks_router
from libtv_agent.domain.enums import ParentTaskPhase
from libtv_agent.domain.models import ParentTask
from sqlalchemy import update
from test_image_quota_concurrency import world  # noqa: F401


async def test_reconnect_uses_persisted_snapshot_and_rest_owner_scope(world):  # noqa: F811
    app, factory, _, users = world
    app.include_router(events_router, prefix="/api/v1")
    app.include_router(tasks_router, prefix="/api/v1")
    ids = [uuid.uuid4(), uuid.uuid4()]
    async with factory() as session:
        session.add_all(
            [
                ParentTask(
                    id=task_id,
                    user_id=user,
                    client_task_id=str(task_id),
                    title="synthetic",
                    asset_count=1,
                    phase=ParentTaskPhase.DRAFT,
                )
                for task_id, user in zip(ids, users, strict=True)
            ]
        )
        await session.commit()
    headers = {"X-User-Id": str(users[0])}
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        first = await client.get("/api/v1/events?once=true", headers=headers)
        assert first.status_code == 200
        old_id = next(line[4:] for line in first.text.splitlines() if line.startswith("id: "))
        async with factory() as writer:
            await writer.execute(
                update(ParentTask)
                .where(ParentTask.id == ids[0])
                .values(
                    phase=ParentTaskPhase.AWAITING_CONFIRMATION,
                    state_version=2,
                )
            )
            await writer.commit()
        second = await client.get(
            "/api/v1/events?once=true", headers={**headers, "Last-Event-ID": old_id}
        )
        payload = json.loads(
            next(line[6:] for line in second.text.splitlines() if line.startswith("data: "))
        )
        assert len(payload["tasks"]) == 1
        assert payload["tasks"][0]["id"] == str(ids[0])
        assert payload["tasks"][0]["phase"] == "AWAITING_CONFIRMATION"
        assert payload["tasks"][0]["stateVersion"] == 2
        assert str(ids[1]) not in second.text
        detail = await client.get(f"/api/v1/tasks/{ids[0]}", headers=headers)
        assert detail.status_code == 200, detail.text
        assert detail.json()["phase"] == "AWAITING_CONFIRMATION"
        forbidden = await client.get(f"/api/v1/tasks/{ids[1]}", headers=headers)
        assert forbidden.status_code in {403, 404}
