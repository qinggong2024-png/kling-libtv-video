"""Immutable, ordered Director analysis contract.

The contract absorbs the plugin's planning rules without claiming that a
Provider, model account, or real media asset was used.  Every stage is
recorded in order so downstream workflow commands can fail closed when an
analysis is missing, reordered, or tampered with.
"""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from libtv_agent.creative.workflow import digest

DIRECTOR_ANALYSIS_SCHEMA = "director-analysis.v1"
ANALYSIS_PIPELINE = (
    "PRODUCT_BRAND_AUDIENCE_DNA",
    "SCENE_REALITY_SPATIAL",
    "STORYBOARD_SHOT_MIX_PRECHECK",
    "KEY_VISUAL_SELECTOR",
    "IMAGE_PROMPT_MOTION_READY",
    "MODEL_AWARE_VIDEO_STRATEGY",
    "EMOTION_VIDEO_PROMPT",
    "VIDEO_QA_ONE_FIX",
)

StageKey = Literal[
    "PRODUCT_BRAND_AUDIENCE_DNA",
    "SCENE_REALITY_SPATIAL",
    "STORYBOARD_SHOT_MIX_PRECHECK",
    "KEY_VISUAL_SELECTOR",
    "IMAGE_PROMPT_MOTION_READY",
    "MODEL_AWARE_VIDEO_STRATEGY",
    "EMOTION_VIDEO_PROMPT",
    "VIDEO_QA_ONE_FIX",
]
StageStatus = Literal["COMPLETE", "PLANNED", "UNRESOLVED", "UNVERIFIED", "NOT_APPLICABLE"]
Strategy = Literal[
    "single_take",
    "single_call_multishot",
    "independent_segments",
    "hybrid",
    "strategy_unresolved",
]


class AnalysisModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)


class DirectorAnalysisStage(AnalysisModel):
    key: StageKey
    order: int = Field(ge=1)
    status: StageStatus
    depends_on: tuple[StageKey, ...] = ()
    evidence: tuple[str, ...] = Field(min_length=1)
    outputs: tuple[str, ...] = Field(min_length=1)


class VideoStrategySummary(AnalysisModel):
    strategy: Strategy = "strategy_unresolved"
    exact_model: str = "unknown"
    entrypoint: str = "unknown"
    capability_evidence: Literal[
        "official_documented",
        "entrypoint_verified",
        "tool_input_accepted",
        "rendered_observed",
        "unknown",
    ] = "unknown"
    segment_map: tuple[str, ...] = ()
    fallback: str = "先核对具体型号、入口和账号能力，再决定分段方式。"
    benchmark_state: Literal["not_tested", "provisional", "verified"] = "not_tested"
    generation_authorized: Literal[False] = False


class DirectorAnalysis(AnalysisModel):
    schema_version: Literal[DIRECTOR_ANALYSIS_SCHEMA] = DIRECTOR_ANALYSIS_SCHEMA
    source_hash: str = Field(min_length=1)
    facts_revision: int = Field(ge=1)
    directions_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    direction_ids: tuple[str, ...]
    selected_direction: str | None = None
    trace: tuple[StageKey, ...]
    stages: tuple[DirectorAnalysisStage, ...]
    product_showcase: Literal["print_first", "not_print_first", "unknown"] = "unknown"
    video_strategy: VideoStrategySummary = VideoStrategySummary()
    planning_status: Literal["READY_FOR_DIRECTION", "READY_FOR_PACKAGE", "UNVERIFIED"] = (
        "READY_FOR_DIRECTION"
    )

    @model_validator(mode="after")
    def validate_pipeline(self) -> DirectorAnalysis:
        if self.trace != ANALYSIS_PIPELINE:
            raise ValueError("director analysis trace must contain every stage in fixed order")
        if tuple(stage.key for stage in self.stages) != ANALYSIS_PIPELINE:
            raise ValueError("director analysis stages must contain every stage in fixed order")
        if tuple(stage.order for stage in self.stages) != tuple(
            range(1, len(ANALYSIS_PIPELINE) + 1)
        ):
            raise ValueError("director analysis stage order must be contiguous")
        for index, stage in enumerate(self.stages):
            expected_dependencies = ANALYSIS_PIPELINE[:index]
            if stage.depends_on != expected_dependencies:
                raise ValueError(f"{stage.key} has an invalid dependency chain")
        if (
            self.selected_direction is not None
            and self.selected_direction not in self.direction_ids
        ):
            raise ValueError("selected direction must reference an analyzed direction")
        if not self.direction_ids or len(set(self.direction_ids)) != len(self.direction_ids):
            raise ValueError("analyzed directions must be nonempty and unique")
        if any(not value.strip() for value in self.direction_ids):
            raise ValueError("analyzed direction IDs must not be blank")
        expected_status = (
            "READY_FOR_PACKAGE" if self.selected_direction is not None else "READY_FOR_DIRECTION"
        )
        if self.planning_status != expected_status:
            raise ValueError("planning status must match direction selection")
        if any(
            not value.strip()
            for stage in self.stages
            for value in (*stage.evidence, *stage.outputs)
        ):
            raise ValueError("stage evidence and output references must not be blank")
        return self


def _stage(
    key: StageKey,
    status: StageStatus,
    *,
    evidence: Sequence[str],
    outputs: Sequence[str],
) -> DirectorAnalysisStage:
    index = ANALYSIS_PIPELINE.index(key)
    return DirectorAnalysisStage(
        key=key,
        order=index + 1,
        status=status,
        depends_on=ANALYSIS_PIPELINE[:index],
        evidence=tuple(evidence),
        outputs=tuple(outputs),
    )


def build_director_analysis(
    *,
    source_hash: str,
    facts_revision: int,
    directions: Sequence[Mapping[str, str]],
    brand_selected: bool,
    product_showcase: Literal["print_first", "not_print_first", "unknown"] = "unknown",
) -> DirectorAnalysis:
    """Build the complete planning trace without calling a model or Provider."""
    direction_ids = tuple(str(direction.get("id", "")) for direction in directions)
    if not direction_ids or any(not value for value in direction_ids):
        raise ValueError("director analysis requires at least one direction")

    brand_evidence = (
        "用户已选择品牌目录快照，分析只读取该版本。"
        if brand_selected
        else "未选择具体品牌，按通用风格记录，不推断品牌归属。"
    )
    showcase_evidence = (
        "当前商品是否以印花为主尚未由用户确认，保留为 unknown。"
        if product_showcase == "unknown"
        else f"商品展示优先级已记录为 {product_showcase}。"
    )
    stages = (
        _stage(
            "PRODUCT_BRAND_AUDIENCE_DNA",
            "COMPLETE",
            evidence=(
                "Canonical Product 正面来源哈希已锁定。",
                brand_evidence,
                "受众和购买理由没有事实证据时保持为创意假设。",
            ),
            outputs=("product_truth", "brand_route", "audience_hypothesis"),
        ),
        _stage(
            "SCENE_REALITY_SPATIAL",
            "PLANNED",
            evidence=(
                "Reality 六维按 Camera→Lighting→Composition→Human Behavior"
                "→Environment→Imperfection 预留。",
                "空间锚点、机位和人物走位保持规划状态，未宣称像素验证。",
            ),
            outputs=("scene_plan", "reality_six_dimensions", "spatial_blocking"),
        ),
        _stage(
            "STORYBOARD_SHOT_MIX_PRECHECK",
            "PLANNED",
            evidence=(
                "先建立镜头时间线，再做商品展示覆盖和景别节奏检查；没有时间线不能计算比例。",
                showcase_evidence,
                "仅适用的 10–12 秒 print_first 上身广告参考按时长 50/30/20；"
                "这是软基线，用户锁定和物理约束优先，不能按镜数或生图数计算。",
                "印花专项展示按时间区间并集计算，重叠只计一次；"
                "重复指摸或同功能特写优先合并，不自动增加镜头或生成张数。",
            ),
            outputs=("storyboard_timeline", "product_display_coverage", "shot_mix_precheck"),
        ),
        _stage(
            "KEY_VISUAL_SELECTOR",
            "PLANNED",
            evidence=(
                "关键视觉按场景、机位、景别、姿态和商品展示变化去重。",
                "Kxx 数量与 Sxx/Vxx 数量分开记录，不自动授权生图。",
                "视频任务必须先核对具体模型和生成策略再冻结 Kxx；"
                "当前策略未决，仅记录待选关键视觉，不宣称已冻结。",
            ),
            outputs=("key_visual_plan", "shot_to_key_visual_mapping"),
        ),
        _stage(
            "IMAGE_PROMPT_MOTION_READY",
            "PLANNED",
            evidence=(
                "首帧先检查支撑点、手部占用、可动空间、衣料受力和相机起始状态。",
                "文字 Prompt 或规划结果不等于实际首帧像素通过。",
            ),
            outputs=("image_prompt", "motion_ready_frame_gate"),
        ),
        _stage(
            "MODEL_AWARE_VIDEO_STRATEGY",
            "UNRESOLVED",
            evidence=(
                "当前没有本次账号、具体型号和入口的能力证据。",
                "不把官方资料或模型系列名当作当前账号已开放能力。",
                "一镜到底、单次含切镜、独立分段和混合方式分别评估；"
                "Sxx、Vxx、Kxx 数量不必相等，未核对入口能力时不自动选定策略。",
            ),
            outputs=("video_production_strategy", "model_capability_profile"),
        ),
        _stage(
            "EMOTION_VIDEO_PROMPT",
            "PLANNED",
            evidence=(
                "视频行为按 perception→reaction→purposeful_action→settle 组织。",
                "跨段交接、音频和镜头语法依具体型号与真实输入能力决定。",
                "只有连续动作需要且上一段真实视频可访问时才使用其结束观察态；"
                "普通蒙太奇不强制对帧，未确认音频能力不宣称口型或音频已生成。",
            ),
            outputs=("emotion_motion_beat", "engine_aware_video_prompt"),
        ),
        _stage(
            "VIDEO_QA_ONE_FIX",
            "UNVERIFIED",
            evidence=(
                "真实视频不可访问时保持 unverified。",
                "拿到实际视频后按时码定位一个主问题，再提出 one-fix；不自动重试。",
                "区分正常衣料形变与商品字母、插画设计漂移；"
                "策略对照记录同条件可用率及真实成本，没有数据不宣称效果或 ROI 改善。",
            ),
            outputs=("temporal_product_fidelity", "video_qa_timeline", "one_fix"),
        ),
    )
    return DirectorAnalysis(
        source_hash=source_hash,
        facts_revision=facts_revision,
        directions_hash=digest(list(directions)),
        direction_ids=direction_ids,
        trace=ANALYSIS_PIPELINE,
        stages=stages,
        product_showcase=product_showcase,
    )


def validate_director_analysis(
    payload: Mapping[str, object] | DirectorAnalysis,
    *,
    selected_direction: str | None = None,
) -> DirectorAnalysis:
    value = payload.model_dump(mode="json") if isinstance(payload, DirectorAnalysis) else payload
    analysis = DirectorAnalysis.model_validate(value)
    if selected_direction is not None and analysis.selected_direction != selected_direction:
        raise ValueError("director analysis selection does not match the requested direction")
    return analysis


def select_director_direction(
    analysis: DirectorAnalysis,
    direction_id: str,
) -> DirectorAnalysis:
    if direction_id not in analysis.direction_ids:
        raise ValueError("selected direction must reference an analyzed direction")
    return analysis.model_copy(
        update={
            "selected_direction": direction_id,
            "planning_status": "READY_FOR_PACKAGE",
        }
    )
