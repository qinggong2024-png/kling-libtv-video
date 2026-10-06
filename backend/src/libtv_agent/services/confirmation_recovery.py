"""Recover confirmation requests whose owning API process disappeared."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from libtv_agent.domain.enums import ParentTaskPhase
from libtv_agent.domain.models import (
    ApiIdempotencyRecord,
    AuditEvent,
    ParentTask,
    TaskConfirmationVersion,
)
from libtv_agent.domain.schemas import BatchConfirmationResponse, BatchConfirmationResult
from libtv_agent.services.idempotency import STALE_CLAIM_GRACE
from libtv_agent.services.tasks import task_to_read
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

CONFIRMATION_OPERATION_PREFIX = "CONFIRM_TASK:"
CONFIRMATION_PROCESS_RESTARTED = "CONFIRMATION_PROCESS_RESTARTED"
BATCH_CONFIRMATION_OPERATION = "BATCH_CONFIRM"


def _claim_task_id(record: ApiIdempotencyRecord) -> uuid.UUID | None:
    if not record.operation_type.startswith(CONFIRMATION_OPERATION_PREFIX):
        return None
    try:
        return uuid.UUID(record.operation_type.removeprefix(CONFIRMATION_OPERATION_PREFIX))
    except ValueError:
        return None


def _utc(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


async def recover_stale_confirmation_claims(
    session: AsyncSession,
    settings,
    *,
    older_than: timedelta = STALE_CLAIM_GRACE,
    limit: int = 200,
) -> dict[str, int]:
    """Resolve response-less confirmation claims without starting paid work.

    A task confirmation can commit its durable task changes before the HTTP response
    idempotency row is settled. On restart, a completed confirmation can therefore
    safely receive a reconstructed response. A task still in PREPARING is made
    explicitly recoverable instead of being left stuck. Ambiguous claims are released
    only; they are never retried automatically.
    """
    cutoff = datetime.now(UTC) - older_than
    records = list(
        await session.scalars(
            select(ApiIdempotencyRecord)
            .where(
                ApiIdempotencyRecord.response_status == 0,
                ApiIdempotencyRecord.created_at <= cutoff,
                ApiIdempotencyRecord.operation_type.like(
                    f"{CONFIRMATION_OPERATION_PREFIX}%"
                ),
            )
            .order_by(ApiIdempotencyRecord.created_at)
            .limit(limit)
        )
    )
    replayed = 0
    reset = 0
    released = 0
    for record in records:
        task_id = _claim_task_id(record)
        task = await session.get(ParentTask, task_id) if task_id else None
        if task is None:
            await session.delete(record)
            released += 1
            continue

        confirmed = await session.scalar(
            select(TaskConfirmationVersion)
            .where(
                TaskConfirmationVersion.parent_task_id == task.id,
                TaskConfirmationVersion.confirmed_by == uuid.UUID(record.tenant_id),
                TaskConfirmationVersion.confirmed_at >= _utc(record.created_at),
            )
            .order_by(TaskConfirmationVersion.confirmed_at.desc())
            .limit(1)
        )
        if confirmed is not None:
            response = await task_to_read(
                session, task, settings.daily_user_points_limit
            )
            record.response_status = 200
            record.response_body_json = response.model_dump(mode="json", by_alias=True)
            replayed += 1
            continue

        if task.phase == ParentTaskPhase.PREPARING:
            previous_phase = task.phase.value
            task.phase = ParentTaskPhase.ACTION_REQUIRED
            task.phase_reason_code = CONFIRMATION_PROCESS_RESTARTED
            task.state_version += 1
            session.add(
                AuditEvent(
                    actor_id=uuid.UUID(record.tenant_id),
                    action="CONFIRMATION_PROCESS_RESTARTED",
                    entity_type="parent_task",
                    entity_id=str(task.id),
                    from_state=previous_phase,
                    to_state=task.phase.value,
                    reason="confirmation worker disappeared before durable confirmation",
                    correlation_id=str(uuid.uuid4()),
                    evidence_refs_json=[],
                )
            )
            reset += 1
        await session.delete(record)
        released += 1
    await session.commit()
    return {"replayed": replayed, "reset": reset, "released": released}


async def recover_stale_batch_confirmation_claims(
    session: AsyncSession,
    settings,
    *,
    older_than: timedelta = STALE_CLAIM_GRACE,
    limit: int = 200,
) -> dict[str, int]:
    """Rebuild a batch-confirm response after durable confirmation committed.

    The request snapshot is retained only on an unfinished idempotency claim. This
    lets startup recover the response without repeating confirmation or dispatch.
    Claims whose tasks are still PREPARING remain for the normal confirmation
    recovery path.
    """
    cutoff = datetime.now(UTC) - older_than
    records = list(
        await session.scalars(
            select(ApiIdempotencyRecord)
            .where(
                ApiIdempotencyRecord.operation_type == BATCH_CONFIRMATION_OPERATION,
                ApiIdempotencyRecord.response_status == 0,
                ApiIdempotencyRecord.created_at <= cutoff,
            )
            .order_by(ApiIdempotencyRecord.created_at)
            .limit(limit)
        )
    )
    replayed = 0
    released = 0
    for record in records:
        payload = (record.response_body_json or {}).get("_requestPayload")
        items = payload.get("tasks") if isinstance(payload, dict) else None
        if not isinstance(items, list) or not items:
            continue
        results: list[BatchConfirmationResult] = []
        recoverable = True
        for item in items:
            if not isinstance(item, dict) or "taskId" not in item:
                recoverable = False
                break
            try:
                task_id = uuid.UUID(str(item["taskId"]))
            except (TypeError, ValueError):
                recoverable = False
                break
            task = await session.scalar(
                select(ParentTask)
                .where(ParentTask.id == task_id, ParentTask.user_id == uuid.UUID(record.tenant_id))
                .options(selectinload(ParentTask.variants), selectinload(ParentTask.assets))
            )
            confirmed = await session.scalar(
                select(TaskConfirmationVersion)
                .where(
                    TaskConfirmationVersion.parent_task_id == task_id,
                    TaskConfirmationVersion.confirmed_by == uuid.UUID(record.tenant_id),
                    TaskConfirmationVersion.confirmed_at >= _utc(record.created_at),
                )
                .order_by(TaskConfirmationVersion.confirmed_at.desc())
                .limit(1)
            )
            if task is None or confirmed is None or task.phase == ParentTaskPhase.PREPARING:
                recoverable = False
                break
            results.append(
                BatchConfirmationResult(
                    task_id=task_id,
                    status="SUCCEEDED",
                    task=await task_to_read(session, task, settings.daily_user_points_limit),
                )
            )
        if not recoverable:
            continue
        response = BatchConfirmationResponse(
            results=results,
            succeeded_count=len(results),
            failed_count=0,
        )
        record.response_status = 200
        record.response_body_json = response.model_dump(mode="json", by_alias=True)
        replayed += 1
    await session.commit()
    return {"replayed": replayed, "released": released}
