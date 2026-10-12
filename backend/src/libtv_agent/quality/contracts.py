from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

QualityResult = Literal["PASS", "WARNING", "FAIL", "NOT_EVALUATED"]
ReviewRecommendation = Literal["PASS", "WARNING", "QUALITY_REVIEW", "UNRESOLVED"]
QualityMode = Literal["LIVE", "OFFLINE_SYNTHETIC_ONLY"]


class QualityModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class QualityCheck(QualityModel):
    check_id: str = Field(pattern=r"^[A-Z][A-Z0-9_]{2,79}$")
    result: QualityResult
    evidence: list[str] = Field(default_factory=list, max_length=100)
    observed_value: Any | None = None
    expected_value: Any | None = None
    failure_code: str | None = Field(default=None, pattern=r"^[A-Z][A-Z0-9_]{2,79}$")


class ImageAsset(QualityModel):
    asset_id: str = Field(min_length=1, max_length=160)
    mime_type: str = Field(pattern=r"^image/")
    sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    width: int | None = Field(default=None, ge=1)
    height: int | None = Field(default=None, ge=1)
    size_bytes: int | None = Field(default=None, ge=0)


class VideoArtifact(QualityModel):
    artifact_id: str = Field(min_length=1, max_length=160)
    mime_type: str = Field(pattern=r"^video/")
    sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    size_bytes: int = Field(ge=1)
    duration_seconds: float | None = Field(default=None, gt=0)
    width: int | None = Field(default=None, ge=1)
    height: int | None = Field(default=None, ge=1)
    has_audio: bool | None = None


class ImageQualityContract(QualityModel):
    contract_version: Literal["1.0"] = "1.0"
    asset: ImageAsset
    checks: list[QualityCheck] = Field(min_length=1)
    observed_at: datetime
    adapter: str | None = Field(default=None, min_length=1, max_length=120)
    mode: QualityMode | None = None


class VideoQualityContract(QualityModel):
    contract_version: Literal["1.0"] = "1.0"
    artifact: VideoArtifact
    checks: list[QualityCheck] = Field(min_length=1)
    observed_at: datetime
    adapter: str | None = Field(default=None, min_length=1, max_length=120)
    mode: QualityMode | None = None


class ReviewSubject(QualityModel):
    subject_type: Literal["IMAGE", "VIDEO"]
    subject_id: str = Field(min_length=1, max_length=160)


class QualityReview(QualityModel):
    review_version: Literal["1.0"] = "1.0"
    subject: ReviewSubject
    recommendation: ReviewRecommendation
    evidence_refs: list[str] = Field(min_length=1, max_length=100)
    failure_codes: list[str] = Field(default_factory=list, max_length=100)
    reviewed_at: datetime
    reviewer: str | None = Field(default=None, min_length=1, max_length=120)
    mode: QualityMode | None = None
    notes: str | None = Field(default=None, max_length=2000)


class FailureTaxonomyEntry(QualityModel):
    code: str = Field(pattern=r"^[A-Z][A-Z0-9_]{2,79}$")
    family: Literal["INPUT", "MEDIA", "CONTENT", "CONSISTENCY", "EVIDENCE", "SYSTEM"]
    severity: Literal["INFO", "WARNING", "ERROR", "CRITICAL"]
    description: str = Field(min_length=1, max_length=500)
    retryable: bool = False
    requires_human_review: bool = False
