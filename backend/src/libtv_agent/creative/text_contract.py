"""Pure persisted-text integrity checks; no pixel or semantic quality claims."""
from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping
from typing import Any

REALITY_ORDER = (
    "Camera", "Lighting", "Composition", "Human Behavior", "Environment", "Imperfection",
)
CONTRACT_SCHEMA = "creative-text-contract.v1"
BOUNDARIES = (
    "visual_truth", "photographic_causality", "semantic_free_revision_safety",
    "substantive_creative_difference",
)


def _mapping(value: Any) -> dict:
    if hasattr(value, "model_dump"):
        value = value.model_dump(mode="json")
    if not isinstance(value, Mapping):
        raise TypeError("expected a JSON mapping or a Pydantic contract")
    # Detach mutable inputs and reject values that cannot be persisted as JSON.
    return json.loads(json.dumps(dict(value), allow_nan=False))


def canonical_hash(value: Any) -> str:
    """SHA-256 over UTF-8 sorted-key compact ASCII JSON; list order is significant."""
    return hashlib.sha256(
        json.dumps(
            value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False,
        ).encode("utf-8")
    ).hexdigest()


def freeze_text_contract(
    plan: Mapping, package: Mapping, registry_snapshot: Mapping, facts_snapshot: Mapping,
) -> dict:
    """Build a context to persist at D4, not an authorization or a trusted record.

    Persist once, retrieve from immutable storage at E1, never reconstruct from
    the mutable task at E1. Registry snapshots are explicit JSON adapters.
    """
    payload = {
        "schema_version": CONTRACT_SCHEMA,
        "plan": _mapping(plan),
        "package": _mapping(package),
        "registry_snapshot": _mapping(registry_snapshot),
        "facts_snapshot": _mapping(facts_snapshot),
    }
    return {**payload, "contract_hash": canonical_hash(payload)}


def _sha(value: Any) -> bool:
    return isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value) is not None


def validate_text_contract(
    plan: Mapping,
    package: Mapping,
    frozen_package: Mapping,
    registry_snapshot: Mapping,
    facts_snapshot: Mapping,
) -> dict:
    """Compare actual content with a caller-loaded immutable frozen record.

    Accepts a freeze_text_contract context or an existing bare PackageRevision.
    Bare packages cannot prove original input context and never receive a full
    static-rule pass. No IO or Provider calls. Storage trust is the caller's duty.
    """
    failures: list[dict] = []
    unverified = [{"code": code, "detail": "outside a pure text gate"} for code in BOUNDARIES]
    checks: list[dict] = []
    missing: list[dict] = []

    def check(code: str, condition: bool, detail: str) -> None:
        checks.append({"code": code, "status": "static_rule_validated" if condition else "failed"})
        if not condition:
            failures.append({"code": code, "detail": detail})

    def unknown(code: str, detail: str) -> None:
        issue = {"code": code, "detail": detail}
        missing.append(issue)
        unverified.append(issue)

    try:
        plan, package, frozen, registry, facts = (
            _mapping(value)
            for value in (plan, package, frozen_package, registry_snapshot, facts_snapshot)
        )
        complete = frozen.get("schema_version") == CONTRACT_SCHEMA
        if complete:
            payload = {key: value for key, value in frozen.items() if key != "contract_hash"}
            check(
                "FROZEN_RECORD_HASH", frozen.get("contract_hash") == canonical_hash(payload),
                "frozen context content hash is inconsistent",
            )
            expected = _mapping(frozen["package"])
            for label, actual in (
                ("plan", plan), ("facts_snapshot", facts), ("registry_snapshot", registry),
            ):
                check(
                    f"FROZEN_{label.upper()}",
                    canonical_hash(actual) == canonical_hash(frozen.get(label)),
                    f"actual {label} differs from immutable context",
                )
        else:
            expected = frozen
            unknown("FROZEN_CONTEXT_MISSING", "bare package lacks immutable input snapshots")
        check(
            "FROZEN_PACKAGE", canonical_hash(package) == canonical_hash(expected),
            "actual package differs from immutable package; "
            "self-computed hashes cannot authorize it",
        )
        for key in ("package_id", "shot_id", "locks_hash"):
            check(key.upper(), isinstance(package.get(key), str) and bool(package[key].strip()),
                  f"{key} must be a nonempty string")
        check("PACKAGE_REVISION", type(package.get("revision")) is int and package["revision"] > 0,
              "package revision must be a positive integer")
        check("PROMPT", isinstance(package.get("prompt"), str) and bool(package["prompt"].strip()),
              "actual Prompt is missing")

        revision = facts.get("facts_revision")
        check("FACTS_REVISION", type(revision) is int and revision > 0
              and type(plan.get("facts_revision")) is int
              and type(package.get("facts_revision")) is int
              and plan.get("facts_revision") == revision
              and package.get("facts_revision") == revision,
              "claim/plan/package must reference the actual facts revision")
        check("FACTS_SNAPSHOT_HASH", plan.get("facts_snapshot_hash") == canonical_hash(facts),
              "plan hash must cover the actual facts, not a snapshot's claimed hash")
        for key in ("product_id", "product_version_id"):
            check(key.upper(), bool(plan.get(key)) and plan.get(key) == facts.get(key),
                  f"{key} does not identify the actual facts snapshot")

        source_sha = plan.get("source_hash")
        check("SOURCE_SHA_FORMAT", _sha(source_sha), "source_hash must be a lowercase SHA-256")
        # Legacy object_key strings prove provenance keys, not an asset hash.
        source_records = facts.get("source_asset_references", [])
        source_shas = [
            record.get("sha256") for record in source_records if isinstance(record, dict)
        ] if isinstance(source_records, list) else []
        if "source_hash" in facts:
            source_shas.append(facts["source_hash"])
        if source_shas:
            check("SOURCE_FACT_SHA", source_sha in source_shas,
                  "canonical source SHA is not in the persisted facts")
        else:
            unknown("SOURCE_FACT_SHA_MISSING", "facts contain no source SHA evidence")
        for key in ("source_hash", "product_id", "product_version_id", "facts_snapshot_hash"):
            if key in package:
                check(f"PACKAGE_{key.upper()}", package[key] == plan.get(key),
                      f"actual package {key} disagrees with plan")

        locks = plan.get("locks")
        if isinstance(locks, dict) and locks:
            check("LOCKS_HASH", package.get("locks_hash") == canonical_hash(locks),
                  "locks_hash must cover actual product and user locks")
            check("PRODUCT_LOCK", locks.get("product_id") == plan.get("product_id")
                  and locks.get("source_hash") == source_sha,
                  "actual product lock differs from canonical source")
            if not locks.get("user_locks"):
                unknown("USER_LOCKS_MISSING", "explicit user-lock snapshot is absent")
        else:
            unknown("LOCK_SNAPSHOT_MISSING", "opaque locks_hash cannot prove actual user locks")

        claims = plan.get("claims")
        check("CLAIMS_SHAPE", isinstance(claims, list) and bool(claims),
              "grounded claims must be a nonempty list")
        for index, claim in enumerate(claims if isinstance(claims, list) else []):
            if not isinstance(claim, dict):
                check("CLAIM_SHAPE", False, f"claim {index} must be an object")
                continue
            keys = claim.get("source_fact_keys")
            check("CLAIM_SOURCE_KEYS", isinstance(keys, list) and bool(keys) and all(
                isinstance(key, str) and bool(key.strip()) and key in facts
                and facts[key] is not None and facts[key] != [] and facts[key] != ""
                for key in (keys if isinstance(keys, list) else [])
            ), f"claim {index} needs real, nonempty fact keys")
            check("CLAIM_FACTS_REVISION", type(claim.get("facts_revision")) is int
                  and claim.get("facts_revision") == revision,
                  f"claim {index} references a different facts revision")
            check("CLAIM_BASIS", isinstance(claim.get("confidence_basis"), str)
                  and bool(claim["confidence_basis"].strip()),
                  f"claim {index} needs nonempty evidence basis")

        reality = package.get("reality")
        check("REALITY_ORDER", isinstance(reality, list) and all(
            isinstance(item, dict) for item in reality
        ) and tuple(item.get("dimension") for item in reality) == REALITY_ORDER,
              "six actual dimensions must appear exactly in the fixed order")
        for item in reality if isinstance(reality, list) else []:
            if not isinstance(item, dict):
                continue
            decision = item.get("decision")
            check("REALITY_DECISION", isinstance(decision, str) and bool(decision.strip()),
                  f"{item.get('dimension')} needs an actual decision")
            if isinstance(decision, str) and decision.strip().upper() in {"N/A", "NA"}:
                reason = item.get("reason") or item.get("na_reason")
                check("REALITY_NA_REASON", isinstance(reason, str) and bool(reason.strip()),
                      f"{item.get('dimension')} N/A needs a reason")

        # ORM adapter: {prompt_key, version, content_hash, payload_json}; the
        # payload needs both the literal Prompt and a rules manifest for proof.
        body = registry.get("payload_json", registry)
        check("REGISTRY_SHAPE", isinstance(body, dict), "Registry payload must be an object")
        if isinstance(body, dict):
            for key in ("prompt_key", "version", "content_hash"):
                if not registry.get(key):
                    unknown("REGISTRY_IDENTITY_MISSING", f"Registry {key} is absent")
            check("REGISTRY_PACKAGE", body.get("package_id") == package.get("package_id"),
                  "Registry refers to another package")
            if "prompt" in body:
                check("REGISTRY_PROMPT", body["prompt"] == package.get("prompt"),
                      "Registry body differs from actual Prompt")
                check("REGISTRY_CONTENT_HASH",
                      registry.get("content_hash") == canonical_hash(body["prompt"]),
                      "Registry content_hash must cover its literal Prompt")
            else:
                unknown("REGISTRY_BODY_MISSING", "legacy Registry has no literal Prompt")
            manifest = body.get("manifest")
            if isinstance(manifest, dict) and manifest:
                check("REGISTRY_MANIFEST_HASH",
                      body.get("manifest_hash") == canonical_hash(manifest),
                      "Registry manifest hash is inconsistent")
            else:
                unknown("REGISTRY_MANIFEST_MISSING", "full Registry rules version is unproven")
    except (TypeError, ValueError, KeyError, OverflowError, RecursionError) as exc:
        check("INPUT_INVALID", False, str(exc))

    status = "rejected" if failures else "unverified" if missing else "static_rule_validated"
    return {
        "valid": status == "static_rule_validated",
        "status": status,
        "static_rule_validated": [item["code"] for item in checks
                                  if item["status"] == "static_rule_validated"],
        "checks": checks, "failures": failures, "unverified": unverified,
        "boundary": dict.fromkeys(BOUNDARIES, "unverified"),
    }
