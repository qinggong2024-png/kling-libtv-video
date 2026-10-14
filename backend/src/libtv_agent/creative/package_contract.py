"""Read-only human handoff projection; never an execution or quality approval."""
from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

from libtv_agent.creative.brand_dna import fit_purchase_reason, validate_brand_dna
from libtv_agent.creative.reality_evidence import render_photographic_cues
from libtv_agent.creative.text_contract import (
    CONTRACT_SCHEMA,
    canonical_hash,
    validate_prompt_preservation,
    validate_text_contract,
)
from libtv_agent.creative.visual_plan import VisualPlan, compile_visual_video_prompt

CONTENT_FIELDS = (
    "direction", "audience", "characterDNA", "sceneDNA", "cameraDNA",
    "imagePrompt", "videoPrompt", "shotPlan", "qualityChecklist",
)


def _object(value: Any, name: str) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise TypeError(f"{name} must be a JSON object")
    return dict(value)


def _json(value: Any) -> str:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False,
    )


def _required_text(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a nonempty string")
    return value


def _packages(snapshot: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Index by declared shot ID; collection position is never an identity."""
    packages: dict[str, dict[str, Any]] = {}
    root = snapshot.get("package")
    storyboard = _object(snapshot.get("storyboard") or {}, "storyboard")
    nested = storyboard.get("packages") or {}
    if isinstance(nested, Mapping):
        entries = list(nested.items())
    elif isinstance(nested, list):
        entries = [(None, item) for item in nested]
    else:
        raise TypeError("storyboard.packages must be an object or array")
    if root is not None:
        root = _object(root, "package")
        if root.get("shot_id") != "FIRST_FRAME":
            raise ValueError("root package requires explicit FIRST_FRAME shot_id")
        entries.insert(0, ("FIRST_FRAME", root))
    for key, raw in entries:
        package = _object(raw, "package")
        shot_id = _required_text(package.get("shot_id"), "shot_id")
        _required_text(package.get("package_id"), "package_id")
        _required_text(package.get("prompt"), "prompt")
        if type(package.get("revision")) is not int or package["revision"] < 1:
            raise ValueError("package revision must be a positive integer")
        if key is not None and key != shot_id:
            raise ValueError("storyboard key conflicts with explicit shot_id")
        if shot_id in packages:
            if key == "FIRST_FRAME" and root == package == packages[shot_id]:
                continue
            raise ValueError(f"duplicate shot_id: {shot_id}")
        packages[shot_id] = package
    identifiers = [package["package_id"] for package in packages.values()]
    if len(identifiers) != len(set(identifiers)):
        raise ValueError("package_id must be unique across shots")
    return packages


def _frozen_context(source: dict, package_id: str) -> tuple[dict, dict]:
    contracts = _object(source.get("package_contracts") or {}, "package_contracts")
    stored = _object(contracts.get(package_id) or {}, "package_contract")
    frozen = stored.get("text_contract")
    if frozen is None and source.get("text_contract") is not None:
        legacy = _object(source["text_contract"], "text_contract")
        if _object(legacy.get("package") or {}, "text_contract.package").get(
            "package_id"
        ) == package_id:
            frozen = legacy
            stored = {
                "text_contract": legacy,
                "registry_snapshot": source.get("registry_snapshot"),
            }
    frozen = _object(frozen, "frozen text_contract") if frozen is not None else {}
    if frozen.get("schema_version") != CONTRACT_SCHEMA:
        raise ValueError(f"frozen text contract required: {package_id}")
    package = _object(frozen.get("package"), "frozen package")
    if package.get("package_id") != package_id:
        raise ValueError("frozen package_id conflicts with contract key")
    return frozen, stored


def _validated_context(
    source: dict, package_id: str, actual_package: dict | None = None,
) -> tuple[dict, dict, dict, dict]:
    frozen, stored = _frozen_context(source, package_id)
    package = actual_package if actual_package is not None else frozen["package"]
    _required_text(package.get("shot_id"), "shot_id")
    if actual_package is None:
        plan = _object(frozen.get("plan"), "frozen plan")
        facts = _object(frozen.get("facts_snapshot"), "frozen facts_snapshot")
    else:
        plan = _object(source.get("plan"), "plan")
        facts = _object(source.get("facts_snapshot"), "facts_snapshot")
    registry = _object(stored.get("registry_snapshot"), "registry_snapshot")
    if canonical_hash(registry) != canonical_hash(frozen.get("registry_snapshot")):
        raise ValueError("package registry differs from frozen registry")
    if actual_package is not None and source.get("registry_snapshot") is not None:
        legacy_registry = _object(source["registry_snapshot"], "registry_snapshot")
        legacy_frozen = _object(source.get("text_contract") or {}, "text_contract")
        # The legacy pointer can name the last compiled storyboard package.
        # It must agree with its frozen record even when exporting the root.
        if legacy_frozen:
            payload = {
                key: value for key, value in legacy_frozen.items() if key != "contract_hash"
            }
            if legacy_frozen.get("contract_hash") != canonical_hash(payload):
                raise ValueError("legacy frozen contract hash mismatch")
            if canonical_hash(legacy_registry) != canonical_hash(
                legacy_frozen.get("registry_snapshot")
            ):
                raise ValueError("current registry differs from frozen registry")
        body = _object(legacy_registry.get("payload_json", legacy_registry), "registry payload")
        if body.get("package_id") == package_id:
            registry = legacy_registry
        elif not legacy_frozen:
            raise ValueError("unbound current registry")
    validation = validate_text_contract(plan, package, frozen, registry, facts)
    if not validation["valid"]:
        codes = [item["code"] for item in validation["failures"]]
        raise ValueError(f"package text contract is {validation['status']}: {', '.join(codes)}")
    return package, plan, facts, stored


def _shot_plan(source: dict, selected: dict) -> list[dict]:
    """Only the selected immutable package and its ancestors, never newer siblings."""
    lineage = []
    package = selected
    seen: set[str] = set()
    while True:
        package_id = package["package_id"]
        if package_id in seen:
            raise ValueError("package parent chain contains a cycle")
        seen.add(package_id)
        lineage.append({
            "shotId": package["shot_id"],
            "packageId": package_id,
            "revision": package["revision"],
            "sourcePackage": package,
        })
        parent_id = package.get("parent_package_id")
        if parent_id is None:
            break
        _required_text(parent_id, "parent_package_id")
        package, _, _, _ = _validated_context(source, parent_id)
    return list(reversed(lineage))


def _field(
    sources: tuple[tuple[str, dict], ...], camel: str, snake: str,
) -> tuple[Any, str | None]:
    for path, source in sources:
        if camel in source and snake in source and source[camel] != source[snake]:
            raise ValueError(f"conflicting aliases for {camel}")
        for key in dict.fromkeys((camel, snake)):
            if key in source:
                return source[key], f"{path}.{key}"
    return None, None


def project_creative_package(
    snapshot: Mapping[str, Any], package_id: str | None = None,
) -> dict[str, Any]:
    """Project a raw CreativeTask snapshot into eleven JSON-only handoff fields.

    With no package_id, select snapshot.package. Otherwise resolve the exact ID
    from current packages or package_contracts. Missing facts remain unresolved.
    The result is detached from the input and cannot authorize production.
    """
    # JSON round-trip both detaches nested data and rejects non-persistable values.
    source = json.loads(_json(_object(snapshot, "snapshot")))
    if package_id is None:
        package_id = _object(source.get("package"), "package").get("package_id")
    _required_text(package_id, "package_id")
    packages = _packages(source)
    current = next(
        (item for item in packages.values() if item["package_id"] == package_id), None,
    )
    package, plan, facts, contract = _validated_context(source, package_id, current)
    brand = _object(plan.get("brand_dna") or {}, "plan.brand_dna")
    if brand and not validate_brand_dna(brand):
        raise ValueError("brand DNA content hash mismatch")
    sources = (("package", package), ("plan", plan))
    projection: dict[str, Any] = {}
    field_sources: dict[str, str | None] = {}
    statuses: dict[str, str] = {}
    for camel, snake in (
        ("direction", "direction"), ("audience", "audience"),
        ("characterDNA", "character_dna"), ("sceneDNA", "scene_dna"),
        ("cameraDNA", "camera_dna"), ("videoPrompt", "video_prompt"),
    ):
        value, path = _field(sources, camel, snake)
        if value is not None and not isinstance(value, (dict, str)):
            raise TypeError(f"{camel} must be an object, string or null")
        if camel == "videoPrompt" and value is not None and not isinstance(value, str):
            raise TypeError("videoPrompt must be a string or null")
        if isinstance(value, str) and not value.strip():
            value = None
        projection[camel] = value
        field_sources[camel] = path
        statuses[camel] = "PRESENT" if value is not None else "UNRESOLVED"

    if projection["direction"] is None and plan.get("selected_direction") is not None:
        directions = plan.get("directions") or []
        if not isinstance(directions, list):
            raise TypeError("plan.directions must be an array")
        matches = [
            item for item in directions
            if isinstance(item, dict) and item.get("id") == plan["selected_direction"]
        ]
        if len(matches) != 1:
            raise ValueError("selected_direction requires one matching explicit direction")
        projection["direction"] = matches[0]
        field_sources["direction"] = "plan.directions[selected_direction]"
        statuses["direction"] = "PROPOSED"
    direction = projection["direction"]
    for field, key in (("characterDNA", "human"), ("sceneDNA", "scene"), ("cameraDNA", "camera")):
        if projection[field] is None and isinstance(direction, dict) and direction.get(key):
            projection[field] = {
                "description": _required_text(direction[key], f"direction.{key}"),
                "origin": "PROPOSED",
            }
            field_sources[field] = f"{field_sources['direction']}.{key}"
            statuses[field] = "PROPOSED"

    explicit_image, _ = _field((("package", package),), "imagePrompt", "image_prompt")
    if explicit_image is not None and explicit_image != package["prompt"]:
        raise ValueError("imagePrompt must not replace the frozen package prompt")
    projection["imagePrompt"] = package["prompt"]
    field_sources["imagePrompt"] = "package.prompt"
    statuses["imagePrompt"] = "PRESENT"
    reality = package.get("reality") or []
    camera = next(
        (item.get("decision") for item in reality
         if isinstance(item, dict) and item.get("dimension") == "Camera"),
        None,
    )
    behavior = direction.get("behavior") if isinstance(direction, dict) else None
    scene = direction.get("scene") if isinstance(direction, dict) else None
    if projection["cameraDNA"] is None and isinstance(camera, str) and camera.strip():
        projection["cameraDNA"] = {"description": camera, "origin": "PROPOSED"}
        field_sources["cameraDNA"] = "package.reality[Camera].decision"
        statuses["cameraDNA"] = "PROPOSED"
    if projection["characterDNA"] is None and isinstance(behavior, str) and behavior.strip():
        projection["characterDNA"] = {
            "behavior": behavior, "identity": None, "appearance": None, "origin": "PROPOSED",
        }
        field_sources["characterDNA"] = f"{field_sources['direction']}.behavior"
        statuses["characterDNA"] = "PROPOSED"
    for field in ("audience", "characterDNA"):
        if brand.get(field) is not None and (
            projection[field] is None
            or (field == "characterDNA" and statuses[field] == "PROPOSED")
        ):
            projection[field] = brand[field]
            field_sources[field] = f"plan.brand_dna.{field}"
            statuses[field] = "PROPOSED"
    # This copyable draft is separate from the immutable execution Prompt.
    if (
        projection["videoPrompt"] is None
        and isinstance(behavior, str) and behavior.strip()
        and isinstance(scene, str) and scene.strip()
    ):
        marker = "FAKE SOURCE. " if plan.get("evidence") == "FAKE_NOT_IMAGE_ANALYSIS" else ""
        projection["videoPrompt"] = (
            f"{marker}PROPOSED HUMAN HANDOFF; requires human confirmation. "
            f"Use a separately reviewed first-frame image. Preserve canonical garment "
            f"SHA {plan['source_hash']}, its visible print, silhouette and garment details. "
            f"Scene: {scene}. Subject behavior: {behavior}. "
            + (f"Camera reference: {camera}. " if camera else "")
            + "Preserve the approved subject and environment from that image; "
            "do not invent unseen garment details. Avoid garment deformation and "
            "abrupt camera changes. Duration and motion timing require human confirmation."
        )
        constraints = render_photographic_cues(reality)
        if constraints:
            projection["videoPrompt"] += f"\nInherited photographic relations:\n{constraints}"
        field_sources["videoPrompt"] = (
            f"proposed-video-handoff.v1({field_sources['direction']}, "
            "package.reality[Camera], frozen plan.source_hash)"
        )
        statuses["videoPrompt"] = "PROPOSED"
    purchase_fit = {"status": "legacy_not_checked"}
    visual = (
        VisualPlan.model_validate(package["visual_plan"])
        if package.get("visual_plan") is not None else None
    )
    if visual is not None and statuses["videoPrompt"] == "PROPOSED":
        projection["videoPrompt"] += "\n" + compile_visual_video_prompt(
            visual, duration_seconds=sum(shot.duration_seconds for shot in visual.shots),
        )
    if any(item.get("compiler_version") for item in reality):
        purchase_fit, projection["videoPrompt"] = fit_purchase_reason(
            plan, facts, projection["videoPrompt"],
            script_locked=statuses["videoPrompt"] == "PRESENT",
        )
    projection["shotPlan"] = _shot_plan(source, package)
    field_sources["shotPlan"] = "selected package + frozen parent chain (explicit shot_id)"
    statuses["shotPlan"] = "PRESENT"
    checklist, path = _field(sources, "qualityChecklist", "quality_checklist")
    if checklist is None:
        reality = package.get("reality") or []
        if not isinstance(reality, list) or any(not isinstance(item, dict) for item in reality):
            raise TypeError("package.reality must be an array of objects")
        checklist = [
            {
                "dimension": item.get("dimension"),
                "expectation": item.get("decision"),
                "evidence": item.get("evidence"),
                "status": "UNVERIFIED",
                **{
                    key: item[key] for key in (
                        "rule_id", "rules_version", "rules_hash", "required_context",
                        "generation_constraint", "judgment_standard", "review_axis",
                        "revision_module", "causal_variable",
                        "compiler_version", "capture_mode", "compiled_cue",
                        "causal_trigger", "physical_relation", "visible_result",
                    ) if key in item
                },
            }
            for item in reality
        ]
        path = "package.reality"
        statuses["qualityChecklist"] = "PROPOSED" if checklist else "UNRESOLVED"
    else:
        if not isinstance(checklist, list):
            raise TypeError("qualityChecklist must be an array")
        statuses["qualityChecklist"] = "PRESENT" if checklist else "UNRESOLVED"
    projection["qualityChecklist"] = checklist
    field_sources["qualityChecklist"] = path

    asset = _object(source.get("asset") or {}, "asset")
    # A historical package can use only source bytes identified by its old plan.
    if asset.get("sha256") != plan.get("source_hash"):
        if current is not None:
            raise ValueError("current source asset conflicts with frozen source hash")
        asset = {}
    markers = {
        key: source[key] for key in ("mode", "provider", "synthetic", "qualification_scope")
        if key in source
    }
    evidence = {
        "planEvidence": plan.get("evidence"),
        "claims": plan.get("claims", []),
        "reality": package.get("reality", []),
        "packageContract": contract,
        "sourceMarkers": markers,
        "packageOriginEvidence": package.get("origin_evidence"),
        "fieldSources": field_sources,
        "promptPreflight": validate_prompt_preservation(
            package["prompt"], reality, plan.get("locks") or {},
        ),
        "purchaseReasonFit": purchase_fit,
        **({"visualPlan": visual.model_dump(mode="json")} if visual is not None else {}),
    }
    # Evidence-only export never promotes results, including fake human PASS.
    synthetic = (
        any(token in _json({"plan": plan, "package": package, "markers": markers}).upper()
            for token in ("FAKE", "OFFLINE_SYNTHETIC", '"SYNTHETIC":TRUE'))
    )
    projection["provenance"] = {
        "schemaVersion": "creative-package.v1",
        "packageId": package["package_id"],
        "revision": package["revision"],
        "parentPackageId": package.get("parent_package_id"),
        "shotId": package["shot_id"],
        "purpose": package.get("purpose"),
        "factsRevision": package.get("facts_revision"),
        "productId": facts.get("product_id"),
        "productVersionId": facts.get("product_version_id"),
        "sourceHash": plan.get("source_hash"),
        "productFacts": facts,
        **({"brandDNA": brand} if brand else {}),
        "sourceAssets": [asset] if asset else [],
        "locks": plan.get("locks"),
        "locksHash": package.get("locks_hash"),
        "preservationHash": package.get("preservation_hash"),
        "sourcePackage": package,
        "originEvidence": evidence,
        "synthetic": synthetic,
        "qualificationScope": (
            "OFFLINE_SYNTHETIC_ONLY" if synthetic else "REAL_INPUT_UNVERIFIED"
        ),
        "qualified": False,
        "deliverable": False,
        "providerSubmissionAllowed": False,
    }
    projection["fieldStatus"] = statuses
    return json.loads(_json(projection))


def serialize_creative_package(projection: Mapping[str, Any]) -> str:
    """Stable compact ASCII JSON, retaining exact frozen Prompt/hash strings."""
    return _json(_object(projection, "projection"))


def render_creative_package_text(projection: Mapping[str, Any]) -> str:
    """Provider-neutral copy text for GPT Image, Nano Banana, Kling or a team."""
    package = _object(projection, "projection")
    provenance = _object(package.get("provenance"), "provenance")
    sections = [
        "Creative Package",
        f"Package: {provenance['packageId']} / revision {provenance['revision']}",
        f"Shot: {provenance['shotId']}",
        f"Evidence scope: {provenance['qualificationScope']}",
        "Human handoff only; no Provider submission, qualification or delivery approval.",
    ]
    for field in CONTENT_FIELDS:
        value = package[field]
        text = "UNRESOLVED" if value is None else (
            value if isinstance(value, str) else _json(value)
        )
        sections.append(f"{field} [{package['fieldStatus'][field]}]:\n{text}")
    sections.append(f"provenance:\n{_json(provenance)}")
    return "\n\n".join(sections) + "\n"
