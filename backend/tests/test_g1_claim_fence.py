from datetime import UTC, datetime, timedelta

import pytest
from libtv_agent.domain.enums import AttemptStatus, CommandStatus, ReservationStatus
from libtv_agent.domain.models import GenerationCommand, PointsReservation
from libtv_agent.runner.launch_recovery import recover_abandoned_claims
from sqlalchemy import update
from test_image_quota_concurrency import world  # noqa: F401
from test_launch_started_recovery import _stranded_command, _supervisor


@pytest.mark.parametrize("changed", [False, True])
async def test_prelaunch_fence_checks_persisted_claim(world, tmp_path, changed):  # noqa: F811
    _, factory, _, _ = world
    async with factory() as setup:
        _, _, _, command, _ = await _stranded_command(
            setup,
            provider="kling_official_api",
            lease_expires_at=datetime.now(UTC) + timedelta(minutes=1),
        )
        command.status = CommandStatus.CLAIMED
        command.claim_owner = "old-owner"
        await setup.commit()
        command_id = command.id
    async with factory() as old:
        command = await old.get(GenerationCommand, command_id)
        if changed:
            async with factory() as newer:
                await newer.execute(
                    update(GenerationCommand)
                    .where(GenerationCommand.id == command_id)
                    .values(claim_owner="new-owner")
                )
                await newer.commit()
        supervisor = _supervisor(tmp_path)
        supervisor.owner = "old-owner"
        assert await supervisor._guard_command(old, command, launching=True) is not changed
        await old.commit()
    async with factory() as verify:
        command = await verify.get(GenerationCommand, command_id)
        assert command.status == (
            CommandStatus.CLAIMED if changed else CommandStatus.LAUNCH_STARTED
        )
        assert command.claim_owner == ("new-owner" if changed else "old-owner")


async def test_expired_claim_recovers_once_and_fences_old_snapshot(world, tmp_path):  # noqa: F811
    _, factory, _, _ = world
    async with factory() as setup:
        _, _, attempt, command, reservation = await _stranded_command(
            setup,
            provider="kling_official_api",
            lease_expires_at=datetime.now(UTC) - timedelta(hours=1),
        )
        command.status = CommandStatus.CLAIMED
        command.claim_owner = "old"
        await setup.commit()
        command_id, reservation_id = command.id, reservation.id
    async with factory() as old:
        stale = await old.get(GenerationCommand, command_id)
        async with factory() as recovery:
            assert await recover_abandoned_claims(recovery) == 1
            assert await recover_abandoned_claims(recovery) == 0
        supervisor = _supervisor(tmp_path)
        supervisor.owner = "old"
        assert not await supervisor._guard_command(old, stale, launching=True)
    async with factory() as verify:
        command = await verify.get(GenerationCommand, command_id)
        assert command.status == CommandStatus.READY
        from libtv_agent.domain.models import GenerationAttempt

        attempt = await verify.get(GenerationAttempt, command.attempt_id)
        assert attempt.status == AttemptStatus.DISPATCH_PENDING
        reservation = await verify.get(PointsReservation, reservation_id)
        assert reservation.status == ReservationStatus.RESERVED
