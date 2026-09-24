import uuid
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from libtv_agent.api import tasks as routes
from libtv_agent.domain.enums import ParentTaskPhase
from libtv_agent.domain.models import ParentTask
from sqlalchemy import update
from test_image_quota_concurrency import world  # noqa: F401


@pytest.mark.parametrize("advanced", [ParentTaskPhase.GENERATING, ParentTaskPhase.DELIVERABLE])
async def test_cancel_cannot_overwrite_advanced_task(world, monkeypatch, advanced):  # noqa: F811
    _, factory, _, users = world
    async with factory() as seed:
        task = ParentTask(
            user_id=users[0],
            client_task_id=str(uuid.uuid4()),
            title="synthetic",
            asset_count=1,
            phase=ParentTaskPhase.AWAITING_CONFIRMATION,
        )
        seed.add(task)
        await seed.commit()
        task_id = task.id

    async def no_claim(*args, **kwargs):
        return None

    async def advance_after_read(session, actor_id, requested_id):
        stale = await session.get(ParentTask, requested_id)
        await session.commit()
        async with factory() as writer:
            await writer.execute(
                update(ParentTask)
                .where(ParentTask.id == requested_id)
                .values(
                    phase=advanced,
                    state_version=ParentTask.state_version + 1,
                )
            )
            await writer.commit()
        return stale

    monkeypatch.setattr(routes, "load_idempotent_response", no_claim)
    monkeypatch.setattr(routes, "get_task", advance_after_read)
    async with factory() as session:
        with pytest.raises(HTTPException) as error:
            await routes.cancel_task(task_id, SimpleNamespace(id=users[0]), session, "cancel")
        assert error.value.status_code == 409
        await session.rollback()
    async with factory() as verify:
        task = await verify.get(ParentTask, task_id)
        assert task.phase == advanced
        assert task.state_version == 2
