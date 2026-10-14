import asyncio
import uuid
from pathlib import Path

import pytest
from libtv_agent.config import Settings
from libtv_agent.domain.enums import AIUsageReservationStatus, UserRole
from libtv_agent.domain.models import (
    AIUsageLedger,
    AIUsageQuotaSummary,
    AIUsageReservation,
    Base,
    User,
)
from libtv_agent.services.ai_usage import (
    AIUsageLimitExceededError,
    AIUsageRequestConflictError,
    estimate_risk_units,
    reserve_ai_usage,
    settle_ai_usage,
)
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine


async def _database(path: Path, *, user_ids: list[uuid.UUID]) -> tuple[object, async_sessionmaker]:
    engine = create_async_engine(
        f"sqlite+aiosqlite:///{path.as_posix()}",
        connect_args={"timeout": 5},
    )
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    async with AsyncSession(engine, expire_on_commit=False) as session:
        session.add_all(
            [
                User(
                    id=user_id,
                    username=f"ai-usage-{user_id.hex[:8]}",
                    password_hash="test",
                    role=UserRole.USER,
                )
                for user_id in user_ids
            ]
        )
        await session.commit()
    return engine, async_sessionmaker(engine, expire_on_commit=False)


def _settings(database_url: str, *, user_limit: int = 100, global_limit: int = 1000) -> Settings:
    return Settings(
        _env_file=None,
        app_env="test",
        database_url=database_url,
        ai_risk_daily_user_limit=user_limit,
        ai_risk_daily_global_limit=global_limit,
    )


@pytest.mark.asyncio
async def test_reservation_settlement_release_and_unknown_are_append_only(tmp_path: Path) -> None:
    user_id = uuid.uuid4()
    engine, factory = await _database(tmp_path / "settlement.db", user_ids=[user_id])
    settings = _settings(f"sqlite+aiosqlite:///{(tmp_path / 'settlement.db').as_posix()}")

    async with factory() as session:
        result = await reserve_ai_usage(
            session,
            settings,
            user_id=user_id,
            task_id=None,
            operation_type="AI_PROMPT_ADVISE",
            provider="offline:fake",
            model="fake",
            input_chars=100,
            input_image_count=0,
            max_output_tokens=2000,
            risk_units=3,
            idempotency_key="advice-1",
            request_hash="a" * 64,
        )
        await session.commit()
        await settle_ai_usage(
            session,
            result.reservation.id,
            status=AIUsageReservationStatus.SETTLED,
            actual_risk_units=0,
            actual_cost_status="OFFLINE",
        )
        await session.commit()

    async with factory() as session:
        current = await session.get(AIUsageReservation, result.reservation.id)
        summary = await session.scalar(
            select(AIUsageQuotaSummary).where(AIUsageQuotaSummary.scope_key == str(user_id))
        )
        entries = list(
            await session.scalars(
                select(AIUsageLedger).where(
                    AIUsageLedger.reservation_id == result.reservation.id
                )
            )
        )
        assert current is not None
        assert current.status == AIUsageReservationStatus.SETTLED
        assert current.actual_cost_status == "OFFLINE"
        assert summary is not None
        assert summary.reserved_units == 0
        assert summary.consumed_units == 0
        assert [entry.entry_type for entry in entries] == ["RESERVE", "SETTLED"]

        released = await reserve_ai_usage(
            session,
            settings,
            user_id=user_id,
            task_id=None,
            operation_type="AI_ANALYSIS",
            provider="openai",
            model="gpt-test",
            input_chars=10,
            input_image_count=1,
            max_output_tokens=1000,
            risk_units=2,
            idempotency_key="analysis-1",
            request_hash="b" * 64,
        )
        await session.commit()
        await settle_ai_usage(
            session,
            released.reservation.id,
            status=AIUsageReservationStatus.RELEASED,
            actual_cost_status="NOT_SUBMITTED",
        )
        await session.commit()

        unknown = await reserve_ai_usage(
            session,
            settings,
            user_id=user_id,
            task_id=None,
            operation_type="AI_ANALYSIS",
            provider="openai",
            model="gpt-test",
            input_chars=10,
            input_image_count=1,
            max_output_tokens=1000,
            risk_units=2,
            idempotency_key="analysis-2",
            request_hash="c" * 64,
        )
        await session.commit()
        await settle_ai_usage(
            session,
            unknown.reservation.id,
            status=AIUsageReservationStatus.UNKNOWN,
        )
        await session.commit()
        summary = await session.scalar(
            select(AIUsageQuotaSummary).where(AIUsageQuotaSummary.scope_key == str(user_id))
        )
        assert summary is not None
        assert summary.unknown_units == 2
    await engine.dispose()


@pytest.mark.asyncio
async def test_same_request_is_replayed_without_a_second_reservation(tmp_path: Path) -> None:
    user_id = uuid.uuid4()
    engine, factory = await _database(tmp_path / "replay.db", user_ids=[user_id])
    settings = _settings(f"sqlite+aiosqlite:///{(tmp_path / 'replay.db').as_posix()}")
    async with factory() as session:
        first = await reserve_ai_usage(
            session,
            settings,
            user_id=user_id,
            task_id=None,
            operation_type="AI_PROMPT_REGENERATE",
            provider="offline:replay",
            model="replay",
            input_chars=10,
            input_image_count=0,
            max_output_tokens=1000,
            risk_units=2,
            idempotency_key="same-key",
            request_hash="d" * 64,
        )
        await session.commit()
        second = await reserve_ai_usage(
            session,
            settings,
            user_id=user_id,
            task_id=None,
            operation_type="AI_PROMPT_REGENERATE",
            provider="offline:replay",
            model="replay",
            input_chars=10,
            input_image_count=0,
            max_output_tokens=1000,
            risk_units=2,
            idempotency_key="same-key",
            request_hash="d" * 64,
        )
        assert second.created is False
        assert second.reservation.id == first.reservation.id
        with pytest.raises(AIUsageRequestConflictError):
            await reserve_ai_usage(
                session,
                settings,
                user_id=user_id,
                task_id=None,
                operation_type="AI_PROMPT_REGENERATE",
                provider="offline:replay",
                model="replay",
                input_chars=10,
                input_image_count=0,
                max_output_tokens=1000,
                risk_units=2,
                idempotency_key="same-key",
                request_hash="e" * 64,
            )
        assert len(list(await session.scalars(select(AIUsageReservation)))) == 1
    await engine.dispose()


@pytest.mark.asyncio
async def test_user_and_global_limits_are_atomic_under_concurrency(tmp_path: Path) -> None:
    users = [uuid.uuid4(), uuid.uuid4()]
    database_path = tmp_path / "concurrent.db"
    engine, factory = await _database(database_path, user_ids=users)
    settings = _settings(
        f"sqlite+aiosqlite:///{database_path.as_posix()}",
        user_limit=10,
        global_limit=3,
    )

    async def reserve(index: int) -> str:
        async with factory() as session:
            try:
                await reserve_ai_usage(
                    session,
                    settings,
                    user_id=users[index],
                    task_id=None,
                    operation_type="AI_ANALYSIS",
                    provider="openai",
                    model="gpt-test",
                    input_chars=100,
                    input_image_count=0,
                    max_output_tokens=1000,
                    risk_units=2,
                    idempotency_key=f"concurrent-{index}",
                    request_hash=str(index) * 64,
                )
                await session.commit()
                return "ok"
            except AIUsageLimitExceededError:
                await session.rollback()
                return "limited"

    outcomes = await asyncio.gather(*(reserve(index) for index in range(2)))
    assert outcomes.count("ok") == 1
    assert outcomes.count("limited") == 1
    async with factory() as session:
        summary = await session.scalar(
            select(AIUsageQuotaSummary).where(AIUsageQuotaSummary.scope_key == "__global__")
        )
        assert summary is not None
        assert summary.reserved_units == 2
    await engine.dispose()


@pytest.mark.asyncio
async def test_persisted_reservation_survives_engine_restart(tmp_path: Path) -> None:
    user_id = uuid.uuid4()
    database_path = tmp_path / "restart.db"
    engine, factory = await _database(database_path, user_ids=[user_id])
    settings = _settings(f"sqlite+aiosqlite:///{database_path.as_posix()}")
    async with factory() as session:
        result = await reserve_ai_usage(
            session,
            settings,
            user_id=user_id,
            task_id=None,
            operation_type="AI_ANALYSIS",
            provider="openai",
            model="gpt-test",
            input_chars=100,
            input_image_count=1,
            max_output_tokens=1000,
            risk_units=3,
            idempotency_key="restart-1",
            request_hash="f" * 64,
        )
        await session.commit()
        reservation_id = result.reservation.id
    await engine.dispose()

    reopened = create_async_engine(f"sqlite+aiosqlite:///{database_path.as_posix()}")
    async with AsyncSession(reopened, expire_on_commit=False) as session:
        persisted = await session.get(AIUsageReservation, reservation_id)
        assert persisted is not None
        assert persisted.status == AIUsageReservationStatus.RESERVED
        assert persisted.risk_units == 3
    await reopened.dispose()


def test_risk_unit_defaults_include_input_images_and_output() -> None:
    settings = Settings(_env_file=None, app_env="test")
    assert estimate_risk_units(
        settings,
        input_chars=1001,
        input_image_count=2,
        max_output_tokens=1001,
        fallback_reserve_units=2,
    ) == 1 + 2 + 8 + 2 + 2
