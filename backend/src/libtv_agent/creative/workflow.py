"""CW-1 contracts and deterministic Fake compilation. No media provider is imported."""
from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from libtv_agent.creative.reality_evidence import (
    compile_reality_decisions,
    render_reality_constraints,
)

PIPELINE = ("G0", "D1", "D2", "D3", "D4", "H1", "E1", "E2", "E3")
REALITY = (
    "Camera", "Lighting", "Composition", "Human Behavior", "Environment", "Imperfection",
)
RULESET = "creative-fake.v1"
UNCERTAIN = {"UNKNOWN", "WRITE_UNCERTAIN"}
def digest(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid")


class GroundedClaim(Contract):
    claim_id: str
    value: str
    source_fact_keys: list[str]
    facts_revision: int = Field(ge=1)
    evidence_kind: Literal["OBSERVED_REFERENCE", "USER_CONFIRMED", "LIBRARY_SNAPSHOT",
                           "PROPOSED", "USER_ASSUMED"]
    confidence_basis: str
    unknown_or_assumption: str


class AssetLink(Contract):
    owner_id: uuid.UUID
    object_key: str
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    width: int = Field(gt=0)
    height: int = Field(gt=0)
    source_type: Literal["USER_UPLOAD"] = "USER_UPLOAD"
    role: Literal["PRODUCT"] = "PRODUCT"
    view: Literal["front"] = "front"
    evidence_status: Literal["OBSERVED_REFERENCE"] = "OBSERVED_REFERENCE"
    materialized: bool = True
    revoked: bool = False
    license_status: Literal["UNVERIFIED"] = "UNVERIFIED"
    retention_policy: Literal["PIN_FOR_OFFLINE_TASK"] = "PIN_FOR_OFFLINE_TASK"


class PlanRevision(Contract):
    revision: int = Field(ge=1)
    facts_revision: int = Field(ge=1)
    product_id: uuid.UUID
    source_hash: str
    product_version_id: uuid.UUID
    facts_snapshot_hash: str
    locks: dict[str, Any] = Field(default_factory=dict)
    claims: list[GroundedClaim] = Field(default_factory=list)
    directions: list[dict[str, str]]
    selected_direction: str | None = None
    evidence: Literal["FAKE_NOT_IMAGE_ANALYSIS"] = "FAKE_NOT_IMAGE_ANALYSIS"
    brand_dna: dict[str, Any] | None = None


class PackageRevision(Contract):
    package_id: str
    revision: int
    parent_package_id: str | None = None
    locks_hash: str
    facts_revision: int = Field(ge=1)
    preservation_hash: str
    ruleset: Literal["creative-fake.v1"] = RULESET
    purpose: Literal["FIRST_FRAME", "VIDEO_STORYBOARD"] = "FIRST_FRAME"
    shot_id: str = Field(default="FIRST_FRAME", min_length=1, max_length=40)
    source_first_frame_candidate_id: str | None = None
    prompt: str
    reality: list[dict[str, str]]

    @model_validator(mode="after")
    def validate_scope(self) -> PackageRevision:
        if self.purpose == "FIRST_FRAME" and self.shot_id != "FIRST_FRAME":
            raise ValueError("FIRST_FRAME package must use FIRST_FRAME shot_id")
        if self.purpose == "VIDEO_STORYBOARD" and self.shot_id != "SHOT_01":
            raise ValueError("only SHOT_01 is supported in MVP-2A")
        if self.purpose == "VIDEO_STORYBOARD" and not self.source_first_frame_candidate_id:
            raise ValueError("VIDEO_STORYBOARD package requires selected FIRST_FRAME")
        return self


class Authorization(Contract):
    authorization_id: str
    package_id: str
    locks_hash: str
    scope: Literal["FIRST_FRAME", "VIDEO_STORYBOARD"] = "FIRST_FRAME"
    shot_ids: list[str] = Field(default_factory=lambda: ["FIRST_FRAME"])
    expires_at: datetime
    loop_enabled: bool = False
    max_revisions: int = Field(default=1, ge=0, le=2)
    max_calls: int = Field(ge=1, le=6)
    max_cost_micros: int = Field(ge=0, le=1_000_000)
    currency: Literal["FAKE"] = "FAKE"
    allowed_modules: list[Literal["Scene", "Reality", "Composition"]] = Field(
        default_factory=lambda: ["Reality"]
    )
    parent_authorization_id: str | None = None
    total_task_cap_micros: int | None = Field(default=None, ge=0, le=1_000_000)

    @field_validator("expires_at")
    @classmethod
    def timezone_required(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError("expires_at must include timezone")
        return value

    @model_validator(mode="after")
    def validate_scope(self) -> Authorization:
        if self.scope == "VIDEO_STORYBOARD":
            if self.shot_ids != ["SHOT_01"]:
                raise ValueError("MVP-2A authorization requires shot_ids=['SHOT_01']")
        return self


class StageAttempt(Contract):
    attempt_id: str
    scope: Literal["FIRST_FRAME", "VIDEO_STORYBOARD"] = "FIRST_FRAME"
    shot_id: str = "FIRST_FRAME"
    package_id: str
    authorization_id: str
    input_hash: str
    output_hash: str | None = None
    status: Literal["SUCCEEDED", "UNKNOWN", "WRITE_UNCERTAIN", "RECONCILED_NOT_SUBMITTED"]
    reserved_cost_micros: int = Field(ge=0)
    actual_cost_micros: int | None = None
    synthetic: Literal[True] = True


class Iteration(Contract):
    loop_id: str
    index: int = Field(ge=0, le=2)
    parent_candidate_id: str | None = None
    candidate_id: str
    package_id: str
    changed_modules: list[str]
    stop_reason: str | None = None


class Review(Contract):
    candidate_id: str
    scope: Literal["FIRST_FRAME", "VIDEO_STORYBOARD"] = "FIRST_FRAME"
    shot_id: str = "FIRST_FRAME"
    reviewer_kind: Literal["FAKE_CRITIC", "HUMAN"]
    reviewer_id: uuid.UUID | None = None
    decision: Literal["UNVERIFIED", "QUALIFIED", "REJECTED"]
    qualification_scope: Literal["OFFLINE_SYNTHETIC_ONLY"] = "OFFLINE_SYNTHETIC_ONLY"
    axes: dict[str, str] = Field(default_factory=dict)
    reason: str | None = Field(default=None, min_length=1, max_length=500)


class Selection(Contract):
    purpose: Literal["FIRST_FRAME", "VIDEO_STORYBOARD"] = "FIRST_FRAME"
    shot_id: str = "FIRST_FRAME"
    package_id: str
    candidate_id: str
    batch_id: str
    item_id: str
    output_id: str
    selected_by: uuid.UUID
    order: Literal[1] = 1
    synthetic: Literal[True] = True


class Command(Contract):
    command_key: str = Field(min_length=1, max_length=120)
    expected_version: int = Field(ge=0)
    action: Literal[
        "analyze", "select_direction", "authorize", "generate", "review",
        "select", "revise", "stop", "revoke_asset", "reconcile",
    ]
    direction_id: Literal["A", "B", "C"] | None = None
    authorization: Authorization | None = None
    package_id: str | None = None
    candidate_id: str | None = None
    shot_id: str | None = None
    decision: Literal["QUALIFIED", "REJECTED"] | None = None
    changed_modules: list[Literal["Scene", "Reality", "Composition"]] = Field(
        default_factory=list
    )
    fix: str | None = Field(default=None, min_length=1, max_length=300)
    failure_region: str | None = Field(default=None, min_length=1, max_length=160)
    fake_outcome: Literal["SUCCEEDED", "UNKNOWN", "WRITE_UNCERTAIN"] = "SUCCEEDED"
    reconcile_not_submitted: bool = False
    client_key: str | None = Field(default=None, min_length=1, max_length=120)
    reason: str | None = Field(default=None, min_length=1, max_length=500)
    impact_scope: str | None = Field(default=None, min_length=1, max_length=200)

    @model_validator(mode="after")
    def validate_review_reason(self) -> Command:
        if self.action == "review" and self.decision == "REJECTED":
            normalized = (self.reason or "").strip()
            if not normalized:
                raise ValueError("REJECTED requires a review reason")
            self.reason = normalized
        elif self.action == "review" and self.reason is not None:
            self.reason = self.reason.strip() or None
        return self


def compile_package(
    task_id: uuid.UUID, plan: dict, locks_hash: str, revision: int,
    parent: str | None = None, fix: str | None = None,
    *, inherited_reality: list[dict[str, str]] | None = None,
) -> PackageRevision:
    direction = next(
        value for value in plan["directions"] if value["id"] == plan["selected_direction"]
    )
    reality = (
        [dict(item) for item in inherited_reality]
        if inherited_reality is not None else compile_reality_decisions(direction)
    )
    decisions = tuple(item["decision"] for item in reality)
    prompt = (
        f"FAKE ONLY. Preserve canonical garment SHA {plan['source_hash']}. "
        f"{direction['scene']}; {direction['behavior']}; {decisions[0]}, "
        f"single soft side light, no added garment details. {fix or ''}"
    )
    constraints = render_reality_constraints(reality)
    if constraints:
        prompt += f"\nReality generation constraints (proposed guidance):\n{constraints}"
    preservation = digest({
        "product_version_id": plan["product_version_id"],
        "source_hash": plan["source_hash"],
        "locks_hash": locks_hash,
        "prompt": prompt,
        "reality": decisions,
    })
    return PackageRevision(
        package_id=f"{task_id}:package:{revision}", revision=revision, parent_package_id=parent,
        locks_hash=locks_hash,
        facts_revision=plan["facts_revision"], preservation_hash=preservation, prompt=prompt,
        reality=reality,
    )


def compile_storyboard_package(
    task_id: uuid.UUID,
    plan: dict,
    first_frame_package: dict,
    first_frame_candidate_id: str,
    shot_id: str,
) -> PackageRevision:
    if shot_id != "SHOT_01":
        raise ValueError("only SHOT_01 is supported in MVP-2A")
    direction = next(
        value for value in plan["directions"] if value["id"] == plan["selected_direction"]
    )
    reality = [dict(item) for item in first_frame_package["reality"]]
    decisions = tuple(item["decision"] for item in reality)
    prompt = (
        f"FAKE ONLY. Preserve canonical garment SHA {plan['source_hash']}. "
        f"Continue selected FIRST_FRAME candidate {first_frame_candidate_id}; "
        f"render {shot_id} as a single storyboard moment in {direction['scene']}; "
        f"{direction['behavior']}; preserve garment locks and do not add garment details."
    )
    constraints = render_reality_constraints(reality)
    if constraints:
        prompt += f"\nReality generation constraints (proposed guidance):\n{constraints}"
    return PackageRevision(
        package_id=f"{task_id}:storyboard:{shot_id}:1",
        revision=1,
        parent_package_id=first_frame_package["package_id"],
        locks_hash=first_frame_package["locks_hash"],
        facts_revision=plan["facts_revision"],
        preservation_hash=digest({
            "product_version_id": plan["product_version_id"],
            "source_hash": plan["source_hash"],
            "locks_hash": first_frame_package["locks_hash"],
            "prompt": prompt,
            "reality": decisions,
            "first_frame_candidate_id": first_frame_candidate_id,
            "shot_id": shot_id,
        }),
        purpose="VIDEO_STORYBOARD",
        shot_id=shot_id,
        source_first_frame_candidate_id=first_frame_candidate_id,
        prompt=prompt,
        reality=reality,
    )


def preservation_input(
    plan: dict, locks_hash: str, prompt: str, decisions: tuple[str, ...],
) -> dict:
    return {
        "product_version_id": plan["product_version_id"],
        "source_hash": plan["source_hash"],
        "locks_hash": locks_hash,
        "prompt": prompt,
        "reality": decisions,
    }
