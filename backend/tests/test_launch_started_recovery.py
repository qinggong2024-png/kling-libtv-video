"""A command abandoned between LAUNCH_STARTED and PROCESS_STARTED must be resolved.

Both _execute and _execute_kling commit LAUNCH_STARTED before handing the request to the
provider -- that commit is what survives a runner crash, because it is the point past
which the provider may already have spent the credit. The follow-up PROCESS_STARTED commit
then never happens, and before recover_stale_launch_started_commands existed nothing looked
at the command again:

* _run_ready_provider claims only CommandStatus.READY, never LAUNCH_STARTED
* observe_command_hosts scans only PROCESS_STARTED, and only for provider == "libtv"

Production held exactly one such row: command 7451a3e5..., attempt 39988a44... for
provider kling_official_cli, lease expired 2026-07-30 08:42 with process_started_at NULL.
It was invisible to every scan set in the runner -- a black hole that persisted for weeks.

The recovery verdict is submitted-and-uncertain, never a resubmit: the spend may already
have happened and there is no provider handle to query. These tests pin that verdict, pin
the guard that protects a merely slow-but-live launch, and pin the promise that recovery
never hands work back to the launch path.
"""

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from libtv_agent.config import Settings
from libtv_agent.domain.enums import (
    AttemptStatus,
    ChargeStatus,
    CommandStatus,
    GenerationStatus,
    LedgerEntryType,
    ParentTaskPhase,
    ReservationStatus,
    VariantKind,
)
from libtv_agent.domain.models import (
    Base,
    CapacitySlot,
    GenerationAttempt,
    GenerationCommand,
    GenerationVariant,
    ParentTask,
    PointsLedger,
    PointsReservation,
    User,
)
from libtv_agent.runner.supervisor import RunnerSupervisor
from libtv_agent.services.points import reserve_points
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

ESTIMATED_POINTS = 240
KLING_PROVIDER = "kling_official_cli"  # the provider of the production orphan
LIBTV_PROVIDER = "libtv"


@pytest.fixture
async def session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as value:
        yield value
    await engine.dispose()


def _settings(tmp_path) -> Settings:
    return Settings(
        app_env="test",
        libtv_adapter_mode="fake",
        runner_root=tmp_path / "runner",
        generation_estimated_points=ESTIMATED_POINTS,
        _env_file=None,
    )


class _Adapter:
    """Stands in for the provider adapter.

    Recovery must not call it. Any call is a test failure, because a call would re-submit
    work that may already have been paid for.
    """

    def __getattr__(self, name):  # pragma: no cover - defensive
        raise AssertionError(f"recovery must not touch the provider adapter ({name})")


def _supervisor(tmp_path) -> RunnerSupervisor:
    return RunnerSupervisor(_Adapter(), object(), _settings(tmp_path))


async def _stranded_command(
    session,
    *,
    provider: str,
    lease_expires_at: datetime | None,
    process_started_at: datetime | None = None,
):
    """Build the task/variant/attempt/command graph a crashed runner leaves behind.

    The attempt is pinned at LAUNCHING and works nothing was recorded against it -- that
    is precisely the shape of the production orphan.
    """
    user = User(
        id=uuid.uuid4(),
        username=f"launch-{uuid.uuid4().hex[:8]}",
        password_hash="disabled",
    )
    session.add(user)
    await session.flush()

    task = ParentTask(
        user_id=user.id,
        client_task_id=f"launch-{uuid.uuid4()}",
        title="stranded launch",
        asset_count=1,
        phase=ParentTaskPhase.GENERATING,
    )
    session.add(task)
    await session.flush()

    variant = GenerationVariant(
        parent_task_id=task.id,
        variant_type=VariantKind.STABLE,
        generation_config_json={},
        generation_status=GenerationStatus.RUNNING,
    )
    session.add(variant)
    await session.flush()

    attempt = GenerationAttempt(
        id=uuid.uuid4(),
        variant_id=variant.id,
        provider=provider,
        status=AttemptStatus.LAUNCHING,
        process_started_at=process_started_at,
    )
    session.add(attempt)
    await session.flush()

    command = GenerationCommand(
        id=uuid.uuid4(),
        attempt_id=attempt.id,
        status=CommandStatus.LAUNCH_STARTED,
        lease_expires_at=lease_expires_at,
    )
    session.add(command)
    await session.flush()

    reservation = await reserve_points(
        session,
        user_id=user.id,
        attempt_id=attempt.id,
        estimated_points=ESTIMATED_POINTS,
        daily_limit=5000,
    )
    await session.commit()
    return task, variant, attempt, command, reservation


async def _reload(session, obj):
    await session.refresh(obj)
    return obj


@pytest.mark.asyncio
async def test_abandoned_launch_is_resolved_as_submitted_and_uncertain(session, tmp_path):
    """The production orphan: kling command, dead lease, no process_started_at."""
    _, variant, attempt, command, reservation = await _stranded_command(
        session,
        provider=KLING_PROVIDER,
        lease_expires_at=datetime.now(UTC) - timedelta(weeks=7),
    )
    supervisor = _supervisor(tmp_path)

    assert await supervisor.recover_stale_launch_started_commands(session) == 1

    assert command.status == CommandStatus.UNCERTAIN
    assert command.lease_expires_at is None
    assert attempt.status == AttemptStatus.UNKNOWN_AFTER_SUBMIT
    assert attempt.charge_status == ChargeStatus.UNKNOWN
    assert variant.generation_status == GenerationStatus.UNKNOWN

    # The money question: an unattributable spend parks as UNCERTAIN, it is never
    # written off as "not charged". Recording a RELEASE here would silently forgive a
    # charge the provider may have taken.
    assert reservation.status == ReservationStatus.UNCERTAIN
    assert reservation.charge_status == ChargeStatus.UNKNOWN
    # reserve_points already wrote the RESERVE entry; recovery must add exactly one
    # UNCERTAIN entry and must not write a RELEASE.
    entries = list(await session.scalars(select(PointsLedger)))
    assert [e.entry_type for e in entries] == [
        LedgerEntryType.RESERVE,
        LedgerEntryType.UNCERTAIN,
    ]
    assert entries[-1].points == ESTIMATED_POINTS


@pytest.mark.asyncio
async def test_libtv_launch_is_recovered_too(session, tmp_path):
    """The old scan sets were provider-filtered; the black hole was not libtv-only.

    observe_command_hosts restricts itself to PROCESS_STARTED *and* provider == "libtv",
    so a stranded libtv command was missed for two independent reasons.
    """
    _, _, attempt, command, _ = await _stranded_command(
        session,
        provider=LIBTV_PROVIDER,
        lease_expires_at=datetime.now(UTC) - timedelta(weeks=7),
    )
    supervisor = _supervisor(tmp_path)

    assert await supervisor.recover_stale_launch_started_commands(session) == 1
    assert command.status == CommandStatus.UNCERTAIN
    assert attempt.status == AttemptStatus.UNKNOWN_AFTER_SUBMIT


@pytest.mark.asyncio
async def test_live_lease_is_left_alone(session, tmp_path):
    """A launch still inside its lease is in flight right now, not abandoned."""
    _, _, attempt, command, reservation = await _stranded_command(
        session,
        provider=KLING_PROVIDER,
        lease_expires_at=datetime.now(UTC) + timedelta(seconds=60),
    )
    supervisor = _supervisor(tmp_path)

    assert await supervisor.recover_stale_launch_started_commands(session) == 0

    assert command.status == CommandStatus.LAUNCH_STARTED
    assert command.lease_expires_at is not None
    assert attempt.status == AttemptStatus.LAUNCHING
    # The column default, i.e. untouched by the sweep.
    assert attempt.charge_status == ChargeStatus.NOT_CHARGED
    assert reservation.status == ReservationStatus.RESERVED


@pytest.mark.asyncio
async def test_expiry_inside_grace_period_is_left_alone(session, tmp_path):
    """The lease is a heartbeat, not a hard deadline.

    A process that is slow to reach PROCESS_STARTED outlives the 60-second lease it was
    granted. Acting the moment the lease lapses would mark a perfectly healthy in-flight
    launch as abandoned, so there is a grace window before recovery engages.
    """
    _, _, attempt, command, _ = await _stranded_command(
        session,
        provider=KLING_PROVIDER,
        lease_expires_at=datetime.now(UTC) - timedelta(minutes=1),
    )
    supervisor = _supervisor(tmp_path)

    assert await supervisor.recover_stale_launch_started_commands(session) == 0
    assert command.status == CommandStatus.LAUNCH_STARTED
    assert attempt.status == AttemptStatus.LAUNCHING


@pytest.mark.asyncio
async def test_null_lease_is_never_stale(session, tmp_path):
    """No lease means no claim was ever staked, so there is nothing to time out."""
    _, _, _, command, _ = await _stranded_command(
        session,
        provider=KLING_PROVIDER,
        lease_expires_at=None,
    )
    supervisor = _supervisor(tmp_path)

    assert await supervisor.recover_stale_launch_started_commands(session) == 0
    assert command.status == CommandStatus.LAUNCH_STARTED


@pytest.mark.asyncio
async def test_recovery_never_resubmits(session, tmp_path, monkeypatch):
    """The one thing recovery must never do.

    A restart would re-issue a request the provider may already have accepted and charged
    for. Both launch entry points are booby-trapped: reaching either one fails the test.
    """
    _, _, attempt, _, _ = await _stranded_command(
        session,
        provider=KLING_PROVIDER,
        lease_expires_at=datetime.now(UTC) - timedelta(weeks=7),
    )

    def _explode(*args, **kwargs):
        raise AssertionError("recovery re-submitted work to the provider")

    monkeypatch.setattr(RunnerSupervisor, "_execute", _explode)
    monkeypatch.setattr(RunnerSupervisor, "_execute_kling", _explode)
    supervisor = _supervisor(tmp_path)

    assert await supervisor.recover_stale_launch_started_commands(session) == 1

    # Resolution must not leave anything in a state the launch path would pick up.
    commands = list(await session.scalars(select(GenerationCommand)))
    assert [c.status for c in commands] == [CommandStatus.UNCERTAIN]
    assert attempt.status != AttemptStatus.LAUNCHING


@pytest.mark.asyncio
async def test_recovery_is_idempotent(session, tmp_path):
    """Running the sweep on every poll must not re-resolve or re-settle anything."""
    _, _, _, command, _ = await _stranded_command(
        session,
        provider=KLING_PROVIDER,
        lease_expires_at=datetime.now(UTC) - timedelta(weeks=7),
    )
    supervisor = _supervisor(tmp_path)

    assert await supervisor.recover_stale_launch_started_commands(session) == 1
    assert await supervisor.recover_stale_launch_started_commands(session) == 0

    assert command.status == CommandStatus.UNCERTAIN
    # One UNCERTAIN entry, not one per sweep.
    entries = list(
        await session.scalars(
            select(PointsLedger).where(PointsLedger.entry_type == LedgerEntryType.UNCERTAIN)
        )
    )
    assert len(entries) == 1


@pytest.mark.asyncio
async def test_other_command_states_are_untouched(session, tmp_path):
    """Only LAUNCH_STARTED is in scope; the other scan sets already own their states."""
    user = User(id=uuid.uuid4(), username="scope", password_hash="disabled")
    session.add(user)
    await session.flush()
    task = ParentTask(
        user_id=user.id,
        client_task_id="scope",
        title="scope",
        asset_count=1,
        phase=ParentTaskPhase.GENERATING,
    )
    session.add(task)
    await session.flush()
    variant = GenerationVariant(
        parent_task_id=task.id,
        variant_type=VariantKind.STABLE,
        generation_config_json={},
    )
    session.add(variant)
    await session.flush()

    stale = datetime.now(UTC) - timedelta(weeks=7)
    by_status = {}
    for status in (
        CommandStatus.READY,
        CommandStatus.CLAIMED,
        CommandStatus.PROCESS_STARTED,
        CommandStatus.TERMINAL,
        CommandStatus.UNCERTAIN,
        CommandStatus.CANCELLED,
    ):
        attempt = GenerationAttempt(
            id=uuid.uuid4(),
            variant_id=variant.id,
            provider=KLING_PROVIDER,
            status=AttemptStatus.LAUNCHING,
        )
        session.add(attempt)
        await session.flush()
        command = GenerationCommand(
            id=uuid.uuid4(),
            attempt_id=attempt.id,
            status=status,
            lease_expires_at=stale,  # equally stale, still out of scope
        )
        session.add(command)
        by_status[status] = command
    await session.commit()

    supervisor = _supervisor(tmp_path)
    assert await supervisor.recover_stale_launch_started_commands(session) == 0

    for status, command in by_status.items():
        assert command.status == status, f"{status} was rewritten by the sweep"


@pytest.mark.asyncio
async def test_kling_releases_its_capacity_slot(session, tmp_path):
    """Kling slots are released unconditionally, matching _handle_error's callers."""
    _, _, _, command, _ = await _stranded_command(
        session,
        provider=KLING_PROVIDER,
        lease_expires_at=datetime.now(UTC) - timedelta(weeks=7),
    )
    slot = CapacitySlot(
        scope_type="provider",
        scope_id="provider:kling",
        slot_no=1,
        command_id=command.id,
        lease_expires_at=datetime.now(UTC) - timedelta(weeks=7),
    )
    session.add(slot)
    await session.commit()

    supervisor = _supervisor(tmp_path)
    assert await supervisor.recover_stale_launch_started_commands(session) == 1

    await session.refresh(slot)
    assert slot.command_id is None
    assert slot.lease_expires_at is None


@pytest.mark.asyncio
async def test_libtv_keeps_capacity_while_the_charge_is_unknown(session, tmp_path):
    """A libtv slot is only freed once the charge is attributed.

    The slot is the concurrency budget. Releasing it while the charge is still unknown
    would let the task relaunch and spend a second time on top of an unresolved first
    charge.
    """
    _, _, _, command, _ = await _stranded_command(
        session,
        provider=LIBTV_PROVIDER,
        lease_expires_at=datetime.now(UTC) - timedelta(weeks=7),
    )
    slot = CapacitySlot(
        scope_type="provider",
        scope_id="provider:libtv",
        slot_no=1,
        command_id=command.id,
        lease_expires_at=datetime.now(UTC) - timedelta(weeks=7),
    )
    session.add(slot)
    await session.commit()

    supervisor = _supervisor(tmp_path)
    assert await supervisor.recover_stale_launch_started_commands(session) == 1

    await session.refresh(slot)
    assert slot.command_id == command.id, "capacity must survive an unattributed charge"


@pytest.mark.asyncio
async def test_command_without_attempt_is_skipped(session, tmp_path):
    """A dangling attempt_id must not abort the sweep for every other row."""
    _, _, attempt, _, _ = await _stranded_command(
        session,
        provider=KLING_PROVIDER,
        lease_expires_at=datetime.now(UTC) - timedelta(weeks=7),
    )
    session.add(
        GenerationCommand(
            id=uuid.uuid4(),
            attempt_id=uuid.uuid4(),  # no such attempt
            status=CommandStatus.LAUNCH_STARTED,
            lease_expires_at=datetime.now(UTC) - timedelta(weeks=7),
        )
    )
    await session.commit()

    supervisor = _supervisor(tmp_path)
    assert await supervisor.recover_stale_launch_started_commands(session) == 1
    assert attempt.status == AttemptStatus.UNKNOWN_AFTER_SUBMIT


@pytest.mark.asyncio
async def test_recovered_charge_is_reconcilable_not_lost(session, tmp_path):
    """Recovery must leave a receivable trail, not merely a silent state change.

    The point of resolving the black hole is that the charge becomes visible to the
    reconciliation backlog, so an operator can decide whether the provider really charged.
    """
    _, _, attempt, _, reservation = await _stranded_command(
        session,
        provider=KLING_PROVIDER,
        lease_expires_at=datetime.now(UTC) - timedelta(weeks=7),
    )
    supervisor = _supervisor(tmp_path)
    await supervisor.recover_stale_launch_started_commands(session)

    # Both provider branches route through record_provider_error, so the operator sees the
    # reason on the attempt as well as in the ledger.
    assert attempt.last_error_code == "LAUNCH_ABANDONED"
    assert reservation.settled_at is not None
    assert reservation.actual_points is None
    assert (
        await session.scalar(
            select(PointsReservation).where(
                PointsReservation.status == ReservationStatus.UNCERTAIN
            )
        )
        is not None
    )
