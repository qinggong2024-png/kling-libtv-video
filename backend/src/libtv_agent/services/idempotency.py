import asyncio
import logging
from datetime import UTC, datetime, timedelta
from typing import Any

from libtv_agent.domain.contracts import sha256_json
from libtv_agent.domain.models import ApiIdempotencyRecord
from sqlalchemy import delete, select, update
from sqlalchemy.dialects.postgresql import insert as postgresql_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


class IdempotencyConflictError(RuntimeError):
    pass


class IdempotencyInProgressError(RuntimeError):
    pass


async def load_idempotent_response(
    session: AsyncSession, *, tenant_id: str, operation_type: str, key: str, payload: Any
) -> tuple[int, dict[str, Any]] | None:
    payload_hash = sha256_json(payload)
    values = {
        "tenant_id": tenant_id,
        "operation_type": operation_type,
        "idempotency_key": key,
        "payload_hash": payload_hash,
        "response_status": 0,
        "response_body_json": {},
        "expires_at": datetime.now(UTC) + timedelta(days=90),
    }
    dialect = session.get_bind().dialect.name
    insert_factory = sqlite_insert if dialect == "sqlite" else postgresql_insert
    statement = (
        insert_factory(ApiIdempotencyRecord)
        .values(**values)
        .on_conflict_do_nothing(index_elements=["tenant_id", "operation_type", "idempotency_key"])
    )
    claimed = await session.execute(statement)
    if claimed.rowcount == 1:
        return None
    await session.rollback()
    lookup = select(ApiIdempotencyRecord).where(
        ApiIdempotencyRecord.tenant_id == tenant_id,
        ApiIdempotencyRecord.operation_type == operation_type,
        ApiIdempotencyRecord.idempotency_key == key,
    )
    record = await session.scalar(lookup)
    if record is None:
        raise RuntimeError("idempotency claim disappeared")
    if record.payload_hash != payload_hash:
        logger.info("idempotency.conflict", extra={"count": 1})
        raise IdempotencyConflictError("idempotency key was reused with a different payload")
    for _ in range(100):
        if record.response_status != 0:
            break
        await asyncio.sleep(0.02)
        await session.rollback()
        record = await session.scalar(lookup)
        if record is None:
            raise RuntimeError("idempotency claim disappeared")
    if record.response_status == 0:
        logger.info("idempotency.in_progress", extra={"count": 1})
        raise IdempotencyInProgressError("the original request is still in progress")
    logger.info("idempotency.replay", extra={"count": 1})
    return record.response_status, record.response_body_json


async def store_idempotent_response(
    session: AsyncSession,
    *,
    tenant_id: str,
    operation_type: str,
    key: str,
    payload: Any,
    response_status: int,
    response_body: dict[str, Any],
) -> None:
    result = await session.execute(
        update(ApiIdempotencyRecord)
        .where(
            ApiIdempotencyRecord.tenant_id == tenant_id,
            ApiIdempotencyRecord.operation_type == operation_type,
            ApiIdempotencyRecord.idempotency_key == key,
            ApiIdempotencyRecord.payload_hash == sha256_json(payload),
        )
        .values(response_status=response_status, response_body_json=response_body)
    )
    if result.rowcount != 1:
        raise RuntimeError("idempotency response was stored without an owned claim")


async def release_idempotency_claim(
    session: AsyncSession,
    *,
    tenant_id: str,
    operation_type: str,
    key: str,
    payload: Any,
) -> None:
    await session.execute(
        delete(ApiIdempotencyRecord).where(
            ApiIdempotencyRecord.tenant_id == tenant_id,
            ApiIdempotencyRecord.operation_type == operation_type,
            ApiIdempotencyRecord.idempotency_key == key,
            ApiIdempotencyRecord.payload_hash == sha256_json(payload),
            ApiIdempotencyRecord.response_status == 0,
        )
    )
    await session.commit()
