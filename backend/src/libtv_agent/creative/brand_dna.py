"""Pure brand-style projection; no identity inference or source verification."""
from __future__ import annotations

import hashlib
import hmac
import json
from collections.abc import Mapping
from typing import Any

from libtv_agent.templates.site_style_profiles import SiteStyleProfile

SCHEMA_VERSION = "brand-dna.v1"


def _canonical_json(value: Any) -> str:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False,
    )


def _hash(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _text(source: dict[str, Any], field: str) -> str:
    value = source.get(field)
    if value is None:
        return ""
    if not isinstance(value, str):
        raise TypeError(f"{field} must be a string or null")
    return value


def _strings(source: dict[str, Any], field: str) -> list[str]:
    value = source.get(field)
    if value is None:
        return []
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise TypeError(f"{field} must be an array of strings or null")
    return value


def project_brand_dna(profile: SiteStyleProfile | Mapping[str, Any]) -> dict[str, Any]:
    """Project a directory record without looking it up or deciding selectability.

    Dataclass inputs use their public API representation. Missing text/arrays
    become empty strings/arrays; missing audience stays null. Source ID/version
    must be explicit. Retired records and unknown IDs remain valid historical
    sources. The detached source snapshot preserves unmapped fields and nulls.

    Hashes use UTF-8 compact, key-sorted, ASCII-escaped JSON, with NaN forbidden.
    sourceHash covers sourceProfile; contentHash covers the entire result except
    contentHash itself. Neither hash authenticates or verifies an external source.
    """
    if isinstance(profile, SiteStyleProfile):
        raw = profile.to_public_dict()
    elif isinstance(profile, Mapping):
        raw = dict(profile)
    else:
        raise TypeError("profile must be a SiteStyleProfile or API JSON object")
    # Round-trip before projection to detach all nested content and reject non-JSON values.
    source = json.loads(_canonical_json(raw))
    for field in ("id", "version"):
        if not _text(source, field).strip():
            raise ValueError(f"profile {field} must be a nonempty string")
    audience = source.get("audience")
    if audience is not None and not isinstance(audience, str):
        raise TypeError("audience must be a string or null")

    result = {
        "profileId": source["id"],
        "profileVersion": source["version"],
        "name": _text(source, "name"),
        "audience": audience,
        "visualDNA": {
            "tone": _text(source, "tone"),
            "palette": _strings(source, "palette"),
        },
        "characterDNA": {
            "expressionLanguage": _text(source, "expressionLanguage"),
            "expressionPool": _strings(source, "expressionPool"),
            "identity": None,
        },
        "sceneDNA": {
            "preferredEnvironment": _strings(source, "preferredEnvironment"),
        },
        "cameraDNA": {
            "language": _text(source, "cameraLanguage"),
            "pool": _strings(source, "cameraPool"),
            "preferredShots": _strings(source, "preferredShots"),
        },
        "avoid": {
            "mismatches": _strings(source, "forbiddenMismatches"),
            "motion": _strings(source, "forbiddenMotion"),
        },
        "productConstraints": {
            "priorities": _strings(source, "productPriorities"),
            "riskRules": _strings(source, "productRiskRules"),
        },
        "provenance": {
            "schemaVersion": SCHEMA_VERSION,
            "status": source.get("status"),
            "libraryScope": source.get("libraryScope"),
            "sourceUrls": _strings(source, "sourceUrls"),
            "retrievedAt": source.get("retrievedAt"),
            "evidenceLevel": source.get("evidenceLevel"),
            "sourceProfile": source,
            "sourceHash": _hash(source),
        },
    }
    result["contentHash"] = _hash(result)
    # Detach both from the caller and between projected fields and provenance.
    return json.loads(_canonical_json(result))


def validate_brand_dna(snapshot: Mapping[str, Any]) -> bool:
    """Check schema marker and content hash only; never verify external evidence.

    Return False for malformed JSON or a changed payload. This is an integrity
    check, not a signature, schema validator, or permission to select a brand.
    """
    if not isinstance(snapshot, Mapping):
        return False
    try:
        payload = dict(snapshot)
        expected = payload.pop("contentHash", None)
        if not isinstance(expected, str) or len(expected) != 64:
            return False
        if any(character not in "0123456789abcdef" for character in expected):
            return False
        provenance = payload.get("provenance")
        if not isinstance(provenance, Mapping):
            return False
        if provenance.get("schemaVersion") != SCHEMA_VERSION:
            return False
        return hmac.compare_digest(expected, _hash(payload))
    except (TypeError, ValueError, OverflowError, RecursionError):
        return False
