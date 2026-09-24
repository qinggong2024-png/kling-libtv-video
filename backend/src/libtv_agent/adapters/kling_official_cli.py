from __future__ import annotations

import asyncio
import json
import logging
import os
import random
import shutil
import time
from collections.abc import Awaitable, Callable
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from urllib.request import Request, urlopen

from libtv_agent.adapters.video_provider import (
    DownloadResult,
    ProviderAvailability,
    ProviderCapabilities,
    ProviderOutput,
    ProviderSubmissionResult,
    ProviderTaskResult,
    VideoGenerationRequest,
)
from libtv_agent.config import Settings

logger = logging.getLogger(__name__)

KLING_SKILL_NAME = "kling-cli"
KLING_SKILL_VERSION = "0.1.3"


@dataclass(frozen=True)
class CliProcessResult:
    exit_code: int
    stdout: str
    stderr: str


class KlingCliError(RuntimeError):
    def __init__(
        self,
        code: str,
        message: str,
        *,
        retryable: bool = False,
        provider_task_id: str | None = None,
        raw_status: str | None = None,
        details: dict[str, Any] | None = None,
        submitted: bool = False,
        uncertain: bool = False,
        retry_after_seconds: float | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.retryable = retryable
        self.provider = "kling_official_cli"
        self.provider_task_id = provider_task_id
        self.raw_status = raw_status
        self.details = details or {}
        self.submitted = submitted
        self.uncertain = uncertain
        self.retry_after_seconds = retry_after_seconds


def parse_cli_json(stdout: str) -> dict[str, Any]:
    text = stdout.strip()
    if not text:
        raise KlingCliError(
            "KLING_CLI_OUTPUT_PARSE_FAILED", "Kling CLI did not return structured output"
        )
    candidates = [text, *reversed(text.splitlines())]
    for candidate in candidates:
        try:
            payload = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            return payload
    raise KlingCliError("KLING_CLI_OUTPUT_PARSE_FAILED", "Kling CLI returned invalid JSON output")


def unwrap_cli_body(payload: dict[str, Any]) -> dict[str, Any]:
    if payload.get("ok") is False:
        body = payload.get("body")
        message = (
            body.get("message")
            if isinstance(body, dict)
            else payload.get("message") or payload.get("error") or body
        )
        text = str(message or "Kling CLI request failed")
        lowered = text.lower()
        if any(marker in lowered for marker in ("unauthorized", "not logged", "login required")):
            code = "KLING_CLI_NOT_AUTHENTICATED"
        elif any(marker in lowered for marker in ("credit", "灵感值", "余额不足")):
            code = "KLING_INSUFFICIENT_CREDITS"
        elif any(marker in lowered for marker in ("rate limit", "too many requests", "限流")):
            code = "KLING_RATE_LIMITED"
        else:
            code = "KLING_CLI_PROCESS_FAILED"
        raise KlingCliError(
            code,
            text,
            retryable=code in {"KLING_RATE_LIMITED", "KLING_CLI_PROCESS_FAILED"},
            details={"status": payload.get("status")},
        )
    body = payload.get("body", payload)
    if not isinstance(body, dict):
        raise KlingCliError("KLING_CLI_OUTPUT_PARSE_FAILED", "Kling CLI JSON body is not an object")
    return body


def map_kling_status(raw_status: object) -> str:
    normalized = str(raw_status or "").strip().upper()
    if normalized in {"QUEUING", "PENDING", "SUBMITTED"}:
        return "queued"
    if normalized in {"RUNNING", "PROCESSING"}:
        return "running"
    if normalized in {"COMPLETED", "SUCCESS", "SUCCEED", "SUCCEEDED"}:
        return "succeeded"
    if normalized == "PARTIAL_COMPLETED":
        return "partial"
    if normalized in {"FAILED", "FAILURE", "ERROR", "CANCELLED", "CANCELED"}:
        return "failed"
    return "unknown"


def _video_model_items(capabilities: ProviderCapabilities) -> list[dict[str, Any]]:
    available = capabilities.raw_capabilities.get("availableModels")
    video_models = available.get("image_to_video") if isinstance(available, dict) else None
    if isinstance(video_models, dict):
        video_models = video_models.get("models")
    if not isinstance(video_models, list):
        return []
    return [item for item in video_models if isinstance(item, dict)]


def _argument_specs(capabilities: ProviderCapabilities, model: str) -> list[dict[str, Any]]:
    for item in _video_model_items(capabilities):
        if isinstance(item, dict) and item.get("model") == model:
            arguments = item.get("arguments")
            return (
                [value for value in arguments if isinstance(value, dict)]
                if isinstance(arguments, list)
                else []
            )
    return []


def _input_specs(capabilities: ProviderCapabilities, model: str) -> list[dict[str, Any]]:
    for item in _video_model_items(capabilities):
        if isinstance(item, dict) and item.get("model") == model:
            inputs = item.get("inputs")
            return (
                [value for value in inputs if isinstance(value, dict)]
                if isinstance(inputs, list)
                else []
            )
    return []


def _allowed_values(specs: list[dict[str, Any]], *names: str) -> tuple[str, ...]:
    normalized_names = {name.replace("_", "").lower() for name in names}
    for spec in specs:
        name = str(spec.get("name") or "").replace("_", "").lower()
        if name not in normalized_names:
            continue
        values = spec.get("allowedValues")
        if isinstance(values, list):
            return tuple(str(value) for value in values)
    return ()


def _model_input_profile(capabilities: ProviderCapabilities, model: str) -> tuple[int, bool, bool]:
    names = {str(item.get("name") or "").lower() for item in _input_specs(capabilities, model)}
    numbered_images = {name for name in names if name.startswith("image_") and name[6:].isdigit()}
    supports_repeated_images = bool(numbered_images)
    supports_tail = any("tail" in name or "end" in name for name in names)
    if supports_repeated_images:
        return len(numbered_images), supports_tail, True
    return (2 if supports_tail else 1), supports_tail, False


def _all_allowed_values(specs: list[dict[str, Any]], *names: str) -> tuple[str, ...]:
    normalized_names = {name.replace("_", "").lower() for name in names}
    values: list[str] = []
    for spec in specs:
        name = str(spec.get("name") or "").replace("_", "").lower()
        if name not in normalized_names:
            continue
        allowed = spec.get("allowedValues")
        if not isinstance(allowed, list):
            allowed = spec.get("allowed_values")
        if isinstance(allowed, list):
            for value in allowed:
                text = str(value)
                if text not in values:
                    values.append(text)
    return tuple(values)


def _role_bound_prompt(request: VideoGenerationRequest) -> str:
    if not request.product_reference_paths:
        return request.prompt
    storyboard_count = len(request.image_paths)
    product_start = storyboard_count + 1
    product_end = storyboard_count + len(request.product_reference_paths)
    storyboard_label = f"图片1至图片{storyboard_count}" if storyboard_count > 1 else "图片1"
    product_label = (
        f"图片{product_start}至图片{product_end}"
        if product_start != product_end
        else f"图片{product_start}"
    )
    role_guard = (
        "【输入图片用途，必须严格遵守】"
        f"{storyboard_label}是分镜图，只用于决定视频的场景、构图、人物姿势、动作、"
        "镜头运动和镜头顺序；"
        f"{product_label}是产品参考图，只用于还原服装款式、版型、颜色、面料、印花、"
        "Logo与文字细节。不得采用产品参考图的背景、构图、摆放方式或拍摄姿势，"
        "不得把白底图、平铺图或商品静物图变成视频场景。若两类图片冲突，"
        "场景与动作以分镜图为准，服装外观细节以产品参考图为准。"
    )
    return f"{role_guard}\n\n{request.prompt}"


class KlingOfficialCliAdapter:
    def __init__(
        self,
        settings: Settings,
        *,
        process_runner: Callable[[list[str], float], Awaitable[CliProcessResult]] | None = None,
    ) -> None:
        self.settings = settings
        self.executable = settings.kling_cli_executable
        self._process_runner = process_runner or self._run_process
        self._capabilities: ProviderCapabilities | None = None
        self._last_availability: ProviderAvailability | None = None
        self._capability_lock = asyncio.Lock()
        self._rate_lock = asyncio.Lock()
        self._last_call = 0.0
        self._submit_semaphore = asyncio.Semaphore(settings.kling_cli_max_submit_concurrency)
        self._query_semaphore = asyncio.Semaphore(settings.kling_cli_max_query_concurrency)
        self._cache_path = settings.runner_root / "kling" / "capabilities.json"

    def get_provider_name(self) -> str:
        return self.settings.kling_cli_provider_name

    def _base_args(self) -> list[str]:
        return [
            "--quiet",
            "--skill-name",
            KLING_SKILL_NAME,
            "--skill-version",
            KLING_SKILL_VERSION,
        ]

    async def _throttle(self) -> None:
        minimum_interval = 1.0 / self.settings.kling_cli_global_qps
        async with self._rate_lock:
            now = time.monotonic()
            remaining = minimum_interval - (now - self._last_call)
            if remaining > 0:
                await asyncio.sleep(remaining)
            self._last_call = time.monotonic()

    async def _run_process(self, arguments: list[str], timeout_seconds: float) -> CliProcessResult:
        executable = shutil.which(self.executable) or self.executable
        creation_flags = 0x08000000 if os.name == "nt" else 0
        try:
            process = await asyncio.create_subprocess_exec(
                executable,
                *arguments,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                creationflags=creation_flags,
            )
        except FileNotFoundError as exc:
            raise KlingCliError("KLING_CLI_NOT_INSTALLED", "Kling CLI is not installed") from exc
        except OSError as exc:
            raise KlingCliError(
                "KLING_CLI_PROCESS_FAILED",
                "Kling CLI process could not be started",
                retryable=True,
                details={"errorType": type(exc).__name__},
            ) from exc
        try:
            stdout, stderr = await asyncio.wait_for(process.communicate(), timeout_seconds)
        except TimeoutError as exc:
            process.kill()
            await process.wait()
            raise KlingCliError(
                "KLING_CLI_TIMEOUT",
                "Kling CLI command timed out",
                retryable=True,
                uncertain=True,
            ) from exc
        return CliProcessResult(
            exit_code=int(process.returncode or 0),
            stdout=stdout.decode("utf-8", errors="replace"),
            stderr=stderr.decode("utf-8", errors="replace"),
        )

    async def _invoke(
        self,
        command: str,
        arguments: list[str] | None = None,
        *,
        timeout_ms: int | None = None,
        submitted: bool = False,
    ) -> dict[str, Any]:
        await self._throttle()
        timeout = (timeout_ms or self.settings.kling_cli_command_timeout_ms) / 1000
        result = await self._process_runner(
            [*self._base_args(), command, *(arguments or [])],
            timeout,
        )
        if result.exit_code != 0:
            lowered = f"{result.stdout}\n{result.stderr}".lower()
            if any(
                marker in lowered for marker in ("not logged", "login required", "unauthorized")
            ):
                code = "KLING_CLI_NOT_AUTHENTICATED"
            elif any(marker in lowered for marker in ("credit", "灵感值", "余额不足")):
                code = "KLING_INSUFFICIENT_CREDITS"
            elif any(marker in lowered for marker in ("rate limit", "too many requests", "限流")):
                code = "KLING_RATE_LIMITED"
            else:
                code = "KLING_CLI_PROCESS_FAILED"
            raise KlingCliError(
                code,
                "Kling CLI command failed",
                retryable=code in {"KLING_RATE_LIMITED", "KLING_CLI_PROCESS_FAILED"},
                details={"exitCode": result.exit_code},
                submitted=submitted,
                uncertain=submitted,
            )
        return unwrap_cli_body(parse_cli_json(result.stdout))

    async def _version(self) -> str:
        await self._throttle()
        result = await self._process_runner(
            ["--version", "--skill-name", KLING_SKILL_NAME, "--skill-version", KLING_SKILL_VERSION],
            self.settings.kling_cli_command_timeout_ms / 1000,
        )
        if result.exit_code != 0:
            raise KlingCliError("KLING_CLI_PROCESS_FAILED", "Unable to read Kling CLI version")
        return result.stdout.strip() or result.stderr.strip()

    def _clear_capability_cache(self) -> None:
        self._capabilities = None
        self._cache_path.unlink(missing_ok=True)

    async def login(self) -> ProviderAvailability:
        if not self.settings.kling_cli_enabled:
            raise KlingCliError(
                "KLING_CAPABILITY_UNSUPPORTED",
                "Kling CLI Provider is disabled",
            )
        self._clear_capability_cache()
        await self._invoke("login", timeout_ms=300_000)
        availability = await self.check_availability()
        if availability.status != "KLING_CLI_READY":
            raise KlingCliError(
                availability.status,
                availability.reason or "Kling CLI login could not be verified",
            )
        await self.refresh_capabilities(force=True)
        return availability

    async def logout(self) -> ProviderAvailability:
        version = await self._version()
        await self._invoke("logout")
        self._clear_capability_cache()
        self._last_availability = ProviderAvailability(
            status="KLING_CLI_NOT_AUTHENTICATED",
            available=True,
            authenticated=False,
            reason="Kling account is logged out",
            cli_version=version,
        )
        return self._last_availability

    async def check_availability(self) -> ProviderAvailability:
        if not self.settings.kling_cli_enabled:
            self._last_availability = ProviderAvailability(
                status="KLING_CAPABILITY_UNSUPPORTED",
                available=False,
                authenticated=False,
                reason="Kling CLI Provider is disabled",
            )
            return self._last_availability
        try:
            version = await self._version()
            await self._invoke("who_am_i")
        except KlingCliError as exc:
            self._last_availability = ProviderAvailability(
                status=exc.code,
                available=exc.code != "KLING_CLI_NOT_INSTALLED",
                authenticated=exc.code != "KLING_CLI_NOT_AUTHENTICATED",
                reason=str(exc),
            )
            return self._last_availability
        self._last_availability = ProviderAvailability(
            status="KLING_CLI_READY",
            available=True,
            authenticated=True,
            cli_version=version,
        )
        return self._last_availability

    def availability_snapshot(self) -> ProviderAvailability:
        if self._last_availability is not None:
            return self._last_availability
        cached = self._capabilities or self._load_cached_capabilities()
        if cached is not None:
            return ProviderAvailability(
                status="KLING_CLI_READY",
                available=True,
                authenticated=cached.authenticated,
                cli_version=cached.cli_version,
            )
        return ProviderAvailability(
            status=(
                "KLING_CAPABILITY_FETCH_FAILED"
                if self.settings.kling_cli_enabled
                else "KLING_CAPABILITY_UNSUPPORTED"
            ),
            available=False,
            authenticated=False,
            reason=(
                "Kling capability discovery has not completed"
                if self.settings.kling_cli_enabled
                else "Kling CLI Provider is disabled"
            ),
        )

    def capabilities_snapshot(self) -> ProviderCapabilities | None:
        return self._capabilities or self._load_cached_capabilities()

    def _load_cached_capabilities(self) -> ProviderCapabilities | None:
        try:
            payload = json.loads(self._cache_path.read_text(encoding="utf-8"))
            checked_at = datetime.fromisoformat(str(payload["checkedAt"]))
            if checked_at.tzinfo is None:
                checked_at = checked_at.replace(tzinfo=UTC)
            return ProviderCapabilities(
                cli_version=str(payload["cliVersion"]),
                checked_at=checked_at,
                authenticated=bool(payload["authenticated"]),
                account_type=payload.get("accountType"),
                supported_models=tuple(payload.get("supportedModels") or ()),
                supported_tools=tuple(payload.get("supportedTools") or ()),
                video_durations=tuple(payload.get("videoDurations") or ()),
                aspect_ratios=tuple(payload.get("aspectRatios") or ()),
                image_input_limit=int(payload.get("imageInputLimit") or 1),
                supports_tail_image=bool(payload.get("supportsTailImage")),
                supports_multiple_images=bool(payload.get("supportsMultipleImages")),
                supports_watermark_free_output=bool(payload.get("supportsWatermarkFreeOutput")),
                supports_sound_control=bool(payload.get("supportsSoundControl")),
                raw_capabilities=dict(payload.get("rawCapabilities") or {}),
            )
        except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError):
            return None

    def _save_capabilities(self, capabilities: ProviderCapabilities) -> None:
        payload = {
            "cliVersion": capabilities.cli_version,
            "checkedAt": capabilities.checked_at.isoformat(),
            "authenticated": capabilities.authenticated,
            "accountType": capabilities.account_type,
            "supportedModels": list(capabilities.supported_models),
            "supportedTools": list(capabilities.supported_tools),
            "videoDurations": list(capabilities.video_durations),
            "aspectRatios": list(capabilities.aspect_ratios),
            "imageInputLimit": capabilities.image_input_limit,
            "supportsTailImage": capabilities.supports_tail_image,
            "supportsMultipleImages": capabilities.supports_multiple_images,
            "supportsWatermarkFreeOutput": capabilities.supports_watermark_free_output,
            "supportsSoundControl": capabilities.supports_sound_control,
            "rawCapabilities": capabilities.raw_capabilities,
        }
        self._cache_path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self._cache_path.with_suffix(f".{os.getpid()}.tmp")
        temporary.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        temporary.replace(self._cache_path)

    async def refresh_capabilities(self, *, force: bool = False) -> ProviderCapabilities:
        now = datetime.now(UTC)
        ttl = timedelta(seconds=self.settings.kling_cli_capability_cache_seconds)
        cached = self._capabilities or self._load_cached_capabilities()
        if cached and now - cached.checked_at < ttl and not force:
            self._capabilities = cached
            return cached
        async with self._capability_lock:
            try:
                version, identity, tools = await asyncio.gather(
                    self._version(),
                    self._invoke("who_am_i"),
                    self._invoke("tool_list"),
                )
            except KlingCliError as exc:
                if cached and now - cached.checked_at < ttl:
                    self._capabilities = cached
                    return cached
                raise KlingCliError(
                    "KLING_CAPABILITY_FETCH_FAILED",
                    str(exc),
                    retryable=exc.retryable,
                ) from exc
            available = identity.get("availableModels")
            video_models = available.get("image_to_video") if isinstance(available, dict) else []
            if isinstance(video_models, dict):
                video_models = video_models.get("models")
            model_items = (
                [item for item in video_models if isinstance(item, dict)]
                if isinstance(video_models, list)
                else []
            )
            models = tuple(
                str(item["model"]) for item in model_items if isinstance(item.get("model"), str)
            )
            argument_specs = [
                argument
                for item in model_items
                for argument in (item.get("arguments") or [])
                if isinstance(argument, dict)
            ]
            profiles = [
                _model_input_profile(
                    ProviderCapabilities(
                        cli_version=version,
                        checked_at=now,
                        authenticated=True,
                        account_type=None,
                        supported_models=models,
                        supported_tools=(),
                        raw_capabilities=identity,
                    ),
                    model,
                )
                for model in models
            ]
            tail = any(profile[1] for profile in profiles)
            image_limit = max((profile[0] for profile in profiles), default=1)
            tool_items = tools.get("tools") if isinstance(tools.get("tools"), list) else []
            supported_tools = tuple(
                str(item["name"])
                for item in tool_items
                if isinstance(item, dict) and isinstance(item.get("name"), str)
            )
            raw = {
                **identity,
                "tools": tool_items,
            }
            user = identity.get("user") if isinstance(identity.get("user"), dict) else {}
            capabilities = ProviderCapabilities(
                cli_version=version,
                checked_at=now,
                authenticated=True,
                account_type=str(user.get("accountType")) if user.get("accountType") else None,
                supported_models=models,
                supported_tools=supported_tools,
                video_durations=_all_allowed_values(argument_specs, "duration"),
                aspect_ratios=_all_allowed_values(argument_specs, "aspect_ratio", "aspectRatio"),
                image_input_limit=image_limit,
                supports_tail_image=tail,
                supports_multiple_images=image_limit > 1,
                supports_watermark_free_output=True,
                supports_sound_control=any(
                    str(item.get("name") or "").replace("_", "").lower()
                    in {"sound", "enablesound", "enableaudio"}
                    for item in argument_specs
                ),
                raw_capabilities=raw,
            )
            previous = self._capabilities
            self._capabilities = capabilities
            self._last_availability = ProviderAvailability(
                status="KLING_CLI_READY",
                available=True,
                authenticated=True,
                cli_version=version,
            )
            self._save_capabilities(capabilities)
            if previous and asdict(previous) != asdict(capabilities):
                logger.warning("Kling CLI capabilities changed")
            return capabilities

    def _select_model(
        self,
        capabilities: ProviderCapabilities,
        preferred: str | None,
        request: VideoGenerationRequest,
    ) -> str:
        if preferred:
            if preferred not in capabilities.supported_models:
                raise KlingCliError(
                    "KLING_CAPABILITY_UNSUPPORTED",
                    f"Configured Kling model is unavailable: {preferred}",
                )
            models_to_check = (preferred,)
        else:
            models_to_check = capabilities.supported_models
        candidates: list[str] = []
        parameter_compatible = False
        role_compatible = False
        total_image_count = len(request.image_paths) + len(request.product_reference_paths)
        for model in models_to_check:
            arguments = _argument_specs(capabilities, model)
            durations = _allowed_values(arguments, "duration")
            ratios = _allowed_values(arguments, "aspect_ratio", "aspectRatio")
            if (
                request.duration is not None
                and durations
                and str(request.duration) not in durations
            ):
                continue
            if request.aspect_ratio and ratios and request.aspect_ratio not in ratios:
                continue
            parameter_compatible = True
            input_limit, supports_tail, supports_repeated_images = _model_input_profile(
                capabilities, model
            )
            if request.product_reference_paths and not supports_repeated_images:
                continue
            role_compatible = True
            if total_image_count > input_limit and not (
                not request.product_reference_paths
                and request.fallback_mode == "first_last_frame"
                and supports_tail
            ):
                continue
            candidates.append(model)
        if not candidates:
            if parameter_compatible and request.product_reference_paths and not role_compatible:
                raise KlingCliError(
                    "KLING_PRODUCT_REFERENCE_UNSUPPORTED",
                    "Compatible Kling models cannot keep product references separate from "
                    "storyboard inputs",
                )
            if parameter_compatible:
                largest_limit = max(
                    (_model_input_profile(capabilities, model)[0] for model in models_to_check),
                    default=1,
                )
                if request.product_reference_paths:
                    raise KlingCliError(
                        "KLING_IMAGE_INPUT_LIMIT_EXCEEDED",
                        "Compatible Kling models support at most "
                        f"{largest_limit} total storyboard and product reference image input(s)",
                    )
                raise KlingCliError(
                    "KLING_MULTI_STORYBOARD_UNSUPPORTED",
                    "Compatible Kling models support at most "
                    f"{largest_limit} storyboard image input(s)",
                )
            raise KlingCliError(
                "KLING_CAPABILITY_UNSUPPORTED",
                "Current Kling account has no image-to-video model compatible with this request",
            )
        return candidates[0]

    async def validate_request(self, request: VideoGenerationRequest) -> str:
        if not request.prompt.strip():
            raise KlingCliError("KLING_INVALID_INPUT", "Video prompt cannot be empty")
        if not request.image_paths:
            raise KlingCliError("KLING_INVALID_INPUT", "At least one storyboard image is required")
        capabilities = await self.refresh_capabilities()
        model = self._select_model(capabilities, request.model, request)
        limit, supports_tail, supports_repeated_images = _model_input_profile(capabilities, model)
        total_image_count = len(request.image_paths) + len(request.product_reference_paths)
        if request.product_reference_paths and not supports_repeated_images:
            raise KlingCliError(
                "KLING_PRODUCT_REFERENCE_UNSUPPORTED",
                "Selected Kling model cannot keep product references separate from "
                "storyboard inputs",
            )
        if total_image_count > limit and not (
            not request.product_reference_paths
            and request.fallback_mode == "first_last_frame"
            and supports_tail
        ):
            kind = (
                "storyboard and product reference"
                if request.product_reference_paths
                else "storyboard"
            )
            raise KlingCliError(
                (
                    "KLING_IMAGE_INPUT_LIMIT_EXCEEDED"
                    if request.product_reference_paths
                    else "KLING_MULTI_STORYBOARD_UNSUPPORTED"
                ),
                f"Selected Kling model supports at most {limit} total {kind} image input(s)",
            )
        if request.fallback_mode not in {"disabled", "first_last_frame"}:
            raise KlingCliError("KLING_INVALID_INPUT", "Invalid Kling storyboard fallback mode")
        for path in request.image_paths:
            if not path.is_file():
                raise KlingCliError(
                    "KLING_INVALID_INPUT", f"Storyboard image is unavailable: {path.name}"
                )
        for path in request.product_reference_paths:
            if not path.is_file():
                raise KlingCliError(
                    "KLING_INVALID_INPUT",
                    f"Product reference image is unavailable: {path.name}",
                )
        return model

    async def submit(self, request: VideoGenerationRequest) -> ProviderSubmissionResult:
        model = await self.validate_request(request)
        capabilities = await self.refresh_capabilities()
        paths = list(request.image_paths)
        product_paths = list(request.product_reference_paths)
        input_limit, supports_tail, supports_repeated_images = _model_input_profile(
            capabilities, model
        )
        if len(paths) > input_limit:
            paths = [paths[0], paths[-1]]
        arguments = ["--model", model]
        if supports_repeated_images:
            for path in [*paths, *product_paths]:
                arguments.extend(["--image", str(path)])
        else:
            arguments.extend(["--image", str(paths[0])])
            if len(paths) > 1:
                if not supports_tail:
                    raise KlingCliError(
                        "KLING_MULTI_STORYBOARD_UNSUPPORTED",
                        "Selected Kling model does not expose a tail-image input",
                    )
                arguments.extend(["--tailImage", str(paths[-1])])
        specs = _argument_specs(capabilities, model)
        spec_names = {str(item.get("name") or "").replace("_", "").lower() for item in specs}
        if request.duration is not None and "duration" in spec_names:
            arguments.extend(["--duration", str(request.duration)])
        if request.aspect_ratio and "aspectratio" in spec_names:
            arguments.extend(["--aspectRatio", request.aspect_ratio])
        if request.task_trace_id:
            arguments.extend(["--task-trace-id", request.task_trace_id])
        arguments.append(_role_bound_prompt(request))
        async with self._submit_semaphore:
            body = await self._invoke(
                "image_to_video",
                arguments,
                timeout_ms=self.settings.kling_cli_command_timeout_ms,
                submitted=True,
            )
        task_id = body.get("generationId") or body.get("generation_id")
        if not isinstance(task_id, str) or not task_id:
            raise KlingCliError(
                "KLING_SUBMIT_RESULT_UNKNOWN",
                "Kling CLI did not return generationId",
                retryable=False,
                submitted=True,
                uncertain=True,
            )
        credits = body.get("creditsConsumed") or body.get("credits_consumed")
        return ProviderSubmissionResult(
            provider_task_id=task_id,
            raw_status=str(body.get("status") or "submitted"),
            credits_consumed=int(credits) if isinstance(credits, (int, float)) else None,
            provider_model=model,
            raw_response=body,
        )

    async def query(self, provider_task_id: str) -> ProviderTaskResult:
        if not provider_task_id:
            raise KlingCliError("KLING_INVALID_INPUT", "generationId is required")
        async with self._query_semaphore:
            body = await self._invoke(
                "query_tasks",
                [provider_task_id],
                timeout_ms=self.settings.kling_cli_query_timeout_ms,
            )
        raw_status = str(body.get("status") or "")
        status = map_kling_status(raw_status)
        works = body.get("works")
        outputs: list[ProviderOutput] = []
        if isinstance(works, list):
            for work in works:
                if not isinstance(work, dict):
                    continue
                url = work.get("url")
                if isinstance(url, str) and url:
                    outputs.append(
                        ProviderOutput(
                            url=url,
                            content_type=str(work.get("contentType"))
                            if work.get("contentType")
                            else None,
                            url_without_watermark=str(work.get("urlWithoutWatermark"))
                            if work.get("urlWithoutWatermark")
                            else None,
                            cover_url=str(work.get("coverUrl")) if work.get("coverUrl") else None,
                        )
                    )
        if status in {"succeeded", "partial"} and not outputs:
            raise KlingCliError(
                "KLING_OUTPUT_URL_MISSING",
                "Kling task completed without a downloadable output URL",
                provider_task_id=provider_task_id,
                raw_status=raw_status,
            )
        return ProviderTaskResult(
            status=status,
            raw_status=raw_status,
            outputs=tuple(outputs),
            raw_response=body,
        )

    async def download(self, output: ProviderOutput, destination: Path) -> DownloadResult:
        from libtv_agent.adapters.download_worker import stage_download

        existing_size = await asyncio.to_thread(
            lambda: destination.stat().st_size if destination.is_file() else 0
        )
        if existing_size > 0:
            return DownloadResult(path=destination, reused=True, size_bytes=existing_size)
        temporary = destination.with_suffix(f"{destination.suffix}.part")
        destination.parent.mkdir(parents=True, exist_ok=True)

        def _download() -> int:
            request = Request(output.url, headers={"User-Agent": "libtv-agent-kling-cli/1"})
            with urlopen(
                request, timeout=self.settings.kling_cli_download_timeout_ms / 1000
            ) as response:
                status = int(getattr(response, "status", 200))
                if status < 200 or status >= 300:
                    raise OSError(f"unexpected HTTP status {status}")
                content_type = str(response.headers.get("Content-Type") or "")
                if content_type and not (
                    content_type.startswith("video/") or content_type == "application/octet-stream"
                ):
                    raise OSError("downloaded Kling output is not a video")
                with temporary.open("wb") as handle:
                    while chunk := response.read(1024 * 1024):
                        handle.write(chunk)
                declared_length = response.headers.get("Content-Length")
            size = temporary.stat().st_size
            if declared_length is not None and size != int(declared_length):
                raise OSError("downloaded output length does not match Content-Length")
            if size <= 0:
                raise OSError("downloaded Kling output is empty")
            return size

        try:
            size = await stage_download(
                _download,
                temporary,
                destination,
                timeout=self.settings.kling_cli_download_timeout_ms / 1000,
            )
        except Exception as exc:
            temporary.unlink(missing_ok=True)
            raise KlingCliError(
                "KLING_DOWNLOAD_FAILED",
                "Kling output download failed",
                retryable=True,
                details={"errorType": type(exc).__name__},
            ) from exc
        return DownloadResult(path=destination, reused=False, size_bytes=size)

    async def download_media(self, *, url: str, destination: Path) -> Path:
        return (
            await self.download(ProviderOutput(url=url, content_type="video"), destination)
        ).path

    async def get_account_status(self) -> dict[str, Any]:
        return await self._invoke("account")


async def retry_kling_call(
    operation: Callable[[], Awaitable[Any]], *, attempts: int = 3, base_delay: float = 1.0
) -> Any:
    for index in range(attempts):
        try:
            return await operation()
        except KlingCliError as exc:
            if not exc.retryable or index == attempts - 1:
                raise
            delay = max(
                base_delay * (2**index) + random.uniform(0, base_delay),
                exc.retry_after_seconds or 0,
            )
            await asyncio.sleep(delay)
    raise AssertionError("unreachable")
