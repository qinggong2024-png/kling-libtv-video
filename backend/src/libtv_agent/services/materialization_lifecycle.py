import uuid
from datetime import UTC, datetime, timedelta

from libtv_agent.config import Settings
from libtv_agent.domain.enums import ParentTaskPhase
from libtv_agent.domain.models import AuditEvent, ParentTask
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession


async def recover_stale_materializations(
    session: AsyncSession,
    settings: Settings,
    *,
    now: datetime | None = None,
) -> list[uuid.UUID]:
    recovered_at = now or datetime.now(UTC)
    stale_before = recovered_at - timedelta(seconds=settings.materialization_stale_after_seconds)
    rows = await session.scalars(
        update(ParentTask)
        .where(
            ParentTask.phase == ParentTaskPhase.PREPARING,
            ParentTask.updated_at < stale_before,
        )
        .values(
            phase=ParentTaskPhase.ACTION_REQUIRED,
            phase_reason_code="MATERIALIZATION_INTERRUPTED",
            state_version=ParentTask.state_version + 1,
            updated_at=recovered_at,
        )
        .returning(ParentTask.id)
    )
    task_ids = list(rows)
    for task_id in task_ids:
        session.add(
            AuditEvent(
                action="MATERIALIZATION_STALE_RECOVERED",
                entity_type="ParentTask",
                entity_id=str(task_id),
                from_state=ParentTaskPhase.PREPARING.value,
                to_state=ParentTaskPhase.ACTION_REQUIRED.value,
                reason="materialization was interrupted before reaching a terminal local state",
                correlation_id=uuid.uuid4().hex,
                evidence_refs_json=[
                    f"staleAfterSeconds:{settings.materialization_stale_after_seconds:g}"
                ],
            )
        )
    await session.commit()
    return task_ids
