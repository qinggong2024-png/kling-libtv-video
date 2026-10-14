import asyncio
import json
import uuid
from datetime import UTC, datetime

import pytest
from libtv_agent.config import Settings
from libtv_agent.domain.enums import AIUsageReservationStatus
from libtv_agent.domain.models import AIUsageLedger, AIUsageQuotaSummary, AIUsageReservation
from libtv_agent.services.ai_pricing import (
    AIPricingError,
    actual_cost_from_snapshot,
    estimate_price,
    estimate_text_price,
    microusd_to_units,
    units_to_usd,
)
from libtv_agent.services.ai_usage import (
    AIUsageLimitExceededError,
    _business_date,
    read_ai_quota,
    reserve_ai_usage_batch,
    reserve_priced_ai_usage,
    settle_ai_usage,
    settle_provider_usage,
)
from sqlalchemy import func, select
from test_ai_usage import _database


def _entry(provider, model, unit, rate, *, quantity=1, **extra):
    return {
        "provider": provider, "model": model, "unit": unit,
        "rate_microusd": rate, "quantity": quantity,
        "version": "test-price-v1", "effective_at": "2026-01-01T00:00:00Z",
        "source": "offline test fixture; NOT a vendor quote", "reference_only": False,
        **extra,
    }


def _priced_settings(**extra):
    prices = [
        _entry("openai", "small", "input_token", 1_000_000, quantity=1_000_000),
        _entry("openai", "small", "output_token", 4_000_000, quantity=1_000_000),
        _entry("openai", "large", "input_token", 10_000_000, quantity=1_000_000),
        _entry("openai", "large", "output_token", 40_000_000, quantity=1_000_000),
        _entry("wavespeed", "image-test", "image", 2_000_000),
        _entry("kling", "video-test", "video_second", 100_000),
    ]
    return Settings(
        _env_file=None, app_env="test",
        ai_price_catalog_json=json.dumps({"version": "test-catalog-v1", "prices": prices}),
        **extra,
    )


def _request(user_id, quote, key, **extra):
    return {
        "user_id": user_id, "task_id": None, "operation_type": quote.kind.upper(),
        "quote": quote, "input_chars": 100, "input_image_count": 0,
        "max_output_tokens": 2000, "idempotency_key": key,
        "request_hash": key.ljust(64, "0")[:64], **extra,
    }


@pytest.mark.parametrize("microusd,units,usd", [
    (0, 0, "0.000"), (1, 1, "0.001"), (999, 1, "0.001"),
    (1000, 1, "0.001"), (1001, 2, "0.002"), (50_000_000, 50_000, "50.000"),
])
def test_exact_integer_conversions(microusd, units, usd):
    assert microusd_to_units(microusd) == units
    assert units_to_usd(units) == usd
    assert units_to_usd(-units) == (f"-{usd}" if units else usd)


def test_defaults_are_one_shared_fifty_dollar_pool():
    settings = Settings(_env_file=None, app_env="test")
    assert settings.ai_risk_daily_user_limit == 50_000
    assert settings.ai_request_max_units == 5000
    assert settings.ai_batch_max_units == 10_000
    assert settings.ai_unknown_price_cap_units == 5000


def test_token_model_and_media_prices_are_provider_specific():
    settings = _priced_settings()
    small = estimate_price(settings, provider="openai", model="small",
                           input_tokens=1000, max_output_tokens=1000)
    large = estimate_price(settings, provider="openai", model="large",
                           input_tokens=1000, max_output_tokens=1000)
    assert small.estimated_cost_microusd == 5000
    assert large.estimated_cost_microusd == 50_000
    assert estimate_price(
        settings, provider="wavespeed", model="image-test", kind="image", image_count=2,
    ).risk_units == 4000
    assert estimate_price(
        settings, provider="kling", model="video-test", kind="video", video_seconds=12,
    ).risk_units == 1200
    other = estimate_price(
        settings, provider="another-provider", model="image-test", kind="image", image_count=1,
    )
    assert other.risk_units == 5000
    assert other.snapshot["price_status"] == "CONSERVATIVE_CAP"


def test_effective_versions_reference_only_and_expiry():
    entries = [
        _entry("wavespeed", "image", "image", 1_000_000),
        _entry("wavespeed", "image", "image", 2_000_000, version="v2",
               effective_at="2026-10-01T00:00:00Z", expires_at="2026-11-01T00:00:00Z"),
        _entry("wavespeed", "image", "image", 3_000_000,
               effective_at="2026-10-02T00:00:00Z", reference_only=True),
        _entry("wavespeed", "image", "image", 4_000_000,
               effective_at="2027-01-01T00:00:00Z"),
    ]
    settings = Settings(_env_file=None, app_env="test",
                        ai_price_catalog_json=json.dumps({"version": "v", "prices": entries}))
    quote = estimate_price(
        settings, provider="wavespeed", model="image", kind="image", image_count=1,
        now=datetime(2026, 10, 14, tzinfo=UTC),
    )
    assert quote.risk_units == 2000
    assert quote.snapshot["prices"]["image"]["version"] == "v2"
    settings.ai_price_catalog_json = json.dumps({"version": "v", "prices": entries[2:3]})
    assert estimate_price(
        settings, provider="wavespeed", model="image", kind="image", image_count=1,
    ).risk_units == 5000
    settings.ai_unknown_price_policy = "reject"
    with pytest.raises(AIPricingError, match="no effective"):
        estimate_price(settings, provider="wavespeed", model="image",
                       kind="image", image_count=1)


def test_request_batch_retry_fallback_and_malformed_prices():
    settings = _priced_settings()
    assert estimate_price(
        settings, provider="wavespeed", model="image-test", kind="image", image_count=1,
        retry_attempts=1, fallback_reserve_microusd=500_000,
    ).risk_units == 4500
    with pytest.raises(AIPricingError, match="request cap"):
        estimate_price(settings, provider="wavespeed", model="image-test",
                       kind="image", image_count=3)
    with pytest.raises(AIPricingError, match="integers"):
        estimate_price(settings, provider="kling", model="video-test",
                       kind="video", video_seconds=1.5)
    settings.ai_price_catalog_json = '{"version":"v","prices":[{"rate_microusd":0.2}]}'
    with pytest.raises(AIPricingError, match="invalid"):
        estimate_price(settings, provider="openai", model="small")


def test_snapshot_survives_catalog_change_and_missing_usage_is_unknown():
    settings = _priced_settings()
    quote = estimate_text_price(
        settings, provider="openai", model="small", input_chars=100,
        input_image_count=2, max_output_tokens=2000,
    )
    assert quote.snapshot["quantities"]["input_token"] >= 8192 + 8192 + 400
    settings.ai_price_catalog_json = '{"version":"new","prices":[]}'
    assert actual_cost_from_snapshot(
        quote.snapshot, input_tokens=100, output_tokens=50,
    ) == 300
    assert actual_cost_from_snapshot(
        quote.snapshot, input_tokens=None, output_tokens=50,
    ) is None


def test_business_date_converts_utc_and_sqlite_naive_timestamps():
    assert _business_date(datetime(2026, 10, 13, 17, tzinfo=UTC)).isoformat() == "2026-10-14"
    assert _business_date(datetime(2026, 10, 13, 17)).isoformat() == "2026-10-14"


@pytest.mark.asyncio
async def test_text_image_video_share_pool_and_restart_preserves_dollars(tmp_path):
    user = uuid.uuid4()
    engine, factory = await _database(tmp_path / "shared.db", user_ids=[user])
    settings = _priced_settings(ai_risk_daily_user_limit=5000)
    quotes = [
        estimate_price(settings, provider="openai", model="small",
                       input_tokens=0, max_output_tokens=250_000),
        estimate_price(settings, provider="wavespeed", model="image-test",
                       kind="image", image_count=1),
        estimate_price(settings, provider="kling", model="video-test",
                       kind="video", video_seconds=20),
    ]
    async with factory() as session:
        for index, quote in enumerate(quotes):
            await reserve_priced_ai_usage(session, settings, **_request(user, quote, str(index)))
        await session.commit()
        quota = await read_ai_quota(session, settings, user_id=user)
        assert quota["total"] == "5.000"
        assert quota["reserved"] == "5.000"
        assert quota["available"] == "0.000"
        with pytest.raises(AIUsageLimitExceededError):
            await reserve_priced_ai_usage(
                session, settings, **_request(user, quotes[0], "extra"),
            )
        await session.commit()  # Failed reservation cannot leak a partial quota update.
    await engine.dispose()
    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

    reopened = create_async_engine(f"sqlite+aiosqlite:///{(tmp_path / 'shared.db').as_posix()}")
    async with AsyncSession(reopened) as session:
        quota = await read_ai_quota(session, settings, user_id=user)
        assert quota["reserved"] == "5.000"
        assert await session.scalar(select(func.count()).select_from(AIUsageReservation)) == 3
    await reopened.dispose()


@pytest.mark.asyncio
async def test_unknown_settlement_retains_budget_and_reconciliation_releases_surplus(tmp_path):
    user = uuid.uuid4()
    engine, factory = await _database(tmp_path / "settle.db", user_ids=[user])
    settings = _priced_settings()
    quote = estimate_price(settings, provider="openai", model="small",
                           input_tokens=10_000, max_output_tokens=10_000)
    async with factory() as session:
        row = await reserve_priced_ai_usage(
            session, settings, **_request(user, quote, "settle"),
        )
        await session.commit()
        await settle_provider_usage(session, row.reservation.id)
        await session.commit()
        assert (await read_ai_quota(session, settings, user_id=user))["unknown"] == "0.050"
        await settle_provider_usage(
            session, row.reservation.id, input_tokens=1001, output_tokens=500,
        )
        await session.commit()
        assert row.reservation.actual_cost_microusd == 3001
        quota = await read_ai_quota(session, settings, user_id=user)
        assert (quota["unknown"], quota["reserved"], quota["settled"]) == (
            "0.000", "0.000", "0.004",
        )
        assert quota["available"] == "49.996"
        assert row.reservation.actual_cost_status == "LOCAL_PRICE_USAGE"
        await settle_provider_usage(session, row.reservation.id, input_tokens=0, output_tokens=0)
        await session.commit()
        assert (await read_ai_quota(session, settings, user_id=user))["settled"] == "0.004"
    await engine.dispose()


@pytest.mark.asyncio
async def test_unknown_price_success_cannot_be_reported_as_known_zero_cost(tmp_path):
    user = uuid.uuid4()
    engine, factory = await _database(tmp_path / "unknown.db", user_ids=[user])
    settings = _priced_settings()
    quote = estimate_price(settings, provider="unpriced", model="unknown")
    async with factory() as session:
        row = await reserve_priced_ai_usage(session, settings, **_request(user, quote, "unknown"))
        await session.commit()
        await settle_provider_usage(session, row.reservation.id, input_tokens=10, output_tokens=20)
        await session.commit()
        assert row.reservation.status == AIUsageReservationStatus.UNKNOWN
        assert row.reservation.actual_input_tokens == 10
        assert row.reservation.actual_cost_microusd is None
        assert (await read_ai_quota(session, settings, user_id=user))["unknown"] == "5.000"
    await engine.dispose()


@pytest.mark.asyncio
async def test_batch_cap_and_quota_failure_leave_no_partial_batch(tmp_path):
    user = uuid.uuid4()
    engine, factory = await _database(tmp_path / "batch.db", user_ids=[user])
    settings = _priced_settings(ai_risk_daily_user_limit=9000)
    quote = estimate_price(settings, provider="unpriced", model="unknown")
    requests = [_request(user, quote, str(index)) for index in range(3)]
    async with factory() as session:
        with pytest.raises(AIPricingError, match="batch cap"):
            await reserve_ai_usage_batch(session, settings, requests=requests)
        with pytest.raises(AIUsageLimitExceededError):
            await reserve_ai_usage_batch(session, settings, requests=requests[:2])
        await session.commit()
        assert await session.scalar(select(func.count()).select_from(AIUsageReservation)) == 0
        assert (await read_ai_quota(session, settings, user_id=user))["reserved"] == "0.000"
        settings.ai_risk_daily_user_limit = 50_000
        results = await reserve_ai_usage_batch(session, settings, requests=requests[:2])
        await session.commit()
        assert len(results) == 2
        assert (await read_ai_quota(session, settings, user_id=user))["reserved"] == "10.000"
    await engine.dispose()


@pytest.mark.asyncio
async def test_concurrent_same_key_and_settlement_claims_are_exactly_once(tmp_path):
    user = uuid.uuid4()
    engine, factory = await _database(tmp_path / "concurrency.db", user_ids=[user])
    settings = _priced_settings()
    quote = estimate_price(settings, provider="unpriced", model="unknown")

    async def reserve():
        async with factory() as session:
            row = await reserve_priced_ai_usage(session, settings, **_request(user, quote, "same"))
            await session.commit()
            return row

    first, second = await asyncio.gather(reserve(), reserve())
    assert first.reservation.id == second.reservation.id
    assert sorted([first.created, second.created]) == [False, True]

    async def settle():
        async with factory() as session:
            await settle_ai_usage(
                session, first.reservation.id, status=AIUsageReservationStatus.SETTLED,
                actual_cost_microusd=1001, actual_cost_status="LOCAL_PRICE_USAGE",
            )
            await session.commit()

    await asyncio.gather(settle(), settle(), settle())
    async with factory() as session:
        assert (await read_ai_quota(session, settings, user_id=user))["settled"] == "0.002"
        assert await session.scalar(select(func.count()).select_from(AIUsageLedger)) == 2
    await engine.dispose()


@pytest.mark.asyncio
async def test_concurrent_distinct_settlements_do_not_lose_usage(tmp_path):
    user = uuid.uuid4()
    engine, factory = await _database(tmp_path / "distinct.db", user_ids=[user])
    settings = _priced_settings()
    quote = estimate_price(settings, provider="unpriced", model="unknown")
    async with factory() as session:
        rows = [
            await reserve_priced_ai_usage(session, settings, **_request(user, quote, str(index)))
            for index in range(2)
        ]
        await session.commit()

    async def settle(index):
        async with factory() as session:
            await settle_ai_usage(
                session, rows[index].reservation.id, status=AIUsageReservationStatus.SETTLED,
                actual_cost_microusd=1001 + index,
            )
            await session.commit()

    await asyncio.gather(settle(0), settle(1))
    async with factory() as session:
        quota = await read_ai_quota(session, settings, user_id=user)
        assert quota["settled"] == "0.004"
        assert quota["reserved"] == "0.000"
    await engine.dispose()


@pytest.mark.asyncio
async def test_legacy_risk_is_not_reinterpreted_as_dollars(tmp_path):
    user = uuid.uuid4()
    engine, factory = await _database(tmp_path / "legacy.db", user_ids=[user])
    settings = _priced_settings()
    async with factory() as session:
        session.add(AIUsageQuotaSummary(
            scope_key="__global__", scope_type="GLOBAL", business_date=_business_date(),
            limit_units=1000, consumed_units=7, reserved_units=0, unknown_units=0,
        ))
        await session.commit()
        quota = await read_ai_quota(session, settings, user_id=user)
        assert quota["settled"] == "0.000"
        assert quota["legacy_reconciliation_required"] is True
        quote = estimate_price(settings, provider="unpriced", model="unknown")
        with pytest.raises(AIPricingError, match="legacy"):
            await reserve_priced_ai_usage(session, settings, **_request(user, quote, "new"))
        await session.commit()
        assert await session.scalar(select(func.count()).select_from(AIUsageReservation)) == 0
    await engine.dispose()


def test_migration_preserves_old_risk_units(tmp_path, monkeypatch):
    from pathlib import Path

    from alembic import command
    from alembic.config import Config
    from alembic.script import ScriptDirectory
    from libtv_agent import config as config_module
    from sqlalchemy import create_engine, inspect, text

    database_path = tmp_path / "migration.db"
    settings = Settings(_env_file=None, app_env="test",
                        database_url=f"sqlite+aiosqlite:///{database_path.as_posix()}")
    monkeypatch.setattr(config_module, "get_settings", lambda: settings)
    configuration = Config(str(Path(__file__).parents[1] / "alembic.ini"))
    graph = ScriptDirectory.from_config(configuration)
    assert graph.get_heads() == ["ca01b2c3d406"]
    assert graph.get_revision("c9f0a1b2c3d4").down_revision == "c8e9f0a1b2c3"
    command.upgrade(configuration, "c8e9f0a1b2c3")
    engine = create_engine(f"sqlite:///{database_path.as_posix()}")
    identifier = uuid.uuid4().hex
    user = uuid.uuid4().hex
    with engine.begin() as connection:
        connection.execute(text(
            "INSERT INTO app_user (id, username, password_hash, role, is_active, "
            "created_at, auto_confirm_prompts, video_learning_enabled) VALUES "
            "(:id, 'legacy', 'unused', 'USER', 1, '2026-10-14 00:00:00', 0, 0)"
        ), {"id": user})
        connection.execute(text(
            "INSERT INTO ai_usage_reservation "
            "(id,user_id,operation_type,provider,model,input_chars,input_image_count,"
            "max_output_tokens,risk_units,actual_cost_status,idempotency_key,request_hash,status,"
            "created_at)"
            " VALUES (:id,:user,'AI_ANALYSIS','openai','legacy',0,0,1000,7,"
            "'UNKNOWN_COST','legacy','hash','UNKNOWN','2026-10-14 00:00:00')"
            ), {"id": identifier, "user": user})
    command.upgrade(configuration, "head")
    with engine.connect() as connection:
        row = connection.execute(text(
            "SELECT risk_units, accounting_version, estimated_cost_microusd "
            "FROM ai_usage_reservation"
        )).one()
        assert row == (7, "LEGACY_RISK_V0", None)
        assert "points_reservation" in inspect(connection).get_table_names()
    engine.dispose()
