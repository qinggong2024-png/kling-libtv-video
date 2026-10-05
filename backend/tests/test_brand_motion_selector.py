from dataclasses import replace

from libtv_agent.services.prompt_compiler import PromptCompileInput, compile_video_plan
from libtv_agent.templates.motion_actions import (
    ACTION_LIBRARY,
    ActionCapability,
    ActionContext,
    action_family,
    select_brand_motion,
)
from libtv_agent.templates.site_style_profiles import get_site_style_profile
from libtv_agent.templates.video_templates import get_video_template


def _all_capabilities() -> ActionContext:
    return ActionContext(confirmed=frozenset(ActionCapability))


def test_brand_motion_selector_chooses_primary_micro_and_style_pools() -> None:
    profile = get_site_style_profile("nerdywave")

    selection = select_brand_motion(
        template_id="ootd_walk",
        primary_motion_pool=profile.primary_motion_pool,
        micro_motion_pool=profile.micro_motion_pool,
        expression_pool=profile.expression_pool,
        camera_pool=profile.camera_pool,
        variant_index=1,
        context=_all_capabilities(),
        library=ACTION_LIBRARY,
    )

    assert selection.primary_action_id == "stance_shift"
    assert selection.micro_action_id == "controlled_gaze"
    assert selection.expression == "neutral confidence"
    assert selection.camera == "slow subtle push-in"
    assert selection.family == action_family("stance_shift")
    assert selection.combo_key == "stance_shift::slow subtle push-in"


def test_brand_motion_selector_applies_recent_primary_and_family_limits() -> None:
    profile = get_site_style_profile("nerdywave")
    recent = (
        "stance_shift",
        "torso_angle_hold",
        "controlled_gaze",
        "one_step_settle",
        "pocket_insert_release",
    )
    selection = select_brand_motion(
        template_id="ootd_walk",
        primary_motion_pool=profile.primary_motion_pool,
        camera_pool=profile.camera_pool,
        variant_index=1,
        recent_selected_action_ids=recent,
        context=_all_capabilities(),
        library=ACTION_LIBRARY,
    )

    assert selection.primary_action_id not in set(recent)
    assert selection.primary_action_id == "lean_release"


def test_profile_public_contract_exposes_absorbed_motion_layer() -> None:
    profile = get_site_style_profile("pagewings")
    public = profile.to_public_dict()

    assert public["motionEnergy"] == "low"
    assert "hair_tuck_release" in public["primaryMotionPool"]
    assert public["expressionPool"]
    assert public["cameraPool"]
    assert public["dedupeRecentCount"] == 5


def test_prompt_compiler_records_selected_motion_layer() -> None:
    profile = get_site_style_profile("geeksoutfit")
    compiled = compile_video_plan(
        PromptCompileInput(
            template=get_video_template("ootd_walk"),
            storyboard_count=1,
            result_count=2,
            action_intensity="standard",
            camera_tempo="standard",
            cut_mode="explicit_cuts",
            variant_index=1,
            site_profile=replace(profile, primary_motion_pool=("stance_shift",)),
            action_context=_all_capabilities(),
            action_library=ACTION_LIBRARY,
        )
    )

    assert "主动作：" in compiled.master_prompt
    assert "微动作：" in compiled.master_prompt
    assert "表情：" in compiled.master_prompt
    assert compiled.variant_seed["selectedActionIds"]
