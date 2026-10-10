from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass

from libtv_agent.templates.motion_actions import (
    ACTION_LIBRARY,
    ActionCapability,
    ActionContext,
    MotionAction,
    canonical_action_id,
    normalize_action_ids,
    render_action_ids,
    select_brand_motion,
)
from libtv_agent.templates.shot_contracts import camera_motion, shot_motion_contract
from libtv_agent.templates.site_style_profiles import SiteStyleProfile
from libtv_agent.templates.video_templates import (
    ActionIntensity,
    CameraTempo,
    CutMode,
    VideoTemplate,
)


@dataclass(frozen=True)
class PromptCompileInput:
    template: VideoTemplate
    storyboard_count: int
    result_count: int
    action_intensity: ActionIntensity
    camera_tempo: CameraTempo
    cut_mode: CutMode
    variant_index: int
    duration_seconds: int | None = None
    site_profile: SiteStyleProfile | None = None
    action_context: ActionContext | None = None
    action_library: Mapping[str, MotionAction] | None = None
    learning_guidance: str = ""
    learning_preferred_action_ids: tuple[str, ...] = ()
    learning_avoided_action_ids: tuple[str, ...] = ()
    learning_profile_version: int | None = None
    learning_evidence_count: int = 0
    recent_selected_action_ids: tuple[str, ...] = ()
    recent_motion_combinations: tuple[str, ...] = ()
    prompt_budget: int = 3072


@dataclass(frozen=True)
class ShotInstruction:
    order: int
    start_seconds: float
    end_seconds: float
    instruction: str


@dataclass(frozen=True)
class CompiledVideoPlan:
    template_id: str
    template_version: str
    master_prompt: str
    shot_instructions: tuple[ShotInstruction, ...]
    invariants: tuple[str, ...]
    negative_prompt: str
    variant_seed: dict[str, object]
    site_profile_id: str | None = None
    site_profile_version: str | None = None


_MAX_KLING_PROMPT_CHARS = 3072
_NEGATIVE_PROFILE_PREFIXES = (
    "避免",
    "不得",
    "不要",
    "不用",
    "不使用",
    "不做",
    "不呈现",
    "不新增",
    "不凭空",
    "不能",
    "无意义",
)

_VARIANT_MODIFIERS: tuple[tuple[str, str, str], ...] = (
    (
        "模板主动作完整执行一次，结束时回到对应输入分镜支持的稳定姿态",
        "保持站点表演基调，视线稳定",
        "自然呼吸感",
    ),
    (
        "把模板主动作拆成两个克制的小幅阶段，结束时保持对应输入分镜支持的稳定姿态",
        "在站点表演基调内更克制，短暂离镜后回看",
        "稳定lookbook构图",
    ),
    (
        "模板主动作中加入一次短暂停顿，结束时放松定姿",
        "在站点表演基调内增加一次自然表情变化",
        "近距离朋友视角",
    ),
    (
        "模板主动作完成后回到起始稳定姿态，结束时克制定姿",
        "在站点表演基调内更冷静，视线坚定",
        "简洁克制的编辑感",
    ),
)


def _cut_instruction(cut_mode: CutMode) -> str:
    if cut_mode == "explicit_cuts":
        return "按照输入分镜顺序允许明确、干净的切镜，不强制连接成长镜头"
    return "优先在可行时保持连续运动；画面条件不兼容时使用干净切镜"


def _shot_rule(template_id: str, order: int, total: int) -> str:
    if total == 1:
        return "建立完整上装视图，保持商品区域清晰并稳定结束"
    if order == 1:
        return "建立输入中可见的上装与人物关系"
    if order == total:
        return "回到输入支持的上装清晰画面并稳定结束"
    return {
        "garment_detail": "清晰展示输入中已有的上装纹理、印花或领袖细节",
        "mood_model": "保留既有环境关系，上装始终是可辨认的主体",
    }.get(template_id, "清晰展示输入中已有的上装肩线、衣摆和廓形")


def _partition_profile_text(value: str) -> tuple[str, tuple[str, ...]]:
    """Separate standalone prohibitions from positive profile guidance."""

    segments = re.split(
        rf"；|，(?=(?:{'|'.join(_NEGATIVE_PROFILE_PREFIXES)}))",
        value,
    )
    positive: list[str] = []
    negative: list[str] = []
    for segment in segments:
        clause = segment.strip("。；， ")
        if not clause:
            continue
        if clause.startswith(_NEGATIVE_PROFILE_PREFIXES):
            negative.append(clause)
        else:
            positive.append(clause)
    if not positive:
        rendered = ""
    elif len(positive) == 1:
        rendered = positive[0]
    else:
        rendered = f"{positive[0]}；补充：{'；'.join(positive[1:])}"
    return rendered, tuple(negative)


def _style_instruction(
    profile: SiteStyleProfile | None,
    template_id: str,
    action_context: ActionContext | None,
    action_library: Mapping[str, MotionAction] | None,
    learning_preferred_action_ids: tuple[str, ...],
    learning_avoided_action_ids: tuple[str, ...],
    *,
    variant_index: int,
    recent_selected_action_ids: tuple[str, ...],
    recent_motion_combinations: tuple[str, ...],
) -> tuple[str, tuple[str, ...], tuple[str, ...], dict[str, object]]:
    if profile is None:
        return (
            "自然日常，上装展示优先",
            ("motion_to_rest",),
            (),
            {
                "selectedPrimaryActionId": "motion_to_rest",
                "cameraFamily": "locked",
            },
        )
    base_action_ids = normalize_action_ids(
        (
            *profile.primary_motion_pool,
            *profile.preferred_actions,
        )
        if profile.primary_motion_pool
        else profile.preferred_actions
    )
    allowed = set(base_action_ids)
    preferred = tuple(
        canonical_action_id(action_id)
        for action_id in learning_preferred_action_ids
        if canonical_action_id(action_id) in allowed
    )
    avoided = {
        canonical_action_id(action_id)
        for action_id in learning_avoided_action_ids
        if canonical_action_id(action_id) in allowed
    }
    ordered_action_ids = tuple(
        dict.fromkeys(
            (
                *preferred,
                *(action_id for action_id in base_action_ids if action_id not in avoided),
            )
        )
    )
    selection = select_brand_motion(
        template_id=template_id,
        primary_motion_pool=ordered_action_ids,
        micro_motion_pool=profile.micro_motion_pool,
        expression_pool=profile.expression_pool,
        camera_pool=tuple(
            dict.fromkeys(camera_motion(candidate).family for candidate in profile.camera_pool)
        ),
        variant_index=variant_index,
        recent_selected_action_ids=recent_selected_action_ids,
        recent_motion_combinations=recent_motion_combinations,
        dedupe_recent_count=profile.dedupe_recent_count,
        dedupe_combo_window=profile.dedupe_combo_window,
        dedupe_family_window=profile.dedupe_family_window,
        dedupe_family_limit=profile.dedupe_family_limit,
        context=action_context,
        library=action_library,
    )
    selected_action_ids = selection.selected_action_ids or ("motion_to_rest",)
    motion_metadata: dict[str, object] = {
        key: value
        for key, value in (
            ("selectedPrimaryActionId", selection.primary_action_id),
            ("selectedMicroActionId", selection.micro_action_id),
            ("selectedMotionFamily", selection.family),
            ("selectedMotionCombination", selection.combo_key),
        )
        if value
    }
    motion_metadata["selectedPrimaryActionId"] = selection.primary_action_id or "motion_to_rest"
    motion_metadata["cameraFamily"] = selection.camera or "locked"
    expression_allowed = (action_context or ActionContext()).supports(
        (
            ActionCapability.FACE_VISIBLE,
            ActionCapability.FACE_GAZE_ADJUSTABLE,
        )
    )
    selected_layer = "；".join(
        part
        for part in (
            (
                "主动作停稳后才执行微动作："
                + render_action_ids(
                    template_id,
                    (selection.micro_action_id,),
                    context=action_context,
                    library=action_library,
                ).rstrip("。；")
            )
            if selection.micro_action_id
            else "",
            f"表情：{selection.expression}" if selection.expression and expression_allowed else "",
        )
        if part
    )
    expression, expression_negatives = _partition_profile_text(profile.expression_language)
    _, camera_negatives = _partition_profile_text(profile.camera_language)
    pacing, pacing_negatives = _partition_profile_text(profile.pacing)
    return (
        "；".join(
            part
            for part in (
                f"基调：{profile.tone.rstrip('。；')}",
                f"表演（面部清晰时）：{expression}" if expression and expression_allowed else "",
                selected_layer,
                f"节奏：{pacing}" if pacing else "",
                "仅采用输入支持的动作，不新增场景、道具或商品面",
            )
            if part
        ),
        selected_action_ids,
        (*expression_negatives, *camera_negatives, *pacing_negatives),
        motion_metadata,
    )


def _learning_instruction(value: str) -> str:
    normalized = " ".join(value.replace("{{", "{").replace("}}", "}").split()).strip()
    if not normalized:
        return ""
    return f"个人反馈偏好（不得覆盖素材约束和禁止项）：{normalized[:600]}"


def compile_video_plan(
    value: PromptCompileInput,
    *,
    allow_draft: bool = False,
) -> CompiledVideoPlan:
    template = value.template
    if template.status != "active" and not allow_draft:
        raise ValueError(f"video template is not active: {template.id}")
    if value.site_profile is not None and value.site_profile.status != "active" and not allow_draft:
        raise ValueError(f"site style profile is not active: {value.site_profile.id}")
    if (
        value.site_profile is not None
        and value.site_profile.evidence_level != "verified_site"
        and not allow_draft
    ):
        raise ValueError(f"site style profile evidence is not verified: {value.site_profile.id}")
    if not template.min_images <= value.storyboard_count <= template.max_images:
        raise ValueError("storyboard count is incompatible with video template")
    if not 1 <= value.result_count <= 4:
        raise ValueError("result count must be between 1 and 4")
    if not 1 <= value.variant_index <= value.result_count:
        raise ValueError("variant index must be between 1 and result count")

    action_context = value.action_context
    # The same contract is rendered for all shots, so every shot must support it.
    if action_context is not None and action_context.evidence_sets:
        action_context = ActionContext(
            confirmed=frozenset.intersection(*action_context.evidence_sets),
            denied=action_context.denied,
        )
    action = template.action_presets[value.action_intensity]
    variant_action, variant_expression, variant_style = _VARIANT_MODIFIERS[value.variant_index - 1]
    if not (action_context or ActionContext()).supports(
        (
            ActionCapability.FACE_VISIBLE,
            ActionCapability.FACE_GAZE_ADJUSTABLE,
        )
    ):
        variant_expression = "沿用输入可见表情，不补造不可见面部"
    variant_modifier = "；".join(
        (
            f"动作：{variant_action}",
            f"神态（面部清晰时）：{variant_expression}",
            f"呈现：{variant_style}",
        )
    )
    cut_instruction = (
        "单镜头连续展示，不新增切镜"
        if value.storyboard_count == 1
        else _cut_instruction(value.cut_mode)
    )
    (
        style_instruction,
        selected_action_ids,
        style_negatives,
        motion_metadata,
    ) = _style_instruction(
        value.site_profile,
        template.id,
        action_context,
        value.action_library,
        value.learning_preferred_action_ids,
        value.learning_avoided_action_ids,
        variant_index=value.variant_index,
        recent_selected_action_ids=value.recent_selected_action_ids,
        recent_motion_combinations=value.recent_motion_combinations,
    )
    duration_seconds = value.duration_seconds or template.duration_seconds
    if not 3 <= duration_seconds <= 15:
        raise ValueError("duration must be between 3 and 15 seconds")
    duration = float(duration_seconds)
    shot_duration = duration / value.storyboard_count
    actions = value.action_library if value.action_library is not None else ACTION_LIBRARY
    primary_id = str(motion_metadata["selectedPrimaryActionId"])
    primary_instruction = render_action_ids(
        template.id,
        (primary_id,),
        context=action_context,
        library=actions,
    )
    if primary_id == "motion_to_rest":
        primary_instruction = ACTION_LIBRARY["motion_to_rest"].instruction
    contract = shot_motion_contract(
        primary_instruction.rstrip("。；"),
        camera_motion(str(motion_metadata["cameraFamily"])),
    )
    shots = tuple(
        ShotInstruction(
            order=index,
            start_seconds=round((index - 1) * shot_duration, 2),
            end_seconds=round(
                duration if index == value.storyboard_count else index * shot_duration,
                2,
            ),
            instruction=(
                _shot_rule(template.id, index, value.storyboard_count)
                if value.storyboard_count == 1
                else f"分镜{index}：{_shot_rule(template.id, index, value.storyboard_count)}"
            ),
        )
        for index in range(1, value.storyboard_count + 1)
    )
    invariants = tuple(
        item
        for item in template.prompt_rules.invariants
        if value.storyboard_count > 1 or not item.startswith("按输入分镜顺序执行")
    )
    profile_negatives = (
        tuple(
            dict.fromkeys(
                (
                    *value.site_profile.forbidden_mismatches,
                    *(
                        value.site_profile.forbidden_motion
                        if value.action_context is not None
                        else ()
                    ),
                )
            )
        )
        if value.site_profile
        else ()
    )
    negatives = tuple(
        dict.fromkeys(
            (
                *template.prompt_rules.negatives,
                *profile_negatives,
                *style_negatives,
                "过度磨皮、塑料感、蜡感或精修广告感",
            )
        )
    )
    negative_prompt = "；".join(negatives)
    timeline = "；".join(
        (
            f"{shot.start_seconds:g}-{shot.end_seconds:g}秒：{shot.instruction}"
            if value.storyboard_count == 1
            else (
                f"{shot.start_seconds:g}-{shot.end_seconds:g}秒/图{shot.order}：{shot.instruction}"
            )
        )
        for shot in shots
    )
    learning_instruction = _learning_instruction(value.learning_guidance)
    motion_instruction = "；".join(
        part
        for part in (
            f"时间轴：{timeline}",
            f"切镜：{cut_instruction}",
            f"幅度：{action.instruction}",
        )
        if part
    )
    style_parts = [style_instruction, f"本条变化：{variant_modifier}"]
    prompt_parts = [
        (
            "任务："
            + (
                "基于输入图"
                if value.storyboard_count == 1
                else f"按{value.storyboard_count}张分镜顺序"
            )
            + f"生成{duration_seconds}秒、{template.ratio}的{template.name}视频"
        ),
        (f"保持：{'；'.join(invariants)}；其余输入事实不变；仅改变动作细节、神态和拍摄表达"),
        f"动作：{motion_instruction}；逐镜执行：{contract.render()}",
        f"风格：{'；'.join(style_parts)}",
        learning_instruction,
        "质感：真实皮肤与布料，保留自然细节",
        f"避免：{negative_prompt}",
    ]
    master_prompt = "。".join(part for part in prompt_parts if part)
    prompt_budget = min(value.prompt_budget, _MAX_KLING_PROMPT_CHARS)
    if prompt_budget < 1:
        raise ValueError("prompt budget must be positive")
    compression_level = "full"
    if len(master_prompt) > prompt_budget and learning_instruction:
        overflow = len(master_prompt) - prompt_budget
        keep = max(0, len(learning_instruction) - overflow - 1)
        learning_instruction = learning_instruction[:keep].rstrip("；，。 ")
        prompt_parts[4] = learning_instruction
        master_prompt = "。".join(part for part in prompt_parts if part)
        compression_level = "trimmed-learning"
    if len(master_prompt) > prompt_budget:
        compact_style = (
            f"基调：{value.site_profile.tone.rstrip('。；')}；"
            if value.site_profile is not None
            else ""
        )
        micro_instruction = (
            "；主动作停稳后才执行微动作："
            + render_action_ids(
                template.id,
                selected_action_ids[1:],
                context=action_context,
                library=actions,
            ).rstrip("。；")
            if len(selected_action_ids) > 1
            else ""
        )
        prompt_parts[3] = (
            f"风格：{compact_style}本条变化：{variant_modifier}；"
            "仅采用输入支持的动作，不新增场景、道具或商品面" + micro_instruction
        )
        master_prompt = "。".join(part for part in prompt_parts if part)
        compression_level = "compact-style"
    if len(master_prompt) > prompt_budget:
        prompt_parts[5] = "质感：真实皮肤与布料"
        master_prompt = "。".join(part for part in prompt_parts if part)
        compression_level = "compact-quality"
    if len(master_prompt) > prompt_budget:
        raise ValueError(f"compiled prompt exceeds budget: {len(master_prompt)} > {prompt_budget}")
    return CompiledVideoPlan(
        template_id=template.id,
        template_version=template.version,
        master_prompt=master_prompt,
        shot_instructions=shots,
        invariants=invariants,
        negative_prompt=negative_prompt,
        variant_seed={
            "variantIndex": value.variant_index,
            "actionIntensity": value.action_intensity,
            "cutMode": value.cut_mode,
            "modifier": variant_modifier,
            "pacingSource": "site-profile" if value.site_profile else "template-default",
            "siteProfileId": value.site_profile.id if value.site_profile else "none",
            "selectedActionIds": list(selected_action_ids),
            "shotMotionContract": contract.to_dict(),
            "productScope": "upper_garment",
            "capabilityEvidencePolicy": "explicit-confirmation-only",
            **motion_metadata,
            "recentSelectedActionIds": list(value.recent_selected_action_ids),
            "recentMotionCombinations": list(value.recent_motion_combinations),
            "learningProfileVersion": value.learning_profile_version,
            "learningEvidenceCount": value.learning_evidence_count,
            "promptCompressionLevel": compression_level,
        },
        site_profile_id=value.site_profile.id if value.site_profile else None,
        site_profile_version=value.site_profile.version if value.site_profile else None,
    )
