import asyncio
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from uuid import UUID

import pytest
from libtv_agent.api import tasks as tasks_api
from libtv_agent.app import _shutdown_analysis_jobs, create_app
from libtv_agent.config import Settings
from libtv_agent.domain.enums import ParentTaskPhase, UserRole
from libtv_agent.domain.models import AuditEvent, Base, ParentTask, User
from libtv_agent.services.analysis_lifecycle import (
    ANALYSIS_STAGE_QUEUED,
    StaleAnalysisRunError,
    claim_analysis_run,
    fail_active_analysis,
    recover_stale_analyses,
    touch_analysis_run,
)
from libtv_agent.services.state_machine import VersionConflictError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

USER_ID = "00000000-0000-0000-0000-000000000001"
USER_UUID = UUID(USER_ID)


async def _create_database(path: Path) -> str:
    database_url = f"sqlite+aiosqlite:///{path.as_posix()}"
    engine = create_async_engine(database_url)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    await engine.dispose()
    return database_url


async def _seed_analyzing_task(session: AsyncSession, *, updated_at: datetime) -> ParentTask:
    user = User(
        id=USER_UUID,
        username="analysis-test-user",
        password_hash="offline-disabled",
        role=UserRole.USER,
    )
    task = ParentTask(
        user_id=USER_UUID,
        client_task_id="analysis-lifecycle",
        title="Analysis lifecycle",
        asset_count=1,
        phase=ParentTaskPhase.ANALYZING,
        state_version=2,
        updated_at=updated_at,
    )
    session.add_all([user, task])
    await session.commit()
    return task


def _settings(database_url: str, tmp_path: Path) -> Settings:
    return Settings(
        app_env="test",
        database_url=database_url,
        artifact_root=tmp_path / "artifacts",
        runner_root=tmp_path / "runner",
        object_store_mode="local",
        openai_analysis_timeout_seconds=1,
        openai_analysis_timeout_max_seconds=2,
        analysis_stale_after_seconds=3,
        analysis_recovery_poll_seconds=30,
        _env_file=None,
    )


@pytest.mark.asyncio
async def test_fail_active_analysis_writes_terminal_state_and_audit(tmp_path: Path) -> None:
    database_url = await _create_database(tmp_path / "failure.db")
    engine = create_async_engine(database_url)
    async with AsyncSession(engine, expire_on_commit=False) as session:
        task = await _seed_analyzing_task(session, updated_at=datetime.now(UTC))
        changed = await fail_active_analysis(
            session,
            task.id,
            reason_code="ANALYSIS_TIMEOUT",
            audit_action="ANALYSIS_REQUEST_TIMED_OUT",
            reason="provider exceeded the configured timeout",
        )
        assert changed is True
        await session.refresh(task)
        current = await session.get(ParentTask, task.id)
        event = await session.scalar(select(AuditEvent).where(AuditEvent.entity_id == str(task.id)))
        assert current is not None
        assert current.phase == ParentTaskPhase.ACTION_REQUIRED
        assert current.phase_reason_code == "ANALYSIS_TIMEOUT"
        assert current.state_version == 3
        assert event is not None
        assert event.from_state == ParentTaskPhase.ANALYZING.value
        assert event.to_state == ParentTaskPhase.ACTION_REQUIRED.value
    await engine.dispose()


@pytest.mark.asyncio
async def test_recover_stale_analyses_only_updates_expired_tasks(tmp_path: Path) -> None:
    database_url = await _create_database(tmp_path / "recovery.db")
    engine = create_async_engine(database_url)
    settings = _settings(database_url, tmp_path)
    now = datetime.now(UTC)
    async with AsyncSession(engine, expire_on_commit=False) as session:
        stale = await _seed_analyzing_task(session, updated_at=now - timedelta(seconds=10))
        fresh = ParentTask(
            user_id=USER_UUID,
            client_task_id="fresh-analysis",
            title="Fresh analysis",
            asset_count=1,
            phase=ParentTaskPhase.ANALYZING,
            state_version=2,
            updated_at=now,
        )
        session.add(fresh)
        await session.commit()

        recovered = await recover_stale_analyses(session, settings, now=now)
        assert recovered == [stale.id]
        await session.refresh(stale)
        await session.refresh(fresh)
        assert stale.phase == ParentTaskPhase.ACTION_REQUIRED
        assert stale.phase_reason_code == "ANALYSIS_STALE_RECOVERED"
        assert fresh.phase == ParentTaskPhase.ANALYZING
        assert await session.scalar(
            select(AuditEvent).where(AuditEvent.action == "ANALYSIS_STALE_RECOVERED")
        )
    await engine.dispose()


@pytest.mark.asyncio
async def test_app_startup_recovers_stale_analysis(tmp_path: Path) -> None:
    database_url = await _create_database(tmp_path / "startup.db")
    seed_engine = create_async_engine(database_url)
    async with AsyncSession(seed_engine, expire_on_commit=False) as session:
        task = await _seed_analyzing_task(
            session, updated_at=datetime.now(UTC) - timedelta(seconds=10)
        )
    await seed_engine.dispose()

    app = create_app(_settings(database_url, tmp_path))
    async with app.router.lifespan_context(app):
        async with app.state.database.session_factory() as session:
            recovered = await session.get(ParentTask, task.id)
            assert recovered is not None
            assert recovered.phase == ParentTaskPhase.ACTION_REQUIRED
            assert recovered.phase_reason_code == "ANALYSIS_STALE_RECOVERED"


@pytest.mark.asyncio
async def test_concurrent_analysis_claim_has_exactly_one_winner(tmp_path: Path) -> None:
    database_url = await _create_database(tmp_path / "claim.db")
    engine = create_async_engine(database_url)
    async with AsyncSession(engine, expire_on_commit=False) as session:
        user = User(
            id=USER_UUID,
            username="claim-test-user",
            password_hash="offline-disabled",
            role=UserRole.USER,
        )
        task = ParentTask(
            user_id=USER_UUID,
            client_task_id="claim-race",
            title="Claim race",
            asset_count=1,
            phase=ParentTaskPhase.DRAFT,
            state_version=1,
        )
        session.add_all([user, task])
        await session.commit()

    async def claim() -> object:
        async with AsyncSession(engine, expire_on_commit=False) as session:
            return await claim_analysis_run(session, task.id, USER_UUID, expected_state_version=1)

    outcomes = await asyncio.gather(claim(), claim(), return_exceptions=True)
    winners = [outcome for outcome in outcomes if isinstance(outcome, UUID)]
    conflicts = [outcome for outcome in outcomes if isinstance(outcome, VersionConflictError)]
    assert len(winners) == 1
    assert len(conflicts) == 1

    async with AsyncSession(engine, expire_on_commit=False) as session:
        current = await session.get(ParentTask, task.id)
        assert current is not None
        assert current.phase == ParentTaskPhase.ANALYZING
        assert current.analysis_run_id == winners[0]
        assert current.analysis_stage == ANALYSIS_STAGE_QUEUED
        assert current.state_version == 2
    await engine.dispose()


@pytest.mark.asyncio
async def test_old_analysis_run_cannot_touch_or_fail_a_new_retry(tmp_path: Path) -> None:
    database_url = await _create_database(tmp_path / "run-token.db")
    engine = create_async_engine(database_url)
    async with AsyncSession(engine, expire_on_commit=False) as session:
        user = User(
            id=USER_UUID,
            username="run-token-user",
            password_hash="offline-disabled",
            role=UserRole.USER,
        )
        task = ParentTask(
            user_id=USER_UUID,
            client_task_id="run-token",
            title="Run token",
            asset_count=1,
            phase=ParentTaskPhase.DRAFT,
            state_version=1,
        )
        session.add_all([user, task])
        await session.commit()
        task_id = task.id
        old_run_id = await claim_analysis_run(session, task_id, USER_UUID, 1)
        assert await fail_active_analysis(
            session,
            task_id,
            analysis_run_id=old_run_id,
            reason_code="ANALYSIS_TIMEOUT",
            audit_action="ANALYSIS_REQUEST_TIMED_OUT",
            reason="first run timed out",
        )
        new_run_id = await claim_analysis_run(session, task_id, USER_UUID, 3)

        with pytest.raises(StaleAnalysisRunError):
            await touch_analysis_run(session, task_id, old_run_id, "VALIDATING")
        assert not await fail_active_analysis(
            session,
            task_id,
            analysis_run_id=old_run_id,
            reason_code="ANALYSIS_PROVIDER_FAILED",
            audit_action="ANALYSIS_REQUEST_FAILED",
            reason="late result from old run",
        )
        current = await session.get(ParentTask, task_id)
        assert current is not None
        assert current.phase == ParentTaskPhase.ANALYZING
        assert current.analysis_run_id == new_run_id
        assert current.phase_reason_code is None
    await engine.dispose()


@pytest.mark.asyncio
async def test_heartbeat_prevents_recovery_and_stale_recovery_clears_run_token(
    tmp_path: Path,
) -> None:
    database_url = await _create_database(tmp_path / "heartbeat.db")
    engine = create_async_engine(database_url)
    settings = _settings(database_url, tmp_path)
    now = datetime.now(UTC)
    stale_run_id = UUID("00000000-0000-0000-0000-000000000011")
    fresh_run_id = UUID("00000000-0000-0000-0000-000000000012")
    async with AsyncSession(engine, expire_on_commit=False) as session:
        user = User(
            id=USER_UUID,
            username="heartbeat-user",
            password_hash="offline-disabled",
            role=UserRole.USER,
        )
        stale = ParentTask(
            user_id=USER_UUID,
            client_task_id="stale-token",
            title="Stale token",
            asset_count=1,
            phase=ParentTaskPhase.ANALYZING,
            state_version=2,
            analysis_run_id=stale_run_id,
            analysis_stage="PROVIDER_RUNNING",
            analysis_heartbeat_at=now - timedelta(seconds=10),
            updated_at=now - timedelta(seconds=10),
        )
        fresh = ParentTask(
            user_id=USER_UUID,
            client_task_id="fresh-heartbeat",
            title="Fresh heartbeat",
            asset_count=1,
            phase=ParentTaskPhase.ANALYZING,
            state_version=2,
            analysis_run_id=fresh_run_id,
            analysis_stage="PROVIDER_RUNNING",
            analysis_heartbeat_at=now,
            updated_at=now - timedelta(seconds=10),
        )
        session.add_all([user, stale, fresh])
        await session.commit()
        recovered = await recover_stale_analyses(session, settings, now=now)
        assert recovered == [stale.id]
        await session.refresh(stale)
        await session.refresh(fresh)
        assert stale.analysis_run_id is None
        assert stale.phase_reason_code == "ANALYSIS_STALE_RECOVERED"
        assert fresh.phase == ParentTaskPhase.ANALYZING
        assert fresh.analysis_run_id == fresh_run_id
    await engine.dispose()


@pytest.mark.asyncio
async def test_shutdown_cancels_active_analysis_and_persists_terminal_state(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    database_url = await _create_database(tmp_path / "shutdown.db")
    engine = create_async_engine(database_url)
    run_id = UUID("00000000-0000-0000-0000-000000000013")
    async with AsyncSession(engine, expire_on_commit=False) as session:
        task = await _seed_analyzing_task(session, updated_at=datetime.now(UTC))
        task.analysis_run_id = run_id
        task.analysis_stage = "PROVIDER_RUNNING"
        task.analysis_heartbeat_at = datetime.now(UTC)
        await session.commit()

    entered = asyncio.Event()

    async def wait_for_cancellation(*args: object, **kwargs: object) -> None:
        del args, kwargs
        entered.set()
        await asyncio.Event().wait()

    monkeypatch.setattr(tasks_api, "analyze_task", wait_for_cancellation)
    app = SimpleNamespace(
        state=SimpleNamespace(
            database=SimpleNamespace(
                session_factory=lambda: AsyncSession(engine, expire_on_commit=False)
            ),
            settings=SimpleNamespace(analysis_shutdown_grace_seconds=0.2),
            object_store=object(),
            kling_adapter=object(),
            analysis_jobs=set(),
        )
    )
    job = asyncio.create_task(tasks_api._run_analysis_job(app, task.id, USER_UUID, run_id))
    app.state.analysis_jobs.add(job)
    await entered.wait()
    await _shutdown_analysis_jobs(app)
    assert job.cancelled()

    async with AsyncSession(engine, expire_on_commit=False) as session:
        current = await session.get(ParentTask, task.id)
        assert current is not None
        assert current.phase == ParentTaskPhase.ACTION_REQUIRED
        assert current.phase_reason_code == "ANALYSIS_CANCELLED"
        assert current.analysis_run_id is None
    await engine.dispose()
