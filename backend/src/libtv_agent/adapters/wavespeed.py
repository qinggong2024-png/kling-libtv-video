from __future__ import annotations

import asyncio
import json
import logging
import random
import time
import uuid
from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlsplit
from urllib.request import Request, urlopen

from libtv_agent.config import Settings

WAVESPEED_MODELS = {
    ("gpt-image-2", "edit"): "openai/gpt-image-2/edit",
    ("gpt-image-2", "text-to-image"): "openai/gpt-image-2/text-to-image",
    ("nano-banana-2", "edit"): "google/nano-banana-2/edit",
    ("nano-banana-2", "text-to-image"): "google/nano-banana-2/text-to-image",
}
WAVESPEED_MODEL_IDS = frozenset(WAVESPEED_MODELS.values())
WAVESPEED_STATUSES = frozenset(
    {"created", "processing", "completed", "failed", "cancelled", "timeout"}
)
WAVESPEED_TERMINAL_STATUSES = frozenset({"completed", "failed", "cancelled", "timeout"})
_RETRYABLE_GET_STATUSES = frozenset({429, 500, 502, 503, 504})
_ALLOWED_EXTENSIONS = frozenset({".jpg", ".jpeg", ".png", ".webp"})
_ALLOWED_CONTENT_TYPES = frozenset({"image/jpeg", "image/png", "image/webp"})
_CONTENT_TYPE_BY_EXTENSION = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".webp": "image/webp",
}
_RESOLUTIONS = frozenset({"1k", "2k", "4k"})
_QUALITIES = frozenset({"low", "medium", "high"})
_OUTPUT_FORMATS = frozenset({"png", "jpeg"})
_VERIFY_TASK_ID = "libtv-read-only-provider-verification"
logger = logging.getLogger(__name__)

ImageProvider = Literal["gpt-image-2", "nano-banana-2"]
ImageMode = Literal["edit", "text-to-image"]
PredictionStatus = Literal["created", "processing", "completed", "failed", "cancelled", "timeout"]


@dataclass(frozen=True)
class WaveSpeedHttpResponse:
    status_code: int
    headers: dict[str, str]
    body: bytes


@dataclass(frozen=True)
class WaveSpeedSubmission:
    task_id: str
    status: PredictionStatus
    model_id: str
    result_url: str
    raw_response: dict[str, Any]


@dataclass(frozen=True)
class WaveSpeedPrediction:
    task_id: str
    status: PredictionStatus
    outputs: tuple[str, ...]
    error: str | None
    model_id: str | None
    raw_response: dict[str, Any]


@dataclass(frozen=True)
class WaveSpeedAvailability:
    status: str
    available: bool
    authenticated: bool
    reason: str | None
    checked_at: datetime | None


class WaveSpeedError(RuntimeError):
    def __init__(
        self,
        code: str,
        message: str,
        *,
        status: int | None = None,
        task_id: str | None = None,
        model_id: str | None = None,
        retryable: bool = False,
        submitted: bool = False,
        uncertain: bool = False,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.status = status
        self.task_id = task_id
        self.model_id = model_id
        self.retryable = retryable
        self.submitted = submitted
        self.uncertain = uncertain
        self.details = details or {}


HttpRequest = Callable[
    [str, str, dict[str, str], bytes | None, float], Awaitable[WaveSpeedHttpResponse]
]


def model_id_for(provider: ImageProvider, mode: ImageMode) -> str:
    try:
        return WAVESPEED_MODELS[(provider, mode)]
    except KeyError as exc:
        raise WaveSpeedError(
            "WAVESPEED_INPUT_INVALID", f"unsupported provider/mode: {provider}/{mode}"
        ) from exc


def build_generation_payload(
    *,
    provider: ImageProvider,
    mode: ImageMode,
    prompt: str,
    images: Sequence[str] = (),
    aspect_ratio: str = "9:16",
    resolution: Literal["1k", "2k", "4k"] = "2k",
    quality: Literal["low", "medium", "high"] = "medium",
    output_format: Literal["png", "jpeg"] = "png",
) -> tuple[str, dict[str, object]]:
    normalized_prompt = prompt.strip()
    if not normalized_prompt:
        raise WaveSpeedError("WAVESPEED_INPUT_INVALID", "prompt is required")
    if len(normalized_prompt) > 32_000:
        raise WaveSpeedError("WAVESPEED_INPUT_INVALID", "prompt is too long")
    if not aspect_ratio.strip() or len(aspect_ratio) > 32:
        raise WaveSpeedError("WAVESPEED_INPUT_INVALID", "aspect_ratio is invalid")
    if resolution not in _RESOLUTIONS:
        raise WaveSpeedError("WAVESPEED_INPUT_INVALID", "resolution must be 1k, 2k, or 4k")
    if quality not in _QUALITIES:
        raise WaveSpeedError("WAVESPEED_INPUT_INVALID", "quality is invalid")
    if output_format not in _OUTPUT_FORMATS:
        raise WaveSpeedError("WAVESPEED_INPUT_INVALID", "output_format must be png or jpeg")

    normalized_images = tuple(_validate_remote_url(value, field="images") for value in images)
    if mode == "edit" and not normalized_images:
        raise WaveSpeedError("WAVESPEED_INPUT_INVALID", "edit mode requires reference images")
    if mode == "text-to-image" and normalized_images:
        raise WaveSpeedError("WAVESPEED_INPUT_INVALID", "text-to-image mode does not accept images")
    limit = 6 if provider == "gpt-image-2" else 4
    if len(normalized_images) > limit:
        raise WaveSpeedError(
            "WAVESPEED_INPUT_INVALID",
            f"{provider} edit accepts at most {limit} reference images",
        )

    payload: dict[str, object] = {
        "prompt": normalized_prompt,
        "aspect_ratio": aspect_ratio.strip(),
        "resolution": resolution,
        "output_format": output_format,
    }
    if mode == "edit":
        payload["images"] = list(normalized_images)
    if provider == "gpt-image-2":
        payload["quality"] = quality
    else:
        payload["enable_web_search"] = False
        payload["enable_image_search"] = False
    return model_id_for(provider, mode), payload


def _validate_remote_url(value: str, *, field: str) -> str:
    normalized = value.strip()
    parsed = urlsplit(normalized)
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.hostname
        or parsed.username
        or parsed.password
        or parsed.fragment
    ):
        raise WaveSpeedError("WAVESPEED_INPUT_INVALID", f"{field} must contain HTTP(S) URLs")
    return normalized


def _is_remote_source(value: object) -> bool:
    return isinstance(value, str) and urlsplit(value.strip()).scheme in {"http", "https"}


def _message_from_payload(payload: Mapping[str, Any], fallback: str) -> str:
    error = payload.get("error")
    if isinstance(error, str) and error.strip():
        return error.strip()
    if isinstance(error, Mapping):
        message = error.get("message")
        if isinstance(message, str) and message.strip():
            return message.strip()
    message = payload.get("message")
    return message.strip() if isinstance(message, str) and message.strip() else fallback


def _error_for_response(
    response: WaveSpeedHttpResponse,
    payload: Mapping[str, Any],
    *,
    submitted: bool,
) -> WaveSpeedError:
    status = response.status_code
    if status == 400:
        code = "WAVESPEED_VALIDATION_FAILED"
    elif status == 401:
        code = "WAVESPEED_AUTHENTICATION_FAILED"
    elif status == 402:
        code = "WAVESPEED_BALANCE_INSUFFICIENT"
    elif status == 413:
        code = "WAVESPEED_FILE_TOO_LARGE"
    elif status == 429:
        code = "WAVESPEED_RATE_LIMITED"
    elif status in {500, 502, 503, 504}:
        code = "WAVESPEED_SERVICE_UNAVAILABLE"
    else:
        code = "WAVESPEED_RESPONSE_ERROR"
    retryable = status in _RETRYABLE_GET_STATUSES
    return WaveSpeedError(
        code,
        _message_from_payload(payload, "WaveSpeed API request failed"),
        status=status,
        retryable=retryable and not submitted,
        submitted=submitted,
        uncertain=submitted and (status >= 500),
        details={"httpStatus": status},
    )


class WaveSpeedAdapter:
    def __init__(self, settings: Settings, *, http_request: HttpRequest | None = None) -> None:
        self.settings = settings
        self._http_request = http_request or self._default_http_request
        self._submit_semaphore = asyncio.Semaphore(settings.wavespeed_max_submit_concurrency)
        self._poll_semaphore = asyncio.Semaphore(settings.wavespeed_max_poll_concurrency)
        self._last_availability: WaveSpeedAvailability | None = None

    def availability_snapshot(self) -> WaveSpeedAvailability:
        if self._last_availability is not None:
            return self._last_availability
        if not self.settings.wavespeed_enabled:
            return WaveSpeedAvailability(
                "WAVESPEED_DISABLED", False, False, "WaveSpeed is disabled", None
            )
        if not self.settings.effective_wavespeed_api_key:
            return WaveSpeedAvailability(
                "WAVESPEED_API_KEY_MISSING",
                False,
                False,
                "WaveSpeed API key is not configured",
                None,
            )
        return WaveSpeedAvailability(
            "WAVESPEED_CONFIGURED_UNVERIFIED",
            False,
            False,
            "WaveSpeed credentials have not passed read-only verification",
            None,
        )

    async def verify_credentials(self) -> WaveSpeedAvailability:
        checked_at = datetime.now(UTC)
        if not self.settings.wavespeed_enabled or not self.settings.effective_wavespeed_api_key:
            self._last_availability = None
            return self.availability_snapshot()
        try:
            await self._request_json(
                "GET",
                f"/predictions/{_VERIFY_TASK_ID}/result",
                None,
                accepted_statuses={404},
            )
        except WaveSpeedError as exc:
            authenticated = exc.code != "WAVESPEED_AUTHENTICATION_FAILED"
            self._last_availability = WaveSpeedAvailability(
                "WAVESPEED_VERIFICATION_FAILED",
                False,
                authenticated,
                str(exc),
                checked_at,
            )
        else:
            self._last_availability = WaveSpeedAvailability(
                "WAVESPEED_READY", True, True, None, checked_at
            )
        return self._last_availability

    async def upload_media(
        self,
        source: str | Path | bytes,
        *,
        filename: str | None = None,
        content_type: str | None = None,
    ) -> str:
        if _is_remote_source(source):
            assert isinstance(source, str)
            return _validate_remote_url(source, field="source")
        if isinstance(source, (str, Path)):
            path = Path(source)
            if not await asyncio.to_thread(path.is_file):
                raise WaveSpeedError("WAVESPEED_FILE_NOT_FOUND", "reference image does not exist")
            data = await asyncio.to_thread(path.read_bytes)
            filename = filename or path.name
        else:
            data = source
        if not filename:
            raise WaveSpeedError("WAVESPEED_INPUT_INVALID", "filename is required for byte uploads")
        extension = Path(filename).suffix.lower()
        if extension not in _ALLOWED_EXTENSIONS:
            raise WaveSpeedError(
                "WAVESPEED_FILE_TYPE_UNSUPPORTED", "reference image must be JPG, PNG, or WebP"
            )
        if not data:
            raise WaveSpeedError("WAVESPEED_FILE_EMPTY", "reference image is empty")
        if len(data) > self.settings.max_input_image_bytes:
            raise WaveSpeedError("WAVESPEED_FILE_TOO_LARGE", "reference image is too large")
        detected_type = content_type or _CONTENT_TYPE_BY_EXTENSION[extension]
        if detected_type not in _ALLOWED_CONTENT_TYPES:
            raise WaveSpeedError(
                "WAVESPEED_FILE_TYPE_UNSUPPORTED", "reference image must be JPG, PNG, or WebP"
            )

        boundary = f"libtv-{uuid.uuid4().hex}"
        disposition_name = filename.replace('"', "")
        body = b"".join(
            (
                f"--{boundary}\r\n".encode(),
                (
                    'Content-Disposition: form-data; name="file"; '
                    f'filename="{disposition_name}"\r\n'
                ).encode(),
                f"Content-Type: {detected_type}\r\n\r\n".encode(),
                data,
                f"\r\n--{boundary}--\r\n".encode(),
            )
        )
        async with self._submit_semaphore:
            response = await self._request_json(
                "POST",
                "/media/upload/binary",
                body,
                content_type=f"multipart/form-data; boundary={boundary}",
                submitted=False,
            )
        result = _response_data(response)
        download_url = result.get("download_url")
        if not isinstance(download_url, str):
            raise WaveSpeedError(
                "WAVESPEED_RESPONSE_INVALID", "WaveSpeed upload response omitted download_url"
            )
        return _validate_remote_url(download_url, field="download_url")

    async def submit_prediction(
        self,
        model_id: str,
        payload: Mapping[str, object],
        *,
        validate_model: bool = True,
    ) -> WaveSpeedSubmission:
        if validate_model:
            _validate_model_payload(model_id, payload)
        elif not _valid_custom_model_id(model_id):
            raise WaveSpeedError("WAVESPEED_MODEL_UNSUPPORTED", "invalid WaveSpeed model id")
        async with self._submit_semaphore:
            response = await self._request_json(
                "POST", f"/{model_id}", dict(payload), submitted=True
            )
        data = _response_data(response)
        task_id = data.get("id")
        raw_status = data.get("status")
        if not isinstance(task_id, str) or not task_id.strip():
            raise WaveSpeedError(
                "WAVESPEED_RESPONSE_INVALID",
                "WaveSpeed submission response omitted task id",
                model_id=model_id,
                submitted=True,
                uncertain=True,
            )
        if raw_status not in {"created", "processing"}:
            raise WaveSpeedError(
                "WAVESPEED_RESPONSE_INVALID",
                "WaveSpeed submission returned an invalid status",
                task_id=task_id,
                model_id=model_id,
                submitted=True,
            )
        urls = data.get("urls")
        result_url = urls.get("get") if isinstance(urls, Mapping) else None
        if not isinstance(result_url, str) or not result_url.strip():
            result_url = (
                f"{self.settings.wavespeed_api_base_url}/predictions/"
                f"{quote(task_id, safe='')}/result"
            )
        return WaveSpeedSubmission(
            task_id=task_id,
            status=raw_status,
            model_id=model_id,
            result_url=result_url,
            raw_response=response,
        )

    async def get_prediction(self, task_id: str) -> WaveSpeedPrediction:
        normalized_id = task_id.strip()
        if not normalized_id or len(normalized_id) > 512:
            raise WaveSpeedError("WAVESPEED_INPUT_INVALID", "task_id is invalid")
        async with self._poll_semaphore:
            response = await self._request_json(
                "GET", f"/predictions/{quote(normalized_id, safe='')}/result", None
            )
        data = _response_data(response)
        raw_status = data.get("status")
        if raw_status not in WAVESPEED_STATUSES:
            raise WaveSpeedError(
                "WAVESPEED_RESPONSE_INVALID",
                "WaveSpeed prediction returned an unknown status",
                task_id=normalized_id,
            )
        outputs_value = data.get("outputs") or []
        if not isinstance(outputs_value, list) or not all(
            isinstance(value, str) for value in outputs_value
        ):
            raise WaveSpeedError(
                "WAVESPEED_RESPONSE_INVALID",
                "WaveSpeed prediction outputs must be a URL array",
                task_id=normalized_id,
            )
        outputs = tuple(_validate_remote_url(value, field="outputs") for value in outputs_value)
        model_id = data.get("model") or data.get("model_id")
        parsed_model_id = model_id if isinstance(model_id, str) else None
        error = (
            _message_from_payload(data, "WaveSpeed prediction failed")
            if raw_status in {"failed", "cancelled", "timeout"}
            else None
        )
        return WaveSpeedPrediction(
            task_id=normalized_id,
            status=raw_status,
            outputs=outputs,
            error=error,
            model_id=parsed_model_id,
            raw_response=response,
        )

    async def _request_json(
        self,
        method: str,
        path: str,
        payload: Mapping[str, object] | bytes | None,
        *,
        content_type: str = "application/json",
        submitted: bool = False,
        accepted_statuses: set[int] | None = None,
    ) -> dict[str, Any]:
        key = self.settings.effective_wavespeed_api_key
        if not key:
            raise WaveSpeedError("WAVESPEED_API_KEY_MISSING", "WaveSpeed API key is not configured")
        body = (
            payload
            if isinstance(payload, bytes)
            else (
                json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
                if payload is not None
                else None
            )
        )
        headers = {
            "Authorization": f"Bearer {key}",
            "Content-Type": content_type,
            "User-Agent": "libtv-agent-wavespeed/1",
        }
        attempts = self.settings.wavespeed_get_max_retries if method == "GET" else 1
        for attempt in range(attempts):
            started_at = time.monotonic()
            try:
                http_response = await self._http_request(
                    method,
                    f"{self.settings.wavespeed_api_base_url}{path}",
                    headers,
                    body,
                    self.settings.wavespeed_request_timeout_seconds,
                )
            except (TimeoutError, URLError, OSError) as exc:
                if method == "GET" and attempt + 1 < attempts:
                    await asyncio.sleep(self._retry_delay(attempt, {}))
                    continue
                raise WaveSpeedError(
                    "WAVESPEED_NETWORK_ERROR",
                    "WaveSpeed network request failed",
                    retryable=method == "GET",
                    submitted=submitted,
                    uncertain=submitted,
                    details={"errorType": type(exc).__name__},
                ) from exc
            logger.info(
                "WaveSpeed API response",
                extra={
                    "provider": self.settings.wavespeed_provider_name,
                    "http_method": method,
                    "endpoint": path.split("?", 1)[0],
                    "http_status": http_response.status_code,
                    "duration_ms": round((time.monotonic() - started_at) * 1000),
                },
            )
            try:
                decoded = (
                    json.loads(http_response.body.decode("utf-8")) if http_response.body else {}
                )
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                raise WaveSpeedError(
                    "WAVESPEED_RESPONSE_INVALID",
                    "WaveSpeed API returned invalid JSON",
                    status=http_response.status_code,
                    submitted=submitted,
                    uncertain=submitted,
                ) from exc
            if not isinstance(decoded, dict):
                raise WaveSpeedError(
                    "WAVESPEED_RESPONSE_INVALID", "WaveSpeed API response must be an object"
                )
            if accepted_statuses and http_response.status_code in accepted_statuses:
                return decoded
            if not 200 <= http_response.status_code < 300:
                if (
                    method == "GET"
                    and http_response.status_code in _RETRYABLE_GET_STATUSES
                    and attempt + 1 < attempts
                ):
                    await asyncio.sleep(self._retry_delay(attempt, http_response.headers))
                    continue
                raise _error_for_response(http_response, decoded, submitted=submitted)
            return decoded
        raise AssertionError("WaveSpeed request retry loop exited unexpectedly")

    def _retry_delay(self, attempt: int, headers: Mapping[str, str]) -> float:
        retry_after = next(
            (value for key, value in headers.items() if key.lower() == "retry-after"), None
        )
        if retry_after is not None:
            try:
                return min(
                    self.settings.wavespeed_get_retry_max_seconds,
                    max(self.settings.wavespeed_get_retry_base_seconds, float(retry_after)),
                )
            except ValueError:
                pass
        base = self.settings.wavespeed_get_retry_base_seconds * (2**attempt)
        jitter = random.uniform(0, min(1.0, base * 0.1))
        return min(self.settings.wavespeed_get_retry_max_seconds, base + jitter)

    @staticmethod
    async def _default_http_request(
        method: str,
        url: str,
        headers: dict[str, str],
        body: bytes | None,
        request_timeout: float,
    ) -> WaveSpeedHttpResponse:
        def send() -> WaveSpeedHttpResponse:
            request = Request(url, data=body, headers=headers, method=method)
            try:
                with urlopen(request, timeout=request_timeout) as response:
                    return WaveSpeedHttpResponse(
                        int(getattr(response, "status", 200)),
                        dict(response.headers.items()),
                        response.read(),
                    )
            except HTTPError as exc:
                return WaveSpeedHttpResponse(
                    exc.code,
                    dict(exc.headers.items()) if exc.headers else {},
                    exc.read(),
                )

        return await asyncio.to_thread(send)


def _response_data(response: Mapping[str, Any]) -> dict[str, Any]:
    data = response.get("data")
    if data is None:
        return dict(response)
    if not isinstance(data, Mapping):
        raise WaveSpeedError("WAVESPEED_RESPONSE_INVALID", "WaveSpeed data must be an object")
    return dict(data)


def _validate_model_payload(model_id: str, payload: Mapping[str, object]) -> None:
    if model_id not in WAVESPEED_MODEL_IDS:
        raise WaveSpeedError("WAVESPEED_MODEL_UNSUPPORTED", "unsupported WaveSpeed model")
    required = {"prompt", "aspect_ratio", "resolution", "output_format"}
    provider = "gpt-image-2" if model_id.startswith("openai/") else "nano-banana-2"
    edit = model_id.endswith("/edit")
    allowed = set(required)
    if edit:
        required.add("images")
        allowed.add("images")
    if provider == "gpt-image-2":
        required.add("quality")
        allowed.add("quality")
    else:
        required.update({"enable_web_search", "enable_image_search"})
        allowed.update({"enable_web_search", "enable_image_search"})
    missing = required - set(payload)
    unexpected = set(payload) - allowed
    if missing or unexpected:
        raise WaveSpeedError(
            "WAVESPEED_INPUT_INVALID",
            f"invalid parameters for {model_id}",
            model_id=model_id,
            details={"missing": sorted(missing), "unexpected": sorted(unexpected)},
        )
    expected_model, normalized = build_generation_payload(
        provider=provider,  # type: ignore[arg-type]
        mode="edit" if edit else "text-to-image",
        prompt=str(payload["prompt"]),
        images=payload.get("images", ()),  # type: ignore[arg-type]
        aspect_ratio=str(payload["aspect_ratio"]),
        resolution=payload["resolution"],  # type: ignore[arg-type]
        quality=payload.get("quality", "medium"),  # type: ignore[arg-type]
        output_format=payload["output_format"],  # type: ignore[arg-type]
    )
    if expected_model != model_id:
        raise WaveSpeedError("WAVESPEED_MODEL_UNSUPPORTED", "unsupported WaveSpeed model")
    if provider == "nano-banana-2" and (
        payload["enable_web_search"] is not False or payload["enable_image_search"] is not False
    ):
        raise WaveSpeedError(
            "WAVESPEED_INPUT_INVALID", "Nano Banana 2 search options must remain disabled"
        )
    if dict(payload) != normalized:
        raise WaveSpeedError(
            "WAVESPEED_INPUT_INVALID", f"parameters for {model_id} are not normalized"
        )


def _valid_custom_model_id(model_id: str) -> bool:
    parts = model_id.strip().split("/")
    return (
        2 <= len(parts) <= 5
        and len(model_id) <= 255
        and all(
            part and all(character.isalnum() or character in {"-", "_", "."} for character in part)
            for part in parts
        )
    )
