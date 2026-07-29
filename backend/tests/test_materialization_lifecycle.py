from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID

import pytest
from libtv_agent.config import Settings
from libtv_agent.domain.enums import ParentTaskPhase, UserRole
from libtv_agent.domain.models import AuditEvent, Base, ParentTask, User
from libtv_agent.services.materialization_lifecycle import recover_stale_materializations
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

USER_UUID = UUID("00000000-0000-0000-0000-000000000001")


async def _create_database(path: Path) -> str:
    database_url = f"sqlite+aiosqlite:///{path.as_posix()}"
    engine = create_async_engine(database_url)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    await engine.dispose()
    return database_url


def _settings(database_url: str, tmp_path: Path) -> Settings:
    return Settings(
        app_env="test",
        database_url=database_url,
        artifact_root=tmp_path / "artifacts",
        runner_root=tmp_path / "runner",
        object_store_mode="local",
        materialization_stale_after_seconds=300,
        _env_file=None,
    )


@pytest.mark.asyncio
async def test_recover_stale_materializations_only_updates_expired_tasks(
    tmp_path: Path,
) -> None:
    database_url = await _create_database(tmp_path / "recovery.db")
    engine = create_async_engine(database_url)
    now = datetime.now(UTC)
    async with AsyncSession(engine, expire_on_commit=False) as session:
        session.add(
            User(
                id=USER_UUID,
                username="materialization-test-user",
                password_hash="offline-disabled",
                role=UserRole.USER,
            )
        )
        stale = ParentTask(
            user_id=USER_UUID,
            client_task_id="stale-materialization",
            title="Stale materialization",
            asset_count=1,
            phase=ParentTaskPhase.PREPARING,
            state_version=4,
            updated_at=now - timedelta(minutes=10),
        )
        fresh = ParentTask(
            user_id=USER_UUID,
            client_task_id="fresh-materialization",
            title="Fresh materialization",
            asset_count=1,
            phase=ParentTaskPhase.PREPARING,
            state_version=4,
            updated_at=now,
        )
        session.add_all([stale, fresh])
        await session.commit()

        recovered = await recover_stale_materializations(
            session,
            _settings(database_url, tmp_path),
            now=now,
        )

        assert recovered == [stale.id]
        await session.refresh(stale)
        await session.refresh(fresh)
        assert stale.phase == ParentTaskPhase.ACTION_REQUIRED
        assert stale.phase_reason_code == "MATERIALIZATION_INTERRUPTED"
        assert stale.state_version == 5
        assert fresh.phase == ParentTaskPhase.PREPARING
        assert await session.scalar(
            select(AuditEvent).where(AuditEvent.action == "MATERIALIZATION_STALE_RECOVERED")
        )
    await engine.dispose()
