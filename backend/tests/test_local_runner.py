from pathlib import Path
from unittest.mock import AsyncMock

import pytest
from libtv_agent.runner import local_runner


@pytest.mark.parametrize("isolated", [False, True])
def test_local_runner_preserves_source_and_uses_selected_runtime_root(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, isolated: bool,
) -> None:
    loop = AsyncMock()
    logs = []
    monkeypatch.setattr(local_runner, "run_service_loop", loop)
    monkeypatch.setattr(local_runner, "configure_file_logging", logs.append)
    monkeypatch.setattr(local_runner.signal, "signal", lambda *_args: None)
    local_runner.main(tmp_path if isolated else None)
    loop.assert_awaited_once()
    _, source, runtime = loop.await_args.args
    assert source == local_runner.PROJECT_ROOT
    assert runtime == (tmp_path.resolve() if isolated else local_runner.PROJECT_ROOT)
    assert logs == [tmp_path / "logs" / "runner.log" if isolated else local_runner.RUNNER_LOG_PATH]


def test_safe_launcher_keeps_api_worker_and_credentials_isolated() -> None:
    script = (Path(__file__).parents[2] / "scripts" / "start-test-stack.ps1").read_text("utf-8")
    assert "[string]$DataRoot" in script
    assert "Stop-RecordedProcesses $processFile" in script
    assert "var\\test-live\\runtime\\stack-processes.json" not in script
    assert "--data-root" in script
    assert "'/d /s /c \"{0}\"'" in script
    assert "Push-Location $runtimeWorkingDirectory" in script
    assert "Remove-Item -LiteralPath \"Env:$name\"" in script
    assert "$env:GLOBAL_PAUSED = 'true'" in script
    assert "$env:DIRECTOR_WORKFLOW_MODE = 'offline_demo'" in script
