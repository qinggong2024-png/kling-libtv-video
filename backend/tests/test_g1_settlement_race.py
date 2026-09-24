import uuid

from libtv_agent.domain.enums import ChargeStatus, LedgerEntryType
from libtv_agent.domain.models import (
    GenerationAttempt,
    GenerationVariant,
    ParentTask,
    PointsLedger,
    PointsReservation,
    UserDailyPointsSummary,
)
from libtv_agent.services.points import reserve_points, settle_points
from sqlalchemy import select
from test_image_quota_concurrency import world  # noqa: F401


async def test_stale_session_cannot_settle_same_reservation_twice(world):  # noqa: F811
    _, factory, _, users = world
    async with factory() as session:
        task = ParentTask(
            user_id=users[0], client_task_id=str(uuid.uuid4()), title="synthetic", asset_count=1
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
        reservation = await reserve_points(
            session,
            user_id=users[0],
            attempt_id=attempt.id,
            estimated_points=240,
            daily_limit=5000,
        )
        await session.commit()
        reservation_id, user_id, attempt_id = (
            reservation.id,
            reservation.user_id,
            reservation.attempt_id,
        )
    async with factory() as first, factory() as second:
        a = await first.get(PointsReservation, reservation_id)
        b = await second.get(PointsReservation, reservation_id)
        await first.commit()
        await second.commit()
        await settle_points(first, a, actual_points=120, charge_status=ChargeStatus.CHARGED)
        await first.commit()
        await settle_points(second, b, actual_points=120, charge_status=ChargeStatus.CHARGED)
        await second.commit()
    async with factory() as verify:
        summary = await verify.scalar(
            select(UserDailyPointsSummary).where(UserDailyPointsSummary.user_id == user_id)
        )
        assert summary.reserved_points == 0
        assert summary.consumed_points == 120
        entries = list(
            await verify.scalars(select(PointsLedger).where(PointsLedger.attempt_id == attempt_id))
        )
        assert sum(e.entry_type == LedgerEntryType.CONSUME for e in entries) == 1
