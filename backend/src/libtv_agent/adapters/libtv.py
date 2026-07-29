import asyncio
import json
import logging
import os
import re
import shutil
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from libtv_agent.config import Settings
from libtv_agent.services.generation_safety import (
    PAID_GENERATION_CONFIRMATION,
    build_generation_command,
)

logger = logging.getLogger(__name__)


def _hidden_process_creation_flags() -> int:
    return 0x08000000 if os.name == "nt" else 0  # CREATE_NO_WINDOW


@dataclass(frozen=True)
class GenerationResult:
    status: str
    payload: dict[str, object]
    stdout: str = ""
    stderr: str = ""


class LibTVError(RuntimeError):
    def __init__(
        self, code: str, message: str, *, submitted: bool = False, uncertain: bool = False
    ) -> None:
        super().__init__(message)
        self.code = code
        self.submitted = submitted
        self.uncertain = uncertain


def _last_json_object(stdout: str) -> dict[str, Any]:
    text = stdout.strip()
    if not text:
        raise LibTVError("LIBTV_JSON_INVALID", "libtv stdout did not contain JSON")
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        payload = None
        for line in reversed(text.splitlines()):
            try:
                payload = json.loads(line)
                break
            except json.JSONDecodeError:
                continue
    if not isinstance(payload, dict):
        raise LibTVError("LIBTV_JSON_INVALID", "libtv stdout did not contain a JSON object")
    return payload


def _task_info(payload: dict[str, Any]) -> dict[str, Any]:
    data = payload.get("data")
    if isinstance(data, dict) and isinstance(data.get("taskInfo"), dict):
        return data["taskInfo"]
    value = payload.get("taskInfo")
    return value if isinstance(value, dict) else {}


def _first_media_url(payload: dict[str, Any]) -> str | None:
    data = payload.get("data")
    values: object = data.get("url") if isinstance(data, dict) else None
    if isinstance(values, str) and values:
        return values
    if isinstance(values, list):
        return next((item for item in values if isinstance(item, str) and item), None)
    for key in ("videoUrl", "url"):
        value = payload.get(key)
        if isinstance(value, str) and value:
            return value
    return None


def _task_id(payload: dict[str, Any], stderr: str = "") -> str | None:
    info = _task_info(payload)
    for value in (info.get("taskId"), payload.get("taskId")):
        if isinstance(value, str) and value:
            return value
    match = re.search(r"\btask=([^\s]+)", stderr)
    return match.group(1) if match else None


def _error_message(payload: dict[str, Any], stderr: str = "") -> str:
    info = _task_info(payload)
    candidates = [
        info.get("error"),
        info.get("errorMessage"),
        info.get("message"),
        payload.get("error"),
        payload.get("message"),
        payload.get("reason"),
    ]
    for value in candidates:
        if isinstance(value, dict):
            nested = value.get("message") or value.get("reason") or value.get("code")
            if nested:
                return str(nested)
        elif value:
            return str(value)
    return stderr.strip() or "LibTV generation failed"


def _error_code(payload: dict[str, Any], default: str) -> str:
    info = _task_info(payload)
    for value in (info.get("error"), payload.get("error")):
        if isinstance(value, dict) and value.get("code"):
            return str(value["code"])
    for value in (info.get("errorCode"), payload.get("code"), payload.get("errorCode")):
        if value:
            return str(value)
    return default


def _normalized_error_code(payload: dict[str, Any], stderr: str, default: str) -> str:
    raw_code = _error_code(payload, default)
    message = _error_message(payload, stderr).lower()
    auth_codes = {"401", "LOGIN_REQUIRED", "UNAUTHORIZED", "NOT_LOGGED_IN"}
    auth_markers = ("未登录", "登录失效", "login expired", "not logged", "unauthorized")
    if str(raw_code).upper() in auth_codes or any(marker in message for marker in auth_markers):
        return "LIBTV_AUTH_REQUIRED"
    return raw_code


def _normalize_project(payload: dict[str, Any]) -> dict[str, Any]:
    candidates = [payload]
    for key in ("data", "project", "projectMeta"):
        value = payload.get(key)
        if isinstance(value, dict):
            candidates.append(value)
    for candidate in candidates:
        project_uuid = candidate.get("uuid") or candidate.get("projectUuid")
        if isinstance(project_uuid, str) and project_uuid:
            return {**candidate, "uuid": project_uuid}
    raise LibTVError("LIBTV_PROJECT_INVALID", "project response is missing its UUID")


def _find_project(payload: dict[str, Any], name: str) -> dict[str, Any] | None:
    projects = payload.get("projectMetaList")
    if not isinstance(projects, list):
        return None
    matches = [item for item in projects if isinstance(item, dict) and item.get("name") == name]
    if len(matches) > 1:
        raise LibTVError(
            "LIBTV_PROJECT_AMBIGUOUS",
            f"multiple LibTV projects have the expected name: {name}",
            uncertain=True,
        )
    return _normalize_project(matches[0]) if matches else None


def parse_node_snapshot(payload: dict[str, Any]) -> dict[str, Any]:
    data = payload.get("data")
    if not isinstance(data, dict):
        raise LibTVError("LIBTV_NODE_INVALID", "node query is missing data")
    params = data.get("params") if isinstance(data.get("params"), dict) else {}
    input_order = params.get("mixedListOrder") or params.get("imageListOrder") or []
    if not isinstance(input_order, list) or not all(isinstance(item, str) for item in input_order):
        raise LibTVError("LIBTV_NODE_INVALID", "node input order is invalid")
    node_key = payload.get("nodeKey")
    if not isinstance(node_key, str) or not node_key:
        raise LibTVError("LIBTV_NODE_INVALID", "node query is missing nodeKey")
    return {
        **payload,
        "nodeKey": node_key,
        "nodeType": payload.get("nodeType") or data.get("type"),
        "name": payload.get("name") or data.get("name"),
        "prompt": params.get("prompt", ""),
        "inputNodeKeys": input_order,
        "videoUrl": _first_media_url(payload),
        "taskInfo": _task_info(payload),
    }


def parse_generation_payload(payload: dict[str, Any]) -> GenerationResult:
    info = _task_info(payload)
    raw_status = info.get("status", payload.get("status"))
    status_text = str(raw_status).upper() if raw_status is not None else ""
    url = _first_media_url(payload)
    task_id = _task_id(payload)
    normalized = dict(payload)
    if task_id:
        normalized["taskId"] = task_id
    if url:
        normalized["videoUrl"] = url
    if raw_status == 2 or status_text in {"SUCCEEDED", "SUCCESS", "COMPLETED"}:
        if not url:
            return GenerationResult(status="UNKNOWN", payload=normalized)
        return GenerationResult(status="SUCCEEDED", payload=normalized)
    if raw_status in {3, 4} or status_text in {"FAILED", "FAILURE", "ERROR", "CANCELLED"}:
        normalized["reason"] = _error_message(payload)
        return GenerationResult(status="FAILED", payload=normalized)
    return GenerationResult(status="UNKNOWN", payload=normalized)


class LibTVAdapter(Protocol):
    async def check_account(self) -> dict[str, Any]: ...
    async def list_accounts(self) -> dict[str, Any]: ...
    async def use_account(self, account: str) -> dict[str, Any]: ...
    async def create_project(self, name: str) -> dict[str, Any]: ...
    async def create_group(self, *, project_uuid: str, name: str) -> dict[str, Any]: ...
    async def upload_image(
        self, *, project_uuid: str, group_node_key: str, name: str, path: Path, order: int
    ) -> dict[str, Any]: ...
    async def create_video_node(
        self, *, project_uuid: str, group_node_key: str, name: str
    ) -> dict[str, Any]: ...
    async def configure_video_node(
        self,
        *,
        project_uuid: str,
        node_key: str,
        prompt: str,
        params: dict[str, Any],
        input_node_keys: list[str],
    ) -> dict[str, Any]: ...
    async def read_node(self, *, project_uuid: str, node_key: str) -> dict[str, Any]: ...
    async def run_generation(
        self, *, project_uuid: str, node: str, working_directory: Path
    ) -> GenerationResult: ...
    async def query_node_result(self, *, project_uuid: str, node_key: str) -> GenerationResult: ...
    async def download_media(self, *, url: str, destination: Path) -> Path: ...


class FakeLibTVAdapter:
    def __init__(
        self, result: GenerationResult | None = None, *, scenario: str = "success"
    ) -> None:
        self.result = result
        self.scenario = scenario
        self.projects: dict[str, dict[str, Any]] = {}
        self.nodes: dict[str, dict[str, Any]] = {}
        self.upload_count = 0
        self.run_count = 0
        self.download_count = 0

    async def check_account(self) -> dict[str, Any]:
        return {"ok": True, "adapter": "fake"}

    async def list_accounts(self) -> dict[str, Any]:
        return {
            "accounts": [
                {
                    "accountId": "fake-personal",
                    "accountName": "本地模拟账号",
                    "accountType": "PERSONAL",
                    "isActive": True,
                    "teamId": 0,
                }
            ]
        }

    async def use_account(self, account: str) -> dict[str, Any]:
        return {
            "ok": True,
            "accountId": account,
            "accountName": "本地模拟账号",
            "accountType": "PERSONAL",
            "teamId": 0,
            "alreadyActive": True,
        }

    def _key(self, prefix: str, name: str) -> str:
        return f"{prefix}-{uuid.uuid5(uuid.NAMESPACE_URL, name).hex[:16]}"

    async def create_project(self, name: str) -> dict[str, Any]:
        project_uuid = str(uuid.uuid5(uuid.NAMESPACE_URL, f"fake-project:{name}"))
        self.projects.setdefault(project_uuid, {"uuid": project_uuid, "name": name})
        return self.projects[project_uuid]

    async def create_group(self, *, project_uuid: str, name: str) -> dict[str, Any]:
        key = self._key("group", f"{project_uuid}:{name}")
        self.nodes.setdefault(
            key,
            {
                "nodeKey": key,
                "name": name,
                "type": "group",
                "projectUuid": project_uuid,
                "children": [],
            },
        )
        return self.nodes[key]

    async def upload_image(
        self, *, project_uuid: str, group_node_key: str, name: str, path: Path, order: int
    ) -> dict[str, Any]:
        self.upload_count += 1
        if self.scenario == f"upload_fail_{self.upload_count}":
            raise LibTVError("MATERIALIZATION_RETRYABLE", "injected image upload failure")
        key = self._key("image", f"{project_uuid}:{group_node_key}:{name}")
        node = {
            "nodeKey": key,
            "name": name,
            "type": "image",
            "projectUuid": project_uuid,
            "groupNodeKey": group_node_key,
            "path": str(path),
            "order": order,
        }
        self.nodes.setdefault(key, node)
        return self.nodes[key]

    async def create_video_node(
        self, *, project_uuid: str, group_node_key: str, name: str
    ) -> dict[str, Any]:
        key = self._key("video", f"{project_uuid}:{group_node_key}:{name}")
        node = {
            "nodeKey": key,
            "name": name,
            "type": "video",
            "projectUuid": project_uuid,
            "groupNodeKey": group_node_key,
            "params": {},
            "inputNodeKeys": [],
        }
        self.nodes.setdefault(key, node)
        if self.scenario == "node_write_uncertain":
            raise LibTVError(
                "MATERIALIZATION_UNCERTAIN", "node created but result was lost", uncertain=True
            )
        return self.nodes[key]

    async def configure_video_node(
        self,
        *,
        project_uuid: str,
        node_key: str,
        prompt: str,
        params: dict[str, Any],
        input_node_keys: list[str],
    ) -> dict[str, Any]:
        node = self.nodes[node_key]
        node.update(
            {"prompt": prompt, "params": dict(params), "inputNodeKeys": list(input_node_keys)}
        )
        if self.scenario == "params_timeout":
            raise LibTVError(
                "MATERIALIZATION_UNCERTAIN", "parameters written before timeout", uncertain=True
            )
        return dict(node)

    async def read_node(self, *, project_uuid: str, node_key: str) -> dict[str, Any]:
        node = self.nodes.get(node_key)
        if node is None or node["projectUuid"] != project_uuid:
            raise LibTVError("MATERIALIZATION_RETRYABLE", "node not found")
        return dict(node)

    async def run_generation(
        self, *, project_uuid: str, node: str, working_directory: Path
    ) -> GenerationResult:
        self.run_count += 1
        if self.result is not None:
            return self.result
        if self.scenario in {"exit_before_task", "rate_limit"}:
            code = "RATE_LIMITED" if self.scenario == "rate_limit" else "FAILED_BEFORE_SUBMIT"
            raise LibTVError(code, "injected failure before task id")
        if self.scenario in {
            "exit_after_task",
            "host_restart",
            "database_writeback_fail",
            "disk_full",
        }:
            raise LibTVError(
                "GENERATION_UNKNOWN",
                "injected uncertain result after submit",
                submitted=True,
                uncertain=True,
            )
        if self.scenario == "terminal_failure" or (
            self.scenario == "dynamic_terminal_failure" and self.run_count == 2
        ):
            return GenerationResult(
                status="FAILED",
                payload={
                    "taskId": f"fake-task-{self.run_count}",
                    "reason": "injected terminal failure",
                },
            )
        stderr = "[run] task=fake-task\n"
        stdout = json.dumps(
            {"taskId": f"fake-task-{self.run_count}", "videoUrl": f"fake://{node}.mp4"}
        )
        if self.scenario == "stdout_stderr_reorder":
            stderr = "[run] terminal before buffered stdout\n"
        return GenerationResult(
            status="SUCCEEDED", payload=json.loads(stdout), stdout=stdout, stderr=stderr
        )

    async def query_node_result(self, *, project_uuid: str, node_key: str) -> GenerationResult:
        if self.scenario in {"exit_after_task", "database_writeback_fail", "terminal_pending"}:
            return GenerationResult(
                status="SUCCEEDED",
                payload={"taskId": "fake-reconciled", "videoUrl": f"fake://{node_key}.mp4"},
            )
        if self.scenario == "host_restart":
            return GenerationResult(status="UNKNOWN", payload={"nodeKey": node_key})
        return GenerationResult(
            status="SUCCEEDED",
            payload={"taskId": "fake-task", "videoUrl": f"fake://{node_key}.mp4"},
        )

    async def download_media(self, *, url: str, destination: Path) -> Path:
        self.download_count += 1
        if self.scenario == "download_interrupt_once" and self.download_count == 1:
            raise LibTVError("DOWNLOAD_RETRYABLE", "injected one-time download interruption")
        if self.scenario == "download_interrupt":
            raise LibTVError("DOWNLOAD_RETRYABLE", "injected download interruption")
        if self.scenario == "remote_restore_expired":
            raise LibTVError("REMOTE_RESULT_EXPIRED", "remote output is no longer available")
        destination.parent.mkdir(parents=True, exist_ok=True)
        await _create_fake_video(destination)
        return destination


class ReplayLibTVAdapter(FakeLibTVAdapter):
    def __init__(self, fixture_directory: Path) -> None:
        super().__init__(scenario="replay")
        self.fixture_directory = fixture_directory

    async def run_generation(
        self, *, project_uuid: str, node: str, working_directory: Path
    ) -> GenerationResult:
        fixture = self.fixture_directory / f"{node}.json"
        if not await asyncio.to_thread(fixture.is_file):
            fixture = self.fixture_directory / "generation.json"
        data = json.loads(fixture.read_text(encoding="utf-8"))
        return GenerationResult(**data)


class RealLibTVAdapter:
    def __init__(
        self,
        executable: str = "libtv",
        download_helper: Path | None = None,
        *,
        execution_mode: str = "dry-run",
        paid_generation_enabled: bool = False,
        paid_generation_confirmation: str = "",
        app_env: str = "development",
        workspace_id: str | None = None,
        config_dir: Path | None = None,
    ) -> None:
        self.executable = executable
        self.download_helper = download_helper
        self.execution_mode = execution_mode
        self.paid_generation_enabled = paid_generation_enabled
        self.paid_generation_confirmation = paid_generation_confirmation
        self.app_env = app_env
        self.workspace_id = workspace_id
        self.config_dir = config_dir.resolve() if config_dir is not None else None

    def _process_env(self) -> dict[str, str] | None:
        if self.config_dir is None:
            return None
        environment = os.environ.copy()
        environment["LIBTV_CONFIG_DIR"] = str(self.config_dir)
        return environment

    def _require_preparation_allowed(self) -> None:
        if self.execution_mode == "dry-run":
            logger.warning("LibTV remote preparation command blocked by dry-run mode")
            raise LibTVError(
                "LIBTV_PREPARATION_BLOCKED",
                "remote LibTV mutations are blocked in dry-run mode; use prepare-only explicitly",
            )

    def _require_paid_generation_allowed(self) -> None:
        authorized = (
            self.app_env != "test"
            and self.execution_mode == "live"
            and self.paid_generation_enabled
            and self.paid_generation_confirmation == PAID_GENERATION_CONFIRMATION
        )
        if authorized:
            return
        logger.warning("Paid LibTV generation command blocked by the adapter safety boundary")
        raise LibTVError(
            "PAID_GENERATION_BLOCKED",
            "paid LibTV generation is blocked; live mode, the explicit enable switch, "
            "and the exact confirmation phrase are all required",
        )

    def build_generation_command(self, *, project_uuid: str, node: str) -> list[str]:
        return build_generation_command(self.executable, project_uuid, node)

    async def _run_json(
        self, args: list[str], *, working_directory: Path | None = None
    ) -> dict[str, Any]:
        process_options: dict[str, Any] = {
            "cwd": working_directory,
            "stdout": asyncio.subprocess.PIPE,
            "stderr": asyncio.subprocess.PIPE,
            "creationflags": _hidden_process_creation_flags(),
        }
        if environment := self._process_env():
            process_options["env"] = environment
        process = await asyncio.create_subprocess_exec(
            *args,
            **process_options,
        )
        stdout_bytes, stderr_bytes = await process.communicate()
        stdout = stdout_bytes.decode("utf-8", errors="replace")
        stderr = stderr_bytes.decode("utf-8", errors="replace")
        if process.returncode != 0:
            payload: dict[str, Any] = {}
            if stdout.strip():
                try:
                    payload = _last_json_object(stdout)
                except LibTVError:
                    pass
            task_id = _task_id(payload, stderr)
            raise LibTVError(
                _normalized_error_code(payload, stderr, "LIBTV_CLI_ERROR"),
                f"libtv exited with {process.returncode}: {_error_message(payload, stderr)}",
                submitted=bool(task_id),
                uncertain=bool(task_id),
            )
        return _last_json_object(stdout)

    async def check_account(self) -> dict[str, Any]:
        return await self._run_json([self.executable, "account", "info"])

    async def list_accounts(self) -> dict[str, Any]:
        return await self._run_json([self.executable, "account", "list"])

    async def use_account(self, account: str) -> dict[str, Any]:
        return await self._run_json([self.executable, "account", "use", account])

    async def create_project(self, name: str) -> dict[str, Any]:
        self._require_preparation_allowed()
        list_args = [self.executable, "project", "list"]
        if self.workspace_id:
            list_args.extend(["--workspace", self.workspace_id])
            existing = _find_project(await self._run_json(list_args), name)
            if existing is not None:
                return existing
        args = [self.executable, "project", "create", name]
        if self.workspace_id:
            args.extend(["--workspace", self.workspace_id])
        created = await self._run_json(args)
        try:
            return _normalize_project(created)
        except LibTVError:
            if not self.workspace_id:
                raise
            existing = _find_project(await self._run_json(list_args), name)
            if existing is None:
                raise
            return existing

    async def create_group(self, *, project_uuid: str, name: str) -> dict[str, Any]:
        self._require_preparation_allowed()
        payload = await self._run_json(
            [self.executable, "group", "create", name, "--project", project_uuid]
        )
        group_node_key = payload.get("nodeKey") or payload.get("groupNodeKey")
        if not group_node_key:
            raise LibTVError(
                "LIBTV_CLI_CONTRACT_ERROR",
                "libtv group create did not return groupNodeKey",
            )
        return {**payload, "nodeKey": str(group_node_key)}

    async def upload_image(
        self, *, project_uuid: str, group_node_key: str, name: str, path: Path, order: int
    ) -> dict[str, Any]:
        self._require_preparation_allowed()
        payload = await self._run_json(
            [
                self.executable,
                "upload",
                name,
                "--file",
                str(path),
                "--project",
                project_uuid,
                "--group",
                group_node_key,
                "--x",
                str(order * 240),
                "--y",
                "80",
            ]
        )
        node_key = payload.get("nodeKey") or payload.get("newNodeKey")
        if not node_key:
            raise LibTVError(
                "LIBTV_CLI_CONTRACT_ERROR",
                "libtv upload did not return nodeKey",
            )
        return {**payload, "nodeKey": str(node_key)}

    async def create_video_node(
        self, *, project_uuid: str, group_node_key: str, name: str
    ) -> dict[str, Any]:
        self._require_preparation_allowed()
        payload = await self._run_json(
            [
                self.executable,
                "node",
                "create",
                name,
                "--type",
                "video",
                "--project",
                project_uuid,
                "--group",
                group_node_key,
            ]
        )
        node_key = payload.get("nodeKey") or payload.get("newNodeKey")
        if not node_key:
            raise LibTVError(
                "LIBTV_CLI_CONTRACT_ERROR",
                "libtv node create did not return nodeKey",
            )
        return {**payload, "nodeKey": str(node_key)}

    async def configure_video_node(
        self,
        *,
        project_uuid: str,
        node_key: str,
        prompt: str,
        params: dict[str, Any],
        input_node_keys: list[str],
    ) -> dict[str, Any]:
        self._require_preparation_allowed()
        args = [self.executable, "node", node_key, "--project", project_uuid]
        for input_node_key in input_node_keys:
            args.extend(["--left", input_node_key])
        for key, value in params.items():
            serialized = (
                json.dumps(value, ensure_ascii=False)
                if isinstance(value, (dict, list, bool))
                else str(value)
            )
            args.extend(["--set", f"{key}={serialized}"])
        args.extend(["--prompt", prompt])
        return await self._run_json(args)

    async def read_node(self, *, project_uuid: str, node_key: str) -> dict[str, Any]:
        payload = await self._run_json(
            [self.executable, "node", node_key, "--project", project_uuid]
        )
        return parse_node_snapshot(payload)

    async def run_generation(
        self, *, project_uuid: str, node: str, working_directory: Path
    ) -> GenerationResult:
        self._require_paid_generation_allowed()
        process_options: dict[str, Any] = {
            "cwd": working_directory,
            "stdout": asyncio.subprocess.PIPE,
            "stderr": asyncio.subprocess.PIPE,
            "creationflags": _hidden_process_creation_flags(),
        }
        if environment := self._process_env():
            process_options["env"] = environment
        process = await asyncio.create_subprocess_exec(
            *self.build_generation_command(project_uuid=project_uuid, node=node),
            **process_options,
        )
        # Official libtv owns submission and polling; this await has deliberately no timeout.
        stdout_bytes, stderr_bytes = await process.communicate()
        stdout = stdout_bytes.decode("utf-8", errors="replace")
        stderr = stderr_bytes.decode("utf-8", errors="replace")
        payload: dict[str, Any] = {}
        if stdout.strip():
            try:
                payload = _last_json_object(stdout)
            except LibTVError:
                if process.returncode == 0:
                    raise
        result = parse_generation_payload(payload)
        if result.status == "FAILED":
            return GenerationResult("FAILED", result.payload, stdout, stderr)
        if process.returncode != 0:
            task_id = _task_id(payload, stderr)
            if task_id:
                raise LibTVError(
                    "GENERATION_UNKNOWN",
                    f"libtv exited with {process.returncode} after task acceptance",
                    submitted=True,
                    uncertain=True,
                )
            raise LibTVError(
                _normalized_error_code(payload, stderr, "LIBTV_CLI_ERROR"),
                f"libtv exited with {process.returncode}: {_error_message(payload, stderr)}",
            )
        if result.status != "SUCCEEDED":
            raise LibTVError(
                "GENERATION_UNKNOWN",
                "libtv exited without a successful or failed terminal node result",
                submitted=bool(_task_id(payload, stderr)),
                uncertain=True,
            )
        return GenerationResult("SUCCEEDED", result.payload, stdout, stderr)

    async def query_node_result(self, *, project_uuid: str, node_key: str) -> GenerationResult:
        payload = await self.read_node(project_uuid=project_uuid, node_key=node_key)
        return parse_generation_payload(payload)

    async def download_media(self, *, url: str, destination: Path) -> Path:
        helper = self.download_helper
        powershell = shutil.which("powershell.exe") or shutil.which("pwsh")
        if helper is None or not helper.is_file() or powershell is None:
            raise LibTVError(
                "DOWNLOAD_REQUIRES_TRANSFER_HELPER",
                "the approved LibTV PowerShell transfer helper is unavailable",
            )
        destination.parent.mkdir(parents=True, exist_ok=True)
        process = await asyncio.create_subprocess_exec(
            powershell,
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(helper),
            "-Url",
            url,
            "-OutputFile",
            str(destination),
            "-NetworkMode",
            "Auto",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            creationflags=_hidden_process_creation_flags(),
        )
        # The approved helper owns segmented retries and resume; do not impose a caller timeout.
        stdout, stderr = await process.communicate()
        downloaded = await asyncio.to_thread(destination.is_file)
        if process.returncode != 0 or not downloaded:
            message = stderr.decode("utf-8", errors="replace").strip()
            if not message:
                message = stdout.decode("utf-8", errors="replace").strip()
            raise LibTVError("DOWNLOAD_RETRYABLE", message or "LibTV download helper failed")
        return destination


async def _create_fake_video(destination: Path) -> None:
    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg is None:
        await asyncio.to_thread(destination.write_bytes, b"FAKE-MP4-OFFLINE-CONTRACT")
        return
    process = await asyncio.create_subprocess_exec(
        ffmpeg,
        "-y",
        "-f",
        "lavfi",
        "-i",
        "testsrc2=s=360x640:r=10:d=10",
        "-an",
        "-c:v",
        "libx264",
        "-pix_fmt",
        "yuv420p",
        str(destination),
        stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.DEVNULL,
        creationflags=_hidden_process_creation_flags(),
    )
    if await process.wait() != 0:
        raise LibTVError("DOWNLOAD_RETRYABLE", "ffmpeg could not create fake video")


def create_libtv_adapter(settings: Settings) -> LibTVAdapter:
    if settings.libtv_adapter_mode == "real":
        return RealLibTVAdapter(
            settings.libtv_executable,
            settings.libtv_download_helper,
            execution_mode=settings.libtv_execution_mode,
            paid_generation_enabled=settings.paid_generation_enabled,
            paid_generation_confirmation=settings.paid_generation_confirmation,
            app_env=settings.app_env,
            workspace_id=settings.libtv_workspace_id,
            config_dir=settings.libtv_config_dir,
        )
    if settings.libtv_adapter_mode == "replay":
        return ReplayLibTVAdapter(settings.libtv_replay_fixture_dir)
    return FakeLibTVAdapter(scenario=settings.fake_libtv_scenario)
