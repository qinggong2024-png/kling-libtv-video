import asyncio
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal, Protocol

from libtv_agent.config import Settings
from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel


class ContractModel(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, extra="forbid")


class GarmentFacts(ContractModel):
    category: str = Field(default="", max_length=40)
    main_color: str = Field(default="", max_length=40)
    secondary_color: str = Field(default="", max_length=40)
    print: str = Field(default="", max_length=80)
    logo: str = Field(default="", max_length=80)
    text: str = Field(default="", max_length=80)
    fit: str = Field(default="", max_length=60)
    front_selling_points: list[str] = Field(default_factory=list, max_length=4)
    back_selling_points: list[str] = Field(default_factory=list, max_length=4)
    unknown_fields: list[str] = Field(default_factory=list, max_length=8)


class StoryboardFact(ContractModel):
    asset_id: str
    order: int = Field(ge=1, le=7)
    scene: str = Field(default="", max_length=80)
    framing: str = Field(default="", max_length=60)
    pose: str = Field(default="", max_length=80)
    action_candidates: list[str] = Field(default_factory=list, max_length=3)
    interaction_objects: list[str] = Field(default_factory=list, max_length=3)
    product_visibility: str = Field(default="front_clear", max_length=80)
    shot_function: str = Field(default="product_opening", max_length=80)


class ConsistencyObservations(ContractModel):
    reason_codes: list[str] = Field(default_factory=list, max_length=8)
    summary: str = Field(default="", max_length=240)
    unknown_fields: list[str] = Field(default_factory=list, max_length=8)
    evidence_asset_ids: list[str] = Field(default_factory=list, max_length=7)


class ShotPlan(ContractModel):
    reference_asset_ids: list[str] = Field(min_length=1, max_length=7)
    duration_weight: float = Field(gt=0)
    entry_state: str = Field(max_length=120)
    action: str = Field(max_length=120)
    exit_state: str = Field(max_length=120)
    camera: str = Field(max_length=100)
    product_display: str = Field(max_length=100)
    shot_function: str = Field(max_length=100)


class VariantPlan(ContractModel):
    continuity_strategy: Literal["state_continuity"] = "state_continuity"
    shots: list[ShotPlan] = Field(min_length=1, max_length=4)


class AnalysisResult(ContractModel):
    schema_version: Literal["2.2"] = "2.2"
    garment_facts: GarmentFacts
    storyboard_facts: list[StoryboardFact] = Field(min_length=1, max_length=7)
    consistency_observations: ConsistencyObservations = Field(
        default_factory=ConsistencyObservations
    )
    risk_flags: list[str] = Field(default_factory=list, max_length=8)
    stable_plan: VariantPlan
    dynamic_plan: VariantPlan
    user_requirement_normalized: str = Field(default="", max_length=240)
    model_version: str = Field(max_length=80)


class AnalysisAdapter(Protocol):
    async def analyze(self, prompt: str, images: list["AnalysisImageInput"]) -> AnalysisResult: ...


@dataclass(frozen=True)
class AnalysisImageInput:
    asset_id: str
    order: int
    image_url: str
    role: str = "STORYBOARD"


class AnalysisTimeoutError(TimeoutError):
    pass


class AnalysisNotSubmittedError(RuntimeError):
    """The request failed local preflight before an OpenAI call was sent."""


def fake_analysis(asset_ids: list[str], user_requirement: str = "") -> AnalysisResult:
    facts = [
        StoryboardFact(asset_id=asset_id, order=index + 1)
        for index, asset_id in enumerate(asset_ids)
    ]
    stable_group_count = min(3, len(asset_ids))
    dynamic_group_count = min(4, len(asset_ids))
    stable_groups = [
        asset_ids[
            index * len(asset_ids) // stable_group_count : (index + 1)
            * len(asset_ids)
            // stable_group_count
        ]
        for index in range(stable_group_count)
    ]
    dynamic_groups = [
        asset_ids[
            index * len(asset_ids) // dynamic_group_count : (index + 1)
            * len(asset_ids)
            // dynamic_group_count
        ]
        for index in range(dynamic_group_count)
    ]
    stable = [
        ShotPlan(
            reference_asset_ids=group,
            duration_weight=1 + (0.25 if index == len(stable_groups) - 1 else 0),
            entry_state=(
                "从参考图中的自然站姿开始"
                if index == 0
                else "承接上一段结束时的人物位置、朝向和手部状态"
            ),
            action="做小幅自然动作",
            exit_state="动作自然落定并保持商品区域清晰",
            camera="稳定缓慢推进",
            product_display="服装正面",
            shot_function="产品清晰开场" if index == 0 else "细节展示",
        )
        for index, group in enumerate(stable_groups)
    ]
    dynamic = [
        ShotPlan(
            reference_asset_ids=group,
            duration_weight=1.25 if index == 0 else 1,
            entry_state=(
                "从参考图中的自然站姿开始" if index == 0 else "从上一段结束姿势和运动方向继续"
            ),
            action="在场景中自信行进",
            exit_state="动作平稳收束并形成下一段可延续的姿势",
            camera="控制横向跟拍",
            product_display="服装整体轮廓",
            shot_function="强动态广告开场" if index == 0 else "动态展示",
        )
        for index, group in enumerate(dynamic_groups)
    ]
    return AnalysisResult(
        garment_facts=GarmentFacts(),
        storyboard_facts=facts,
        stable_plan=VariantPlan(shots=stable),
        dynamic_plan=VariantPlan(shots=dynamic),
        user_requirement_normalized=" ".join(user_requirement.split()),
        model_version="fake-2.2",
    )


class FakeAnalysisAdapter:
    def __init__(self, asset_ids: list[str], user_requirement: str = "") -> None:
        self.asset_ids = asset_ids
        self.user_requirement = user_requirement

    async def analyze(self, prompt: str, images: list[AnalysisImageInput]) -> AnalysisResult:
        del prompt, images
        return fake_analysis(self.asset_ids, self.user_requirement)


class ReplayAnalysisAdapter:
    def __init__(self, fixture: Path, asset_ids: list[str] | None = None) -> None:
        self.fixture = fixture
        self.asset_ids = asset_ids or []

    async def analyze(self, prompt: str, images: list[AnalysisImageInput]) -> AnalysisResult:
        del prompt, images
        payload = self.fixture.read_text(encoding="utf-8")
        for index, asset_id in enumerate(self.asset_ids, start=1):
            payload = payload.replace(f"{{{{ASSET_{index}}}}}", asset_id)
        return AnalysisResult.model_validate_json(payload)


class OpenAIAnalysisAdapter:
    def __init__(self, settings: Settings, client: Any | None = None) -> None:
        self.settings = settings
        self.client = client
        self.provider_response_id: str | None = None

    async def analyze(self, prompt: str, images: list[AnalysisImageInput]) -> AnalysisResult:
        if self.client is None and not self.settings.openai_api_key:
            raise AnalysisNotSubmittedError("OPENAI_API_KEY is required for real AI analysis")
        if not images:
            raise ValueError("at least one ordered analysis image is required")
        orders = [item.order for item in images]
        if orders != list(range(1, len(images) + 1)):
            raise ValueError("analysis images must be in contiguous 1-based order")
        if len({item.asset_id for item in images}) != len(images):
            raise ValueError("analysis image asset IDs must be unique")

        client = self.client
        if client is None:
            from openai import AsyncOpenAI

            request_timeout = self.settings.analysis_timeout_for_image_count(len(images))
            client = AsyncOpenAI(
                api_key=self.settings.openai_api_key,
                base_url=self.settings.openai_base_url,
                timeout=request_timeout,
            )
        else:
            request_timeout = self.settings.analysis_timeout_for_image_count(len(images))
        content: list[dict[str, object]] = [{"type": "input_text", "text": prompt}]
        for image in images:
            content.append(
                {
                    "type": "input_text",
                    "text": f"{image.role} assetId={image.asset_id} order={image.order}",
                }
            )
            content.append({"type": "input_image", "image_url": image.image_url, "detail": "low"})
        try:
            async with asyncio.timeout(request_timeout):
                response = await client.responses.parse(
                    model=self.settings.openai_model,
                    reasoning={"effort": self.settings.openai_reasoning_effort},
                    max_output_tokens=self.settings.openai_analysis_max_output_tokens,
                    input=[{"role": "user", "content": content}],
                    text_format=AnalysisResult,
                )
        except TimeoutError as exc:
            raise AnalysisTimeoutError(
                f"OpenAI image analysis exceeded {request_timeout:g} seconds "
                f"for {len(images)} image(s)"
            ) from exc
        response_id = getattr(response, "id", None)
        self.provider_response_id = response_id if isinstance(response_id, str) else None
        if response.output_parsed is None:
            raise RuntimeError("OpenAI response did not contain a valid structured result")
        return response.output_parsed
