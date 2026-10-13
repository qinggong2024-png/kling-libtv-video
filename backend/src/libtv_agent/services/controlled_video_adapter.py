"""Read-only projection from a qualified image into the legacy video payload.

The Provider request and creative video bridge remain the source of truth for
creative identity and lineage.  This adapter only translates that already
compiled contract into ``VideoTaskCreate`` shape.  It never creates a task,
submits a Provider request, reserves quota, or writes state.
"""

from __future__ import annotations

from typing import Literal
from uuid import UUID

from libtv_agent.domain.schemas import VideoTaskCreate
from libtv_agent.services.creative_provider_requests import CreativeVideoProviderRequest
from pydantic import BaseModel, ConfigDict, Field, model_validator

Sha256 = str


class ControlledVideoAdapterRejected(ValueError):
    """Stable service-layer rejection for the read-only legacy payload adapter."""

    def __init__(self, code: str, message: str | None = None) -> None:
        self.code = code
        self.message = message or code
        super().__init__(self.message)


class ControlledVideoPackageLineage(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    package_revision_id: str = Field(min_length=1, max_length=240)
    parent_package_revision_id: str = Field(min_length=1, max_length=240)


class ControlledVideoRevisionLineage(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    revision: int = Field(ge=1)
    parent_revision: int = Field(ge=1)

    @model_validator(mode="after")
    def parent_precedes_revision(self) -> ControlledVideoRevisionLineage:
        if self.parent_revision >= self.revision:
            raise ValueError("parent revision must precede revision")
        return self


class QualifiedVideoImageSource(BaseModel):
    """The one real, already materialized image allowed into this adapter."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    upload_id: UUID
    source_image_output_id: UUID
    source_image_hash: Sha256 = Field(pattern=r"^[0-9a-f]{64}$")
    output_image_hash: Sha256 = Field(pattern=r"^[0-9a-f]{64}$")
    creative_task_id: str = Field(min_length=1, max_length=160)
    shot_id: Literal["SHOT_01"] = "SHOT_01"
    candidate_id: str = Field(min_length=1, max_length=240)
    batch_id: UUID
    item_id: UUID
    package_lineage: ControlledVideoPackageLineage
    revision_lineage: ControlledVideoRevisionLineage
    qualification_status: Literal["QUALIFIED"] = "QUALIFIED"
    qualification_scope: Literal["PRODUCTION", "OFFLINE_SYNTHETIC_ONLY"] = "PRODUCTION"
    synthetic: bool = False

    @model_validator(mode="after")
    def source_and_output_hash_match(self) -> QualifiedVideoImageSource:
        if self.source_image_hash != self.output_image_hash:
            raise ValueError("source image hash must equal output image hash")
        return self


class ControlledVideoTaskInput(BaseModel):
    """Frozen read-only output; ``payload`` is the existing task-create shape."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    payload: VideoTaskCreate
    source_image_output_id: UUID
    source_image_hash: Sha256 = Field(pattern=r"^[0-9a-f]{64}$")
    output_image_hash: Sha256 = Field(pattern=r"^[0-9a-f]{64}$")
    shot_id: Literal["SHOT_01"] = "SHOT_01"
    package_lineage: ControlledVideoPackageLineage
    revision_lineage: ControlledVideoRevisionLineage
    creative_task_id: str = Field(min_length=1, max_length=160)
    provider_submission_allowed: Literal[False] = False


def _reject(code: str, message: str | None = None) -> None:
    raise ControlledVideoAdapterRejected(code, message)


def _storyboard_reference(request: CreativeVideoProviderRequest):
    matches = [
        reference
        for reference in request.references
        if reference.role == "STORYBOARD"
    ]
    if len(matches) != 1:
        _reject("STORYBOARD_REFERENCE_COUNT_INVALID")
    reference = matches[0]
    if reference.source_mapping is None:
        _reject("STORYBOARD_SOURCE_MAPPING_REQUIRED")
    return reference


def _first_frame_reference(request: CreativeVideoProviderRequest):
    matches = [
        reference
        for reference in request.references
        if reference.role == "FIRST_FRAME"
    ]
    if len(matches) != 1:
        _reject("FIRST_FRAME_REFERENCE_COUNT_INVALID")
    reference = matches[0]
    if reference.source_mapping is None:
        _reject("FIRST_FRAME_SOURCE_MAPPING_REQUIRED")
    return reference


def _validate_request_lineage(
    request: CreativeVideoProviderRequest,
    source: QualifiedVideoImageSource,
) -> None:
    if source.shot_id != "SHOT_01":
        _reject("SHOT_ID_INVALID")
    if source.qualification_scope != "PRODUCTION" or source.synthetic is not False:
        _reject("QUALIFICATION_SCOPE_INVALID")
    if source.qualification_status != "QUALIFIED":
        _reject("IMAGE_NOT_QUALIFIED")
    if request.provider_submission_allowed is not False:
        _reject("PROVIDER_SUBMISSION_MUST_REMAIN_DISABLED")
    if request.actual_submitted is not False:
        _reject("PROVIDER_REQUEST_ALREADY_SUBMITTED")
    if request.options.multi_shot is not False:
        _reject("MULTI_SHOT_NOT_ALLOWED")
    if request.shot_id != "SHOT_01" or request.source_mapping.shot_id != "SHOT_01":
        _reject("SHOT_ID_INVALID")
    if request.creative_task_id != source.creative_task_id:
        _reject("CREATIVE_TASK_ID_MISMATCH")

    storyboard = _storyboard_reference(request)
    storyboard_mapping = storyboard.source_mapping
    assert storyboard_mapping is not None
    if storyboard_mapping.shot_id != "SHOT_01":
        _reject("STORYBOARD_SHOT_ID_INVALID")
    if storyboard_mapping.output_id != str(source.source_image_output_id):
        _reject("SOURCE_IMAGE_OUTPUT_ID_MISMATCH")
    if storyboard_mapping.package_revision_id != source.package_lineage.package_revision_id:
        _reject("PACKAGE_REVISION_MISMATCH")
    if storyboard_mapping.candidate_id != source.candidate_id:
        _reject("CANDIDATE_ID_MISMATCH")
    if storyboard_mapping.batch_id != str(source.batch_id):
        _reject("BATCH_ID_MISMATCH")
    if storyboard_mapping.item_id != str(source.item_id):
        _reject("ITEM_ID_MISMATCH")
    if storyboard.sha256 != source.output_image_hash:
        _reject("OUTPUT_HASH_MISMATCH")
    if source.source_image_hash != source.output_image_hash:
        _reject("SOURCE_OUTPUT_HASH_MISMATCH")

    first_frame = _first_frame_reference(request)
    first_mapping = first_frame.source_mapping
    assert first_mapping is not None
    if first_mapping.shot_id != "FIRST_FRAME":
        _reject("FIRST_FRAME_SHOT_ID_INVALID")
    if first_mapping.package_revision_id != source.package_lineage.parent_package_revision_id:
        _reject("PACKAGE_PARENT_MISMATCH")
    if (
        first_mapping.package_revision_id == storyboard_mapping.package_revision_id
        or first_mapping.output_id == storyboard_mapping.output_id
    ):
        _reject("PACKAGE_LINEAGE_COLLISION")

def compile_controlled_video_task_input(
    request: CreativeVideoProviderRequest,
    source: QualifiedVideoImageSource,
    *,
    client_task_id: str | None = None,
    title: str | None = None,
    duration_seconds: int | None = None,
) -> ControlledVideoTaskInput:
    """Compile one qualified image into a legacy ``VideoTaskCreate`` payload.

    This function is deliberately synchronous and side-effect free.  The
    resulting payload remains non-submittable because paid consent is false and
    the returned contract explicitly keeps Provider submission disabled.
    """

    if isinstance(source, (list, tuple, set)):
        _reject("BATCH_INPUT_NOT_ALLOWED")
    _validate_request_lineage(request, source)
    if request.package_revision_id != source.package_lineage.package_revision_id:
        _reject("PACKAGE_REVISION_MISMATCH")
    if request.source_mapping.output_id != str(source.source_image_output_id):
        _reject("REQUEST_SOURCE_OUTPUT_ID_MISMATCH")
    if request.source_mapping.batch_id != str(source.batch_id):
        _reject("REQUEST_BATCH_ID_MISMATCH")
    if request.source_mapping.item_id != str(source.item_id):
        _reject("REQUEST_ITEM_ID_MISMATCH")
    if request.locked_prompt.prompt.strip() == "":
        _reject("LOCKED_PROMPT_REQUIRED")

    payload = VideoTaskCreate(
        client_task_id=client_task_id or request.adapter_parameters.external_task_id,
        title=title or f"Creative video {source.creative_task_id} / {source.shot_id}",
        storyboards=[{"upload_id": source.upload_id, "order": 1}],
        generation_mode="custom",
        custom_prompt=request.locked_prompt.prompt,
        result_count=1,
        duration_seconds=duration_seconds or request.options.duration,
        action_intensity="standard",
        cut_mode="explicit_cuts",
        paid_submission_consent=False,
        source_upload_duration_seconds=0,
    )
    return ControlledVideoTaskInput(
        payload=payload,
        source_image_output_id=source.source_image_output_id,
        source_image_hash=source.source_image_hash,
        output_image_hash=source.output_image_hash,
        package_lineage=source.package_lineage,
        revision_lineage=source.revision_lineage,
        creative_task_id=source.creative_task_id,
    )


compile_controlled_video_task = compile_controlled_video_task_input
