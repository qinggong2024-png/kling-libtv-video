"""Hashing and integrity helpers for immutable CreativeState revisions."""
from __future__ import annotations

import hashlib
import json
from typing import Any

from pydantic import ValidationError

from libtv_agent.creative.state import CreativeStateRevision, ProductState


def canonical_json(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


def canonical_hash(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def _dump(value: Any) -> Any:
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    return value


def revision_hash_payload(revision: CreativeStateRevision) -> dict[str, Any]:
    payload = revision.model_dump(mode="json")
    payload.pop("content_hash", None)
    return payload


def calculate_revision_hash(revision: CreativeStateRevision) -> str:
    return canonical_hash(revision_hash_payload(revision))


def calculate_locks_hash(product: ProductState) -> str:
    return canonical_hash(product.locks.model_dump(mode="json"))


def calculate_source_snapshot_hash(product: ProductState) -> str:
    return canonical_hash(
        {
            "product_id": product.product_id,
            "product_version_id": product.product_version_id,
            "owner_id": product.owner_id,
            "sku": product.sku,
            "source_assets": [asset.model_dump(mode="json") for asset in product.source_assets],
            "truth": product.truth.model_dump(mode="json"),
            "license": product.license.model_dump(mode="json"),
        }
    )


def seal_revision(revision: CreativeStateRevision) -> CreativeStateRevision:
    """Return a copy with hashes computed from the immutable revision payload."""
    return revision.model_copy(
        update={
            "content_hash": calculate_revision_hash(revision),
            "locks_hash": calculate_locks_hash(revision.product),
            "source_snapshot_hash": calculate_source_snapshot_hash(revision.product),
        }
    )


def validate_revision_integrity(revision: CreativeStateRevision) -> None:
    expected = {
        "content_hash": calculate_revision_hash(revision),
        "locks_hash": calculate_locks_hash(revision.product),
        "source_snapshot_hash": calculate_source_snapshot_hash(revision.product),
    }
    actual = {
        "content_hash": revision.content_hash,
        "locks_hash": revision.locks_hash,
        "source_snapshot_hash": revision.source_snapshot_hash,
    }
    mismatches = [key for key, value in expected.items() if actual[key] != value]
    if mismatches:
        raise ValueError(f"creative state revision hash mismatch: {', '.join(mismatches)}")


def immutable_json(value: Any) -> str:
    """Serialize a state snapshot for append-only storage or an evidence record."""
    return canonical_json(_dump(value))


def validate_revision_payload(payload: dict[str, Any]) -> CreativeStateRevision:
    try:
        revision = CreativeStateRevision.model_validate(payload)
    except ValidationError:
        raise
    validate_revision_integrity(revision)
    return revision
