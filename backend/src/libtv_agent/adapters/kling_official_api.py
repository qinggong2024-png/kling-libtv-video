from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import logging
import random
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlsplit
from urllib.request import Request, urlopen

from libtv_agent.adapters.kling_official_cli import KlingCliError
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
from PIL import Image

KLING_API_VERSION = "2.0"
KLING_OMNI_CREATE_PATH = "/omni-video/kling-3.0-omni"
KLING_TASKS_PATH = "/tasks"
KLING_API_STATUSES = frozenset({"submitted", "processing", "succeeded", "failed"})
KLING_IMAGE_TYPES = frozenset({".jpg", ".jpeg", ".png"})
KLING_MAX_IMAGE_BYTES = 50 * 1024 * 1024
logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ApiHttpResponse:
    status_code: int
    headers: dict[str, str]
    body: bytes


HttpRequest = Callable[
    [str, str, dict[str, str], bytes | None, float],
    Awaitable[ApiHttpResponse],
]


class KlingApiError(KlingCliError):
    def __init__(self, code: str, message: str, **kwargs: Any) -> None:
        super().__init__(code, message, **kwargs)
        self.provider = "kling_official_api"


def map_kling_api_status(raw_status: object) -> str:
    status = str(raw_status or "").strip()
    if status == "submitted":
        return "queued"
    if status == "processing":
        return "running"
    if status == "succeeded":
        return "succeeded"
    if status == "failed":
        return "failed"
    return "unknown"


def _retry_after(headers: dict[str, str]) -> float | None:
    value = next(
        (item for key, item in headers.items() if key.lower() == "retry-after"),
        None,
    )
    if value is None:
        return None
    try:
        return max(0.0, float(value))
    except ValueError:
        return None


def _classify_api_error(
    *,
    http_status: int,
    service_code: int | None,
    message: str,
    headers: dict[str, str],
    submitted: bool,
) -> KlingApiError:
    if http_status == 401 or service_code in {1000, 1001, 1002, 1003, 1004}:
        code = "KLING_API_AUTHENTICATION_FAILED"
        retryable = False
    elif service_code in {1100, 1101, 1102, 1103}:
        code = "KLING_API_ACCOUNT_UNAVAILABLE"
        retryable = False
    elif http_status == 429 or service_code in {1302, 1303}:
        code = "KLING_API_RATE_LIMITED"
        retryable = True
    elif service_code in {1200, 1201, 1202, 1203, 1300, 1301, 1304}:
        code = "KLING_API_VALIDATION_FAILED"
        retryable = False
    elif http_status >= 500 or service_code in {5000, 5001, 5002}:
        code = "KLING_API_SERVER_ERROR"
        retryable = True
    else:
        code = "KLING_API_RESPONSE_ERROR"
        retryable = False
    uncertain = submitted and http_status >= 500
    return KlingApiError(
        code,
        message or "Kling API request failed",
        retryable=retryable,
        details={"httpStatus": http_status, "serviceCode": service_code},
        submitted=submitted,
        uncertain=uncertain,
        retry_after_seconds=_retry_after(headers),
    )


class KlingOfficialApiAdapter:
    def __init__(
        self,
        settings: Settings,
        *,
        http_request: HttpRequest | None = None,
    ) -> None:
        self.settings = settings
        self._http_request = http_request or self._default_http_request
        self._submit_semaphore = asyncio.Semaphore(settings.kling_api_max_submit_concurrency)
        self._query_semaphore = asyncio.Semaphore(settings.kling_api_max_poll_concurrency)
        self._last_availability: ProviderAvailability | None = None
        self._capabilities: ProviderCapabilities | None = None

    def get_provider_name(self) -> str:
        return self.settings.kling_api_provider_name

    def availability_snapshot(self) -> ProviderAvailability:
        if self._last_availability is not None:
            return self._last_availability
        if not self.settings.kling_api_enabled:
            return ProviderAvailability(
                status="KLING_API_DISABLED",
                available=False,
                authenticated=False,
                reason="Kling official API Provider is disabled",
            )
        if not self.settings.kling_api_key:
            return ProviderAvailability(
                status="KLING_API_KEY_MISSING",
                available=False,
                authenticated=False,
                reason="KLING_API_KEY is not configured",
            )
        return ProviderAvailability(
            status="KLING_API_READY",
            available=True,
            authenticated=True,
            cli_version=f"api-{KLING_API_VERSION}",
        )

    def capabilities_snapshot(self) -> ProviderCapabilities | None:
        return self._capabilities

    async def check_availability(self) -> ProviderAvailability:
        self._last_availability = self.availability_snapshot()
        return self._last_availability

    async def refresh_capabilities(self, *, force: bool = False) -> ProviderCapabilities:
        del force
        if self._capabilities is None:
            self._capabilities = ProviderCapabilities(
                cli_version=f"api-{KLING_API_VERSION}",
                checked_at=datetime.now(UTC),
                authenticated=bool(self.settings.kling_api_key),
                account_type=None,
                supported_models=(self.settings.kling_api_model,),
                supported_tools=("omni_video_generation", "query_tasks"),
                video_durations=tuple(str(value) for value in range(3, 16)),
                aspect_ratios=("16:9", "9:16", "1:1"),
                image_input_limit=7,
                supports_tail_image=True,
                supports_multiple_images=True,
                supports_watermark_free_output=True,
                supports_sound_control=True,
                raw_capabilities={
                    "apiVersion": KLING_API_VERSION,
                    "createPath": KLING_OMNI_CREATE_PATH,
                    "queryPath": KLING_TASKS_PATH,
                    "statusValues": sorted(KLING_API_STATUSES),
                    "imageTypes": sorted(KLING_IMAGE_TYPES),
                    "maxImageBytes": KLING_MAX_IMAGE_BYTES,
                    "maxReferenceImages": 7,
                },
            )
        return self._capabilities

    async def login(self) -> ProviderAvailability:
        raise KlingApiError(
            "KLING_API_LOGIN_UNSUPPORTED",
            "Kling API 2.0 uses KLING_API_KEY; browser OAuth login is only for the CLI Provider",
        )

    async def logout(self) -> ProviderAvailability:
        raise KlingApiError(
            "KLING_API_LOGOUT_UNSUPPORTED",
            "Kling API keys are managed in the official developer console",
        )

    async def get_account_status(self) -> dict[str, Any]:
        availability = await self.check_availability()
        return {
            "provider": self.get_provider_name(),
            "status": availability.status,
            "configured": availability.authenticated,
        }

    async def validate_request(self, request: VideoGenerationRequest) -> str:
        prompt = request.prompt
        if not prompt.strip():
            raise KlingApiError("KLING_INVALID_INPUT", "Video prompt cannot be empty")
        if len(prompt) > 3072:
            raise KlingApiError(
                "KLING_INVALID_INPUT",
                "Kling 3.0 Omni prompts cannot exceed 3072 characters",
            )
        if not request.image_paths:
            raise KlingApiError(
                "KLING_INVALID_INPUT",
                "At least one ordered storyboard image is required",
            )
        paths = (*request.image_paths, *request.product_reference_paths)
        if len(paths) > 7:
            raise KlingApiError(
                "KLING_IMAGE_INPUT_LIMIT_EXCEEDED",
                "Kling 3.0 Omni accepts at most 7 reference images for this request type",
            )
        if request.duration is not None and request.duration not in range(3, 16):
            raise KlingApiError(
                "KLING_INVALID_INPUT",
                "Kling 3.0 Omni duration must be between 3 and 15 seconds",
            )
        if request.aspect_ratio and request.aspect_ratio not in {"16:9", "9:16", "1:1"}:
            raise KlingApiError(
                "KLING_INVALID_INPUT",
                "Kling 3.0 Omni aspect ratio must be 16:9, 9:16, or 1:1",
            )
        if request.resolution and request.resolution not in {"720p", "1080p", "4k"}:
            raise KlingApiError("KLING_INVALID_INPUT", "Unsupported Kling API resolution")
        if request.audio and request.audio not in {"native", "off"}:
            raise KlingApiError("KLING_INVALID_INPUT", "Unsupported Kling API audio mode")
        for path in paths:
            await asyncio.to_thread(self._validate_image, path)
        return self.settings.kling_api_model

    def _validate_image(self, path: Path) -> None:
        if not path.is_file():
            raise KlingApiError(
                "KLING_INVALID_INPUT",
                f"Reference image is unavailable: {path.name}",
            )
        if path.suffix.lower() not in KLING_IMAGE_TYPES:
            raise KlingApiError(
                "KLING_INVALID_INPUT",
                f"Kling API only accepts JPG/JPEG/PNG images: {path.name}",
            )
        size = path.stat().st_size
        limit = min(self.settings.max_input_image_bytes, KLING_MAX_IMAGE_BYTES)
        if size <= 0 or size > limit:
            raise KlingApiError(
                "KLING_INVALID_INPUT",
                f"Reference image exceeds the configured {limit}-byte limit: {path.name}",
            )
        try:
            with Image.open(path) as image:
                width, height = image.size
        except OSError as exc:
            raise KlingApiError(
                "KLING_INVALID_INPUT",
                f"Reference image is unreadable: {path.name}",
            ) from exc
        ratio = width / height if height else 0
        if width < 300 or height < 300 or not 0.4 <= ratio <= 2.5:
            raise KlingApiError(
                "KLING_INVALID_INPUT",
                "Kling API images must be at least 300px per side with aspect ratio "
                f"between 1:2.5 and 2.5:1: {path.name}",
            )

    async def build_request_payload(self, request: VideoGenerationRequest) -> dict[str, Any]:
        await self.validate_request(request)
        if not request.external_task_id:
            raise KlingApiError(
                "KLING_INVALID_INPUT",
                "external_task_id is required to prevent duplicate paid submissions",
            )
        ordered_paths = [*request.image_paths, *request.product_reference_paths]
        encoded = await asyncio.gather(
            *(asyncio.to_thread(self._encode_image, path) for path in ordered_paths)
        )
        contents: list[dict[str, Any]] = [{"type": "prompt", "text": request.prompt}]
        for index, data in enumerate(encoded, start=1):
            contents.append(
                {
                    "type": "first_frame" if index == 1 else "refer_image",
                    "url": data,
                    "id": f"image_{index}",
                }
            )
        settings: dict[str, Any] = {
            "resolution": request.resolution or self.settings.kling_api_resolution,
            "duration": request.duration or self.settings.kling_api_duration,
            "audio": request.audio or self.settings.kling_api_audio,
            "multi_shot": (
                request.multi_shot
                if request.multi_shot is not None
                else self.settings.kling_api_multi_shot
            ),
        }
        if request.aspect_ratio:
            settings["aspect_ratio"] = request.aspect_ratio
        else:
            settings["aspect_ratio"] = self.settings.kling_api_aspect_ratio
        options: dict[str, Any] = {
            "external_task_id": request.external_task_id,
            "watermark_info": {"enabled": False},
        }
        callback_url = request.callback_url or self.settings.kling_api_callback_url
        if callback_url:
            options["callback_url"] = callback_url
        return {"contents": contents, "settings": settings, "options": options}

    async def request_summary(self, request: VideoGenerationRequest) -> dict[str, Any]:
        await self.validate_request(request)
        paths = [*request.image_paths, *request.product_reference_paths]
        assets = await asyncio.gather(
            *(
                asyncio.to_thread(self._asset_summary, path, index)
                for index, path in enumerate(paths, 1)
            )
        )
        return {
            "provider": self.get_provider_name(),
            "endpoint": KLING_OMNI_CREATE_PATH,
            "model": self.settings.kling_api_model,
            "promptSha256": hashlib.sha256(request.prompt.encode("utf-8")).hexdigest(),
            "promptLength": len(request.prompt),
            "contents": list(assets),
            "settings": {
                "resolution": request.resolution or self.settings.kling_api_resolution,
                "duration": request.duration or self.settings.kling_api_duration,
                "aspectRatio": request.aspect_ratio or self.settings.kling_api_aspect_ratio,
                "audio": request.audio or self.settings.kling_api_audio,
                "multiShot": (
                    request.multi_shot
                    if request.multi_shot is not None
                    else self.settings.kling_api_multi_shot
                ),
            },
            "externalTaskId": request.external_task_id,
        }

    @staticmethod
    def _encode_image(path: Path) -> str:
        return base64.b64encode(path.read_bytes()).decode("ascii")

    @staticmethod
    def _asset_summary(path: Path, index: int) -> dict[str, Any]:
        content = path.read_bytes()
        return {
            "type": "first_frame" if index == 1 else "refer_image",
            "id": f"image_{index}",
            "filename": path.name,
            "sizeBytes": len(content),
            "sha256": hashlib.sha256(content).hexdigest(),
        }

    async def submit(self, request: VideoGenerationRequest) -> ProviderSubmissionResult:
        payload = await self.build_request_payload(request)
        response: dict[str, Any] | None = None
        last_error: KlingApiError | None = None
        for retry_index in range(self.settings.kling_api_max_retries):
            try:
                async with self._submit_semaphore:
                    response = await self._request_json(
                        "POST",
                        KLING_OMNI_CREATE_PATH,
                        payload,
                        submitted=True,
                    )
                break
            except KlingApiError as exc:
                last_error = exc
                if exc.uncertain and request.external_task_id:
                    try:
                        recovered = await self._query_one(
                            external_task_id=request.external_task_id,
                            missing_ok=True,
                        )
                    except KlingApiError as recovery_error:
                        if not recovery_error.retryable:
                            raise
                        recovered = None
                    if recovered is not None:
                        return self._submission_result(recovered, recovered=True)
                if not exc.retryable or retry_index + 1 >= self.settings.kling_api_max_retries:
                    raise
                delay = max(
                    exc.retry_after_seconds or 0,
                    (2**retry_index) + random.uniform(0, 0.5),
                )
                await asyncio.sleep(delay)
        if response is None:
            if last_error is not None:
                raise last_error
            raise KlingApiError(
                "KLING_API_RESPONSE_INVALID",
                "Kling API submission ended without a response",
            )
        data = response.get("data")
        if not isinstance(data, dict):
            raise KlingApiError(
                "KLING_API_RESPONSE_INVALID",
                "Kling API create response data must be an object",
                submitted=True,
                uncertain=True,
            )
        return self._submission_result(data)

    def _submission_result(
        self,
        data: dict[str, Any],
        *,
        recovered: bool = False,
    ) -> ProviderSubmissionResult:
        task_id = data.get("id")
        raw_status = data.get("status")
        if not isinstance(task_id, str) or not task_id:
            raise KlingApiError(
                "KLING_API_RESPONSE_INVALID",
                "Kling API create response is missing data.id",
                submitted=True,
                uncertain=True,
            )
        if raw_status not in KLING_API_STATUSES:
            raise KlingApiError(
                "KLING_API_RESPONSE_INVALID",
                "Kling API create response contains an unknown status",
                provider_task_id=task_id,
                raw_status=str(raw_status or ""),
                submitted=True,
                uncertain=True,
            )
        raw = dict(data)
        if recovered:
            raw["recoveredByExternalTaskId"] = True
        logger.info(
            "Kling API task accepted",
            extra={
                "provider": self.get_provider_name(),
                "provider_task_id": task_id,
                "provider_status": raw_status,
                "recovered": recovered,
            },
        )
        return ProviderSubmissionResult(
            provider_task_id=task_id,
            raw_status=str(raw_status),
            credits_consumed=_billing_units(data),
            provider_model=self.settings.kling_api_model,
            raw_response=raw,
        )

    async def query(self, provider_task_id: str) -> ProviderTaskResult:
        if not provider_task_id:
            raise KlingApiError("KLING_INVALID_INPUT", "Kling task ID is required")
        async with self._query_semaphore:
            data = await self._query_one(task_id=provider_task_id)
        if data is None:
            raise KlingApiError(
                "KLING_API_TASK_NOT_FOUND",
                "Kling API task was not found",
                provider_task_id=provider_task_id,
            )
        return self._task_result(data)

    async def _query_one(
        self,
        *,
        task_id: str | None = None,
        external_task_id: str | None = None,
        missing_ok: bool = False,
    ) -> dict[str, Any] | None:
        if bool(task_id) == bool(external_task_id):
            raise ValueError("exactly one Kling task identifier is required")
        query = urlencode(
            {"task_ids": task_id}
            if task_id
            else {"external_task_ids": external_task_id or ""}
        )
        response = await self._request_json("GET", f"{KLING_TASKS_PATH}?{query}", None)
        data = response.get("data")
        if not isinstance(data, list):
            raise KlingApiError(
                "KLING_API_RESPONSE_INVALID",
                "Kling API task query data must be an array",
            )
        matches = [item for item in data if isinstance(item, dict)]
        if not matches:
            return None if missing_ok else None
        expected_key = "id" if task_id else "external_id"
        expected_value = task_id or external_task_id
        exact = [item for item in matches if item.get(expected_key) == expected_value]
        if len(exact) != 1:
            raise KlingApiError(
                "KLING_API_RESPONSE_INVALID",
                "Kling API task query did not return exactly one matching task",
            )
        return exact[0]

    def _task_result(self, data: dict[str, Any]) -> ProviderTaskResult:
        raw_status = data.get("status")
        status = map_kling_api_status(raw_status)
        outputs_value = data.get("outputs")
        if outputs_value is not None and not isinstance(outputs_value, list):
            raise KlingApiError(
                "KLING_API_RESPONSE_INVALID",
                "Kling API task outputs must be an array",
            )
        outputs: list[ProviderOutput] = []
        for item in outputs_value or []:
            if not isinstance(item, dict) or item.get("type") != "video":
                continue
            url = item.get("url")
            if isinstance(url, str) and url:
                outputs.append(
                    ProviderOutput(
                        url=url,
                        content_type="video",
                        url_without_watermark=url,
                        cover_url=None,
                    )
                )
        if status == "succeeded" and not outputs:
            raise KlingApiError(
                "KLING_OUTPUT_URL_MISSING",
                "Kling API task succeeded without outputs[].url",
                provider_task_id=str(data.get("id") or ""),
                raw_status=str(raw_status or ""),
            )
        logger.info(
            "Kling API task status",
            extra={
                "provider": self.get_provider_name(),
                "provider_task_id": str(data.get("id") or ""),
                "provider_status": str(raw_status or ""),
            },
        )
        return ProviderTaskResult(
            status=status,
            raw_status=str(raw_status or ""),
            outputs=tuple(outputs),
            raw_response=data,
            credits_consumed=_billing_units(data),
        )

    async def _request_json(
        self,
        method: str,
        path: str,
        payload: dict[str, Any] | None,
        *,
        submitted: bool = False,
    ) -> dict[str, Any]:
        key = self.settings.kling_api_key
        if not key:
            raise KlingApiError(
                "KLING_API_KEY_MISSING",
                "KLING_API_KEY is not configured",
            )
        body = (
            json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
            if payload is not None
            else None
        )
        headers = {
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
            "User-Agent": "libtv-agent-kling-api/2",
        }
        started_at = time.monotonic()
        try:
            response = await self._http_request(
                method,
                f"{self.settings.kling_api_base_url}{path}",
                headers,
                body,
                self.settings.kling_api_request_timeout_seconds,
            )
        except (TimeoutError, URLError, OSError) as exc:
            logger.warning(
                "Kling API network request failed",
                extra={
                    "provider": self.get_provider_name(),
                    "http_method": method,
                    "endpoint": path.split("?", 1)[0],
                    "duration_ms": round((time.monotonic() - started_at) * 1000),
                    "error_category": type(exc).__name__,
                },
            )
            raise KlingApiError(
                "KLING_API_NETWORK_ERROR",
                "Kling API network request failed",
                retryable=True,
                details={"errorType": type(exc).__name__},
                submitted=submitted,
                uncertain=submitted,
            ) from exc
        logger.info(
            "Kling API response",
            extra={
                "provider": self.get_provider_name(),
                "http_method": method,
                "endpoint": path.split("?", 1)[0],
                "http_status": response.status_code,
                "duration_ms": round((time.monotonic() - started_at) * 1000),
            },
        )
        try:
            decoded = json.loads(response.body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise KlingApiError(
                "KLING_API_RESPONSE_INVALID",
                "Kling API returned invalid JSON",
                retryable=response.status_code >= 500,
                details={"httpStatus": response.status_code},
                submitted=submitted,
                uncertain=submitted,
            ) from exc
        if not isinstance(decoded, dict):
            raise KlingApiError(
                "KLING_API_RESPONSE_INVALID",
                "Kling API response must be an object",
                submitted=submitted,
                uncertain=submitted,
            )
        service_code = decoded.get("code")
        parsed_code = service_code if isinstance(service_code, int) else None
        if not 200 <= response.status_code < 300 or parsed_code != 0:
            raise _classify_api_error(
                http_status=response.status_code,
                service_code=parsed_code,
                message=str(decoded.get("message") or "Kling API request failed"),
                headers=response.headers,
                submitted=submitted,
            )
        return decoded

    @staticmethod
    async def _default_http_request(
        method: str,
        url: str,
        headers: dict[str, str],
        body: bytes | None,
        request_timeout: float,
    ) -> ApiHttpResponse:
        def send() -> ApiHttpResponse:
            request = Request(url, data=body, headers=headers, method=method)
            try:
                with urlopen(request, timeout=request_timeout) as response:
                    return ApiHttpResponse(
                        status_code=int(getattr(response, "status", 200)),
                        headers=dict(response.headers.items()),
                        body=response.read(),
                    )
            except HTTPError as exc:
                return ApiHttpResponse(
                    status_code=exc.code,
                    headers=dict(exc.headers.items()) if exc.headers else {},
                    body=exc.read(),
                )

        return await asyncio.to_thread(send)

    async def download(self, output: ProviderOutput, destination: Path) -> DownloadResult:
        existing_size = await asyncio.to_thread(
            lambda: destination.stat().st_size if destination.is_file() else 0
        )
        if existing_size > 0:
            return DownloadResult(path=destination, reused=True, size_bytes=existing_size)
        temporary = destination.with_suffix(f"{destination.suffix}.part")
        destination.parent.mkdir(parents=True, exist_ok=True)

        def download_file() -> int:
            request = Request(
                output.url,
                headers={"User-Agent": "libtv-agent-kling-api/2"},
            )
            with urlopen(
                request,
                timeout=self.settings.kling_api_download_timeout_seconds,
            ) as response:
                status = int(getattr(response, "status", 200))
                if not 200 <= status < 300:
                    raise OSError(f"unexpected HTTP status {status}")
                content_type = str(response.headers.get("Content-Type") or "")
                if content_type and not (
                    content_type.startswith("video/")
                    or content_type == "application/octet-stream"
                ):
                    raise OSError("downloaded Kling output is not a video")
                with temporary.open("wb") as handle:
                    while chunk := response.read(1024 * 1024):
                        handle.write(chunk)
            size = temporary.stat().st_size
            if size <= 0:
                raise OSError("downloaded Kling output is empty")
            temporary.replace(destination)
            return size

        try:
            started_at = time.monotonic()
            size = await asyncio.wait_for(
                asyncio.to_thread(download_file),
                timeout=self.settings.kling_api_download_timeout_seconds,
            )
        except Exception as exc:
            temporary.unlink(missing_ok=True)
            raise KlingApiError(
                "KLING_DOWNLOAD_FAILED",
                "Kling API output download failed",
                retryable=True,
                details={"errorType": type(exc).__name__},
            ) from exc
        logger.info(
            "Kling API output downloaded",
            extra={
                "provider": self.get_provider_name(),
                "output_host": urlsplit(output.url).hostname,
                "output_path": str(destination),
                "size_bytes": size,
                "duration_ms": round((time.monotonic() - started_at) * 1000),
            },
        )
        return DownloadResult(path=destination, reused=False, size_bytes=size)

    async def download_media(self, *, url: str, destination: Path) -> Path:
        return (
            await self.download(ProviderOutput(url=url, content_type="video"), destination)
        ).path


def _billing_units(data: dict[str, Any]) -> int | None:
    billing = data.get("billing")
    if not isinstance(billing, list):
        return None
    total = 0.0
    found = False
    for item in billing:
        if not isinstance(item, dict) or item.get("charge_type") != "unit":
            continue
        try:
            total += float(item["amount"])
        except (KeyError, TypeError, ValueError):
            return None
        found = True
    if found and total.is_integer():
        return int(total)
    return None
