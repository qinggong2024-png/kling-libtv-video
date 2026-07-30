from __future__ import annotations

from dataclasses import dataclass

from libtv_agent.templates.motion_actions import render_action_ids
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
    action_intensity: ActionIntensity
    camera_tempo: CameraTempo
    cut_mode: CutMode
    variant_index: int
    site_profile: SiteStyleProfile | None = None


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


_VARIANT_MODIFIERS: tuple[str, ...] = (
    "使用模板的首选动作组合",
    "在不改变人物和服装事实的前提下调整轻微动作组合",
    "在不改变人物和服装事实的前提下调整有限运镜方式",
    "在不改变人物和服装事实的前提下调整动作与停留时机",
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


def _style_instruction(profile: SiteStyleProfile | None, template_id: str) -> str:
    if profile is None:
        return "不额外套用站点风格，优先执行视频模板和输入分镜"
    return "；".join(
        (
            f"站点风格：{profile.tone}",
            f"镜头触感：{profile.camera_language}",
            (
                f"视频结构：开场 {profile.opening_rule}；"
                f"中段 {profile.middle_rule}；结尾 {profile.ending_rule}"
            ),
            f"优先镜头：{'、'.join(profile.preferred_shots)}",
            f"优先动作：{render_action_ids(template_id, profile.preferred_actions)}",
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
    if not template.min_images <= value.storyboard_count <= template.max_images:
        raise ValueError("storyboard count is incompatible with video template")
    if not 1 <= value.variant_index <= 4:
        raise ValueError("variant index must be between 1 and 4")

    action = template.action_presets[value.action_intensity]
    camera = template.camera_presets[value.camera_tempo]
    tempo = template.tempo_presets[value.camera_tempo]
    variant_modifier = _VARIANT_MODIFIERS[value.variant_index - 1]
    cut_instruction = _cut_instruction(value.cut_mode)
    style_instruction = _style_instruction(value.site_profile, template.id)
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
            instruction=(
                f"分镜{index}：{_shot_rule(template, index, value.storyboard_count)}；"
                f"{action.instruction}；{camera.instruction}；{tempo.instruction}；"
                f"{style_instruction}"
            ),
        )
        for index in range(1, value.storyboard_count + 1)
    )
    invariants = template.prompt_rules.invariants
    profile_negatives = value.site_profile.forbidden_mismatches if value.site_profile else ()
    negative_prompt = "；".join((*template.prompt_rules.negatives, *profile_negatives))
    master_prompt = "。".join(
        (
            (
                f"按照输入的{value.storyboard_count}张有序分镜生成一条"
                f"{template.duration_seconds}秒、{template.ratio}的{template.name}视频"
            ),
            cut_instruction,
            action.instruction,
            camera.instruction,
            tempo.instruction,
            style_instruction,
            variant_modifier,
            "；".join(invariants),
            f"禁止项：{negative_prompt}",
            "无声音，无字幕",
        )
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
