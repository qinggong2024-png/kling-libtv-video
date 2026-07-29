import uuid
from datetime import UTC, datetime
from typing import Any, Literal

from libtv_agent.domain.enums import (
    ConsistencyLevel,
    DownloadStatus,
    FeedbackReason,
    FeedbackValue,
    GenerationStatus,
    ParentTaskPhase,
    ValidationStatus,
    VariantKind,
)
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from pydantic.alias_generators import to_camel


class ApiModel(BaseModel):
    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
        serialize_by_alias=True,
        from_attributes=True,
    )


class UploadRead(ApiModel):
    id: uuid.UUID
    original_filename: str
    sha256: str
    width: int
    height: int
    mime_type: str
    thumbnail_url: str


class StoryboardInput(ApiModel):
    upload_id: uuid.UUID
    order: int = Field(ge=1, le=7)
    required: bool = True


class ProductReferenceInput(ApiModel):
    upload_id: uuid.UUID
    order: int = Field(ge=1, le=5)


class TaskCreate(ApiModel):
    client_task_id: str = Field(min_length=1, max_length=160)
    title: str = Field(min_length=1, max_length=160)
    storyboards: list[StoryboardInput] = Field(min_length=1, max_length=7)
    product_images: list[ProductReferenceInput] = Field(default_factory=list, max_length=5)
    user_requirement: str = Field(default="", max_length=4000)
    generation_preset: str = "DEFAULT_10S_9X16"
    analysis_model: str = Field(
        default="gpt-5.6-terra",
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
    thumbnail_url: str
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
    download_artifact_id: uuid.UUID | None = None
    error_code: str | None = None
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


class PointsQuotaRead(ApiModel):
    daily_limit: int = 5000
    consumed: int = 0
    reserved: int = 0
    uncertain: int = 0
    remaining: int = 5000
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
    created_at: datetime
    updated_at: datetime

    @field_validator(
        "created_at",
        "updated_at",
        "analysis_started_at",
        "analysis_heartbeat_at",
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
