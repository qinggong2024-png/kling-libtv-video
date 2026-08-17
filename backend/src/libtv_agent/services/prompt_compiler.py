from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from libtv_agent.templates.motion_actions import ActionContext, MotionAction, render_action_ids
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
    variant_seed: dict[str, str | int]
    site_profile_id: str | None = None
    site_profile_version: str | None = None


_MAX_KLING_PROMPT_CHARS = 3072

_VARIANT_MODIFIERS: tuple[tuple[str, str, str], ...] = (
    (
        "模板主动作完整执行一次，结束时回到对应输入分镜支持的稳定姿态",
        "放松、自然的轻微微笑，视线稳定",
        "生活化UGC记录感，画面保留极轻微的自然呼吸",
    ),
    (
        "把模板主动作拆成两个克制的小幅阶段，结束时保持对应输入分镜支持的稳定姿态",
        "平静、自信，嘴角放松，视线短暂离镜后回到镜头",
        "干净的日常lookbook式UGC，构图稳定",
    ),
    (
        "模板主动作中加入一次短暂停顿，结束时放松定姿",
        "轻松、专注，表情自然变化一次后恢复放松",
        "近距离朋友视角UGC，不呈现广告式炫技",
    ),
    (
        "模板主动作完成后回到起始稳定姿态，结束时克制定姿",
        "克制、略带酷感，视线坚定，不做夸张表情",
        "简洁编辑感UGC，构图克制，商品始终清晰",
    ),
)


def _cut_instruction(cut_mode: CutMode) -> str:
    if cut_mode == "explicit_cuts":
        return "按照输入分镜顺序允许明确、干净的切镜，不强制连接成长镜头"
    return "优先在可行时保持连续运动；画面条件不兼容时使用干净切镜"


def _shot_rule(template: VideoTemplate, order: int, total: int) -> str:
    rules = template.prompt_rules
    if total == 1:
        selected = (*rules.opening, *rules.middle, *rules.ending)
    elif order == 1:
        selected = rules.opening
    elif order == total:
        selected = rules.ending
    else:
        selected = rules.middle
    return "；".join(selected)


def _positive_profile_text(value: str) -> str:
    clauses = tuple(part.strip("。； ") for part in value.split("；") if part.strip("。； "))
    if not clauses:
        return ""
    if len(clauses) == 1:
        return clauses[0]
    return f"{clauses[0]}；补充：{'；'.join(clauses[1:])}"


def _style_instruction(
    profile: SiteStyleProfile | None,
    template_id: str,
    action_context: ActionContext | None,
    action_library: Mapping[str, MotionAction] | None,
) -> str:
    if profile is None:
        return "不额外套用站点风格，优先执行视频模板和输入分镜"
    preferred_actions = render_action_ids(
        template_id,
        profile.preferred_actions,
        context=action_context,
        library=action_library,
    )
    return "；".join(
        (
            "站点表达只作用于已有素材支持的动作、神态和拍摄触感，不新增或改写场景、道具、服装面与商品细节",
            f"站点风格：{profile.tone.rstrip('。；')}",
            f"人物表达（仅在面部清晰可见时执行）：{_positive_profile_text(profile.expression_language)}",
            f"镜头触感：{_positive_profile_text(profile.camera_language)}",
            f"可用动作：{preferred_actions}",
            (
                f"站点节奏：{profile.pacing.rstrip('。；')}；"
                "涉及输入未提供的商品面或场景时忽略对应描述"
            ),
        )
    )


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

    action = template.action_presets[value.action_intensity]
    camera = template.camera_presets["standard"]
    variant_action, variant_expression, variant_style = _VARIANT_MODIFIERS[value.variant_index - 1]
    variant_modifier = "；".join(
        (
            f"动作变化：{variant_action}",
            f"神态变化：仅在面部清晰可见时执行，{variant_expression}",
            f"视频风格变化：{variant_style}",
        )
    )
    cut_instruction = (
        "单镜头连续展示，不新增切镜"
        if value.storyboard_count == 1
        else _cut_instruction(value.cut_mode)
    )
    style_instruction = _style_instruction(
        value.site_profile,
        template.id,
        value.action_context,
        value.action_library,
    )
    duration_seconds = value.duration_seconds or template.duration_seconds
    if not 3 <= duration_seconds <= 15:
        raise ValueError("duration must be between 3 and 15 seconds")
    duration = float(duration_seconds)
    shot_duration = duration / value.storyboard_count
    shots = tuple(
        ShotInstruction(
            order=index,
            start_seconds=round((index - 1) * shot_duration, 2),
            end_seconds=round(
                duration if index == value.storyboard_count else index * shot_duration,
                2,
            ),
            instruction=f"分镜{index}：{_shot_rule(template, index, value.storyboard_count)}",
        )
        for index in range(1, value.storyboard_count + 1)
    )
    invariants = template.prompt_rules.invariants
    profile_negatives = value.site_profile.forbidden_mismatches if value.site_profile else ()
    negative_prompt = "；".join((*template.prompt_rules.negatives, *profile_negatives))
    timeline = "；".join(
        (f"{shot.start_seconds:g}-{shot.end_seconds:g}秒（输入图{shot.order}）：{shot.instruction}")
        for shot in shots
    )
    prompt_parts = (
        (
            f"按照输入的{value.storyboard_count}张有序分镜生成一条"
            f"{duration_seconds}秒、{template.ratio}的{template.name}视频"
        ),
        (
            "素材约束（最高优先级）："
            f"{'；'.join(invariants)}；所有未明确允许变化的输入事实保持不变；"
            "当前结果相对输入只允许改变动作细节、神态和拍摄表达"
        ),
        f"分镜与切镜：{cut_instruction}；切镜：{cut_instruction}；时间轴：{timeline}",
        f"动作幅度：{action.instruction}",
        camera.instruction if value.site_profile is None else "",
        style_instruction,
        f"本结果差异：{variant_modifier}",
        "皮肤保留真实纹理和自然细节，避免过度磨皮、塑料感和蜡感",
        "保持真实日常UGC记录感，允许轻微手持呼吸，不呈现精修商业广告感",
        f"禁止项：{negative_prompt}",
        "无声音，无字幕",
    )
    master_prompt = "。".join(part for part in prompt_parts if part)
    prompt_budget = min(value.prompt_budget, _MAX_KLING_PROMPT_CHARS)
    if prompt_budget < 1:
        raise ValueError("prompt budget must be positive")
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
        },
        site_profile_id=value.site_profile.id if value.site_profile else None,
        site_profile_version=value.site_profile.version if value.site_profile else None,
    )
