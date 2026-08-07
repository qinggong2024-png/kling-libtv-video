from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from libtv_agent.config import Settings
from libtv_agent.services.credentials import read_secure_payload, write_secure_payload_atomic
from pydantic import BaseModel, ConfigDict, Field, field_validator

_FORMAT = "libtv-bach-config-v1"
_DESCRIPTION = "LibTV Bach provider configuration"
_OFFICIAL_BASE_URL = "https://api-gen-na.bach.art/api/vdr"


class _StoredBachConfig(BaseModel):
    model_config = ConfigDict(extra="allow")

    format: str = _FORMAT
    accessKey: str | None = Field(default=None, min_length=8, max_length=4096)
    secretKey: str | None = Field(default=None, min_length=8, max_length=4096)
    enabled: bool = False
    baseUrl: str = _OFFICIAL_BASE_URL
    model: str = Field(default="bach-1.0", min_length=1, max_length=255)
    resolution: str = Field(default="720p", pattern="^(720p|1080p)$")
    duration: int = Field(default=6, ge=1, le=8)
    aspectRatio: str = Field(default="9:16", pattern="^(16:9|9:16|1:1)$")
    generateAudio: bool = False
    maxSubmitConcurrency: int = Field(default=1, ge=1, le=20)
    maxPollConcurrency: int = Field(default=4, ge=1, le=50)

    @field_validator("accessKey", "secretKey", mode="before")
    @classmethod
    def normalize_secret(cls, value: object) -> object:
        return value.strip() if isinstance(value, str) else value

    @field_validator("baseUrl")
    @classmethod
    def validate_base_url(cls, value: str) -> str:
        normalized = value.strip().rstrip("/")
        parsed = urlsplit(normalized)
        official = (
            parsed.scheme == "https"
            and parsed.hostname == "api-gen-na.bach.art"
            and parsed.path == "/api/vdr"
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
            raise ValueError("baseUrl must be the official Bach API endpoint")
        return normalized


def bach_admin_config_signature(settings: Settings) -> tuple[int, int] | None:
    path = settings.bach_admin_config_file
    if not path.is_file():
        return None
    stat = path.stat()
    return stat.st_mtime_ns, stat.st_size


def _read(path: Path) -> _StoredBachConfig | None:
    payload = read_secure_payload(path)
    if not payload:
        return None
    if payload.get("format") != _FORMAT:
        raise ValueError("Bach administrator configuration file is invalid")
    return _StoredBachConfig.model_validate(payload)


def _snapshot(settings: Settings) -> _StoredBachConfig:
    return _StoredBachConfig(
        accessKey=settings.bach_admin_access_key or settings.bach_access_key,
        secretKey=settings.bach_admin_secret_key or settings.bach_secret_key,
        enabled=settings.bach_enabled,
        baseUrl=settings.bach_api_base_url,
        model=settings.bach_model,
        resolution=settings.bach_resolution,
        duration=settings.bach_duration,
        aspectRatio=settings.bach_aspect_ratio,
        generateAudio=settings.bach_generate_audio,
        maxSubmitConcurrency=settings.bach_max_submit_concurrency,
        maxPollConcurrency=settings.bach_max_poll_concurrency,
    )


def _validate_environment(settings: Settings, config: _StoredBachConfig) -> None:
    parsed = urlsplit(config.baseUrl)
    if settings.app_env in {"staging", "production"} and parsed.hostname in {
        "localhost",
        "127.0.0.1",
        "::1",
    }:
        raise ValueError("shared environments require the official Bach API endpoint")


def _apply(settings: Settings, config: _StoredBachConfig) -> None:
    _validate_environment(settings, config)
    settings.bach_admin_access_key = config.accessKey
    settings.bach_admin_secret_key = config.secretKey
    settings.bach_enabled = config.enabled
    settings.bach_api_base_url = config.baseUrl
    settings.bach_model = config.model
    settings.bach_resolution = config.resolution  # type: ignore[assignment]
    settings.bach_duration = config.duration
    settings.bach_aspect_ratio = config.aspectRatio  # type: ignore[assignment]
    settings.bach_generate_audio = config.generateAudio
    settings.bach_max_submit_concurrency = config.maxSubmitConcurrency
    settings.bach_max_poll_concurrency = config.maxPollConcurrency


def load_bach_admin_config(settings: Settings) -> bool:
    config = _read(settings.bach_admin_config_file)
    if config is None:
        return False
    _apply(settings, config)
    return True


def bach_admin_config_status(settings: Settings) -> dict[str, object]:
    path = settings.bach_admin_config_file
    modified = (
        datetime.fromtimestamp(path.stat().st_mtime, UTC).isoformat() if path.is_file() else None
    )
    return {
        "enabled": settings.bach_enabled,
        "accessKeyConfigured": bool(settings.effective_bach_access_key),
        "secretKeyConfigured": bool(settings.effective_bach_secret_key),
        "credentialsConfigured": bool(
            settings.effective_bach_access_key and settings.effective_bach_secret_key
        ),
        "credentialSource": settings.bach_credential_source,
        "baseUrl": settings.bach_api_base_url,
        "model": settings.bach_model,
        "resolution": settings.bach_resolution,
        "duration": settings.bach_duration,
        "aspectRatio": settings.bach_aspect_ratio,
        "generateAudio": settings.bach_generate_audio,
        "maxSubmitConcurrency": settings.bach_max_submit_concurrency,
        "maxPollConcurrency": settings.bach_max_poll_concurrency,
        "provider": settings.bach_provider_name,
        "updatedAt": modified,
    }


def update_bach_admin_config(
    settings: Settings,
    updates: dict[str, Any],
) -> dict[str, object]:
    allowed = {
        "accessKey",
        "secretKey",
        "enabled",
        "baseUrl",
        "model",
        "resolution",
        "duration",
        "aspectRatio",
        "generateAudio",
        "maxSubmitConcurrency",
        "maxPollConcurrency",
    }
    if set(updates) - allowed:
        raise ValueError("unsupported Bach administrator configuration")
    current = _read(settings.bach_admin_config_file) or _snapshot(settings)
    values = current.model_dump()
    values.update(updates)
    updated = _StoredBachConfig.model_validate(values)
    _validate_environment(settings, updated)
    if updated.enabled and not updated.accessKey:
        raise ValueError("an AccessKey is required before enabling Bach")
    if updated.enabled and not updated.secretKey:
        raise ValueError("a SecretKey is required before enabling Bach")
    write_secure_payload_atomic(
        settings.bach_admin_config_file,
        settings,
        updated.model_dump(),
        description=_DESCRIPTION,
    )
    _apply(settings, updated)
    return bach_admin_config_status(settings)
