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
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode, urlsplit
from urllib.request import Request, urlopen

from libtv_agent.adapters.kling_official_cli import KlingCliError
from libtv_agent.adapters.video_provider import (
    DownloadResult,
    ProviderAvailability,
    ProviderBillingCharge,
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
KLING_READ_ONLY_VERIFICATION_ID = "libtv-read-only-provider-verification"
KLING_ELEMENTS_PATH = "/v1/general/advanced-custom-elements"
KLING_PRESET_ELEMENTS_PATH = "/v1/general/advanced-presets-elements"
KLING_DELETE_ELEMENT_PATH = "/v1/general/delete-advanced-elements"
KLING_API_STATUSES = frozenset({"submitted", "processing", "succeeded", "failed"})
KLING_IMAGE_TYPES = frozenset({".jpg", ".jpeg", ".png"})
KLING_MAX_IMAGE_BYTES = 50 * 1024 * 1024
logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ApiHttpResponse:
    status_code: int
    headers: dict[str, str]
    body: bytes


@dataclass(frozen=True)
class KlingTaskPage:
    tasks: tuple[ProviderTaskResult, ...]
    count: int
    next_cursor: str | None
    has_more: bool
    raw_response: dict[str, Any]


@dataclass(frozen=True)
class KlingElementCreateRequest:
    element_name: str
    element_description: str
    reference_type: str
    frontal_image: str | None = None
    refer_images: tuple[str, ...] = ()
    refer_videos: tuple[str, ...] = ()
    element_voice_id: str | None = None
    tag_ids: tuple[str, ...] = ()
    callback_url: str | None = None
    external_task_id: str | None = None


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
            status="KLING_API_CONFIGURED_UNVERIFIED",
            available=False,
            authenticated=False,
            reason=(
                "Kling API credentials are configured but have not passed the "
                "official read-only task-query verification"
            ),
        )

    def capabilities_snapshot(self) -> ProviderCapabilities | None:
        return self._capabilities

    async def check_availability(self) -> ProviderAvailability:
        if not self.settings.kling_api_enabled or not self.settings.kling_api_key:
            self._last_availability = None
            return self.availability_snapshot()
        if self._last_availability and self._last_availability.available:
            return self._last_availability
        try:
            # This endpoint is the same official read-only task query used for
            # recovery. It cannot create media or consume generation credits.
            verification_query = urlencode({"external_task_ids": KLING_READ_ONLY_VERIFICATION_ID})
            await self._request_json(
                "GET",
                f"{KLING_TASKS_PATH}?{verification_query}",
                None,
            )
        except KlingApiError as exc:
            authentication_failed = exc.code == "KLING_API_AUTHENTICATION_FAILED"
            self._last_availability = ProviderAvailability(
                status=(
                    "KLING_API_AUTHENTICATION_FAILED"
                    if authentication_failed
                    else "KLING_API_VERIFICATION_FAILED"
                ),
                available=False,
                authenticated=False,
                reason=str(exc),
                cli_version=f"api-{KLING_API_VERSION}",
            )
            return self._last_availability
        self._last_availability = ProviderAvailability(
            status="KLING_API_READY",
            available=True,
            authenticated=True,
            reason=None,
            cli_version=f"api-{KLING_API_VERSION}",
        )
        return self._last_availability

    async def refresh_capabilities(self, *, force: bool = False) -> ProviderCapabilities:
        if force:
            self._last_availability = None
            self._capabilities = None
        availability = await self.check_availability()
        if not availability.available:
            raise KlingApiError(
                availability.status,
                availability.reason or "Kling API verification has not completed",
            )
        if self._capabilities is None:
            self._capabilities = ProviderCapabilities(
                cli_version=f"api-{KLING_API_VERSION}",
                checked_at=datetime.now(UTC),
                authenticated=bool(self.settings.kling_api_key),
                account_type=None,
                supported_models=(self.settings.kling_api_model,),
                supported_tools=(
                    "omni_video_generation",
                    "query_tasks",
                    "query_tasks_cursor",
                    "element_management",
                ),
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
        image_inputs = self._request_image_inputs(request)
        if request.last_frame_path is not None and not any(
            role == "first_frame" for role, _ in image_inputs
        ):
            raise KlingApiError(
                "KLING_INVALID_INPUT",
                "Kling 3.0 Omni does not accept a last frame without a first frame",
            )
        if len(image_inputs) + len(request.element_references) > 7:
            raise KlingApiError(
                "KLING_IMAGE_INPUT_LIMIT_EXCEEDED",
                "Kling 3.0 Omni accepts at most 7 image and element references",
            )
        if request.feature_video_url and request.base_video_url:
            raise KlingApiError(
                "KLING_INVALID_INPUT",
                "feature_video and base_video are mutually exclusive",
            )
        for label, url in (
            ("feature_video", request.feature_video_url),
            ("base_video", request.base_video_url),
        ):
            if url and urlsplit(url).scheme not in {"http", "https"}:
                raise KlingApiError(
                    "KLING_INVALID_INPUT",
                    f"{label} must be an accessible HTTP(S) URL",
                )
        content_ids = [item.content_id.strip() for item in request.element_references]
        element_ids = [item.element_id.strip() for item in request.element_references]
        if any(
            not item.element_id.strip() or not item.content_id.strip()
            for item in request.element_references
        ):
            raise KlingApiError(
                "KLING_INVALID_INPUT",
                "Every element reference requires element_id and content_id",
            )
        if len(content_ids) != len(set(content_ids)):
            raise KlingApiError("KLING_INVALID_INPUT", "Element content IDs must be unique")
        if len(element_ids) != len(set(element_ids)):
            raise KlingApiError("KLING_INVALID_INPUT", "Element IDs must be unique")
        generated_ids = {f"image_{index}" for index in range(1, len(image_inputs) + 1)}
        if request.feature_video_url or request.base_video_url:
            generated_ids.add("video_1")
        if generated_ids.intersection(content_ids):
            raise KlingApiError(
                "KLING_INVALID_INPUT",
                "Element content IDs cannot collide with generated image or video IDs",
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
        if request.audio and request.audio not in {"native", "original", "off"}:
            raise KlingApiError("KLING_INVALID_INPUT", "Unsupported Kling API audio mode")
        for _, path in image_inputs:
            await asyncio.to_thread(self._validate_image, path)
        return self.settings.kling_api_model

    @staticmethod
    def _request_image_inputs(
        request: VideoGenerationRequest,
    ) -> list[tuple[str, Path]]:
        legacy = list(request.image_paths)
        first_frame = request.first_frame_path
        if first_frame is None and legacy:
            first_frame = legacy.pop(0)
        inputs: list[tuple[str, Path]] = []
        if first_frame is not None:
            inputs.append(("first_frame", first_frame))
        if request.last_frame_path is not None:
            inputs.append(("last_frame", request.last_frame_path))
        inputs.extend(("refer_image", path) for path in legacy)
        inputs.extend(("refer_image", path) for path in request.refer_image_paths)
        inputs.extend(("refer_image", path) for path in request.product_reference_paths)
        return inputs

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
        image_inputs = self._request_image_inputs(request)
        encoded = await asyncio.gather(
            *(asyncio.to_thread(self._encode_image, path) for _, path in image_inputs)
        )
        contents: list[dict[str, Any]] = [{"type": "prompt", "text": request.prompt}]
        for index, ((role, _), data) in enumerate(zip(image_inputs, encoded, strict=True), start=1):
            contents.append(
                {
                    "type": role,
                    "url": data,
                    "id": f"image_{index}",
                }
            )
        video_url = request.feature_video_url or request.base_video_url
        if video_url:
            contents.append(
                {
                    "type": "feature_video" if request.feature_video_url else "base_video",
                    "url": video_url,
                    "id": "video_1",
                }
            )
        contents.extend(
            {
                "type": "element",
                "element_id": reference.element_id,
                "id": reference.content_id,
            }
            for reference in request.element_references
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
        image_inputs = self._request_image_inputs(request)
        assets = await asyncio.gather(
            *(
                asyncio.to_thread(self._asset_summary, path, index, role)
                for index, (role, path) in enumerate(image_inputs, 1)
            )
        )
        return {
            "provider": self.get_provider_name(),
            "endpoint": KLING_OMNI_CREATE_PATH,
            "model": self.settings.kling_api_model,
            "promptSha256": hashlib.sha256(request.prompt.encode("utf-8")).hexdigest(),
            "promptLength": len(request.prompt),
            "contents": [
                *assets,
                *(
                    [
                        {
                            "type": (
                                "feature_video" if request.feature_video_url else "base_video"
                            ),
                            "id": "video_1",
                            "urlHost": urlsplit(
                                request.feature_video_url or request.base_video_url or ""
                            ).hostname,
                        }
                    ]
                    if request.feature_video_url or request.base_video_url
                    else []
                ),
                *[
                    {
                        "type": "element",
                        "id": reference.content_id,
                        "elementId": reference.element_id,
                    }
                    for reference in request.element_references
                ],
            ],
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
    def _asset_summary(path: Path, index: int, role: str) -> dict[str, Any]:
        content = path.read_bytes()
        return {
            "type": role,
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
            billing=_parse_billing(data),
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

    async def query_many(
        self,
        *,
        task_ids: tuple[str, ...] = (),
        external_task_ids: tuple[str, ...] = (),
    ) -> tuple[ProviderTaskResult, ...]:
        if bool(task_ids) == bool(external_task_ids):
            raise KlingApiError(
                "KLING_INVALID_INPUT",
                "Provide exactly one of task_ids or external_task_ids",
            )
        identifiers = task_ids or external_task_ids
        if any(not identifier.strip() for identifier in identifiers):
            raise KlingApiError("KLING_INVALID_INPUT", "Kling task IDs cannot be empty")
        parameter = "task_ids" if task_ids else "external_task_ids"
        query = urlencode({parameter: ",".join(identifiers)})
        async with self._query_semaphore:
            response = await self._request_json("GET", f"{KLING_TASKS_PATH}?{query}", None)
        data = response.get("data")
        if not isinstance(data, list):
            raise KlingApiError(
                "KLING_API_RESPONSE_INVALID",
                "Kling API batch task query data must be an array",
            )
        return tuple(self._task_result(item) for item in data if isinstance(item, dict))

    async def query_tasks_cursor(
        self,
        *,
        start_time: int | None = None,
        end_time: int | None = None,
        cursor: str | None = None,
        limit: int = 100,
        filters: tuple[dict[str, Any], ...] = (),
    ) -> KlingTaskPage:
        if not 1 <= limit <= 500:
            raise KlingApiError("KLING_INVALID_INPUT", "Kling task query limit must be 1..500")
        if cursor and (start_time is not None or end_time is not None):
            raise KlingApiError(
                "KLING_INVALID_INPUT",
                "Cursor queries cannot also specify start_time or end_time",
            )
        if start_time is not None and end_time is not None and start_time >= end_time:
            raise KlingApiError("KLING_INVALID_INPUT", "start_time must be before end_time")
        payload: dict[str, Any] = {"limit": limit}
        if cursor:
            payload["cursor"] = cursor
        else:
            if start_time is not None:
                payload["start_time"] = str(start_time)
            if end_time is not None:
                payload["end_time"] = str(end_time)
        if filters:
            payload["filters"] = list(filters)
        async with self._query_semaphore:
            response = await self._request_json("POST", KLING_TASKS_PATH, payload)
        data = response.get("data")
        if not isinstance(data, dict) or not isinstance(data.get("result"), list):
            raise KlingApiError(
                "KLING_API_RESPONSE_INVALID",
                "Kling API cursor task query data must contain result[]",
            )
        tasks = tuple(self._task_result(item) for item in data["result"] if isinstance(item, dict))
        count = data.get("count")
        return KlingTaskPage(
            tasks=tasks,
            count=count if isinstance(count, int) else len(tasks),
            next_cursor=(
                str(data["next_cursor"]) if data.get("next_cursor") not in {None, ""} else None
            ),
            has_more=bool(data.get("has_more")),
            raw_response=response,
        )

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
            {"task_ids": task_id} if task_id else {"external_task_ids": external_task_id or ""}
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
                watermark_url = item.get("watermark_url")
                outputs.append(
                    ProviderOutput(
                        url=url,
                        content_type="video",
                        url_without_watermark=url,
                        cover_url=None,
                        watermark_url=(
                            watermark_url
                            if isinstance(watermark_url, str) and watermark_url
                            else None
                        ),
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
            message=str(data["message"]) if data.get("message") is not None else None,
            billing=_parse_billing(data),
        )

    async def create_element(
        self,
        request: KlingElementCreateRequest | dict[str, Any],
    ) -> dict[str, Any]:
        if isinstance(request, dict):
            image_urls = tuple(
                str(value) for value in request.get("imageUrls", request.get("image_urls", ()))
            )
            video_url = request.get("videoUrl") or request.get("video_url")
            name = str(request.get("element_name") or request.get("name") or "")
            request = KlingElementCreateRequest(
                element_name=name,
                element_description=str(
                    request.get("element_description") or request.get("description") or name
                ),
                reference_type="image_refer" if image_urls else "video_refer",
                frontal_image=image_urls[0] if image_urls else None,
                refer_images=image_urls[1:],
                refer_videos=(str(video_url),) if video_url else (),
                element_voice_id=(
                    str(request.get("element_voice_id") or request.get("voiceId"))
                    if request.get("element_voice_id") or request.get("voiceId")
                    else None
                ),
            )
        self._validate_element_create_request(request)
        payload: dict[str, Any] = {
            "element_name": request.element_name,
            "element_description": request.element_description,
            "reference_type": request.reference_type,
        }
        if request.reference_type == "image_refer":
            payload["element_image_list"] = {
                "frontal_image": request.frontal_image,
                "refer_images": [{"image_url": image_url} for image_url in request.refer_images],
            }
        else:
            payload["element_video_list"] = {
                "refer_videos": [{"video_url": video_url} for video_url in request.refer_videos]
            }
        if request.element_voice_id:
            payload["element_voice_id"] = request.element_voice_id
        if request.tag_ids:
            payload["tag_list"] = [{"tag_id": tag_id} for tag_id in request.tag_ids]
        if request.callback_url:
            payload["callback_url"] = request.callback_url
        if request.external_task_id:
            payload["external_task_id"] = request.external_task_id
        return await self._request_json("POST", KLING_ELEMENTS_PATH, payload, submitted=True)

    @staticmethod
    def _validate_element_create_request(request: KlingElementCreateRequest) -> None:
        if not request.element_name.strip() or len(request.element_name) > 20:
            raise KlingApiError(
                "KLING_INVALID_INPUT",
                "Element name is required and cannot exceed 20 characters",
            )
        if not request.element_description.strip() or len(request.element_description) > 100:
            raise KlingApiError(
                "KLING_INVALID_INPUT",
                "Element description is required and cannot exceed 100 characters",
            )
        if request.reference_type not in {"image_refer", "video_refer"}:
            raise KlingApiError(
                "KLING_INVALID_INPUT",
                "Element reference_type must be image_refer or video_refer",
            )
        if request.reference_type == "image_refer":
            if not request.frontal_image or not 1 <= len(request.refer_images) <= 3:
                raise KlingApiError(
                    "KLING_INVALID_INPUT",
                    "Image elements require a frontal image and 1..3 reference images",
                )
            if request.refer_videos:
                raise KlingApiError(
                    "KLING_INVALID_INPUT",
                    "Image elements cannot include reference videos",
                )
        elif len(request.refer_videos) != 1 or request.frontal_image or request.refer_images:
            raise KlingApiError(
                "KLING_INVALID_INPUT",
                "Video elements require exactly one reference video and no images",
            )

    async def query_element(
        self,
        *,
        task_id: str | None = None,
        external_task_id: str | None = None,
    ) -> dict[str, Any]:
        if bool(task_id) == bool(external_task_id):
            raise KlingApiError(
                "KLING_INVALID_INPUT",
                "Provide exactly one element task_id or external_task_id",
            )
        identifier = task_id or external_task_id or ""
        return await self._request_json(
            "GET",
            f"{KLING_ELEMENTS_PATH}/{quote(identifier, safe='')}",
            None,
        )

    async def get_element(self, element_id: str) -> dict[str, Any]:
        return await self.query_element(task_id=element_id)

    async def list_elements(
        self,
        *,
        page_num: int = 1,
        page_size: int = 30,
        cursor: str | None = None,
        limit: int | None = None,
        official: bool = False,
    ) -> dict[str, Any]:
        if cursor:
            try:
                page_num = int(cursor)
            except ValueError as exc:
                raise KlingApiError(
                    "KLING_INVALID_INPUT",
                    "Element list cursor must be a numeric page number",
                ) from exc
        if limit is not None:
            page_size = limit
        if not 1 <= page_num <= 1000 or not 1 <= page_size <= 500:
            raise KlingApiError(
                "KLING_INVALID_INPUT",
                "Element page_num must be 1..1000 and page_size must be 1..500",
            )
        path = KLING_PRESET_ELEMENTS_PATH if official else KLING_ELEMENTS_PATH
        return await self._request_json(
            "GET",
            f"{path}?{urlencode({'pageNum': page_num, 'pageSize': page_size})}",
            None,
        )

    async def delete_element(self, element_id: str) -> dict[str, Any]:
        if not element_id.strip():
            raise KlingApiError("KLING_INVALID_INPUT", "element_id is required")
        return await self._request_json(
            "POST",
            KLING_DELETE_ELEMENT_PATH,
            {"element_id": element_id},
            submitted=True,
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
        if existing_size > 0 and await asyncio.to_thread(_is_probably_video_file, destination):
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
                    content_type.startswith("video/") or content_type == "application/octet-stream"
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
    charges = _parse_billing(data)
    unit_amounts = [charge.amount for charge in charges if charge.charge_type == "unit"]
    if not unit_amounts:
        return None
    total = sum(unit_amounts, Decimal(0))
    return int(total) if total == total.to_integral_value() else None


def _parse_billing(data: dict[str, Any]) -> tuple[ProviderBillingCharge, ...]:
    value = data.get("billing")
    if value is None:
        return ()
    if not isinstance(value, list):
        raise KlingApiError(
            "KLING_API_RESPONSE_INVALID",
            "Kling API billing must be an array",
        )
    charges: list[ProviderBillingCharge] = []
    for item in value:
        if not isinstance(item, dict):
            raise KlingApiError(
                "KLING_API_RESPONSE_INVALID",
                "Kling API billing entries must be objects",
            )
        charge_type = item.get("charge_type")
        if charge_type not in {"cash", "unit"}:
            raise KlingApiError(
                "KLING_API_RESPONSE_INVALID",
                "Kling API billing charge_type must be cash or unit",
            )
        try:
            amount = Decimal(str(item["amount"]))
            list_price = (
                Decimal(str(item["list_price"])) if item.get("list_price") is not None else None
            )
        except (KeyError, InvalidOperation, TypeError, ValueError) as exc:
            raise KlingApiError(
                "KLING_API_RESPONSE_INVALID",
                "Kling API billing contains an invalid decimal amount",
            ) from exc
        if not amount.is_finite() or (list_price is not None and not list_price.is_finite()):
            raise KlingApiError(
                "KLING_API_RESPONSE_INVALID",
                "Kling API billing contains a non-finite decimal amount",
            )
        charges.append(
            ProviderBillingCharge(
                charge_type=charge_type,
                amount=amount,
                package_type=(
                    str(item["package_type"]) if item.get("package_type") is not None else None
                ),
                list_price=list_price,
            )
        )
    return tuple(charges)


def _is_probably_video_file(path: Path) -> bool:
    try:
        with path.open("rb") as handle:
            header = handle.read(16)
    except OSError:
        return False
    return (
        len(header) >= 8
        and header[4:8] == b"ftyp"
        or header.startswith(b"\x1aE\xdf\xa3")
        or header.startswith(b"RIFF")
        and header[8:12] == b"AVI "
    )
