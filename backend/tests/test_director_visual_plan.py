from __future__ import annotations

import json
from copy import deepcopy
from uuid import UUID

import pytest
from libtv_agent.creative.visual_plan import (
    VisualPlanRejected,
    assert_reference_budget,
    assert_visual_inputs,
    assert_visual_plan_current,
    compile_visual_plan,
    compile_visual_video_prompt,
)
from libtv_agent.creative.workflow import compile_package, digest
from libtv_agent.services.controlled_video_adapter import (
    ControlledVideoAdapterRejected,
    compile_controlled_video_task_input,
)
from libtv_agent.services.creative_provider_preflight import (
    CreativeProviderPreflightRejected,
    _assert_capability,
)
from libtv_agent.services.creative_provider_requests import (
    CreativeProviderRequestRejected,
    _visual_package,
)
from pydantic import ValidationError
from test_controlled_video_adapter import _request, _source
from test_creative_provider_preflight import _capability
from test_creative_provider_requests import _compile, _counts, _ready
from test_creative_provider_requests import workflow as workflow  # noqa: F401
from test_reality_evidence import plan


def moment(**updates):
    return {
        "scene": "bookshop", "camera": "eye-level", "framing": "medium",
        "actor_zone": "by the shelf", "garment_view": "front", "pose": "standing",
        "hands": [], "support": ["floor"], "details": ["READ BOOKS"],
        "print_visibility": "clear", **updates,
    }


def beat(identifier="B01", *moments, **updates):
    return {
        "beat_id": identifier, "duration_seconds": 4,
        "action": "hold a natural pose",
        "moments": list(moments or (moment(),)), **updates,
    }


def visual(*beats, **updates):
    current = plan()
    current.update(script_beats=list(beats or (beat(),)), **updates)
    return compile_visual_plan(current, current["directions"][0])


@pytest.mark.parametrize("views", [
    ("side", "front"), ("front", "back"), ("back", "front"),
    ("front", "back", "front"),
])
def test_face_changes_add_locks_inside_one_shot_and_reuse_returning_front(views):
    result = visual(beat(
        "turn", *(moment(garment_view=view) for view in views), action="turn slowly",
    ), product_view_evidence={"side": "b" * 64, "back": "c" * 64})
    assert len(result.shots) == 1
    assert len(result.keyframes) == len(set(views))
    assert len(result.bindings) == len(views)
    assert all(item.role == "product_lock" for item in result.bindings[1:])
    if views[0] == views[-1]:
        assert result.bindings[0].key_id == result.bindings[-1].key_id
    assert result.missing_product_views == ()


def test_similar_actions_and_same_view_share_clear_print_representative():
    result = visual(
        beat("B01", moment(print_visibility="partial"), action="breathe"),
        beat("B02", moment(), action="smile"),
    )
    assert len(result.shots) == len(result.keyframes) == 1
    assert result.keyframes[0].moment.print_visibility == "clear"
    assert len({item.key_id for item in result.bindings}) == 1
    assert result.optimization == "minimum_cover"


def test_clear_end_pose_cannot_replace_different_motion_start():
    result = visual(beat(
        "B01", moment(pose="seated", support=["chair"]),
        moment(pose="standing", support=["floor"]),
        action="stand up",
    ))
    assert len(result.keyframes) == 2
    assert result.keyframes[0].moment.pose == "seated"
    assert result.bindings[1].role == "state_change"


def test_detail_reveal_requires_image_even_without_new_cut():
    result = visual(beat(
        "B01", moment(details=[]), moment(details=["READ BOOKS", "small sleeve logo"]),
        action="release the sleeve",
    ))
    assert len(result.shots) == 1
    assert result.bindings[-1].role == "product_lock"
    # A matching, unobstructed pose can lock both requirements using one image.
    assert len(result.keyframes) == 1
    assert "small sleeve logo" in result.keyframes[0].image_prompt


@pytest.mark.parametrize("change", [
    {"scene": "street"}, {"camera": "new axis"}, {"framing": "print closeup"},
])
def test_scene_camera_or_framing_change_splits_shot_and_never_merges(change):
    result = visual(beat(), beat("B02", moment(**change)))
    assert len(result.shots) == len(result.keyframes) == 2
    assert result.shots[0].shot_id == "S01"
    assert result.shots[1].shot_id == "S02"


def test_new_action_segment_splits_shot_without_forcing_another_image():
    result = visual(beat(), beat("B02", action_segment_change=True))
    assert len(result.shots) == 2 and len(result.keyframes) == 1
    prompt = compile_visual_video_prompt(result, duration_seconds=12, key_slots={"K01": 2})
    assert "S01 0-6s" in prompt and "S02 6-12s" in prompt
    assert prompt.count("@image_2") == 2


def test_script_timing_is_not_divided_by_number_of_images():
    result = visual(
        beat(duration_seconds=2),
        beat("B02", moment(framing="print closeup"), duration_seconds=10),
    )
    prompt = compile_visual_video_prompt(
        result, duration_seconds=12, key_slots={"K01": 1, "K02": 2},
    )
    assert "S01 0-2s" in prompt and "S02 2-12s" in prompt


def test_continuous_beat_windows_remain_separate_without_added_cuts():
    result = visual(beat(duration_seconds=2), beat("B02", duration_seconds=10))
    prompt = compile_visual_video_prompt(result, duration_seconds=12)
    assert len(result.shots) == 1
    assert "B01 0-2s" in prompt and "B02 2-12s" in prompt


def test_hidden_scene_cut_inside_continuous_turn_is_rejected():
    with pytest.raises(VisualPlanRejected, match="SCENE_OR_CAMERA_CHANGE_REQUIRES_BEAT"):
        visual(beat("B01", moment(), moment(scene="street")))


def test_missing_back_source_blocks_instead_of_inventing_plain_back():
    result = visual(beat("B01", moment(), moment(garment_view="back")))
    assert result.missing_product_views == ("back",)
    with pytest.raises(VisualPlanRejected, match="PRODUCT_VIEW_EVIDENCE_REQUIRED"):
        assert_visual_inputs(
            result, {"K01": 1, "K02": 2}, actual_slot_count=3, profile="kling",
        )


@pytest.mark.parametrize("profile, limit", [("flow", 5), ("kling", 7)])
def test_budget_includes_product_character_scene_and_preserves_required_images(profile, limit):
    beats = tuple(beat(f"B{index:02}", moment(scene=f"scene-{index}"))
                  for index in range(limit - 1))
    result = visual(
        *beats, video_reference_profile=profile,
        reference_reservations=[
            {"role": "product", "source_id": "a" * 64},
            {"role": "character", "source_id": "person"},
            {"role": "scene", "source_id": "location"},
        ],
    )
    assert result.budget_exceeded
    assert result.planned_reference_count == limit + 2
    assert len(result.keyframes) == limit - 1
    with pytest.raises(VisualPlanRejected, match="VIDEO_REFERENCE_BUDGET_EXCEEDED"):
        assert_visual_inputs(
            result, {key.key_id: index for index, key in enumerate(result.keyframes, 1)},
            actual_slot_count=limit + 2, profile=profile,
        )
    assert_reference_budget(profile, limit)
    with pytest.raises(VisualPlanRejected, match="VIDEO_REFERENCE_BUDGET_EXCEEDED"):
        assert_reference_budget(profile, limit + 1)


def test_verified_capability_can_only_narrow_project_budget():
    assert_reference_budget("flow", 5, verified_limit=10)
    with pytest.raises(VisualPlanRejected, match="VIDEO_REFERENCE_BUDGET_EXCEEDED"):
        assert_reference_budget("flow", 4, verified_limit=3)
    with pytest.raises(VisualPlanRejected, match="VIDEO_REFERENCE_CAPABILITY_UNKNOWN"):
        assert_reference_budget("kling", 1, verified_limit=0)


@pytest.mark.parametrize("slots, count, code", [
    ({}, 2, "KEYFRAME_BINDINGS_INCOMPLETE"),
    ({"K01": 0}, 2, "KEYFRAME_BINDINGS_INVALID"),
    ({"K01": 3}, 2, "KEYFRAME_BINDINGS_INVALID"),
    ({"K01": True}, 2, "KEYFRAME_BINDINGS_INVALID"),
])
def test_api_binding_validation_uses_actual_reference_slots(slots, count, code):
    with pytest.raises(VisualPlanRejected, match=code):
        assert_visual_inputs(visual(), slots, actual_slot_count=count, profile="kling")


def test_duplicate_binding_slots_and_wrong_model_profile_are_rejected():
    result = visual(beat(), beat("B02", moment(scene="street")))
    with pytest.raises(VisualPlanRejected, match="KEYFRAME_BINDINGS_INVALID"):
        assert_visual_inputs(
            result, {"K01": 1, "K02": 1}, actual_slot_count=3, profile="kling",
        )
    with pytest.raises(VisualPlanRejected, match="VIDEO_REFERENCE_PROFILE_MISMATCH"):
        assert_visual_inputs(
            result, {"K01": 1, "K02": 2}, actual_slot_count=3, profile="flow",
        )


def test_plan_is_frozen_and_recomputed_against_backend_script():
    current = plan()
    current["script_beats"] = [beat()]
    result = compile_visual_plan(current, current["directions"][0])
    with pytest.raises(ValidationError):
        result.keyframes[0].moment.pose = "changed"
    stored = result.model_dump(mode="json")
    stored["bindings"][0]["key_id"] = "K99"
    with pytest.raises(VisualPlanRejected, match="VISUAL_PLAN_STALE"):
        assert_visual_plan_current(current, current["directions"][0], stored)


def test_plain_language_turn_cannot_bypass_product_lock_planning():
    current = plan()
    current["directions"][0]["behavior"] = "turn from side to front"
    result = compile_visual_plan(current, current["directions"][0])
    assert result.unresolved == ("STRUCTURED_SCRIPT_REQUIRED",)
    with pytest.raises(VisualPlanRejected, match="STRUCTURED_SCRIPT_REQUIRED"):
        assert_visual_inputs(result, {"K01": 1}, actual_slot_count=2, profile="kling")


def test_image_prompts_are_static_and_video_has_ordered_motion():
    result = visual(beat(
        "B01", moment(garment_view="side"), moment(), action="turn from side to front",
    ), product_view_evidence={"side": "b" * 64})
    assert "side view" in result.keyframes[0].image_prompt
    assert "front view" in result.keyframes[1].image_prompt
    assert all(
        "One pose and one hand-contact state" in key.image_prompt for key in result.keyframes
    )
    assert result.keyframes[0].purpose == "MOTION_READY_START"
    assert result.keyframes[0].next_action == "turn from side to front"
    assert "Video-ready start" in result.keyframes[0].image_prompt
    assert "just before turn from side to front" in result.keyframes[0].image_prompt
    assert "just before" not in result.keyframes[1].image_prompt
    video = compile_visual_video_prompt(result, duration_seconds=12)
    assert "turn from side to front" in video
    assert "product_lock=K02" in video
    assert "MOTION_READY_START" in video


def test_motion_ready_frame_carries_expression_gaze_and_weight_constraints():
    result = visual(beat(
        "B01",
        moment(
            expression="small amused smile",
            gaze_target="the sweatshirt graphic",
            weight_distribution="left foot grounded, right foot ready to step",
        ),
        action="take the next step",
    ))
    keyframe = result.keyframes[0]
    assert keyframe.purpose == "MOTION_READY_START"
    assert "small amused smile" in keyframe.image_prompt
    assert "gaze the sweatshirt graphic" in keyframe.image_prompt
    assert "left foot grounded, right foot ready to step" in keyframe.image_prompt
    video = compile_visual_video_prompt(result, duration_seconds=4)
    assert "next action: take the next step" in video
    assert "gaze: the sweatshirt graphic" in video


def test_static_display_frame_cannot_be_used_as_video_start():
    result = visual(frame_purpose="STATIC_DISPLAY")
    assert result.keyframes[0].purpose == "STATIC_DISPLAY"
    assert "Static display:" in result.keyframes[0].image_prompt
    with pytest.raises(VisualPlanRejected, match="VIDEO_START_FRAME_NOT_MOTION_READY"):
        assert_visual_inputs(
            result, {"K01": 1}, actual_slot_count=2, profile="kling",
        )


def test_unplanned_historical_packages_are_readable_but_not_submittable():
    with pytest.raises(CreativeProviderRequestRejected, match="VISUAL_PLAN_REQUIRED"):
        _visual_package(current_plan=plan(), package={"prompt": "legacy frozen text"})


def test_preflight_checks_actual_video_prompt_length_instead_of_short_image_prompt():
    request = _request()
    request = request.model_copy(update={
        "model": "kling-3.0-omni",
        "options": request.options.model_copy(update={
            "model": "kling-3.0-omni", "resolution": "720p",
        }),
        "adapter_parameters": request.adapter_parameters.model_copy(update={"prompt": "x" * 3073}),
    })
    with pytest.raises(CreativeProviderPreflightRejected, match="PROMPT_TOO_LONG"):
        _assert_capability(request, _capability(request))


def test_legacy_single_upload_adapter_cannot_drop_director_reference_bindings():
    request = _request()
    request = request.model_copy(update={
        "locked_prompt": request.locked_prompt.model_copy(update={
            "text_contract_json": json.dumps({"package": {
                "visual_plan": visual().model_dump(mode="json"),
            }}),
        }),
    })
    with pytest.raises(
        ControlledVideoAdapterRejected, match="DIRECTOR_REFERENCE_BINDINGS_NOT_PRESERVED",
    ):
        compile_controlled_video_task_input(request, _source())


@pytest.mark.parametrize("kind", ["image", "video"])
@pytest.mark.parametrize("blocked", ["back", "multiple", "overflow", "legacy"])
async def test_real_compiler_rejects_invalid_plan_before_provider_or_state_write(
    workflow, monkeypatch, kind, blocked,
):
    import libtv_agent.services.creative_workflow as service

    original = service.compile_package

    def constrained_package(task_id, current_plan, *args, **kwargs):
        if blocked == "back":
            current_plan["script_beats"] = [beat(
                "B01", moment(), moment(garment_view="back"),
            )]
        elif blocked == "multiple":
            current_plan["script_beats"] = [
                beat(), beat("B02", moment(scene="other scene")),
            ]
        elif blocked == "overflow":
            current_plan["script_beats"] = [
                beat(f"B{index}", moment(scene=f"scene-{index}")) for index in range(7)
            ]
        package = original(task_id, current_plan, *args, **kwargs)
        if blocked == "legacy":
            package = package.model_copy(update={"visual_plan": None})
        return package

    monkeypatch.setattr(service, "compile_package", constrained_package)
    flow, task = await _ready(workflow, kind)
    calls = []

    def forbidden(*args, **kwargs):
        calls.append("submit")
        raise AssertionError("Provider must never be invoked")

    monkeypatch.setattr(
        "libtv_agent.adapters.wavespeed.WaveSpeedAdapter.submit_prediction", forbidden,
    )
    monkeypatch.setattr("libtv_agent.adapters.kling_official_api.KlingOfficialApiAdapter.submit",
                        forbidden)
    codes = {
        "back": "PRODUCT_VIEW_EVIDENCE_REQUIRED",
        "multiple": "VIDEO_SHOT_MODE_MISMATCH",
        "overflow": "VIDEO_REFERENCE_BUDGET_EXCEEDED",
        "legacy": "VISUAL_PLAN_REQUIRED",
    }
    async with flow.app.state.database.session_factory() as session:
        before = await _counts(session)
        if blocked == "multiple" and kind == "image":
            request = await _compile(session, flow, task, kind)
            assert request.shot_id == "FIRST_FRAME"
            assert request.provider_submission_allowed is False
        else:
            with pytest.raises(CreativeProviderRequestRejected, match=codes[blocked]):
                await _compile(session, flow, task, kind)
        assert before == await _counts(session)
    assert calls == []


def test_package_freezes_plan_and_image_context_independently():
    current = plan()
    current["script_beats"] = [beat()]
    before = deepcopy(current)
    package = compile_package(UUID(int=1), current, digest(current["locks"]), 1)
    assert current == before
    assert "One pose and one hand-contact state" in package.prompt
    assert "One pose and one hand-contact state" not in package.video_prompt_context
    assert package.visual_plan["keyframes"][0]["moment"]["garment_view"] == "front"
