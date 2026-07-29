import hashlib
import json
from collections.abc import Iterable
from pathlib import Path
from typing import Any


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def sha256_json(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def ordered_assets_hash(assets: Iterable[dict[str, Any]]) -> str:
    ordered = sorted(assets, key=lambda item: int(item["order"]))
    return sha256_json(ordered)


def generation_intent_hash(payload: dict[str, Any]) -> str:
    required = {
        "userId",
        "parentTaskId",
        "variant",
        "projectUuid",
        "groupNodeKey",
        "nodeKey",
        "modelKey",
        "schemaFingerprint",
        "referenceAssets",
        "promptHash",
        "generationConfig",
        "assetVersion",
        "promptVersion",
    }
    missing = sorted(required - payload.keys())
    if missing:
        raise ValueError(f"intent hash is missing fields: {', '.join(missing)}")
    return sha256_json(payload)


ERROR_CODES = {
    "INPUT_INVALID",
    "ANALYSIS_SCHEMA_INVALID",
    "CONSISTENCY_REVIEW_REQUIRED",
    "SCHEMA_STALE",
    "SCHEMA_INCOMPATIBLE",
    "POINTS_LIMIT_EXCEEDED",
    "LIBTV_BALANCE_INSUFFICIENT",
    "MATERIALIZATION_RETRYABLE",
    "MATERIALIZATION_UNCERTAIN",
    "GENERATION_UNKNOWN",
    "GENERATION_TERMINAL_FAILED",
    "DOWNLOAD_RETRYABLE",
    "VALIDATION_MANUAL_REVIEW",
    "VERSION_CONFLICT",
    "IDEMPOTENCY_KEY_REUSED",
}


def map_error_code(category: str, submitted: bool = False) -> str:
    mapping = {
        "input": "INPUT_INVALID",
        "analysis": "ANALYSIS_SCHEMA_INVALID",
        "schema": "SCHEMA_INCOMPATIBLE",
        "points": "POINTS_LIMIT_EXCEEDED",
        "materialization": "MATERIALIZATION_UNCERTAIN",
        "download": "DOWNLOAD_RETRYABLE",
        "validation": "VALIDATION_MANUAL_REVIEW",
    }
    if category == "generation":
        return "GENERATION_UNKNOWN" if submitted else "GENERATION_TERMINAL_FAILED"
    return mapping.get(category, "MATERIALIZATION_RETRYABLE")


def compatible_schema(old: dict[str, Any], new: dict[str, Any], current: dict[str, Any]) -> bool:
    if int(new.get("maxMediaCount", 0)) < len(current.get("media", [])):
        return False
    old_fields = old.get("fields", {})
    new_fields = new.get("fields", {})
    for key, value in current.get("params", {}).items():
        if key not in new_fields:
            return False
        choices = new_fields[key].get("enum")
        if choices is not None and value not in choices:
            return False
        if key in old_fields and old_fields[key].get("originalField") != new_fields[key].get(
            "originalField"
        ):
            return False
    return True


def delivery_filename(
    business_date: str, user_id: str, parent_task_id: str, variant: str, revision: int
) -> str:
    return f"{business_date}_{user_id[:8]}_{parent_task_id[:8]}_{variant.lower()}_v{revision}.mp4"
