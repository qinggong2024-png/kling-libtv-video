import uuid
from datetime import UTC, datetime, timedelta

from libtv_agent.config import Settings
from libtv_agent.domain.enums import ParentTaskPhase
from libtv_agent.domain.models import AuditEvent, ParentTask
from libtv_agent.services.state_machine import VersionConflictError
from sqlalchemy import and_, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

ANALYSIS_STAGE_QUEUED = "QUEUED"
ANALYSIS_STAGE_PREPARING_IMAGES = "PREPARING_IMAGES"
ANALYSIS_STAGE_PROVIDER_RUNNING = "PROVIDER_RUNNING"
ANALYSIS_STAGE_VALIDATING = "VALIDATING"
ANALYSIS_STAGE_COMPLETED = "COMPLETED"
ANALYSIS_STAGE_FAILED = "FAILED"
ANALYSIS_STAGE_STALE_RECOVERED = "STALE_RECOVERED"

ANALYSIS_RETRYABLE_REASON_CODES = frozenset(
    {
        "ANALYSIS_TIMEOUT",
        "ANALYSIS_CANCELLED",
        "ANALYSIS_PROVIDER_FAILED",
        "ANALYSIS_SCHEMA_INVALID",
        "ANALYSIS_STALE_RECOVERED",
    }
)


def is_retryable_analysis_failure(task: ParentTask) -> bool:
    return (
        task.phase == ParentTaskPhase.ACTION_REQUIRED
        and task.phase_reason_code in ANALYSIS_RETRYABLE_REASON_CODES
    )


class StaleAnalysisRunError(RuntimeError):
    pass


async def claim_analysis_run(
    session: AsyncSession,
    task_id: uuid.UUID,
    user_id: uuid.UUID,
    expected_state_version: int,
) -> uuid.UUID:
    snapshot = await session.scalar(
        select(ParentTask).where(ParentTask.id == task_id, ParentTask.user_id == user_id)
    )
    if snapshot is None:
        raise VersionConflictError("task state changed")
    from_phase = snapshot.phase
    from_reason = snapshot.phase_reason_code
    retrying = is_retryable_analysis_failure(snapshot)
    run_id = uuid.uuid4()
    now = datetime.now(UTC)
    claimed = await session.scalar(
        update(ParentTask)
        .where(
            ParentTask.id == task_id,
            ParentTask.user_id == user_id,
            ParentTask.state_version == expected_state_version,
            or_(
                ParentTask.phase == ParentTaskPhase.DRAFT,
                and_(
                    ParentTask.phase == ParentTaskPhase.ACTION_REQUIRED,
                    ParentTask.phase_reason_code.in_(ANALYSIS_RETRYABLE_REASON_CODES),
                ),
            ),
        )
        .values(
            phase=ParentTaskPhase.ANALYZING,
            phase_reason_code=None,
            analysis_result_json=None,
            analysis_result_hash=None,
            consistency_level=None,
            analysis_run_id=run_id,
            analysis_stage=ANALYSIS_STAGE_QUEUED,
            analysis_started_at=now,
            analysis_heartbeat_at=now,
            analysis_attempt_count=ParentTask.analysis_attempt_count + 1,
            state_version=ParentTask.state_version + 1,
            updated_at=now,
        )
        .returning(ParentTask.id)
    )
    if claimed is None:
        await session.rollback()
        raise VersionConflictError("task state changed or cannot be analyzed")
    session.add(
        AuditEvent(
            action=("ANALYSIS_RETRY_STARTED" if retrying else "ANALYSIS_RUN_CLAIMED"),
            entity_type="ParentTask",
            entity_id=str(task_id),
            from_state=from_phase.value,
            to_state=ParentTaskPhase.ANALYZING.value,
            reason=from_reason,
            correlation_id=run_id.hex,
            evidence_refs_json=[f"analysisRun:{run_id}"],
        )
    )
    await session.commit()
    return run_id


async def touch_analysis_run(
    session: AsyncSession,
    task_id: uuid.UUID,
    analysis_run_id: uuid.UUID,
    stage: str,
) -> None:
    now = datetime.now(UTC)
    touched = await session.scalar(
        update(ParentTask)
        .where(
            ParentTask.id == task_id,
            ParentTask.phase == ParentTaskPhase.ANALYZING,
            ParentTask.analysis_run_id == analysis_run_id,
        )
        .values(
            analysis_stage=stage,
            analysis_heartbeat_at=now,
            updated_at=now,
        )
        .returning(ParentTask.id)
    )
    if touched is None:
        await session.rollback()
        raise StaleAnalysisRunError(f"analysis run {analysis_run_id} is no longer current")
    await session.commit()


async def fail_active_analysis(
    session: AsyncSession,
    task_id: uuid.UUID,
    *,
    reason_code: str,
    audit_action: str,
    reason: str,
    analysis_run_id: uuid.UUID | None = None,
) -> bool:
    now = datetime.now(UTC)
    statement = update(ParentTask).where(
        ParentTask.id == task_id,
        ParentTask.phase == ParentTaskPhase.ANALYZING,
    )
    if analysis_run_id is not None:
        statement = statement.where(ParentTask.analysis_run_id == analysis_run_id)
    transitioned = await session.scalar(
        statement.values(
            phase=ParentTaskPhase.ACTION_REQUIRED,
            phase_reason_code=reason_code,
            analysis_run_id=None,
            analysis_stage=ANALYSIS_STAGE_FAILED,
            analysis_heartbeat_at=now,
            state_version=ParentTask.state_version + 1,
            updated_at=now,
        ).returning(ParentTask.id)
    )
    if transitioned is None:
        await session.rollback()
        return False
    session.add(
        AuditEvent(
            action=audit_action,
            entity_type="ParentTask",
            entity_id=str(task_id),
            from_state=ParentTaskPhase.ANALYZING.value,
            to_state=ParentTaskPhase.ACTION_REQUIRED.value,
            reason=reason[:255],
            correlation_id=uuid.uuid4().hex,
            evidence_refs_json=[
                reason_code,
                *([f"analysisRun:{analysis_run_id}"] if analysis_run_id else []),
            ],
        )
    )
    await session.commit()
    return True


async def recover_stale_analyses(
    session: AsyncSession,
    settings: Settings,
    *,
    now: datetime | None = None,
) -> list[uuid.UUID]:
    recovered_at = now or datetime.now(UTC)
    stale_before = recovered_at - timedelta(seconds=settings.analysis_stale_after_seconds)
    candidates = list(
        await session.execute(
            select(ParentTask.id, ParentTask.analysis_run_id).where(
                ParentTask.phase == ParentTaskPhase.ANALYZING,
                func.coalesce(ParentTask.analysis_heartbeat_at, ParentTask.updated_at)
                < stale_before,
            )
        )
    )
    task_ids: list[uuid.UUID] = []
    for task_id, analysis_run_id in candidates:
        statement = update(ParentTask).where(
            ParentTask.id == task_id,
            ParentTask.phase == ParentTaskPhase.ANALYZING,
            func.coalesce(ParentTask.analysis_heartbeat_at, ParentTask.updated_at) < stale_before,
        )
        if analysis_run_id is None:
            statement = statement.where(ParentTask.analysis_run_id.is_(None))
        else:
            statement = statement.where(ParentTask.analysis_run_id == analysis_run_id)
        recovered = await session.scalar(
            statement.values(
                phase=ParentTaskPhase.ACTION_REQUIRED,
                phase_reason_code="ANALYSIS_STALE_RECOVERED",
                analysis_run_id=None,
                analysis_stage=ANALYSIS_STAGE_STALE_RECOVERED,
                analysis_heartbeat_at=recovered_at,
                state_version=ParentTask.state_version + 1,
                updated_at=recovered_at,
            ).returning(ParentTask.id)
        )
        if recovered is None:
            continue
        task_ids.append(task_id)
        session.add(
            AuditEvent(
                action="ANALYSIS_STALE_RECOVERED",
                entity_type="ParentTask",
                entity_id=str(task_id),
                from_state=ParentTaskPhase.ANALYZING.value,
                to_state=ParentTaskPhase.ACTION_REQUIRED.value,
                reason="analysis exceeded the configured stale threshold",
                correlation_id=uuid.uuid4().hex,
                evidence_refs_json=[
                    f"staleAfterSeconds:{settings.analysis_stale_after_seconds:g}",
                    *([f"analysisRun:{analysis_run_id}"] if analysis_run_id else []),
                ],
            )
        )
    await session.commit()
    return task_ids
