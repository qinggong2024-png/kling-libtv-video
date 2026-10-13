"""Canonical creative state value objects.

These models describe creative truth and its evidence. They deliberately do
not contain provider lifecycle, billing, quota, download, or delivery state.
"""
from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

CANONICAL_CREATIVE_STATE_SCHEMA = "creative-state.v1"
SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")

CreativeOrigin = Literal[
    "OBSERVED_REFERENCE",
    "USER_CONFIRMED",
    "LIBRARY_SNAPSHOT",
    "PROPOSED",
    "UNRESOLVED",
]


class StateModel(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        str_strip_whitespace=True,
    )


class EvidenceRef(StateModel):
    evidence_id: str = Field(min_length=1, max_length=160)
    source_kind: Literal[
        "PRODUCT_VERSION",
        "SOURCE_ASSET",
        "USER_CONFIRMATION",
        "LIBRARY_SNAPSHOT",
        "CREATIVE_RECORD",
        "TASK_OUTPUT",
        "QUALITY_REVIEW",
        "OFFLINE_SYNTHETIC",
    ]
    source_id: str = Field(min_length=1, max_length=240)
    statement: str = Field(min_length=1, max_length=1000)
    status: Literal["VERIFIED", "UNVERIFIED", "ASSUMED", "REVOKED"] = "UNVERIFIED"


class LicenseEvidence(StateModel):
    status: Literal["VERIFIED", "UNVERIFIED", "UNKNOWN", "REVOKED"] = "UNKNOWN"
    references: tuple[str, ...] = ()


class ProductSourceAsset(StateModel):
    asset_id: str = Field(min_length=1, max_length=160)
    object_key: str = Field(min_length=1, max_length=500)
    sha256: str = Field(pattern=SHA256_PATTERN.pattern)
    view: Literal["front", "back", "side", "detail", "unknown"] = "unknown"
    mime_type: str | None = Field(default=None, max_length=120)
    width: int | None = Field(default=None, gt=0)
    height: int | None = Field(default=None, gt=0)
    evidence_status: Literal[
        "OBSERVED_REFERENCE",
        "USER_CONFIRMED",
        "USER_ASSUMED",
        "UNVERIFIED",
        "REVOKED",
    ] = "UNVERIFIED"
    materialized: bool = False
    revoked: bool = False


class ProductLocks(StateModel):
    immutable_attributes: dict[str, object] = Field(default_factory=dict)
    print_logo_text_constraints: tuple[str, ...] = ()
    color_constraints: tuple[str, ...] = ()
    garment_shape_constraints: tuple[str, ...] = ()
    forbidden_changes: tuple[str, ...] = ()


class ProductTruth(StateModel):
    known_attributes: dict[str, object] = Field(default_factory=dict)
    unknown_attributes: tuple[str, ...] = ()
    user_assumptions: tuple[str, ...] = ()
    source_fact_keys: tuple[str, ...] = ()
    facts_revision: int = Field(ge=1)


class ProductState(StateModel):
    product_id: str = Field(min_length=1, max_length=160)
    product_version_id: str = Field(min_length=1, max_length=160)
    owner_id: str = Field(min_length=1, max_length=160)
    sku: str | None = Field(default=None, max_length=160)
    source_assets: tuple[ProductSourceAsset, ...] = ()
    identity: dict[str, str] = Field(default_factory=dict)
    truth: ProductTruth
    locks: ProductLocks = ProductLocks()
    license: LicenseEvidence = LicenseEvidence()

    @model_validator(mode="after")
    def validate_source_assets(self) -> ProductState:
        asset_ids = [asset.asset_id for asset in self.source_assets]
        if len(asset_ids) != len(set(asset_ids)):
            raise ValueError("product source assets must have unique asset_id values")
        if any(asset.revoked for asset in self.source_assets):
            raise ValueError("revoked product source assets cannot be canonical inputs")
        return self


class CharacterIdentity(StateModel):
    face_structure: tuple[str, ...] = ()
    hairstyle: tuple[str, ...] = ()
    age_appearance: str | None = None
    body_proportions: tuple[str, ...] = ()
    skin_characteristics: tuple[str, ...] = ()


class CharacterContinuity(StateModel):
    wardrobe: tuple[str, ...] = ()
    behavior: tuple[str, ...] = ()
    recurring_traits: tuple[str, ...] = ()


class CharacterState(StateModel):
    character_id: str = Field(min_length=1, max_length=160)
    revision: int = Field(ge=1)
    origin: CreativeOrigin
    identity: CharacterIdentity
    continuity: CharacterContinuity = CharacterContinuity()
    allowed_changes: tuple[Literal["POSE", "EXPRESSION", "ACTION", "FRAMING"], ...] = (
        "POSE",
        "EXPRESSION",
        "ACTION",
        "FRAMING",
    )
    forbidden_changes: tuple[
        Literal[
            "FACE_REPLACEMENT",
            "BODY_CHANGE",
            "AGE_CHANGE",
            "WARDROBE_LOCK_BREAK",
        ],
        ...,
    ] = (
        "FACE_REPLACEMENT",
        "BODY_CHANGE",
        "AGE_CHANGE",
        "WARDROBE_LOCK_BREAK",
    )
    evidence_refs: tuple[str, ...] = ()
    constraints: tuple[str, ...] = ()


class SceneEnvironment(StateModel):
    location: str | None = None
    description: str = ""
    important_objects: tuple[str, ...] = ()
    atmosphere: str | None = None
    time_of_day: str | None = None
    weather: str | None = None
    season: str | None = None


class SceneLighting(StateModel):
    source: str | None = None
    direction: str | None = None
    quality: str | None = None
    contrast: str | None = None
    color_temperature: str | None = None


class SceneState(StateModel):
    scene_id: str = Field(min_length=1, max_length=160)
    revision: int = Field(ge=1)
    origin: CreativeOrigin
    environment: SceneEnvironment = SceneEnvironment()
    lighting: SceneLighting = SceneLighting()
    continuity: tuple[str, ...] = ()
    evidence_refs: tuple[str, ...] = ()
    constraints: tuple[str, ...] = ()


class SpatialAnchor(StateModel):
    anchor_id: str = Field(min_length=1, max_length=160)
    entity_id: str = Field(min_length=1, max_length=160)
    kind: Literal["FURNITURE", "OBJECT", "WINDOW", "DOOR", "SUBJECT", "CAMERA"]
    x: float | None = None
    y: float | None = None
    depth_band: Literal["FOREGROUND", "MIDGROUND", "BACKGROUND", "UNKNOWN"] = "UNKNOWN"
    orientation: str | None = None
    dimensions: str | None = None


class SpatialRelationship(StateModel):
    subject_id: str = Field(min_length=1, max_length=160)
    reference_id: str = Field(min_length=1, max_length=160)
    relation: Literal[
        "SITTING_ON",
        "STANDING_BY",
        "TOUCHING",
        "FACING",
        "LEFT_OF",
        "RIGHT_OF",
        "IN_FRONT_OF",
        "BEHIND",
        "OCCLUDES",
        "LIT_BY",
    ]
    details: str | None = None


class SpatialState(StateModel):
    spatial_id: str = Field(min_length=1, max_length=160)
    revision: int = Field(ge=1)
    coordinate_system: Literal[
        "IMAGE_NORMALIZED_2D",
        "SCREEN_SPACE_2D",
        "SCENE_RELATIVE_3D",
    ]
    anchors: tuple[SpatialAnchor, ...] = ()
    relationships: tuple[SpatialRelationship, ...] = ()
    subject_depth: str | None = None
    physical_contact: tuple[str, ...] = ()
    occlusion_rules: tuple[str, ...] = ()
    camera_relationship: tuple[str, ...] = ()
    lighting_direction: str | None = None
    evidence_refs: tuple[str, ...] = ()
    provider_submission_allowed: bool = False


class CameraLens(StateModel):
    focal_length: str | None = None
    depth_of_field: str | None = None
    distortion: str | None = None


class CameraFraming(StateModel):
    shot_size: str | None = None
    aspect_ratio: str | None = None
    subject_placement: str | None = None
    headroom: str | None = None


class CameraMovement(StateModel):
    allowed: tuple[str, ...] = ()
    forbidden: tuple[str, ...] = ()
    stabilization: str | None = None
    speed: str | None = None


class CameraState(StateModel):
    camera_id: str = Field(min_length=1, max_length=160)
    revision: int = Field(ge=1)
    position: str | None = None
    distance: str | None = None
    height: str | None = None
    orientation: str | None = None
    lens: CameraLens = CameraLens()
    framing: CameraFraming = CameraFraming()
    movement: CameraMovement = CameraMovement()
    scene_geometry_refs: tuple[str, ...] = ()
    evidence_refs: tuple[str, ...] = ()


class DirectionCandidate(StateModel):
    direction_id: str = Field(min_length=1, max_length=80)
    title: str = ""
    summary: str = ""
    human: str = ""
    scene: str = ""
    behavior: str = ""
    camera: str = ""
    emotion: str = ""
    status: Literal["PROPOSED", "SELECTED", "REJECTED"] = "PROPOSED"


class StoryboardCampaign(StateModel):
    intent: str = ""
    hook: str = ""
    emotional_progression: tuple[str, ...] = ()
    product_evidence: tuple[str, ...] = ()
    cta_purpose: str | None = None


class StoryboardState(StateModel):
    storyboard_id: str = Field(min_length=1, max_length=160)
    revision: int = Field(ge=1)
    campaign: StoryboardCampaign = StoryboardCampaign()
    selected_direction_id: str | None = None
    direction_candidates: tuple[DirectionCandidate, ...] = ()
    continuity_rules: tuple[str, ...] = ()
    shot_order: tuple[str, ...] = ()
    package_revision_id: str | None = None
    source_refs: tuple[str, ...] = ()
    unresolved_references: tuple[str, ...] = ()

    @model_validator(mode="after")
    def validate_selected_direction(self) -> StoryboardState:
        ids = {candidate.direction_id for candidate in self.direction_candidates}
        if self.selected_direction_id is not None and self.selected_direction_id not in ids:
            raise ValueError("selected direction must reference a direction candidate")
        if len(self.shot_order) != len(set(self.shot_order)):
            raise ValueError("storyboard shot_order must be unique")
        return self


class ShotPromptRefs(StateModel):
    image_prompt_revision: str | None = None
    video_prompt_revision: str | None = None
    package_revision: int | None = Field(default=None, ge=1)
    preservation_hash: str | None = Field(
        default=None,
        pattern=SHA256_PATTERN.pattern,
    )


class ActionCapabilityState(StateModel):
    required: tuple[str, ...] = ()
    confirmed: tuple[str, ...] = ()
    denied: tuple[str, ...] = ()
    status: Literal["NOT_REQUIRED", "VALIDATED", "UNRESOLVED", "BLOCKED"] = (
        "NOT_REQUIRED"
    )


class ShotSourceBindings(StateModel):
    selected_candidate_id: str | None = None
    batch_id: str | None = None
    item_id: str | None = None
    output_id: str | None = None
    source_sha256: str | None = Field(default=None, pattern=SHA256_PATTERN.pattern)


class ShotExecutionRefs(StateModel):
    parent_task_id: str | None = None
    variant_id: str | None = None
    attempt_id: str | None = None


class ShotState(StateModel):
    shot_id: str = Field(min_length=1, max_length=160)
    order: int = Field(ge=1)
    purpose: str = ""
    duration_seconds: float | None = Field(default=None, gt=0)
    entry_state: str | None = None
    action: str = ""
    exit_state: str | None = None
    camera_language: str | None = None
    product_evidence: tuple[str, ...] = ()
    inherited_product_revision: str = Field(min_length=1, max_length=160)
    inherited_character_revision: str | None = None
    inherited_scene_revision: str | None = None
    inherited_spatial_revision: str | None = None
    inherited_camera_revision: str | None = None
    action_capabilities: ActionCapabilityState = ActionCapabilityState()
    unresolved_references: tuple[str, ...] = ()
    allowed_changes: tuple[Literal["POSE", "EXPRESSION", "MOVEMENT", "FRAMING"], ...] = (
        "POSE",
        "EXPRESSION",
        "MOVEMENT",
        "FRAMING",
    )
    forbidden_changes: tuple[
        Literal[
            "IDENTITY_DRIFT",
            "ENVIRONMENT_REDESIGN",
            "PRODUCT_REDESIGN",
            "LOCK_BREAK",
        ],
        ...,
    ] = (
        "IDENTITY_DRIFT",
        "ENVIRONMENT_REDESIGN",
        "PRODUCT_REDESIGN",
        "LOCK_BREAK",
    )
    prompt_refs: ShotPromptRefs = ShotPromptRefs()
    source_bindings: ShotSourceBindings | None = None
    review: dict[str, object] | None = None
    execution_refs: ShotExecutionRefs | None = None


class QualityEvidence(StateModel):
    evidence_id: str = Field(min_length=1, max_length=160)
    source_id: str = Field(min_length=1, max_length=240)
    scope: Literal[
        "OFFLINE_SYNTHETIC_ONLY",
        "REAL_INPUT_UNVERIFIED",
        "PRODUCTION",
    ]
    decision: Literal["PASS", "WARNING", "FAIL", "UNVERIFIED", "QUALITY_REVIEW"]
    failure_codes: tuple[str, ...] = ()
    evidence_refs: tuple[str, ...] = ()
    reviewer_kind: Literal["RULE", "MODEL", "HUMAN"] = "RULE"


class HumanQualityDecision(StateModel):
    decision_id: str = Field(min_length=1, max_length=160)
    source_id: str = Field(min_length=1, max_length=240)
    decision: Literal["QUALIFIED", "REJECTED"]
    reviewer_id: str = Field(min_length=1, max_length=160)
    reason: str | None = None
    scope: Literal[
        "OFFLINE_SYNTHETIC_ONLY",
        "REAL_INPUT_UNVERIFIED",
        "PRODUCTION",
    ]


class QualityState(StateModel):
    qualification_scope: Literal[
        "OFFLINE_SYNTHETIC_ONLY",
        "REAL_INPUT_UNVERIFIED",
        "PRODUCTION",
    ] = "OFFLINE_SYNTHETIC_ONLY"
    evidence: tuple[QualityEvidence, ...] = ()
    human_decisions: tuple[HumanQualityDecision, ...] = ()
    current_decision: Literal["PENDING", "UNVERIFIED", "QUALIFIED", "REJECTED"] = "PENDING"
    qualification_scope_reason: str | None = None
    delivery_eligibility: Literal["NOT_ELIGIBLE", "ELIGIBLE"] = "NOT_ELIGIBLE"

    @model_validator(mode="after")
    def validate_delivery_boundary(self) -> QualityState:
        if (
            self.qualification_scope != "PRODUCTION"
            or self.current_decision != "QUALIFIED"
        ) and self.delivery_eligibility == "ELIGIBLE":
            raise ValueError("non-production or non-qualified state cannot be delivery eligible")
        return self


class Provenance(StateModel):
    source_systems: tuple[str, ...] = ()
    source_record_ids: tuple[str, ...] = ()
    legacy_snapshot: bool = True


class CreativeStateRevision(StateModel):
    schema_version: Literal[CANONICAL_CREATIVE_STATE_SCHEMA] = CANONICAL_CREATIVE_STATE_SCHEMA
    creative_state_id: str = Field(min_length=1, max_length=160)
    revision: int = Field(ge=1)
    parent_revision: int | None = Field(default=None, ge=1)
    state_version: int = Field(ge=0)
    facts_revision: int = Field(ge=1)
    content_hash: str = Field(pattern=SHA256_PATTERN.pattern)
    locks_hash: str = Field(pattern=SHA256_PATTERN.pattern)
    source_snapshot_hash: str = Field(pattern=SHA256_PATTERN.pattern)
    created_by: str = Field(min_length=1, max_length=160)
    created_at: str = Field(min_length=1, max_length=80)
    reason: str = Field(min_length=1, max_length=500)
    product: ProductState
    character: CharacterState | None = None
    scene: SceneState | None = None
    spatial: SpatialState | None = None
    camera: CameraState | None = None
    storyboard: StoryboardState
    shots: tuple[ShotState, ...] = ()
    quality: QualityState = QualityState()
    evidence: tuple[EvidenceRef, ...] = ()
    provenance: Provenance = Provenance()

    @model_validator(mode="after")
    def validate_revision_graph(self) -> CreativeStateRevision:
        orders = [shot.order for shot in self.shots]
        if orders != list(range(1, len(orders) + 1)):
            raise ValueError("creative state shot order must be contiguous and start at 1")
        shot_ids = [shot.shot_id for shot in self.shots]
        if len(shot_ids) != len(set(shot_ids)):
            raise ValueError("creative state shot IDs must be unique")
        if tuple(shot_ids) != self.storyboard.shot_order:
            raise ValueError("storyboard shot_order must match creative state shots")
        if any(
            shot.inherited_product_revision != self.product.product_version_id
            for shot in self.shots
        ):
            raise ValueError("every shot must inherit the current product version")
        if self.parent_revision is not None and self.parent_revision >= self.revision:
            raise ValueError("parent revision must precede the current revision")
        return self


class CreativeState(StateModel):
    schema_version: Literal[CANONICAL_CREATIVE_STATE_SCHEMA] = CANONICAL_CREATIVE_STATE_SCHEMA
    creative_state_id: str = Field(min_length=1, max_length=160)
    owner_id: str = Field(min_length=1, max_length=160)
    project_id: str | None = None
    current_revision: int = Field(ge=1)
    state_version: int = Field(ge=0)
    status: Literal["DRAFT", "READY", "STALE", "BLOCKED"] = "DRAFT"
    product: ProductState
    character: CharacterState | None = None
    scene: SceneState | None = None
    spatial: SpatialState | None = None
    camera: CameraState | None = None
    storyboard: StoryboardState
    shots: tuple[ShotState, ...] = ()
    quality: QualityState = QualityState()
    evidence: tuple[EvidenceRef, ...] = ()
    provenance: Provenance = Provenance()
    content_hash: str = Field(pattern=SHA256_PATTERN.pattern)
    locks_hash: str = Field(pattern=SHA256_PATTERN.pattern)
    source_snapshot_hash: str = Field(pattern=SHA256_PATTERN.pattern)

    @classmethod
    def from_revision(
        cls,
        revision: CreativeStateRevision,
        *,
        owner_id: str,
        project_id: str | None = None,
        status: Literal["DRAFT", "READY", "STALE", "BLOCKED"] = "DRAFT",
    ) -> CreativeState:
        return cls(
            creative_state_id=revision.creative_state_id,
            owner_id=owner_id,
            project_id=project_id,
            current_revision=revision.revision,
            state_version=revision.state_version,
            status=status,
            product=revision.product,
            character=revision.character,
            scene=revision.scene,
            spatial=revision.spatial,
            camera=revision.camera,
            storyboard=revision.storyboard,
            shots=revision.shots,
            quality=revision.quality,
            evidence=revision.evidence,
            provenance=revision.provenance,
            content_hash=revision.content_hash,
            locks_hash=revision.locks_hash,
            source_snapshot_hash=revision.source_snapshot_hash,
        )
