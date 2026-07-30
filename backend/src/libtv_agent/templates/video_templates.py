from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Literal

TemplateStatus = Literal["draft", "active", "retired"]
ActionIntensity = Literal["low", "standard", "high"]
CameraTempo = Literal["slow", "standard", "fast"]
CutMode = Literal["explicit_cuts", "continuous_when_possible"]


@dataclass(frozen=True)
class ActionPreset:
    label: str
    instruction: str


@dataclass(frozen=True)
class CameraPreset:
    label: str
    instruction: str


@dataclass(frozen=True)
class TempoPreset:
    label: str
    instruction: str


@dataclass(frozen=True)
class PromptRules:
    opening: tuple[str, ...]
    middle: tuple[str, ...]
    ending: tuple[str, ...]
    invariants: tuple[str, ...]
    negatives: tuple[str, ...]


@dataclass(frozen=True)
class VideoTemplate:
    id: str
    version: str
    status: TemplateStatus
    name: str
    description: str
    min_images: int
    max_images: int
    duration_seconds: int
    ratio: str
    sound: bool
    subtitles: bool
    smart_storyboard: bool
    continuity_strategy: CutMode
    action_presets: dict[ActionIntensity, ActionPreset]
    camera_presets: dict[CameraTempo, CameraPreset]
    tempo_presets: dict[CameraTempo, TempoPreset]
    prompt_rules: PromptRules
    source_note: str

    def to_public_dict(self) -> dict[str, object]:
        value = asdict(self)
        value["defaultSettings"] = {
            "durationSeconds": value.pop("duration_seconds"),
            "ratio": value.pop("ratio"),
            "sound": value.pop("sound"),
            "subtitles": value.pop("subtitles"),
            "smartStoryboard": value.pop("smart_storyboard"),
            "continuityStrategy": value.pop("continuity_strategy"),
        }
        value["minImages"] = value.pop("min_images")
        value["maxImages"] = value.pop("max_images")
        value["actionPresets"] = value.pop("action_presets")
        value["cameraPresets"] = value.pop("camera_presets")
        value["tempoPresets"] = value.pop("tempo_presets")
        value["promptRules"] = value.pop("prompt_rules")
        value["sourceNote"] = value.pop("source_note")
        return value


_COMMON_ACTION_PRESETS: dict[ActionIntensity, ActionPreset] = {
    "low": ActionPreset("轻微", "动作幅度轻微、克制，优先保持服装细节稳定"),
    "standard": ActionPreset("标准", "动作自然清晰，幅度适中，不使用突然或夸张的动作"),
    "high": ActionPreset("明显", "动作表达更明显，但保持自然身体力学和服装结构稳定"),
}

_COMMON_CAMERA_PRESETS: dict[CameraTempo, CameraPreset] = {
    "slow": CameraPreset("舒缓", "镜头缓慢平稳移动，以稳定展示为主"),
    "standard": CameraPreset("标准", "镜头以自然速度平稳跟随和有限推进"),
    "fast": CameraPreset("快", "镜头切换更紧凑，但禁止甩镜、突然变焦和无意义旋转"),
}

_COMMON_TEMPO_PRESETS: dict[CameraTempo, TempoPreset] = {
    "slow": TempoPreset("舒缓", "节奏舒缓，各段保留充足稳定展示时间"),
    "standard": TempoPreset("标准", "节奏均衡，动作和展示时长清晰"),
    "fast": TempoPreset("快", "节奏相对紧凑，仍保持动作完整和商品清晰"),
}

_COMMON_INVARIANTS = (
    "保持人物身份、面部特征和体型一致",
    "保持服装款式、颜色、面料、版型、印花、Logo和文字内容不变",
    "保持输入图片中的场景、背景陈设和光线条件不变",
    "保持输入分镜结构、镜头对应关系及素材先后顺序，不跳过、不替换、不重排",
    "不得换装、不得新增配饰、不得改变服装结构",
)

_COMMON_NEGATIVES = (
    "避免人物身份漂移",
    "避免面部、肢体、手指和衣物变形",
    "避免印花、Logo和文字扭曲、漂移或闪烁",
    "避免突然换装、增加配饰或改变服装结构",
    "避免无意义镜头旋转、甩镜和突然变焦",
    "不要生成声音、字幕、贴纸或画面外文字",
)


def _production_template(
    *,
    template_id: str,
    name: str,
    description: str,
    opening: tuple[str, ...],
    middle: tuple[str, ...],
    ending: tuple[str, ...],
    extra_invariants: tuple[str, ...] = (),
    extra_negatives: tuple[str, ...] = (),
) -> VideoTemplate:
    return VideoTemplate(
        id=template_id,
        version="1.0.0",
        status="active",
        name=name,
        description=description,
        min_images=1,
        max_images=7,
        duration_seconds=10,
        ratio="9:16",
        sound=False,
        subtitles=False,
        smart_storyboard=True,
        continuity_strategy="explicit_cuts",
        action_presets=dict(_COMMON_ACTION_PRESETS),
        camera_presets=dict(_COMMON_CAMERA_PRESETS),
        tempo_presets=dict(_COMMON_TEMPO_PRESETS),
        prompt_rules=PromptRules(
            opening=opening,
            middle=middle,
            ending=ending,
            invariants=(*_COMMON_INVARIANTS, *extra_invariants),
            negatives=(*_COMMON_NEGATIVES, *extra_negatives),
        ),
        source_note="已依据用户确认的生产总结提示词拆解，并通过固定模板约束测试",
    )


VIDEO_TEMPLATES: dict[str, VideoTemplate] = {
    "ootd_walk": _production_template(
        template_id="ootd_walk",
        name="OOTD走动展示",
        description="以自然走动和有限转身展示服装整体版型。",
        opening=("从输入分镜中的自然姿态开始", "保持服装完整可见"),
        middle=("自然走动并轻微转身", "按分镜顺序展示服装正面、侧面和整体版型"),
        ending=("以自然定姿结束", "镜头稳定停留展示整体穿搭"),
        extra_negatives=("避免奔跑、跳跃、快速旋转和过大步幅",),
    ),
    "garment_detail": _production_template(
        template_id="garment_detail",
        name="服装细节展示",
        description="从整体到局部展示面料、版型、印花或衣摆细节。",
        opening=("先建立服装整体视图", "保持商品主体清晰"),
        middle=("以小幅动作展示面料、版型、印花或衣摆", "使用有限且平稳的镜头推进"),
        ending=("回到清晰稳定的商品展示",),
        extra_invariants=("局部细节必须来自输入图片，不得补画新的图案或文字",),
        extra_negatives=("避免过度拉近导致局部重绘", "避免手部遮挡主要印花和文字"),
    ),
    "mood_model": _production_template(
        template_id="mood_model",
        name="氛围感模特展示",
        description="以轻微身体动作和有限运镜共同表达氛围，服装仍是主要识别对象。",
        opening=("从输入分镜的环境与人物关系开始",),
        middle=("使用轻微身体动作和有限运镜表达氛围", "避免大幅走动和过多切镜"),
        ending=("以自然停留结束并保持服装清晰可辨",),
        extra_invariants=("环境可以参与氛围表达，但不得改变人物和服装事实",),
    ),
}


def list_video_templates(*, include_retired: bool = False) -> tuple[VideoTemplate, ...]:
    return tuple(
        template
        for template in VIDEO_TEMPLATES.values()
        if include_retired or template.status != "retired"
    )


def get_video_template(template_id: str, *, require_active: bool = False) -> VideoTemplate:
    template = VIDEO_TEMPLATES.get(template_id)
    if template is None:
        raise ValueError(f"unknown video template: {template_id}")
    if require_active and template.status != "active":
        raise ValueError(f"video template is not active: {template_id}")
    return template
