from types import SimpleNamespace

import pytest
from libtv_agent.adapters.kling_official_cli import KlingCliError
from libtv_agent.domain.enums import AttemptStatus, CommandStatus, GenerationStatus
from libtv_agent.domain.models import GenerationAttempt, GenerationVariant
from libtv_agent.runner.supervisor import RunnerSupervisor
from sqlalchemy import update
from test_image_quota_concurrency import world  # noqa: F401
from test_launch_started_recovery import _stranded_command


@pytest.mark.parametrize("query_error", [False, True])
@pytest.mark.parametrize("observation", ["terminal", "newer", "none"])
async def test_stale_poll_cannot_overwrite_terminal_observation(world, query_error, observation):  # noqa: F811
    app, factory, _, _ = world
    settings = app.state.settings.model_copy(update={"kling_cli_enabled": True})
    async with factory() as session:
        _, variant, attempt, command, _ = await _stranded_command(
            session, provider=settings.kling_cli_provider_name, lease_expires_at=None
        )
        attempt.status = AttemptStatus.RUNNING
        attempt.task_id = "original-provider-task"
        command.status = CommandStatus.PROCESS_STARTED
        await session.commit()
        attempt_id, variant_id = attempt.id, variant.id

    class Adapter:
        async def query(self, task_id):
            assert task_id == "original-provider-task"
            # Another observer commits a terminal result while this query is in flight.
            if observation != "none":
                async with factory() as other:
                    await other.execute(
                        update(GenerationAttempt)
                        .where(GenerationAttempt.id == attempt_id)
                        .values(
                            status=(
                                AttemptStatus.SUCCEEDED
                                if observation == "terminal"
                                else AttemptStatus.RUNNING
                            ),
                            provider_status="succeeded" if observation == "terminal" else "running",
                            raw_response_json={"newer": True},
                            state_version=GenerationAttempt.state_version + 1,
                        )
                    )
                    await other.execute(
                        update(GenerationVariant)
                        .where(GenerationVariant.id == variant_id)
                        .values(
                            generation_status=(
                                GenerationStatus.SUCCEEDED
                                if observation == "terminal"
                                else GenerationStatus.RUNNING
                            )
                        )
                    )
                    await other.commit()
            if query_error:
                raise KlingCliError("SYNTHETIC_QUERY_FAILED", "synthetic", retryable=False)
            return SimpleNamespace(
                status="running",
                raw_status="running",
                raw_response={"stale": True},
                credits_consumed=None,
            )

    supervisor = RunnerSupervisor(object(), object(), settings)
    supervisor._kling_adapters[settings.kling_cli_provider_name] = Adapter()
    async with factory() as polling:
        await supervisor.poll_kling_tasks(polling)
    async with factory() as verify:
        attempt = await verify.get(GenerationAttempt, attempt_id)
        variant = await verify.get(GenerationVariant, variant_id)
        if observation == "terminal":
            assert attempt.status == AttemptStatus.SUCCEEDED
            assert attempt.provider_status == "succeeded"
            assert attempt.raw_response_json == {"newer": True}
            assert variant.generation_status == GenerationStatus.SUCCEEDED
        elif observation == "newer":
            assert attempt.status == AttemptStatus.RUNNING
            assert attempt.provider_status == "running"
            assert attempt.raw_response_json == {"newer": True}
            assert variant.generation_status == GenerationStatus.RUNNING
        elif query_error:
            assert attempt.status == AttemptStatus.UNKNOWN_AFTER_SUBMIT
            assert attempt.provider_status == "unknown"
            assert variant.generation_status == GenerationStatus.UNKNOWN
        else:
            assert attempt.status == AttemptStatus.RUNNING
            assert attempt.provider_status == "running"
            assert attempt.raw_response_json == {"stale": True}
            assert variant.generation_status == GenerationStatus.RUNNING
