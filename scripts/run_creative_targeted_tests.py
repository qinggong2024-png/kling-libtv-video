"""Run an explicit Creative Workflow test selection in an isolated process."""

from __future__ import annotations

import argparse
import hashlib
import os
import subprocess
import sys
import tempfile
from pathlib import Path


def _root_hash(root: Path) -> str:
    digest = hashlib.sha256()
    candidates = [
        *sorted((root / "backend" / "src").rglob("*.py")),
        *sorted((root / "backend" / "alembic").rglob("*.py")),
        *sorted((root / "backend" / "tests").rglob("test_creative_*.py")),
    ]
    for path in candidates:
        digest.update(path.relative_to(root).as_posix().encode())
        digest.update(path.read_bytes())
    return digest.hexdigest()


def _network_guard() -> str:
    return """
import ssl as _ssl
import socket as _socket
_real_socket = _socket.socket
_real_create_connection = _socket.create_connection
_real_socketpair = _socket.socketpair
_internal_socketpair = False
class _GuardedSocket(_real_socket):
    def bind(self, address):
        if not _internal_socketpair:
            raise RuntimeError("creative targeted runner denies network bind")
        return super().bind(address)
    def listen(self, *args, **kwargs):
        if not _internal_socketpair:
            raise RuntimeError("creative targeted runner denies network listen")
        return super().listen(*args, **kwargs)
    def connect(self, address):
        if not _internal_socketpair:
            raise RuntimeError("creative targeted runner denies network connect")
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
    RuntimeError("creative targeted runner denies network connections")
)
_socket.socketpair = _socketpair
"""


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--tests", nargs="+", required=True)
    parser.add_argument("--evidence-dir", type=Path)
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    root = args.root.resolve()
    tests_root = (root / "backend" / "tests").resolve()
    selected: list[Path] = []
    for raw in args.tests:
        path = (root / raw).resolve() if not Path(raw).is_absolute() else Path(raw).resolve()
        if path.parent != tests_root or path.suffix != ".py":
            raise SystemExit(f"test must be a direct .py file in {tests_root}: {raw}")
        if not path.is_file():
            raise SystemExit(f"test file does not exist: {path}")
        selected.append(path)

    evidence = (
        args.evidence_dir.resolve()
        if getattr(args, "evidence_dir", None)
        else Path(tempfile.mkdtemp(prefix="creative-targeted-"))
    )
    if root == evidence or root in evidence.parents:
        raise SystemExit("evidence directory must be outside --root")
    evidence.mkdir(parents=True, exist_ok=True)
    temp = evidence / "runtime"
    temp.mkdir()
    sitecustomize = temp / "sitecustomize.py"
    sitecustomize.write_text(_network_guard(), encoding="utf-8")
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
            "PYTHONPATH": os.pathsep.join([str(temp), str(root / "backend" / "src")]),
            "PYTHONNOUSERSITE": "1",
        }
    )
    command = [
        sys.executable,
        "-m",
        "pytest",
        *(str(path) for path in selected),
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
    print(f"source_hash={_root_hash(root)}")
    print(f"cwd={temp}")
    print("command=" + " ".join(command))
    completed = subprocess.run(command, cwd=temp, env=env, check=False)
    print(f"exit_code={completed.returncode}")
    print(f"junit={evidence / 'junit.xml'}")
    return completed.returncode


if __name__ == "__main__":
    raise SystemExit(main())
