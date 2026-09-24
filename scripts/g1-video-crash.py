"""Isolated video launch crash drill.

The submit worker commits LAUNCH_STARTED and then blocks awaiting a loopback HTTP response.
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
import threading
from datetime import UTC, datetime, timedelta
from http.server import BaseHTTPRequestHandler, HTTPServer
from types import SimpleNamespace

SOURCE = pathlib.Path(__file__).resolve().parents[1]
ROOT = pathlib.Path(sys.argv[1]).resolve()
MODE = sys.argv[2]
SCENARIO = sys.argv[3] if len(sys.argv) > 3 else "unknown"
if SCENARIO not in {"unknown", "known", "before"}:
    raise SystemExit("Expected unknown, known or before scenario")
if MODE not in {"submit", "recover"} or not ROOT.is_dir():
    raise SystemExit("Expected an existing isolated directory and submit/recover mode")
if any(
    p.lstat().st_file_attributes & stat.FILE_ATTRIBUTE_REPARSE_POINT for p in (ROOT, *ROOT.parents)
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
        if sys._getframe(1).f_code.co_name != "_fallback_socketpair" and args[1][:2] != (
            "127.0.0.1",
            18439,
        ):
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


class Receiver(BaseHTTPRequestHandler):
    def do_POST(self):
        body = self.rfile.read(int(self.headers["Content-Length"]))
        assert json.loads(body)["prompt"] == "synthetic crash drill"
        with (ROOT / "requests.jsonl").open("a") as stream:
            stream.write(json.dumps({"method": "POST", "bytes": len(body)}) + "\n")
            stream.flush()
            os.fsync(stream.fileno())
        (ROOT / "provider-entered.json").write_text(json.dumps({"pid": os.getpid()}))
        if SCENARIO in {"known", "before"}:
            body = json.dumps(
                {"code": 0, "data": {"id": "synthetic-remote-task", "status": "submitted"}}
            ).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        threading.Event().wait(120)

    def log_message(self, *_args):
        pass


class BlockingProvider:
    """Recovery sentinel: any provider operation fails the drill."""

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
        raise AssertionError("recovery must not resubmit")

    async def query(self, provider_task_id):
        raise AssertionError("recovery must not query without a provider handle")

    async def download(self, output, destination):
        raise AssertionError("download is outside this drill")

    async def get_account_status(self):
        return {}


class IsolatedObjectStore:
    async def localize(self, object_key, destination):
        if SCENARIO == "before" and MODE == "submit":
            (ROOT / "before-submit.json").write_text(json.dumps({"pid": os.getpid()}))
            await asyncio.Event().wait()
        return ROOT / "source.png"


class OriginalProvider(BlockingProvider):
    def __init__(self):
        super().__init__()
        self.queries = []

    async def query(self, provider_task_id):
        assert provider_task_id == "synthetic-remote-task"
        self.queries.append(provider_task_id)
        return SimpleNamespace(
            status="running",
            raw_status="processing",
            raw_response={"synthetic": True},
            credits_consumed=None,
        )


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
        kling_api_base_url="http://127.0.0.1:18439",
        paid_submissions_paused=False,
        generation_estimated_points=240,
        daily_user_points_limit=5000,
    )
    provider = BlockingProvider()
    if MODE == "submit" or SCENARIO == "before":
        from libtv_agent.adapters.kling_official_api import KlingOfficialApiAdapter

        provider = KlingOfficialApiAdapter(settings)

        async def synthetic_payload(request):
            return {"prompt": request.prompt, "external_task_id": request.external_task_id}

        provider.build_request_payload = synthetic_payload
        server = HTTPServer(("127.0.0.1", 18439), Receiver)
        threading.Thread(target=server.serve_forever, daemon=True).start()
    (ROOT / "source.png").write_bytes(b"synthetic image")
    supervisor = RunnerSupervisor(object(), IsolatedObjectStore(), settings, kling_adapter=provider)
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
                if SCENARIO == "known":
                    await session.refresh(attempt)
                    assert attempt.task_id == "synthetic-remote-task"
                    assert attempt.status == AttemptStatus.RUNNING
                    (ROOT / "handle-saved.json").write_text(json.dumps({"pid": os.getpid()}))
                    await asyncio.Event().wait()
        else:
            async with factory() as session:
                command = await session.scalar(select(GenerationCommand))
                attempt = await session.scalar(select(GenerationAttempt))
                if command is None or attempt is None:
                    raise RuntimeError("persisted launch fixture is missing")
                if SCENARIO == "before":
                    assert command.status == CommandStatus.READY
                    assert command.launch_started_at is None and attempt.task_id is None
                    assert not (ROOT / "requests.jsonl").exists()
                    assert await supervisor.recover_stale_launch_started_commands(session) == 0
                    await supervisor._execute(session, command.id)
                    await session.refresh(attempt)
                    await session.refresh(command)
                    assert attempt.task_id == "synthetic-remote-task"
                    assert attempt.status == AttemptStatus.RUNNING
                    assert command.status == CommandStatus.PROCESS_STARTED
                    assert await supervisor.recover_stale_launch_started_commands(session) == 0
                    reservations = list(await session.scalars(select(PointsReservation)))
                    entries = list(await session.scalars(select(PointsLedger)))
                    assert len(reservations) == 1
                    assert reservations[0].status == ReservationStatus.RESERVED
                    assert [entry.entry_type for entry in entries] == [LedgerEntryType.RESERVE]
                    assert len((ROOT / "requests.jsonl").read_text().splitlines()) == 1
                    (ROOT / "result.json").write_text(
                        json.dumps(
                            {
                                "scenario": "before",
                                "posts_before_crash": 0,
                                "posts_after_resume": 1,
                                "reservations": 1,
                                "attempt": attempt.status.value,
                                "scope": "pre-launch localization; direct command resume",
                            },
                            indent=2,
                        )
                    )
                    return
                command.lease_expires_at = datetime.now(UTC) - timedelta(hours=1)
                await session.commit()
                first = await supervisor.recover_stale_launch_started_commands(session)
                second = await supervisor.recover_stale_launch_started_commands(session)
                await session.refresh(command)
                await session.refresh(attempt)
                reservation = await session.scalar(select(PointsReservation))
                entries = list(await session.scalars(select(PointsLedger)))
                if SCENARIO == "known":
                    assert [first, second] == [0, 0]
                    original = OriginalProvider()
                    supervisor._kling_adapters[settings.kling_api_provider_name] = original
                    supervisor.kling_adapter = BlockingProvider()
                    assert await supervisor.poll_kling_tasks(session) == 1
                    await session.refresh(attempt)
                    assert attempt.task_id == "synthetic-remote-task"
                    assert attempt.status == AttemptStatus.RUNNING
                    assert command.status == CommandStatus.PROCESS_STARTED
                    assert reservation.status == ReservationStatus.RESERVED
                    assert [entry.entry_type for entry in entries] == [LedgerEntryType.RESERVE]
                    assert original.queries == ["synthetic-remote-task"]
                    assert original.calls == 0 and provider.calls == 0
                    assert len((ROOT / "requests.jsonl").read_text().splitlines()) == 1
                    (ROOT / "result.json").write_text(
                        json.dumps(
                            {
                                "scenario": "known",
                                "recovery_counts": [first, second],
                                "generation_posts": 1,
                                "original_provider_queries": 1,
                                "new_submissions": 0,
                                "attempt": attempt.status.value,
                                "reservation": reservation.status.value,
                            },
                            indent=2,
                        )
                    )
                    return
                assert first == 1 and second == 0
                assert command.status == CommandStatus.UNCERTAIN
                assert attempt.status == AttemptStatus.UNKNOWN_AFTER_SUBMIT
                assert attempt.charge_status == ChargeStatus.UNKNOWN
                assert reservation is not None and reservation.status == ReservationStatus.UNCERTAIN
                assert sorted(e.entry_type for e in entries) == sorted(
                    [LedgerEntryType.RESERVE, LedgerEntryType.UNCERTAIN]
                )
                assert provider.calls == 0
                assert len((ROOT / "requests.jsonl").read_text().splitlines()) == 1
                assert attempt.task_id is None
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
                            "generation_posts": 1,
                            "scope": "API HTTP acceptance then process kill; synthetic payload",
                        },
                        indent=2,
                    )
                )
    finally:
        await engine.dispose()


asyncio.run(main())
