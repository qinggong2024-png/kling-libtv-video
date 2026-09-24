import asyncio
import uuid

from libtv_agent.domain.enums import LedgerEntryType
from libtv_agent.domain.models import (
    GenerationAttempt,
    GenerationVariant,
    ParentTask,
    PointsLedger,
    PointsReservation,
    UserDailyPointsSummary,
)
from libtv_agent.services.points import PointsLimitExceededError, reserve_points
from sqlalchemy import func, select
from test_image_quota_concurrency import world  # noqa: F401


async def test_video_last_quota_and_user_isolation(world):  # noqa: F811
    _, factory, _, users = world
    attempts = []
    async with factory() as session:
        for user in [users[0], users[0], users[1]]:
            task = ParentTask(
                user_id=user, client_task_id=str(uuid.uuid4()), title="synthetic", asset_count=1
            )
            session.add(task)
            await session.flush()
            variant = GenerationVariant(
                parent_task_id=task.id, variant_type="STABLE", generation_config_json={}
            )
            session.add(variant)
            await session.flush()
            attempt = GenerationAttempt(variant_id=variant.id, provider="kling_official_cli")
            session.add(attempt)
            await session.flush()
            attempts.append(attempt.id)
        await session.commit()

    gate = asyncio.Event()

    async def reserve(user, attempt):
        async with factory() as session:
            await gate.wait()
            try:
                reservation = await reserve_points(
                    session, user_id=user, attempt_id=attempt, estimated_points=120, daily_limit=120
                )
                await session.commit()
                return reservation.id
            except PointsLimitExceededError:
                await session.rollback()
                return None

    pending = [
        asyncio.create_task(reserve(user, attempt))
        for user, attempt in zip([users[0], users[0], users[1]], attempts, strict=True)
    ]
    gate.set()
    results = await asyncio.gather(*pending)
    assert sum(value is not None for value in results[:2]) == 1
    assert results[2] is not None
    winner = 0 if results[0] is not None else 1
    assert await reserve(users[0], attempts[winner]) == results[winner]
    async with factory() as verify:
        assert await verify.scalar(select(func.count()).select_from(PointsReservation)) == 2
        ledger = list(await verify.scalars(select(PointsLedger)))
        assert len(ledger) == 2
        assert all(entry.entry_type == LedgerEntryType.RESERVE for entry in ledger)
        summaries = list(await verify.scalars(select(UserDailyPointsSummary)))
        assert len(summaries) == 2
        assert all(s.reserved_points == 120 and s.consumed_points == 0 for s in summaries)
