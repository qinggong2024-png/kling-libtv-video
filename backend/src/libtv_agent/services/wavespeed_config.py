from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from libtv_agent.config import Settings
from libtv_agent.services.credentials import read_secure_payload, write_secure_payload_atomic
from pydantic import BaseModel, ConfigDict, Field, field_validator

_FORMAT = "libtv-wavespeed-config-v1"
_DESCRIPTION = "LibTV WaveSpeed provider configuration"


class _StoredWaveSpeedConfig(BaseModel):
    # Administrator config is hot-reloaded while rolling upgrades can briefly
    # leave older and newer API processes alive together. Unknown future fields
    # must not make an otherwise usable provider configuration fatal. Preserve
    # those fields as well so an older process cannot erase them on its next write.
    model_config = ConfigDict(extra="allow")

    format: str = _FORMAT
    apiKey: str | None = Field(default=None, min_length=8, max_length=4096)
    enabled: bool = False
    baseUrl: str = "https://api.wavespeed.ai/api/v3"
    maxSubmitConcurrency: int = Field(default=1, ge=1, le=50)
    maxPollConcurrency: int = Field(default=4, ge=1, le=50)
    videoModel: str = Field(
        default="kwaivgi/kling-video-o3-pro/reference-to-video",
        min_length=3,
        max_length=255,
        pattern=r"^[A-Za-z0-9._-]+(?:/[A-Za-z0-9._-]+)+$",
    )
    videoDuration: int = Field(default=10, ge=3, le=15)
    videoAspectRatio: str = Field(default="9:16", pattern="^(16:9|9:16|1:1)$")
    videoSound: bool = False

    @field_validator("apiKey", mode="before")
    @classmethod
    def normalize_api_key(cls, value: object) -> object:
        return value.strip() if isinstance(value, str) else value

    @field_validator("baseUrl")
    @classmethod
    def validate_base_url(cls, value: str) -> str:
        normalized = value.strip().rstrip("/")
        parsed = urlsplit(normalized)
        official = (
            parsed.scheme == "https"
            and parsed.hostname == "api.wavespeed.ai"
            and parsed.path == "/api/v3"
            and not parsed.username
            and not parsed.password
            and not parsed.query
            and not parsed.fragment
        )
        loopback = (
            parsed.scheme in {"http", "https"}
            and parsed.hostname in {"localhost", "127.0.0.1", "::1"}
            and not parsed.username
            and not parsed.password
            and not parsed.query
            and not parsed.fragment
        )
        if not official and not loopback:
            raise ValueError("baseUrl must be the official WaveSpeed API endpoint")
        return normalized


def wavespeed_admin_config_signature(settings: Settings) -> tuple[int, int] | None:
    path = settings.wavespeed_admin_config_file
    if not path.is_file():
        return None
    stat = path.stat()
    return stat.st_mtime_ns, stat.st_size


def _read(path: Path) -> _StoredWaveSpeedConfig | None:
    payload = read_secure_payload(path)
    if not payload:
        return None
    if payload.get("format") != _FORMAT:
        raise ValueError("WaveSpeed administrator configuration file is invalid")
    return _StoredWaveSpeedConfig.model_validate(payload)


def _snapshot(settings: Settings) -> _StoredWaveSpeedConfig:
    return _StoredWaveSpeedConfig(
        apiKey=settings.wavespeed_admin_api_key,
        enabled=settings.wavespeed_enabled,
        baseUrl=settings.wavespeed_api_base_url,
        maxSubmitConcurrency=settings.wavespeed_max_submit_concurrency,
        maxPollConcurrency=settings.wavespeed_max_poll_concurrency,
        videoModel=settings.wavespeed_video_model,
        videoDuration=settings.wavespeed_video_duration,
        videoAspectRatio=settings.wavespeed_video_aspect_ratio,
        videoSound=settings.wavespeed_video_sound,
    )


def _validate_environment(settings: Settings, config: _StoredWaveSpeedConfig) -> None:
    parsed = urlsplit(config.baseUrl)
    if settings.app_env in {"staging", "production"} and parsed.hostname in {
        "localhost",
        "127.0.0.1",
        "::1",
    }:
        raise ValueError("shared environments require the official WaveSpeed API endpoint")


def _apply(settings: Settings, config: _StoredWaveSpeedConfig) -> None:
    _validate_environment(settings, config)
    settings.wavespeed_admin_api_key = config.apiKey
    settings.wavespeed_enabled = config.enabled
    settings.wavespeed_api_base_url = config.baseUrl
    settings.wavespeed_max_submit_concurrency = config.maxSubmitConcurrency
    settings.wavespeed_max_poll_concurrency = config.maxPollConcurrency
    settings.wavespeed_video_model = config.videoModel
    settings.wavespeed_video_duration = config.videoDuration
    settings.wavespeed_video_aspect_ratio = config.videoAspectRatio  # type: ignore[assignment]
    settings.wavespeed_video_sound = config.videoSound


def _validate_environment_endpoint(settings: Settings, base_url: str) -> None:
    parsed = urlsplit(base_url)
    if parsed.hostname in {"localhost", "127.0.0.1", "::1"} and settings.app_env not in {
        "development",
        "test",
    }:
        raise ValueError("loopback WaveSpeed endpoints are allowed only in development or test")


def load_wavespeed_admin_config(settings: Settings) -> bool:
    config = _read(settings.wavespeed_admin_config_file)
    if config is None:
        return False
    _validate_environment_endpoint(settings, config.baseUrl)
    _apply(settings, config)
    return True


def wavespeed_admin_config_status(settings: Settings) -> dict[str, object]:
    path = settings.wavespeed_admin_config_file
    modified = (
        datetime.fromtimestamp(path.stat().st_mtime, UTC).isoformat() if path.is_file() else None
    )
    return {
        "enabled": settings.wavespeed_enabled,
        "apiKeyConfigured": bool(settings.effective_wavespeed_api_key),
        "credentialSource": settings.wavespeed_credential_source,
        "baseUrl": settings.wavespeed_api_base_url,
        "maxSubmitConcurrency": settings.wavespeed_max_submit_concurrency,
        "maxPollConcurrency": settings.wavespeed_max_poll_concurrency,
        "videoModel": settings.wavespeed_video_model,
        "videoDuration": settings.wavespeed_video_duration,
        "videoAspectRatio": settings.wavespeed_video_aspect_ratio,
        "videoSound": settings.wavespeed_video_sound,
        "provider": settings.wavespeed_provider_name,
        "videoProvider": settings.wavespeed_video_provider_name,
        "videoBackendActive": settings.kling_provider_backend == "wavespeed",
        "updatedAt": modified,
    }


def update_wavespeed_admin_config(
    settings: Settings,
    updates: dict[str, Any],
) -> dict[str, object]:
    updates = dict(updates)
    allowed = {
        "apiKey",
        "enabled",
        "baseUrl",
        "maxSubmitConcurrency",
        "maxPollConcurrency",
        "videoModel",
        "videoDuration",
        "videoAspectRatio",
        "videoSound",
    }
    if set(updates) - allowed:
        raise ValueError("unsupported WaveSpeed administrator configuration")
    api_key = updates.get("apiKey")
    if isinstance(api_key, str):
        api_key = api_key.strip()
        if not 8 <= len(api_key) <= 4096:
            raise ValueError("apiKey must contain between 8 and 4096 characters")
        updates["apiKey"] = api_key

    current = _read(settings.wavespeed_admin_config_file) or _snapshot(settings)
    values = current.model_dump()
    values.update(updates)
    updated = _StoredWaveSpeedConfig.model_validate(values)
    _validate_environment_endpoint(settings, updated.baseUrl)
    _validate_environment(settings, updated)
    effective_key = updated.apiKey or settings.wavespeed_api_key
    if updated.enabled and not effective_key:
        raise ValueError("an API key is required before enabling WaveSpeed")
    write_secure_payload_atomic(
        settings.wavespeed_admin_config_file,
        settings,
        updated.model_dump(),
        description=_DESCRIPTION,
    )
    _apply(settings, updated)
    return wavespeed_admin_config_status(settings)
