import pytest
from libtv_agent.services.material_validator import (
    MaterialDescriptor,
    action_context_from_materials,
    validate_materials,
)
from libtv_agent.templates.motion_actions import (
    ACTION_ALIASES,
    ACTION_LIBRARY,
    OOTD_REVIEWED_ACTION_COVERAGE,
    ActionCapability,
    ActionContext,
    MotionAction,
    canonical_action_id,
    compatible_action_ids,
    evaluate_action,
    evaluate_action_with_base,
    render_action_ids,
)
from libtv_agent.templates.video_templates import get_video_template


def material(
    index: int = 1,
    *,
    confirmed: frozenset[ActionCapability] = frozenset(),
    denied: frozenset[ActionCapability] = frozenset(),
) -> MaterialDescriptor:
    return MaterialDescriptor(
        id=f"asset-{index}",
        order=index,
        original_name=f"storyboard-{index}.jpg",
        mime_type="image/jpeg",
        size_bytes=1024,
        sha256=f"{index:064d}",
        width=1080,
        height=1920,
        confirmed_action_capabilities=confirmed,
        denied_action_capabilities=denied,
    )


def test_unknown_context_keeps_only_unconditional_low_risk_actions() -> None:
    selected = compatible_action_ids(
        "ootd_walk",
        (
            "stance_shift",
            "one_step_settle",
            "controlled_walk",
            "print_indicate_release",
            "back_reveal",
            "mirror_phone_hold",
        ),
    )

    assert selected == ("stance_shift",)


@pytest.mark.parametrize(
    ("action_id", "confirmed"),
    [
        ("controlled_walk", {ActionCapability.WALK_DEPTH}),
        (
            "print_indicate_release",
            {ActionCapability.FREE_HAND, ActionCapability.SAFE_HAND_PATH},
        ),
        ("back_reveal", {ActionCapability.BACK_REFERENCE}),
        (
            "front_back_quarter_return",
            {
                ActionCapability.BACK_REFERENCE,
                ActionCapability.OVER_SHOULDER_GAZE_SAFE,
            },
        ),
        (
            "mirror_phone_hold",
            {ActionCapability.MIRROR_SELFIE, ActionCapability.PHONE_HOLD_VISIBLE},
        ),
        (
            "seated_weight_shift",
            {
                ActionCapability.SEATED_POSE,
                ActionCapability.SEAT_VISIBLE,
                ActionCapability.LOWER_BODY_PATH_VISIBLE,
            },
        ),
        ("lean_release", {ActionCapability.SUPPORT_SURFACE}),
        (
            "existing_prop_return",
            {
                ActionCapability.EXISTING_PROP,
                ActionCapability.FREE_HAND,
                ActionCapability.PROP_PICKUP_SAFE,
            },
        ),
        (
            "hair_tuck_release",
            {
                ActionCapability.FREE_HAND,
                ActionCapability.SAFE_HAND_PATH,
                ActionCapability.FACE_VISIBLE,
                ActionCapability.HAIR_REACHABLE,
            },
        ),
        (
            "seated_prop_sip_return",
            {
                ActionCapability.SEATED_POSE,
                ActionCapability.SEAT_VISIBLE,
                ActionCapability.EXISTING_PROP,
                ActionCapability.FREE_HAND,
                ActionCapability.PROP_PICKUP_SAFE,
            },
        ),
        (
            "layer_reveal_return",
            {
                ActionCapability.FREE_HAND,
                ActionCapability.LAYERED_GARMENT,
                ActionCapability.LAYER_BOUNDARIES_CLEAR,
            },
        ),
        (
            "fastener_adjust_release",
            {
                ActionCapability.GARMENT_FASTENER_VISIBLE,
                ActionCapability.FREE_HAND,
                ActionCapability.SAFE_HAND_PATH,
            },
        ),
        (
            "stair_ascend_settle",
            {
                ActionCapability.STAIR_VISIBLE,
                ActionCapability.STAIR_PATH_CLEAR,
                ActionCapability.LOWER_BODY_PATH_VISIBLE,
            },
        ),
        (
            "sit_down_settle",
            {
                ActionCapability.SEAT_VISIBLE,
                ActionCapability.SEAT_APPROACH_CLEAR,
                ActionCapability.LOWER_BODY_PATH_VISIBLE,
            },
        ),
        (
            "companion_gaze_return",
            {
                ActionCapability.COMPANION_PRESENT,
                ActionCapability.FACE_GAZE_ADJUSTABLE,
            },
        ),
    ],
)
def test_machine_capabilities_enable_matching_conditional_action(
    action_id: str,
    confirmed: set[ActionCapability],
) -> None:
    context = ActionContext(confirmed=frozenset(confirmed))

    eligibility = evaluate_action(ACTION_LIBRARY[action_id], context)

    assert eligibility.allowed
    assert not eligibility.missing
    assert not eligibility.denied


def test_reviewed_ootd_actions_are_fully_normalized_into_the_library() -> None:
    assert set(OOTD_REVIEWED_ACTION_COVERAGE) == set(range(296, 361))
    assert set(OOTD_REVIEWED_ACTION_COVERAGE.values()) <= set(ACTION_LIBRARY)
    assert len(set(OOTD_REVIEWED_ACTION_COVERAGE.values())) == 43
    assert OOTD_REVIEWED_ACTION_COVERAGE[296] == OOTD_REVIEWED_ACTION_COVERAGE[298]
    assert OOTD_REVIEWED_ACTION_COVERAGE[351] == OOTD_REVIEWED_ACTION_COVERAGE[359]


def test_legacy_action_aliases_are_not_exposed_as_duplicate_catalog_entries() -> None:
    assert set(ACTION_ALIASES) == {
        "chest_print_pause",
        "eye_contact_neutral",
        "cool_detached_glance",
    }
    assert set(ACTION_ALIASES).isdisjoint(ACTION_LIBRARY)
    assert canonical_action_id("chest_print_pause") == "print_detail_pause"
    assert canonical_action_id("eye_contact_neutral") == "controlled_gaze"


def test_legacy_action_ids_are_normalized_before_compatibility_filtering() -> None:
    assert compatible_action_ids(
        "garment_detail",
        ("chest_print_pause", "print_detail_pause"),
        context=ActionContext(
            confirmed=frozenset({ActionCapability.FRONT_PRINT_VISIBLE})
        ),
    ) == ("print_detail_pause",)


@pytest.mark.parametrize(
    "action_id",
    [
        "fastener_adjust_release",
        "stair_ascend_settle",
        "sit_down_settle",
        "companion_gaze_return",
    ],
)
def test_new_conditional_ootd_actions_are_excluded_when_context_is_unknown(
    action_id: str,
) -> None:
    assert not evaluate_action(ACTION_LIBRARY[action_id]).allowed


def test_denied_capability_excludes_action_even_when_other_requirements_are_confirmed() -> None:
    context = ActionContext(
        confirmed=frozenset({ActionCapability.FREE_HAND}),
        denied=frozenset({ActionCapability.SAFE_HAND_PATH}),
    )

    eligibility = evaluate_action(ACTION_LIBRARY["print_indicate_release"], context)

    assert not eligibility.allowed
    assert eligibility.denied == (ActionCapability.SAFE_HAND_PATH,)


def test_action_context_rejects_contradictory_facts() -> None:
    with pytest.raises(ValueError, match="both confirmed and denied"):
        ActionContext(
            confirmed=frozenset({ActionCapability.BACK_REFERENCE}),
            denied=frozenset({ActionCapability.BACK_REFERENCE}),
        )


def test_material_context_aggregates_only_explicit_capabilities() -> None:
    context = action_context_from_materials(
        [
            material(1, confirmed=frozenset({ActionCapability.FRONT_PRINT_VISIBLE})),
            material(2, confirmed=frozenset({ActionCapability.FREE_HAND})),
        ]
    )

    assert context.confirmed == frozenset(
        {ActionCapability.FRONT_PRINT_VISIBLE, ActionCapability.FREE_HAND}
    )
    assert ActionCapability.BACK_REFERENCE not in context.confirmed
    assert ActionCapability.BACK_REFERENCE not in context.denied


def test_capabilities_from_different_storyboards_do_not_form_false_support() -> None:
    context = action_context_from_materials(
        [
            material(1, confirmed=frozenset({ActionCapability.FREE_HAND})),
            material(2, confirmed=frozenset({ActionCapability.SAFE_HAND_PATH})),
        ]
    )

    eligibility = evaluate_action(ACTION_LIBRARY["print_indicate_release"], context)

    assert not eligibility.allowed
    assert eligibility.missing == (
        ActionCapability.FREE_HAND,
        ActionCapability.SAFE_HAND_PATH,
    )


def test_material_validation_marks_unknown_action_facts_for_visual_check() -> None:
    result = validate_materials(
        [material()],
        template=get_video_template("ootd_walk"),
        variant_count=1,
        action_intensity="standard",
        camera_tempo="standard",
        cut_mode="explicit_cuts",
        requested_action_ids=("back_reveal",),
    )

    assert result.valid
    assert result.vision_check_required
    assert {warning.code for warning in result.warnings} == {"ACTION_REQUIREMENTS_UNKNOWN"}
    assert (
        compatible_action_ids(
            "ootd_walk",
            ("back_reveal",),
            context=result.action_context,
        )
        == ()
    )


def test_material_validation_exposes_confirmed_context_for_filtering() -> None:
    result = validate_materials(
        [
            material(
                confirmed=frozenset(
                    {
                        ActionCapability.MIRROR_SELFIE,
                        ActionCapability.PHONE_HOLD_VISIBLE,
                    }
                )
            )
        ],
        template=get_video_template("ootd_walk"),
        variant_count=1,
        action_intensity="standard",
        camera_tempo="standard",
        cut_mode="explicit_cuts",
        requested_action_ids=("mirror_phone_hold",),
    )

    assert result.valid
    assert not result.vision_check_required
    assert compatible_action_ids(
        "ootd_walk",
        ("mirror_phone_hold",),
        context=result.action_context,
    ) == ("mirror_phone_hold",)


def test_material_capability_conflict_is_a_validation_error() -> None:
    contradictory = material(
        confirmed=frozenset({ActionCapability.SEATED_POSE}),
        denied=frozenset({ActionCapability.SEATED_POSE}),
    )

    result = validate_materials(
        [contradictory],
        template=get_video_template("ootd_walk"),
        variant_count=1,
        action_intensity="standard",
        camera_tempo="standard",
        cut_mode="explicit_cuts",
    )

    assert not result.valid
    assert "ACTION_CAPABILITY_CONFLICT" in {error.code for error in result.errors}


def test_public_action_shape_contains_machine_readable_requirements() -> None:
    public = ACTION_LIBRARY["back_reveal"].to_public_dict()

    assert public["requiredCapabilities"] == ["back_reference"]
    assert "required_capabilities" not in public


def test_brand_action_inherits_general_action_instruction_and_capability_gates() -> None:
    base = ACTION_LIBRARY["controlled_walk"]
    variant = MotionAction(
        id="nerdywave_controlled_walk",
        label="暗黑受控走动",
        category=base.category,
        instruction="保持冷漠直视和明确肩线，让动作更有受控攻击性。",
        purpose="在不改变走动骨架的前提下增加品牌张力。",
        compatible_templates=base.compatible_templates,
        library_scope="brand",
        brand_id="nerdywave",
        base_action_id=base.id,
    )
    library = {base.id: base, variant.id: variant}

    eligibility = evaluate_action_with_base(variant, ActionContext(), library)
    assert eligibility.missing == (ActionCapability.WALK_DEPTH,)

    rendered = render_action_ids(
        "ootd_walk",
        (variant.id,),
        context=ActionContext.from_values(confirmed=(ActionCapability.WALK_DEPTH,)),
        library=library,
    )
    assert base.instruction in rendered
    assert "品牌风格差异" in rendered
    assert variant.instruction in rendered
