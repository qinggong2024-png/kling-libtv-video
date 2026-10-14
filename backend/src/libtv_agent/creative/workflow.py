"""CW-1 contracts and deterministic Fake compilation. No media provider is imported."""
from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from libtv_agent.creative.reality_evidence import (
    compile_photographic_cues,
    compile_reality_decisions,
    render_photographic_cues,
)
from libtv_agent.creative.visual_plan import (
    ScriptBeat,
    VisualMoment,
    VisualPlan,
    compile_visual_plan,
    storyboard_keyframes,
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
    view: Literal["front", "back"] = "front"
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
    script_beats: list[dict[str, Any]] | None = Field(default=None, min_length=1, max_length=32)
    frame_purpose: Literal[
        "STATIC_DISPLAY", "MOTION_READY_START", "DISPLAY_KEYFRAME"
    ] = "MOTION_READY_START"
    product_view_evidence: dict[str, str] = Field(default_factory=dict)
    duration_seconds: float = Field(default=12, gt=0, le=120, allow_inf_nan=False)
    video_reference_profile: Literal["flow", "kling"] = "kling"
    verified_video_reference_limit: int | None = Field(default=None, ge=1, le=32)
    reference_reservations: list[dict[str, str]] | None = None
    product_reference_assets: dict[str, dict[str, str]] = Field(default_factory=dict)


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
    visual_plan: dict[str, Any] | None = None
    video_prompt_context: str | None = None
    keyframe_id: str | None = None

    @model_validator(mode="after")
    def validate_scope(self) -> PackageRevision:
        if self.purpose == "FIRST_FRAME" and self.shot_id != "FIRST_FRAME":
            raise ValueError("FIRST_FRAME package must use FIRST_FRAME shot_id")
        if self.purpose == "VIDEO_STORYBOARD" and (
            not self.shot_id.startswith("SHOT_") or not self.shot_id[5:].isdigit()
            or not 1 <= int(self.shot_id[5:]) <= 31
            or self.shot_id != f"SHOT_{int(self.shot_id[5:]):02}"
        ):
            raise ValueError("invalid storyboard materialization slot")
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
            if len(self.shot_ids) != 1 or not (
                self.shot_ids[0].startswith("SHOT_")
                and self.shot_ids[0][5:].isdigit()
                and 1 <= int(self.shot_ids[0][5:]) <= 31
                and self.shot_ids[0] == f"SHOT_{int(self.shot_ids[0][5:]):02}"
            ):
                raise ValueError("authorize exactly one storyboard materialization slot")
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
        "analyze", "retry_analysis", "select_direction", "authorize", "generate", "review",
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
    script_beats: list[dict[str, Any]] | None = Field(default=None, min_length=1, max_length=32)

    @field_validator("script_beats")
    @classmethod
    def validate_script(cls, value: list[dict] | None) -> list[dict] | None:
        if value is None:
            return None
        beats = [ScriptBeat.model_validate(b) for b in value]
        if (
            len({b.beat_id for b in beats}) != len(beats)
            or sum(b.duration_seconds for b in beats) > 120
        ):
            raise ValueError("script beat ids must be unique and total duration at most 120s")
        return [b.model_dump(mode="json") for b in beats]

    @model_validator(mode="after")
    def validate_review_reason(self) -> Command:
        if self.script_beats is not None and self.action != "select_direction":
            raise ValueError("script_beats can only be frozen when selecting a direction")
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
    direction = dict(next(
        value for value in plan["directions"] if value["id"] == plan["selected_direction"]
    ))
    if plan.get("script_beats") is not None:
        first = ScriptBeat.model_validate(plan["script_beats"][0]).moments[0]
        direction.update(scene=first.scene, behavior=first.pose, camera=first.camera)
    user_locks = plan.get("locks", {}).get("user_locks", {})
    for key in ("photo_intent", "operator", "capture_reason", "attention", "body_state"):
        if isinstance(user_locks.get(key), str) and user_locks[key].strip():
            direction[key] = user_locks[key]
    locked_camera = user_locks.get("camera") or user_locks.get("framing")
    if isinstance(locked_camera, str) and locked_camera.strip():
        direction["camera"] = locked_camera
    reality = (
        [dict(item) for item in inherited_reality]
        if inherited_reality is not None else compile_reality_decisions(direction)
    )
    reality = compile_photographic_cues(reality, direction)
    decisions = tuple(item["decision"] for item in reality)
    visible_locks = {
        key: value for key, value in user_locks.items()
        if key not in {"selected_direction", "shot_id"}
    }
    shared = (
        f"FAKE ONLY. Preserve canonical garment SHA {plan['source_hash']}. "
        "Preserve original color, print, exact lettering, silhouette and garment condition; "
        "keep the product readable at the selected framing, no added garment details. "
    )
    if visible_locks:
        shared += f"User locks: {json.dumps(visible_locks, sort_keys=True, ensure_ascii=True)}. "
    structured = plan.get("script_beats") is not None
    prompt = shared
    if not structured:
        prompt += f"{direction['scene']}; {direction['behavior']}; {decisions[0]}. "
    prompt += "\n" + render_photographic_cues(reality)
    if fix:
        prompt += f"\n{fix}"
    visual = compile_visual_plan(plan, direction)
    video_context = prompt
    if structured:
        camera = next(item for item in reality if item["dimension"] == "Camera")
        light = next(item for item in reality if item["dimension"] == "Lighting")
        video_context = (
            shared + f"\nCapture mode: {camera['capture_mode']}.\n"
            + light.get("compiled_cue", "")
        )
    prompt += "\n" + visual.keyframes[0].image_prompt
    if structured:
        prompt += "\n" + _image_reference_roles(plan, supplemental=False)
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
        visual_plan=visual.model_dump(mode="json"), video_prompt_context=video_context,
        keyframe_id="K01" if plan.get("script_beats") is not None else None,
    )


def _image_reference_roles(plan: dict, *, supplemental: bool) -> str:
    views = sorted(plan.get("product_reference_assets", {}))
    roles = ["Reference image 1 is original front garment design."]
    roles.extend(
        f"Reference image {index} is original {view} garment design."
        for index, view in enumerate(views, 2)
    )
    if supplemental:
        roles.append(
            f"Reference image {len(views) + 2} is the approved person/outfit; "
            "use its identity, not its scene, pose or garment-facing direction."
        )
    return " ".join(roles)


def _keyframe_reality(
    inherited: list[dict[str, str]], moment: VisualMoment, user_locks: dict,
) -> list[dict[str, str]]:
    """Retarget a new frame while retaining its parent's frozen rules and capture mode."""
    reality = [dict(item) for item in inherited]
    camera = next(item for item in reality if item["dimension"] == "Camera")
    mode = camera.get("capture_mode", "casual_portrait")
    for key in (
        "compiler_version", "capture_mode", "causal_trigger", "physical_relation",
        "visible_result", "compiled_cue", "unresolved_context",
    ):
        camera.pop(key, None)
    for item in reality:
        if item["dimension"] == "Camera":
            item["decision"] = moment.camera
        elif item["dimension"] == "Human Behavior":
            item["decision"] = "N/A" if mode == "product_only" else moment.pose
        elif item["dimension"] == "Environment":
            item["decision"] = moment.scene
    direction = {
        "camera": moment.camera, "behavior": moment.pose, "scene": moment.scene,
        "photo_intent": mode,
        **{key: user_locks[key] for key in (
            "operator", "capture_reason", "attention", "body_state",
        ) if isinstance(user_locks.get(key), str)},
    }
    return compile_photographic_cues(reality, direction)


def compile_storyboard_package(
    task_id: uuid.UUID,
    plan: dict,
    first_frame_package: dict,
    first_frame_candidate_id: str,
    shot_id: str,
) -> PackageRevision:
    structured = plan.get("script_beats") is not None
    visual = (
        VisualPlan.model_validate(first_frame_package["visual_plan"]) if structured else None
    )
    key_id = storyboard_keyframes(visual).get(shot_id) if structured else "K01"
    if key_id is None or (not structured and shot_id != "SHOT_01"):
        raise ValueError("storyboard slot is not in the frozen visual plan")
    direction = next(
        value for value in plan["directions"] if value["id"] == plan["selected_direction"]
    )
    reality = [dict(item) for item in first_frame_package["reality"]]
    # Reuse the parent's exact locks and photographic instructions, not today's defaults.
    if structured:
        key = next(k for k in visual.keyframes if k.key_id == key_id)
        reality = _keyframe_reality(
            reality, key.moment, plan.get("locks", {}).get("user_locks", {}),
        )
        prompt = (
            first_frame_package["video_prompt_context"]
            + "\n" + render_photographic_cues(reality) + "\n" + key.image_prompt
            + "\n" + _image_reference_roles(plan, supplemental=True)
            + f"\nPreserve selected person/outfit from FIRST_FRAME {first_frame_candidate_id}."
        )
    else:
        prompt = first_frame_package["prompt"] + "\n" + (
            f"Continue selected FIRST_FRAME candidate {first_frame_candidate_id}; "
            f"render {shot_id} as a single storyboard moment in {direction['scene']}; "
            f"{direction['behavior']}; preserve garment locks and do not add garment details."
        )
    decisions = tuple(item["decision"] for item in reality)
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
        visual_plan=first_frame_package.get("visual_plan"),
        video_prompt_context=first_frame_package.get("video_prompt_context"),
        keyframe_id=key_id if structured else None,
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
