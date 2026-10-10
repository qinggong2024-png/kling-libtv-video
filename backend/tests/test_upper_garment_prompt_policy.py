from dataclasses import replace

import pytest
from libtv_agent.services.prompt_compiler import PromptCompileInput, compile_video_plan
from libtv_agent.templates.motion_actions import (
    ACTION_LIBRARY,
    ActionCapability,
    ActionContext,
    MotionAction,
    compatible_action_ids,
    select_brand_motion,
)
from libtv_agent.templates.shot_contracts import camera_motion
from libtv_agent.templates.site_style_profiles import (
    get_site_style_profile,
    list_site_style_profiles,
)
from libtv_agent.templates.video_templates import get_video_template
from test_content_catalog_editing import catalog_client as catalog_client
from test_content_catalog_editing import motion_action_payload


def compile_plan(**overrides):
    values = dict(
        template=get_video_template("ootd_walk"),
        storyboard_count=1,
        result_count=1,
        variant_index=1,
        action_intensity="standard",
        camera_tempo="standard",
        cut_mode="explicit_cuts",
    )
    values.update(overrides)
    return compile_video_plan(PromptCompileInput(**values))


@pytest.mark.parametrize("focus", ["lower_garment", "footwear"])
def test_non_upper_actions_and_brand_children_are_not_recommended(focus):
    base = MotionAction(
        "other_product",
        "Other product",
        "detail",
        "Display another product rather than an upper garment.",
        "Other product display.",
        ("ootd_walk",),
        product_focus=focus,
    )
    child = replace(
        base,
        id="brand_child",
        product_focus="upper_garment",
        library_scope="brand",
        brand_id="geeksoutfit",
        base_action_id=base.id,
    )
    library = {base.id: base, child.id: child}
    assert compatible_action_ids("ootd_walk", tuple(library), library=library) == ()


def test_historical_lower_product_ids_cannot_be_relabelled_to_bypass_scope():
    action = replace(ACTION_LIBRARY["stance_shift"], id="footwear_forward_hold")
    assert (
        compatible_action_ids(
            "ootd_walk",
            (action.id,),
            library={action.id: action},
        )
        == ()
    )


@pytest.mark.parametrize(
    "value",
    [
        None,
        "orbit + zoom + whip pan",
        "低机位环绕推进",
        "fast push-in",
        "add wind and smoke",
    ],
)
def test_unapproved_camera_text_falls_back_to_locked(value):
    camera = camera_motion(value)
    assert camera.family == "locked"
    assert camera.max_axes == 0


@pytest.mark.parametrize(
    "value,family",
    [
        ("slow subtle push-in", "push_in"),
        ("gentle pull-back", "pull_back"),
        ("slight tracking", "lateral_follow"),
    ],
)
def test_approved_cameras_have_one_axis(value, family):
    camera = camera_motion(value)
    assert camera.family == family
    assert camera.energy == "low"
    assert camera.max_axes == 1


def test_unknown_material_uses_stable_upper_garment_fallback():
    profile = replace(
        get_site_style_profile("geeksoutfit"),
        preferred_actions=("back_reveal",),
        primary_motion_pool=("back_reveal",),
        camera_pool=("orbit + zoom",),
        micro_motion_pool=("hair_tuck_release",),
    )
    plan = compile_plan(site_profile=profile)
    assert plan.variant_seed["selectedActionIds"] == ["motion_to_rest"]
    assert plan.variant_seed["productScope"] == "upper_garment"
    contract = plan.variant_seed["shotMotionContract"]
    assert contract["camera"]["family"] == "locked"
    assert contract["start_state"] and contract["end_state"] and contract["preserved_facts"]
    assert ACTION_LIBRARY["motion_to_rest"].instruction.rstrip("。；") in plan.master_prompt
    assert "双脚" not in plan.master_prompt
    assert "表演（面部清晰时）：" not in plan.master_prompt
    assert "orbit" not in plan.master_prompt
    assert "背景与光线沿用输入" in plan.master_prompt


def test_conditional_action_supported_in_only_one_shot_is_not_applied_to_all_shots():
    profile = replace(
        get_site_style_profile("guidingcross"),
        preferred_actions=("back_reveal",),
        primary_motion_pool=("back_reveal",),
    )
    plan = compile_plan(
        storyboard_count=2,
        site_profile=profile,
        action_context=ActionContext(
            confirmed=frozenset({ActionCapability.BACK_REFERENCE}),
            evidence_sets=(frozenset({ActionCapability.BACK_REFERENCE}), frozenset()),
        ),
    )
    assert plan.variant_seed["selectedPrimaryActionId"] == "motion_to_rest"


def test_hand_micro_action_is_not_stacked_with_walking():
    selection = select_brand_motion(
        template_id="ootd_walk",
        primary_motion_pool=("controlled_walk",),
        micro_motion_pool=("hem_adjust", "controlled_gaze"),
        context=ActionContext(confirmed=frozenset(ActionCapability)),
    )
    assert selection.primary_action_id == "controlled_walk"
    assert selection.micro_action_id is None


@pytest.mark.parametrize(
    "primary_id",
    ["walk_in_stop", "diagonal_step_turn", "back_walk_settle", "over_shoulder_back"],
)
@pytest.mark.parametrize("brand_child", [False, True])
def test_extended_motion_families_and_brand_children_do_not_stack_gaze(primary_id, brand_child):
    library = dict(ACTION_LIBRARY)
    if brand_child:
        child = replace(
            library[primary_id],
            id="brand_motion_child",
            category="detail",
            library_scope="brand",
            brand_id="geeksoutfit",
            base_action_id=primary_id,
        )
        library[child.id] = child
        primary_id = child.id
    selection = select_brand_motion(
        template_id="ootd_walk",
        primary_motion_pool=(primary_id,),
        micro_motion_pool=("controlled_gaze",),
        context=ActionContext(confirmed=frozenset(ActionCapability)),
        library=library,
    )
    assert selection.primary_action_id == primary_id
    assert selection.micro_action_id is None


def test_primary_and_micro_require_joint_evidence_in_the_same_material():
    selection = select_brand_motion(
        template_id="ootd_walk",
        primary_motion_pool=("pocket_insert_release",),
        micro_motion_pool=("controlled_gaze",),
        context=ActionContext(
            evidence_sets=(
                frozenset(
                    {
                        ActionCapability.POCKET_VISIBLE,
                        ActionCapability.FREE_HAND,
                        ActionCapability.SAFE_HAND_PATH,
                    }
                ),
                frozenset({ActionCapability.FACE_VISIBLE, ActionCapability.FACE_GAZE_ADJUSTABLE}),
            ),
        ),
    )
    assert selection.primary_action_id == "pocket_insert_release"
    assert selection.micro_action_id is None


def test_compression_preserves_selected_action_and_camera_contract():
    profile = replace(
        get_site_style_profile("guidingcross"),
        primary_motion_pool=("hem_adjust",),
        preferred_actions=("hem_adjust",),
        micro_motion_pool=(),
        tone="自然克制的品牌基调" * 30,
        camera_pool=("slow subtle push-in",),
    )
    plan = compile_plan(
        site_profile=profile,
        action_context=ActionContext(confirmed=frozenset(ActionCapability)),
        learning_guidance="保持自然上装展示。" * 60,
        prompt_budget=1100,
    )
    assert len(plan.master_prompt) <= 1100
    assert plan.variant_seed["selectedPrimaryActionId"] == "hem_adjust"
    assert ACTION_LIBRARY["hem_adjust"].instruction.rstrip("。；") in plan.master_prompt
    assert camera_motion("push_in").instruction in plan.master_prompt
    assert "退出：" in plan.master_prompt


def test_upper_garment_detail_and_back_walk_are_evidence_gated():
    context = ActionContext(confirmed=frozenset(ActionCapability))
    assert compatible_action_ids(
        "ootd_walk",
        ("fastener_adjust_release", "back_walk_settle"),
        context=context,
    ) == ("fastener_adjust_release", "back_walk_settle")
    assert (
        compatible_action_ids(
            "ootd_walk",
            ("fastener_adjust_release", "back_walk_settle"),
        )
        == ()
    )
    assert "开合沿用输入状态" in ACTION_LIBRARY["fastener_adjust_release"].instruction
    assert "上装后身" in ACTION_LIBRARY["back_walk_settle"].instruction


@pytest.mark.parametrize("template_id", ["ootd_walk", "garment_detail", "mood_model"])
@pytest.mark.parametrize("variant", range(1, 5))
@pytest.mark.parametrize("confirmed", [False, True])
def test_all_active_brand_prompts_fit_budget_with_locked_upper_scope(
    template_id,
    variant,
    confirmed,
):
    for profile in list_site_style_profiles():
        if profile.status != "active":
            continue
        plan = compile_plan(
            template=get_video_template(template_id),
            storyboard_count=7,
            result_count=4,
            variant_index=variant,
            site_profile=profile,
            action_context=ActionContext(confirmed=frozenset(ActionCapability))
            if confirmed
            else None,
        )
        assert len(plan.master_prompt) <= 3072
        assert len(plan.variant_seed["selectedActionIds"]) <= 2
        assert plan.variant_seed["shotMotionContract"]["camera"]["max_axes"] <= 1
        assert plan.variant_seed["productScope"] == "upper_garment"
        assert (
            plan.variant_seed["selectedActionIds"][0]
            == plan.variant_seed["selectedPrimaryActionId"]
        )


@pytest.mark.parametrize("capabilities", [None, []])
@pytest.mark.asyncio
async def test_empty_conditional_prerequisites_are_rejected(catalog_client, capabilities):
    client, settings = catalog_client
    payload = motion_action_payload()
    payload.update(id="conditional_empty", riskLevel="conditional")
    if capabilities is not None:
        payload["requiredCapabilities"] = capabilities
    response = await client.post(
        "/api/v1/motion-actions",
        headers={"X-User-Id": settings.dev_admin_id},
        json=payload,
    )
    assert response.status_code == 422
    assert "capability prerequisites" in response.json()["detail"]["message"]


@pytest.mark.asyncio
async def test_edit_cannot_clear_existing_capability_gate_even_by_marking_low_risk(catalog_client):
    client, settings = catalog_client
    payload = ACTION_LIBRARY["hem_adjust"].to_public_dict()
    payload.update(requiredCapabilities=[], riskLevel="low")
    response = await client.put(
        "/api/v1/motion-actions/hem_adjust",
        headers={"X-User-Id": settings.dev_admin_id},
        json=payload,
    )
    assert response.status_code == 422
    assert "cannot be removed" in response.json()["detail"]["message"]


@pytest.mark.asyncio
async def test_product_focus_round_trips_and_old_payload_preserves_it(catalog_client):
    client, settings = catalog_client
    headers = {"X-User-Id": settings.dev_admin_id}
    payload = motion_action_payload()
    payload["productFocus"] = "footwear"
    created = await client.post("/api/v1/motion-actions", headers=headers, json=payload)
    assert created.status_code == 201
    assert created.json()["productFocus"] == "footwear"
    updated = await client.put(
        f"/api/v1/motion-actions/{payload['id']}",
        headers=headers,
        json=motion_action_payload(),
    )
    assert updated.status_code == 200
    assert updated.json()["productFocus"] == "footwear"
    refreshed = await client.get("/api/v1/motion-actions", headers=headers)
    persisted = next(item for item in refreshed.json() if item["id"] == payload["id"])
    assert persisted["productFocus"] == "footwear"
