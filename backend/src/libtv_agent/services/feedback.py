import uuid
from collections import Counter
from typing import Any

from libtv_agent.domain.contracts import sha256_json
from libtv_agent.domain.enums import FeedbackValue, VariantKind
from libtv_agent.domain.models import GenerationFeedback
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

FEEDBACK_HISTORY_LIMIT = 40
FEEDBACK_SIGNAL_LIMIT = 2


def _clean(value: Any, fallback: str) -> str:
    normalized = " ".join(str(value or "").split()).strip()
    return normalized or fallback


def feedback_context(
    analysis_result: dict[str, Any] | None,
    variant_type: VariantKind,
) -> dict[str, Any]:
    analysis = analysis_result or {}
    garment = analysis.get("garmentFacts") or {}
    storyboard = analysis.get("storyboardFacts") or []
    category = _clean(garment.get("category"), "未分类服装")
    scenes = sorted(
        {_clean(fact.get("scene"), "未分类场景") for fact in storyboard if isinstance(fact, dict)}
    ) or ["未分类场景"]
    plan_name = "stablePlan" if variant_type == VariantKind.STABLE else "dynamicPlan"
    plan = analysis.get(plan_name) or {}
    signals: list[str] = []
    for shot in plan.get("shots") or []:
        if not isinstance(shot, dict):
            continue
        for key in ("shotFunction", "action", "camera"):
            signal = _clean(shot.get(key), "")
            if signal and signal not in signals:
                signals.append(signal)
    signature = {
        "category": category.casefold(),
        "scenes": [scene.casefold() for scene in scenes],
    }
    return {
        "sceneKey": sha256_json(signature),
        "category": category,
        "scenes": scenes,
        "signals": signals[:8],
    }


def _guidance_for_kind(
    context: dict[str, Any],
    history: list[GenerationFeedback],
) -> str:
    if not history:
        return ""
    scores: Counter[str] = Counter()
    likes = 0
    dislikes = 0
    for item in history:
        direction = 1 if item.value == FeedbackValue.LIKE else -1
        if direction > 0:
            likes += 1
        else:
            dislikes += 1
        for signal in item.context_json.get("signals", []):
            cleaned = _clean(signal, "")
            if cleaned:
                scores[cleaned] += direction
    preferred = [
        signal
        for signal, score in sorted(scores.items(), key=lambda item: (-item[1], item[0]))
        if score > 0
    ][:FEEDBACK_SIGNAL_LIMIT]
    avoided = [
        signal
        for signal, score in sorted(scores.items(), key=lambda item: (item[1], item[0]))
        if score < 0
    ][:FEEDBACK_SIGNAL_LIMIT]
    parts = [
        f"参考当前用户对同类“{context['category']} / {'、'.join(context['scenes'])}”成片的历史评价"
        f"（赞 {likes}，踩 {dislikes}）"
    ]
    if preferred:
        parts.append(f"优先延续“{'；'.join(preferred)}”")
    elif likes:
        parts.append("延续已获好评方案的动作克制、产品可见度与镜头节奏")
    if avoided:
        parts.append(f"避免重复“{'；'.join(avoided)}”")
    elif dislikes:
        parts.append("不要机械复用获差评方案，调整动作幅度、镜头运动和切镜节奏")
    return "；".join(parts) + "。"


async def load_feedback_guidance(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    analysis_result: dict[str, Any],
) -> dict[VariantKind, str]:
    result: dict[VariantKind, str] = {}
    for kind in VariantKind:
        context = feedback_context(analysis_result, kind)
        history = list(
            await session.scalars(
                select(GenerationFeedback)
                .where(
                    GenerationFeedback.user_id == user_id,
                    GenerationFeedback.scene_key == context["sceneKey"],
                )
                .order_by(GenerationFeedback.updated_at.desc())
                .limit(FEEDBACK_HISTORY_LIMIT)
            )
        )
        result[kind] = _guidance_for_kind(context, history)
    return result
