"""Every exit from _handle_success must settle the attempt's points reservation.

Settlement used to sit on the last line of _handle_success, so four earlier returns
skipped it entirely: a missing variant, a missing task, an artifact that was already
READY, and a failed download. Production recorded the consequence -- 24 of 42
successful attempts held UNCERTAIN reservations worth 2880 points and the ledger
contained zero RELEASE entries -- so each of those paths is driven here and asserted to
reach a decision.

The charge verdict is delegated to attempt.charge_status, so these tests also pin the
three outcomes: an attributable libtv spend settles, an unreadable receipt parks as
UNCERTAIN rather than being recorded as "not charged", and a repeated call is a no-op.
"""

import uuid
from types import SimpleNamespace

import pytest
from libtv_agent.adapters.libtv import GenerationResult
from libtv_agent.config import Settings
from libtv_agent.domain.enums import (
    AttemptStatus,
    ChargeStatus,
    CommandStatus,
    DownloadStatus,
    ParentTaskPhase,
    ReservationStatus,
    VariantKind,
)
from libtv_agent.domain.models import (
    Base,
    DownloadArtifact,
    GenerationAttempt,
    GenerationCommand,
    GenerationVariant,
    ParentTask,
    PointsReservation,
    User,
)
from libtv_agent.runner.supervisor import RunnerSupervisor
from libtv_agent.services.points import reserve_points
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

ESTIMATED_POINTS = 120
PROVIDER = "libtv"
VIDEO_URL = "http://provider.invalid/clip.mp4"


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


async def _world(
    session,
    *,
    with_task: bool = True,
    with_variant: bool = True,
    provider: str = PROVIDER,
    credits_consumed: int | None = None,
):
    """Build a task/variant/attempt/command/reservation graph.

    set with_variant=False to leave attempt.variant_id dangling, with_task=False to
    leave variant.parent_task_id dangling.
    """
    user = User(
        id=uuid.uuid4(),
        username=f"settle-{uuid.uuid4().hex[:8]}",
        password_hash="disabled",
    )
    session.add(user)
    await session.flush()

    task = None
    if with_task:
        task = ParentTask(
            user_id=user.id,
            client_task_id=f"settle-{uuid.uuid4()}",
            title="settle",
            asset_count=1,
            phase=ParentTaskPhase.GENERATING,
        )
        session.add(task)
        await session.flush()

    variant = None
    variant_id = uuid.uuid4()
    if with_variant:
        variant = GenerationVariant(
            id=variant_id,
            parent_task_id=task.id if task is not None else uuid.uuid4(),
            variant_type=VariantKind.STABLE,
            generation_config_json={},
        )
        session.add(variant)
        await session.flush()

    attempt = GenerationAttempt(
        id=uuid.uuid4(),
        variant_id=variant_id,
        provider=provider,
        status=AttemptStatus.LAUNCHING,
        credits_consumed=credits_consumed,
    )
    session.add(attempt)
    await session.flush()

    command = GenerationCommand(
        id=uuid.uuid4(),
        attempt_id=attempt.id,
        status=CommandStatus.LAUNCH_STARTED,
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


async def _reservation(session, attempt) -> PointsReservation:
    return await session.scalar(
        select(PointsReservation).where(PointsReservation.attempt_id == attempt.id)
    )


def _result() -> GenerationResult:
    return GenerationResult(
        status="SUCCEEDED",
        payload={"taskId": "provider-task", "videoUrl": VIDEO_URL},
    )


async def _run(session, settings, task, attempt, command, *, variant, tmp_path):
    supervisor = RunnerSupervisor(None, None, settings)  # type: ignore[arg-type]
    await supervisor._handle_success(session, command, attempt, _result())
    return supervisor


# ---------------------------------------------------------------- previously dark paths


@pytest.mark.asyncio
async def test_settles_when_the_variant_is_missing(session, tmp_path) -> None:
    task, _variant, attempt, command, reservation = await _world(session, with_variant=False)
    assert await session.get(GenerationVariant, attempt.variant_id) is None

    await _run(
        session, _settings(tmp_path), task, attempt, command, variant=None, tmp_path=tmp_path
    )

    fresh = await _reservation(session, attempt)
    assert fresh.status is ReservationStatus.SETTLED, (
        "a successful attempt whose variant is missing left the points reserved forever"
    )


@pytest.mark.asyncio
async def test_settles_when_the_task_is_missing(session, tmp_path) -> None:
    task, variant, attempt, command, reservation = await _world(session, with_task=False)
    assert await session.get(ParentTask, variant.parent_task_id) is None

    await _run(
        session, _settings(tmp_path), task, attempt, command, variant=variant, tmp_path=tmp_path
    )

    fresh = await _reservation(session, attempt)
    assert fresh.status is ReservationStatus.SETTLED


@pytest.mark.asyncio
async def test_settles_when_a_ready_artifact_already_exists(session, tmp_path) -> None:
    task, variant, attempt, command, reservation = await _world(session)
    session.add(
        DownloadArtifact(
            attempt_id=attempt.id,
            status=DownloadStatus.READY,
            object_key=f"users/x/outputs/{task.id}/clip.mp4",
            revision=1,
        )
    )
    await session.commit()

    await _run(
        session, _settings(tmp_path), task, attempt, command, variant=variant, tmp_path=tmp_path
    )

    fresh = await _reservation(session, attempt)
    assert fresh.status is ReservationStatus.SETTLED, (
        "the already-downloaded path returned without settling"
    )
    refreshed_variant = await session.get(GenerationVariant, variant.id)
    assert refreshed_variant.download_status is DownloadStatus.READY


@pytest.mark.asyncio
async def test_settles_when_the_download_fails(session, tmp_path, monkeypatch) -> None:
    async def boom(*args, **kwargs):
        raise RuntimeError("provider url unreachable")

    monkeypatch.setattr("libtv_agent.runner.supervisor.download_with_retries", boom)
    task, variant, attempt, command, reservation = await _world(session)
    settings = _settings(tmp_path)

    supervisor = RunnerSupervisor(None, None, settings)  # type: ignore[arg-type]
    await supervisor._handle_success(session, command, attempt, _result())

    fresh = await _reservation(session, attempt)
    assert fresh.status is ReservationStatus.SETTLED, (
        "an upstream success whose download failed left the points reserved"
    )
    refreshed_variant = await session.get(GenerationVariant, variant.id)
    assert refreshed_variant.download_status is DownloadStatus.FAILED
    assert attempt.last_error_code == "DOWNLOAD_RETRYABLE"
    assert attempt.charge_status is ChargeStatus.CHARGED


# ---------------------------------------------------------------- the happy path


@pytest.mark.asyncio
async def test_happy_path_settles_exactly_once(session, tmp_path, monkeypatch) -> None:
    async def fake_download(*args, **kwargs):
        return None

    async def fake_validate(*args, **kwargs):
        return SimpleNamespace(
            sha256="a" * 64,
            size_bytes=1024,
            duration_seconds=5.0,
            width=1080,
            height=1920,
            has_audio=True,
            passed=True,
            issue_codes=(),
        )

    monkeypatch.setattr("libtv_agent.runner.supervisor.download_with_retries", fake_download)
    monkeypatch.setattr("libtv_agent.runner.supervisor.technical_validate", fake_validate)

    store = SimpleNamespace(
        put_file=_async_returning("users/x/outputs/clip.mp4"),
    )
    task, variant, attempt, command, reservation = await _world(session)
    settings = _settings(tmp_path)
    supervisor = RunnerSupervisor(None, store, settings)  # type: ignore[arg-type]

    await supervisor._handle_success(session, command, attempt, _result())

    fresh = await _reservation(session, attempt)
    assert fresh.status is ReservationStatus.SETTLED
    assert fresh.actual_points == ESTIMATED_POINTS
    assert fresh.settled_at is not None

    # Ledger must show exactly one CONSUME and one RESERVE for this attempt.
    from libtv_agent.domain.models import PointsLedger

    counts = dict(
        (
            await session.execute(
                select(PointsLedger.entry_type, func.count())
                .where(PointsLedger.attempt_id == attempt.id)
                .group_by(PointsLedger.entry_type)
            )
        ).all()
    )
    assert sum(counts.values()) == 2, f"expected exactly one RESERVE and one settle, got {counts}"


def _async_returning(value):
    async def inner(*args, **kwargs):
        return value

    return inner


@pytest.mark.asyncio
async def test_settlement_is_idempotent_across_repeated_calls(
    session, tmp_path, monkeypatch
) -> None:
    async def fake_download(*args, **kwargs):
        return None

    async def fake_validate(*args, **kwargs):
        return SimpleNamespace(
            sha256="b" * 64,
            size_bytes=1024,
            duration_seconds=5.0,
            width=1080,
            height=1920,
            has_audio=True,
            passed=True,
            issue_codes=(),
        )

    monkeypatch.setattr("libtv_agent.runner.supervisor.download_with_retries", fake_download)
    monkeypatch.setattr("libtv_agent.runner.supervisor.technical_validate", fake_validate)
    store = SimpleNamespace(put_file=_async_returning("k"))

    task, variant, attempt, command, reservation = await _world(session)
    settings = _settings(tmp_path)
    supervisor = RunnerSupervisor(None, store, settings)  # type: ignore[arg-type]

    await supervisor._handle_success(session, command, attempt, _result())
    first = await _reservation(session, attempt)
    first_points = first.actual_points

    # A second delivery of the same attempt (recovery, resume, duplicate callback) must
    # not consume twice. settle_points guards on reservation.status.
    await supervisor._finalize_attempt_billing(
        session, attempt, actual_points=None, has_attributable_billing=True
    )
    await session.commit()

    again = await _reservation(session, attempt)
    assert again.status is ReservationStatus.SETTLED
    assert again.actual_points == first_points


# ---------------------------------------------------------------- charge verdict


@pytest.mark.asyncio
async def test_unreadable_receipt_parks_the_reservation_as_uncertain(
    session, tmp_path, monkeypatch
) -> None:
    async def fake_download(*args, **kwargs):
        return None

    async def fake_validate(*args, **kwargs):
        return SimpleNamespace(
            sha256="c" * 64,
            size_bytes=1,
            duration_seconds=1.0,
            width=1,
            height=1,
            has_audio=False,
            passed=True,
            issue_codes=(),
        )

    monkeypatch.setattr("libtv_agent.runner.supervisor.download_with_retries", fake_download)
    monkeypatch.setattr("libtv_agent.runner.supervisor.technical_validate", fake_validate)
    store = SimpleNamespace(put_file=_async_returning("k"))

    # A non-libtv provider with no reported credit usage cannot be attributed.
    task, variant, attempt, command, reservation = await _world(
        session, provider="kling-waveSpeed", credits_consumed=None
    )
    settings = _settings(tmp_path)
    supervisor = RunnerSupervisor(None, store, settings)  # type: ignore[arg-type]

    await supervisor._handle_success(session, command, attempt, _result())

    assert attempt.charge_status is ChargeStatus.UNKNOWN
    fresh = await _reservation(session, attempt)
    assert fresh.status is ReservationStatus.UNCERTAIN, (
        "an unattributable spend must be parked as UNCERTAIN, never recorded as not charged"
    )
