import hashlib
import json
import subprocess
import sys
from dataclasses import asdict
from pathlib import Path

import psutil
from libtv_agent.runner.command_host_manager import CommandHostManager, CommandHostManifest


def file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_command_host_manifest_observation_protects_pid_nonce_and_terminal_result(
    tmp_path: Path,
) -> None:
    manager = CommandHostManager(tmp_path / "runner", tmp_path)
    manager.ensure_layout()
    process = subprocess.Popen(
        [sys.executable, "-c", "import time; time.sleep(30)"],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    observed = psutil.Process(process.pid)
    executable = Path(observed.exe())
    command_id = "command-one"
    result_file = manager.results / f"{command_id}.json"
    manifest = CommandHostManifest(
        command_id=command_id,
        nonce="nonce-one",
        pid=process.pid,
        process_started_at=observed.create_time(),
        executable=str(executable),
        executable_hash=file_hash(executable),
        command_hash="command-hash",
        arguments=(sys.executable, "-c", "import time; time.sleep(30)"),
        result_file=str(result_file),
        stdout_file=str(manager.logs / "stdout.log"),
        stderr_file=str(manager.logs / "stderr.log"),
        created_at="2026-07-27T00:00:00+00:00",
    )
    manager.manifest_path(command_id).write_text(json.dumps(asdict(manifest)), encoding="utf-8")
    try:
        assert manager.observe(command_id).status == "RUNNING"
        reused_payload = asdict(manifest)
        reused_payload["process_started_at"] = 0
        manager.manifest_path(command_id).write_text(json.dumps(reused_payload), encoding="utf-8")
        assert manager.observe(command_id).status == "PID_REUSED"
        manager.manifest_path(command_id).write_text(json.dumps(asdict(manifest)), encoding="utf-8")
        result_file.write_text(
            json.dumps(
                {
                    "ok": True,
                    "commandId": command_id,
                    "nonce": "wrong-nonce",
                    "result": {},
                }
            ),
            encoding="utf-8",
        )
        assert manager.observe(command_id).status == "INVALID_RESULT"
        result_file.write_text(
            json.dumps(
                {
                    "ok": True,
                    "commandId": command_id,
                    "nonce": manifest.nonce,
                    "result": {"status": "SUCCEEDED"},
                }
            ),
            encoding="utf-8",
        )
        terminal = manager.observe(command_id)
        assert terminal.status == "TERMINAL"
        assert terminal.terminal_result is not None
        assert manager.disk_status(15, 10)["status"] in {"OK", "WARNING", "STOP"}
    finally:
        process.terminate()
        process.wait(timeout=10)
