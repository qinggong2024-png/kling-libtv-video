import uuid
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
from libtv_agent.db import Database
from libtv_agent.domain.models import Base, SubjectElementJob
from libtv_agent.services import subject_elements
from sqlalchemy import select


@pytest.mark.asyncio
async def test_recovery_reschedules_future_retry_and_resets_interrupted_job(
    tmp_path,
    monkeypatch,
) -> None:
    database = Database(
        f"sqlite+aiosqlite:///{(tmp_path / 'subject-recovery.db').as_posix()}"
    )
    async with database.engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    future_retry_task_id = uuid.uuid4()
    interrupted_task_id = uuid.uuid4()
    user_id = uuid.uuid4()
    future_retry_at = datetime.now(UTC) + timedelta(minutes=5)
    async with database.session_factory() as session:
        session.add_all(
            [
                SubjectElementJob(
                    parent_task_id=future_retry_task_id,
                    user_id=user_id,
                    external_task_id=f"future-{future_retry_task_id.hex}",
                    name="future-retry",
                    description="retry after provider backoff",
                    status="FAILED",
                    attempt_count=1,
                    next_attempt_at=future_retry_at,
                ),
                SubjectElementJob(
                    parent_task_id=interrupted_task_id,
                    user_id=user_id,
                    external_task_id=f"interrupted-{interrupted_task_id.hex}",
                    name="interrupted",
                    description="resume after process shutdown",
                    status="PROCESSING",
                    attempt_count=1,
                ),
            ]
        )
        await session.commit()

    scheduled: list[tuple[uuid.UUID, uuid.UUID]] = []

    def record_schedule(app, *, task_id, user_id):
        del app
        scheduled.append((task_id, user_id))
        return True

    monkeypatch.setattr(
        subject_elements,
        "schedule_subject_element_job",
        record_schedule,
    )
    app = SimpleNamespace(state=SimpleNamespace(database=database))

    assert await subject_elements.recover_subject_element_jobs(app) == 2
    assert set(scheduled) == {
        (future_retry_task_id, user_id),
        (interrupted_task_id, user_id),
    }
    async with database.session_factory() as session:
        jobs = {
            job.parent_task_id: job
            for job in await session.scalars(select(SubjectElementJob))
        }
    assert jobs[future_retry_task_id].status == "FAILED"
    assert jobs[future_retry_task_id].next_attempt_at is not None
    assert jobs[interrupted_task_id].status == "PENDING"

    await database.dispose()
