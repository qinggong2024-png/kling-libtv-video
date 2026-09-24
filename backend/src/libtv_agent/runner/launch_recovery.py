"""Resolve expired launch intents without calling a provider or resubmitting."""

from datetime import UTC, datetime, timedelta

from libtv_agent.adapters.libtv import LibTVError
from libtv_agent.domain.enums import CommandStatus
from libtv_agent.domain.models import GenerationAttempt, GenerationCommand
from libtv_agent.services.capacity import release_capacity
from libtv_agent.services.provider_routing import provider_kind
from sqlalchemy import select, update


async def recover_abandoned_launches(supervisor, session) -> int:
    cutoff = datetime.now(UTC) - timedelta(minutes=15)
    candidates = list(
        await session.scalars(
            select(GenerationCommand.id).where(
                GenerationCommand.status == CommandStatus.LAUNCH_STARTED,
                GenerationCommand.lease_expires_at < cutoff,
            )
        )
    )
    resolved = 0
    for command_id in candidates:
        # Re-check after acquiring the write lock; a scan is not a claim.
        claimed = await session.execute(
            update(GenerationCommand)
            .where(
                GenerationCommand.id == command_id,
                GenerationCommand.status == CommandStatus.LAUNCH_STARTED,
                GenerationCommand.lease_expires_at < cutoff,
            )
            .values(status=GenerationCommand.status)
            .execution_options(synchronize_session=False)
        )
        if claimed.rowcount != 1:
            await session.commit()
            continue
        command = await session.get(GenerationCommand, command_id, populate_existing=True)
        attempt = await session.get(GenerationAttempt, command.attempt_id, populate_existing=True)
        if attempt is None or attempt.task_id:
            # Known remote handles belong to the provider-specific query path.
            await session.commit()
            continue
        command.lease_expires_at = None
        if provider_kind(attempt.provider, supervisor.settings) == "kling":
            await release_capacity(session, command.id)
        # Capacity release and uncertainty settlement commit together in _handle_error.
        await supervisor._handle_error(
            session,
            command,
            attempt,
            LibTVError(
                "LAUNCH_ABANDONED",
                "runner stopped before persisting a remote handle; submission remains uncertain",
                submitted=True,
                uncertain=True,
            ),
        )
        resolved += 1
    return resolved
