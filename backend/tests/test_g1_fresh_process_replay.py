import os
import subprocess
import sys
from pathlib import Path

SCRIPT = Path(__file__).parents[2] / "scripts" / "g1-fresh-process-replay.py"


def _run(root: Path, mode: str) -> None:
    env = {
        key: value
        for key, value in os.environ.items()
        if key.upper() not in {"DATABASE_URL", "APP_ENV", "ENV_FILE"}
    }
    result = subprocess.run(
        [sys.executable, str(SCRIPT), str(root), mode],
        cwd=SCRIPT.parents[1],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, (
        f"{mode} failed with {result.returncode}\n"
        f"stdout:\n{result.stdout}\n"
        f"stderr:\n{result.stderr}"
    )


def test_confirmation_replays_in_a_fresh_process(tmp_path: Path) -> None:
    _run(tmp_path, "seed-confirm")
    _run(tmp_path, "replay-confirm")


def test_confirmation_dispatch_replays_in_a_fresh_process(tmp_path: Path) -> None:
    _run(tmp_path, "seed-dispatch")
    _run(tmp_path, "replay-dispatch")
