from __future__ import annotations

import asyncio
import os
import re
import uuid
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

_LOGIN_URL = re.compile(r"https://[^\s]+")
_LOGIN_HOSTS = ("liblib.tv", "liblib.art")


class LibTVLoginStartError(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class LibTVLoginStart:
    session_id: str
    login_url: str
    started_at: str
    already_running: bool = False

    def as_response(self) -> dict[str, object]:
        payload = asdict(self)
        return {
            "sessionId": payload["session_id"],
            "loginUrl": payload["login_url"],
            "startedAt": payload["started_at"],
            "alreadyRunning": payload["already_running"],
        }


def _validate_login_url(value: str) -> str:
    parsed = urlsplit(value)
    callbacks = parse_qs(parsed.query).get("callback_url", [])
    callback = urlsplit(callbacks[0]) if callbacks else None
    is_official_host = bool(
        parsed.hostname
        and any(
            parsed.hostname == host or parsed.hostname.endswith(f".{host}") for host in _LOGIN_HOSTS
        )
    )
    if (
        parsed.scheme != "https"
        or not is_official_host
        or callback is None
        or callback.scheme != "http"
        or callback.hostname != "127.0.0.1"
        or callback.port is None
    ):
        raise LibTVLoginStartError(
            "LIBTV_LOGIN_URL_INVALID",
            "LibTV CLI returned an invalid browser login URL",
        )
    return value


async def _drain(reader: asyncio.StreamReader | None) -> None:
    if reader is None:
        return
    while await reader.readline():
        pass


class LibTVLoginManager:
    def __init__(self, *, startup_timeout_seconds: float = 10.0) -> None:
        self.startup_timeout_seconds = startup_timeout_seconds
        self._lock = asyncio.Lock()
        self._process: asyncio.subprocess.Process | None = None
        self._session: LibTVLoginStart | None = None
        self._tasks: set[asyncio.Task[object]] = set()

    def _track(self, task: asyncio.Task[object]) -> None:
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    async def in_progress(self) -> bool:
        async with self._lock:
            return self._process is not None and self._process.returncode is None

    async def start(self, executable: str, config_dir: Path) -> LibTVLoginStart:
        async with self._lock:
            if (
                self._process is not None
                and self._process.returncode is None
                and self._session is not None
            ):
                return LibTVLoginStart(
                    **{
                        **asdict(self._session),
                        "already_running": True,
                    }
                )

            resolved_config_dir = await asyncio.to_thread(config_dir.resolve)
            await asyncio.to_thread(resolved_config_dir.mkdir, parents=True, exist_ok=True)
            environment = os.environ.copy()
            environment["LIBTV_CONFIG_DIR"] = str(resolved_config_dir)
            try:
                process = await asyncio.create_subprocess_exec(
                    executable,
                    "login",
                    "web",
                    env=environment,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    creationflags=0x08000000 if os.name == "nt" else 0,
                )
            except OSError as exc:
                raise LibTVLoginStartError(
                    "LIBTV_LOGIN_CLI_UNAVAILABLE",
                    "LibTV CLI could not be started",
                ) from exc
            self._process = process
            try:
                login_url = await asyncio.wait_for(
                    self._read_login_url(process),
                    timeout=self.startup_timeout_seconds,
                )
            except TimeoutError as exc:
                await self._stop_process(process)
                self._process = None
                self._session = None
                raise LibTVLoginStartError(
                    "LIBTV_LOGIN_START_TIMEOUT",
                    "LibTV CLI did not produce a browser login URL in time",
                ) from exc
            except Exception:
                await self._stop_process(process)
                self._process = None
                self._session = None
                raise

            self._session = LibTVLoginStart(
                session_id=str(uuid.uuid4()),
                login_url=login_url,
                started_at=datetime.now(UTC).isoformat(),
            )
            self._track(asyncio.create_task(_drain(process.stdout)))
            self._track(asyncio.create_task(_drain(process.stderr)))
            self._track(asyncio.create_task(process.wait()))
            return self._session

    async def _read_login_url(self, process: asyncio.subprocess.Process) -> str:
        if process.stderr is None:
            raise LibTVLoginStartError(
                "LIBTV_LOGIN_START_FAILED",
                "LibTV CLI did not expose a login stream",
            )
        while True:
            line = await process.stderr.readline()
            if not line:
                code = await process.wait()
                raise LibTVLoginStartError(
                    "LIBTV_LOGIN_START_FAILED",
                    f"LibTV CLI exited with {code} before producing a login URL",
                )
            match = _LOGIN_URL.search(line.decode("utf-8", errors="replace"))
            if match:
                return _validate_login_url(match.group(0))

    async def _stop_process(self, process: asyncio.subprocess.Process) -> None:
        if process.returncode is not None:
            return
        try:
            process.terminate()
        except ProcessLookupError:
            await process.wait()
            return
        try:
            await asyncio.wait_for(process.wait(), timeout=3)
        except TimeoutError:
            process.kill()
            await process.wait()

    async def close(self) -> None:
        async with self._lock:
            if self._process is not None:
                await self._stop_process(self._process)
            tasks = list(self._tasks)
            for task in tasks:
                task.cancel()
            if tasks:
                await asyncio.gather(*tasks, return_exceptions=True)
            self._tasks.clear()
            self._process = None
            self._session = None
