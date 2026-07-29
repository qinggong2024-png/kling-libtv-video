from __future__ import annotations

import hashlib
import json
import os
import secrets
import shutil
import subprocess
import sys
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

import psutil


@dataclass(frozen=True)
class CommandHostManifest:
    command_id: str
    nonce: str
    pid: int
    process_started_at: float
    executable: str
    executable_hash: str
    command_hash: str
    arguments: tuple[str, ...]
    result_file: str
    stdout_file: str
    stderr_file: str
    created_at: str


@dataclass(frozen=True)
class CommandHostObservation:
    status: Literal["RUNNING", "TERMINAL", "PID_REUSED", "LOST", "INVALID_RESULT"]
    manifest: CommandHostManifest
    terminal_result: dict[str, Any] | None = None


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _file_hash(path: Path) -> str:
    with path.open("rb") as handle:
        digest = hashlib.sha256()
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _write_json_atomic(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(f"{path.suffix}.{os.getpid()}.tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=True, sort_keys=True), encoding="utf-8")
    temporary.replace(path)


class CommandHostManager:
    def __init__(
        self,
        root: Path,
        project_root: Path,
        libtv_executable: str = "libtv",
        *,
        execution_mode: str = "dry-run",
        paid_generation_enabled: bool = False,
        paid_generation_confirmation: str = "",
        app_env: str = "development",
        libtv_config_dir: Path | None = None,
    ) -> None:
        self.root = root.resolve()
        self.project_root = project_root.resolve()
        self.libtv_executable = libtv_executable
        self.execution_mode = execution_mode
        self.paid_generation_enabled = paid_generation_enabled
        self.paid_generation_confirmation = paid_generation_confirmation
        self.app_env = app_env
        self.libtv_config_dir = libtv_config_dir.resolve() if libtv_config_dir is not None else None
        self.manifests = self.root / "manifests"
        self.results = self.root / "results"
        self.logs = self.root / "logs"
        self.work = self.root / "work"

    def ensure_layout(self) -> None:
        for path in (self.root, self.manifests, self.results, self.logs, self.work):
            path.mkdir(parents=True, exist_ok=True)

    def manifest_path(self, command_id: str) -> Path:
        return self.manifests / f"{command_id}.json"

    def launch_generation(
        self, command_id: str, project_uuid: str, node: str
    ) -> CommandHostManifest:
        self.ensure_layout()
        nonce = secrets.token_hex(32)
        result_file = self.results / f"{command_id}.json"
        stdout_file = self.logs / f"{command_id}.stdout.log"
        stderr_file = self.logs / f"{command_id}.stderr.log"
        working_directory = self.work / command_id
        working_directory.mkdir(parents=True, exist_ok=True)
        script = (
            self.project_root / "backend" / "src" / "libtv_agent" / "runner" / "command_host.py"
        )
        arguments = (
            sys.executable,
            str(script),
            "--command-id",
            command_id,
            "--nonce",
            nonce,
            "--project-uuid",
            project_uuid,
            "--node",
            node,
            "--working-directory",
            str(working_directory),
            "--result-file",
            str(result_file),
            "--libtv-executable",
            self.libtv_executable,
        )
        environment = os.environ.copy()
        source_root = str(self.project_root / "backend" / "src")
        environment["PYTHONPATH"] = os.pathsep.join(
            [source_root, environment.get("PYTHONPATH", "")]
        ).rstrip(os.pathsep)
        environment["LIBTV_COMMAND_NONCE"] = nonce
        environment["LIBTV_EXECUTION_MODE"] = self.execution_mode
        environment["LIBTV_PAID_GENERATION_ENABLED"] = str(self.paid_generation_enabled).lower()
        environment["LIBTV_PAID_GENERATION_CONFIRMATION"] = self.paid_generation_confirmation
        environment["APP_ENV"] = self.app_env
        if self.libtv_config_dir is not None:
            environment["LIBTV_CONFIG_DIR"] = str(self.libtv_config_dir)
        creation_flags = 0
        if os.name == "nt":
            creation_flags = subprocess.CREATE_NEW_PROCESS_GROUP | 0x08000000  # CREATE_NO_WINDOW
        with (
            stdout_file.open("ab", buffering=0) as stdout,
            stderr_file.open("ab", buffering=0) as stderr,
        ):
            process = subprocess.Popen(
                arguments,
                cwd=working_directory,
                env=environment,
                stdin=subprocess.DEVNULL,
                stdout=stdout,
                stderr=stderr,
                creationflags=creation_flags,
                close_fds=True,
            )
        observed = psutil.Process(process.pid)
        executable = Path(observed.exe())
        manifest = CommandHostManifest(
            command_id=command_id,
            nonce=nonce,
            pid=process.pid,
            process_started_at=observed.create_time(),
            executable=str(executable),
            executable_hash=_file_hash(executable),
            command_hash=_sha256_bytes(json.dumps(arguments).encode("utf-8")),
            arguments=arguments,
            result_file=str(result_file),
            stdout_file=str(stdout_file),
            stderr_file=str(stderr_file),
            created_at=datetime.now(UTC).isoformat(),
        )
        _write_json_atomic(self.manifest_path(command_id), asdict(manifest))
        return manifest

    def read_manifest(self, command_id: str) -> CommandHostManifest:
        payload = json.loads(self.manifest_path(command_id).read_text(encoding="utf-8"))
        payload["arguments"] = tuple(payload["arguments"])
        return CommandHostManifest(**payload)

    def observe(self, command_id: str) -> CommandHostObservation:
        manifest = self.read_manifest(command_id)
        result_file = Path(manifest.result_file)
        if result_file.is_file():
            try:
                result = json.loads(result_file.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                return CommandHostObservation("INVALID_RESULT", manifest)
            if (
                result.get("commandId") != manifest.command_id
                or result.get("nonce") != manifest.nonce
            ):
                return CommandHostObservation("INVALID_RESULT", manifest, result)
            return CommandHostObservation("TERMINAL", manifest, result)
        try:
            process = psutil.Process(manifest.pid)
            create_time = process.create_time()
            executable = Path(process.exe())
        except (psutil.NoSuchProcess, psutil.AccessDenied, OSError):
            return CommandHostObservation("LOST", manifest)
        if (
            abs(create_time - manifest.process_started_at) > 0.01
            or _file_hash(executable) != manifest.executable_hash
        ):
            return CommandHostObservation("PID_REUSED", manifest)
        return CommandHostObservation("RUNNING", manifest)

    def disk_status(self, warning_percent: float, stop_percent: float) -> dict[str, Any]:
        self.ensure_layout()
        usage = shutil.disk_usage(self.root)
        free_percent = 100.0 * usage.free / usage.total
        status = (
            "STOP"
            if free_percent <= stop_percent
            else "WARNING"
            if free_percent <= warning_percent
            else "OK"
        )
        return {"status": status, "freePercent": round(free_percent, 2)}

    def find_orphan_processes(self) -> list[int]:
        known = {
            self.read_manifest(path.stem).pid
            for path in self.manifests.glob("*.json")
            if path.is_file()
        }
        orphans: list[int] = []
        for process in psutil.process_iter(["pid", "cmdline"]):
            try:
                command_line = process.info.get("cmdline") or []
                if "command_host.py" in " ".join(command_line) and process.pid not in known:
                    orphans.append(process.pid)
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
        return sorted(orphans)
