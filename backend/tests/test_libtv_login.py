import asyncio
from pathlib import Path
from unittest.mock import AsyncMock

import pytest
from libtv_agent.services.libtv_login import (
    LibTVLoginManager,
    LibTVLoginStartError,
    _validate_login_url,
)

LOGIN_URL = "https://www.liblib.tv/zh?callback_url=http%3A%2F%2F127.0.0.1%3A6708%2Fcallback"


class StubReader:
    def __init__(self, lines: list[bytes]) -> None:
        self.lines = list(lines)

    async def readline(self) -> bytes:
        await asyncio.sleep(0)
        return self.lines.pop(0) if self.lines else b""


class StubLoginProcess:
    def __init__(self) -> None:
        self.returncode: int | None = None
        self.stdout = StubReader([])
        self.stderr = StubReader(
            [
                "在浏览器中打开以下链接完成登录：\n".encode(),
                f"{LOGIN_URL}\n".encode(),
                "等待本机回调…\n".encode(),
            ]
        )
        self.finished = asyncio.Event()

    async def wait(self) -> int:
        await self.finished.wait()
        return self.returncode or 0

    def terminate(self) -> None:
        self.returncode = -15
        self.finished.set()

    def kill(self) -> None:
        self.returncode = -9
        self.finished.set()


def test_login_url_requires_https_and_loopback_callback() -> None:
    assert _validate_login_url(LOGIN_URL) == LOGIN_URL

    with pytest.raises(LibTVLoginStartError, match="invalid browser login URL"):
        _validate_login_url(
            "https://www.liblib.tv/zh?callback_url=https%3A%2F%2Fattacker.example%2Fcallback"
        )

    with pytest.raises(LibTVLoginStartError, match="invalid browser login URL"):
        _validate_login_url(
            "https://attacker.example/zh?callback_url=http%3A%2F%2F127.0.0.1%3A6708%2Fcallback"
        )


@pytest.mark.asyncio
async def test_login_manager_starts_once_and_reuses_active_session(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    process = StubLoginProcess()
    create_process = AsyncMock(return_value=process)
    monkeypatch.setattr(asyncio, "create_subprocess_exec", create_process)
    manager = LibTVLoginManager()

    first = await manager.start("libtv", tmp_path / "libtv-config")
    second = await manager.start("libtv", tmp_path / "libtv-config")

    assert first.login_url == LOGIN_URL
    assert second.session_id == first.session_id
    assert second.already_running is True
    assert await manager.in_progress()
    create_process.assert_awaited_once()
    assert create_process.await_args.args == ("libtv", "login", "web")
    assert create_process.await_args.kwargs["env"]["LIBTV_CONFIG_DIR"] == str(
        (tmp_path / "libtv-config").resolve()
    )

    await manager.close()
    assert process.returncode == -15
    assert not await manager.in_progress()
