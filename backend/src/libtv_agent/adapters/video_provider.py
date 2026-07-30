from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Protocol


@dataclass(frozen=True)
class ProviderAvailability:
    status: str
    available: bool
    authenticated: bool
    reason: str | None = None
    cli_version: str | None = None


@dataclass(frozen=True)
class ProviderCapabilities:
    cli_version: str
    checked_at: datetime
    authenticated: bool
    account_type: str | None
    supported_models: tuple[str, ...]
    supported_tools: tuple[str, ...]
    video_durations: tuple[str, ...] = ()
    aspect_ratios: tuple[str, ...] = ()
    image_input_limit: int = 1
    supports_tail_image: bool = False
    supports_multiple_images: bool = False
    supports_watermark_free_output: bool = False
    supports_sound_control: bool = False
    raw_capabilities: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class VideoGenerationRequest:
    prompt: str
    model: str | None
    image_paths: tuple[Path, ...]
    duration: int | None
    aspect_ratio: str | None
    product_reference_paths: tuple[Path, ...] = ()
    fallback_mode: str = "disabled"
    task_trace_id: str | None = None
    resolution: str | None = None
    audio: str | None = None
    multi_shot: bool | None = None
    external_task_id: str | None = None
    callback_url: str | None = None


@dataclass(frozen=True)
class ProviderSubmissionResult:
    provider_task_id: str
    raw_status: str
    credits_consumed: int | None
    provider_model: str
    raw_response: dict[str, Any]


@dataclass(frozen=True)
class ProviderOutput:
    url: str
    content_type: str | None = None
    url_without_watermark: str | None = None
    cover_url: str | None = None


@dataclass(frozen=True)
class ProviderTaskResult:
    status: str
    raw_status: str
    outputs: tuple[ProviderOutput, ...]
    raw_response: dict[str, Any]
    credits_consumed: int | None = None


@dataclass(frozen=True)
class DownloadResult:
    path: Path
    reused: bool
    size_bytes: int


class VideoProviderAdapter(Protocol):
    def get_provider_name(self) -> str: ...

    async def check_availability(self) -> ProviderAvailability: ...

    async def refresh_capabilities(self, *, force: bool = False) -> ProviderCapabilities: ...

    async def validate_request(self, request: VideoGenerationRequest) -> str: ...

    async def submit(self, request: VideoGenerationRequest) -> ProviderSubmissionResult: ...

    async def query(self, provider_task_id: str) -> ProviderTaskResult: ...

    async def download(self, output: ProviderOutput, destination: Path) -> DownloadResult: ...

    async def get_account_status(self) -> dict[str, Any]: ...
