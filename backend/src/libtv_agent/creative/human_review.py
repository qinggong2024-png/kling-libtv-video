"""Human feedback contracts, independent of production qualification."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from pydantic.alias_generators import to_camel

SubjectType = Literal["IMAGE_OUTPUT", "VIDEO_VARIANT", "DIRECTOR_CANDIDATE"]
Verdict = Literal["PASS", "REWORK", "FAIL"]
ReasonCode = Literal[
    "FACE", "GARMENT", "REALISM", "SPACE", "LIGHTING", "OTHER",
    "MOTION", "DEFORMATION", "CAMERA",
]
OutputHash = Annotated[str, Field(pattern=r"^[0-9a-fA-F]{64}$")]
IMAGE_REASONS = frozenset({"FACE", "GARMENT", "REALISM", "SPACE", "LIGHTING", "OTHER"})
VIDEO_REASONS = frozenset({"MOTION", "DEFORMATION", "CAMERA", "OTHER"})
REVIEW_SCHEMA = "human-production-review.v1"
EXPORT_SCHEMA = "human-production-review-export.v1"


class ReviewModel(BaseModel):
    model_config = ConfigDict(
        alias_generator=to_camel, populate_by_name=True, serialize_by_alias=True, extra="forbid",
    )


class HumanReviewQuery(ReviewModel):
    subject_type: SubjectType
    subject_id: str = Field(min_length=1, max_length=150)
    task_id: uuid.UUID | None = None

    @field_validator("subject_id")
    @classmethod
    def nonblank_subject(cls, value: str) -> str:
        if not value.strip() or value != value.strip():
            raise ValueError("subjectId must be nonblank and have no surrounding whitespace")
        return value

    @model_validator(mode="after")
    def require_director_task(self) -> HumanReviewQuery:
        if self.subject_type == "DIRECTOR_CANDIDATE" and self.task_id is None:
            raise ValueError("DIRECTOR_CANDIDATE requires taskId")
        return self


class HumanReviewExportQuery(HumanReviewQuery):
    include_synthetic: bool = False


class HumanReviewDecision(ReviewModel):
    verdict: Verdict
    reason_codes: list[ReasonCode] = Field(default_factory=list, max_length=32)
    note: str | None = Field(default=None, max_length=255)

    @field_validator("reason_codes")
    @classmethod
    def normalize_reasons(cls, values: list[ReasonCode]) -> list[ReasonCode]:
        return sorted(set(values))

    @field_validator("note", mode="before")
    @classmethod
    def normalize_note(cls, value: object) -> object:
        return value.strip() or None if isinstance(value, str) else value

    @model_validator(mode="after")
    def validate_decision(self) -> HumanReviewDecision:
        if self.verdict == "PASS" and self.reason_codes:
            raise ValueError("PASS must not contain failure reasons")
        if self.verdict != "PASS" and not self.reason_codes:
            raise ValueError("non-PASS requires reasonCodes")
        if "OTHER" in self.reason_codes and not self.note:
            raise ValueError("OTHER requires note")
        return self

    def validate_media(self, subject_type: SubjectType) -> None:
        video = subject_type == "VIDEO_VARIANT"
        if video and self.verdict == "REWORK":
            raise ValueError("VIDEO_VARIANT does not support REWORK")
        if not set(self.reason_codes) <= (VIDEO_REASONS if video else IMAGE_REASONS):
            raise ValueError("reasonCodes do not match subject media")


class HumanReviewRequest(HumanReviewQuery, HumanReviewDecision):
    review_key: str = Field(min_length=1, max_length=120, pattern=r"^\S(?:.*\S)?$")
    expected_output_hash: OutputHash

    @field_validator("expected_output_hash")
    @classmethod
    def normalize_hash(cls, value: str) -> str:
        return value.lower()

    @model_validator(mode="after")
    def validate_subject_media(self) -> HumanReviewRequest:
        self.validate_media(self.subject_type)
        return self


class HumanReviewSubject(HumanReviewQuery):
    output_hash: OutputHash | None
    synthetic: bool
    package_id: str | None = Field(default=None, max_length=160)
    package_revision: int | None = Field(default=None, ge=1)
    input_hash: OutputHash | None = None
    prompt_hash: OutputHash | None = None


class HumanReviewRecord(HumanReviewDecision):
    id: uuid.UUID
    review_key: str = Field(min_length=1, max_length=120)
    reviewer_id: uuid.UUID
    reviewed_at: datetime
    subject: HumanReviewSubject

    @model_validator(mode="after")
    def validate_record(self) -> HumanReviewRecord:
        self.validate_media(self.subject.subject_type)
        if self.subject.output_hash is None:
            raise ValueError("review requires a persisted output hash")
        if self.reviewed_at.tzinfo is None:
            raise ValueError("reviewedAt requires a timezone")
        return self


class HumanReviewEnvelope(HumanReviewRecord):
    schema_version: Literal["human-production-review.v1"] = REVIEW_SCHEMA
    owner_id: uuid.UUID


class HumanReviewList(ReviewModel):
    subject: HumanReviewSubject
    reviews: list[HumanReviewRecord]


class HumanReviewExport(ReviewModel):
    schema_version: Literal["human-production-review-export.v1"] = EXPORT_SCHEMA
    records: list[HumanReviewRecord]
    excluded_synthetic_count: int = Field(ge=0)
