"""Persistent risk-unit reservations for AI analysis and prompt assistance.

This ledger is intentionally separate from video PointsReservation. A reservation
must be committed before a provider call starts; provider execution never runs
inside the transaction that updates the quota summaries.
"""

from __future__ import annotations

import hashlib
import math
import uuid
from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import Literal

from libtv_agent.config import Settings
from libtv_agent.domain.enums import AIUsageReservationStatus
from libtv_agent.domain.models import AIUsageLedger, AIUsageQuotaSummary, AIUsageReservation
from libtv_agent.services.ai_pricing import (
    ACCOUNTING_VERSION,
    MICROUSD_PER_UNIT,
    AIPricingError,
    PriceQuote,
    actual_cost_from_snapshot,
    microusd_to_units,
    units_to_usd,
)
from sqlalchemy import and_, select, update
from sqlalchemy.dialects.postgresql import insert as postgresql_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.ext.asyncio import AsyncSession

GLOBAL_SCOPE_KEY = "__global_usd_v1__"


def user_scope_key(user_id: uuid.UUID) -> str:
    return f"usd:v1:{user_id}"


def _request_key(task_id: uuid.UUID | None, key: str) -> str:
    return hashlib.sha256(f"{task_id}:{key}".encode()).hexdigest() if task_id else key


class AIUsageLimitExceededError(RuntimeError):
    def __init__(self, scope: Literal["user", "global"]) -> None:
        self.scope = scope
        super().__init__(f"AI {scope} daily USD allowance exceeded")


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

    current = now or datetime.now(UTC)
    if current.tzinfo is None:
        current = current.replace(tzinfo=UTC)
    return current.astimezone(ZoneInfo("Asia/Shanghai")).date()


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
    price_quote: PriceQuote | None = None,
) -> AIUsageReservationResult:
    if type(risk_units) is not int or risk_units < 1:
        raise ValueError("AI usage risk_units must be positive")
    if risk_units > settings.ai_request_max_units:
        raise AIPricingError("AI request exceeds the configured USD request cap")
    if price_quote is not None and (
        price_quote.risk_units != risk_units
        or price_quote.provider != provider or price_quote.model != model
    ):
        raise AIPricingError("price quote does not match the reservation")
    # The savepoint makes quota denial atomic even if a caller catches it and
    # later commits another change in the same session.
    async with session.begin_nested():
        return await _reserve_locked(
            session, settings, user_id=user_id, task_id=task_id,
            operation_type=operation_type, provider=provider, model=model,
            input_chars=input_chars, input_image_count=input_image_count,
            max_output_tokens=max_output_tokens, risk_units=risk_units,
            idempotency_key=_request_key(task_id, idempotency_key),
            request_hash=request_hash, price_quote=price_quote,
        )


async def legacy_usage_blocked(session: AsyncSession, business_date: date) -> bool:
    return await session.scalar(
        select(AIUsageQuotaSummary.id).where(
            AIUsageQuotaSummary.scope_key == "__global__",
            (
                (AIUsageQuotaSummary.reserved_units > 0)
                | (AIUsageQuotaSummary.unknown_units > 0)
                | (
                    (AIUsageQuotaSummary.business_date == business_date)
                    & (AIUsageQuotaSummary.consumed_units > 0)
                )
            ),
        ).limit(1)
    ) is not None


async def _reserve_locked(
    session: AsyncSession, settings: Settings, *, user_id: uuid.UUID,
    task_id: uuid.UUID | None, operation_type: str, provider: str, model: str,
    input_chars: int, input_image_count: int, max_output_tokens: int,
    risk_units: int, idempotency_key: str, request_hash: str,
    price_quote: PriceQuote | None,
) -> AIUsageReservationResult:
    business_date = _business_date()
    scope = user_scope_key(user_id)
    await _ensure_summary(
        session, scope_key=scope, scope_type="USER", user_id=user_id,
        business_date=business_date, limit_units=settings.ai_risk_daily_user_limit,
    )
    # Serialize same-user requests before checking the reservation identity.
    await session.execute(
        update(AIUsageQuotaSummary).where(
            AIUsageQuotaSummary.scope_key == scope,
            AIUsageQuotaSummary.business_date == business_date,
        ).values(reserved_units=AIUsageQuotaSummary.reserved_units + 0)
    )
    existing = await session.scalar(
        select(AIUsageReservation).where(
            AIUsageReservation.user_id == user_id,
            AIUsageReservation.operation_type == operation_type,
            AIUsageReservation.idempotency_key == idempotency_key,
            AIUsageReservation.accounting_version == ACCOUNTING_VERSION,
        )
    )
    if existing is not None:
        if existing.request_hash != request_hash:
            raise AIUsageRequestConflictError(
                "AI usage idempotency key was reused with a different request"
            )
        return AIUsageReservationResult(existing, False)

    if await legacy_usage_blocked(session, business_date):
        raise AIPricingError("legacy risk usage requires reconciliation before USD submissions")
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
        scope_key=scope,
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
        accounting_version=ACCOUNTING_VERSION,
        business_date=business_date,
        estimated_cost_microusd=(
            price_quote.estimated_cost_microusd if price_quote else risk_units * MICROUSD_PER_UNIT
        ),
        pricing_snapshot_json=(
            price_quote.snapshot if price_quote else {
                "accounting_version": ACCOUNTING_VERSION,
                "price_status": "CONSERVATIVE_CAP",
                "source": "internal explicit risk cap",
            }
        ),
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
            accounting_version=ACCOUNTING_VERSION,
            cost_microusd=reservation.estimated_cost_microusd,
            actual_cost_status="PENDING",
        )
    )
    await session.flush()
    return AIUsageReservationResult(reservation, True)


async def reserve_priced_ai_usage(
    session: AsyncSession, settings: Settings, *, quote: PriceQuote, **request: object,
) -> AIUsageReservationResult:
    return await reserve_ai_usage(
        session, settings, provider=quote.provider, model=quote.model,
        risk_units=quote.risk_units, price_quote=quote, **request,
    )


async def reserve_ai_usage_batch(
    session: AsyncSession, settings: Settings, *, requests: list[dict],
) -> list[AIUsageReservationResult]:
    if not requests or sum(item["quote"].risk_units for item in requests) > (
        settings.ai_batch_max_units
    ):
        raise AIPricingError("AI batch exceeds the configured USD batch cap")
    async with session.begin_nested():
        return [
            await reserve_priced_ai_usage(session, settings, **request)
            for request in requests
        ]


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
    actual_cost_microusd: int | None = None,
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
    if reservation.accounting_version != ACCOUNTING_VERSION:
        raise AIPricingError("legacy risk units cannot be settled as USD")
    if actual_cost_microusd is not None:
        calculated_units = microusd_to_units(actual_cost_microusd)
        if actual_risk_units is not None and actual_risk_units != calculated_units:
            raise AIPricingError("actual cost and units disagree")
        actual_risk_units = calculated_units
    if actual_risk_units is not None and (
        type(actual_risk_units) is not int or actual_risk_units < 0
    ):
        raise AIPricingError("actual usage must be a nonnegative integer")
    if reservation.status in {
        AIUsageReservationStatus.SETTLED,
        AIUsageReservationStatus.RELEASED,
    }:
        return reservation
    if reservation.status == AIUsageReservationStatus.UNKNOWN and status == (
        AIUsageReservationStatus.UNKNOWN
    ):
        return reservation

    if status == AIUsageReservationStatus.SETTLED and actual_risk_units is None:
        status = AIUsageReservationStatus.UNKNOWN
        actual_cost_status = "UNKNOWN_COST"
    if reservation.status == status == AIUsageReservationStatus.UNKNOWN:
        return reservation
    business_date = reservation.business_date or _business_date(reservation.created_at)
    previous = reservation.status
    if previous == AIUsageReservationStatus.RESERVED:
        from_reserved = reservation.risk_units
    else:
        from_reserved = 0
    if previous == AIUsageReservationStatus.UNKNOWN:
        from_unknown = reservation.risk_units
    else:
        from_unknown = 0

    cost_status = actual_cost_status or (
        "UNKNOWN_COST" if status == AIUsageReservationStatus.UNKNOWN else "NOT_SUBMITTED"
    )
    charged_units = actual_risk_units if status == AIUsageReservationStatus.SETTLED else (
        0 if status == AIUsageReservationStatus.RELEASED else None
    )
    cost = actual_cost_microusd if charged_units is not None else None
    if cost is None and charged_units is not None:
        cost = charged_units * MICROUSD_PER_UNIT
    claimed = await session.execute(
        update(AIUsageReservation).where(
            AIUsageReservation.id == reservation_id,
            AIUsageReservation.status == previous,
        ).values(
            status=status, actual_input_tokens=actual_input_tokens,
            actual_output_tokens=actual_output_tokens, actual_risk_units=charged_units,
            actual_cost_microusd=cost, actual_cost_status=cost_status,
            provider_response_id=provider_response_id, settled_at=datetime.now(UTC),
        ).execution_options(synchronize_session=False)
    )
    if claimed.rowcount != 1:
        await session.refresh(reservation)
        return reservation
    for scope in (user_scope_key(reservation.user_id), GLOBAL_SCOPE_KEY):
        changed = await session.execute(
            update(AIUsageQuotaSummary).where(
                AIUsageQuotaSummary.scope_key == scope,
                AIUsageQuotaSummary.business_date == business_date,
            ).values(
                reserved_units=AIUsageQuotaSummary.reserved_units - from_reserved,
                unknown_units=AIUsageQuotaSummary.unknown_units - from_unknown + (
                    reservation.risk_units if status == AIUsageReservationStatus.UNKNOWN else 0
                ),
                consumed_units=AIUsageQuotaSummary.consumed_units + (
                    charged_units if status == AIUsageReservationStatus.SETTLED else 0
                ),
            ).execution_options(synchronize_session="fetch")
        )
        if changed.rowcount != 1:
            raise RuntimeError("AI usage quota summary is missing")
    session.add(
        AIUsageLedger(
            reservation_id=reservation.id,
            user_id=reservation.user_id,
            task_id=reservation.task_id,
            operation_type=reservation.operation_type,
            entry_type=status.value,
            risk_units=charged_units if charged_units is not None else reservation.risk_units,
            accounting_version=ACCOUNTING_VERSION,
            cost_microusd=cost,
            actual_input_tokens=actual_input_tokens,
            actual_output_tokens=actual_output_tokens,
            actual_cost_status=cost_status,
        )
    )
    await session.flush()
    await session.refresh(reservation)
    return reservation


async def settle_provider_usage(
    session: AsyncSession, reservation_id: uuid.UUID, *,
    input_tokens: int | None = None, output_tokens: int | None = None,
    provider_response_id: str | None = None, offline: bool = False,
) -> AIUsageReservation | None:
    reservation = await session.get(AIUsageReservation, reservation_id)
    if reservation is None:
        return None
    cost = 0 if offline else actual_cost_from_snapshot(
        reservation.pricing_snapshot_json or {},
        input_tokens=input_tokens, output_tokens=output_tokens,
    )
    return await settle_ai_usage(
        session, reservation_id,
        status=(
            AIUsageReservationStatus.SETTLED if cost is not None
            else AIUsageReservationStatus.UNKNOWN
        ),
        actual_input_tokens=input_tokens, actual_output_tokens=output_tokens,
        actual_cost_microusd=cost, provider_response_id=provider_response_id,
        actual_cost_status=(
            "OFFLINE" if offline else "LOCAL_PRICE_USAGE" if cost is not None else "UNKNOWN_COST"
        ),
    )


async def read_ai_quota(
    session: AsyncSession, settings: Settings, *, user_id: uuid.UUID,
) -> dict:
    today = _business_date()
    summary = await session.scalar(select(AIUsageQuotaSummary).where(
        AIUsageQuotaSummary.scope_key == user_scope_key(user_id),
        AIUsageQuotaSummary.business_date == today,
    ))
    total = settings.ai_risk_daily_user_limit
    reserved = summary.reserved_units if summary else 0
    settled = summary.consumed_units if summary else 0
    unknown = summary.unknown_units if summary else 0
    available = max(0, total - reserved - settled - unknown)
    return {
        "currency": "USD", "business_date": today.isoformat(),
        "accounting_version": ACCOUNTING_VERSION,
        "total": units_to_usd(total), "available": units_to_usd(available),
        "reserved": units_to_usd(reserved), "settled": units_to_usd(settled),
        "unknown": units_to_usd(unknown),
        "request_max": units_to_usd(settings.ai_request_max_units),
        "batch_max": units_to_usd(settings.ai_batch_max_units),
        "legacy_reconciliation_required": await legacy_usage_blocked(session, today),
        "diagnostics": {
            "unit_microusd": MICROUSD_PER_UNIT, "total_units": total,
            "available_units": available, "reserved_units": reserved,
            "settled_units": settled, "unknown_units": unknown,
        },
        "enforced_entries": ["task_analysis", "prompt_assistant"],
        "deferred_entries": ["image_submission", "video_submission", "feedback_learning",
                             "director_planning", "quality_review"],
    }


async def get_ai_usage_reservation(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    operation_type: str,
    idempotency_key: str,
    task_id: uuid.UUID | None = None,
) -> AIUsageReservation | None:
    return await session.scalar(
        select(AIUsageReservation).where(
            and_(
                AIUsageReservation.user_id == user_id,
                AIUsageReservation.operation_type == operation_type,
                AIUsageReservation.idempotency_key == _request_key(task_id, idempotency_key),
                AIUsageReservation.accounting_version == ACCOUNTING_VERSION,
            )
        )
    )
