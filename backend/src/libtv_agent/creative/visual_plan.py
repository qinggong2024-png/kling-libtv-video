"""Backend shot/keyframe planning and prompt constraints; no media or Provider IO."""
from __future__ import annotations

import hashlib
import json
import math
import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class VisualPlanRejected(ValueError):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


class Frozen(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


FramePurpose = Literal["STATIC_DISPLAY", "MOTION_READY_START", "DISPLAY_KEYFRAME"]


class VisualMoment(Frozen):
    scene: str = Field(min_length=1)
    camera: str = Field(min_length=1)
    framing: str = Field(min_length=1)
    actor_zone: str = Field(min_length=1)
    garment_view: Literal["front", "side", "back"]
    pose: str = Field(min_length=1)
    hands: tuple[str, ...] = ()
    support: tuple[str, ...] = ()
    details: tuple[str, ...] = ()
    expression: str = "natural, restrained expression"
    gaze_target: str = "natural scene attention"
    weight_distribution: str = "stable natural weight"
    print_visibility: Literal["clear", "partial", "hidden"] = "clear"


class ScriptBeat(Frozen):
    beat_id: str = Field(min_length=1)
    duration_seconds: float = Field(gt=0, le=120, allow_inf_nan=False)
    action: str = Field(min_length=1, max_length=1000)
    moments: tuple[VisualMoment, ...] = Field(min_length=1, max_length=16)
    cut_before: bool = False
    action_segment_change: bool = False
    # For a continuous action crossing beat boundaries, use the same segment.
    action_segment: str = "continuous"
    moment_offsets_seconds: tuple[float, ...] | None = None

    @model_validator(mode="after")
    def validate_offsets(self) -> ScriptBeat:
        offsets = self.moment_offsets_seconds
        if offsets is not None and (
            len(offsets) != len(self.moments) or not offsets or offsets[0] != 0
            or any(not math.isfinite(t) or not 0 <= t <= self.duration_seconds for t in offsets)
            or any(a >= b for a, b in zip(offsets, offsets[1:], strict=False))
        ):
            raise ValueError("moment offsets must start at zero and increase within the beat")
        return self


class PlannedKeyframe(Frozen):
    key_id: str
    moment: VisualMoment
    purpose: FramePurpose
    next_action: str = Field(min_length=1)
    image_prompt: str


class VisualBinding(Frozen):
    beat_id: str
    moment_index: int = Field(ge=0)
    key_id: str
    role: Literal["start", "product_lock", "state_change"]
    reason: str = ""
    offset_seconds: float | None = None


class PlannedShot(Frozen):
    shot_id: str
    beat_ids: tuple[str, ...]
    duration_seconds: float
    actions: tuple[str, ...]
    split_reasons: tuple[str, ...] = ()


class ReferenceReservation(Frozen):
    role: Literal["product", "character", "scene"]
    source_id: str = Field(min_length=1)


class VisualPlan(Frozen):
    schema_version: Literal["director-visual-plan.v1"] = "director-visual-plan.v1"
    source_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    input_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    beats: tuple[ScriptBeat, ...]
    shots: tuple[PlannedShot, ...]
    keyframes: tuple[PlannedKeyframe, ...]
    bindings: tuple[VisualBinding, ...]
    reference_profile: Literal["flow", "kling"] = "kling"
    reservations: tuple[ReferenceReservation, ...] = ()
    reference_budget: int = Field(ge=1)
    planned_reference_count: int = Field(ge=1)
    frame_purpose: FramePurpose = "MOTION_READY_START"
    budget_exceeded: bool = False
    optimization: Literal["minimum_cover", "bounded_cover"] = "minimum_cover"
    missing_product_views: tuple[str, ...] = ()
    unresolved: tuple[str, ...] = ()


def _hash(value: object) -> str:
    return hashlib.sha256(json.dumps(
        value, sort_keys=True, separators=(",", ":"), allow_nan=False,
    ).encode()).hexdigest()


def reference_limit(profile: str, verified_limit: int | None = None) -> int:
    """Project entrypoint budgets; verified Provider limits can only narrow them."""
    if profile not in {"flow", "kling"}:
        raise VisualPlanRejected("VIDEO_REFERENCE_PROFILE_UNKNOWN")
    limit = {"flow": 5, "kling": 7}[profile]
    if verified_limit is not None:
        if verified_limit < 1:
            raise VisualPlanRejected("VIDEO_REFERENCE_CAPABILITY_UNKNOWN")
        limit = min(limit, verified_limit)
    return limit


def assert_reference_budget(
    profile: str, actual_slot_count: int, *, verified_limit: int | None = None,
) -> None:
    # Count the actual wire slots, including repeats with different temporal roles.
    if actual_slot_count < 1 or actual_slot_count > reference_limit(profile, verified_limit):
        raise VisualPlanRejected("VIDEO_REFERENCE_BUDGET_EXCEEDED")


def _state_key(moment: VisualMoment, *, start: bool) -> tuple:
    return (
        moment.scene, moment.camera, moment.framing, moment.actor_zone, moment.garment_view,
        tuple(sorted(moment.hands)), tuple(sorted(moment.support)),
        moment.pose if start else None,
    )


def _covers(candidate: VisualMoment, target: VisualMoment, *, start: bool) -> bool:
    return (
        _state_key(candidate, start=start) == _state_key(target, start=start)
        and set(target.details) <= set(candidate.details)
        and (target.print_visibility != "clear" or candidate.print_visibility == "clear")
    )


def _image_prompt(
    moment: VisualMoment,
    source_hash: str,
    *,
    purpose: FramePurpose,
    next_action: str,
) -> str:
    if purpose == "MOTION_READY_START":
        frame_instruction = (
            f"Video-ready start: just before {next_action}; leave room to move and "
            "do not start halfway through the action."
        )
    elif purpose == "STATIC_DISPLAY":
        frame_instruction = (
            "Static display: hold a finished readable pose; do not stage a later action."
        )
    else:
        frame_instruction = (
            "Display keyframe: hold this readable moment without implying a new action."
        )
    return (
        f"{frame_instruction} Single still: {moment.garment_view} view; "
        f"{moment.pose}; "
        f"{moment.framing}; {moment.scene}; camera {moment.camera}; "
        f"position {moment.actor_zone}; hands {','.join(moment.hands) or 'unoccupied'}; "
        f"support {','.join(moment.support) or 'unchanged'}; expr {moment.expression}; "
        f"gaze {moment.gaze_target}; weight {moment.weight_distribution}. "
        f"Preserve garment SHA {source_hash}, approved person, outfit and spatial anchors. "
        f"Lock visible details: {','.join(moment.details) or 'visible garment design'}. "
        + ("Keep exact print lettering clear and unobstructed. "
           if moment.print_visibility == "clear" else "")
        + "One pose and one hand-contact state; no before/after montage or turning sequence."
    )


def _default_beats(plan: dict, direction: dict) -> tuple[tuple[ScriptBeat, ...], tuple[str, ...]]:
    """Legacy directions have no timed script. Never infer unobserved product faces."""
    action = direction["behavior"]
    unresolved = ()
    if re.search(
        r"\b(turn|rotate|spin|back|side|close.?up|cut|then)\b|"
        r"转身|转到|转向|背面|侧面|特写|切镜|然后",
        action, re.I,
    ):
        unresolved = ("STRUCTURED_SCRIPT_REQUIRED",)
    moment = VisualMoment(
        scene=direction["scene"], camera=direction.get("camera") or "inherited camera",
        framing="inherited framing", actor_zone="inherited position",
        garment_view="front", pose="approved starting pose",
        expression=direction.get("expression") or "natural, restrained expression",
        gaze_target=direction.get("gaze_target") or "the scene action",
        weight_distribution=direction.get("weight_distribution") or "stable natural weight",
    )
    return (ScriptBeat(
        beat_id="B01", duration_seconds=plan.get("duration_seconds", 12),
        action=action, moments=(moment,),
    ),), unresolved


def compile_visual_plan(plan: dict, direction: dict) -> VisualPlan:
    """Compile backend-authored beats; image count never defines shot count."""
    raw = plan.get("script_beats")
    if raw is None:
        beats, unresolved = _default_beats(plan, direction)
    else:
        if not isinstance(raw, list) or not 1 <= len(raw) <= 32:
            raise VisualPlanRejected("SCRIPT_BEATS_INVALID")
        beats = tuple(ScriptBeat.model_validate(item) for item in raw)
        unresolved = ()
    if len({beat.beat_id for beat in beats}) != len(beats):
        raise VisualPlanRejected("SCRIPT_BEAT_ID_DUPLICATE")
    source_hash = plan["source_hash"]
    frame_purpose = plan.get("frame_purpose", "MOTION_READY_START")
    if frame_purpose not in {"STATIC_DISPLAY", "MOTION_READY_START", "DISPLAY_KEYFRAME"}:
        raise VisualPlanRejected("FRAME_PURPOSE_UNKNOWN")
    profile = plan.get("video_reference_profile", "kling")
    limit = reference_limit(profile, plan.get("verified_video_reference_limit"))
    raw_reservations = plan.get("reference_reservations")
    if raw_reservations is None:
        raw_reservations = [{"role": "product", "source_id": source_hash}]
    reservations = tuple(ReferenceReservation.model_validate(item) for item in raw_reservations)
    if not any(
        item.role == "product" and item.source_id == source_hash for item in reservations
    ):
        raise VisualPlanRejected("CANONICAL_REFERENCE_RESERVATION_REQUIRED")
    # These are evidence refs in the trusted plan, not a front/back invention flag.
    evidence = {"front": source_hash, **plan.get("product_view_evidence", {})}
    if evidence.get("front") != source_hash:
        raise VisualPlanRejected("CANONICAL_PRODUCT_VIEW_MISMATCH")
    for view in sorted({m.garment_view for beat in beats for m in beat.moments} - {"front"}):
        if evidence.get(view) and not any(
            r.role == "product" and r.source_id == evidence[view] for r in reservations
        ):
            reservations += (ReferenceReservation(role="product", source_id=evidence[view]),)
    missing = tuple(sorted({
        moment.garment_view for beat in beats for moment in beat.moments
        if not evidence.get(moment.garment_view)
    }))

    shot_beats: list[list[ScriptBeat]] = []
    shot_reasons: list[tuple[str, ...]] = []
    requirements: list[tuple[ScriptBeat, int, str]] = []
    previous = None
    for beat in beats:
        first = beat.moments[0]
        split = (
            previous is None or beat.cut_before or beat.action_segment_change
            or beat.action_segment != previous.action_segment
            or first.scene != previous.moments[-1].scene
            or first.camera != previous.moments[-1].camera
            or first.framing != previous.moments[-1].framing
        )
        if split:
            shot_beats.append([])
            reasons = ("script_start",) if previous is None else tuple(
                name for name, changed in (
                    ("explicit_cut", beat.cut_before),
                    ("action_segment", beat.action_segment_change
                     or beat.action_segment != previous.action_segment),
                    ("scene", first.scene != previous.moments[-1].scene),
                    ("camera", first.camera != previous.moments[-1].camera),
                    ("framing", first.framing != previous.moments[-1].framing),
                ) if changed
            )
            shot_reasons.append(reasons)
        shot_beats[-1].append(beat)
        requirements.append((beat, 0, "start"))
        for index, moment in enumerate(beat.moments[1:], 1):
            before = beat.moments[index - 1]
            if (
                moment.scene != first.scene or moment.camera != first.camera
                or moment.framing != first.framing
            ):
                # A cut must be represented as another beat, not hidden within a turn.
                raise VisualPlanRejected("SCENE_OR_CAMERA_CHANGE_REQUIRES_BEAT")
            if (
                moment.garment_view != before.garment_view
                or not set(moment.details) <= set(before.details)
                or (moment.print_visibility == "clear" and before.print_visibility != "clear")
            ):
                requirements.append((beat, index, "product_lock"))
            elif _state_key(moment, start=False) != _state_key(before, start=False):
                requirements.append((beat, index, "state_change"))
        previous = beat

    # Equivalent display moments share a representative image. Start-pose checks
    # remain stricter, so a readable end pose cannot replace an incompatible start.
    candidates = list(dict.fromkeys(
        moment for beat in beats for moment in beat.moments
    ))
    candidates.sort(key=lambda moment: (
        moment.print_visibility != "clear", -len(moment.details),
    ))
    coverage = [
        frozenset(
            index for index, (beat, moment_index, role) in enumerate(requirements)
            if _covers(candidate, beat.moments[moment_index], start=role == "start")
        )
        for candidate in candidates
    ]
    uncovered = frozenset(range(len(requirements)))
    best: tuple[int, ...] = ()
    while uncovered:
        candidate_index = max(
            range(len(candidates)), key=lambda index: len(coverage[index] & uncovered),
        )
        best += (candidate_index,)
        uncovered -= coverage[candidate_index]
    visits = 0
    bounded = False

    def search(remaining: frozenset[int], chosen: tuple[int, ...]) -> None:
        nonlocal best, visits, bounded
        visits += 1
        if visits > 10_000:
            bounded = True
            return
        if not remaining:
            if len(chosen) < len(best):
                best = chosen
            return
        if len(chosen) >= len(best):
            return
        pivot = min(
            remaining,
            key=lambda req: sum(req in covered for covered in coverage),
        )
        for index in sorted(
            (index for index, covered in enumerate(coverage) if pivot in covered),
            key=lambda index: -len(coverage[index] & remaining),
        ):
            search(remaining - coverage[index], (*chosen, index))
            if bounded:
                return

    search(frozenset(range(len(requirements))), ())
    selected = [candidates[index] for index in best]
    # Preserve temporal first-use order in the Provider reference manifest.
    selected.sort(key=lambda candidate: next(
        index for index, (beat, moment_index, role) in enumerate(requirements)
        if _covers(candidate, beat.moments[moment_index], start=role == "start")
    ))
    bindings = []
    for beat, index, role in requirements:
        representative = next(
            item for item in selected if _covers(item, beat.moments[index], start=role == "start")
        )
        bindings.append(VisualBinding(
            beat_id=beat.beat_id, moment_index=index,
            key_id=f"K{selected.index(representative) + 1:02}", role=role,
            reason=(
                "motion_start" if role == "start" else
                "new_view_detail_or_clear_print" if role == "product_lock" else
                "contact_or_spatial_state"
            ),
            offset_seconds=(
                beat.moment_offsets_seconds[index] if beat.moment_offsets_seconds is not None
                else 0 if index == 0 else None
            ),
        ))
    start_actions: dict[str, str] = {}
    for (beat, _index, role), binding in zip(requirements, bindings, strict=True):
        if role == "start":
            start_actions.setdefault(binding.key_id, beat.action)
    keyframe_data = []
    for index, moment in enumerate(selected, 1):
        key_id = f"K{index:02}"
        next_action = start_actions.get(key_id, "hold the approved visual moment")
        purpose: FramePurpose = (
            frame_purpose if key_id in start_actions else "DISPLAY_KEYFRAME"
        )
        keyframe_data.append(PlannedKeyframe(
            key_id=key_id,
            moment=moment,
            purpose=purpose,
            next_action=next_action,
            image_prompt=_image_prompt(
                moment, source_hash, purpose=purpose, next_action=next_action,
            ),
        ))
    return VisualPlan(
        source_hash=source_hash,
        input_hash=_hash({
            "beats": [beat.model_dump(mode="json") for beat in beats],
            "product_view_evidence": evidence,
            "reference_profile": profile, "reference_budget": limit,
            "frame_purpose": frame_purpose,
            "reservations": [item.model_dump(mode="json") for item in reservations],
        }),
        beats=beats,
        shots=tuple(PlannedShot(
            shot_id=f"S{index:02}", beat_ids=tuple(beat.beat_id for beat in group),
            duration_seconds=sum(beat.duration_seconds for beat in group),
            actions=tuple(beat.action for beat in group),
            split_reasons=shot_reasons[index - 1],
        ) for index, group in enumerate(shot_beats, 1)),
        keyframes=tuple(keyframe_data),
        bindings=tuple(bindings), missing_product_views=missing, unresolved=unresolved,
        reference_profile=profile, reservations=reservations, reference_budget=limit,
        planned_reference_count=len(selected) + len(reservations),
        frame_purpose=frame_purpose,
        budget_exceeded=len(selected) + len(reservations) > limit,
        optimization="bounded_cover" if bounded else "minimum_cover",
    )


def storyboard_keyframes(visual: VisualPlan) -> dict[str, str]:
    """SHOT_nn identifies a materialization slot, not an editing shot Snn."""
    return {
        f"SHOT_{index:02}": key.key_id
        for index, key in enumerate(visual.keyframes[1:], 1)
    }


def assert_visual_plan_current(plan: dict, direction: dict, stored: dict) -> VisualPlan:
    current = compile_visual_plan(plan, direction)
    if current.model_dump(mode="json") != stored:
        raise VisualPlanRejected("VISUAL_PLAN_STALE")
    return current


def assert_visual_inputs(
    visual: VisualPlan, key_slots: dict[str, int], *, actual_slot_count: int,
    profile: str, verified_limit: int | None = None,
) -> None:
    if visual.unresolved:
        raise VisualPlanRejected(visual.unresolved[0])
    if visual.missing_product_views:
        raise VisualPlanRejected("PRODUCT_VIEW_EVIDENCE_REQUIRED")
    if any(binding.offset_seconds is None for binding in visual.bindings):
        raise VisualPlanRejected("KEYFRAME_TIMING_REQUIRED")
    if profile != visual.reference_profile:
        raise VisualPlanRejected("VIDEO_REFERENCE_PROFILE_MISMATCH")
    if visual.budget_exceeded:
        raise VisualPlanRejected("VIDEO_REFERENCE_BUDGET_EXCEEDED")
    verified_limit = (
        visual.reference_budget if verified_limit is None
        else min(verified_limit, visual.reference_budget)
    )
    assert_reference_budget(profile, actual_slot_count, verified_limit=verified_limit)
    expected = {key.key_id for key in visual.keyframes}
    if set(key_slots) != expected:
        raise VisualPlanRejected("KEYFRAME_BINDINGS_INCOMPLETE")
    by_key = {key.key_id: key for key in visual.keyframes}
    start_bindings = [item for item in visual.bindings if item.role == "start"]
    if not start_bindings:
        raise VisualPlanRejected("VIDEO_START_BINDING_REQUIRED")
    if any(by_key[item.key_id].purpose != "MOTION_READY_START" for item in start_bindings):
        raise VisualPlanRejected("VIDEO_START_FRAME_NOT_MOTION_READY")
    if actual_slot_count < len(expected) + len(visual.reservations):
        raise VisualPlanRejected("REFERENCE_RESERVATIONS_NOT_BOUND")
    if (
        any(type(slot) is not int or not 1 <= slot <= actual_slot_count
            for slot in key_slots.values())
        or len(set(key_slots.values())) != len(key_slots)
    ):
        raise VisualPlanRejected("KEYFRAME_BINDINGS_INVALID")


def compile_visual_video_prompt(
    visual: VisualPlan, *, duration_seconds: float, key_slots: dict[str, int] | None = None,
) -> str:
    """Use script timing and explicit image roles, never image-count timing."""
    if not math.isfinite(duration_seconds) or duration_seconds <= 0:
        raise VisualPlanRejected("VIDEO_DURATION_INVALID")
    if key_slots is not None and set(key_slots) != {key.key_id for key in visual.keyframes}:
        raise VisualPlanRejected("KEYFRAME_BINDINGS_INCOMPLETE")
    total = sum(shot.duration_seconds for shot in visual.shots)
    lines = [
        f"Video timeline {duration_seconds:g}s; {len(visual.shots)} shots. "
        "Reference images are visual locks, not separate cuts. Preserve the approved "
        "person, clothing DNA, exact print lettering, spatial axis and lighting. "
        "Do not invent unseen garment faces, details, extra actions or camera cuts."
    ]
    time = 0.0
    for shot in visual.shots:
        end = time + shot.duration_seconds / total * duration_seconds
        lines.append(f"{shot.shot_id} {time:g}-{end:g}s; one continuous shot.")
        for beat_id in shot.beat_ids:
            beat = next(item for item in visual.beats if item.beat_id == beat_id)
            beat_end = time + beat.duration_seconds / total * duration_seconds
            refs = []
            for binding in visual.bindings:
                if binding.beat_id != beat_id:
                    continue
                label = (
                    f"@image_{key_slots[binding.key_id]}"
                    if key_slots is not None else binding.key_id
                )
                detail = (
                    f"{binding.beat_id}:moment{binding.moment_index}:{binding.role}={label}"
                )
                if binding.offset_seconds is not None:
                    at = time + binding.offset_seconds / total * duration_seconds
                    detail += f" at {at:g}s"
                if binding.role == "start":
                    moment = beat.moments[binding.moment_index]
                    detail += (
                        f" [MOTION_READY_START; next action: {beat.action}; "
                        f"expression: {moment.expression}; "
                        f"gaze: {moment.gaze_target}; "
                        f"weight: {moment.weight_distribution}]"
                    )
                refs.append(detail)
            lines.append(
                f"{beat_id} {time:g}-{beat_end:g}s: {beat.action}. "
                f"Visual locks in temporal order: {', '.join(refs)}."
            )
            time = beat_end
        time = end
    lines.append(
        "Within each continuous turn, lock the revealed front/back print from its "
        "assigned image. Keep print readable during its display moment; a product "
        "reference constrains design and must not replace a scene/action keyframe."
    )
    return "\n".join(lines)
