"""Persistent risk-unit reservations for AI analysis and prompt assistance.

This ledger is intentionally separate from video PointsReservation. A reservation
must be committed before a provider call starts; provider execution never runs
inside the transaction that updates the quota summaries.
"""

from __future__ import annotations

import math
import uuid
from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import Literal

from libtv_agent.config import Settings
from libtv_agent.domain.enums import AIUsageReservationStatus
from libtv_agent.domain.models import AIUsageLedger, AIUsageQuotaSummary, AIUsageReservation
from sqlalchemy import and_, select, update
from sqlalchemy.dialects.postgresql import insert as postgresql_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.ext.asyncio import AsyncSession

GLOBAL_SCOPE_KEY = "__global__"


class AIUsageLimitExceededError(RuntimeError):
    def __init__(self, scope: Literal["user", "global"]) -> None:
        self.scope = scope
        super().__init__(f"AI {scope} risk-unit limit exceeded")


class AIUsageRequestConflictError(RuntimeError):
    pass


@dataclass(frozen=True)
class AIUsageReservationResult:
    reservation: AIUsageReservation
    created: bool


def _business_date(now: datetime | None = None) -> date:
    # The product quota resets in Asia/Shanghai. Avoid depending on the host
    # timezone when tests or a worker run elsewhere.
    from zoneinfo import ZoneInfo

    return (now or datetime.now(ZoneInfo("Asia/Shanghai"))).date()


def estimate_risk_units(
    settings: Settings,
    *,
    input_chars: int,
    input_image_count: int,
    max_output_tokens: int,
    fallback_reserve_units: int = 0,
) -> int:
    if input_chars < 0 or input_image_count < 0 or max_output_tokens < 0:
        raise ValueError("AI usage input sizes cannot be negative")
    return (
        settings.ai_risk_base_units
        + math.ceil(input_chars / settings.ai_risk_input_chars_per_unit)
        + input_image_count * settings.ai_risk_image_unit
        + math.ceil(max_output_tokens / settings.ai_risk_output_tokens_per_unit)
        + fallback_reserve_units
    )


def _summary_values(
    *,
    scope_key: str,
    scope_type: str,
    user_id: uuid.UUID | None,
    business_date: date,
    limit_units: int,
) -> dict[str, object]:
    return {
        "scope_key": scope_key,
        "scope_type": scope_type,
        "user_id": user_id,
        "business_date": business_date,
        "limit_units": limit_units,
        "reserved_units": 0,
        "consumed_units": 0,
        "unknown_units": 0,
    }


async def _ensure_summary(
    session: AsyncSession,
    *,
    scope_key: str,
    scope_type: str,
    user_id: uuid.UUID | None,
    business_date: date,
    limit_units: int,
) -> None:
    dialect = session.get_bind().dialect.name
    insert_factory = sqlite_insert if dialect == "sqlite" else postgresql_insert
    statement = insert_factory(AIUsageQuotaSummary).values(
        **_summary_values(
            scope_key=scope_key,
            scope_type=scope_type,
            user_id=user_id,
            business_date=business_date,
            limit_units=limit_units,
        )
    )
    await session.execute(
        statement.on_conflict_do_nothing(index_elements=["scope_key", "business_date"])
    )


async def _reserve_summary(
    session: AsyncSession,
    *,
    scope_key: str,
    business_date: date,
    limit_units: int,
    risk_units: int,
) -> bool:
    updated = await session.execute(
        update(AIUsageQuotaSummary)
        .where(
            AIUsageQuotaSummary.scope_key == scope_key,
            AIUsageQuotaSummary.business_date == business_date,
            (
                AIUsageQuotaSummary.reserved_units
                + AIUsageQuotaSummary.consumed_units
                + AIUsageQuotaSummary.unknown_units
                + risk_units
                <= limit_units
            ),
        )
        .values(
            limit_units=limit_units,
            reserved_units=AIUsageQuotaSummary.reserved_units + risk_units,
        )
    )
    return updated.rowcount == 1


async def reserve_ai_usage(
    session: AsyncSession,
    settings: Settings,
    *,
    user_id: uuid.UUID,
    task_id: uuid.UUID | None,
    operation_type: str,
    provider: str,
    model: str,
    input_chars: int,
    input_image_count: int,
    max_output_tokens: int,
    risk_units: int,
    idempotency_key: str,
    request_hash: str,
) -> AIUsageReservationResult:
    if risk_units < 1:
        raise ValueError("AI usage risk_units must be positive")
    existing = await session.scalar(
        select(AIUsageReservation).where(
            AIUsageReservation.user_id == user_id,
            AIUsageReservation.operation_type == operation_type,
            AIUsageReservation.idempotency_key == idempotency_key,
        )
    )
    if existing is not None:
        if existing.request_hash != request_hash:
            raise AIUsageRequestConflictError(
                "AI usage idempotency key was reused with a different request"
            )
        return AIUsageReservationResult(existing, False)

    business_date = _business_date()
    await _ensure_summary(
        session,
        scope_key=str(user_id),
        scope_type="USER",
        user_id=user_id,
        business_date=business_date,
        limit_units=settings.ai_risk_daily_user_limit,
    )
    await _ensure_summary(
        session,
        scope_key=GLOBAL_SCOPE_KEY,
        scope_type="GLOBAL",
        user_id=None,
        business_date=business_date,
        limit_units=settings.ai_risk_daily_global_limit,
    )
    if not await _reserve_summary(
        session,
        scope_key=str(user_id),
        business_date=business_date,
        limit_units=settings.ai_risk_daily_user_limit,
        risk_units=risk_units,
    ):
        raise AIUsageLimitExceededError("user")
    if not await _reserve_summary(
        session,
        scope_key=GLOBAL_SCOPE_KEY,
        business_date=business_date,
        limit_units=settings.ai_risk_daily_global_limit,
        risk_units=risk_units,
    ):
        raise AIUsageLimitExceededError("global")

    reservation = AIUsageReservation(
        user_id=user_id,
        task_id=task_id,
        operation_type=operation_type,
        provider=provider,
        model=model,
        input_chars=input_chars,
        input_image_count=input_image_count,
        max_output_tokens=max_output_tokens,
        risk_units=risk_units,
        actual_cost_status="PENDING",
        idempotency_key=idempotency_key,
        request_hash=request_hash,
        status=AIUsageReservationStatus.RESERVED,
    )
    session.add(reservation)
    await session.flush()
    session.add(
        AIUsageLedger(
            reservation_id=reservation.id,
            user_id=user_id,
            task_id=task_id,
            operation_type=operation_type,
            entry_type="RESERVE",
            risk_units=risk_units,
            actual_cost_status="PENDING",
        )
    )
    await session.flush()
    return AIUsageReservationResult(reservation, True)


async def settle_ai_usage(
    session: AsyncSession,
    reservation_id: uuid.UUID,
    *,
    status: AIUsageReservationStatus,
    actual_input_tokens: int | None = None,
    actual_output_tokens: int | None = None,
    actual_risk_units: int | None = None,
    actual_cost_status: str | None = None,
    provider_response_id: str | None = None,
) -> AIUsageReservation | None:
    if status not in {
        AIUsageReservationStatus.SETTLED,
        AIUsageReservationStatus.RELEASED,
        AIUsageReservationStatus.UNKNOWN,
    }:
        raise ValueError("AI usage settlement requires a terminal status")
    reservation = await session.scalar(
        select(AIUsageReservation).where(AIUsageReservation.id == reservation_id)
    )
    if reservation is None:
        return None
    if reservation.status in {
        AIUsageReservationStatus.SETTLED,
        AIUsageReservationStatus.RELEASED,
    }:
        return reservation
    if reservation.status == AIUsageReservationStatus.UNKNOWN and status == (
        AIUsageReservationStatus.UNKNOWN
    ):
        return reservation

    business_date = _business_date(reservation.created_at)
    previous = reservation.status
    if previous == AIUsageReservationStatus.RESERVED:
        from_reserved = reservation.risk_units
    else:
        from_reserved = 0
    if previous == AIUsageReservationStatus.UNKNOWN:
        from_unknown = reservation.risk_units
    else:
        from_unknown = 0

    summary = await session.scalar(
        select(AIUsageQuotaSummary).where(
            AIUsageQuotaSummary.scope_key == str(reservation.user_id),
            AIUsageQuotaSummary.business_date == business_date,
        )
    )
    global_summary = await session.scalar(
        select(AIUsageQuotaSummary).where(
            AIUsageQuotaSummary.scope_key == GLOBAL_SCOPE_KEY,
            AIUsageQuotaSummary.business_date == business_date,
        )
    )
    if summary is None or global_summary is None:
        raise RuntimeError("AI usage quota summary is missing")

    for current in (summary, global_summary):
        current.reserved_units -= from_reserved
        current.unknown_units -= from_unknown
        if status == AIUsageReservationStatus.SETTLED:
            current.consumed_units += (
                reservation.risk_units if actual_risk_units is None else actual_risk_units
            )
        elif status == AIUsageReservationStatus.UNKNOWN:
            current.unknown_units += reservation.risk_units

    reservation.status = status
    reservation.actual_input_tokens = actual_input_tokens
    reservation.actual_output_tokens = actual_output_tokens
    reservation.actual_risk_units = (
        reservation.risk_units if actual_risk_units is None else actual_risk_units
    )
    reservation.actual_cost_status = actual_cost_status or (
        "UNKNOWN_COST" if status == AIUsageReservationStatus.UNKNOWN else "NOT_SUBMITTED"
    )
    reservation.provider_response_id = provider_response_id
    reservation.settled_at = datetime.now(UTC)
    session.add(
        AIUsageLedger(
            reservation_id=reservation.id,
            user_id=reservation.user_id,
            task_id=reservation.task_id,
            operation_type=reservation.operation_type,
            entry_type=status.value,
            risk_units=reservation.risk_units,
            actual_input_tokens=actual_input_tokens,
            actual_output_tokens=actual_output_tokens,
            actual_cost_status=reservation.actual_cost_status,
        )
    )
    await session.flush()
    return reservation


async def get_ai_usage_reservation(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    operation_type: str,
    idempotency_key: str,
) -> AIUsageReservation | None:
    return await session.scalar(
        select(AIUsageReservation).where(
            and_(
                AIUsageReservation.user_id == user_id,
                AIUsageReservation.operation_type == operation_type,
                AIUsageReservation.idempotency_key == idempotency_key,
            )
        )
    )
