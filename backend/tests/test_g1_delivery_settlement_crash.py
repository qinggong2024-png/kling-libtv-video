import os
import subprocess
import sys
import time
from pathlib import Path

SCRIPT = Path(__file__).parents[2] / "scripts" / "g1-delivery-settlement-crash.py"


def _env():
    return {
        key: value
        for key, value in os.environ.items()
        if key.upper() not in {"DATABASE_URL", "APP_ENV", "ENV_FILE"}
    }


def _start(root: Path, mode: str) -> subprocess.Popen[str]:
    return subprocess.Popen(
        [sys.executable, str(SCRIPT), str(root), mode],
        cwd=SCRIPT.parents[1],
        env=_env(),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )


def _crash_after(root: Path, mode: str, marker: str) -> None:
    process = _start(root, mode)
    deadline = time.monotonic() + 45
    while time.monotonic() < deadline and not (root / marker).exists():
        time.sleep(0.05)
    assert (root / marker).exists(), process.communicate(timeout=2)
    process.kill()
    process.communicate(timeout=5)
    assert process.returncode != 0


def _recover(root: Path, mode: str) -> None:
    result = subprocess.run(
        [sys.executable, str(SCRIPT), str(root), mode],
        cwd=SCRIPT.parents[1],
        env=_env(),
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, (
        f"{mode} failed with {result.returncode}\n"
        f"stdout:\n{result.stdout}\n"
        f"stderr:\n{result.stderr}"
    )


def test_download_interruption_recovers_in_a_fresh_process(tmp_path: Path) -> None:
    _crash_after(tmp_path, "seed-download", "download-entered")
    _recover(tmp_path, "recover-download")


def test_settlement_interruption_recovers_in_a_fresh_process(tmp_path: Path) -> None:
    _crash_after(tmp_path, "seed-settlement", "settlement-committed")
    _recover(tmp_path, "recover-settlement")
