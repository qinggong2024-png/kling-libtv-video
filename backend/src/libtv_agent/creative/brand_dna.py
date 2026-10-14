"""Pure brand-style projection; no identity inference or source verification."""
from __future__ import annotations

import hashlib
import hmac
import json
import re
from collections.abc import Mapping
from datetime import date
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


def fit_purchase_reason(
    plan: Mapping[str, Any], facts: Mapping[str, Any], script: str | None,
    *, script_locked: bool = False,
) -> tuple[dict[str, Any], str | None]:
    """One SKU-specific fit heuristic inside the existing human script handoff."""
    truth = facts.get("truth_fields") or {}
    locks = (plan.get("locks") or {}).get("user_locks") or {}
    brand = plan.get("brand_dna") or {}
    audience = brand.get("audience") or plan.get("audience")
    feature = None
    feature_key = None
    for key in (
        "print", "graphic", "pattern", "text", "silhouette", "fit", "material", "color",
        "front_color",
    ):
        value = truth.get(key)
        if isinstance(value, dict):
            if value.get("evidence_status") not in {"USER_CONFIRMED", "OBSERVED_REFERENCE"}:
                continue
            value = value.get("value")
        if isinstance(value, str) and value.strip() and value.lower() not in {
            "unknown", "unverified", "n/a",
        }:
            feature, feature_key = value.strip(), key
            break
    reason = locks.get("primary_purchase_reason") or truth.get("purchase_reason")
    reason_source = "USER_LOCK" if locks.get("primary_purchase_reason") else "PRODUCT_DNA"
    if not isinstance(reason, str) or not reason.strip():
        reason = None
    record = truth.get("purchase_evidence") or {}
    scoped = False
    if isinstance(record, dict):
        try:
            start = date.fromisoformat(record.get("date_from", ""))
            end = date.fromisoformat(record.get("date_to", ""))
            scoped = bool(
                record.get("evidence_kind") == "USER_CONFIRMED"
                and bool(facts.get("product_id")) and bool(facts.get("source_hash"))
                and record.get("product_id") == facts.get("product_id")
                and record.get("source_hash") == facts.get("source_hash")
                and audience and record.get("audience") == audience
                and record.get("metric") == "purchase"
                and type(record.get("purchases")) is int and record["purchases"] > 0
                and record.get("attribution") and record.get("source")
                and start <= end
                and isinstance(record.get("reason"), str) and record["reason"].strip()
                and (reason is None or reason == record["reason"])
            )
        except (TypeError, ValueError):
            scoped = False
    if scoped:
        reason = record["reason"]
        reason_source = "USER_CONFIRMED_SCOPED_PURCHASE_RECORD"
    elif reason is None and feature:
        reason = (
            f"Express personal taste through {feature}"
            if feature_key in {"print", "graphic", "pattern", "text"}
            else f"Everyday styling with {feature}"
        )
        reason_source = "PRODUCT_AND_BRAND_HYPOTHESIS" if brand else "PRODUCT_HYPOTHESIS"
    evidence = "observed_with_scope" if scoped else "hypothesis" if reason else "unresolved"
    report = {
        "sourceVersion": "meta-creative.v1.13.15",
        "primaryPurchaseReason": reason, "productFeature": feature,
        "productFactKey": f"truth_fields.{feature_key}" if feature_key else None,
        "reasonSource": reason_source if reason else None,
        "audience": audience, "evidenceStatus": evidence,
        "scriptCarrier": None, "repairCount": 0, "status": "unresolved",
        "boundary": "SCRIPT_FIT_HEURISTIC_NOT_CONVERSION_APPROVAL",
        "scope": record if scoped else None,
    }
    if not reason or not feature or not script:
        return report, script
    proven_baseline = scoped and record.get("baseline_script") == script
    if script_locked or proven_baseline:
        report["status"] = (
            "preserved_locked_script" if script_locked else "preserved_proven_baseline"
        )
        return report, script
    carrier = (
        f"In the existing product-view moment, keep {feature} readable within the "
        f"selected framing to convey this purchase {evidence}: {reason}."
    )
    expressed = any(
        feature.casefold() in clause.casefold()
        and not re.search(
            r"\b(?:do not|don't|hide|obscure|replace|avoid|without|no)\b.*"
            + re.escape(feature), clause, re.IGNORECASE,
        )
        for clause in re.split(r"[.;\n]", script)
    )
    if expressed or carrier in script:
        report.update(status="represented", scriptCarrier="existing product expression")
        return report, script
    # Keep the same action, scene, duration and shots. Only the responsibility of
    # the already planned product view changes; no gesture or dialogue is added.
    report.update(status="one_moment_repaired", scriptCarrier=carrier, repairCount=1)
    return report, script + "\n" + carrier
