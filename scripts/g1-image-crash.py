"""Worker for kill-after-HTTP-acceptance testing; output must be a fresh isolated directory."""

import asyncio
import json
import os
import pathlib
import platform
import stat
import sys
import threading
import uuid
from datetime import UTC, datetime
from http.server import BaseHTTPRequestHandler, HTTPServer
from types import SimpleNamespace

SOURCE = pathlib.Path(__file__).resolve().parents[1]
ROOT = pathlib.Path(sys.argv[1]).resolve()
MODE = sys.argv[2]
if MODE not in {"submit", "recover"} or not ROOT.is_dir():
    raise SystemExit("Expected existing isolated root and submit/recover")
if any(
    p.lstat().st_file_attributes & stat.FILE_ATTRIBUTE_REPARSE_POINT for p in (ROOT, *ROOT.parents)
):
    raise SystemExit("Reparse points forbidden")
for key in list(os.environ):
    if key.upper() not in {"SYSTEMROOT", "WINDIR", "PATH", "PATHEXT", "COMSPEC"}:
        del os.environ[key]
os.environ.update(APP_ENV="test", TEMP=str(ROOT), TMP=str(ROOT), USERPROFILE=str(ROOT))
os.chdir(ROOT)
sys.dont_write_bytecode = True
sys.path[:0] = [str(SOURCE / "backend/src"), str(SOURCE / "backend/tests")]
platform.uname()


def audit(event, args):
    if event == "socket.connect":
        if sys._getframe(1).f_code.co_name != "_fallback_socketpair" and args[1][:2] != (
            "127.0.0.1",
            18439,
        ):
            raise RuntimeError("External network forbidden")
    if event in {"subprocess.Popen", "os.system"}:
        raise RuntimeError("Child processes forbidden")
    if event == "open" and isinstance(args[0], (str, bytes)):
        path = pathlib.Path(os.fsdecode(args[0])).resolve()
        if path.name == ".env" or "libtv-production" in path.parts:
            raise RuntimeError("Production access forbidden")
        writing = any(c in (args[1] or "") for c in "wax+") or (args[2] or 0) & (
            os.O_WRONLY | os.O_RDWR
        )
        if writing and not path.is_relative_to(ROOT):
            raise RuntimeError("Write outside isolated root")


sys.addaudithook(audit)


class Receiver(BaseHTTPRequestHandler):
    def do_POST(self):
        self.rfile.read(int(self.headers["Content-Length"]))
        with (ROOT / "requests.jsonl").open("a") as stream:
            stream.write(json.dumps({"method": "POST", "pid": os.getpid()}) + "\n")
            stream.flush()
            os.fsync(stream.fileno())
        (ROOT / "accepted.json").write_text(json.dumps({"pid": os.getpid()}))
        threading.Event().wait(120)

    def log_message(self, *_args):
        pass


async def main():
    from fastapi import FastAPI
    from httpx import ASGITransport, AsyncClient
    from libtv_agent.adapters.wavespeed import WaveSpeedAdapter, WaveSpeedAvailability
    from libtv_agent.api.image_generations import router
    from libtv_agent.config import Settings
    from libtv_agent.domain.models import Base, ImageGenerationBatch, ImageGenerationItem, User
    from libtv_agent.services.runtime_control import get_runtime_config
    from sqlalchemy import func, select
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
    from test_image_quota_concurrency import post

    database = ROOT / "image-crash.db"
    if MODE == "submit" and database.exists():
        raise RuntimeError("Fresh directory required")
    if MODE == "recover" and not database.exists():
        raise RuntimeError("Missing persisted database")
    engine = create_async_engine(f"sqlite+aiosqlite:///{database.as_posix()}")
    factory = async_sessionmaker(engine, expire_on_commit=False)
    user = uuid.UUID("00000000-0000-0000-0000-000000000123")
    settings = Settings(
        _env_file=None,
        app_env="test",
        wavespeed_enabled=True,
        wavespeed_api_key="synthetic-only",
        paid_submissions_paused=False,
        wavespeed_api_base_url="http://127.0.0.1:18439/api/v3",
        runner_root=ROOT / "runner",
        artifact_root=ROOT / "artifacts",
    )
    adapter = WaveSpeedAdapter(settings)
    adapter._last_availability = WaveSpeedAvailability(
        "AVAILABLE", True, True, None, datetime.now(UTC)
    )

    async def upload(_path):
        return "https://synthetic.invalid/reference.png"

    adapter.upload_media = upload
    app = FastAPI()
    app.include_router(router, prefix="/api/v1")
    app.state.database = SimpleNamespace(session_factory=factory)
    app.state.settings = settings
    app.state.wavespeed_adapter = adapter
    try:
        if MODE == "submit":
            async with engine.begin() as connection:
                await connection.run_sync(Base.metadata.create_all)
            async with factory() as session:
                session.add(User(id=user, username="synthetic", password_hash="disabled"))
                await get_runtime_config(session, settings)
                await session.commit()
            server = HTTPServer(("127.0.0.1", 18439), Receiver)
            threading.Thread(target=server.serve_forever, daemon=True).start()
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await post(client, user, "crash-stable-key")
            assert response.status_code == 201, response.text
            if MODE == "recover":
                assert response.json()["status"] == "write_uncertain"
                again = await post(client, user, "crash-stable-key")
                assert again.json()["id"] == response.json()["id"]
        if MODE == "recover":
            async with factory() as session:
                assert (
                    await session.scalar(select(func.count()).select_from(ImageGenerationBatch))
                    == 1
                )
                item = await session.scalar(select(ImageGenerationItem))
                assert item.status == "WRITE_UNCERTAIN" and item.provider_task_id is None
            assert len((ROOT / "requests.jsonl").read_text().splitlines()) == 1
            (ROOT / "result.json").write_text(
                json.dumps(
                    {
                        "pid": os.getpid(),
                        "status": "WRITE_UNCERTAIN",
                        "generation_posts": 1,
                        "batches": 1,
                        "replays": 2,
                        "scope": "real HTTP acceptance then process kill",
                    },
                    indent=2,
                )
            )
    finally:
        await engine.dispose()


asyncio.run(main())
