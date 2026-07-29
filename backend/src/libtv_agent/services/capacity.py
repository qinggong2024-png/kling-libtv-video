from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from libtv_agent.config import Settings
from libtv_agent.domain.models import (
    CapacitySlot,
    GenerationAttempt,
    GenerationCommand,
    GenerationVariant,
    ParentTask,
)
from libtv_agent.services.runtime_control import get_runtime_config
from sqlalchemy import or_, select, update
from sqlalchemy.dialects.postgresql import insert as postgresql_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.ext.asyncio import AsyncSession


@dataclass(frozen=True)
class CapacityLease:
    command_id: uuid.UUID
    slot_ids: tuple[uuid.UUID, ...]


async def _ensure_scope_slots(
    session: AsyncSession, scope_type: str, scope_id: str, count: int
) -> None:
    insert_factory = (
        sqlite_insert if session.get_bind().dialect.name == "sqlite" else postgresql_insert
    )
    for slot_no in range(1, count + 1):
        await session.execute(
            insert_factory(CapacitySlot)
            .values(
                id=uuid.uuid4(),
                scope_type=scope_type,
                scope_id=scope_id,
                slot_no=slot_no,
            )
            .on_conflict_do_nothing(index_elements=["scope_type", "scope_id", "slot_no"])
        )


async def acquire_capacity(
    session: AsyncSession,
    settings: Settings,
    command: GenerationCommand,
    *,
    lease_seconds: int = 60,
) -> CapacityLease | None:
    attempt = await session.get(GenerationAttempt, command.attempt_id)
    if attempt is None:
        return None
    variant = await session.get(GenerationVariant, attempt.variant_id)
    if variant is None:
        return None
    task = await session.get(ParentTask, variant.parent_task_id)
    if task is None:
        return None
    project_scope_id = attempt.project_uuid
    if not project_scope_id:
        if attempt.provider not in {"kling", settings.kling_cli_provider_name}:
            return None
        project_scope_id = f"{attempt.provider}:{task.id}"
    runtime = await get_runtime_config(session, settings)
    if runtime is None or runtime.config_json["globalPaused"]:
        return None
    limits = runtime.config_json["generationConcurrency"]
    scopes = (
        ("GLOBAL", settings.deployment_id, int(limits["global"])),
        ("USER", str(task.user_id), int(limits["perUser"])),
        ("PROJECT", project_scope_id, int(limits["sameProject"])),
    )
    now = datetime.now(UTC)
    expires = now + timedelta(seconds=lease_seconds)
    acquired: list[CapacitySlot] = []
    for scope_type, scope_id, count in scopes:
        await _ensure_scope_slots(session, scope_type, scope_id, count)
        slot = await session.scalar(
            select(CapacitySlot)
            .where(
                CapacitySlot.scope_type == scope_type,
                CapacitySlot.scope_id == scope_id,
                CapacitySlot.slot_no <= count,
                or_(
                    CapacitySlot.command_id.is_(None),
                    CapacitySlot.lease_expires_at < now,
                    CapacitySlot.command_id == command.id,
                ),
            )
            .order_by(CapacitySlot.slot_no)
            .with_for_update(skip_locked=True)
            .limit(1)
        )
        if slot is None:
            for held in acquired:
                held.command_id = None
                held.lease_expires_at = None
            await session.flush()
            return None
        slot.command_id = command.id
        slot.lease_expires_at = expires
        acquired.append(slot)
    await session.flush()
    return CapacityLease(command.id, tuple(slot.id for slot in acquired))


async def renew_capacity(
    session: AsyncSession, command_id: uuid.UUID, *, lease_seconds: int = 60
) -> int:
    result = await session.execute(
        update(CapacitySlot)
        .where(CapacitySlot.command_id == command_id)
        .values(lease_expires_at=datetime.now(UTC) + timedelta(seconds=lease_seconds))
    )
    return int(result.rowcount or 0)


async def release_capacity(session: AsyncSession, command_id: uuid.UUID) -> int:
    result = await session.execute(
        update(CapacitySlot)
        .where(CapacitySlot.command_id == command_id)
        .values(command_id=None, lease_expires_at=None)
    )
    return int(result.rowcount or 0)
