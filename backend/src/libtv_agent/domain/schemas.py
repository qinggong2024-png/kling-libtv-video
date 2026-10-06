import uuid
from datetime import UTC, date, datetime
from typing import Any, Literal

from libtv_agent.domain.enums import (
    ConsistencyLevel,
    DownloadStatus,
    FeedbackReason,
    FeedbackValue,
    GenerationStatus,
    ParentTaskPhase,
    QualityDecisionStatus,
    ValidationStatus,
    VariantKind,
)
from libtv_agent.templates.motion_actions import ActionCapability
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from pydantic.alias_generators import to_camel


class ApiModel(BaseModel):
    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
        serialize_by_alias=True,
        from_attributes=True,
    )


class MotionActionWrite(ApiModel):
    id: str = Field(min_length=2, max_length=80, pattern=r"^[a-z][a-z0-9_]*$")
    label: str = Field(min_length=2, max_length=80)
    category: Literal["outfit", "detail", "back", "interaction", "product"]
    instruction: str = Field(min_length=20, max_length=500)
    purpose: str = Field(min_length=8, max_length=300)
    compatible_templates: list[str] = Field(min_length=1, max_length=20)
    requirements: list[str] = Field(default_factory=list, max_length=20)
    required_capabilities: list[ActionCapability] | None = Field(default=None, max_length=20)
    avoid: list[str] = Field(default_factory=list, max_length=20)
    risk_level: Literal["low", "conditional"] = "low"
    library_scope: Literal["general", "brand"] = "general"
    brand_id: str | None = Field(default=None, min_length=2, max_length=80)
    base_action_id: str | None = Field(default=None, min_length=2, max_length=80)


class SiteStyleProfileWrite(ApiModel):
    id: str = Field(min_length=2, max_length=80, pattern=r"^[a-z][a-z0-9_-]*$")
    status: Literal["draft", "active", "retired"] = "draft"
    name: str = Field(min_length=2, max_length=120)
    site_url: str = Field(default="", max_length=500)
    source_urls: list[str] = Field(default_factory=list, max_length=30)
    retrieved_at: date
    evidence_level: Literal["verified_site", "restricted_site"] = "restricted_site"
    tone: str = Field(min_length=8, max_length=300)
    expression_language: str = Field(
        default="自然、克制并服务于商品展示",
        min_length=8,
        max_length=500,
    )
    audience: str = Field(min_length=6, max_length=300)
    palette: list[str] = Field(default_factory=list, max_length=20)
    typography: str = Field(min_length=2, max_length=300)
    camera_language: str = Field(min_length=10, max_length=500)
    opening_rule: str = Field(min_length=10, max_length=500)
    middle_rule: str = Field(min_length=10, max_length=500)
    ending_rule: str = Field(min_length=10, max_length=500)
    preferred_shots: list[str] = Field(min_length=1, max_length=20)
    preferred_actions: list[str] = Field(default_factory=list, max_length=30)
    pacing: str = Field(min_length=5, max_length=300)
    product_priorities: list[str] = Field(min_length=1, max_length=30)
    forbidden_mismatches: list[str] = Field(min_length=1, max_length=30)
    research_note: str = Field(min_length=8, max_length=1000)
    motion_energy: str = Field(default="standard", min_length=2, max_length=40)
    primary_motion_pool: list[str] = Field(default_factory=list, max_length=30)
    micro_motion_pool: list[str] = Field(default_factory=list, max_length=30)
    expression_pool: list[str] = Field(default_factory=list, max_length=20)
    camera_pool: list[str] = Field(default_factory=list, max_length=20)
    forbidden_motion: list[str] = Field(default_factory=list, max_length=30)
    preferred_environment: list[str] = Field(default_factory=list, max_length=20)
    product_risk_rules: list[str] = Field(default_factory=list, max_length=30)
    dedupe_recent_count: int = Field(default=5, ge=1, le=20)
    dedupe_combo_window: int = Field(default=8, ge=1, le=30)
    dedupe_family_window: int = Field(default=10, ge=1, le=40)
    dedupe_family_limit: int = Field(default=3, ge=1, le=10)
    library_scope: Literal["general", "brand"] = "brand"
    brand_id: str | None = Field(default=None, min_length=2, max_length=80)


class UploadRead(ApiModel):
    id: uuid.UUID
    original_filename: str
    sha256: str
    width: int
    height: int
    mime_type: str
    size_bytes: int
    thumbnail_url: str
    source_image_output_id: uuid.UUID | None = None


class StoryboardInput(ApiModel):
    upload_id: uuid.UUID
    order: int = Field(ge=1, le=7)
    required: bool = True


class ProductReferenceInput(ApiModel):
    upload_id: uuid.UUID
    order: int = Field(ge=1, le=5)


class SubjectImageInput(ApiModel):
    """An ordered subject reference; order 1 is the required frontal image."""

    upload_id: uuid.UUID
    order: int = Field(ge=1, le=4)


class TaskCreate(ApiModel):
    client_task_id: str = Field(min_length=1, max_length=160)
    title: str = Field(min_length=1, max_length=160)
    storyboards: list[StoryboardInput] = Field(min_length=1, max_length=7)
    product_images: list[ProductReferenceInput] = Field(default_factory=list, max_length=5)
    user_requirement: str = Field(default="", max_length=4000)
    generation_preset: str = "DEFAULT_10S_9X16"
    analysis_model: str = Field(
        default="gpt-5.6-luna",
        min_length=1,
        max_length=100,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]*$",
    )
    generation_provider: Literal["libtv", "kling"] = "libtv"
    source_upload_duration_seconds: float = Field(default=0, ge=0, le=86_400)
    variants: list[VariantKind] = Field(
        default_factory=lambda: [VariantKind.STABLE, VariantKind.DYNAMIC],
        min_length=1,
        max_length=2,
    )

    @model_validator(mode="after")
    def validate_order_and_variants(self) -> "TaskCreate":
        orders = [item.order for item in self.storyboards]
        if sorted(orders) != list(range(1, len(orders) + 1)):
            raise ValueError("storyboard order must be contiguous and start at 1")
        valid_variants = (
            [VariantKind.STABLE],
            [VariantKind.DYNAMIC],
            [VariantKind.STABLE, VariantKind.DYNAMIC],
        )
        if self.variants not in valid_variants:
            raise ValueError(
                "variants must request STABLE, DYNAMIC, or the ordered STABLE and DYNAMIC pair"
            )
        product_orders = [item.order for item in self.product_images]
        if sorted(product_orders) != list(range(1, len(product_orders) + 1)):
            raise ValueError("product image order must be contiguous and start at 1")
        upload_ids = [item.upload_id for item in [*self.storyboards, *self.product_images]]
        if len(set(upload_ids)) != len(upload_ids):
            raise ValueError("storyboard and product reference images must be unique")
        return self


class VideoTaskCreate(ApiModel):
    client_task_id: str = Field(min_length=1, max_length=160)
    title: str = Field(min_length=1, max_length=160)
    storyboards: list[StoryboardInput] = Field(min_length=1, max_length=7)
    subject_images: list[SubjectImageInput] = Field(
        default_factory=list,
        max_length=4,
    )
    element_ids: list[str] = Field(default_factory=list, max_length=7)
    generation_mode: Literal["automatic", "custom"] = "automatic"
    custom_prompt: str | None = Field(default=None, max_length=2800)
    template_id: str | None = Field(default=None, min_length=1, max_length=80)
    site_profile_id: str | None = Field(default=None, min_length=1, max_length=80)
    result_count: int = Field(default=1, ge=1, le=4)
    duration_seconds: int = Field(default=10, ge=1, le=15)
    action_intensity: Literal["low", "standard", "high"] = "standard"
    cut_mode: Literal["explicit_cuts", "continuous_when_possible"] = "explicit_cuts"
    paid_submission_consent: bool
    source_upload_duration_seconds: float = Field(default=0, ge=0, le=86_400)

    @model_validator(mode="after")
    def validate_storyboards(self) -> "VideoTaskCreate":
        orders = [item.order for item in self.storyboards]
        if sorted(orders) != list(range(1, len(orders) + 1)):
            raise ValueError("storyboard order must be contiguous and start at 1")
        upload_ids = [item.upload_id for item in [*self.storyboards, *self.subject_images]]
        if len(set(upload_ids)) != len(upload_ids):
            raise ValueError("storyboard and subject image uploads must be unique")
        subject_orders = [item.order for item in self.subject_images]
        if subject_orders and sorted(subject_orders) != list(range(1, len(subject_orders) + 1)):
            raise ValueError("subject image order must be contiguous and start at 1")
        normalized_element_ids = [element_id.strip() for element_id in self.element_ids]
        if any(not element_id or len(element_id) > 160 for element_id in normalized_element_ids):
            raise ValueError("element IDs must be non-empty and at most 160 characters")
        if len(set(normalized_element_ids)) != len(normalized_element_ids):
            raise ValueError("element IDs must be unique")
        if self.subject_images and normalized_element_ids:
            raise ValueError("new subject images and historical element IDs are mutually exclusive")
        if len(self.storyboards) + len(self.subject_images) + len(normalized_element_ids) > 7:
            raise ValueError(
                "storyboards, subject images, and element IDs together cannot exceed "
                "the Kling Omni 7-reference limit"
            )
        if self.generation_mode == "automatic" and not self.site_profile_id:
            raise ValueError("automatic generation requires a site profile")
        if self.generation_mode == "custom":
            prompt = (self.custom_prompt or "").strip()
            if not prompt:
                raise ValueError("custom generation requires a prompt")
            self.custom_prompt = prompt
            self.site_profile_id = None
        else:
            self.custom_prompt = None
        self.element_ids = normalized_element_ids
        return self


class PromptPresetWrite(ApiModel):
    scope: Literal["video", "image_fusion", "image_storyboard"] = "video"
    name: str = Field(min_length=1, max_length=80)
    content: str = Field(min_length=1, max_length=2800)
    sort_order: int = Field(default=0, ge=0, le=10_000)

    @model_validator(mode="after")
    def normalize_values(self) -> "PromptPresetWrite":
        self.name = self.name.strip()
        self.content = self.content.strip()
        if not self.name or not self.content:
            raise ValueError("prompt preset name and content cannot be blank")
        return self


class PromptPresetRead(PromptPresetWrite):
    id: uuid.UUID
    created_at: datetime
    updated_at: datetime


class TaskReuseRequest(ApiModel):
    client_task_id: str = Field(min_length=1, max_length=160)
    title: str = Field(min_length=1, max_length=160)
    expected_source_state_version: int = Field(ge=1)
    variants: list[VariantKind] = Field(min_length=1, max_length=2)

    @model_validator(mode="after")
    def validate_variants(self) -> "TaskReuseRequest":
        valid_variants = (
            [VariantKind.STABLE],
            [VariantKind.DYNAMIC],
            [VariantKind.STABLE, VariantKind.DYNAMIC],
        )
        if self.variants not in valid_variants:
            raise ValueError(
                "variants must request STABLE, DYNAMIC, or the ordered STABLE and DYNAMIC pair"
            )
        return self


class AssetRead(ApiModel):
    id: uuid.UUID
    order: int
    required: bool
    original_filename: str
    sha256: str
    width: int
    height: int
    size_bytes: int = 0
    thumbnail_url: str
    source_image_output_id: uuid.UUID | None = None
    role: str = "STORYBOARD"
    used_for_analysis: bool = True
    used_for_generation: bool = True


class VariantRead(ApiModel):
    id: uuid.UUID
    kind: VariantKind
    revision: int
    prompt_text: str
    prompt_hash: str | None
    generation_status: GenerationStatus
    download_status: DownloadStatus
    validation_status: ValidationStatus
    final_approval_status: QualityDecisionStatus = QualityDecisionStatus.PENDING
    quality_gates: dict[str, Any] = Field(default_factory=dict)
    final_approved_by: uuid.UUID | None = None
    final_approved_at: datetime | None = None
    human_review_seconds: float | None = None
    review_notes: str | None = None
    download_artifact_id: uuid.UUID | None = None
    error_code: str | None = None
    provider_error_message: str | None = None
    provider_error_details: dict[str, Any] | None = None
    provider_error_retryable: bool | None = None
    provider: str
    provider_task_id: str | None = None
    provider_status: str | None = None
    execution_backend: str | None = None
    variant_index: int | None = None
    variant_key: str | None = None
    variant_seed: dict[str, Any] = Field(default_factory=dict)
    feedback: FeedbackValue | None = None
    feedback_reasons: list[FeedbackReason] = Field(default_factory=list)
    feedback_comment: str | None = None


class VariantFeedbackRequest(ApiModel):
    feedback: FeedbackValue | None
    reasons: list[FeedbackReason] | None = Field(default=None, max_length=3)
    comment: str | None = Field(default=None, max_length=240)

    @field_validator("comment")
    @classmethod
    def normalize_comment(cls, value: str | None) -> str | None:
        normalized = " ".join((value or "").split()).strip()
        return normalized or None

    @model_validator(mode="after")
    def validate_details(self) -> "VariantFeedbackRequest":
        if self.feedback is None and (self.reasons or self.comment):
            raise ValueError("feedback details require a like or dislike")
        like_reasons = {
            FeedbackReason.GARMENT_ACCURATE,
            FeedbackReason.PRODUCT_CLEAR,
            FeedbackReason.NATURAL_MOTION,
            FeedbackReason.COMFORTABLE_CAMERA,
            FeedbackReason.GOOD_PACING,
            FeedbackReason.STRONG_APPEAL,
        }
        if self.reasons:
            if len(set(self.reasons)) != len(self.reasons):
                raise ValueError("feedback reasons must be unique")
            if self.feedback == FeedbackValue.LIKE and not set(self.reasons) <= like_reasons:
                raise ValueError("like feedback contains a dislike reason")
            if self.feedback == FeedbackValue.DISLIKE and set(self.reasons) & like_reasons:
                raise ValueError("dislike feedback contains a like reason")
        return self


class FinalApprovalRequest(ApiModel):
    decision: Literal["APPROVED", "REJECTED"]
    product_fidelity_pass: bool
    editing_assembly_pass: bool
    human_critical_pass: bool
    human_review_seconds: float = Field(gt=0, le=28_800)
    expected_state_version: int = Field(ge=1)
    notes: str | None = Field(default=None, max_length=500)

    @model_validator(mode="after")
    def validate_decision(self) -> "FinalApprovalRequest":
        gates_pass = (
            self.product_fidelity_pass and self.editing_assembly_pass and self.human_critical_pass
        )
        if (self.decision == "APPROVED") != gates_pass:
            raise ValueError("APPROVED requires every human Required Hard Gate to pass")
        self.notes = " ".join((self.notes or "").split()).strip() or None
        if self.decision == "REJECTED" and not self.notes:
            raise ValueError("REJECTED requires a review reason")
        return self


class PointsQuotaRead(ApiModel):
    """Per-user daily generation quota.

    Field names keep the historical "points" wording so the API contract stays
    compatible, but the unit is now *video generations per day* (configured by
    DAILY_USER_POINTS_LIMIT / GENERATION_ESTIMATED_POINTS). Image generation does
    not consume this quota. See services/points.py for the enforcement rule.
    """

    daily_limit: int = 100
    consumed: int = 0
    reserved: int = 0
    uncertain: int = 0
    remaining: int = 100
    team_limit: int | None = None


class ActionCapabilities(ApiModel):
    can_edit: bool
    can_confirm: bool
    can_cancel: bool
    can_retry_analysis: bool
    can_regenerate: bool
    can_download: bool


class TaskStageTimingRead(ApiModel):
    key: Literal[
        "SOURCE_UPLOAD",
        "ANALYSIS",
        "CONFIRMATION",
        "MATERIALIZATION",
        "GENERATION",
        "DOWNLOAD",
    ]
    status: Literal["COMPLETED", "ACTIVE", "PENDING", "FAILED"]
    duration_seconds: float | None = None
    active_started_at: datetime | None = None
    attempt_count: int | None = None


class TaskTimingRead(ApiModel):
    stages: list[TaskStageTimingRead] = Field(default_factory=list)


class TaskRead(ApiModel):
    id: uuid.UUID
    user_id: uuid.UUID
    client_task_id: str
    title: str
    asset_count: int
    user_requirement: str
    analysis_model: str
    generation_provider: str
    phase: ParentTaskPhase
    phase_reason_code: str | None
    consistency_level: ConsistencyLevel | None
    analysis_result: dict[str, Any] | None
    analysis_run_id: uuid.UUID | None
    analysis_stage: str | None
    analysis_started_at: datetime | None
    analysis_heartbeat_at: datetime | None
    canvas_project_uuid: str | None
    state_version: int
    assets: list[AssetRead]
    variants: list[VariantRead]
    points_quota: PointsQuotaRead
    action_capabilities: ActionCapabilities
    timing: TaskTimingRead = Field(default_factory=TaskTimingRead)
    workflow_kind: str = "LEGACY_ANALYSIS"
    template_id: str | None = None
    template_version: str | None = None
    site_profile_id: str | None = None
    site_profile_version: str | None = None
    settings: dict[str, Any] = Field(default_factory=dict)
    compiled_plan: dict[str, Any] | None = None
    material_validation: dict[str, Any] | None = None
    paid_submission_consent_at: datetime | None = None
    created_at: datetime
    updated_at: datetime

    @field_validator(
        "created_at",
        "updated_at",
        "analysis_started_at",
        "analysis_heartbeat_at",
        "paid_submission_consent_at",
    )
    @classmethod
    def normalize_task_timestamp(cls, value: datetime | None) -> datetime | None:
        if value is None:
            return None
        # SQLite drops timezone metadata even though these columns store UTC.
        # Restore it before JSON serialization so browsers do not read UTC as local time.
        return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)

    @property
    def status(self) -> ParentTaskPhase:
        return self.phase


class AnalyzeRequest(ApiModel):
    expected_state_version: int


class ConfirmRequest(ApiModel):
    expected_state_version: int
    accept_risk: bool = False
    variants: list[VariantKind] | None = Field(default=None, min_length=1, max_length=2)

    @model_validator(mode="after")
    def validate_variants(self) -> "ConfirmRequest":
        if self.variants is not None and len(set(self.variants)) != len(self.variants):
            raise ValueError("variants must not contain duplicates")
        return self


class PromptUpdateRequest(ApiModel):
    expected_state_version: int
    stable_prompt: str = Field(min_length=1, max_length=2000)
    dynamic_prompt: str = Field(min_length=1, max_length=2000)

    @model_validator(mode="after")
    def validate_prompts(self) -> "PromptUpdateRequest":
        self.stable_prompt = self.stable_prompt.strip()
        self.dynamic_prompt = self.dynamic_prompt.strip()
        if not self.stable_prompt or not self.dynamic_prompt:
            raise ValueError("stablePrompt and dynamicPrompt cannot be blank")
        return self


class PromptAssistantRequest(PromptUpdateRequest):
    instruction: str = Field(min_length=1, max_length=2000)
    action: Literal["REGENERATE", "ADVISE"]
    target_variant: VariantKind | None = None

    @model_validator(mode="after")
    def validate_instruction(self) -> "PromptAssistantRequest":
        self.instruction = self.instruction.strip()
        if not self.instruction:
            raise ValueError("instruction cannot be blank")
        return self


class PromptAssistantResponse(ApiModel):
    task: TaskRead
    advice: str


class ReorderRequest(ApiModel):
    expected_state_version: int
    ordered_asset_ids: list[uuid.UUID] = Field(min_length=1, max_length=7)


class ReconcileRequest(ApiModel):
    action: str = Field(pattern="^(RECONCILE|MARK_MANUAL_REVIEW)$")


class RestoreRequest(ApiModel):
    variant: VariantKind


class BatchConfirmationItem(ApiModel):
    task_id: uuid.UUID
    expected_state_version: int
    accept_risk: bool = False


class BatchConfirmationRequest(ApiModel):
    tasks: list[BatchConfirmationItem] = Field(min_length=1, max_length=100)

    @model_validator(mode="after")
    def validate_unique_tasks(self) -> "BatchConfirmationRequest":
        task_ids = [item.task_id for item in self.tasks]
        if len(task_ids) != len(set(task_ids)):
            raise ValueError("batch confirmation cannot contain duplicate task IDs")
        return self


class BatchConfirmationResult(ApiModel):
    task_id: uuid.UUID
    status: Literal["SUCCEEDED", "FAILED"]
    task: TaskRead | None = None
    error_code: str | None = None
    message: str | None = None


class BatchConfirmationResponse(ApiModel):
    results: list[BatchConfirmationResult]
    succeeded_count: int
    failed_count: int


class ErrorDetail(ApiModel):
    code: str
    message: str
    correlation_id: str
    retryable: bool = False
    field_errors: list[dict[str, Any]] = Field(default_factory=list)
    current_state_version: int | None = None


class ErrorResponse(ApiModel):
    error: ErrorDetail
