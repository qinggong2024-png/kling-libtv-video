import asyncio
import uuid
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest
from libtv_agent.domain.enums import (
    AttemptStatus,
    ChargeStatus,
    DownloadStatus,
    GenerationStatus,
    ParentTaskPhase,
    QualityDecisionStatus,
    ReservationStatus,
    ValidationStatus,
)
from libtv_agent.domain.models import Base, GenerationAttempt, ParentTask, PointsReservation
from libtv_agent.services.points import (
    PointsLimitExceededError,
    business_date,
    reserve_points,
    settle_points,
)
from libtv_agent.services.state_machine import (
    VersionConflictError,
    aggregate_parent_phase,
    assert_transition,
    cas_attempt_status,
    cas_task_phase,
)
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine


@pytest.fixture
async def session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as value:
        yield value
    await engine.dispose()


def test_machine_rejects_illegal_transition() -> None:
    assert_transition("generationAttempt", "RUNNING", "SUCCEEDED")
    with pytest.raises(ValueError, match="illegal"):
        assert_transition("generationAttempt", "SUCCEEDED", "RUNNING")


def test_parent_phase_stays_generating_until_every_variant_is_terminal() -> None:
    ready = SimpleNamespace(
        generation_status=GenerationStatus.SUCCEEDED,
        download_status=DownloadStatus.READY,
        validation_status=ValidationStatus.PASSED,
        final_approval_status=QualityDecisionStatus.PENDING,
    )
    running = SimpleNamespace(
        generation_status=GenerationStatus.RUNNING,
        download_status=DownloadStatus.NOT_READY,
        validation_status=ValidationStatus.NOT_READY,
        final_approval_status=QualityDecisionStatus.PENDING,
    )
    failed = SimpleNamespace(
        generation_status=GenerationStatus.FAILED,
        download_status=DownloadStatus.NOT_READY,
        validation_status=ValidationStatus.NOT_READY,
        final_approval_status=QualityDecisionStatus.PENDING,
    )
    unknown = SimpleNamespace(
        generation_status=GenerationStatus.UNKNOWN,
        download_status=DownloadStatus.NOT_READY,
        validation_status=ValidationStatus.NOT_READY,
        final_approval_status=QualityDecisionStatus.PENDING,
    )
    approved = SimpleNamespace(
        generation_status=GenerationStatus.SUCCEEDED,
        download_status=DownloadStatus.READY,
        validation_status=ValidationStatus.PASSED,
        final_approval_status=QualityDecisionStatus.APPROVED,
    )

    assert aggregate_parent_phase([ready, running]) == ParentTaskPhase.GENERATING
    assert aggregate_parent_phase([ready, failed]) == ParentTaskPhase.ACTION_REQUIRED
    assert aggregate_parent_phase([approved, failed]) == ParentTaskPhase.PARTIALLY_DELIVERABLE
    assert aggregate_parent_phase([ready, ready]) == ParentTaskPhase.AWAITING_FINAL_APPROVAL
    assert aggregate_parent_phase([approved, approved]) == ParentTaskPhase.DELIVERABLE
    assert aggregate_parent_phase([failed, failed]) == ParentTaskPhase.ACTION_REQUIRED
    assert aggregate_parent_phase([unknown, running]) == ParentTaskPhase.ACTION_REQUIRED


@pytest.mark.asyncio
async def test_state_cas_detects_stale_version(session) -> None:
    task = ParentTask(
        user_id=uuid.uuid4(),
        client_task_id="client-1",
        title="task",
        asset_count=1,
        phase=ParentTaskPhase.DRAFT,
    )
    attempt = GenerationAttempt(
        id=uuid.uuid4(), variant_id=uuid.uuid4(), status=AttemptStatus.DRAFT
    )
    session.add_all([task, attempt])
    await session.commit()
    assert await cas_task_phase(session, task.id, "DRAFT", 1, "ANALYZING") == 2
    assert await cas_attempt_status(session, attempt.id, "DRAFT", 1, "MATERIALIZING") == 2
    await session.commit()
    with pytest.raises(VersionConflictError):
        await cas_task_phase(session, task.id, "DRAFT", 1, "ANALYZING")


@pytest.mark.asyncio
async def test_points_reservation_settlement_and_shanghai_day(session) -> None:
    user_id, attempt_id = uuid.uuid4(), uuid.uuid4()
    reservation = await reserve_points(
        session,
        user_id=user_id,
        attempt_id=attempt_id,
        estimated_points=120,
        daily_limit=200,
        now=datetime(2026, 7, 26, 16, 30, tzinfo=UTC),
    )
    assert reservation.business_date.isoformat() == "2026-07-27"
    with pytest.raises(PointsLimitExceededError):
        await reserve_points(
            session,
            user_id=user_id,
            attempt_id=uuid.uuid4(),
            estimated_points=120,
            daily_limit=200,
            now=datetime(2026, 7, 26, 16, 30, tzinfo=UTC),
        )
    await settle_points(session, reservation, actual_points=100, charge_status=ChargeStatus.CHARGED)
    assert reservation.status == ReservationStatus.SETTLED
    assert business_date(datetime(2026, 7, 26, 16, 30, tzinfo=UTC)).isoformat() == "2026-07-27"


@pytest.mark.asyncio
async def test_concurrent_points_reservation_cannot_exceed_limit(tmp_path) -> None:
    engine = create_async_engine(f"sqlite+aiosqlite:///{(tmp_path / 'points.db').as_posix()}")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    user_id = uuid.uuid4()

    async def reserve(attempt_id: uuid.UUID) -> str:
        async with factory() as concurrent_session:
            try:
                await reserve_points(
                    concurrent_session,
                    user_id=user_id,
                    attempt_id=attempt_id,
                    estimated_points=120,
                    daily_limit=200,
                )
                await concurrent_session.commit()
                return "reserved"
            except PointsLimitExceededError:
                await concurrent_session.rollback()
                return "limited"

    results = await asyncio.gather(reserve(uuid.uuid4()), reserve(uuid.uuid4()))
    assert sorted(results) == ["limited", "reserved"]
    async with factory() as verification:
        count = await verification.scalar(select(func.count()).select_from(PointsReservation))
        assert count == 1
    await engine.dispose()
