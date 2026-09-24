"""Isolated video launch crash drill.

The submit worker commits LAUNCH_STARTED and then blocks inside a synthetic provider.
The caller terminates that process.  The recover worker opens the same SQLite database,
resolves the expired launch exactly once, and verifies that no provider call is repeated.
This deliberately exercises the real RunnerSupervisor video launch path without paid API
credentials or external network access.
"""

import asyncio
import json
import os
import pathlib
import platform
import stat
import sys
from datetime import UTC, datetime, timedelta

SOURCE = pathlib.Path(__file__).resolve().parents[1]
ROOT = pathlib.Path(sys.argv[1]).resolve()
MODE = sys.argv[2]
if MODE not in {"submit", "recover"} or not ROOT.is_dir():
    raise SystemExit("Expected an existing isolated directory and submit/recover mode")
if any(
    p.lstat().st_file_attributes & stat.FILE_ATTRIBUTE_REPARSE_POINT
    for p in (ROOT, *ROOT.parents)
):
    raise SystemExit("Reparse points are forbidden")
for key in list(os.environ):
    if key.upper() not in {"SYSTEMROOT", "WINDIR", "PATH", "PATHEXT", "COMSPEC"}:
        del os.environ[key]
os.environ.update(APP_ENV="test", USERPROFILE=str(ROOT), TEMP=str(ROOT), TMP=str(ROOT))
os.chdir(ROOT)
sys.dont_write_bytecode = True
sys.path[:0] = [str(SOURCE / "backend/src")]
platform.uname()


def audit(event, args):
    if event == "socket.connect":
        if sys._getframe(1).f_code.co_name != "_fallback_socketpair":
            raise RuntimeError("External network is forbidden")
    if event in {"subprocess.Popen", "os.system"}:
        raise RuntimeError("Child processes are forbidden")
    if event == "open" and isinstance(args[0], (str, bytes)):
        path = pathlib.Path(os.fsdecode(args[0])).resolve()
        if path.name == ".env" or "libtv-production" in path.parts:
            raise RuntimeError("Production access is forbidden")
        writing = any(c in (args[1] or "") for c in "wax+") or (args[2] or 0) & (
            os.O_WRONLY | os.O_RDWR
        )
        if writing and not path.is_relative_to(ROOT) and "site-packages" not in path.parts:
            raise RuntimeError("Write outside isolated root")


sys.addaudithook(audit)


class BlockingProvider:
    """Provider that records entry, then waits until the worker is killed."""

    def __init__(self):
        self.calls = 0

    def get_provider_name(self):
        return "kling_official_api"

    async def check_availability(self):
        from libtv_agent.adapters.video_provider import ProviderAvailability

        return ProviderAvailability("AVAILABLE", True, True)

    async def refresh_capabilities(self, *, force=False):
        raise AssertionError("capability refresh is outside this drill")

    async def validate_request(self, request):
        return request.model or "kling-3.0"

    async def submit(self, request):
        self.calls += 1
        (ROOT / "provider-accepted.json").write_text(
            json.dumps({"calls": self.calls, "pid": os.getpid()})
        )
        (ROOT / "provider-entered.json").write_text(json.dumps({"pid": os.getpid()}))
        await asyncio.Event().wait()

    async def query(self, provider_task_id):
        raise AssertionError("recovery must not query without a provider handle")

    async def download(self, output, destination):
        raise AssertionError("download is outside this drill")

    async def get_account_status(self):
        return {}


class IsolatedObjectStore:
    async def localize(self, object_key, destination):
        return ROOT / "source.png"


async def main():
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
        Asset,
        Base,
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

    database = ROOT / "video-crash.db"
    if MODE == "submit" and database.exists():
        raise RuntimeError("Fresh directory required")
    if MODE == "recover" and not database.exists():
        raise RuntimeError("Missing persisted database")
    engine = create_async_engine(f"sqlite+aiosqlite:///{database.as_posix()}")
    factory = async_sessionmaker(engine, expire_on_commit=False)
    settings = Settings(
        _env_file=None,
        app_env="test",
        runner_root=ROOT / "runner",
        artifact_root=ROOT / "artifacts",
        kling_provider_backend="api",
        kling_api_enabled=True,
        kling_api_key="synthetic-only",
        paid_submissions_paused=False,
        generation_estimated_points=240,
        daily_user_points_limit=5000,
    )
    provider = BlockingProvider()
    (ROOT / "source.png").write_bytes(b"synthetic image")
    supervisor = RunnerSupervisor(
        object(), IsolatedObjectStore(), settings, kling_adapter=provider
    )
    try:
        if MODE == "submit":
            async with engine.begin() as connection:
                await connection.run_sync(Base.metadata.create_all)
            async with factory() as session:
                user = User(username="synthetic-video", password_hash="disabled")
                session.add(user)
                await session.flush()
                task = ParentTask(
                    user_id=user.id,
                    client_task_id="video-crash",
                    title="synthetic video crash",
                    asset_count=1,
                    phase=ParentTaskPhase.QUEUED,
                )
                session.add(task)
                await session.flush()
                asset = Asset(
                    parent_task_id=task.id,
                    order_no=1,
                    role="STORYBOARD",
                    original_filename="source.png",
                    sha256="a" * 64,
                    mime_type="image/png",
                    size_bytes=100,
                    width=128,
                    height=128,
                    object_key="source.png",
                    used_for_generation=True,
                )
                variant = GenerationVariant(
                    parent_task_id=task.id,
                    variant_type=VariantKind.STABLE,
                    prompt_text="synthetic crash drill",
                    generation_config_json={"model": "kling-3.0"},
                    generation_status=GenerationStatus.PENDING,
                )
                session.add_all([asset, variant])
                await session.flush()
                attempt = GenerationAttempt(
                    variant_id=variant.id,
                    provider=settings.kling_api_provider_name,
                    provider_model="kling-3.0",
                    intent_hash="b" * 64,
                    status=AttemptStatus.DISPATCH_PENDING,
                )
                session.add(attempt)
                await session.flush()
                await reserve_points(
                    session,
                    user_id=user.id,
                    attempt_id=attempt.id,
                    estimated_points=settings.generation_estimated_points,
                    daily_limit=settings.daily_user_points_limit,
                )
                command = GenerationCommand(
                    attempt_id=attempt.id,
                    status=CommandStatus.READY,
                    command_manifest_json={"provider": settings.kling_api_provider_name},
                )
                session.add(command)
                await session.commit()
                (ROOT / "ready.json").write_text(
                    json.dumps({"task_id": str(task.id), "command_id": str(command.id)})
                )
                await supervisor._execute(session, command.id)
        else:
            async with factory() as session:
                command = await session.scalar(select(GenerationCommand))
                attempt = await session.scalar(select(GenerationAttempt))
                if command is None or attempt is None:
                    raise RuntimeError("persisted launch fixture is missing")
                command.lease_expires_at = datetime.now(UTC) - timedelta(hours=1)
                await session.commit()
                first = await supervisor.recover_stale_launch_started_commands(session)
                second = await supervisor.recover_stale_launch_started_commands(session)
                await session.refresh(command)
                await session.refresh(attempt)
                reservation = await session.scalar(select(PointsReservation))
                entries = list(await session.scalars(select(PointsLedger)))
                assert first == 1 and second == 0
                assert command.status == CommandStatus.UNCERTAIN
                assert attempt.status == AttemptStatus.UNKNOWN_AFTER_SUBMIT
                assert attempt.charge_status == ChargeStatus.UNKNOWN
                assert reservation is not None and reservation.status == ReservationStatus.UNCERTAIN
                assert sorted(e.entry_type for e in entries) == sorted(
                    [LedgerEntryType.RESERVE, LedgerEntryType.UNCERTAIN]
                )
                assert not (ROOT / "provider-retry.json").exists()
                (ROOT / "result.json").write_text(
                    json.dumps(
                        {
                            "pid": os.getpid(),
                            "recovery_counts": [first, second],
                            "command": command.status.value,
                            "attempt": attempt.status.value,
                            "charge_status": attempt.charge_status.value,
                            "reservation": reservation.status.value,
                            "ledger": [e.entry_type.value for e in entries],
                            "provider_calls_after_restart": 0,
                            "scope": "video provider launch entered, process killed, no resubmit",
                        },
                        indent=2,
                    )
                )
    finally:
        await engine.dispose()


asyncio.run(main())
