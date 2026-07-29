import argparse
import json
from pathlib import Path
from unittest.mock import AsyncMock

import pytest
from libtv_agent.adapters.libtv import LibTVError, RealLibTVAdapter
from libtv_agent.runner.command_host import execute, write_terminal_result


def test_terminal_result_is_written_atomically(tmp_path: Path) -> None:
    result_file = tmp_path / "terminal.json"

    write_terminal_result(result_file, {"ok": True, "taskId": "task-1"})

    assert json.loads(result_file.read_text(encoding="utf-8"))["taskId"] == "task-1"
    assert list(tmp_path.glob("*.tmp")) == []


@pytest.mark.asyncio
async def test_command_host_preserves_structured_auth_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    nonce = "test-nonce"
    result_file = tmp_path / "terminal.json"
    monkeypatch.setenv("LIBTV_COMMAND_NONCE", nonce)
    monkeypatch.setattr(
        RealLibTVAdapter,
        "run_generation",
        AsyncMock(side_effect=LibTVError("LIBTV_AUTH_REQUIRED", "login expired")),
    )
    args = argparse.Namespace(
        command_id="command-1",
        nonce=nonce,
        project_uuid="project-1",
        node="node-1",
        working_directory=tmp_path,
        result_file=result_file,
        libtv_executable="libtv",
    )

    assert await execute(args) == 1
    payload = json.loads(result_file.read_text(encoding="utf-8"))
    assert payload["error"] == {
        "code": "LIBTV_AUTH_REQUIRED",
        "message": "login expired",
        "submitted": False,
        "uncertain": False,
    }
