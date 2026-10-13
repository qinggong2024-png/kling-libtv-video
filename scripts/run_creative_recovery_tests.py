"""Run CW-4C recovery-contract tests with SQLite and network isolation."""

from __future__ import annotations

import argparse
import hashlib
import os
import subprocess
import sys
import tempfile
from pathlib import Path

TEST_RELATIVE = Path("backend/tests/test_creative_workflow_recovery_contract.py")


def _source_hash(root: Path) -> str:
    digest = hashlib.sha256()
    paths = [
        root / "backend/src/libtv_agent/services/creative_workflow.py",
        root / "backend/src/libtv_agent/api/creative_workflow.py",
        root / "backend/src/libtv_agent/creative/workflow.py",
        root / TEST_RELATIVE,
        root / "scripts/run_creative_recovery_tests.py",
    ]
    for path in paths:
        digest.update(path.relative_to(root).as_posix().encode())
        digest.update(path.read_bytes())
    return digest.hexdigest()


def _network_guard() -> str:
    return """
import socket as _socket
_real_socket = _socket.socket
_real_socketpair = _socket.socketpair
_internal_socketpair = False
class _GuardedSocket(_real_socket):
    def bind(self, address):
        if not _internal_socketpair:
            raise RuntimeError("CW-4C runner denies network bind")
        return super().bind(address)
    def listen(self, *args, **kwargs):
        if not _internal_socketpair:
            raise RuntimeError("CW-4C runner denies network listen")
        return super().listen(*args, **kwargs)
    def connect(self, address):
        if not _internal_socketpair:
            raise RuntimeError("CW-4C runner denies network connect")
        return super().connect(address)
def _socketpair(*args, **kwargs):
    global _internal_socketpair
    _internal_socketpair = True
    try:
        return _real_socketpair(*args, **kwargs)
    finally:
        _internal_socketpair = False
_socket.socket = _GuardedSocket
_socket.create_connection = lambda *args, **kwargs: (_ for _ in ()).throw(
    RuntimeError("CW-4C runner denies network connections")
)
_socket.socketpair = _socketpair
"""


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--evidence-dir", type=Path)
    args = parser.parse_args()

    root = args.root.resolve()
    test_path = (root / TEST_RELATIVE).resolve()
    if not test_path.is_file():
        raise SystemExit(f"missing CW-4C test: {test_path}")
    evidence = (
        args.evidence_dir.resolve()
        if args.evidence_dir
        else Path(tempfile.mkdtemp(prefix="creative-recovery-"))
    )
    if root == evidence or root in evidence.parents:
        raise SystemExit("evidence directory must be outside --root")
    evidence.mkdir(parents=True, exist_ok=True)
    runtime = evidence / "runtime"
    runtime.mkdir()
    (runtime / "sitecustomize.py").write_text(_network_guard(), encoding="utf-8")

    env = {
        key: os.environ[key]
        for key in ("PATH", "SystemRoot", "WINDIR", "TEMP", "TMP")
        if key in os.environ
    }
    env.update(
        {
            "APP_ENV": "test",
            "HOME": str(evidence),
            "USERPROFILE": str(evidence),
            "DATABASE_URL": f"sqlite+aiosqlite:///{(evidence / 'runner.db').as_posix()}",
            "OBJECT_STORE_MODE": "local",
            "PAID_GENERATION_ENABLED": "false",
            "AI_ADAPTER_MODE": "fake",
            "LIBTV_ADAPTER_MODE": "fake",
            "LIBTV_EXECUTION_MODE": "dry-run",
            "KLING_API_ENABLED": "false",
            "WAVESPEED_ENABLED": "false",
            "BACH_ENABLED": "false",
            "ARTIFACT_ROOT": str(evidence / "artifacts"),
            "RUNNER_ROOT": str(evidence / "runner"),
            "LIBTV_CONFIG_DIR": str(evidence / "libtv"),
            "PYTHONPATH": os.pathsep.join(
                [str(runtime), str(root / "backend" / "src")]
            ),
            "PYTHONNOUSERSITE": "1",
        }
    )
    command = [
        sys.executable,
        "-m",
        "pytest",
        str(test_path),
        "-c",
        str(root / "pyproject.toml"),
        "-o",
        "addopts=",
        "-p",
        "no:cacheprovider",
        "--basetemp",
        str(evidence / "pytest-basetemp"),
        "--junitxml",
        str(evidence / "junit.xml"),
    ]
    print(f"root={root}")
    print(f"source_hash={_source_hash(root)}")
    print(f"cwd={runtime}")
    print("network=denied")
    print("database=isolated-sqlite")
    print("command=" + " ".join(command))
    completed = subprocess.run(command, cwd=runtime, env=env, check=False)
    print(f"exit_code={completed.returncode}")
    print(f"junit={evidence / 'junit.xml'}")
    return completed.returncode


if __name__ == "__main__":
    raise SystemExit(main())
