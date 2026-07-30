from __future__ import annotations

from dataclasses import dataclass

from libtv_agent.templates.motion_actions import ActionContext, render_action_ids
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
    site_profile: SiteStyleProfile | None = None
    action_context: ActionContext | None = None


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

_VARIANT_MODIFIERS: tuple[tuple[str, str, str, str], ...] = (
    (
        "开场静止半秒，中段完整执行模板主动作一次，结尾正面自然定姿",
        "放松、自然的轻微微笑，视线稳定",
        "生活化UGC轻手持跟拍，镜头有极轻微呼吸感",
        "均衡节奏；开场短停、中段连贯、结尾停留一秒",
    ),
    (
        "开场轻移重心，中段把模板主动作拆成两个克制的小幅阶段，结尾三分之四定姿",
        "平静、自信，嘴角放松，视线短暂离镜后回到镜头",
        "干净的日常lookbook式UGC，平稳轻跟拍",
        "舒缓节奏；动作之间各保留一次清楚停顿，结尾稳定停留",
    ),
    (
        "开场视线先落在商品再回到镜头，中段连续执行模板主动作并短暂停顿，结尾放松定姿",
        "轻松、专注，表情自然变化一次后恢复放松",
        "近距离朋友视角UGC，轻微手持横移，不使用广告式炫技运镜",
        "前缓后紧；前段建立商品，中段动作稍快，结尾回到稳定",
    ),
    (
        "开场直接进入模板主动作，中段完成一次动作后回正，结尾克制定姿",
        "克制、略带酷感，视线坚定，不做夸张表情",
        "简洁编辑感UGC，使用一次干净切镜和有限推进",
        "紧凑节奏；快速建立、中段完整执行、结尾明确停住",
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


def _style_instruction(
    profile: SiteStyleProfile | None,
    template_id: str,
    action_context: ActionContext | None,
) -> str:
    if profile is None:
        return "不额外套用站点风格，优先执行视频模板和输入分镜"
    preferred_actions = render_action_ids(
        template_id,
        profile.preferred_actions,
        context=action_context,
    )
    return "；".join(
        (
            f"站点风格：{profile.tone}",
            f"镜头触感：{profile.camera_language}",
            (
                f"视频结构：开场 {profile.opening_rule}；"
                f"中段 {profile.middle_rule}；结尾 {profile.ending_rule}"
            ),
            f"优先镜头：{'、'.join(profile.preferred_shots)}",
            f"优先动作：{preferred_actions}",
            f"节奏：{profile.pacing}",
            f"商品呈现重点：{'、'.join(profile.product_priorities)}",
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
    camera = template.camera_presets[value.camera_tempo]
    tempo = template.tempo_presets[value.camera_tempo]
    variant_action, variant_expression, variant_style, variant_rhythm = _VARIANT_MODIFIERS[
        value.variant_index - 1
    ]
    variant_modifier = "；".join(
        (
            f"动作变化：{variant_action}",
            f"神态变化：{variant_expression}",
            f"视频风格变化：{variant_style}",
            f"节奏变化：{variant_rhythm}",
        )
    )
    cut_instruction = _cut_instruction(value.cut_mode)
    style_instruction = _style_instruction(value.site_profile, template.id, value.action_context)
    duration = float(template.duration_seconds)
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
    result_scope = (
        "当前结果相对输入"
        if value.result_count == 1
        else f"本次生成的{value.result_count}个结果相对输入都"
    )
    master_prompt = "。".join(
        (
            (
                f"按照输入的{value.storyboard_count}张有序分镜生成一条"
                f"{template.duration_seconds}秒、{template.ratio}的{template.name}视频"
            ),
            cut_instruction,
            f"时间轴：{timeline}",
            action.instruction,
            camera.instruction,
            tempo.instruction,
            style_instruction,
            variant_modifier,
            (
                "所有未明确允许变化的输入事实永久不变；"
                f"{result_scope}只允许改变动作、神态、视频风格和节奏"
            ),
            "皮肤保留真实纹理和自然细节，避免过度磨皮、塑料感和蜡感",
            "保持真实日常UGC记录感，允许轻微手持呼吸，不呈现精修商业广告感",
            "；".join(invariants),
            f"禁止项：{negative_prompt}",
            "无声音，无字幕",
        )
    )
    if len(master_prompt) > _MAX_KLING_PROMPT_CHARS:
        raise ValueError(
            f"compiled prompt exceeds Kling limit: {len(master_prompt)} > {_MAX_KLING_PROMPT_CHARS}"
        )
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
            "cameraTempo": value.camera_tempo,
            "cutMode": value.cut_mode,
            "modifier": variant_modifier,
            "siteProfileId": value.site_profile.id if value.site_profile else "none",
        },
        site_profile_id=value.site_profile.id if value.site_profile else None,
        site_profile_version=value.site_profile.version if value.site_profile else None,
    )
