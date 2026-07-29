from __future__ import annotations

import asyncio
import json
import os
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from libtv_agent.config import Settings
from libtv_agent.domain.contracts import sha256_json
from libtv_agent.domain.models import ModelSchemaSnapshot
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

MODEL_KEY = "kling-v3-omni"


class ModelRegistryError(RuntimeError):
    pass


@dataclass(frozen=True)
class ModelCompatibility:
    compatible: bool
    issues: tuple[str, ...]


def as_utc(value: datetime | None) -> datetime | None:
    """Normalize database datetimes before comparing them with UTC values.

    SQLite does not preserve timezone information for SQLAlchemy DateTime columns,
    while PostgreSQL does. Treat a naive value as UTC so both backends follow the
    same expiration semantics.
    """
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _enum_values(field: dict[str, Any]) -> list[Any]:
    return [item.get("value") if isinstance(item, dict) else item for item in field.get("enum", [])]


def normalize_live_schema(payload: dict[str, Any]) -> dict[str, Any]:
    if payload.get("modelKey") != MODEL_KEY or payload.get("modality") != "video":
        raise ModelRegistryError("target video model was not resolved exactly")
    raw = payload.get("schema") or {}
    properties = raw.get("properties") or {}
    config_settings = (raw.get("config") or {}).get("settings") or {}
    mode_items = (properties.get("modeType") or {}).get("items") or {}
    max_media = max(
        (
            int(bounds[1])
            for bounds in mode_items.values()
            if isinstance(bounds, list) and len(bounds) > 1
        ),
        default=0,
    )
    quality_key = "quality_4k" if "quality_4k" in properties else "quality"
    fields = {
        "model": {"originalField": "model"},
        "modeType": properties.get("modeType") or {"originalField": "modeType"},
        "quality": properties.get(quality_key) or {},
        "duration": properties.get("duration") or properties.get("duration_10") or {},
        "aspectRatio": properties.get("ratio") or properties.get("ratio_auto") or {},
        "sound": properties.get("enableSound") or {},
        "smartStoryboard": properties.get("smartStoryboard") or {},
    }
    normalized = {
        "modelKey": payload["modelKey"],
        "modelName": payload.get("modelName"),
        "toolKey": payload.get("toolKey"),
        "maxMediaCount": max_media,
        "maxPromptLength": int((properties.get("prompt") or {}).get("maxLength") or 0),
        "modeTypes": sorted(mode_items),
        "modeMediaRanges": mode_items,
        "modeSettings": config_settings,
        "fields": fields,
        "rawSchema": raw,
    }
    compatibility = validate_model_compatibility(normalized)
    if not compatibility.compatible:
        raise ModelRegistryError("; ".join(compatibility.issues))
    return normalized


def validate_model_compatibility(schema: dict[str, Any]) -> ModelCompatibility:
    issues: list[str] = []
    if schema.get("maxMediaCount", 0) < 7:
        issues.append("model does not support seven ordered references")
    modes = schema.get("modeMediaRanges") or {}
    if (modes.get("singleImage2video") or [0, 0])[1] < 1:
        issues.append("singleImage2video is unavailable")
    if (modes.get("mixed2video") or [0, 0])[1] < 7:
        issues.append("mixed2video does not support seven references")
    fields = schema.get("fields") or {}
    ratio = fields.get("aspectRatio") or {}
    if "9:16" not in _enum_values(ratio):
        issues.append("9:16 is unavailable")
    duration = fields.get("duration") or {}
    duration_values = _enum_values(duration)
    if not (10 in duration_values or (duration.get("min", 11) <= 10 <= duration.get("max", 9))):
        issues.append("10 second duration is unavailable")
    if "high" not in _enum_values(fields.get("quality") or {}):
        issues.append("high quality is unavailable")
    if "off" not in _enum_values(fields.get("sound") or {}):
        issues.append("sound-off mode is unavailable")
    if int(schema.get("maxPromptLength") or 0) < 2000:
        issues.append("prompt limit is below 2000 characters")
    return ModelCompatibility(not issues, tuple(issues))


def compatibility_fingerprint(schema: dict[str, Any]) -> str:
    relevant = {
        "modelKey": schema["modelKey"],
        "maxMediaCount": schema["maxMediaCount"],
        "maxPromptLength": schema["maxPromptLength"],
        "modeMediaRanges": schema["modeMediaRanges"],
        "modeSettings": schema["modeSettings"],
        "fields": schema["fields"],
    }
    return sha256_json(relevant)


def map_generation_params(config: dict[str, Any], schema: dict[str, Any]) -> dict[str, Any]:
    mapping = schema.get("fields") or {}
    output: dict[str, Any] = {}
    for business_key, value in config.items():
        if business_key in {"preset", "modelKey", "analysisModel", "generationProvider"}:
            continue
        field = mapping.get(business_key) or {}
        remote_key = field.get("originalField") or business_key
        output[str(remote_key)] = value
    return output


async def _run_json(executable: str, *arguments: str) -> dict[str, Any]:
    creation_flags = 0
    if os.name == "nt":
        creation_flags = 0x08000000  # CREATE_NO_WINDOW
    process = await asyncio.create_subprocess_exec(
        executable,
        *arguments,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        creationflags=creation_flags,
    )
    stdout, stderr = await process.communicate()
    if process.returncode != 0:
        message = stderr.decode("utf-8", errors="replace").strip()
        raise ModelRegistryError(f"official libtv CLI read failed: {message[:500]}")
    try:
        return json.loads(stdout.decode("utf-8"))
    except json.JSONDecodeError as exc:
        raise ModelRegistryError("official libtv CLI returned invalid JSON") from exc


async def refresh_model_registry(
    session: AsyncSession, settings: Settings, *, force: bool = False
) -> ModelSchemaSnapshot:
    now = datetime.now(UTC)
    current = await session.scalar(
        select(ModelSchemaSnapshot)
        .where(ModelSchemaSnapshot.model_key == MODEL_KEY)
        .order_by(ModelSchemaSnapshot.fetched_at.desc())
        .limit(1)
    )
    current_expires_at = as_utc(current.expires_at) if current is not None else None
    if current_expires_at is not None and current_expires_at > now and not force:
        return current
    payload = await _run_json(settings.libtv_executable, "model", MODEL_KEY)
    normalized = normalize_live_schema(payload)
    fingerprint = compatibility_fingerprint(normalized)
    existing = await session.scalar(
        select(ModelSchemaSnapshot).where(
            ModelSchemaSnapshot.compatibility_fingerprint == fingerprint
        )
    )
    if existing is not None:
        existing.fetched_at = now
        existing.expires_at = now + timedelta(minutes=30)
        existing.schema_json = normalized
        await session.flush()
        return existing
    snapshot = ModelSchemaSnapshot(
        cli_version="1.1.1",
        account_id=settings.deployment_id,
        team_id=None,
        workspace_id=settings.libtv_workspace_id,
        model_key=MODEL_KEY,
        schema_json=normalized,
        compatibility_fingerprint=fingerprint,
        fetched_at=now,
        expires_at=now + timedelta(minutes=30),
    )
    session.add(snapshot)
    await session.flush()
    return snapshot
