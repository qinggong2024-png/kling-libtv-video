import asyncio
import json
import uuid
from contextvars import ContextVar
from datetime import UTC, date, datetime

import pytest
from libtv_agent.domain.enums import AIUsageReservationStatus as Status
from libtv_agent.domain.models import AIUsageLedger, AIUsageQuotaSummary, AIUsageReservation
from libtv_agent.services import ai_usage as usage
from libtv_agent.services.ai_pricing import AIPricingError, estimate_price
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from test_ai_pricing import _entry, _priced_settings, _request
from test_ai_usage import _database


@pytest.fixture
async def world(tmp_path):
    users = [uuid.uuid4(), uuid.uuid4()]
    path = tmp_path / "pending.db"
    engine, factory = await _database(path, user_ids=users)
    settings = _priced_settings(
        database_url=f"sqlite+aiosqlite:///{path.as_posix()}",
        openai_model="small", openai_analysis_fallback_model=None,
    )
    try:
        yield path, factory, users, settings
    finally:
        await engine.dispose()


def _quote(settings):
    return estimate_price(settings, provider="offline:fake", model="fake")


@pytest.mark.asyncio
async def test_pending_cap_rejects_third_request_and_preserves_replay(world):
    _, factory, users, settings = world
    quote = _quote(settings)
    async with factory() as session:
        first = await usage.reserve_priced_ai_usage(
            session, settings, **_request(users[0], quote, "first"),
        )
        await usage.reserve_priced_ai_usage(
            session, settings, **_request(users[0], quote, "second"),
        )
        await session.commit()
        with pytest.raises(usage.AIUsageLimitExceededError) as denied:
            await usage.reserve_priced_ai_usage(
                session, settings, **_request(users[0], quote, "third"),
            )
        assert denied.value.scope == "pending"
        await session.commit()
        replay = await usage.reserve_priced_ai_usage(
            session, settings, **_request(users[0], quote, "first"),
        )
        assert not replay.created and replay.reservation.id == first.reservation.id
        quota = await usage.read_ai_quota(session, settings, user_id=users[0])
        assert quota["pending_available"] == quota["admission_available"] == "0.000"
        assert quota["available"] == "40.000"
        assert quota["daily_available"] == "40.000"
        assert await session.scalar(select(func.count()).select_from(AIUsageReservation)) == 2


@pytest.mark.asyncio
async def test_midnight_restart_retains_reserved_unknown_and_original_business_date(
    world, monkeypatch,
):
    path, factory, users, settings = world
    today = date(2026, 10, 14)
    monkeypatch.setattr(usage, "_business_date", lambda *_: today)
    quote = _quote(settings)
    async with factory() as session:
        rows = [
            await usage.reserve_priced_ai_usage(
                session, settings, **_request(users[0], quote, str(index)),
            ) for index in range(2)
        ]
        await session.commit()
        await usage.settle_ai_usage(session, rows[0].reservation.id, status=Status.UNKNOWN)
        await session.commit()
    today = date(2026, 10, 15)
    reopened = create_async_engine(settings.database_url)
    try:
        async with async_sessionmaker(reopened, expire_on_commit=False)() as session:
            quota = await usage.read_ai_quota(session, settings, user_id=users[0])
            assert quota["reserved"] == quota["unknown"] == "0.000"
            assert quota["historical_reserved"] == quota["historical_unknown"] == "5.000"
            assert quota["admission_available"] == quota["pending_available"] == "0.000"
            assert quota["available"] == quota["daily_available"] == "50.000"
            with pytest.raises(usage.AIUsageLimitExceededError):
                await usage.reserve_priced_ai_usage(
                    session, settings, **_request(users[0], quote, "next-day"),
                )
            replay = await usage.reserve_priced_ai_usage(
                session, settings, **_request(users[0], quote, "0"),
            )
            assert not replay.created and replay.reservation.id == rows[0].reservation.id
            await usage.settle_ai_usage(session, rows[1].reservation.id, status=Status.UNKNOWN)
            await session.commit()
            quota = await usage.read_ai_quota(session, settings, user_id=users[0])
            assert quota["historical_reserved"] == "0.000"
            assert quota["historical_unknown"] == "10.000"
            assert quota["admission_available"] == "0.000"
            assert quota["available"] == "50.000"
            await usage.settle_ai_usage(
                session, rows[0].reservation.id, status=Status.SETTLED,
                actual_cost_microusd=1000, actual_cost_status="LOCAL_PRICE_USAGE",
            )
            await session.commit()
            quota = await usage.read_ai_quota(session, settings, user_id=users[0])
            assert quota["pending_available"] == "5.000"
            assert quota["settled"] == "0.000"
            old_summary = await session.scalar(select(AIUsageQuotaSummary).where(
                AIUsageQuotaSummary.scope_key == usage.user_scope_key(users[0]),
                AIUsageQuotaSummary.business_date == date(2026, 10, 14),
            ))
            assert old_summary.consumed_units == 1 and old_summary.unknown_units == 5000
    finally:
        await reopened.dispose()


@pytest.mark.asyncio
async def test_concurrent_requests_across_midnight_share_one_pending_lock(world, monkeypatch):
    _, factory, users, settings = world
    current = ContextVar("pending_business_date", default=date(2026, 10, 13))
    monkeypatch.setattr(usage, "_business_date", lambda *_: current.get())
    quote = _quote(settings)
    async with factory() as session:
        first = await usage.reserve_priced_ai_usage(
            session, settings, **_request(users[0], quote, "old"),
        )
        await session.commit()
        await usage.settle_ai_usage(session, first.reservation.id, status=Status.UNKNOWN)
        await session.commit()

    async def reserve(day):
        current.set(day)
        async with factory() as session:
            try:
                await usage.reserve_priced_ai_usage(
                    session, settings, **_request(users[0], quote, day.isoformat()),
                )
                await session.commit()
                return "accepted"
            except usage.AIUsageLimitExceededError as exc:
                await session.rollback()
                assert exc.scope == "pending"
                return "denied"

    outcomes = await asyncio.wait_for(asyncio.gather(
        reserve(date(2026, 10, 14)), reserve(date(2026, 10, 15)),
    ), timeout=10)
    assert sorted(outcomes) == ["accepted", "denied"]


@pytest.mark.asyncio
async def test_concurrent_same_key_across_dates_is_single_reservation(world, monkeypatch):
    _, factory, users, settings = world
    current = ContextVar("replay_business_date", default=date(2026, 10, 14))
    monkeypatch.setattr(usage, "_business_date", lambda *_: current.get())
    quote = _quote(settings)

    async def reserve(day):
        current.set(day)
        async with factory() as session:
            result = await usage.reserve_priced_ai_usage(
                session, settings, **_request(users[0], quote, "same"),
            )
            await session.commit()
            return result

    results = await asyncio.wait_for(asyncio.gather(
        reserve(date(2026, 10, 14)), reserve(date(2026, 10, 15)),
    ), timeout=10)
    assert results[0].reservation.id == results[1].reservation.id
    assert sorted(item.created for item in results) == [False, True]


@pytest.mark.asyncio
async def test_settlement_refreshes_stale_identity_before_moving_unknown(world):
    _, factory, users, settings = world
    async with factory() as stale:
        result = await usage.reserve_priced_ai_usage(
            stale, settings, **_request(users[0], _quote(settings), "stale"),
        )
        await stale.commit()
        async with factory() as other:
            await usage.settle_ai_usage(other, result.reservation.id, status=Status.UNKNOWN)
            await other.commit()
        assert result.reservation.status == Status.RESERVED
        await usage.settle_ai_usage(
            stale, result.reservation.id, status=Status.SETTLED, actual_cost_microusd=1001,
        )
        await stale.commit()
        summary = await stale.scalar(select(AIUsageQuotaSummary).where(
            AIUsageQuotaSummary.scope_key == usage.user_scope_key(users[0]),
        ))
        assert (summary.reserved_units, summary.unknown_units, summary.consumed_units) == (0, 0, 2)


@pytest.mark.asyncio
async def test_opposite_multi_user_settlements_finish_once(world):
    _, factory, users, settings = world
    async with factory() as session:
        rows = [
            await usage.reserve_priced_ai_usage(
                session, settings, **_request(user, _quote(settings), str(index)),
            ) for index, user in enumerate(users)
        ]
        await session.commit()

    async def settle(order):
        async with factory() as session:
            for index in order:
                await usage.settle_ai_usage(
                    session, rows[index].reservation.id, status=Status.SETTLED,
                    actual_cost_microusd=1000,
                )
            await session.commit()

    await asyncio.wait_for(asyncio.gather(settle([0, 1]), settle([1, 0])), timeout=10)
    async with factory() as session:
        assert await session.scalar(select(func.count()).select_from(AIUsageLedger)) == 4
        for user in users:
            quota = await usage.read_ai_quota(session, settings, user_id=user)
            assert quota["settled"] == "0.001" and quota["reserved"] == "0.000"


@pytest.mark.asyncio
async def test_mixed_user_batch_is_rejected_before_writes(world):
    _, factory, users, settings = world
    requests = [_request(user, _quote(settings), str(index)) for index, user in enumerate(users)]
    async with factory() as session:
        with pytest.raises(AIPricingError, match="single user"):
            await usage.reserve_ai_usage_batch(session, settings, requests=requests)
        await session.commit()
        assert await session.scalar(select(func.count()).select_from(AIUsageReservation)) == 0
        assert await session.scalar(select(func.count()).select_from(AIUsageQuotaSummary)) == 0


def _legacy(user, status, **extra):
    return AIUsageReservation(
        user_id=user, task_id=None, operation_type="AI_ANALYSIS", provider="openai",
        model="legacy", input_chars=0, input_image_count=0, max_output_tokens=1000,
        risk_units=7, accounting_version="LEGACY_RISK_V0", actual_cost_status="UNKNOWN_COST",
        idempotency_key="legacy-key", request_hash="a" * 64, status=status, **extra,
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("status", [Status.RESERVED, Status.UNKNOWN])
async def test_legacy_pending_blocks_only_affected_user_without_summary(world, status):
    _, factory, users, settings = world
    async with factory() as session:
        session.add(_legacy(users[0], status, created_at=datetime(2020, 1, 1, tzinfo=UTC)))
        session.add(AIUsageQuotaSummary(
            scope_key="__global__", scope_type="GLOBAL", business_date=date(2020, 1, 1),
            limit_units=1000, reserved_units=7, consumed_units=0, unknown_units=0,
        ))
        await session.commit()
        with pytest.raises(AIPricingError, match="legacy"):
            await usage.reserve_priced_ai_usage(
                session, settings, **_request(users[0], _quote(settings), "new"),
            )
        row = await usage.reserve_priced_ai_usage(
            session, settings, **_request(users[1], _quote(settings), "unaffected"),
        )
        await session.commit()
        assert row.created
        blocked = await usage.read_ai_quota(session, settings, user_id=users[0])
        unaffected = await usage.read_ai_quota(session, settings, user_id=users[1])
        assert blocked["legacy_reconciliation_required"]
        assert blocked["available"] == "50.000"
        assert blocked["admission_available"] == "0.000"
        assert not unaffected["legacy_reconciliation_required"]


@pytest.mark.asyncio
async def test_legacy_user_summary_does_not_block_another_user(world):
    _, factory, users, settings = world
    async with factory() as session:
        session.add(AIUsageQuotaSummary(
            scope_key=str(users[0]), scope_type="USER", user_id=users[0],
            business_date=usage._business_date(), limit_units=100, consumed_units=7,
        ))
        await session.commit()
        assert await usage.legacy_usage_blocked(
            session, usage._business_date(), user_id=users[0],
        )
        assert not await usage.legacy_usage_blocked(
            session, usage._business_date(), user_id=users[1],
        )


@pytest.mark.asyncio
async def test_legacy_unique_key_collision_is_controlled_even_when_released(world):
    _, factory, users, settings = world
    async with factory() as session:
        session.add(_legacy(users[0], Status.RELEASED))
        await session.commit()
        for operation in ("reserve", "lookup"):
            with pytest.raises(usage.AIUsageRequestConflictError, match="legacy"):
                if operation == "lookup":
                    await usage.get_ai_usage_reservation(
                        session, user_id=users[0], operation_type="AI_ANALYSIS",
                        idempotency_key="legacy-key",
                    )
                else:
                    await usage.reserve_priced_ai_usage(
                        session, settings, **_request(
                            users[0], _quote(settings), "legacy-key", operation_type="AI_ANALYSIS",
                        ),
                    )
            await session.commit()
        assert await session.scalar(select(func.count()).select_from(AIUsageReservation)) == 1


@pytest.mark.asyncio
async def test_quota_breakdown_includes_feedback_media_and_pricing_diagnostics(world, monkeypatch):
    _, factory, users, settings = world
    today = date(2026, 10, 14)
    monkeypatch.setattr(usage, "_business_date", lambda *_: today)
    quotes = [
        (estimate_price(settings, provider="openai", model="small",
                        input_tokens=1000, max_output_tokens=1000), "AI_FEEDBACK_LEARNING"),
        (estimate_price(settings, provider="wavespeed", model="image-test",
                        kind="image", image_count=1), "AI_IMAGE_SUBMIT"),
        (estimate_price(settings, provider="kling", model="video-test",
                        kind="video", video_seconds=10), "AI_VIDEO_SUBMIT"),
    ]
    async with factory() as session:
        rows = [
            await usage.reserve_priced_ai_usage(
                session, settings, **_request(
                    users[0], quote, str(index), operation_type=operation,
                ),
            ) for index, (quote, operation) in enumerate(quotes)
        ]
        await session.commit()
        await usage.settle_provider_usage(
            session, rows[0].reservation.id, input_tokens=100, output_tokens=50,
        )
        await usage.settle_ai_usage(session, rows[1].reservation.id, status=Status.UNKNOWN)
        await session.commit()
        quota = await usage.read_ai_quota(session, settings, user_id=users[0])
        assert quota["breakdown"]["text"]["settled"] == "0.001"
        assert quota["breakdown"]["image"]["unknown"] == "2.000"
        assert quota["breakdown"]["video"]["reserved"] == "1.000"
        assert quota["diagnostics"]["pricing_configured"]
        assert quota["diagnostics"]["missing_price_entries"] == []
        assert "feedback_learning" in quota["enforced_entries"]
        today = date(2026, 10, 15)
        quota = await usage.read_ai_quota(session, settings, user_id=users[0])
        assert quota["historical_reserved"] == "1.000"
        assert quota["historical_unknown"] == "2.000"
        assert quota["pending_available"] == quota["admission_available"] == "7.000"
        assert quota["available"] == "50.000"
        assert quota["breakdown"]["image"]["historical_unknown"] == "2.000"
        settings.ai_price_catalog_json = json.dumps({"version": "reference", "prices": [
            _entry("openai", "small", "input_token", 1, reference_only=True),
            _entry("openai", "small", "output_token", 1,
                   expires_at="2026-02-01T00:00:00Z"),
        ]})
        quota = await usage.read_ai_quota(session, settings, user_id=users[0])
        assert not quota["diagnostics"]["pricing_configured"]
        assert "openai/small/input_token" in quota["diagnostics"]["missing_price_entries"]
        assert "openai/small/output_token" in quota["diagnostics"]["missing_price_entries"]
        settings.ai_price_catalog_json = "invalid"
        quota = await usage.read_ai_quota(session, settings, user_id=users[0])
        assert quota["diagnostics"]["missing_price_entries"] == ["invalid_local_price_catalog"]


@pytest.mark.asyncio
async def test_midnight_daily_reset_does_not_charge_historical_pending_twice(world, monkeypatch):
    _, factory, users, settings = world
    settings.ai_risk_daily_user_limit = 5000
    today = date(2026, 10, 14)
    monkeypatch.setattr(usage, "_business_date", lambda *_: today)
    async with factory() as session:
        previous = await usage.reserve_priced_ai_usage(
            session, settings, **_request(users[0], _quote(settings), "old-day"),
        )
        await session.commit()
        await usage.settle_ai_usage(session, previous.reservation.id, status=Status.UNKNOWN)
        await session.commit()
        today = date(2026, 10, 15)
        quota = await usage.read_ai_quota(session, settings, user_id=users[0])
        assert quota["available"] == quota["pending_available"] == "5.000"
        current = await usage.reserve_priced_ai_usage(
            session, settings, **_request(users[0], _quote(settings), "new-day"),
        )
        await session.commit()
        assert current.created
        quota = await usage.read_ai_quota(session, settings, user_id=users[0])
        assert quota["historical_unknown"] == "5.000"
        assert quota["available"] == quota["pending_available"] == "0.000"


@pytest.mark.asyncio
async def test_diagnostics_checks_selected_price_bounds_not_older_valid_versions(world):
    _, factory, users, settings = world
    prices = [
        _entry("openai", "small", "input_token", 1),
        _entry("openai", "small", "output_token", 1),
        _entry("openai", "small", "input_token", 1, trusted_input_token_upper_bound=None,
               effective_at="2026-02-01T00:00:00Z"),
        _entry("openai", "small", "output_token", 1, all_parameters_upper_bound=False,
               effective_at="2026-02-01T00:00:00Z"),
    ]
    settings.ai_price_catalog_json = json.dumps({"version": "untrusted", "prices": prices})
    async with factory() as session:
        quota = await usage.read_ai_quota(session, settings, user_id=users[0])
        assert not quota["diagnostics"]["pricing_configured"]
        assert quota["diagnostics"]["missing_price_entries"] == [
            "openai/small/input_token", "openai/small/output_token",
        ]
