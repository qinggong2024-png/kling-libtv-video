from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from libtv_agent.config import Settings
from libtv_agent.services.credentials import (
    read_secure_payload,
    write_secure_payload_atomic,
)
from pydantic import BaseModel, ConfigDict, Field, field_validator

_FORMAT = "libtv-kling-config-v1"
_DESCRIPTION = "LibTV Kling provider configuration"
_BASE_URLS = {
    "https://api-beijing.klingai.com",
    "https://api-singapore.klingai.com",
}


class _StoredKlingConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    format: str = _FORMAT
    backend: str = Field(pattern="^(cli|api|wavespeed|bach)$")
    apiKey: str | None = Field(default=None, min_length=8, max_length=4096)
    baseUrl: str = "https://api-beijing.klingai.com"
    callbackUrl: str | None = Field(default=None, max_length=2048)
    model: str = Field(default="kling-3.0-omni", pattern="^kling-3\\.0-omni$")
    duration: int = Field(default=10, ge=3, le=15)
    aspectRatio: str = Field(default="9:16", pattern="^(16:9|9:16|1:1)$")
    resolution: str = Field(default="1080p", pattern="^(720p|1080p|4k)$")
    audio: str = Field(default="off", pattern="^(native|original|off)$")
    multiShot: bool = True
    maxSubmitConcurrency: int = Field(default=1, ge=1, le=20)
    maxPollConcurrency: int = Field(default=4, ge=1, le=50)
    cliEnabled: bool = False
    apiEnabled: bool = False

    @field_validator("apiKey", mode="before")
    @classmethod
    def normalize_api_key(cls, value: object) -> object:
        return value.strip() if isinstance(value, str) else value

    @field_validator("baseUrl")
    @classmethod
    def validate_base_url(cls, value: str) -> str:
        normalized = value.strip().rstrip("/")
        if normalized not in _BASE_URLS:
            raise ValueError("baseUrl must be the Beijing or Singapore Kling API endpoint")
        return normalized

    @field_validator("callbackUrl")
    @classmethod
    def validate_callback_url(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        parsed = urlsplit(normalized)
        if (
            parsed.scheme != "https"
            or not parsed.netloc
            or parsed.username
            or parsed.password
            or parsed.fragment
        ):
            raise ValueError(
                "callbackUrl must be an absolute HTTPS URL without credentials or fragment"
            )
        return normalized


def kling_admin_config_signature(settings: Settings) -> tuple[int, int] | None:
    path = settings.kling_admin_config_file
    if not path.is_file():
        return None
    stat = path.stat()
    return stat.st_mtime_ns, stat.st_size


def _snapshot(settings: Settings) -> _StoredKlingConfig:
    return _StoredKlingConfig(
        backend=settings.kling_provider_backend,
        apiKey=settings.kling_api_key,
        baseUrl=settings.kling_api_base_url,
        callbackUrl=settings.kling_api_callback_url,
        model=settings.kling_api_model,
        duration=settings.kling_api_duration,
        aspectRatio=settings.kling_api_aspect_ratio,
        resolution=settings.kling_api_resolution,
        audio=settings.kling_api_audio,
        multiShot=settings.kling_api_multi_shot,
        maxSubmitConcurrency=settings.kling_api_max_submit_concurrency,
        maxPollConcurrency=settings.kling_api_max_poll_concurrency,
        cliEnabled=settings.kling_cli_enabled,
        apiEnabled=settings.kling_api_enabled,
    )


def _read(path: Path) -> _StoredKlingConfig | None:
    payload = read_secure_payload(path)
    if not payload:
        return None
    if payload.get("format") != _FORMAT:
        raise ValueError("Kling administrator configuration file is invalid")
    return _StoredKlingConfig.model_validate(payload)


def _apply(settings: Settings, config: _StoredKlingConfig) -> None:
    # CLI can exist in an older snapshot but remains recovery-only.
    settings.kling_provider_backend = (  # type: ignore[assignment]
        "api" if config.backend == "cli" else config.backend
    )
    settings.kling_api_key = config.apiKey
    settings.kling_api_base_url = config.baseUrl  # type: ignore[assignment]
    settings.kling_api_callback_url = config.callbackUrl
    settings.kling_api_model = config.model  # type: ignore[assignment]
    settings.kling_api_duration = config.duration
    settings.kling_api_aspect_ratio = config.aspectRatio  # type: ignore[assignment]
    settings.kling_api_resolution = config.resolution  # type: ignore[assignment]
    settings.kling_api_audio = config.audio  # type: ignore[assignment]
    settings.kling_api_multi_shot = config.multiShot
    settings.kling_api_max_submit_concurrency = config.maxSubmitConcurrency
    settings.kling_api_max_poll_concurrency = config.maxPollConcurrency
    settings.kling_cli_enabled = config.cliEnabled
    settings.kling_api_enabled = config.apiEnabled


def load_kling_admin_config(settings: Settings) -> bool:
    config = _read(settings.kling_admin_config_file)
    if config is None:
        return False
    _apply(settings, config)
    return True


def kling_admin_config_status(settings: Settings) -> dict[str, object]:
    path = settings.kling_admin_config_file
    modified = (
        datetime.fromtimestamp(path.stat().st_mtime, UTC).isoformat() if path.is_file() else None
    )
    return {
        "backend": settings.kling_provider_backend,
        "apiKeyConfigured": bool(settings.kling_api_key),
        "baseUrl": settings.kling_api_base_url,
        "callbackUrl": settings.kling_api_callback_url,
        "model": settings.kling_api_model,
        "duration": settings.kling_api_duration,
        "aspectRatio": settings.kling_api_aspect_ratio,
        "resolution": settings.kling_api_resolution,
        "audio": settings.kling_api_audio,
        "multiShot": settings.kling_api_multi_shot,
        "maxSubmitConcurrency": settings.kling_api_max_submit_concurrency,
        "maxPollConcurrency": settings.kling_api_max_poll_concurrency,
        "enabled": settings.kling_api_enabled,
        "provider": settings.active_kling_provider_name,
        "updatedAt": modified,
    }


def update_kling_admin_config(
    settings: Settings,
    updates: dict[str, Any],
) -> dict[str, object]:
    updates = dict(updates)
    allowed = {
        "backend",
        "apiKey",
        "baseUrl",
        "callbackUrl",
        "model",
        "duration",
        "aspectRatio",
        "resolution",
        "audio",
        "multiShot",
        "maxSubmitConcurrency",
        "maxPollConcurrency",
        "enabled",
    }
    unknown = set(updates) - allowed
    if unknown:
        raise ValueError("unsupported Kling administrator configuration")
    if "backend" in updates and updates["backend"] not in {"api", "wavespeed", "bach"}:
        raise ValueError(
            "video generation backend must be api, wavespeed, or bach; "
            "CLI is available only for historical attempt recovery"
        )
    api_key = updates.get("apiKey")
    if isinstance(api_key, str):
        api_key = api_key.strip()
        if len(api_key) < 8 or len(api_key) > 4096:
            raise ValueError("apiKey must contain between 8 and 4096 characters")
        updates["apiKey"] = api_key

    current = _read(settings.kling_admin_config_file) or _snapshot(settings)
    values = current.model_dump()
    enabled = updates.pop("enabled", None)
    values.update(updates)
    if enabled is not None:
        values["apiEnabled"] = enabled
    if updates.get("apiKey", object()) is None:
        values["apiEnabled"] = False
    updated = _StoredKlingConfig.model_validate(values)
    if updated.apiEnabled and not updated.apiKey:
        raise ValueError("an API key is required before enabling the Kling API Provider")
    write_secure_payload_atomic(
        settings.kling_admin_config_file,
        settings,
        updated.model_dump(),
        description=_DESCRIPTION,
    )
    _apply(settings, updated)
    return kling_admin_config_status(settings)
