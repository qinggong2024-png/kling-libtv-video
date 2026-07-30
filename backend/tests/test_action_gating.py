import pytest
from libtv_agent.services.material_validator import (
    MaterialDescriptor,
    action_context_from_materials,
    validate_materials,
)
from libtv_agent.templates.motion_actions import (
    ACTION_LIBRARY,
    ActionCapability,
    ActionContext,
    compatible_action_ids,
    evaluate_action,
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
            "layer_reveal_return",
            {
                ActionCapability.FREE_HAND,
                ActionCapability.LAYERED_GARMENT,
                ActionCapability.LAYER_BOUNDARIES_CLEAR,
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
    assert {warning.code for warning in result.warnings} == {
        "ACTION_REQUIREMENTS_UNKNOWN"
    }
    assert compatible_action_ids(
        "ootd_walk",
        ("back_reveal",),
        context=result.action_context,
    ) == ()


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
