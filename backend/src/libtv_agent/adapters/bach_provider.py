from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
import json
import logging
import time
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote
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

logger = logging.getLogger(__name__)
_IMAGE_EXTENSIONS = frozenset({".jpg", ".jpeg", ".png"})
_BACH_STATUSES = frozenset({"TASK_PENDING", "TASK_PROCESSING", "TASK_SUCCEEDED", "TASK_FAILED"})


@dataclass(frozen=True)
class BachHttpResponse:
    status_code: int
    headers: dict[str, str]
    body: bytes


HttpRequest = Callable[
    [str, str, dict[str, str], bytes | None, float], Awaitable[BachHttpResponse]
]


class BachApiError(KlingCliError):
    def __init__(self, code: str, message: str, **kwargs: Any) -> None:
        super().__init__(code, message, **kwargs)
        self.provider = "bach"


def _map_status(raw_status: object) -> str:
    value = str(raw_status or "").strip().upper()
    if value == "TASK_PENDING":
        return "queued"
    if value == "TASK_PROCESSING":
        return "running"
    if value == "TASK_SUCCEEDED":
        return "succeeded"
    if value == "TASK_FAILED":
        return "failed"
    return "unknown"


def _base64url(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def build_bach_token(access_key: str, secret_key: str, *, now: int | None = None) -> str:
    issued_at = int(time.time()) if now is None else int(now)
    header = _base64url(b'{"alg":"HS256","typ":"JWT"}')
    payload = _base64url(
        json.dumps(
            {"iss": access_key, "nbf": issued_at - 5, "exp": issued_at + 10 * 24 * 3600},
            separators=(",", ":"),
        ).encode("utf-8")
    )
    signing_input = f"{header}.{payload}".encode("ascii")
    signature = hmac.new(secret_key.encode("utf-8"), signing_input, hashlib.sha256).digest()
    return f"{header}.{payload}.{_base64url(signature)}"


def _multipart_body(fields: dict[str, str], files: tuple[Path, ...]) -> tuple[bytes, str]:
    boundary = f"----libtv-bach-{uuid.uuid4().hex}"
    chunks: list[bytes] = []
    for name, value in fields.items():
        chunks.extend(
            [
                f"--{boundary}\r\n".encode(),
                f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode(),
                value.encode("utf-8"),
                b"\r\n",
            ]
        )
    for path in files:
        filename = path.name
        content_type = "image/png" if path.suffix.lower() == ".png" else "image/jpeg"
        chunks.extend(
            [
                f"--{boundary}\r\n".encode(),
                (
                    f'Content-Disposition: form-data; name="files"; filename="{filename}"\r\n'
                    f"Content-Type: {content_type}\r\n\r\n"
                ).encode(),
                path.read_bytes(),
                b"\r\n",
            ]
        )
    chunks.append(f"--{boundary}--\r\n".encode())
    return b"".join(chunks), f"multipart/form-data; boundary={boundary}"


class BachApiAdapter:
    """Bach v1 Image-to-Video adapter used by the existing video runner."""

    def __init__(self, settings: Settings, *, http_request: HttpRequest | None = None) -> None:
        self.settings = settings
        self._http_request = http_request or self._default_http_request
        self._token: str | None = None
        self._token_expiry = 0.0
        self._availability: ProviderAvailability | None = None
        self._capabilities: ProviderCapabilities | None = None
        self._submit_semaphore = asyncio.Semaphore(settings.bach_max_submit_concurrency)
        self._query_semaphore = asyncio.Semaphore(settings.bach_max_poll_concurrency)

    def get_provider_name(self) -> str:
        return self.settings.bach_provider_name

    def availability_snapshot(self) -> ProviderAvailability:
        if self._availability is not None:
            return self._availability
        configured = bool(
            self.settings.bach_enabled
            and self.settings.effective_bach_access_key
            and self.settings.effective_bach_secret_key
        )
        return ProviderAvailability(
            status="BACH_CONFIGURED" if configured else "BACH_CREDENTIALS_MISSING",
            available=configured,
            authenticated=configured,
            reason=None if configured else "Bach AccessKey and SecretKey are not configured",
            cli_version="api-v1",
        )

    def capabilities_snapshot(self) -> ProviderCapabilities | None:
        return self._capabilities

    async def check_availability(self) -> ProviderAvailability:
        self._availability = self.availability_snapshot()
        return self._availability

    async def refresh_capabilities(self, *, force: bool = False) -> ProviderCapabilities:
        if force:
            self._availability = None
            self._capabilities = None
        availability = await self.check_availability()
        if not availability.available:
            raise BachApiError(availability.status, availability.reason or "Bach is unavailable")
        if self._capabilities is None:
            self._capabilities = ProviderCapabilities(
                cli_version="api-v1",
                checked_at=datetime.now(UTC),
                authenticated=True,
                account_type=None,
                supported_models=(self.settings.bach_model,),
                supported_tools=("image_to_video", "batch_upload", "task_query"),
                video_durations=tuple(str(value) for value in range(1, 9)),
                tail_image_video_durations=tuple(str(value) for value in range(1, 7)),
                aspect_ratios=("16:9", "9:16", "1:1"),
                image_input_limit=2,
                supports_tail_image=True,
                supports_multiple_images=False,
                supports_watermark_free_output=True,
                supports_sound_control=True,
                raw_capabilities={
                    "baseUrl": self.settings.bach_api_base_url,
                    "createPath": "/videos/image2video",
                    "queryPath": "/videos/image2video/{task_id}",
                    "uploadPath": "/batch-upload/submit-with-files",
                    "statusValues": sorted(_BACH_STATUSES),
                },
            )
        return self._capabilities

    async def get_account_status(self) -> dict[str, Any]:
        availability = await self.check_availability()
        return {
            "provider": self.get_provider_name(),
            "status": availability.status,
            "configured": availability.authenticated,
            "verificationMode": "credentials_only",
        }

    @staticmethod
    def _images(request: VideoGenerationRequest) -> tuple[Path, ...]:
        first = request.first_frame_path
        paths = list(request.image_paths)
        if first is None and paths:
            first = paths.pop(0)
        result = [first] if first is not None else []
        if request.last_frame_path is not None:
            result.append(request.last_frame_path)
        elif len(paths) == 1:
            result.append(paths[0])
        elif len(paths) > 1:
            # The existing fixed workflow may provide a storyboard sequence;
            # P1 preserves only its first and final frame until Elements-to-Video.
            result.append(paths[-1])
        return tuple(dict.fromkeys(result))

    async def validate_request(self, request: VideoGenerationRequest) -> str:
        if not request.prompt.strip():
            raise BachApiError("BACH_INVALID_INPUT", "Video prompt cannot be empty")
        if len(request.prompt) > 10_000:
            raise BachApiError("BACH_INVALID_INPUT", "Bach prompt cannot exceed 10000 characters")
        images = self._images(request)
        if not images or len(images) > 2:
            raise BachApiError(
                "BACH_IMAGE_INPUT_INVALID",
                "Bach Image-to-Video requires one image or a first/last image pair",
            )
        if request.product_reference_paths or request.element_references:
            raise BachApiError(
                "BACH_ELEMENTS_NOT_IN_P1",
                "Bach P1 supports Image-to-Video only; product/element references are deferred",
            )
        resolution = request.resolution or self.settings.bach_resolution
        if resolution not in {"720p", "1080p"}:
            raise BachApiError("BACH_INVALID_INPUT", "Bach resolution must be 720p or 1080p")
        duration = request.duration or self.settings.bach_duration
        maximum = 6 if len(images) == 2 else 8
        if duration not in range(1, maximum + 1):
            raise BachApiError(
                "BACH_INVALID_INPUT",
                f"Bach Image-to-Video duration must be between 1 and {maximum} seconds",
            )
        for path in images:
            if not path.is_file() or path.suffix.lower() not in _IMAGE_EXTENSIONS:
                raise BachApiError("BACH_INVALID_INPUT", f"Bach image is unavailable: {path.name}")
            if path.stat().st_size <= 0 or path.stat().st_size > 10 * 1024 * 1024:
                raise BachApiError("BACH_INVALID_INPUT", f"Bach image exceeds 10 MB: {path.name}")
        return request.model or self.settings.bach_model

    def _token_value(self) -> str:
        access_key = self.settings.effective_bach_access_key
        secret_key = self.settings.effective_bach_secret_key
        if not access_key or not secret_key:
            raise BachApiError(
                "BACH_CREDENTIALS_MISSING",
                "Bach AccessKey and SecretKey are required",
            )
        now = time.time()
        if self._token is None or now >= self._token_expiry - 60:
            self._token = build_bach_token(access_key, secret_key)
            self._token_expiry = now + 10 * 24 * 3600
        return self._token

    async def _request_json(
        self,
        method: str,
        path: str,
        payload: dict[str, Any] | None = None,
        *,
        submitted: bool = False,
    ) -> dict[str, Any]:
        body = (
            json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
            if payload is not None
            else None
        )
        headers = {
            "Authorization": f"Bearer {self._token_value()}",
            "Content-Type": "application/json",
            "User-Agent": "libtv-agent-bach/1",
        }
        response = await self._call_request(method, path, headers, body, submitted=submitted)
        return self._decode_response(response, submitted=submitted)

    async def _request_multipart(
        self, path: str, fields: dict[str, str], files: tuple[Path, ...]
    ) -> dict[str, Any]:
        body, content_type = await asyncio.to_thread(_multipart_body, fields, files)
        headers = {
            "Authorization": f"Bearer {self._token_value()}",
            "Content-Type": content_type,
            "User-Agent": "libtv-agent-bach/1",
        }
        response = await self._call_request("POST", path, headers, body, submitted=True)
        return self._decode_response(response, submitted=True)

    async def _call_request(
        self,
        method: str,
        path: str,
        headers: dict[str, str],
        body: bytes | None,
        *,
        submitted: bool,
    ) -> BachHttpResponse:
        try:
            return await self._http_request(
                method,
                f"{self.settings.bach_api_base_url}{path}",
                headers,
                body,
                self.settings.bach_request_timeout_seconds,
            )
        except (TimeoutError, URLError, OSError) as exc:
            raise BachApiError(
                "BACH_NETWORK_ERROR",
                "Bach API network request failed",
                retryable=True,
                submitted=submitted,
                uncertain=submitted,
                details={"errorType": type(exc).__name__},
            ) from exc

    @staticmethod
    def _decode_response(response: BachHttpResponse, *, submitted: bool) -> dict[str, Any]:
        try:
            decoded = json.loads(response.body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise BachApiError(
                "BACH_RESPONSE_INVALID",
                "Bach API returned invalid JSON",
                retryable=response.status_code >= 500,
                submitted=submitted,
                uncertain=submitted,
            ) from exc
        if not isinstance(decoded, dict):
            raise BachApiError("BACH_RESPONSE_INVALID", "Bach API response must be an object")
        code = decoded.get("code")
        if not 200 <= response.status_code < 300 or code != 200:
            http_status = response.status_code
            service_code = int(code) if isinstance(code, int) else None
            retryable = (
                http_status >= 500
                or http_status == 429
                or service_code in {1800, 5000, 500}
            )
            if service_code in {1000, 1001, 1100, 1101, 1102, 1103, 1200, 1301, 1302}:
                retryable = False
            raise BachApiError(
                f"BACH_HTTP_{http_status}" if service_code is None else f"BACH_CODE_{service_code}",
                str(decoded.get("message") or "Bach API request failed"),
                retryable=retryable,
                submitted=submitted,
                uncertain=submitted and (http_status >= 500 or service_code in {5000, 500}),
                details={"httpStatus": http_status, "serviceCode": service_code},
            )
        return decoded

    async def _upload_images(self, images: tuple[Path, ...], batch_id: str) -> tuple[str, ...]:
        response = await self._request_multipart(
            "/batch-upload/submit-with-files",
            {"batch_id": batch_id},
            images,
        )
        data = response.get("data")
        if not isinstance(data, dict) or not isinstance(data.get("batch_id"), str):
            raise BachApiError(
                "BACH_UPLOAD_RESPONSE_INVALID", "Bach upload did not return batch_id"
            )
        upload_id = data["batch_id"]
        deadline = time.monotonic() + self.settings.bach_task_timeout_seconds
        while True:
            status = await self._request_json(
                "GET", f"/batch-upload/status/{quote(upload_id, safe='')}"
            )
            status_data = status.get("data")
            if not isinstance(status_data, dict):
                raise BachApiError(
                    "BACH_UPLOAD_RESPONSE_INVALID", "Bach upload status data is invalid"
                )
            raw_status = str(status_data.get("status") or "").upper()
            if raw_status == "TASK_FAILED":
                raise BachApiError(
                    "BACH_UPLOAD_FAILED",
                    str(status_data.get("message") or "Bach image upload failed"),
                )
            if raw_status == "TASK_SUCCEEDED":
                results = status_data.get("results")
                if not isinstance(results, list):
                    raise BachApiError(
                        "BACH_UPLOAD_RESPONSE_INVALID", "Bach upload results are missing"
                    )
                urls = [
                    str(item["image_url"])
                    for item in sorted(results, key=lambda value: int(value.get("index", 0)))
                    if (
                        isinstance(item, dict)
                        and item.get("status") == "TASK_SUCCEEDED"
                        and item.get("image_url")
                    )
                ]
                if len(urls) != len(images):
                    raise BachApiError(
                        "BACH_UPLOAD_FAILED",
                        "Bach did not return every uploaded image URL",
                    )
                return tuple(urls)
            if time.monotonic() >= deadline:
                raise BachApiError(
                    "BACH_UPLOAD_TIMEOUT", "Bach image upload timed out", retryable=True
                )
            await asyncio.sleep(self.settings.bach_poll_interval_seconds)

    async def submit(self, request: VideoGenerationRequest) -> ProviderSubmissionResult:
        async with self._submit_semaphore:
            model = await self.validate_request(request)
            images = self._images(request)
            upload_urls = await self._upload_images(
                images,
                f"libtv-{request.task_trace_id or uuid.uuid4().hex}",
            )
            payload: dict[str, Any] = {
                "model_name": model,
                "image_url": upload_urls[0],
                "prompt": request.prompt.strip(),
                "resolution": request.resolution or self.settings.bach_resolution,
                "duration": request.duration or self.settings.bach_duration,
                "generate_audio": request.audio in {"native", "original"},
            }
            if len(upload_urls) == 2:
                payload["end_image_url"] = upload_urls[1]
            if request.audio and request.audio not in {"native", "original", "off"}:
                payload["audio_prompt"] = request.audio
            if request.callback_url:
                payload["callback_url"] = request.callback_url
            response = await self._request_json(
                "POST", "/videos/image2video", payload, submitted=True
            )
            data = response.get("data")
            if not isinstance(data, dict) or not isinstance(data.get("task_id"), str):
                raise BachApiError(
                    "BACH_SUBMIT_RESPONSE_INVALID",
                    "Bach create task did not return task_id",
                    submitted=True,
                    uncertain=True,
                )
            return ProviderSubmissionResult(
                provider_task_id=data["task_id"],
                raw_status=str(data.get("status") or "TASK_PENDING"),
                credits_consumed=None,
                provider_model=model,
                raw_response={"upload": {"imageUrls": list(upload_urls)}, "task": response},
            )

    async def query(self, provider_task_id: str) -> ProviderTaskResult:
        async with self._query_semaphore:
            response = await self._request_json(
                "GET", f"/videos/image2video/{quote(provider_task_id, safe='')}"
            )
        data = response.get("data")
        if not isinstance(data, dict):
            raise BachApiError(
                "BACH_RESPONSE_INVALID",
                "Bach task data is invalid",
                provider_task_id=provider_task_id,
            )
        raw_status = str(data.get("status") or "")
        status = _map_status(raw_status)
        outputs: tuple[ProviderOutput, ...] = ()
        if status == "succeeded":
            url = data.get("video_url")
            if not isinstance(url, str) or not url:
                raise BachApiError(
                    "BACH_OUTPUT_URL_MISSING",
                    "Bach task succeeded without video_url",
                    provider_task_id=provider_task_id,
                )
            outputs = (ProviderOutput(url=url, content_type="video"),)
        return ProviderTaskResult(
            status=status,
            raw_status=raw_status,
            outputs=outputs,
            raw_response=response,
            message=str(data.get("message")) if data.get("message") is not None else None,
        )

    async def download(self, output: ProviderOutput, destination: Path) -> DownloadResult:
        existing_size = await asyncio.to_thread(
            lambda: destination.stat().st_size if destination.is_file() else 0
        )
        if existing_size > 0:
            return DownloadResult(path=destination, reused=True, size_bytes=existing_size)
        temporary = destination.with_suffix(f"{destination.suffix}.part")
        destination.parent.mkdir(parents=True, exist_ok=True)

        def download_file() -> int:
            request = Request(output.url, headers={"User-Agent": "libtv-agent-bach/1"})
            with urlopen(request, timeout=self.settings.bach_download_timeout_seconds) as response:
                if not 200 <= int(getattr(response, "status", 200)) < 300:
                    raise OSError("unexpected Bach output HTTP status")
                with temporary.open("wb") as handle:
                    while chunk := response.read(1024 * 1024):
                        handle.write(chunk)
                declared_length = response.headers.get("Content-Length")
            size = temporary.stat().st_size
            if declared_length is not None and size != int(declared_length):
                raise OSError("downloaded output length does not match Content-Length")
            if size <= 0:
                raise OSError("downloaded Bach output is empty")
            temporary.replace(destination)
            return size

        try:
            size = await asyncio.wait_for(
                asyncio.to_thread(download_file),
                timeout=self.settings.bach_download_timeout_seconds,
            )
        except Exception as exc:
            temporary.unlink(missing_ok=True)
            raise BachApiError(
                "BACH_DOWNLOAD_FAILED",
                "Bach video output download failed",
                retryable=True,
                details={"errorType": type(exc).__name__},
            ) from exc
        return DownloadResult(path=destination, reused=False, size_bytes=size)

    @staticmethod
    async def _default_http_request(
        method: str,
        url: str,
        headers: dict[str, str],
        body: bytes | None,
        request_timeout: float,
    ) -> BachHttpResponse:
        def send() -> BachHttpResponse:
            request = Request(url, data=body, headers=headers, method=method)
            try:
                with urlopen(request, timeout=request_timeout) as response:
                    return BachHttpResponse(
                        status_code=int(getattr(response, "status", 200)),
                        headers=dict(response.headers.items()),
                        body=response.read(),
                    )
            except HTTPError as exc:
                return BachHttpResponse(
                    status_code=exc.code,
                    headers=dict(exc.headers.items()) if exc.headers else {},
                    body=exc.read(),
                )

        return await asyncio.to_thread(send)
