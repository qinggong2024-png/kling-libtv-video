import uuid
from datetime import date, datetime
from typing import Any

from libtv_agent.domain.enums import (
    AttemptStatus,
    BillingSource,
    CanvasExecutionState,
    CanvasMutationState,
    ChargeStatus,
    CommandStatus,
    ConsistencyLevel,
    DownloadStatus,
    FeedbackValue,
    GenerationStatus,
    LedgerEntryType,
    OperationStatus,
    OutboxStatus,
    ParentTaskPhase,
    ProductLicenseStatus,
    ProductVersionStatus,
    QualityDecisionStatus,
    ReservationStatus,
    RunnerHostStatus,
    SagaStatus,
    UserRole,
    ValidationStatus,
    VariantKind,
)
from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    Date,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


ACTIVE_ATTEMPT_SQL = (
    "status IN ('PREPARED','DISPATCH_PENDING','LAUNCHING','RUNNING',"
    "'UNKNOWN_AFTER_SUBMIT','SUCCEEDED')"
)


def enum_column(enum_type: type, **kwargs: Any) -> Any:
    return mapped_column(Enum(enum_type, native_enum=False), **kwargs)


class User(Base):
    __tablename__ = "app_user"
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    username: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[UserRole] = enum_column(UserRole, default=UserRole.USER)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    auto_confirm_prompts: Mapped[bool] = mapped_column(Boolean, default=False)
    video_learning_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class UserSession(Base):
    __tablename__ = "user_session"
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("app_user.id", ondelete="CASCADE"))
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Product(Base):
    __tablename__ = "product"
    __table_args__ = (
        UniqueConstraint("user_id", "internal_sku_id", name="uq_product_user_sku"),
        Index("ix_product_user_updated", "user_id", "updated_at", "id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("app_user.id", ondelete="CASCADE"), index=True
    )
    internal_sku_id: Mapped[str] = mapped_column(String(160))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    versions: Mapped[list["ProductVersion"]] = relationship(
        back_populates="product", cascade="all, delete-orphan", lazy="selectin"
    )


class ProductVersion(Base):
    __tablename__ = "product_version"
    __table_args__ = (
        UniqueConstraint("product_id", "version_number", name="uq_product_version_number"),
        Index("ix_product_version_product_created", "product_id", "created_at", "id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    product_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("product.id", ondelete="CASCADE"), index=True
    )
    version_number: Mapped[int] = mapped_column(Integer)
    product_page_url: Mapped[str] = mapped_column(String(1000))
    page_title: Mapped[str | None] = mapped_column(String(500))
    candidate_names: Mapped[list[str]] = mapped_column(JSON, default=list)
    truth_fields: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    immutable_fields: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    allowed_variation: Mapped[list[str]] = mapped_column(JSON, default=list)
    source_asset_references: Mapped[list[str]] = mapped_column(JSON, default=list)
    license_status: Mapped[ProductLicenseStatus] = enum_column(
        ProductLicenseStatus, default=ProductLicenseStatus.UNKNOWN, index=True
    )
    status: Mapped[ProductVersionStatus] = enum_column(
        ProductVersionStatus, default=ProductVersionStatus.DRAFT, index=True
    )
    blocked_reason: Mapped[str | None] = mapped_column(String(500))
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    product: Mapped["Product"] = relationship(back_populates="versions")


class PromptPreset(Base):
    __tablename__ = "prompt_preset"
    __table_args__ = (
        UniqueConstraint("user_id", "scope", "name", name="uq_prompt_preset_user_scope_name"),
        Index(
            "ix_prompt_preset_user_scope_order",
            "user_id",
            "scope",
            "sort_order",
            "created_at",
        ),
    )
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("app_user.id", ondelete="CASCADE"), index=True
    )
    scope: Mapped[str] = mapped_column(String(32), default="video")
    name: Mapped[str] = mapped_column(String(80))
    content: Mapped[str] = mapped_column(Text)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class CatalogEntry(Base):
    __tablename__ = "catalog_entry"
    __table_args__ = (
        UniqueConstraint("entry_type", "entry_id", name="uq_catalog_entry_type_id"),
        Index("ix_catalog_entry_type_updated", "entry_type", "updated_at"),
    )
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    entry_type: Mapped[str] = mapped_column(String(32))
    entry_id: Mapped[str] = mapped_column(String(80))
    payload_json: Mapped[dict[str, Any]] = mapped_column(JSON)
    updated_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("app_user.id", ondelete="RESTRICT"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class ParentTask(Base):
    __tablename__ = "parent_task"
    __table_args__ = (
        UniqueConstraint("user_id", "client_task_id", name="uq_task_user_client"),
        Index("ix_parent_task_user_created", "user_id", "created_at", "id"),
        Index("ix_parent_task_user_updated", "user_id", "updated_at", "id"),
    )
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("app_user.id", ondelete="RESTRICT"), index=True
    )
    client_task_id: Mapped[str] = mapped_column(String(160))
    title: Mapped[str] = mapped_column(String(160))
    asset_count: Mapped[int] = mapped_column(Integer)
    phase: Mapped[ParentTaskPhase] = enum_column(
        ParentTaskPhase, default=ParentTaskPhase.DRAFT, index=True
    )
    phase_reason_code: Mapped[str | None] = mapped_column(String(80))
    consistency_level: Mapped[ConsistencyLevel | None] = enum_column(ConsistencyLevel)
    analysis_result_json: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    analysis_result_hash: Mapped[str | None] = mapped_column(String(64))
    analysis_run_id: Mapped[uuid.UUID | None] = mapped_column(index=True)
    analysis_stage: Mapped[str | None] = mapped_column(String(40), index=True)
    analysis_started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    analysis_heartbeat_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), index=True
    )
    source_upload_duration_seconds: Mapped[float] = mapped_column(Float, default=0.0)
    analysis_duration_seconds: Mapped[float] = mapped_column(Float, default=0.0)
    prompt_analysis_duration_seconds: Mapped[float] = mapped_column(Float, default=0.0)
    analysis_attempt_count: Mapped[int] = mapped_column(Integer, default=0)
    user_requirement_raw: Mapped[str] = mapped_column(Text, default="")
    user_requirement_normalized: Mapped[str] = mapped_column(Text, default="")
    workflow_kind: Mapped[str] = mapped_column(
        String(32), default="LEGACY_ANALYSIS", server_default="LEGACY_ANALYSIS", index=True
    )
    template_id: Mapped[str | None] = mapped_column(String(80), index=True)
    template_version: Mapped[str | None] = mapped_column(String(40))
    site_profile_id: Mapped[str | None] = mapped_column(String(80), index=True)
    site_profile_version: Mapped[str | None] = mapped_column(String(40))
    settings_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    compiled_plan_json: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    material_validation_json: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    paid_submission_consent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    assigned_project_uuid: Mapped[str | None] = mapped_column(String(64), index=True)
    state_version: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    variants: Mapped[list["GenerationVariant"]] = relationship(
        back_populates="parent_task", cascade="all, delete-orphan", lazy="selectin"
    )
    assets: Mapped[list["Asset"]] = relationship(
        back_populates="parent_task",
        cascade="all, delete-orphan",
        lazy="selectin",
        order_by="Asset.order_no",
    )

    @property
    def status(self) -> ParentTaskPhase:
        return self.phase

    @property
    def user_requirement(self) -> str:
        return self.user_requirement_raw


class StagedUpload(Base):
    __tablename__ = "staged_upload"
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("app_user.id", ondelete="CASCADE"), index=True
    )
    original_filename: Mapped[str] = mapped_column(String(255))
    sha256: Mapped[str] = mapped_column(String(64), index=True)
    mime_type: Mapped[str] = mapped_column(String(80))
    size_bytes: Mapped[int] = mapped_column(BigInteger, default=0, server_default="0")
    width: Mapped[int] = mapped_column(Integer)
    height: Mapped[int] = mapped_column(Integer)
    object_key: Mapped[str] = mapped_column(String(500))
    thumbnail_key: Mapped[str] = mapped_column(String(500))
    claimed_task_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("parent_task.id"), index=True
    )
    source_image_output_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("image_generation_output.id", ondelete="SET NULL"), index=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Asset(Base):
    __tablename__ = "asset"
    __table_args__ = (UniqueConstraint("parent_task_id", "order_no", name="uq_asset_task_order"),)
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    parent_task_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("parent_task.id", ondelete="CASCADE"), index=True
    )
    source_type: Mapped[str] = mapped_column(String(32), default="STORYBOARD")
    role: Mapped[str] = mapped_column(String(32), default="STORYBOARD")
    order_no: Mapped[int] = mapped_column(Integer)
    required: Mapped[bool] = mapped_column(Boolean, default=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    original_filename: Mapped[str] = mapped_column(String(255))
    sha256: Mapped[str] = mapped_column(String(64), index=True)
    mime_type: Mapped[str] = mapped_column(String(80))
    size_bytes: Mapped[int] = mapped_column(BigInteger, default=0, server_default="0")
    width: Mapped[int] = mapped_column(Integer)
    height: Mapped[int] = mapped_column(Integer)
    object_key: Mapped[str | None] = mapped_column(String(500))
    thumbnail_key: Mapped[str | None] = mapped_column(String(500))
    source_image_output_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("image_generation_output.id", ondelete="SET NULL"), index=True
    )
    used_for_analysis: Mapped[bool] = mapped_column(Boolean, default=True)
    used_for_generation: Mapped[bool] = mapped_column(Boolean, default=True)
    libtv_node_key: Mapped[str | None] = mapped_column(String(160))
    materialized_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    parent_task: Mapped[ParentTask] = relationship(back_populates="assets")


class CanvasProject(Base):
    __tablename__ = "canvas_project"
    __table_args__ = (
        Index(
            "uq_canvas_open_per_user",
            "user_id",
            unique=True,
            postgresql_where=text("mutation_state = 'OPEN'"),
            sqlite_where=text("mutation_state = 'OPEN'"),
        ),
        Index(
            "uq_canvas_draining_per_user",
            "user_id",
            unique=True,
            postgresql_where=text("mutation_state = 'DRAINING'"),
            sqlite_where=text("mutation_state = 'DRAINING'"),
        ),
    )
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("app_user.id", ondelete="RESTRICT"), index=True
    )
    project_uuid: Mapped[str] = mapped_column(String(64), unique=True)
    mutation_state: Mapped[CanvasMutationState] = enum_column(
        CanvasMutationState, default=CanvasMutationState.OPEN
    )
    execution_state: Mapped[CanvasExecutionState] = enum_column(
        CanvasExecutionState, default=CanvasExecutionState.IDLE
    )
    reserved_parent_count: Mapped[int] = mapped_column(Integer, default=0)
    prepared_video_count: Mapped[int] = mapped_column(Integer, default=0)
    reservation_opened_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    batch_opened_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    seal_deadline: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    state_version: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class ModelSchemaSnapshot(Base):
    __tablename__ = "model_schema_snapshot"
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    cli_version: Mapped[str] = mapped_column(String(40))
    account_id: Mapped[str] = mapped_column(String(80))
    team_id: Mapped[str | None] = mapped_column(String(80))
    workspace_id: Mapped[str | None] = mapped_column(String(80))
    model_key: Mapped[str] = mapped_column(String(120))
    schema_json: Mapped[dict[str, Any]] = mapped_column(JSON)
    compatibility_fingerprint: Mapped[str] = mapped_column(String(64), index=True)
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class GenerationVariant(Base):
    __tablename__ = "generation_variant"
    __table_args__ = (
        UniqueConstraint(
            "parent_task_id", "variant_type", "revision", name="uq_variant_task_type_revision"
        ),
    )
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    parent_task_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("parent_task.id", ondelete="CASCADE"), index=True
    )
    variant_type: Mapped[VariantKind] = enum_column(VariantKind)
    revision: Mapped[int] = mapped_column(Integer, default=1)
    prompt_text: Mapped[str] = mapped_column(Text, default="")
    prompt_hash: Mapped[str | None] = mapped_column(String(64))
    prompt_template_version: Mapped[str] = mapped_column(String(40), default="1.0.0")
    variant_index: Mapped[int | None] = mapped_column(Integer)
    variant_key: Mapped[str | None] = mapped_column(String(80))
    variant_seed_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    generation_config_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    generation_config_hash: Mapped[str | None] = mapped_column(String(64))
    ordered_storyboard_assets_hash: Mapped[str | None] = mapped_column(String(64))
    schema_snapshot_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("model_schema_snapshot.id")
    )
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    generation_status: Mapped[GenerationStatus] = enum_column(
        GenerationStatus, default=GenerationStatus.PENDING
    )
    download_status: Mapped[DownloadStatus] = enum_column(
        DownloadStatus, default=DownloadStatus.NOT_READY
    )
    validation_status: Mapped[ValidationStatus] = enum_column(
        ValidationStatus, default=ValidationStatus.NOT_READY
    )
    final_approval_status: Mapped[QualityDecisionStatus] = enum_column(
        QualityDecisionStatus, default=QualityDecisionStatus.PENDING
    )
    quality_gates_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    final_approved_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("app_user.id"))
    final_approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    human_review_seconds: Mapped[float | None] = mapped_column(Float)
    review_notes: Mapped[str | None] = mapped_column(String(500))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    parent_task: Mapped[ParentTask] = relationship(back_populates="variants")
    attempts: Mapped[list["GenerationAttempt"]] = relationship(
        back_populates="variant", cascade="all, delete-orphan"
    )

    @property
    def kind(self) -> VariantKind:
        return self.variant_type


class GenerationFeedback(Base):
    __tablename__ = "generation_feedback"
    __table_args__ = (
        UniqueConstraint("variant_id", name="uq_generation_feedback_variant"),
        Index(
            "ix_generation_feedback_learning",
            "user_id",
            "scene_key",
            "variant_type",
            "updated_at",
        ),
    )
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("app_user.id", ondelete="CASCADE"), index=True
    )
    parent_task_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("parent_task.id", ondelete="CASCADE"), index=True
    )
    variant_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("generation_variant.id", ondelete="CASCADE"), index=True
    )
    variant_type: Mapped[VariantKind] = enum_column(VariantKind)
    value: Mapped[FeedbackValue] = enum_column(FeedbackValue)
    scene_key: Mapped[str] = mapped_column(String(64))
    context_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    prompt_snapshot: Mapped[str] = mapped_column(Text)
    reason_codes_json: Mapped[list[str]] = mapped_column(JSON, default=list)
    comment: Mapped[str | None] = mapped_column(String(240), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=func.now(), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=func.now(),
        server_default=func.now(),
        onupdate=func.now(),
    )


class UserVideoLearningProfile(Base):
    __tablename__ = "user_video_learning_profile"
    __table_args__ = (
        UniqueConstraint("user_id", "scope_key", name="uq_video_learning_profile_user_scope"),
        Index("ix_video_learning_profile_user_updated", "user_id", "updated_at"),
    )
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("app_user.id", ondelete="CASCADE"), index=True
    )
    scope_key: Mapped[str] = mapped_column(String(240))
    template_id: Mapped[str] = mapped_column(String(80))
    site_profile_id: Mapped[str] = mapped_column(String(80))
    summary: Mapped[str] = mapped_column(Text, default="")
    deterministic_guidance: Mapped[str] = mapped_column(Text, default="")
    llm_prompt_guidance: Mapped[str] = mapped_column(Text, default="")
    preferred_action_ids_json: Mapped[list[str]] = mapped_column(JSON, default=list)
    avoided_action_ids_json: Mapped[list[str]] = mapped_column(JSON, default=list)
    llm_preferred_action_ids_json: Mapped[list[str]] = mapped_column(JSON, default=list)
    llm_avoided_action_ids_json: Mapped[list[str]] = mapped_column(JSON, default=list)
    evidence_count: Mapped[int] = mapped_column(Integer, default=0)
    positive_count: Mapped[int] = mapped_column(Integer, default=0)
    negative_count: Mapped[int] = mapped_column(Integer, default=0)
    version: Mapped[int] = mapped_column(Integer, default=1)
    synthesized_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class FeedbackLearningJob(Base):
    __tablename__ = "feedback_learning_job"
    __table_args__ = (
        UniqueConstraint("user_id", "scope_key", name="uq_feedback_learning_job_user_scope"),
        Index("ix_feedback_learning_job_status_available", "status", "available_at"),
    )
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("app_user.id", ondelete="CASCADE"), index=True
    )
    scope_key: Mapped[str] = mapped_column(String(240))
    status: Mapped[str] = mapped_column(String(24), default="PENDING")
    profile_version: Mapped[int] = mapped_column(Integer, default=1)
    attempt_count: Mapped[int] = mapped_column(Integer, default=0)
    last_error: Mapped[str | None] = mapped_column(String(500))
    available_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=func.now(), server_default=func.now()
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class GenerationAttempt(Base):
    __tablename__ = "generation_attempt"
    __table_args__ = (
        Index(
            "uq_attempt_active_node",
            "project_uuid",
            "video_node_key",
            unique=True,
            postgresql_where=text(ACTIVE_ATTEMPT_SQL),
            sqlite_where=text(ACTIVE_ATTEMPT_SQL),
        ),
        Index(
            "uq_attempt_active_intent",
            "intent_hash",
            unique=True,
            postgresql_where=text(ACTIVE_ATTEMPT_SQL),
            sqlite_where=text(ACTIVE_ATTEMPT_SQL),
        ),
        Index("ix_generation_attempt_variant_created", "variant_id", "created_at"),
    )
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    variant_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("generation_variant.id", ondelete="CASCADE"), index=True
    )
    project_uuid: Mapped[str | None] = mapped_column(String(64))
    group_node_key: Mapped[str | None] = mapped_column(String(160))
    video_node_key: Mapped[str | None] = mapped_column(String(160))
    intent_hash: Mapped[str | None] = mapped_column(String(64), index=True)
    status: Mapped[AttemptStatus] = enum_column(
        AttemptStatus, default=AttemptStatus.DRAFT, index=True
    )
    state_version: Mapped[int] = mapped_column(Integer, default=1)
    provider: Mapped[str] = mapped_column(String(80), default="libtv", server_default="libtv")
    task_id: Mapped[str | None] = mapped_column(String(160))
    provider_model: Mapped[str | None] = mapped_column(String(160))
    provider_status: Mapped[str | None] = mapped_column(String(40))
    provider_raw_status: Mapped[str | None] = mapped_column(String(120))
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_polled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    output_url: Mapped[str | None] = mapped_column(Text)
    local_output_path: Mapped[str | None] = mapped_column(String(500))
    credits_consumed: Mapped[int | None] = mapped_column(Integer)
    error_message: Mapped[str | None] = mapped_column(Text)
    provider_error_details_json: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    provider_error_retryable: Mapped[bool | None] = mapped_column(Boolean)
    raw_response_json: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    launch_started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    process_started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    runner_host_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("runner_host.id"))
    runner_execution_backend: Mapped[str | None] = mapped_column(String(64))
    runner_execution_ref: Mapped[str | None] = mapped_column(String(255))
    runner_process_id: Mapped[int | None] = mapped_column(Integer)
    runner_process_started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    runner_process_nonce: Mapped[str | None] = mapped_column(String(64))
    runner_executable_hash: Mapped[str | None] = mapped_column(String(64))
    runner_command_hash: Mapped[str | None] = mapped_column(String(64))
    stdout_ref: Mapped[str | None] = mapped_column(String(500))
    stderr_ref: Mapped[str | None] = mapped_column(String(500))
    terminal_result_ref: Mapped[str | None] = mapped_column(String(500))
    exit_code: Mapped[int | None] = mapped_column(Integer)
    last_error_code: Mapped[str | None] = mapped_column(String(80))
    charge_status: Mapped[ChargeStatus] = enum_column(
        ChargeStatus, default=ChargeStatus.NOT_CHARGED
    )
    billing_source: Mapped[BillingSource | None] = enum_column(BillingSource)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    variant: Mapped[GenerationVariant] = relationship(back_populates="attempts")
    command: Mapped["GenerationCommand | None"] = relationship(
        back_populates="attempt", uselist=False
    )


class GenerationCommand(Base):
    __tablename__ = "generation_command"
    __table_args__ = (Index("ix_generation_command_status_created", "status", "created_at"),)
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    attempt_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("generation_attempt.id", ondelete="CASCADE"), unique=True
    )
    status: Mapped[CommandStatus] = enum_column(
        CommandStatus, default=CommandStatus.READY, index=True
    )
    protocol_version: Mapped[int] = mapped_column(Integer, default=1)
    claim_owner: Mapped[str | None] = mapped_column(String(120))
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    launch_started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    process_started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    command_manifest_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    attempt: Mapped[GenerationAttempt] = relationship(back_populates="command")


class MaterializationSaga(Base):
    __tablename__ = "materialization_saga"
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    parent_task_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("parent_task.id", ondelete="CASCADE"), unique=True
    )
    project_uuid: Mapped[str] = mapped_column(String(64))
    status: Mapped[SagaStatus] = enum_column(SagaStatus, default=SagaStatus.PENDING)
    state_version: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class MaterializationOperation(Base):
    __tablename__ = "materialization_operation"
    __table_args__ = (
        UniqueConstraint("saga_id", "step_type", name="uq_materialization_saga_step"),
    )
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    saga_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("materialization_saga.id", ondelete="CASCADE"), index=True
    )
    step_type: Mapped[str] = mapped_column(String(80))
    expected_remote_identity: Mapped[str] = mapped_column(String(255))
    remote_node_key: Mapped[str | None] = mapped_column(String(160))
    status: Mapped[OperationStatus] = enum_column(OperationStatus, default=OperationStatus.PENDING)
    attempt_count: Mapped[int] = mapped_column(Integer, default=0)
    stdout_ref: Mapped[str | None] = mapped_column(String(500))
    stderr_ref: Mapped[str | None] = mapped_column(String(500))
    remote_snapshot_json: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error_code: Mapped[str | None] = mapped_column(String(80))


class PointsReservation(Base):
    __tablename__ = "points_reservation"
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("app_user.id", ondelete="RESTRICT"), index=True
    )
    business_date: Mapped[date] = mapped_column(Date, index=True)
    attempt_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("generation_attempt.id", ondelete="RESTRICT"), unique=True
    )
    estimated_points: Mapped[int] = mapped_column(Integer)
    actual_points: Mapped[int | None] = mapped_column(Integer)
    charge_status: Mapped[ChargeStatus] = enum_column(
        ChargeStatus, default=ChargeStatus.NOT_CHARGED
    )
    billing_source: Mapped[BillingSource | None] = enum_column(BillingSource)
    status: Mapped[ReservationStatus] = enum_column(
        ReservationStatus, default=ReservationStatus.RESERVED
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    settled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class PointsLedger(Base):
    __tablename__ = "points_ledger"
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("app_user.id", ondelete="RESTRICT"), index=True
    )
    business_date: Mapped[date] = mapped_column(Date, index=True)
    attempt_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("generation_attempt.id"))
    entry_type: Mapped[LedgerEntryType] = enum_column(LedgerEntryType)
    points: Mapped[int] = mapped_column(Integer)
    reason: Mapped[str] = mapped_column(String(255))
    operator_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("app_user.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class UserDailyPointsSummary(Base):
    __tablename__ = "user_daily_points_summary"
    __table_args__ = (UniqueConstraint("user_id", "business_date", name="uq_user_points_date"),)
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("app_user.id", ondelete="RESTRICT"))
    business_date: Mapped[date] = mapped_column(Date)
    consumed_points: Mapped[int] = mapped_column(Integer, default=0)
    reserved_points: Mapped[int] = mapped_column(Integer, default=0)
    uncertain_points: Mapped[int] = mapped_column(Integer, default=0)
    state_version: Mapped[int] = mapped_column(Integer, default=1)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class DownloadArtifact(Base):
    __tablename__ = "download_artifact"
    __table_args__ = (
        UniqueConstraint("attempt_id", "revision", name="uq_download_attempt_revision"),
    )
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    attempt_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("generation_attempt.id", ondelete="CASCADE"), index=True
    )
    status: Mapped[DownloadStatus] = enum_column(DownloadStatus, default=DownloadStatus.NOT_READY)
    source_url_hash: Mapped[str | None] = mapped_column(String(64))
    object_key: Mapped[str | None] = mapped_column(String(500))
    sha256: Mapped[str | None] = mapped_column(String(64))
    size_bytes: Mapped[int | None] = mapped_column(BigInteger)
    duration_seconds: Mapped[float | None] = mapped_column(Float)
    width: Mapped[int | None] = mapped_column(Integer)
    height: Mapped[int | None] = mapped_column(Integer)
    has_audio: Mapped[bool | None] = mapped_column(Boolean)
    source_type: Mapped[str] = mapped_column(String(40), default="GENERATION")
    revision: Mapped[int] = mapped_column(Integer, default=1)
    deletion_pending_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class ValidationResult(Base):
    __tablename__ = "validation_result"
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    attempt_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("generation_attempt.id", ondelete="CASCADE"), index=True
    )
    status: Mapped[ValidationStatus] = enum_column(ValidationStatus)
    coverage: Mapped[str] = mapped_column(String(40), default="TECHNICAL")
    rule_version: Mapped[str] = mapped_column(String(40))
    model_version: Mapped[str | None] = mapped_column(String(80))
    issue_codes_json: Mapped[list[str]] = mapped_column(JSON, default=list)
    evidence_object_keys_json: Mapped[list[str]] = mapped_column(JSON, default=list)
    summary: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ApiIdempotencyRecord(Base):
    __tablename__ = "api_idempotency_record"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id", "operation_type", "idempotency_key", name="uq_idempotency_scope_key"
        ),
    )
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[str] = mapped_column(String(80))
    operation_type: Mapped[str] = mapped_column(String(80))
    idempotency_key: Mapped[str] = mapped_column(String(200))
    payload_hash: Mapped[str] = mapped_column(String(64))
    response_status: Mapped[int] = mapped_column(Integer)
    response_body_json: Mapped[dict[str, Any]] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class AuditEvent(Base):
    __tablename__ = "audit_event"
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    actor_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("app_user.id"))
    action: Mapped[str] = mapped_column(String(100))
    entity_type: Mapped[str] = mapped_column(String(80))
    entity_id: Mapped[str] = mapped_column(String(160))
    from_state: Mapped[str | None] = mapped_column(String(80))
    to_state: Mapped[str | None] = mapped_column(String(80))
    reason: Mapped[str | None] = mapped_column(String(255))
    correlation_id: Mapped[str] = mapped_column(String(80), index=True)
    evidence_refs_json: Mapped[list[str]] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class OutboxEvent(Base):
    __tablename__ = "outbox_event"
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    aggregate_type: Mapped[str] = mapped_column(String(80))
    aggregate_id: Mapped[str] = mapped_column(String(160))
    event_type: Mapped[str] = mapped_column(String(100))
    payload_json: Mapped[dict[str, Any]] = mapped_column(JSON)
    status: Mapped[OutboxStatus] = enum_column(
        OutboxStatus, default=OutboxStatus.PENDING, index=True
    )
    attempt_count: Mapped[int] = mapped_column(Integer, default=0)
    next_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class SubjectElementJob(Base):
    """Durable creation state for a reusable Kling subject element."""

    __tablename__ = "subject_element_job"
    __table_args__ = (
        UniqueConstraint("parent_task_id", name="uq_subject_element_job_task"),
        UniqueConstraint("external_task_id", name="uq_subject_element_job_external"),
        Index("ix_subject_element_job_recovery", "status", "next_attempt_at"),
    )
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    parent_task_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("parent_task.id", ondelete="CASCADE"), index=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("app_user.id", ondelete="CASCADE"), index=True
    )
    external_task_id: Mapped[str] = mapped_column(String(160))
    provider_task_id: Mapped[str | None] = mapped_column(String(160), index=True)
    element_id: Mapped[str | None] = mapped_column(String(160), index=True)
    name: Mapped[str] = mapped_column(String(20))
    description: Mapped[str] = mapped_column(String(100))
    status: Mapped[str] = mapped_column(String(24), default="PENDING", index=True)
    attempt_count: Mapped[int] = mapped_column(Integer, default=0)
    next_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error_code: Mapped[str | None] = mapped_column(String(80))
    last_error_message: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class ImageGenerationBatch(Base):
    """A user-owned, idempotent collection of paid WaveSpeed predictions."""

    __tablename__ = "image_generation_batch"
    __table_args__ = (
        UniqueConstraint("user_id", "idempotency_key", name="uq_image_batch_user_idempotency"),
        Index("ix_image_batch_user_created", "user_id", "created_at"),
    )
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("app_user.id", ondelete="CASCADE"), index=True
    )
    client_batch_id: Mapped[str] = mapped_column(String(160))
    idempotency_key: Mapped[str] = mapped_column(String(200))
    request_hash: Mapped[str] = mapped_column(String(64))
    name: Mapped[str] = mapped_column(String(160))
    provider: Mapped[str] = mapped_column(String(32))
    status: Mapped[str] = mapped_column(String(32), default="CREATED", index=True)
    expected_generation_count: Mapped[int] = mapped_column(Integer)
    paid_submission_consent_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    request_json: Mapped[dict[str, Any]] = mapped_column(JSON)
    error_json: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    items: Mapped[list["ImageGenerationItem"]] = relationship(
        back_populates="batch",
        cascade="all, delete-orphan",
        lazy="selectin",
        order_by="ImageGenerationItem.order_no",
    )


class ImageQuotaReservation(Base):
    __tablename__ = "image_quota_reservation"
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    batch_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("image_generation_batch.id", ondelete="RESTRICT"), unique=True, index=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("app_user.id", ondelete="RESTRICT"), index=True
    )
    business_date: Mapped[date] = mapped_column(Date, index=True)
    estimated_images: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(24), default="RESERVED", index=True)
    unknown_reason: Mapped[str | None] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    settled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ImageGenerationItem(Base):
    __tablename__ = "image_generation_item"
    __table_args__ = (
        UniqueConstraint("batch_id", "order_no", name="uq_image_item_batch_order"),
        Index("ix_image_item_provider_task", "provider_task_id"),
    )
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    batch_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("image_generation_batch.id", ondelete="CASCADE"), index=True
    )
    order_no: Mapped[int] = mapped_column(Integer)
    client_task_id: Mapped[str] = mapped_column(String(160))
    outfit_id: Mapped[str] = mapped_column(String(160))
    outfit_name: Mapped[str] = mapped_column(String(160))
    sku: Mapped[str] = mapped_column(String(160), default="")
    kind: Mapped[str] = mapped_column(String(24))
    view: Mapped[str] = mapped_column(String(24))
    label: Mapped[str] = mapped_column(String(160))
    prompt: Mapped[str] = mapped_column(Text)
    model_id: Mapped[str] = mapped_column(String(160))
    status: Mapped[str] = mapped_column(String(32), default="PENDING", index=True)
    provider_task_id: Mapped[str | None] = mapped_column(String(160))
    provider_result_url: Mapped[str | None] = mapped_column(Text)
    request_json: Mapped[dict[str, Any]] = mapped_column(JSON)
    raw_response_json: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    error_json: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_polled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    batch: Mapped[ImageGenerationBatch] = relationship(back_populates="items")
    outputs: Mapped[list["ImageGenerationOutput"]] = relationship(
        back_populates="item",
        cascade="all, delete-orphan",
        lazy="selectin",
        order_by="ImageGenerationOutput.order_no",
    )


class ImageGenerationOutput(Base):
    __tablename__ = "image_generation_output"
    __table_args__ = (UniqueConstraint("item_id", "order_no", name="uq_image_output_item_order"),)
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    item_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("image_generation_item.id", ondelete="CASCADE"), index=True
    )
    order_no: Mapped[int] = mapped_column(Integer)
    remote_url: Mapped[str] = mapped_column(Text)
    object_key: Mapped[str | None] = mapped_column(String(500))
    content_type: Mapped[str | None] = mapped_column(String(80))
    sha256: Mapped[str | None] = mapped_column(String(64))
    size_bytes: Mapped[int | None] = mapped_column(BigInteger)
    qualification_status: Mapped[QualityDecisionStatus] = enum_column(
        QualityDecisionStatus, default=QualityDecisionStatus.PENDING
    )
    quality_gates_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    reviewed_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("app_user.id"))
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    human_review_seconds: Mapped[float | None] = mapped_column(Float)
    review_notes: Mapped[str | None] = mapped_column(String(500))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    item: Mapped[ImageGenerationItem] = relationship(back_populates="outputs")


class VisualFactCache(Base):
    __tablename__ = "visual_fact_cache"
    cache_key: Mapped[str] = mapped_column(String(64), primary_key=True)
    ordered_storyboard_hash: Mapped[str] = mapped_column(String(64), index=True)
    model_version: Mapped[str] = mapped_column(String(80))
    schema_version: Mapped[str] = mapped_column(String(40))
    facts_json: Mapped[dict[str, Any]] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ManualFactRevision(Base):
    __tablename__ = "manual_fact_revision"
    __table_args__ = (
        UniqueConstraint("parent_task_id", "revision", name="uq_manual_fact_task_revision"),
    )
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    parent_task_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("parent_task.id", ondelete="CASCADE")
    )
    base_analysis_hash: Mapped[str] = mapped_column(String(64))
    revision: Mapped[int] = mapped_column(Integer)
    facts_json: Mapped[dict[str, Any]] = mapped_column(JSON)
    operator_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("app_user.id"))
    reason: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class TaskConfirmationVersion(Base):
    __tablename__ = "task_confirmation_version"
    __table_args__ = (
        UniqueConstraint("parent_task_id", "revision", name="uq_confirmation_task_revision"),
    )
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    parent_task_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("parent_task.id", ondelete="CASCADE")
    )
    revision: Mapped[int] = mapped_column(Integer)
    analysis_result_hash: Mapped[str] = mapped_column(String(64))
    stable_prompt_hash: Mapped[str] = mapped_column(String(64))
    dynamic_prompt_hash: Mapped[str] = mapped_column(String(64))
    ordered_storyboard_assets_hash: Mapped[str] = mapped_column(String(64))
    generation_config_hash: Mapped[str] = mapped_column(String(64))
    schema_snapshot_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("model_schema_snapshot.id")
    )
    confirmed_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("app_user.id"))
    confirmed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class GenerationReferenceAsset(Base):
    __tablename__ = "generation_reference_asset"
    __table_args__ = (
        UniqueConstraint("generation_variant_id", "order_no", name="uq_reference_variant_order"),
        UniqueConstraint("generation_variant_id", "asset_id", name="uq_reference_variant_asset"),
    )
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    generation_variant_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("generation_variant.id", ondelete="CASCADE")
    )
    asset_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("asset.id", ondelete="RESTRICT"))
    order_no: Mapped[int] = mapped_column(Integer)
    remote_node_key: Mapped[str | None] = mapped_column(String(160))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class RunnerHost(Base):
    __tablename__ = "runner_host"
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    hostname: Mapped[str] = mapped_column(String(120))
    os_type: Mapped[str] = mapped_column(String(40), default="WINDOWS")
    os_version: Mapped[str] = mapped_column(String(120))
    protocol_version: Mapped[int] = mapped_column(Integer, default=1)
    service_version: Mapped[str] = mapped_column(String(40))
    service_instance_id: Mapped[str] = mapped_column(String(80), unique=True)
    status: Mapped[RunnerHostStatus] = enum_column(
        RunnerHostStatus, default=RunnerHostStatus.ONLINE
    )
    last_heartbeat_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    free_disk_percent: Mapped[float] = mapped_column(Float, default=100.0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class OperationalMetricSample(Base):
    __tablename__ = "operational_metric_sample"
    __table_args__ = (Index("ix_operational_sample_host_time", "runner_host_id", "captured_at"),)
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    runner_host_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("runner_host.id", ondelete="CASCADE"), index=True
    )
    deployment_id: Mapped[str] = mapped_column(String(80), index=True)
    libtv_adapter_mode: Mapped[str] = mapped_column(String(20), index=True)
    captured_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )
    global_slots: Mapped[int] = mapped_column(Integer)
    backlog_count: Mapped[int] = mapped_column(Integer)
    running_count: Mapped[int] = mapped_column(Integer)
    slot_utilization: Mapped[float] = mapped_column(Float)
    orphan_process_count: Mapped[int] = mapped_column(Integer)
    free_disk_percent: Mapped[float] = mapped_column(Float)
    global_paused: Mapped[bool] = mapped_column(Boolean)
    paid_submissions_paused: Mapped[bool] = mapped_column(Boolean)


class RuntimeConfigVersion(Base):
    __tablename__ = "runtime_config_version"
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    version: Mapped[int] = mapped_column(Integer, unique=True)
    config_json: Mapped[dict[str, Any]] = mapped_column(JSON)
    changed_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("app_user.id"))
    change_reason: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    rolled_back_from: Mapped[int | None] = mapped_column(Integer)


class CapacitySlot(Base):
    __tablename__ = "capacity_slot"
    __table_args__ = (
        UniqueConstraint("scope_type", "scope_id", "slot_no", name="uq_capacity_scope_slot"),
    )
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    scope_type: Mapped[str] = mapped_column(String(20))
    scope_id: Mapped[str] = mapped_column(String(80))
    slot_no: Mapped[int] = mapped_column(Integer)
    command_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("generation_command.id"))
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
