import copy
import re
from dataclasses import dataclass
from typing import Any

from libtv_agent.domain.enums import VariantKind

PROMPT_TEMPLATE_VERSION = "1.3.0"
PROMPT_EXTENDED_MAX = 1600

_MOTION_REPLACEMENTS: tuple[tuple[str, str], ...] = (
    (r"\bspeed[\s-]?ramp(?:ing)?\b", "smooth constant-speed movement"),
    (r"\bwhip[\s-]?pan(?:ning)?\b", "gentle pan"),
    (r"\bfast[\s-]?tracking\b", "smooth tracking"),
    (r"\brapid(?:ly)?\b", "smoothly"),
    (r"\bquick(?:ly)?\b", "smoothly"),
    (r"\bfast\b", "controlled"),
    (r"\bbrisk(?:ly)?\b", "naturally"),
    (r"\bsudden(?:ly)?\b", "smoothly"),
    (r"速度渐变", "匀速运动"),
    (r"快速跟拍", "平稳跟随"),
    (r"快速推进", "平稳推进"),
    (r"快速推近", "平稳推近"),
    (r"快速移动", "自然移动"),
    (r"较快", "自然"),
    (r"快速|迅速|急速|疾速", "平稳"),
    (r"猛然|突然", "自然"),
    (r"甩镜", "平稳横移"),
)

_MIRROR_KEYWORDS = ("对镜", "镜子", "镜面", "mirror", "selfie")
_SEATED_KEYWORDS = ("坐姿", "坐着", "坐在", "seated", "sitting", "沙发", "椅子")
_OUTDOOR_KEYWORDS = (
    "室外",
    "户外",
    "街道",
    "公园",
    "广场",
    "海边",
    "outdoor",
    "street",
    "park",
    "plaza",
)
_ROOM_KEYWORDS = ("房间", "卧室", "客厅", "室内", "room", "bedroom", "indoor")
_DRESS_KEYWORDS = ("连衣裙", "半身裙", "裙装", "裙子", "dress", "skirt")
_JERSEY_KEYWORDS = ("球衣", "运动衫", "jersey", "sports shirt")
_TEE_KEYWORDS = (
    "短袖",
    "t恤",
    "t-shirt",
    "t shirt",
    "tee",
    "short-sleeve",
    "short sleeve",
)
_ACTION_QUALIFIER_PATTERN = re.compile(
    r"\b(?:small|slight|subtle|gentle|controlled|natural|smooth|visible|clear|"
    r"more|less|pronounced|restrained)\b|"
    r"轻微|小幅|稍微|略微|明显|清晰|自然|缓慢|平稳|克制|受控|更大|较大|较小",
    flags=re.IGNORECASE,
)


@dataclass(frozen=True)
class TimelineShot:
    start: float
    end: float
    reference_asset_ids: tuple[str, ...]
    action: str
    camera: str
    product_display: str
    shot_function: str


def calculate_timeline(
    shots: list[dict[str, Any]], total_seconds: float = 10.0
) -> list[TimelineShot]:
    if not shots:
        raise ValueError("at least one shot is required")
    weights = [float(shot.get("durationWeight", 0)) for shot in shots]
    if any(weight <= 0 for weight in weights):
        raise ValueError("durationWeight must be positive")
    total_weight = sum(weights)
    cursor = 0.0
    result: list[TimelineShot] = []
    for index, (shot, weight) in enumerate(zip(shots, weights, strict=True)):
        end = (
            total_seconds
            if index == len(shots) - 1
            else round(cursor + total_seconds * weight / total_weight, 1)
        )
        result.append(
            TimelineShot(
                start=cursor,
                end=end,
                reference_asset_ids=tuple(shot.get("referenceAssetIds", [])),
                action=str(shot.get("action", "presents the product naturally")),
                camera=str(shot.get("camera", "remains steady")),
                product_display=str(shot.get("productDisplay", "the garment details")),
                shot_function=str(shot.get("shotFunction", "product display")),
            )
        )
        cursor = end
    return result


def validate_required_coverage(timeline: list[TimelineShot], required_asset_ids: list[str]) -> None:
    covered = {asset_id for shot in timeline for asset_id in shot.reference_asset_ids}
    missing = [asset_id for asset_id in required_asset_ids if asset_id not in covered]
    if missing:
        raise ValueError(f"required storyboard assets are missing: {', '.join(missing)}")


def count_ab_differences(stable: list[TimelineShot], dynamic: list[TimelineShot]) -> int:
    comparisons = [
        stable[0].shot_function != dynamic[0].shot_function,
        [s.action for s in stable] != [s.action for s in dynamic],
        [s.camera for s in stable] != [s.camera for s in dynamic],
        [s.reference_asset_ids for s in stable] != [s.reference_asset_ids for s in dynamic],
        [s.end - s.start for s in stable] != [s.end - s.start for s in dynamic],
    ]
    return sum(comparisons)


def validate_ab_action_difference(stable: list[TimelineShot], dynamic: list[TimelineShot]) -> None:
    stable_actions = [_action_signature(shot.action) for shot in stable]
    dynamic_actions = [_action_signature(shot.action) for shot in dynamic]
    if stable_actions == dynamic_actions:
        raise ValueError("stable and dynamic plans must use visibly different person actions")


def _action_signature(text: str) -> str:
    without_qualifiers = _ACTION_QUALIFIER_PATTERN.sub("", normalize_motion_language(text))
    return re.sub(r"[\s,，。.!！？、;；:：-]+", "", without_qualifiers.casefold())


def normalize_motion_language(text: str) -> str:
    normalized = " ".join(text.split())
    for pattern, replacement in _MOTION_REPLACEMENTS:
        normalized = re.sub(pattern, replacement, normalized, flags=re.IGNORECASE)
    return normalized


def normalize_analysis_motion(payload: dict[str, Any]) -> dict[str, Any]:
    normalized = copy.deepcopy(payload)
    for plan_name in ("stablePlan", "dynamicPlan"):
        plan = normalized.get(plan_name)
        if not isinstance(plan, dict):
            continue
        for shot in plan.get("shots", []):
            if not isinstance(shot, dict):
                continue
            for field in ("action", "camera", "shotFunction"):
                value = shot.get(field)
                if isinstance(value, str):
                    shot[field] = normalize_motion_language(value)
    return normalized


def select_mode_type(storyboard_count: int, schema: dict[str, Any]) -> str:
    if storyboard_count < 1 or storyboard_count > min(7, int(schema.get("maxMediaCount", 7))):
        raise ValueError("storyboard count is incompatible with realtime schema")
    preferred = "singleImage2video" if storyboard_count == 1 else "mixed2video"
    if preferred not in schema.get("modeTypes", ["singleImage2video", "mixed2video"]):
        raise ValueError(f"modeType {preferred} is not supported")
    return preferred


def compress_prompt(text: str, max_chars: int) -> str:
    normalized = " ".join(text.split())
    if len(normalized) <= max_chars:
        return normalized
    sentences = [
        part.strip() for part in re.findall(r".+?(?:[。.!?！？]+|$)", normalized) if part.strip()
    ]
    kept: list[str] = []
    for sentence in sentences:
        candidate = " ".join([*kept, sentence])
        if len(candidate) > max_chars:
            break
        kept.append(sentence)
    return " ".join(kept) if kept else normalized[: max_chars - 3].rstrip() + "..."


def _contains_any(text: str, keywords: tuple[str, ...]) -> bool:
    lowered = text.casefold()
    return any(keyword.casefold() in lowered for keyword in keywords)


def _garment_motion_guidance(category: str) -> str:
    if _contains_any(category, _DRESS_KEYWORDS):
        return (
            "裙装模特以原地重心变化、手臂动作和小角度转向为主，最多缓慢移动半步；"
            "不得连续走动或交叉步；不得旋转甩裙、拉扯裙摆或制造大幅布料摆动。"
            "裙摆自然轻微响应后立即稳定，不得出现果冻式波动。"
        )
    if _contains_any(category, _JERSEY_KEYWORDS):
        return (
            "球衣可使用比裙装更清晰的站姿切换、一至两步自然位移和肩部动作；"
            "号码、标识和文字保持正面可读，只能使用参考图中确实存在的运动道具。"
        )
    if _contains_any(category, _TEE_KEYWORDS):
        return (
            "短袖可使用自然重心切换、小步位移、肩部转向、手臂展开或短暂触碰侧下摆"
            "来避免单调；手臂不得遮挡胸前印花或文字。"
        )
    return (
        "动作幅度依据服装结构、松散面料、文字标识风险和场景空间确定，"
        "不得为了区分版本而加快人物或镜头速度。"
    )


def _fact_text(fact: dict[str, Any]) -> str:
    values: list[str] = []
    for field in ("scene", "framing", "pose"):
        value = fact.get(field)
        if isinstance(value, str):
            values.append(value)
    for field in ("actionCandidates", "interactionObjects"):
        value = fact.get(field)
        if isinstance(value, list):
            values.extend(str(item) for item in value)
    return " ".join(values)


def _shot_scene_guidance(
    reference_asset_ids: tuple[str, ...],
    facts_by_asset: dict[str, dict[str, Any]],
    garment_category: str,
) -> str:
    facts = [
        facts_by_asset[asset_id] for asset_id in reference_asset_ids if asset_id in facts_by_asset
    ]
    if not facts:
        return "动作必须保持在对应参考图可见空间内，不发明画外移动或新道具。"
    combined = " ".join(_fact_text(fact) for fact in facts)
    guidance: list[str] = []
    if _contains_any(combined, _MIRROR_KEYWORDS):
        guidance.append(
            "对镜动作保持在镜面范围内，并保持手机、手臂、倒影和人物关系稳定，不使用第三人称跟拍"
        )
    if _contains_any(combined, _SEATED_KEYWORDS):
        guidance.append("保持坐姿，用姿态、身体朝向、手臂位置和景别变化区分版本")
    elif _contains_any(garment_category, _DRESS_KEYWORDS):
        guidance.append("裙装保持原地或最多缓慢移动半步，用姿态和景别切镜形成变化")
    elif _contains_any(combined, _OUTDOOR_KEYWORDS):
        guidance.append("室外或空旷场景允许更大的自然移动范围和景别切镜，但全程匀速")
    elif _contains_any(combined, _ROOM_KEYWORDS):
        guidance.append("室内动作限制在可见地面范围内，最多使用一至两步自然位移")
    else:
        guidance.append("动作范围以参考图实际可见空间和当前姿势为上限")
    return "动作边界：" + "；".join(guidance) + "。"


def _truncate_clean(text: str, limit: int) -> str:
    normalized = " ".join(text.split())
    if len(normalized) <= limit:
        return normalized
    if limit <= 1:
        return "…"
    candidate = normalized[: limit - 1].rstrip(" ,，。.!！？、;；:")
    return candidate + "…"


def _allocate_field_limits(values: list[str], budget: int) -> list[int]:
    if not values:
        return []
    limits = [0] * len(values)
    remaining = max(len(values), budget)
    active = {index for index, value in enumerate(values) if value}
    while remaining > 0 and active:
        share = max(1, remaining // len(active))
        progressed = False
        for index in tuple(active):
            needed = len(values[index]) - limits[index]
            addition = min(needed, share, remaining)
            limits[index] += addition
            remaining -= addition
            progressed = progressed or addition > 0
            if limits[index] >= len(values[index]):
                active.discard(index)
            if remaining <= 0:
                break
        if not progressed:
            break
    return [max(1, limit) for limit in limits]


def _render_bounded_shot(
    index: int,
    shot: TimelineShot,
    scene_guidance: str,
    max_chars: int,
) -> str:
    prefix = f"镜头 {index}（{shot.start:.1f}-{shot.end:.1f} 秒）："
    labels = ("功能", "；模特", "；镜头", "；展示", "；")
    values = [
        shot.shot_function,
        shot.action,
        shot.camera,
        shot.product_display,
        scene_guidance,
    ]
    value_budget = max(
        len(values),
        max_chars - len(prefix) - sum(len(label) for label in labels),
    )
    limits = _allocate_field_limits(values, value_budget)
    rendered = prefix + "".join(
        f"{label}{_truncate_clean(value, limit)}"
        for label, value, limit in zip(labels, values, limits, strict=True)
    )
    return _truncate_clean(rendered, max_chars)


def render_prompt(
    kind: VariantKind,
    timeline: list[TimelineShot],
    node_names: list[str],
    user_requirement: str,
    max_chars: int = PROMPT_EXTENDED_MAX,
    feedback_guidance: str = "",
    *,
    garment_category: str = "",
    storyboard_facts: list[dict[str, Any]] | None = None,
) -> str:
    references = ", ".join(f'{{{{Node "{name}"}}}}' for name in node_names)
    facts_by_asset = {
        str(fact.get("assetId")): fact
        for fact in (storyboard_facts or [])
        if isinstance(fact, dict) and fact.get("assetId")
    }
    intro_lines = [
        "生成一条 10 秒、9:16 竖版 UGC 视频，采用真实 iPhone 后置摄像头的曝光、"
        "透视和克制的手持运动。",
        f"使用 {references} 作为场景、模特和服装身份的完整有序分镜参考。",
        "严格遵循上传参考图的顺序，不跳过、合并或重排镜头。",
        "全程保持同一模特、服装、颜色、印花、文字、场景身份、版型和面料结构。",
        "将服装印花、文字和缝线视为锁定在布料表面的固定纹理；逐帧保持位置、尺度和形状连续，"
        "不得爬行、漂移、闪烁、抖动或局部伸缩，时序一致性优先于夸张布料模拟。",
        _garment_motion_guidance(garment_category),
    ]
    motion_instruction = (
        "稳定版不是静止版：使用克制但可见的人物动作、平滑转场和自然身体力学，"
        "动作完成后保留清晰稳定的商品展示。"
        if kind == VariantKind.STABLE
        else "动态版与稳定版保持接近的自然速度，通过明显不同的人物动作、身体朝向、"
        "可行移动轨迹和景别切镜形成差异，不通过快速移动或快速跟拍增强节奏。"
    )
    closing_lines = [
        motion_instruction,
        "相邻镜头仅在景别、方向和姿势连续时自然衔接，否则使用干净硬切，不做变形过渡。",
        "保持背景和光线一致，只使用服装原有印花、标识和文字，不添加字幕或贴纸。",
        "避免身份、肢体、手部、服装细节和背景变形，以及突然变焦和明显 AI 瑕疵。",
    ]
    if user_requirement.strip():
        safe_requirement = user_requirement.replace("{{", "{").replace("}}", "}").strip()
        closing_lines.append(f"用户要求：{_truncate_clean(safe_requirement, 240)}。")
    if feedback_guidance.strip():
        safe_guidance = normalize_motion_language(
            feedback_guidance.replace("{{", "{").replace("}}", "}").strip()
        )
        closing_lines.append(f"同类场景反馈优化：{_truncate_clean(safe_guidance, 240)}")
    closing_lines.append(
        "硬约束：全片人物与镜头保持自然匀速；版本差异必须来自人物动作，"
        "并服从每张参考图的实际空间、姿势、服装和道具边界。"
    )
    fixed_lines = [*intro_lines, *closing_lines]
    separator_count = len(fixed_lines) + len(timeline) - 1
    shots_budget = max_chars - sum(len(line) for line in fixed_lines) - separator_count
    if shots_budget <= len(timeline):
        fallback = " ".join(
            [
                *intro_lines,
                *(
                    f"镜头 {index}：{shot.shot_function}；模特{shot.action}；"
                    f"镜头{shot.camera}；展示{shot.product_display}。"
                    for index, shot in enumerate(timeline, start=1)
                ),
                *closing_lines,
            ]
        )
        return compress_prompt(fallback, max_chars)
    base_shot_budget, remainder = divmod(shots_budget, len(timeline))
    shot_lines = [
        _render_bounded_shot(
            index,
            shot,
            _shot_scene_guidance(shot.reference_asset_ids, facts_by_asset, garment_category),
            base_shot_budget + (1 if index <= remainder else 0),
        )
        for index, shot in enumerate(timeline, start=1)
    ]
    return " ".join([*intro_lines, *shot_lines, *closing_lines])[:max_chars]
