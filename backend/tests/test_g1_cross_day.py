import uuid
from datetime import UTC, datetime

from libtv_agent.domain.enums import ChargeStatus, LedgerEntryType
from libtv_agent.domain.models import PointsLedger, UserDailyPointsSummary
from libtv_agent.services.points import reserve_points, settle_points
from sqlalchemy import select
from test_state_and_points import session  # noqa: F401


async def test_old_unknown_recovery_stays_on_original_day(session):  # noqa: F811
    user, attempt = uuid.uuid4(), uuid.uuid4()
    old = await reserve_points(
        session,
        user_id=user,
        attempt_id=attempt,
        estimated_points=120,
        daily_limit=200,
        now=datetime(2026, 9, 23, 15, 59, 59, tzinfo=UTC),
    )
    await session.commit()
    replay = await reserve_points(
        session,
        user_id=user,
        attempt_id=attempt,
        estimated_points=120,
        daily_limit=200,
        now=datetime(2026, 9, 23, 16, 0, 1, tzinfo=UTC),
    )
    assert replay.id == old.id
    await reserve_points(
        session,
        user_id=user,
        attempt_id=uuid.uuid4(),
        estimated_points=120,
        daily_limit=200,
        now=datetime(2026, 9, 23, 16, 0, 1, tzinfo=UTC),
    )
    for _ in range(3):
        await settle_points(session, old, actual_points=None, charge_status=ChargeStatus.UNKNOWN)
        await session.commit()
    entries = list(
        await session.scalars(select(PointsLedger).where(PointsLedger.attempt_id == attempt))
    )
    assert [entry.entry_type for entry in entries].count(LedgerEntryType.UNCERTAIN) == 1
    await settle_points(session, old, actual_points=100, charge_status=ChargeStatus.CHARGED)
    await session.commit()
    await settle_points(session, old, actual_points=100, charge_status=ChargeStatus.CHARGED)
    await session.commit()
    summaries = list(
        await session.scalars(
            select(UserDailyPointsSummary).order_by(UserDailyPointsSummary.business_date)
        )
    )
    assert [
        (s.business_date.isoformat(), s.reserved_points, s.uncertain_points, s.consumed_points)
        for s in summaries
    ] == [
        ("2026-09-23", 0, 0, 100),
        ("2026-09-24", 120, 0, 0),
    ]
    entries = list(
        await session.scalars(select(PointsLedger).where(PointsLedger.attempt_id == attempt))
    )
    assert len(entries) == 3
    assert all(entry.business_date.isoformat() == "2026-09-23" for entry in entries)
