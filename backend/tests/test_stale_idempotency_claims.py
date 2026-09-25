"""Abandoned idempotency claims must be released, while live claims survive."""

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from libtv_agent.domain.contracts import sha256_json
from libtv_agent.domain.models import ApiIdempotencyRecord, Base
from libtv_agent.services.idempotency import (
    STALE_CLAIM_GRACE,
    release_idempotency_claim,
    release_stale_idempotency_claims,
)
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

SETTLED = 200
UNSETTLED = 0


@pytest.fixture
async def session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as value:
        yield value
    await engine.dispose()


def _record(*, age: timedelta, response_status: int, key: str = "k") -> ApiIdempotencyRecord:
    return ApiIdempotencyRecord(
        id=uuid.uuid4(),
        tenant_id="tenant",
        operation_type="CONFIRM_TASK:whatever",
        idempotency_key=key,
        payload_hash="0" * 64,
        response_status=response_status,
        response_body_json={},
        created_at=datetime.now(UTC) - age,
        expires_at=datetime.now(UTC) + timedelta(days=90),
    )


async def _count(session) -> int:
    return await session.scalar(select(func.count()).select_from(ApiIdempotencyRecord))


@pytest.mark.asyncio
async def test_releases_only_the_abandoned_claim(session) -> None:
    session.add_all(
        [
            _record(age=timedelta(hours=2), response_status=UNSETTLED, key="abandoned"),
            _record(age=timedelta(hours=2), response_status=SETTLED, key="answered"),
            _record(age=timedelta(seconds=5), response_status=UNSETTLED, key="in-flight"),
        ]
    )
    await session.commit()
    assert await release_stale_idempotency_claims(session) == 1
    remaining = {row.idempotency_key for row in await session.scalars(select(ApiIdempotencyRecord))}
    assert remaining == {"answered", "in-flight"}


@pytest.mark.asyncio
async def test_a_live_request_is_never_released(session) -> None:
    session.add(_record(age=timedelta(seconds=1), response_status=UNSETTLED))
    await session.commit()
    assert await release_stale_idempotency_claims(session) == 0
    assert await _count(session) == 1


@pytest.mark.asyncio
async def test_a_settled_claim_survives_regardless_of_age(session) -> None:
    session.add(_record(age=timedelta(days=30), response_status=SETTLED))
    await session.commit()
    assert await release_stale_idempotency_claims(session) == 0
    assert await _count(session) == 1


@pytest.mark.asyncio
async def test_sweep_is_bounded_and_reports_what_it_released(session) -> None:
    session.add_all(
        [_record(age=timedelta(hours=3), response_status=UNSETTLED, key=f"k{i}") for i in range(5)]
    )
    await session.commit()
    assert await release_stale_idempotency_claims(session, limit=2) == 2
    assert await _count(session) == 3
    assert await release_stale_idempotency_claims(session, limit=2) == 2
    assert await release_stale_idempotency_claims(session, limit=2) == 1
    assert await _count(session) == 0


@pytest.mark.asyncio
async def test_sweep_on_an_empty_table_is_a_no_op(session) -> None:
    assert await release_stale_idempotency_claims(session) == 0


def test_grace_period_is_long_enough_to_never_catch_a_live_request() -> None:
    assert STALE_CLAIM_GRACE >= timedelta(minutes=5)


@pytest.mark.asyncio
async def test_release_claim_leaves_a_settled_row_for_the_same_key(session) -> None:
    payload = {"a": 1}
    session.add(
        ApiIdempotencyRecord(
            id=uuid.uuid4(),
            tenant_id="tenant",
            operation_type="CONFIRM_TASK:x",
            idempotency_key="key",
            payload_hash=sha256_json(payload),
            response_status=SETTLED,
            response_body_json={},
            created_at=datetime.now(UTC),
            expires_at=datetime.now(UTC) + timedelta(days=90),
        )
    )
    await session.commit()
    await release_idempotency_claim(
        session, tenant_id="tenant", operation_type="CONFIRM_TASK:x", key="key", payload=payload
    )
    assert await _count(session) == 1
