"""Aggregation must keep parent_task.phase and phase_reason_code in agreement.

Before this, _aggregate_task moved the phase and left the reason code alone, so a task
driven into ACTION_REQUIRED by a variant failure kept a NULL code. confirm_task's
recovery branch requires a non-empty code, so such tasks were silently unrecoverable
and the field told the operator nothing.

The naive fix -- write a code on entry and clear it on exit -- introduces a worse bug,
so these tests pin the exact policy: only the codes that actually gate recovery are
cleared, only on the way out of ACTION_REQUIRED, and codes the read model consumes are
never destroyed.
"""

import uuid

import pytest
from libtv_agent.config import Settings
from libtv_agent.domain.enums import (
    DownloadStatus,
    GenerationStatus,
    ParentTaskPhase,
    QualityDecisionStatus,
    ValidationStatus,
    VariantKind,
)
from libtv_agent.domain.models import Base, GenerationVariant, ParentTask
from libtv_agent.runner.supervisor import (
    AGGREGATED_ACTION_REQUIRED,
    RECOVERY_GATING_REASON_PREFIX,
    RunnerSupervisor,
    reason_code_for_aggregate,
)
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

MATERIALIZATION_CODE = f"{RECOVERY_GATING_REASON_PREFIX}INTERRUPTED"
PROVIDER_HINT_CODE = "BACH_ELEMENT_UNSUPPORTED"
BUSINESS_CODE = "POINTS_LIMIT_EXCEEDED"


@pytest.fixture
async def session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as value:
        yield value
    await engine.dispose()


def _supervisor() -> RunnerSupervisor:
    return RunnerSupervisor(None, None, Settings(_env_file=None))  # type: ignore[arg-type]


# ---------------------------------------------------------------- pure policy


@pytest.mark.parametrize("existing", [None, "", BUSINESS_CODE, PROVIDER_HINT_CODE])
def test_entering_action_required_always_leaves_a_usable_code(existing) -> None:
    # confirm_task refuses recovery on an empty code, so NULL/"" must not survive.
    result = reason_code_for_aggregate(
        existing, ParentTaskPhase.GENERATING, ParentTaskPhase.ACTION_REQUIRED
    )
    assert result, "aggregation left ACTION_REQUIRED without a reason code"
    assert result == (existing or AGGREGATED_ACTION_REQUIRED)


def test_business_reason_codes_are_not_overwritten() -> None:
    assert (
        reason_code_for_aggregate(
            BUSINESS_CODE, ParentTaskPhase.PREPARING, ParentTaskPhase.ACTION_REQUIRED
        )
        == BUSINESS_CODE
    )


def test_provider_hint_reason_codes_are_not_overwritten() -> None:
    # services.tasks._provider_for_read reads the BACH_/WAVESPEED_ prefixes to
    # attribute a Kling task to its sub-provider. Destroying these breaks the UI.
    assert (
        reason_code_for_aggregate(
            PROVIDER_HINT_CODE, ParentTaskPhase.GENERATING, ParentTaskPhase.ACTION_REQUIRED
        )
        == PROVIDER_HINT_CODE
    )


def test_leaving_action_required_clears_only_recovery_gating_codes() -> None:
    assert (
        reason_code_for_aggregate(
            MATERIALIZATION_CODE, ParentTaskPhase.ACTION_REQUIRED, ParentTaskPhase.GENERATING
        )
        is None
    )


def test_leaving_action_required_keeps_non_gating_codes() -> None:
    # BACH_* does not unlock recovery, so clearing it would only lose information.
    assert (
        reason_code_for_aggregate(
            PROVIDER_HINT_CODE, ParentTaskPhase.ACTION_REQUIRED, ParentTaskPhase.GENERATING
        )
        == PROVIDER_HINT_CODE
    )


def test_staying_in_action_required_keeps_the_original_cause() -> None:
    # Re-aggregating during the same failure must not relabel the cause.
    assert (
        reason_code_for_aggregate(
            MATERIALIZATION_CODE, ParentTaskPhase.ACTION_REQUIRED, ParentTaskPhase.ACTION_REQUIRED
        )
        == MATERIALIZATION_CODE
    )


def test_transitions_between_non_action_phases_leave_the_code_alone() -> None:
    for code in (None, BUSINESS_CODE, MATERIALIZATION_CODE, PROVIDER_HINT_CODE):
        assert (
            reason_code_for_aggregate(
                code, ParentTaskPhase.GENERATING, ParentTaskPhase.DELIVERABLE
            )
            == code
        )


# ---------------------------------------------------------------- integration


async def _task_with_variant(session, phase, reason_code, generation_status):
    task = ParentTask(
        user_id=uuid.uuid4(),
        client_task_id=f"client-{uuid.uuid4()}",
        title="task",
        asset_count=1,
        phase=phase,
        phase_reason_code=reason_code,
    )
    session.add(task)
    await session.flush()
    variant = GenerationVariant(
        parent_task_id=task.id,
        variant_type=VariantKind.STABLE,
        generation_status=generation_status,
        download_status=DownloadStatus.NOT_READY,
        validation_status=ValidationStatus.NOT_READY,
        final_approval_status=QualityDecisionStatus.PENDING,
    )
    session.add(variant)
    await session.commit()
    return task, variant


@pytest.mark.asyncio
async def test_aggregate_fills_reason_code_when_entering_action_required(session) -> None:
    task, variant = await _task_with_variant(
        session, ParentTaskPhase.GENERATING, None, GenerationStatus.FAILED
    )
    await _supervisor()._aggregate_task(session, variant.id)
    await session.refresh(task)
    assert task.phase is ParentTaskPhase.ACTION_REQUIRED
    assert task.phase_reason_code == AGGREGATED_ACTION_REQUIRED


@pytest.mark.asyncio
async def test_aggregate_clears_stale_recovery_code_when_leaving_action_required(session) -> None:
    task, variant = await _task_with_variant(
        session,
        ParentTaskPhase.ACTION_REQUIRED,
        MATERIALIZATION_CODE,
        GenerationStatus.RUNNING,
    )
    await _supervisor()._aggregate_task(session, variant.id)
    await session.refresh(task)
    assert task.phase is ParentTaskPhase.GENERATING
    assert task.phase_reason_code is None, (
        "a stale MATERIALIZATION_* code survived, which would offer recovery for a "
        "failure that has nothing to do with materialization"
    )


@pytest.mark.asyncio
async def test_aggregate_never_resurrects_a_cancelled_task(session) -> None:
    # resume_incomplete_downloads selects variants by download_status without
    # joining the task, so a cancelled task can still reach aggregation.
    task, variant = await _task_with_variant(
        session,
        ParentTaskPhase.CANCELLED,
        None,
        GenerationStatus.SUCCEEDED,
    )
    variant.download_status = DownloadStatus.READY
    variant.validation_status = ValidationStatus.PASSED
    variant.final_approval_status = QualityDecisionStatus.APPROVED
    await session.commit()
    before = task.state_version

    await _supervisor()._aggregate_task(session, variant.id)

    await session.refresh(task)
    assert task.phase is ParentTaskPhase.CANCELLED
    assert task.state_version == before


@pytest.mark.asyncio
async def test_aggregate_is_a_noop_when_the_phase_is_unchanged(session) -> None:
    task, variant = await _task_with_variant(
        session, ParentTaskPhase.GENERATING, None, GenerationStatus.RUNNING
    )
    before = task.state_version
    await _supervisor()._aggregate_task(session, variant.id)
    await session.refresh(task)
    assert task.phase is ParentTaskPhase.GENERATING
    assert task.state_version == before
    assert task.phase_reason_code is None
