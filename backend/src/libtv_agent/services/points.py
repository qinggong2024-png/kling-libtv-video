import uuid
from datetime import datetime
from zoneinfo import ZoneInfo

from libtv_agent.domain.enums import ChargeStatus, LedgerEntryType, ReservationStatus
from libtv_agent.domain.models import PointsLedger, PointsReservation, UserDailyPointsSummary
from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert as postgresql_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.ext.asyncio import AsyncSession

SHANGHAI = ZoneInfo("Asia/Shanghai")


class PointsLimitExceededError(RuntimeError):
    pass


def business_date(now: datetime | None = None):
    instant = now or datetime.now(tz=SHANGHAI)
    if instant.tzinfo is None:
        instant = instant.replace(tzinfo=SHANGHAI)
    return instant.astimezone(SHANGHAI).date()


async def reserve_points(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    attempt_id: uuid.UUID,
    estimated_points: int,
    daily_limit: int,
    now: datetime | None = None,
) -> PointsReservation:
    existing = await session.scalar(
        select(PointsReservation).where(PointsReservation.attempt_id == attempt_id)
    )
    if existing is not None:
        return existing
    day = business_date(now)
    dialect = session.get_bind().dialect.name
    insert_factory = sqlite_insert if dialect == "sqlite" else postgresql_insert
    await session.execute(
        insert_factory(UserDailyPointsSummary)
        .values(id=uuid.uuid4(), user_id=user_id, business_date=day)
        .on_conflict_do_nothing(index_elements=["user_id", "business_date"])
    )
    summary = await session.scalar(
        select(UserDailyPointsSummary)
        .where(
            UserDailyPointsSummary.user_id == user_id, UserDailyPointsSummary.business_date == day
        )
        .with_for_update()
    )
    if summary is None:
        raise RuntimeError("daily points summary upsert did not produce a row")
    remaining = (
        daily_limit - summary.consumed_points - summary.reserved_points - summary.uncertain_points
    )
    if estimated_points > remaining:
        raise PointsLimitExceededError("daily points limit exceeded")
    reservation = PointsReservation(
        user_id=user_id,
        business_date=day,
        attempt_id=attempt_id,
        estimated_points=estimated_points,
        charge_status=ChargeStatus.NOT_CHARGED,
        status=ReservationStatus.RESERVED,
    )
    summary.reserved_points += estimated_points
    summary.state_version += 1
    session.add_all(
        [
            reservation,
            PointsLedger(
                user_id=user_id,
                business_date=day,
                attempt_id=attempt_id,
                entry_type=LedgerEntryType.RESERVE,
                points=estimated_points,
                reason="generation confirmation",
            ),
        ]
    )
    await session.flush()
    return reservation


async def settle_points(
    session: AsyncSession,
    reservation: PointsReservation,
    *,
    actual_points: int | None,
    charge_status: ChargeStatus,
) -> None:
    # A write lock also serializes SQLite, where SELECT FOR UPDATE is ignored.
    await session.execute(
        update(PointsReservation)
        .where(PointsReservation.id == reservation.id)
        .values(status=PointsReservation.status)
        .execution_options(synchronize_session=False)
    )
    await session.refresh(reservation)
    summary = await session.scalar(
        select(UserDailyPointsSummary)
        .where(
            UserDailyPointsSummary.user_id == reservation.user_id,
            UserDailyPointsSummary.business_date == reservation.business_date,
        )
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if summary is None or reservation.status not in {
        ReservationStatus.RESERVED,
        ReservationStatus.UNCERTAIN,
    }:
        return
    if reservation.status == ReservationStatus.UNCERTAIN and not (
        charge_status == ChargeStatus.NOT_CHARGED
        or (charge_status == ChargeStatus.CHARGED and actual_points is not None)
    ):
        # Repeated recovery with no new charge evidence is not a new ledger event.
        return
    if reservation.status == ReservationStatus.RESERVED:
        summary.reserved_points -= reservation.estimated_points
    else:
        summary.uncertain_points -= reservation.estimated_points
    if charge_status == ChargeStatus.CHARGED and actual_points is not None:
        summary.consumed_points += actual_points
        reservation.actual_points = actual_points
        reservation.status = ReservationStatus.SETTLED
        entry_type = LedgerEntryType.CONSUME
        points = actual_points
    elif charge_status == ChargeStatus.NOT_CHARGED:
        reservation.status = ReservationStatus.RELEASED
        entry_type = LedgerEntryType.RELEASE
        points = -reservation.estimated_points
    else:
        summary.uncertain_points += reservation.estimated_points
        reservation.status = ReservationStatus.UNCERTAIN
        entry_type = LedgerEntryType.UNCERTAIN
        points = reservation.estimated_points
    reservation.charge_status = charge_status
    reservation.settled_at = datetime.now(tz=SHANGHAI)
    summary.state_version += 1
    session.add(
        PointsLedger(
            user_id=reservation.user_id,
            business_date=reservation.business_date,
            attempt_id=reservation.attempt_id,
            entry_type=entry_type,
            points=points,
            reason="generation settlement",
        )
    )
