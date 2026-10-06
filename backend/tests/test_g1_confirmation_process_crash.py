import os
import subprocess
import sys
import time
from pathlib import Path

SCRIPT = Path(__file__).parents[2] / "scripts" / "g1-confirmation-crash.py"


def _env():
    return {
        key: value
        for key, value in os.environ.items()
        if key.upper() not in {"DATABASE_URL", "APP_ENV", "ENV_FILE"}
    }


def test_confirmation_preparing_recovers_in_a_fresh_process(tmp_path: Path) -> None:
    process = subprocess.Popen(
        [sys.executable, str(SCRIPT), str(tmp_path), "seed"],
        cwd=SCRIPT.parents[1],
        env=_env(),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    deadline = time.monotonic() + 45
    while time.monotonic() < deadline and not (tmp_path / "preparing").exists():
        time.sleep(0.05)
    assert (tmp_path / "preparing").exists(), process.communicate(timeout=2)
    process.kill()
    process.communicate(timeout=5)
    assert process.returncode != 0

    recovered = subprocess.run(
        [sys.executable, str(SCRIPT), str(tmp_path), "recover"],
        cwd=SCRIPT.parents[1],
        env=_env(),
        capture_output=True,
        text=True,
        check=False,
    )
    assert recovered.returncode == 0, (
        f"recover failed with {recovered.returncode}\n"
        f"stdout:\n{recovered.stdout}\n"
        f"stderr:\n{recovered.stderr}"
    )
