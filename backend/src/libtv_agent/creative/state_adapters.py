"""Read-only adapters from existing Creative Workflow payloads."""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from copy import deepcopy
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from libtv_agent.creative.state import (
    ActionCapabilityState,
    CameraFraming,
    CameraLens,
    CameraMovement,
    CameraState,
    CharacterContinuity,
    CharacterIdentity,
    CharacterState,
    DirectionCandidate,
    EvidenceRef,
    HumanQualityDecision,
    LicenseEvidence,
    ProductLocks,
    ProductSourceAsset,
    ProductState,
    ProductTruth,
    QualityEvidence,
    QualityState,
    SceneEnvironment,
    SceneLighting,
    SceneState,
    ShotExecutionRefs,
    ShotPromptRefs,
    ShotSourceBindings,
    ShotState,
    SpatialAnchor,
    SpatialRelationship,
    SpatialState,
    StoryboardCampaign,
    StoryboardState,
)


class StoryboardValidationIssue(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    severity: Literal["WARNING", "ERROR"]
    code: str = Field(min_length=1, max_length=120)
    message: str = Field(min_length=1, max_length=1000)
    shot_id: str | None = None


class StoryboardValidationResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    valid: bool
    executable: bool
    unresolved_references: tuple[str, ...] = ()
    issues: tuple[StoryboardValidationIssue, ...] = ()


class StoryboardSourceConflict(ValueError):
    def __init__(self, code: str, shot_id: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.shot_id = shot_id


def _mapping(value: Any) -> Mapping[str, Any]:
    if hasattr(value, "model_dump"):
        value = value.model_dump(mode="json")
    if isinstance(value, Mapping):
        return value
    raise TypeError("expected a mapping or Pydantic model")


def _text(value: Any, default: str = "") -> str:
    return value.strip() if isinstance(value, str) and value.strip() else default


def _tuple_text(value: Any) -> tuple[str, ...]:
    if not isinstance(value, (list, tuple, set)):
        return ()
    return tuple(item.strip() for item in value if isinstance(item, str) and item.strip())


def _number(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)) and value > 0:
        return float(value)
    if isinstance(value, str):
        try:
            parsed = float(value.strip())
        except ValueError:
            return None
        return parsed if parsed > 0 else None
    return None


def _first_value(mapping: Mapping[str, Any], *keys: str) -> Any:
    for key in keys:
        value = mapping.get(key)
        if value is not None:
            return value
    return None


def adapt_product_state(
    product_version: Mapping[str, Any],
    *,
    owner_id: str,
    source_assets: Sequence[Mapping[str, Any]] = (),
) -> ProductState:
    product = _mapping(product_version)
    truth_fields = product.get("truth_fields") or product.get("truthFields") or {}
    immutable_fields = product.get("immutable_fields") or product.get("immutableFields") or {}
    asset_models = []
    for index, raw_asset in enumerate(source_assets, start=1):
        asset = _mapping(raw_asset)
        asset_models.append(
            ProductSourceAsset(
                asset_id=_text(asset.get("asset_id") or asset.get("id"), f"product-asset-{index}"),
                object_key=_text(asset.get("object_key") or asset.get("objectKey")),
                sha256=_text(asset.get("sha256")),
                view=asset.get("view", "unknown"),
                mime_type=asset.get("mime_type") or asset.get("mimeType"),
                width=asset.get("width"),
                height=asset.get("height"),
                evidence_status=asset.get("evidence_status")
                or asset.get("evidenceStatus")
                or "UNVERIFIED",
                materialized=bool(asset.get("materialized", False)),
                revoked=bool(asset.get("revoked", False)),
            )
        )
    source_refs = (
        product.get("source_asset_references")
        or product.get("sourceAssetReferences")
        or []
    )
    source_fact_keys = (
        product.get("source_fact_keys")
        or product.get("sourceFactKeys")
        or []
    )
    unknown = product.get("unknown_attributes") or product.get("unknownAttributes") or []
    assumptions = product.get("user_assumptions") or product.get("userAssumptions") or []
    return ProductState(
        product_id=_text(product.get("product_id") or product.get("productId")),
        product_version_id=_text(
            product.get("product_version_id")
            or product.get("productVersionId")
            or product.get("id")
        ),
        owner_id=owner_id,
        sku=product.get("sku") or product.get("internal_sku_id") or product.get("internalSkuId"),
        source_assets=tuple(asset_models),
        identity={
            key: value
            for key, value in {
                "product_name": product.get("product_name") or product.get("page_title"),
                "brand_name": product.get("brand_name") or product.get("brandName"),
                "brand_mode": product.get("brand_mode") or product.get("brandMode"),
            }.items()
            if isinstance(value, str) and value.strip()
        },
        truth=ProductTruth(
            known_attributes=truth_fields if isinstance(truth_fields, dict) else {},
            unknown_attributes=_tuple_text(unknown),
            user_assumptions=_tuple_text(assumptions),
            source_fact_keys=_tuple_text(source_fact_keys) or _tuple_text(source_refs),
            facts_revision=int(product.get("facts_revision") or product.get("factsRevision") or 1),
        ),
        locks=ProductLocks(
            immutable_attributes=immutable_fields if isinstance(immutable_fields, dict) else {},
            print_logo_text_constraints=_tuple_text(
                product.get("print_logo_text_constraints")
                or product.get("printLogoTextConstraints")
            ),
            color_constraints=_tuple_text(
                product.get("color_constraints") or product.get("colorConstraints")
            ),
            garment_shape_constraints=_tuple_text(
                product.get("garment_shape_constraints")
                or product.get("garmentShapeConstraints")
            ),
            forbidden_changes=_tuple_text(
                product.get("forbidden_changes") or product.get("forbiddenChanges")
            ),
        ),
        license=LicenseEvidence(
            status=product.get("license_status") or product.get("licenseStatus") or "UNKNOWN",
            references=_tuple_text(
                product.get("license_references")
                or product.get("licenseReferences")
            ),
        ),
    )


def adapt_character_state(value: Mapping[str, Any] | None) -> CharacterState | None:
    if value is None:
        return None
    raw = _mapping(value)
    identity = _mapping(raw.get("identity") or {})
    continuity = _mapping(raw.get("continuity") or {})
    return CharacterState(
        character_id=_text(raw.get("id") or raw.get("character_id") or raw.get("characterId")),
        revision=int(raw.get("revision") or 1),
        origin=raw.get("origin") or "UNRESOLVED",
        identity=CharacterIdentity(
            face_structure=_tuple_text(
                identity.get("face_structure") or identity.get("faceStructure")
            ),
            hairstyle=_tuple_text(identity.get("hairstyle")),
            age_appearance=identity.get("age_appearance") or identity.get("ageRange"),
            body_proportions=_tuple_text(
                identity.get("body_proportions") or identity.get("bodyProportions")
            ),
            skin_characteristics=_tuple_text(
                identity.get("skin_characteristics") or identity.get("skinCharacteristics")
            ),
        ),
        continuity=CharacterContinuity(
            wardrobe=_tuple_text(continuity.get("wardrobe")),
            behavior=_tuple_text(continuity.get("behavior")),
            recurring_traits=_tuple_text(
                continuity.get("recurring_traits") or continuity.get("recurringTraits")
            ),
        ),
        evidence_refs=_tuple_text(raw.get("evidence_refs") or raw.get("evidenceRefs")),
        constraints=_tuple_text(raw.get("constraints")),
    )


def adapt_scene_state(value: Mapping[str, Any] | None) -> SceneState | None:
    if value is None:
        return None
    raw = _mapping(value)
    environment = _mapping(raw.get("environment") or {})
    lighting = _mapping(raw.get("lighting") or {})
    return SceneState(
        scene_id=_text(raw.get("id") or raw.get("scene_id") or raw.get("sceneId")),
        revision=int(raw.get("revision") or 1),
        origin=raw.get("origin") or "UNRESOLVED",
        environment=SceneEnvironment(
            location=environment.get("location"),
            description=_text(environment.get("description")),
            important_objects=_tuple_text(
                environment.get("important_objects") or environment.get("importantObjects")
            ),
            atmosphere=environment.get("atmosphere"),
            time_of_day=environment.get("time_of_day") or environment.get("timeOfDay"),
            weather=environment.get("weather"),
            season=environment.get("season"),
        ),
        lighting=SceneLighting(
            source=lighting.get("source"),
            direction=lighting.get("direction"),
            quality=lighting.get("quality"),
            contrast=lighting.get("contrast"),
            color_temperature=lighting.get("color_temperature")
            or lighting.get("colorTemperature"),
        ),
        continuity=_tuple_text(raw.get("continuity")),
        evidence_refs=_tuple_text(raw.get("evidence_refs") or raw.get("evidenceRefs")),
        constraints=_tuple_text(raw.get("constraints")),
    )


def adapt_camera_state(value: Mapping[str, Any] | None) -> CameraState | None:
    if value is None:
        return None
    raw = _mapping(value)
    framing = _mapping(raw.get("framing") or {})
    lens = _mapping(raw.get("lens") or {})
    movement = _mapping(raw.get("motion") or raw.get("movement") or {})
    return CameraState(
        camera_id=_text(raw.get("id") or raw.get("camera_id") or raw.get("cameraId")),
        revision=int(raw.get("revision") or 1),
        position=raw.get("position"),
        distance=raw.get("distance"),
        height=raw.get("height"),
        orientation=raw.get("orientation"),
        framing=CameraFraming(
            shot_size=framing.get("shot") or framing.get("shot_size") or framing.get("shotSize"),
            aspect_ratio=framing.get("aspect_ratio") or framing.get("aspectRatio"),
            subject_placement=framing.get("subject_placement")
            or framing.get("subjectPlacement"),
            headroom=framing.get("headroom"),
        ),
        lens=CameraLens(
            focal_length=lens.get("focal_length") or lens.get("focalLength"),
            depth_of_field=lens.get("depth_of_field") or lens.get("depthOfField"),
            distortion=lens.get("distortion"),
        ),
        movement=CameraMovement(
            allowed=_tuple_text(movement.get("allowed") or movement.get("movement")),
            forbidden=_tuple_text(movement.get("forbidden")),
            stabilization=movement.get("stabilization"),
            speed=movement.get("speed"),
        ),
        scene_geometry_refs=_tuple_text(
            raw.get("scene_geometry_refs") or raw.get("sceneGeometryRefs")
        ),
        evidence_refs=_tuple_text(raw.get("evidence_refs") or raw.get("evidenceRefs")),
    )


def adapt_spatial_state(value: Mapping[str, Any] | None) -> SpatialState | None:
    if value is None:
        return None
    raw = _mapping(value)
    anchors = []
    for item in raw.get("anchors", []):
        anchor = _mapping(item)
        position = _mapping(anchor.get("position") or {})
        anchors.append(
            SpatialAnchor(
                anchor_id=_text(anchor.get("anchor_id") or anchor.get("anchorId")),
                entity_id=_text(anchor.get("entity_id") or anchor.get("entityId")),
                kind=anchor.get("kind", "OBJECT"),
                x=position.get("x"),
                y=position.get("y"),
                depth_band=position.get("zBand") or position.get("depth_band") or "UNKNOWN",
                orientation=anchor.get("orientation"),
                dimensions=anchor.get("dimensions"),
            )
        )
    relationships = []
    for item in raw.get("relationships", []):
        relation = _mapping(item)
        relationships.append(
            SpatialRelationship(
                subject_id=_text(relation.get("subject_id") or relation.get("subjectId")),
                reference_id=_text(relation.get("reference_id") or relation.get("referenceId")),
                relation=relation.get("relation", "FACING"),
                details=relation.get("details"),
            )
        )
    return SpatialState(
        spatial_id=_text(raw.get("reference_id") or raw.get("referenceId") or raw.get("id")),
        revision=int(raw.get("revision") or 1),
        coordinate_system=raw.get("coordinate_system")
        or raw.get("coordinateSystem")
        or "IMAGE_NORMALIZED_2D",
        anchors=tuple(anchors),
        relationships=tuple(relationships),
        subject_depth=raw.get("subject_depth") or raw.get("subjectDepth"),
        physical_contact=_tuple_text(raw.get("physical_contact") or raw.get("physicalContact")),
        occlusion_rules=_tuple_text(raw.get("occlusion_rules") or raw.get("occlusionRules")),
        camera_relationship=_tuple_text(
            raw.get("camera_relationship") or raw.get("cameraRelationship")
        ),
        lighting_direction=raw.get("lighting_direction") or raw.get("lightingDirection"),
        evidence_refs=_tuple_text(raw.get("evidence_refs") or raw.get("evidenceRefs")),
        provider_submission_allowed=bool(raw.get("provider_submission_allowed", False)),
    )


def _direction_candidates(plan: Mapping[str, Any]) -> tuple[DirectionCandidate, ...]:
    selected = plan.get("selected_direction") or plan.get("selectedDirection")
    result = []
    for raw in plan.get("directions", []):
        direction = _mapping(raw)
        direction_id = _text(direction.get("id") or direction.get("direction_id"))
        result.append(
            DirectionCandidate(
                direction_id=direction_id,
                title=_text(direction.get("title")),
                summary=_text(direction.get("summary")),
                human=_text(direction.get("human")),
                scene=_text(direction.get("scene")),
                behavior=_text(direction.get("behavior")),
                camera=_text(direction.get("camera")),
                emotion=_text(direction.get("emotion")),
                status="SELECTED" if direction_id == selected else "PROPOSED",
            )
        )
    return tuple(result)


def _package_for_shot(snapshot: Mapping[str, Any], shot_id: str) -> Mapping[str, Any] | None:
    root = snapshot.get("package")
    if shot_id == "FIRST_FRAME" and isinstance(root, Mapping):
        root_shot = _first_value(root, "shot_id", "shotId")
        if root_shot != shot_id:
            raise StoryboardSourceConflict(
                "PACKAGE_SHOT_CONFLICT",
                shot_id,
                "root package requires explicit FIRST_FRAME shot_id",
            )
        nested = (snapshot.get("storyboard") or {}).get("packages") or {}
        if isinstance(nested, Mapping) and shot_id in nested and nested[shot_id] != root:
            raise StoryboardSourceConflict(
                "PACKAGE_SOURCE_CONFLICT",
                shot_id,
                "root and storyboard FIRST_FRAME packages differ",
            )
        return root
    storyboard = snapshot.get("storyboard") or {}
    packages = storyboard.get("packages") or {}
    if isinstance(packages, Mapping):
        package = packages.get(shot_id)
        if isinstance(package, Mapping):
            return package
    elif isinstance(packages, Sequence) and not isinstance(packages, (str, bytes)):
        for package in packages:
            if isinstance(package, Mapping) and str(
                _first_value(package, "shot_id", "shotId", "id")
            ) == shot_id:
                return package
    shot_specs = storyboard.get("shots") or ()
    if isinstance(shot_specs, Sequence) and not isinstance(shot_specs, (str, bytes)):
        for package in shot_specs:
            if isinstance(package, Mapping) and str(
                _first_value(package, "shot_id", "shotId", "id")
            ) == shot_id:
                return package
    return None


def _validate_shot_source(
    source: Mapping[str, Any],
    *,
    shot_id: str,
    package: Mapping[str, Any],
    kind: str,
) -> None:
    expected_scope = "FIRST_FRAME" if shot_id == "FIRST_FRAME" else "VIDEO_STORYBOARD"
    for keys, expected in (
        (("shot_id", "shotId"), shot_id),
        (("purpose", "scope"), expected_scope),
        (("package_id", "packageId"), _first_value(package, "package_id", "packageId")),
        (("package_revision", "packageRevision"), package.get("revision")),
    ):
        actual = _first_value(source, *keys)
        if actual is not None and expected is not None and actual != expected:
            raise StoryboardSourceConflict(
                "SHOT_SOURCE_CONFLICT",
                shot_id,
                f"{kind} {keys[0]} conflicts with its explicit shot/package",
            )


def _shot_source_binding(
    *,
    shot_id: str,
    package: Mapping[str, Any],
    selection: Mapping[str, Any],
    mapping: Mapping[str, Any],
    candidates: Sequence[Mapping[str, Any]],
) -> tuple[ShotSourceBindings | None, bool]:
    for kind, source in (("selection", selection), ("mapping", mapping)):
        _validate_shot_source(source, shot_id=shot_id, package=package, kind=kind)
    candidate_id = _first_value(selection, "candidate_id", "candidateId")
    mapped_candidate = _first_value(mapping, "candidate_id", "candidateId")
    if candidate_id and mapped_candidate and candidate_id != mapped_candidate:
        raise StoryboardSourceConflict(
            "CANDIDATE_SOURCE_CONFLICT",
            shot_id,
            "selection and mapping identify different candidates",
        )
    matches = [
        item for item in candidates
        if _first_value(item, "candidate_id", "candidateId") == candidate_id
        and candidate_id is not None
        and _first_value(item, "shot_id", "shotId") == shot_id
        and _first_value(item, "package_id", "packageId") is not None
        and _first_value(item, "package_id", "packageId")
        == _first_value(package, "package_id", "packageId")
    ]
    if len(matches) > 1 and any(item != matches[0] for item in matches[1:]):
        raise StoryboardSourceConflict(
            "CANDIDATE_SOURCE_CONFLICT",
            shot_id,
            "selected candidate has conflicting source records",
        )
    candidate = matches[0] if matches else {}
    _validate_shot_source(candidate, shot_id=shot_id, package=package, kind="candidate")
    for key in ("batch_id", "item_id", "output_id"):
        values = {item[key] for item in (selection, mapping, candidate) if item.get(key)}
        if len(values) > 1:
            raise StoryboardSourceConflict(
                "OUTPUT_SOURCE_CONFLICT", shot_id, f"selected source has conflicting {key} values"
            )
    mapped_sha = mapping.get("output_image_hash") or mapping.get("source_image_hash")
    candidate_sha = candidate.get("sha256")
    if candidate_sha and mapped_sha and candidate_sha != mapped_sha:
        raise StoryboardSourceConflict(
            "SOURCE_HASH_CONFLICT", shot_id, "selected candidate and mapping hashes differ"
        )
    unresolved = bool(candidate_id and not candidate)
    if not selection and not mapping:
        return None, unresolved
    return ShotSourceBindings(
        selected_candidate_id=candidate_id,
        batch_id=selection.get("batch_id") or mapping.get("batch_id") or candidate.get("batch_id"),
        item_id=selection.get("item_id") or mapping.get("item_id") or candidate.get("item_id"),
        output_id=(
            selection.get("output_id")
            or mapping.get("output_id")
            or candidate.get("output_id")
        ),
        source_sha256=candidate_sha or mapped_sha,
    ), unresolved


def _ordered_shot_ids(
    snapshot: Mapping[str, Any],
    storyboard: Mapping[str, Any],
) -> list[str]:
    packages = storyboard.get("packages") or {}
    package_items: list[tuple[str, Mapping[str, Any]]] = []
    if isinstance(packages, Mapping):
        package_items = [
            (str(shot_id), package)
            for shot_id, package in packages.items()
            if isinstance(package, Mapping)
        ]
    elif isinstance(packages, Sequence) and not isinstance(packages, (str, bytes)):
        package_items = [
            (
                str(_first_value(package, "shot_id", "shotId", "id")),
                package,
            )
            for package in packages
            if isinstance(package, Mapping)
            and _first_value(package, "shot_id", "shotId", "id")
        ]

    explicit_order = _first_value(storyboard, "shot_order", "shotOrder", "order")
    if isinstance(explicit_order, Sequence) and not isinstance(
        explicit_order, (str, bytes)
    ):
        ordered = [str(item) for item in explicit_order if str(item).strip()]
        ordered.extend(shot_id for shot_id, _ in package_items if shot_id not in ordered)
        return ordered

    def package_order(item: tuple[str, Mapping[str, Any]]) -> tuple[int, int]:
        index = _first_value(
            item[1],
            "order",
            "shot_order",
            "shotOrder",
            "sequence",
            "index",
        )
        numeric = _number(index)
        return (int(numeric) if numeric is not None else 10**9, package_items.index(item))

    if package_items:
        return [shot_id for shot_id, _ in sorted(package_items, key=package_order)]

    shot_specs = storyboard.get("shots") or ()
    if isinstance(shot_specs, Sequence) and not isinstance(shot_specs, (str, bytes)):
        return [
            str(_first_value(item, "shot_id", "shotId", "id"))
            for item in shot_specs
            if isinstance(item, Mapping)
            and _first_value(item, "shot_id", "shotId", "id")
        ]
    if isinstance(snapshot.get("package"), Mapping):
        return ["FIRST_FRAME"]
    return []


def _action_capability_state(package: Mapping[str, Any]) -> ActionCapabilityState:
    nested = _first_value(
        package,
        "action_capabilities",
        "actionCapabilities",
        "capability_check",
        "capabilityCheck",
    )
    capabilities = nested if isinstance(nested, Mapping) else {}
    required = _tuple_text(
        _first_value(
            capabilities,
            "required",
            "required_capabilities",
            "requiredCapabilities",
        )
        or _first_value(package, "required_capabilities", "requiredCapabilities")
    )
    confirmed = _tuple_text(
        _first_value(capabilities, "confirmed", "supported", "confirmed_capabilities")
    )
    denied = _tuple_text(_first_value(capabilities, "denied", "denied_capabilities"))
    raw_status = _text(
        _first_value(capabilities, "status", "result")
        or _first_value(package, "action_capability_status", "actionCapabilityStatus")
    ).upper()
    if not required:
        status = "NOT_REQUIRED"
    elif raw_status in {"BLOCKED", "DENIED", "UNSUPPORTED"} or denied:
        status = "BLOCKED"
    elif raw_status in {"VALIDATED", "SUPPORTED", "ALLOWED"}:
        status = "VALIDATED"
    elif confirmed and set(required) <= set(confirmed):
        status = "VALIDATED"
    else:
        status = "UNRESOLVED"
    return ActionCapabilityState(
        required=required,
        confirmed=confirmed,
        denied=denied,
        status=status,
    )


def adapt_storyboard_state(
    snapshot: Mapping[str, Any],
    *,
    product_version_id: str,
    character_revision: str | None = None,
    scene_revision: str | None = None,
    spatial_revision: str | None = None,
    camera_revision: str | None = None,
) -> tuple[StoryboardState, tuple[ShotState, ...]]:
    plan = _mapping(snapshot.get("plan") or {})
    storyboard = _mapping(snapshot.get("storyboard") or {})
    shot_ids = _ordered_shot_ids(snapshot, storyboard)
    if isinstance(snapshot.get("package"), Mapping) and "FIRST_FRAME" not in shot_ids:
        shot_ids.insert(0, "FIRST_FRAME")
    selected_direction = plan.get("selected_direction") or plan.get("selectedDirection")
    candidates = _direction_candidates(plan)
    selected_package = _package_for_shot(snapshot, "FIRST_FRAME")
    campaign_direction = next(
        (item for item in candidates if item.direction_id == selected_direction),
        None,
    )
    campaign = StoryboardCampaign(
        intent=_text(plan.get("intent") or plan.get("objective")),
        hook=_text(plan.get("hook")),
        emotional_progression=_tuple_text(plan.get("emotional_progression")),
        product_evidence=_tuple_text(plan.get("product_evidence")),
        cta_purpose=plan.get("cta_purpose"),
    )
    if campaign_direction and not campaign.intent:
        campaign = campaign.model_copy(update={"intent": campaign_direction.summary})

    selections = storyboard.get("selections") or {}
    mappings = storyboard.get("shot_mappings") or storyboard.get("shotMappings") or {}
    latest_reviews = storyboard.get("latest_reviews") or storyboard.get("latestReviews") or {}
    root_selection = snapshot.get("selection")
    root_review = snapshot.get("latest_review")
    shots = []
    for order, shot_id in enumerate(shot_ids, start=1):
        package = _package_for_shot(snapshot, shot_id) or {}
        _validate_shot_source(package, shot_id=shot_id, package=package, kind="package")
        if shot_id == "FIRST_FRAME":
            for kind, root, nested in (
                ("selection", root_selection, selections.get(shot_id)),
                ("review", root_review, latest_reviews.get(shot_id)),
            ):
                if root and nested and root != nested:
                    raise StoryboardSourceConflict(
                        "FIRST_FRAME_SOURCE_CONFLICT",
                        shot_id,
                        f"root and storyboard FIRST_FRAME {kind} records differ",
                    )
        selection = selections.get(shot_id) or (
            root_selection if shot_id == "FIRST_FRAME" else None
        )
        review = latest_reviews.get(shot_id) or (
            root_review if shot_id == "FIRST_FRAME" else None
        )
        candidate_pool = snapshot if shot_id == "FIRST_FRAME" else storyboard
        source_binding, source_unresolved = _shot_source_binding(
            shot_id=shot_id,
            package=package,
            selection=_mapping(selection or {}),
            mapping=_mapping(mappings.get(shot_id) or {}),
            candidates=[
                item for item in candidate_pool.get("candidates", [])
                if isinstance(item, Mapping)
            ],
        )
        if review:
            _validate_shot_source(
                _mapping(review), shot_id=shot_id, package=package, kind="review"
            )
        prompt_refs = ShotPromptRefs(
            image_prompt_revision=package.get("package_id"),
            video_prompt_revision=package.get("package_id")
            if package.get("purpose") == "VIDEO_STORYBOARD"
            else None,
            package_revision=package.get("revision"),
            preservation_hash=package.get("preservation_hash"),
        )
        action_capabilities = _action_capability_state(package)
        duration = _first_value(
            package,
            "duration_seconds",
            "durationSeconds",
            "duration",
        )
        timing = package.get("timing")
        if isinstance(timing, Mapping):
            duration = duration or _first_value(
                timing,
                "duration_seconds",
                "durationSeconds",
                "duration",
            )
        camera_language = _text(
            _first_value(
                package,
                "camera_language",
                "cameraLanguage",
                "camera",
            )
            or (campaign_direction.camera if campaign_direction else "")
        ) or None
        unresolved = []
        if source_unresolved:
            unresolved.append("selected_source_candidate")
        if character_revision is None:
            unresolved.append("character")
        if scene_revision is None:
            unresolved.append("scene")
        if spatial_revision is None:
            unresolved.append("spatial")
        if camera_revision is None:
            unresolved.append("camera")
        if action_capabilities.status == "UNRESOLVED":
            unresolved.append("action_capabilities")
        shot_purpose = _text(
            _first_value(
                package,
                "shot_purpose",
                "shotPurpose",
                "shot_function",
                "shotFunction",
                "intent",
            )
        )
        shot_action = _text(
            _first_value(package, "action", "instruction")
            or (campaign_direction.behavior if campaign_direction else "")
        )
        if not shot_purpose:
            unresolved.append("shot_purpose")
        if not shot_action:
            unresolved.append("action")
        shots.append(
            ShotState(
                shot_id=shot_id,
                order=order,
                purpose=shot_purpose,
                duration_seconds=_number(duration),
                entry_state=_text(
                    _first_value(package, "entry_state", "entryState")
                )
                or None,
                action=shot_action,
                exit_state=_text(
                    _first_value(package, "exit_state", "exitState")
                )
                or None,
                camera_language=camera_language,
                product_evidence=_tuple_text(package.get("product_evidence")),
                inherited_product_revision=product_version_id,
                inherited_character_revision=character_revision,
                inherited_scene_revision=scene_revision,
                inherited_spatial_revision=spatial_revision,
                inherited_camera_revision=camera_revision,
                action_capabilities=action_capabilities,
                unresolved_references=tuple(unresolved),
                prompt_refs=prompt_refs,
                source_bindings=source_binding,
                review=deepcopy(dict(review)) if review else None,
                execution_refs=ShotExecutionRefs(
                    parent_task_id=_text(
                        snapshot.get("creative_task_id") or snapshot.get("task_id")
                    )
                    or None
                ),
            )
        )
        if review and review.get("decision") == "REJECTED":
            shots[-1] = shots[-1].model_copy(
                update={
                    "product_evidence": (
                        *shots[-1].product_evidence,
                        f"review:{review.get('reason') or 'rejected'}",
                    )
                }
            )
    storyboard_id = _text(
        snapshot.get("storyboard_id")
        or storyboard.get("storyboard_id")
        or storyboard.get("storyboardId")
        or f"creative-storyboard:{snapshot.get('creative_task_id') or 'legacy'}"
    )
    state = StoryboardState(
        storyboard_id=storyboard_id,
        revision=int(snapshot.get("storyboard_revision") or 1),
        campaign=campaign,
        selected_direction_id=selected_direction,
        direction_candidates=candidates,
        continuity_rules=_tuple_text(storyboard.get("continuity_rules")),
        shot_order=tuple(shot_ids),
        package_revision_id=selected_package.get("package_id") if selected_package else None,
        source_refs=("director.snapshot",),
        unresolved_references=tuple(
            reference
            for reference, revision in (
                ("character", character_revision),
                ("scene", scene_revision),
                ("spatial", spatial_revision),
            )
            if revision is None
        ),
    )
    return state, tuple(shots)


def compile_storyboard_state(
    snapshot: Mapping[str, Any],
    *,
    product_version_id: str,
    character_revision: str | None = None,
    scene_revision: str | None = None,
    spatial_revision: str | None = None,
    camera_revision: str | None = None,
) -> tuple[StoryboardState, tuple[ShotState, ...]]:
    """Compile the legacy Director snapshot into canonical storyboard objects."""
    return adapt_storyboard_state(
        snapshot,
        product_version_id=product_version_id,
        character_revision=character_revision,
        scene_revision=scene_revision,
        spatial_revision=spatial_revision,
        camera_revision=camera_revision,
    )


def validate_storyboard_state(
    storyboard: StoryboardState,
    shots: Sequence[ShotState],
    *,
    product_revision: str,
    character_revision: str | None = None,
    scene_revision: str | None = None,
    spatial: SpatialState | None = None,
    camera_revision: str | None = None,
) -> StoryboardValidationResult:
    """Validate canonical storyboard readiness without changing provider behavior."""
    issues: list[StoryboardValidationIssue] = []
    unresolved: list[str] = list(storyboard.unresolved_references)

    for name, revision, code in (
        ("character", character_revision, "CHARACTER_UNRESOLVED"),
        ("scene", scene_revision, "SCENE_UNRESOLVED"),
        ("camera", camera_revision, "CAMERA_UNRESOLVED"),
    ):
        if revision is None:
            unresolved.append(name)
            issues.append(
                StoryboardValidationIssue(
                    severity="WARNING",
                    code=code,
                    message=f"{name} reference is unresolved; no creative fact was invented",
                )
            )

    spatial_ready = spatial is not None and spatial.provider_submission_allowed
    if not spatial_ready:
        unresolved.append("spatial")
        issues.append(
            StoryboardValidationIssue(
                severity="WARNING",
                code="SPATIAL_SUBMISSION_BLOCKED",
                message=(
                    "spatial reference is unresolved or not validated; provider "
                    "submission remains blocked"
                ),
            )
        )

    for shot in shots:
        expected = {
            "product": product_revision,
            "character": character_revision,
            "scene": scene_revision,
            "spatial": (
                f"{spatial.spatial_id}:r{spatial.revision}" if spatial else None
            ),
            "camera": camera_revision,
        }
        actual = {
            "product": shot.inherited_product_revision,
            "character": shot.inherited_character_revision,
            "scene": shot.inherited_scene_revision,
            "spatial": shot.inherited_spatial_revision,
            "camera": shot.inherited_camera_revision,
        }
        for name, expected_revision in expected.items():
            if expected_revision is not None and actual[name] != expected_revision:
                issues.append(
                    StoryboardValidationIssue(
                        severity="ERROR",
                        code="SHOT_INHERITANCE_MISMATCH",
                        message=f"shot does not inherit the current {name} revision",
                        shot_id=shot.shot_id,
                    )
                )
        for reference in shot.unresolved_references:
            unresolved.append(f"{shot.shot_id}:{reference}")
        if shot.action_capabilities.status in {"UNRESOLVED", "BLOCKED"}:
            issues.append(
                StoryboardValidationIssue(
                    severity="ERROR",
                    code="ACTION_CAPABILITIES_UNRESOLVED",
                    message="shot action capability checks are not validated",
                    shot_id=shot.shot_id,
                )
            )

    deduped_unresolved = tuple(dict.fromkeys(unresolved))
    return StoryboardValidationResult(
        valid=not any(issue.severity == "ERROR" for issue in issues),
        executable=(
            not deduped_unresolved
            and not any(issue.severity == "ERROR" for issue in issues)
        ),
        unresolved_references=deduped_unresolved,
        issues=tuple(issues),
    )


def adapt_evidence_records(records: Sequence[Mapping[str, Any]]) -> tuple[EvidenceRef, ...]:
    evidence = []
    for raw in records:
        record = _mapping(raw)
        payload = record.get("payload_json") or record.get("payload") or {}
        evidence.append(
            EvidenceRef(
                evidence_id=_text(record.get("id") or record.get("record_key")),
                source_kind=(
                    "QUALITY_REVIEW"
                    if record.get("kind") == "review"
                    else "CREATIVE_RECORD"
                ),
                source_id=_text(record.get("record_key") or record.get("id")),
                statement=_text(
                    record.get("statement")
                    or payload.get("reason")
                    or record.get("kind")
                    or "creative record"
                ),
                status=(
                    "REVOKED"
                    if record.get("kind") == "asset_revocation"
                    else "UNVERIFIED"
                ),
            )
        )
    return tuple(evidence)


def adapt_quality_state(
    records: Sequence[Mapping[str, Any]],
    *,
    output_records: Sequence[Mapping[str, Any]] = (),
) -> QualityState:
    quality_evidence = []
    human_decisions = []
    for raw in [*records, *output_records]:
        record = _mapping(raw)
        kind = record.get("kind")
        payload = _mapping(record.get("payload_json") or record.get("payload") or {})
        if kind not in {"review", "validation", "quality", "output"}:
            continue
        scope = (
            payload.get("qualification_scope")
            or payload.get("qualificationScope")
            or "OFFLINE_SYNTHETIC_ONLY"
        )
        decision = payload.get("decision") or payload.get("status") or "UNVERIFIED"
        normalized = {
            "PASS": "PASS",
            "FAILED": "FAIL",
            "FAIL": "FAIL",
            "WARNING": "WARNING",
            "UNVERIFIED": "UNVERIFIED",
            "QUALIFIED": "PASS",
            "REJECTED": "FAIL",
        }.get(str(decision).upper(), "QUALITY_REVIEW")
        quality_evidence.append(
            QualityEvidence(
                evidence_id=_text(record.get("record_key") or record.get("id")),
                source_id=_text(record.get("record_key") or record.get("id")),
                scope=scope,
                decision=normalized,
                failure_codes=_tuple_text(
                    payload.get("failure_codes") or payload.get("issue_codes")
                ),
                evidence_refs=_tuple_text(
                    payload.get("evidence_refs") or payload.get("evidence_object_keys")
                ),
                reviewer_kind="HUMAN" if payload.get("reviewer_kind") == "HUMAN" else (
                    "MODEL" if payload.get("reviewer_kind") else "RULE"
                ),
            )
        )
        if payload.get("reviewer_kind") == "HUMAN" and payload.get("decision") in {
            "QUALIFIED",
            "REJECTED",
        }:
            human_decisions.append(
                HumanQualityDecision(
                    decision_id=_text(record.get("record_key") or record.get("id")),
                    source_id=_text(record.get("record_key") or record.get("id")),
                    decision=payload["decision"],
                    reviewer_id=_text(payload.get("reviewer_id") or payload.get("reviewerId")),
                    reason=payload.get("reason"),
                    scope=scope,
                )
            )
    current = "PENDING"
    if human_decisions:
        current = human_decisions[-1].decision
    elif quality_evidence:
        current = "UNVERIFIED"
    scope = (
        "PRODUCTION"
        if any(item.scope == "PRODUCTION" for item in quality_evidence)
        else "OFFLINE_SYNTHETIC_ONLY"
    )
    return QualityState(
        qualification_scope=scope,
        evidence=tuple(quality_evidence),
        human_decisions=tuple(human_decisions),
        current_decision=current,
        delivery_eligibility="NOT_ELIGIBLE",
    )
