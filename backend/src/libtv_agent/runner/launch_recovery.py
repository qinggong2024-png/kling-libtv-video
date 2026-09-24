"""Resolve expired launch intents without calling a provider or resubmitting."""

from datetime import UTC, datetime, timedelta

from libtv_agent.adapters.libtv import LibTVError
from libtv_agent.domain.enums import AttemptStatus, CommandStatus
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
        if attempt is None:
            await session.commit()
            continue
        if attempt.task_id:
            if provider_kind(
                attempt.provider, supervisor.settings
            ) == "kling" and attempt.status in {
                AttemptStatus.LAUNCHING,
                AttemptStatus.RUNNING,
            }:
                attempt.status = AttemptStatus.RUNNING
                attempt.state_version += 1
                command.status = CommandStatus.PROCESS_STARTED
                command.lease_expires_at = None
                resolved += 1
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


async def recover_abandoned_claims(session) -> int:
    cutoff = datetime.now(UTC) - timedelta(minutes=15)
    ids = list(
        await session.scalars(
            select(GenerationCommand.id).where(
                GenerationCommand.status == CommandStatus.CLAIMED,
                GenerationCommand.lease_expires_at < cutoff,
                GenerationCommand.launch_started_at.is_(None),
            )
        )
    )
    recovered = 0
    for command_id in ids:
        locked = await session.execute(
            update(GenerationCommand)
            .where(
                GenerationCommand.id == command_id,
                GenerationCommand.status == CommandStatus.CLAIMED,
                GenerationCommand.lease_expires_at < cutoff,
                GenerationCommand.launch_started_at.is_(None),
            )
            .values(status=GenerationCommand.status)
            .execution_options(synchronize_session=False)
        )
        if locked.rowcount != 1:
            await session.commit()
            continue
        command = await session.get(GenerationCommand, command_id, populate_existing=True)
        attempt = await session.get(GenerationAttempt, command.attempt_id, populate_existing=True)
        if (
            attempt is None
            or attempt.status != AttemptStatus.LAUNCHING
            or attempt.task_id
            or attempt.launch_started_at
            or attempt.submitted_at
        ):
            await session.commit()
            continue
        command.status = CommandStatus.READY
        command.claim_owner = None
        command.lease_expires_at = None
        attempt.status = AttemptStatus.DISPATCH_PENDING
        attempt.state_version += 1
        await release_capacity(session, command_id)
        await session.commit()
        recovered += 1
    return recovered
