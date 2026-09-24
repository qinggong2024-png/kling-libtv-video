from datetime import UTC, datetime, timedelta

from libtv_agent.domain.enums import CommandStatus
from libtv_agent.domain.models import GenerationAttempt, GenerationCommand
from sqlalchemy import update
from test_image_quota_concurrency import world  # noqa: F401
from test_launch_started_recovery import _stranded_command, _supervisor


async def test_launch_progress_after_recovery_scan_is_not_overwritten(world, tmp_path, monkeypatch):  # noqa: F811
    _, factory, _, _ = world
    async with factory() as seed:
        _, _, attempt, command, _ = await _stranded_command(
            seed,
            provider="kling_official_cli",
            lease_expires_at=datetime.now(UTC) - timedelta(days=1),
        )
        command_id, attempt_id = command.id, attempt.id
    async with factory() as recovery:
        original = recovery.scalars

        async def scan_then_complete(*args, **kwargs):
            result = await original(*args, **kwargs)
            ids = list(result)
            await recovery.commit()
            async with factory() as live:
                await live.execute(
                    update(GenerationCommand)
                    .where(GenerationCommand.id == command_id)
                    .values(status=CommandStatus.PROCESS_STARTED)
                )
                await live.execute(
                    update(GenerationAttempt)
                    .where(GenerationAttempt.id == attempt_id)
                    .values(task_id="synthetic-remote-handle")
                )
                await live.commit()
            return ids

        monkeypatch.setattr(recovery, "scalars", scan_then_complete)
        assert await _supervisor(tmp_path).recover_stale_launch_started_commands(recovery) == 0
    async with factory() as verify:
        assert (
            await verify.get(GenerationCommand, command_id)
        ).status == CommandStatus.PROCESS_STARTED
        assert (
            await verify.get(GenerationAttempt, attempt_id)
        ).task_id == "synthetic-remote-handle"
