from __future__ import annotations

import hashlib
import json
from datetime import datetime
from enum import StrEnum
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

CONTRACT_SCHEMA_VERSION = "1.0"


class ContractModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    schema_version: Literal["1.0"] = CONTRACT_SCHEMA_VERSION


class DifficultyTier(StrEnum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


class Route(StrEnum):
    LONG_CLIP = "LONG_CLIP"
    SHORT_SHOT = "SHORT_SHOT"


class DecisionAction(StrEnum):
    KEEP = "KEEP"
    CUT = "CUT"
    REGENERATE = "REGENERATE"


class Severity(StrEnum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class PropagationRisk(StrEnum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


class ProductTruthSnapshot(ContractModel):
    snapshot_id: str = Field(min_length=1)
    product_id: str = Field(min_length=1)
    source_images: tuple[str, ...] = Field(min_length=1)
    source_image_hashes: tuple[str, ...] = Field(min_length=1)
    product_type: str = Field(min_length=1)
    dominant_color: str | None = None
    graphic_regions: tuple[str, ...] = ()
    logo_regions: tuple[str, ...] = ()
    key_structural_attributes: tuple[str, ...] = ()
    must_preserve_features: tuple[str, ...] = ()
    reference_views: tuple[str, ...] = ()
    unknown_views: tuple[str, ...] = ()
    created_at: datetime
    immutable: Literal[True] = True

    @model_validator(mode="after")
    def hashes_match_images(self) -> ProductTruthSnapshot:
        if len(self.source_images) != len(self.source_image_hashes):
            raise ValueError("source image hashes must map one-to-one to source images")
        return self

    def content_hash(self) -> str:
        payload = self.model_dump(mode="json", exclude={"snapshot_id"})
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        return hashlib.sha256(encoded).hexdigest()


class GeneratedSourceClip(ContractModel):
    clip_id: str
    product_snapshot_id: str
    product_snapshot_hash: str
    route: Route
    duration_ms: Annotated[int, Field(gt=0)]
    provider: str
    model: str
    cost: Annotated[float, Field(ge=0)] = 0


class TemporalError(ContractModel):
    reason_code: str
    severity: Severity
    confidence: Annotated[float, Field(ge=0, le=1)]
    start_ms: Annotated[int, Field(ge=0)]
    end_ms: Annotated[int, Field(gt=0)]
    propagation_risk: PropagationRisk

    @model_validator(mode="after")
    def interval_is_ordered(self) -> TemporalError:
        if self.end_ms <= self.start_ms:
            raise ValueError("temporal error end must be after start")
        return self


class ErrorDecision(ContractModel):
    action: DecisionAction
    reason_code: str
    severity: Severity
    confidence: Annotated[float, Field(ge=0, le=1)]
    target: str
    retry_strategy: str | None = None
    retry_count: Annotated[int, Field(ge=0)] = 0
    retry_budget: Annotated[int, Field(ge=0)] = 2
    propagation_risk: PropagationRisk
    start_ms: Annotated[int, Field(ge=0)]
    end_ms: Annotated[int, Field(gt=0)]
    safe_cut_before_ms: Annotated[int | None, Field(ge=0)] = None
    safe_cut_after_ms: Annotated[int | None, Field(ge=0)] = None
    salvageable: bool

    @model_validator(mode="after")
    def validate_decision(self) -> ErrorDecision:
        if self.end_ms <= self.start_ms:
            raise ValueError("decision end must be after start")
        if self.action == DecisionAction.CUT:
            if not self.salvageable:
                raise ValueError("CUT requires a salvageable error")
            if self.safe_cut_before_ms is None or self.safe_cut_after_ms is None:
                raise ValueError("CUT requires both safe cut boundaries")
            if self.safe_cut_before_ms > self.start_ms:
                raise ValueError("safe cut before must not fall inside the error")
            if self.safe_cut_after_ms < self.end_ms:
                raise ValueError("safe cut after must not fall inside the error")
        if self.action == DecisionAction.REGENERATE and not self.retry_strategy:
            raise ValueError("REGENERATE requires a targeted retry strategy")
        return self


class QualifiedSegment(ContractModel):
    segment_id: str
    source_clip_id: str
    product_snapshot_id: str
    start_ms: Annotated[int, Field(ge=0)]
    end_ms: Annotated[int, Field(gt=0)]
    product_fidelity: Literal["PASS"]
    human_integrity: Literal["PASS"]
    spatial_integrity: Literal["PASS"]
    reason_codes: tuple[str, ...] = ()

    @model_validator(mode="after")
    def segment_is_ordered(self) -> QualifiedSegment:
        if self.end_ms <= self.start_ms:
            raise ValueError("segment end must be after start")
        return self


class MusicTrack(ContractModel):
    track_id: str
    source: str
    license_status: str = Field(min_length=1)
    license_scope: str = Field(min_length=1)
    duration_ms: Annotated[int, Field(gt=0)]
    bpm: Annotated[float, Field(gt=0)]
    beats_ms: tuple[Annotated[int, Field(ge=0)], ...]
    downbeats_ms: tuple[Annotated[int, Field(ge=0)], ...] = ()
    energy_curve: tuple[float, ...] = ()
    usable_range_ms: tuple[int, int]
    genre: str
    mood: str
    brand_fit: tuple[str, ...] = ()

    @property
    def production_eligible(self) -> bool:
        return self.license_status in {"AUTHORIZED", "LICENSED", "PUBLIC_DOMAIN"}


class EditShot(ContractModel):
    segment_id: str
    semantic_cut_ms: Annotated[int, Field(ge=0)]
    minimum_cut_ms: Annotated[int, Field(ge=0)]
    maximum_cut_ms: Annotated[int, Field(ge=0)]
    product_fidelity: Literal["PASS"]
    segment_validity: Literal["PASS"]
    semantic_continuity: Literal["PASS"]
    product_visibility: Literal["PASS"]
    shot_completeness: Literal["PASS"]

    @model_validator(mode="after")
    def cut_window_contains_semantic_cut(self) -> EditShot:
        if not self.minimum_cut_ms <= self.semantic_cut_ms <= self.maximum_cut_ms:
            raise ValueError("semantic cut must be inside its valid edit window")
        return self


class SemanticEditSkeleton(ContractModel):
    skeleton_id: str
    shots: tuple[EditShot, ...] = Field(min_length=1)


class RenderPlan(ContractModel):
    render_plan_id: str
    product_snapshot_id: str
    source_clip_ids: tuple[str, ...] = Field(min_length=1)
    cuts_ms: tuple[Annotated[int, Field(ge=0)], ...]
    track_id: str
    deterministic_fingerprint: str


class GroundTruthReview(ContractModel):
    artifact_id: str
    ground_truth_status: Literal["PASS", "FAIL"]
    product_fidelity: Literal["PASS", "FAIL"]
    human_integrity: Literal["PASS", "FAIL"]
    spatial_integrity: Literal["PASS", "FAIL"]
    editorial_usability: Literal["PASS", "FAIL"]
    failure_codes: tuple[str, ...] = ()
    reviewer_id: str
    reviewed_at: datetime


class PilotRun(ContractModel):
    run_id: str
    sku: str
    difficulty_tier: DifficultyTier
    route: Route
    provider: str
    model: str
    generated_seconds: Annotated[float, Field(gt=0)]
    actual_api_cost: Annotated[float, Field(ge=0)]
    image_attempts: Annotated[int, Field(ge=0)]
    video_attempts: Annotated[int, Field(ge=1)]
    retry_reasons: tuple[str, ...] = ()
    technical_qualified_seconds: Annotated[float, Field(ge=0)]
    editorial_qualified_seconds: Annotated[float, Field(ge=0)]
    final_duration_seconds: Annotated[float, Field(ge=0)]
    lead_time_seconds: Annotated[float, Field(ge=0)]
    system_pass: bool
    ground_truth_pass: bool
    product_fidelity_pass: bool
    human_intervention: bool
    failure_codes: tuple[str, ...] = ()

