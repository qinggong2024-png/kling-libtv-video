"""Isolated crash drill worker; launch seed, terminate it, then launch recover."""

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
if MODE not in {"seed", "recover"} or not ROOT.is_dir():
    raise SystemExit("Expected an existing isolated directory and seed/recover mode")
if not (SOURCE / "backend/tests/test_launch_started_recovery.py").is_file():
    raise SystemExit("This branch lacks the launch recovery fixture; drill is unsupported")
if any(
    p.lstat().st_file_attributes & stat.FILE_ATTRIBUTE_REPARSE_POINT
    for p in (ROOT, *ROOT.parents)
):
    raise SystemExit("Links are forbidden")
for key in list(os.environ):
    if key.upper() not in {"SYSTEMROOT", "WINDIR", "PATH", "PATHEXT", "COMSPEC"}:
        del os.environ[key]
os.environ.update(APP_ENV="test", USERPROFILE=str(ROOT), TEMP=str(ROOT), TMP=str(ROOT))
os.chdir(ROOT)
sys.dont_write_bytecode = True
sys.path[:0] = [str(SOURCE / "backend/src"), str(SOURCE / "backend/tests")]
platform.uname()


def audit(event, args):
    if event == "socket.connect" and sys._getframe(1).f_code.co_name != "_fallback_socketpair":
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
        if writing and not path.is_relative_to(ROOT):
            raise RuntimeError("Write outside isolated root")


sys.addaudithook(audit)


async def main():
    from libtv_agent.runner.supervisor import RunnerSupervisor

    if not hasattr(RunnerSupervisor, "recover_stale_launch_started_commands"):
        raise SystemExit("This branch lacks launch recovery; drill is unsupported")

    from libtv_agent.domain.enums import (
        AttemptStatus,
        CommandStatus,
        LedgerEntryType,
        ReservationStatus,
    )
    from libtv_agent.domain.models import (
        Base,
        GenerationAttempt,
        GenerationCommand,
        PointsLedger,
        PointsReservation,
    )
    from sqlalchemy import select
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
    from test_launch_started_recovery import KLING_PROVIDER, _stranded_command, _supervisor

    engine = create_async_engine(f"sqlite+aiosqlite:///{(ROOT / 'crash.db').as_posix()}")
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        if MODE == "seed":
            if (ROOT / "ready.json").exists():
                raise RuntimeError("Use a fresh drill directory")
            async with engine.begin() as connection:
                await connection.run_sync(Base.metadata.create_all)
            async with factory() as session:
                await _stranded_command(
                    session,
                    provider=KLING_PROVIDER,
                    lease_expires_at=datetime.now(UTC) - timedelta(weeks=7),
                )
            (ROOT / "ready.json").write_text(json.dumps({"pid": os.getpid(), "persisted": True}))
            await asyncio.Event().wait()
        else:
            async with factory() as session:
                supervisor = _supervisor(ROOT)
                first = await supervisor.recover_stale_launch_started_commands(session)
                second = await supervisor.recover_stale_launch_started_commands(session)
                command = await session.scalar(select(GenerationCommand))
                attempt = await session.scalar(select(GenerationAttempt))
                reservation = await session.scalar(select(PointsReservation))
                entries = list(await session.scalars(select(PointsLedger)))
                assert first == 1 and second == 0
                assert command.status == CommandStatus.UNCERTAIN
                assert attempt.status == AttemptStatus.UNKNOWN_AFTER_SUBMIT
                assert reservation.status == ReservationStatus.UNCERTAIN
                assert sorted(e.entry_type.value for e in entries) == sorted(
                    [LedgerEntryType.RESERVE.value, LedgerEntryType.UNCERTAIN.value]
                )
                (ROOT / "result.json").write_text(json.dumps({
                    "pid": os.getpid(), "recovery_counts": [first, second],
                    "command": command.status.value, "attempt": attempt.status.value,
                    "reservation": reservation.status.value,
                    "ledger": [e.entry_type.value for e in entries],
                    "provider_calls": 0,
                    "scope": "Persisted LAUNCH_STARTED fixture; not a live POST crash",
                }, indent=2))
    finally:
        await engine.dispose()


asyncio.run(main())
