"""Persisted media provenance gates for legacy image workflows."""

from __future__ import annotations

from typing import Any

from libtv_agent.domain.models import (
    ImageGenerationBatch,
    ImageGenerationItem,
    ImageGenerationOutput,
)

OFFLINE_PROVIDERS = frozenset({"fake", "offline", "synthetic", "offline_synthetic"})
OFFLINE_SCOPE = "OFFLINE_SYNTHETIC_ONLY"


def _mapping(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _has_offline_marker(value: Any) -> bool:
    data = _mapping(value)
    if data.get("offlineSynthetic") is True or data.get("synthetic") is True:
        return True
    return any(
        str(data.get(key, "")).upper() == OFFLINE_SCOPE
        for key in ("qualificationScope", "qualification_scope", "qualification")
    )


def is_offline_synthetic_batch(batch: ImageGenerationBatch) -> bool:
    """Use durable batch provenance, without relying on mutable quality JSON."""

    if str(batch.provider or "").strip().lower() in OFFLINE_PROVIDERS:
        return True
    return _has_offline_marker(batch.request_json)


def is_offline_synthetic_item(
    item: ImageGenerationItem, *, batch: ImageGenerationBatch | None = None
) -> bool:
    if is_offline_synthetic_batch(batch or item.batch):
        return True
    if str(item.provider_task_id or "").lower().startswith("fake:"):
        return True
    return _has_offline_marker(item.request_json)


def is_offline_synthetic_output(
    output: ImageGenerationOutput,
    *,
    item: ImageGenerationItem | None = None,
    batch: ImageGenerationBatch | None = None,
) -> bool:
    """Return true only when persisted batch/item/output evidence agrees."""

    if _has_offline_marker(output.quality_gates_json):
        return True
    if str(output.remote_url or "").lower().startswith("fake://"):
        return True
    return is_offline_synthetic_item(item or output.item, batch=batch)
