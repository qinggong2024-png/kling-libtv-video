from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import asdict, dataclass
from enum import StrEnum
from typing import Literal

ActionCategory = Literal["outfit", "detail", "back", "interaction", "product"]
ActionRiskLevel = Literal["low", "conditional"]
LibraryScope = Literal["general", "brand"]


class ActionCapability(StrEnum):
    """Facts that must be confirmed from the input before an action is safe."""

    FORWARD_STEP_SPACE = "forward_step_space"
    WALK_DEPTH = "walk_depth"
    LATERAL_STEP_SPACE = "lateral_step_space"
    OPEN_ENTRY_SPACE = "open_entry_space"
    HORIZONTAL_MOVEMENT_SPACE = "horizontal_movement_space"
    DIAGONAL_STEP_SPACE = "diagonal_step_space"
    COMPOSITION_REPOSITIONING = "composition_repositioning"
    FRONT_PRINT_VISIBLE = "front_print_visible"
    FREE_HAND = "free_hand"
    SAFE_HAND_PATH = "safe_hand_path"
    HEM_REACHABLE = "hem_reachable"
    HEM_CLEAR = "hem_clear"
    PRINT_OUTSIDE_STRETCH_AREA = "print_outside_stretch_area"
    SAFE_FABRIC_AREA = "safe_fabric_area"
    SLEEVE_OR_SHOULDER_VISIBLE = "sleeve_or_shoulder_visible"
    FACE_GAZE_ADJUSTABLE = "face_gaze_adjustable"
    HAIR_REACHABLE = "hair_reachable"
    COLLAR_VISIBLE = "collar_visible"
    OPENABLE_OUTER_LAYER = "openable_outer_layer"
    INNER_LAYER_VISIBLE = "inner_layer_visible"
    POCKET_VISIBLE = "pocket_visible"
    CUFFS_AND_HANDS_VISIBLE = "cuffs_and_hands_visible"
    CROSS_CUFF_REACHABLE = "cross_cuff_reachable"
    LAYERED_GARMENT = "layered_garment"
    LAYER_BOUNDARIES_CLEAR = "layer_boundaries_clear"
    LONG_OR_LOOSE_HEM = "long_or_loose_hem"
    BACK_REFERENCE = "back_reference"
    OVER_SHOULDER_GAZE_SAFE = "over_shoulder_gaze_safe"
    FACE_VISIBLE = "face_visible"
    MIRROR_SELFIE = "mirror_selfie"
    PHONE_HOLD_VISIBLE = "phone_hold_visible"
    SEATED_POSE = "seated_pose"
    SEAT_VISIBLE = "seat_visible"
    LOWER_BODY_PATH_VISIBLE = "lower_body_path_visible"
    STANDING_SPACE = "standing_space"
    SUPPORT_SURFACE = "support_surface"
    HANDHELD_UNWORN_PRODUCT = "handheld_unworn_product"
    PACKAGING_OR_PRODUCT_SURFACE = "packaging_or_product_surface"
    EXISTING_PROP = "existing_prop"
    PROP_PICKUP_SAFE = "prop_pickup_safe"
    GARMENT_FASTENER_VISIBLE = "garment_fastener_visible"
    WAISTLINE_VISIBLE = "waistline_visible"
    LOWER_GARMENT_VISIBLE = "lower_garment_visible"
    TROUSER_CUFF_REACHABLE = "trouser_cuff_reachable"
    SKIRT_SLIT_VISIBLE = "skirt_slit_visible"
    FOOTWEAR_VISIBLE = "footwear_visible"
    STAIR_VISIBLE = "stair_visible"
    STAIR_PATH_CLEAR = "stair_path_clear"
    SEAT_APPROACH_CLEAR = "seat_approach_clear"
    COMPANION_PRESENT = "companion_present"
    SHARED_MOVEMENT_SPACE = "shared_movement_space"
    DOORWAY_VISIBLE = "doorway_visible"
    DOORWAY_PATH_CLEAR = "doorway_path_clear"


@dataclass(frozen=True)
class ActionContext:
    """Tri-state capability context.

    Capabilities absent from both sets are unknown. Unknown is deliberately not
    treated as true, so generated movement never assumes facts not established
    by the supplied material.
    """

    confirmed: frozenset[ActionCapability] = frozenset()
    denied: frozenset[ActionCapability] = frozenset()
    evidence_sets: tuple[frozenset[ActionCapability], ...] = ()

    def __post_init__(self) -> None:
        overlap = self.confirmed & self.denied
        if overlap:
            names = ", ".join(sorted(capability.value for capability in overlap))
            raise ValueError(f"action capabilities cannot be both confirmed and denied: {names}")

    @classmethod
    def from_values(
        cls,
        *,
        confirmed: Iterable[ActionCapability | str] = (),
        denied: Iterable[ActionCapability | str] = (),
    ) -> ActionContext:
        return cls(
            confirmed=frozenset(ActionCapability(value) for value in confirmed),
            denied=frozenset(ActionCapability(value) for value in denied),
        )

    def supports(self, capabilities: tuple[ActionCapability, ...]) -> bool:
        required = frozenset(capabilities)
        if not required:
            return True
        if self.evidence_sets:
            return any(required <= evidence for evidence in self.evidence_sets)
        return required <= self.confirmed


@dataclass(frozen=True)
class ActionEligibility:
    allowed: bool
    missing: tuple[ActionCapability, ...] = ()
    denied: tuple[ActionCapability, ...] = ()


@dataclass(frozen=True)
class MotionAction:
    id: str
    label: str
    category: ActionCategory
    instruction: str
    purpose: str
    compatible_templates: tuple[str, ...]
    requirements: tuple[str, ...] = ()
    required_capabilities: tuple[ActionCapability, ...] = ()
    avoid: tuple[str, ...] = ()
    risk_level: ActionRiskLevel = "low"
    library_scope: LibraryScope = "general"
    brand_id: str | None = None
    base_action_id: str | None = None

    def to_public_dict(self) -> dict[str, object]:
        value = asdict(self)
        value["compatibleTemplates"] = value.pop("compatible_templates")
        value["requiredCapabilities"] = [
            capability.value for capability in self.required_capabilities
        ]
        value.pop("required_capabilities")
        value["riskLevel"] = value.pop("risk_level")
        value["libraryScope"] = value.pop("library_scope")
        value["brandId"] = value.pop("brand_id")
        value["baseActionId"] = value.pop("base_action_id")
        return value


ACTION_LIBRARY: dict[str, MotionAction] = {
    "stance_shift": MotionAction(
        "stance_shift",
        "重心换脚停留",
        "outfit",
        "从自然站姿开始，将重心缓慢移到一侧，肩部随之轻微调整；停稳后保持全身穿搭清晰、商品区域无遮挡。",
        "用最小动作建立自然感，同时稳定展示整体版型。",
        ("ootd_walk", "garment_detail", "mood_model"),
        avoid=("连续左右晃动", "肩胯大幅扭转"),
    ),
    "one_step_settle": MotionAction(
        "one_step_settle",
        "向前一步停稳",
        "outfit",
        "从原位自然向前一步，脚步落地后立即停稳；结束时保持主体居中，胸前与衣摆完整可见。",
        "用一次短位移改变构图，不持续逼近镜头。",
        ("ootd_walk", "mood_model"),
        requirements=("画面前方留有一步安全空间",),
        required_capabilities=(ActionCapability.FORWARD_STEP_SPACE,),
        avoid=("连续走近镜头", "跨出画面"),
    ),
    "controlled_walk": MotionAction(
        "controlled_walk",
        "受控走动",
        "outfit",
        "从画面内稳定站姿开始，向镜头方向走两到三步，步幅均匀；走完后停稳并让服装轮廓完整回到画面中心。",
        "展示服装在自然步态中的垂坠与整体轮廓。",
        ("ootd_walk", "mood_model"),
        requirements=("画面具有两到三步纵深",),
        required_capabilities=(ActionCapability.WALK_DEPTH,),
        avoid=("奔跑", "突然冲近镜头", "边走边快速转身"),
        risk_level="conditional",
    ),
    "controlled_side_step": MotionAction(
        "controlled_side_step",
        "受控侧移",
        "outfit",
        "从稳定站姿向侧面移动一步并重新站定，肩线保持自然；结束时让服装完整进入画面。",
        "通过横向构图变化展示宽松版型与环境关系。",
        ("mood_model", "ootd_walk"),
        requirements=("侧方留有一步空间",),
        required_capabilities=(ActionCapability.LATERAL_STEP_SPACE,),
        avoid=("横穿画面", "交叉步过快"),
        risk_level="conditional",
    ),
    "walk_in_stop": MotionAction(
        "walk_in_stop",
        "入画后定姿",
        "outfit",
        "从画面边缘自然入画，以两到三步到达中心位置；停下后完成一次稳定定姿并保持整件服装清晰。",
        "为开放空间视频提供明确的进入动作与商品建立镜头。",
        ("ootd_walk", "mood_model"),
        requirements=("输入分镜支持开放空间或边缘入画",),
        required_capabilities=(ActionCapability.OPEN_ENTRY_SPACE,),
        avoid=("从画外高速冲入", "入画后继续无目的走动"),
        risk_level="conditional",
    ),
    "walk_past_glance": MotionAction(
        "walk_past_glance",
        "小范围经过回望",
        "outfit",
        "在画面内小范围经过镜头视线，经过时短暂看向镜头；随后减速停留，让服装轮廓重新清晰可见。",
        "增强氛围感，同时保留商品确认时刻。",
        ("mood_model",),
        requirements=("画面有横向移动空间",),
        required_capabilities=(ActionCapability.HORIZONTAL_MOVEMENT_SPACE,),
        avoid=("完全走出画面", "长距离跟拍", "高速甩头"),
        risk_level="conditional",
    ),
    "three_quarter_turn": MotionAction(
        "three_quarter_turn",
        "三分之四转身",
        "outfit",
        "从正面稳定姿态缓慢转到三分之四侧面，双脚自然调整后停留；结束时同时保留正面图案与侧面版型。",
        "在不整圈旋转的前提下展示正侧关系。",
        ("ootd_walk", "garment_detail", "mood_model"),
        avoid=("整圈旋转", "转身过程中抬手遮挡商品"),
    ),
    "torso_angle_hold": MotionAction(
        "torso_angle_hold",
        "上身侧角停留",
        "outfit",
        "保持脚步稳定，上身向一侧转动小角度并停留；让正面图案与侧面廓形同时可见，再自然回正。",
        "在空间有限时补充正侧关系。",
        ("ootd_walk", "garment_detail", "mood_model"),
        avoid=("腰部大幅扭转", "衣物被手臂遮挡"),
    ),
    "diagonal_step_turn": MotionAction(
        "diagonal_step_turn",
        "斜前一步侧身定姿",
        "outfit",
        "从稳定站姿向斜前方迈一步，落脚后将身体缓慢转到三分之四侧面并停稳；结束时正面图案与侧面版型同时可见。",
        "用一次连贯的小范围位移同时改变人物位置和商品展示角度。",
        ("ootd_walk", "mood_model"),
        requirements=("斜前方留有一步空间", "输入构图允许主体位置发生小幅变化"),
        required_capabilities=(
            ActionCapability.DIAGONAL_STEP_SPACE,
            ActionCapability.COMPOSITION_REPOSITIONING,
        ),
        avoid=("交叉步", "连续转身", "迈步过程中冲近镜头"),
        risk_level="conditional",
    ),
    "print_detail_pause": MotionAction(
        "print_detail_pause",
        "印花稳定停留",
        "detail",
        "从整体画面平稳切入或推进到输入中已有的印花区域，保持短暂停留；结束后回到能确认商品轮廓的景别。",
        "确保印花、Logo 或文字获得可读的展示时间。",
        ("garment_detail", "ootd_walk", "mood_model"),
        requirements=("输入画面中印花区域清晰可见",),
        required_capabilities=(ActionCapability.FRONT_PRINT_VISIBLE,),
        avoid=("重新绘制图案", "用景深或特效遮挡文字"),
    ),
    "print_indicate_release": MotionAction(
        "print_indicate_release",
        "指向印花后放下",
        "detail",
        "从自然手位开始，用手指或掌缘短暂指向主要印花，停留片刻后自然放下；结束时印花完整无遮挡。",
        "用一次明确手势引导视线到商品主题。",
        ("garment_detail", "ootd_walk"),
        requirements=("输入中已有可用手位", "指向路径不会跨过脸部"),
        required_capabilities=(ActionCapability.FREE_HAND, ActionCapability.SAFE_HAND_PATH),
        avoid=("持续触摸印花", "手掌覆盖文字", "凭空新增手势"),
        risk_level="conditional",
    ),
    "hem_adjust": MotionAction(
        "hem_adjust",
        "衣摆轻触整理",
        "detail",
        "从已有自然手位轻触无印花区域的衣摆一次，立即放回；结束时肩线、下摆和主要图案保持完整。",
        "补充真实穿着细节，并展示衣摆位置。",
        ("garment_detail", "ootd_walk", "mood_model"),
        requirements=("输入中已有接近衣摆的自然手位",),
        required_capabilities=(ActionCapability.FREE_HAND, ActionCapability.HEM_REACHABLE),
        avoid=("反复摸衣服", "遮挡主要印花", "大幅拉扯下摆"),
        risk_level="conditional",
    ),
    "hem_open_release": MotionAction(
        "hem_open_release",
        "轻展衣摆后释放",
        "detail",
        "从自然垂手开始，单手或双手轻轻向外展开衣摆，展示宽松量后立即释放；结束时衣摆自然垂落。",
        "展示宽松版型与衣身宽度。",
        ("garment_detail", "ootd_walk"),
        requirements=("衣摆区域无遮挡", "主要印花不跨越拉伸区域"),
        required_capabilities=(
            ActionCapability.FREE_HAND,
            ActionCapability.HEM_CLEAR,
            ActionCapability.PRINT_OUTSIDE_STRETCH_AREA,
        ),
        avoid=("用力拉伸", "长时间扯住衣摆", "拉扯印花"),
        risk_level="conditional",
    ),
    "fabric_pinch_release": MotionAction(
        "fabric_pinch_release",
        "轻捏面料后释放",
        "detail",
        "在没有文字或图案的安全区域轻捏少量面料，短暂停留后放开；结束时面料自然恢复且纹理稳定。",
        "用低幅度动作表达面料厚薄与柔软度。",
        ("garment_detail",),
        requirements=("存在无文字、无 Logo 的安全面料区域",),
        required_capabilities=(
            ActionCapability.FREE_HAND,
            ActionCapability.SAFE_FABRIC_AREA,
        ),
        avoid=("揉搓面料", "拉伸网眼或印花", "大面积抓握"),
        risk_level="conditional",
    ),
    "sleeve_detail_pause": MotionAction(
        "sleeve_detail_pause",
        "袖口肩线展示",
        "detail",
        "从自然垂手轻抬手臂，短暂展示袖口、肩线或滚边结构；随后手臂回到自然位置并保持面料纹理稳定。",
        "突出袖口、肩线、滚边或针织结构。",
        ("garment_detail", "ootd_walk"),
        requirements=("袖口或肩线在输入中清晰可见",),
        required_capabilities=(ActionCapability.SLEEVE_OR_SHOULDER_VISIBLE,),
        avoid=("手臂举过头顶", "快速挥手", "遮挡胸前图案"),
    ),
    "graphic_glance_return": MotionAction(
        "graphic_glance_return",
        "低头看印花后回望",
        "detail",
        "从自然视线开始，低头短暂看向胸前已有印花或文字，再缓慢抬眼回到镜头；身体保持稳定，结束时图案完整可读。",
        "不用手部接触即可把观众注意力引导到胸前商品信息。",
        ("garment_detail", "ootd_walk", "mood_model"),
        requirements=("胸前图案或文字在输入中清晰可见", "人物面部与颈部允许小幅视线变化"),
        required_capabilities=(
            ActionCapability.FRONT_PRINT_VISIBLE,
            ActionCapability.FACE_GAZE_ADJUSTABLE,
        ),
        avoid=("大幅低头遮挡图案", "快速甩头", "改变面部身份"),
        risk_level="conditional",
    ),
    "collar_frame_release": MotionAction(
        "collar_frame_release",
        "领口轻触后放下",
        "detail",
        "从靠近上身的自然手位开始，用指尖短暂轻触领口边缘，展示领型后立即放下；结束时领口、胸前图案与肩线保持完整。",
        "突出领型、包边或领口做工，同时保留胸前商品信息。",
        ("garment_detail", "ootd_walk"),
        requirements=("领口在输入中清晰可见", "输入已有接近领口的自然手位"),
        required_capabilities=(
            ActionCapability.COLLAR_VISIBLE,
            ActionCapability.FREE_HAND,
            ActionCapability.SAFE_HAND_PATH,
        ),
        avoid=("拉扯领口", "手掌遮挡胸前图案", "触碰颈部或面部"),
        risk_level="conditional",
    ),
    "lapel_open_hold": MotionAction(
        "lapel_open_hold",
        "轻展衣襟停留",
        "detail",
        "从外层衣服自然闭合或垂落的状态开始，用一只手轻展已有衣襟并短暂停留；随后释放，让外层自然回落。",
        "展示外套、衬衫或开衫的衣襟结构与已有内搭。",
        ("garment_detail", "ootd_walk", "mood_model"),
        requirements=("输入明确存在可展开的外层服装", "内搭在输入中已经可见"),
        required_capabilities=(
            ActionCapability.FREE_HAND,
            ActionCapability.OPENABLE_OUTER_LAYER,
            ActionCapability.INNER_LAYER_VISIBLE,
        ),
        avoid=("凭空新增内搭", "把闭合服装改造成开衫", "双手大幅拉开衣服"),
        risk_level="conditional",
    ),
    "pocket_insert_release": MotionAction(
        "pocket_insert_release",
        "单手入袋后抽回",
        "detail",
        "从手臂自然下垂开始，将一只手缓慢放入输入中已有的口袋并短暂停留；随后自然抽回，结束时服装轮廓恢复清晰。",
        "展示口袋位置、服装松量与自然穿着状态。",
        ("ootd_walk", "mood_model"),
        requirements=("输入中口袋位置明确可见", "手部到口袋的路径无遮挡"),
        required_capabilities=(
            ActionCapability.FREE_HAND,
            ActionCapability.POCKET_VISIBLE,
            ActionCapability.SAFE_HAND_PATH,
        ),
        avoid=("凭空生成口袋", "双手同时插袋", "手部穿过衣物"),
        risk_level="conditional",
    ),
    "cuff_adjust_release": MotionAction(
        "cuff_adjust_release",
        "袖口整理后释放",
        "detail",
        "从双手自然分开的姿态开始，一只手轻触另一侧已有袖口并做一次小幅整理；随即放开，双手回到自然位置。",
        "展示袖口、滚边、罗纹或衬衫袖的结构细节。",
        ("garment_detail", "ootd_walk"),
        requirements=("双手和袖口在输入中清晰可见", "手部能够自然到达另一侧袖口"),
        required_capabilities=(
            ActionCapability.FREE_HAND,
            ActionCapability.CUFFS_AND_HANDS_VISIBLE,
            ActionCapability.CROSS_CUFF_REACHABLE,
        ),
        avoid=("反复卷袖", "手指穿过袖口", "双臂交叉遮挡胸前图案"),
        risk_level="conditional",
    ),
    "layer_reveal_return": MotionAction(
        "layer_reveal_return",
        "叠穿展开后复位",
        "detail",
        "保持输入中的叠穿关系，用一只手轻轻展开外层衣襟，让已有内搭短暂完整可见；随后释放外层并回到原始穿着状态。",
        "在不更换服装的前提下展示外层与内搭的搭配关系。",
        ("garment_detail", "ootd_walk", "mood_model"),
        requirements=("输入明确包含外层与内搭", "内外层边界和颜色关系清晰"),
        required_capabilities=(
            ActionCapability.FREE_HAND,
            ActionCapability.LAYERED_GARMENT,
            ActionCapability.LAYER_BOUNDARIES_CLEAR,
        ),
        avoid=("新增或替换内搭", "改变纽扣或拉链状态", "外层长时间遮挡主要商品"),
        risk_level="conditional",
    ),
    "garment_sway_settle": MotionAction(
        "garment_sway_settle",
        "衣摆轻摆后垂落",
        "detail",
        "从稳定站姿开始，通过一次小幅侧向重心变化让裙摆、长外套或宽松衣摆自然轻摆；动作停止后等待面料完全垂落。",
        "展示长下摆的垂坠、层次与自然物理反馈。",
        ("ootd_walk", "garment_detail", "mood_model"),
        requirements=("输入服装具有可见的长下摆或宽松垂坠结构",),
        required_capabilities=(ActionCapability.LONG_OR_LOOSE_HEM,),
        avoid=("用手甩动衣服", "快速旋转", "让印花或文字持续变形"),
        risk_level="conditional",
    ),
    "back_reveal": MotionAction(
        "back_reveal",
        "背面展示停留",
        "back",
        "从三分之四侧面缓慢转到背面并停留，不继续整圈旋转；结束时背部印花、肩线与衣摆完整清晰。",
        "展示输入中已经存在的背面结构与图案。",
        ("ootd_walk", "garment_detail"),
        requirements=("输入包含可靠的背面分镜",),
        required_capabilities=(ActionCapability.BACK_REFERENCE,),
        avoid=("无背面参考时凭空生成", "手臂遮挡背部印花", "连续旋转"),
        risk_level="conditional",
    ),
    "over_shoulder_back": MotionAction(
        "over_shoulder_back",
        "背面回望",
        "back",
        "保持背面朝向镜头，头部小幅越肩回看；身体与背部服装保持稳定，停留后自然将视线移开。",
        "在人镜交流中继续保持背部商品信息完整。",
        ("ootd_walk", "mood_model"),
        requirements=("输入包含可靠背面分镜", "头肩关系允许自然回望"),
        required_capabilities=(
            ActionCapability.BACK_REFERENCE,
            ActionCapability.OVER_SHOULDER_GAZE_SAFE,
        ),
        avoid=("头部过度扭转", "肩部抬起遮挡图案"),
        risk_level="conditional",
    ),
    "front_back_quarter_return": MotionAction(
        "front_back_quarter_return",
        "正背短停回望",
        "back",
        "从正面稳定站姿开始，自然转到背面并短暂停留，背面展示不超过动作总时长的四分之一；随后小幅越肩回看镜头并自然回到三分之四侧面，服装随转身自然摆动且全程连续。",
        "在一个连贯动作中展示正面、背面结构与人镜交流，同时避免背面停留喧宾夺主。",
        ("ootd_walk", "mood_model"),
        requirements=("输入包含可靠的背面分镜", "头肩关系允许自然回望"),
        required_capabilities=(
            ActionCapability.BACK_REFERENCE,
            ActionCapability.OVER_SHOULDER_GAZE_SAFE,
        ),
        avoid=("无背面参考时凭空生成", "整圈旋转", "转身跳变", "背面停留过久"),
        risk_level="conditional",
    ),
    "controlled_gaze": MotionAction(
        "controlled_gaze",
        "视线移回镜头",
        "interaction",
        "从画面外的自然视线开始，缓慢将视线移回镜头并短暂停留；身体保持稳定，随后自然移开视线。",
        "在不增加肢体风险的情况下建立人镜交流。",
        ("ootd_walk", "mood_model"),
        avoid=("突然甩头", "冻结表情", "改变面部身份"),
    ),
    "eye_contact_soft_smile": MotionAction(
        "eye_contact_soft_smile",
        "自然微笑对视",
        "interaction",
        "从自然中性表情开始，短暂看向镜头并形成轻微自然微笑；停留后恢复放松表情，身体与服装保持稳定。",
        "营造亲和、可信的面对镜头交流感。",
        ("ootd_walk", "mood_model"),
        requirements=("输入人物面部清晰且表情允许微调",),
        required_capabilities=(
            ActionCapability.FACE_VISIBLE,
            ActionCapability.FACE_GAZE_ADJUSTABLE,
        ),
        avoid=("夸张大笑", "牙齿或口型重绘", "长时间冻结微笑"),
        risk_level="conditional",
    ),
    "asymmetric_pause": MotionAction(
        "asymmetric_pause",
        "不对称停格",
        "interaction",
        "从稳定站姿做一次轻微肩胯错位停格，形成不对称构图后停留；随后回到自然站姿，不扭曲身体或衣物。",
        "用构图与节奏制造怪诞或编辑感，而不是依赖特效。",
        ("mood_model", "ootd_walk"),
        avoid=("大幅折叠身体", "身体变形", "连续摇摆"),
    ),
    "head_shoulder_tilt": MotionAction(
        "head_shoulder_tilt",
        "头肩轻倾",
        "interaction",
        "从头肩回正姿态开始，头部与肩部做小幅同向倾斜并短暂停留；随后自然回正。",
        "用低风险姿态变化增加人物表现力。",
        ("mood_model", "ootd_walk"),
        avoid=("颈部过度弯折", "头肩反向剧烈摆动"),
    ),
    "hair_tuck_release": MotionAction(
        "hair_tuck_release",
        "轻整发丝后复位",
        "interaction",
        "从自然手位开始，用一只手轻整理脸侧已有发丝或将其轻拨到耳后，随即放下手臂并回到放松姿态；脸部身份、发型轮廓和服装始终保持稳定。",
        "增加日常 UGC 的自然交流感，并避免大幅手势遮挡脸部或服装。",
        ("ootd_walk", "mood_model"),
        requirements=("输入中脸侧发丝与可用手位清晰", "手部到发丝的路径不会遮挡主要商品区域"),
        required_capabilities=(
            ActionCapability.FREE_HAND,
            ActionCapability.SAFE_HAND_PATH,
            ActionCapability.FACE_VISIBLE,
            ActionCapability.HAIR_REACHABLE,
        ),
        avoid=("改变发型或发色", "手掌遮住脸部", "反复拨弄头发", "手臂遮挡主要印花"),
        risk_level="conditional",
    ),
    "mirror_phone_hold": MotionAction(
        "mirror_phone_hold",
        "对镜持机稳定展示",
        "interaction",
        "保持输入中已有的持机手与手机位置稳定，只通过一次重心变化和小角度侧身展示服装；结束时手机与人物关系不变。",
        "适配镜面自拍场景，避免手机在动作中消失或换手。",
        ("ootd_walk", "mood_model"),
        requirements=("输入分镜明确为镜面自拍", "手机和持机手清晰可见"),
        required_capabilities=(
            ActionCapability.MIRROR_SELFIE,
            ActionCapability.PHONE_HOLD_VISIBLE,
        ),
        avoid=("手机换手或消失", "切换为第三人称跟拍", "双手同时离开手机"),
        risk_level="conditional",
    ),
    "seated_weight_shift": MotionAction(
        "seated_weight_shift",
        "坐姿重心调整",
        "interaction",
        "从输入中的稳定坐姿开始，身体重心小幅移向一侧，肩部自然跟随并短暂停留；随后回到居中坐姿，保持上身服装完整。",
        "在坐姿分镜中增加自然变化，并展示上身版型与环境关系。",
        ("garment_detail", "mood_model"),
        requirements=("输入明确包含稳定坐姿与已有座位", "座位边界和腿部位置清晰"),
        required_capabilities=(
            ActionCapability.SEATED_POSE,
            ActionCapability.SEAT_VISIBLE,
            ActionCapability.LOWER_BODY_PATH_VISIBLE,
        ),
        avoid=("改变座椅结构", "大幅交叉双腿", "身体离开座位"),
        risk_level="conditional",
    ),
    "lean_release": MotionAction(
        "lean_release",
        "轻靠环境后回正",
        "interaction",
        "从靠近已有墙面、桌边或栏杆的位置开始，身体轻靠支撑面并短暂停留；随后离开支撑面回到自然站姿。",
        "利用输入中已有环境制造姿态变化与更强的场景关系。",
        ("ootd_walk", "mood_model"),
        requirements=("输入中存在位置明确、可安全依靠的支撑面",),
        required_capabilities=(ActionCapability.SUPPORT_SURFACE,),
        avoid=("凭空新增支撑物", "身体穿过环境", "大幅后仰"),
        risk_level="conditional",
    ),
    "stand_from_seat_settle": MotionAction(
        "stand_from_seat_settle",
        "起身后停稳定姿",
        "interaction",
        "从输入中的自然坐姿开始，身体平稳起身并向前半步离开座位；完全站稳后保持整件服装清晰并完成定姿。",
        "用一次明确状态变化丰富开场或结尾，同时展示服装从坐姿到站姿的版型。",
        ("ootd_walk", "mood_model"),
        requirements=("输入明确包含坐姿、完整座位和足够起身空间", "下肢或起身路径可判断"),
        required_capabilities=(
            ActionCapability.SEATED_POSE,
            ActionCapability.SEAT_VISIBLE,
            ActionCapability.STANDING_SPACE,
            ActionCapability.LOWER_BODY_PATH_VISIBLE,
        ),
        avoid=("座位突然消失", "起身后快速离开画面", "手脚与座位交叠"),
        risk_level="conditional",
    ),
    "unbox_lift_front": MotionAction(
        "unbox_lift_front",
        "取出商品正面展示",
        "product",
        "从包装或桌面上的商品开始，双手固定肩部位置将衣服拿起，把正面转向镜头并停留；结束时商品完整展开。",
        "清楚区分手持商品与穿着状态，完成开箱正面展示。",
        ("garment_detail",),
        requirements=("输入分镜明确包含包装或手持未穿着商品",),
        required_capabilities=(
            ActionCapability.HANDHELD_UNWORN_PRODUCT,
            ActionCapability.PACKAGING_OR_PRODUCT_SURFACE,
        ),
        avoid=("把手持商品变成已穿着状态", "新增包装或桌面", "遮挡正面印花"),
        risk_level="conditional",
    ),
    "unbox_inspect_detail": MotionAction(
        "unbox_inspect_detail",
        "查看商品细节",
        "product",
        "保持手持商品状态，先低头查看已有细节，再将商品小幅转向镜头并停留；结束时双手继续稳定承托商品。",
        "为开箱场景补充真实检查动作与局部展示。",
        ("garment_detail",),
        requirements=("输入分镜明确包含手持未穿着商品",),
        required_capabilities=(ActionCapability.HANDHELD_UNWORN_PRODUCT,),
        avoid=("穿着状态与手持状态混淆", "大幅抖动商品", "凭空新增标签"),
        risk_level="conditional",
    ),
    "existing_prop_return": MotionAction(
        "existing_prop_return",
        "已有物件拿起放回",
        "product",
        "从手边已有物件的静止状态开始，单手将其自然拿起并完成一次短暂停留或查看；随后沿原路径放回原位，结束时人物和商品服装保持清晰。",
        "用输入中真实存在的书、杯子、包装或小件商品增加生活化场景互动。",
        ("garment_detail", "mood_model"),
        requirements=("输入中物件、手部和放置位置均清晰可见", "物件适合单手安全拿取"),
        required_capabilities=(
            ActionCapability.EXISTING_PROP,
            ActionCapability.FREE_HAND,
            ActionCapability.PROP_PICKUP_SAFE,
        ),
        avoid=("凭空新增或替换道具", "将物件递出画面", "物件遮挡主要服装图案"),
        risk_level="conditional",
    ),
    "seated_prop_sip_return": MotionAction(
        "seated_prop_sip_return",
        "坐姿饮用后放回",
        "interaction",
        "保持输入中的稳定坐姿，单手拿起手边已有的杯子或饮品，小口饮用一次后沿原路径放回原位；全程不站起、不掀动衣摆，结束时回到放松坐姿并保持服装清晰。",
        "为海边、咖啡馆或日常坐姿场景增加可信的生活化互动，同时保护服装与坐姿连续性。",
        ("mood_model",),
        requirements=("输入中已有可饮用物件、稳定座位和安全拿取路径", "手部与物件清晰可见"),
        required_capabilities=(
            ActionCapability.SEATED_POSE,
            ActionCapability.SEAT_VISIBLE,
            ActionCapability.EXISTING_PROP,
            ActionCapability.FREE_HAND,
            ActionCapability.PROP_PICKUP_SAFE,
        ),
        avoid=("凭空新增或替换饮品", "站起或离开座位", "掀动裙摆或衣摆", "饮品遮挡主要服装图案"),
        risk_level="conditional",
    ),
    "fastener_adjust_release": MotionAction(
        "fastener_adjust_release",
        "门襟扣件小幅整理",
        "detail",
        "从扣件与手部均清晰的稳定姿态开始，单手小幅调整一颗已有纽扣或一小段已有拉链后立即停下；结束时门襟、内搭和主要商品区域保持连续清晰。",
        "展示外套或上衣已有的纽扣、拉链与门襟结构。",
        ("garment_detail", "ootd_walk"),
        requirements=("输入中纽扣或拉链结构清晰可见", "单手路径不会遮挡主要图案"),
        required_capabilities=(
            ActionCapability.GARMENT_FASTENER_VISIBLE,
            ActionCapability.FREE_HAND,
            ActionCapability.SAFE_HAND_PATH,
        ),
        avoid=("凭空新增扣件", "完整开合服装", "反复拉动拉链", "双手遮挡胸前图案"),
        risk_level="conditional",
    ),
    "outer_layer_carry_hold": MotionAction(
        "outer_layer_carry_hold",
        "前臂搭外套停留",
        "outfit",
        "保持输入中已经搭在前臂的外套位置稳定，只做一次小幅重心变化并停稳；结束时内搭正面、外套轮廓和手臂接触关系保持清晰。",
        "在不执行复杂穿脱的前提下展示内搭与已取下外层的搭配关系。",
        ("ootd_walk", "mood_model"),
        requirements=("输入中外套已经搭在前臂且手部接触关系清晰",),
        required_capabilities=(
            ActionCapability.EXISTING_PROP,
            ActionCapability.FREE_HAND,
            ActionCapability.SAFE_HAND_PATH,
        ),
        avoid=("单镜头内穿上或脱下外套", "外套换手或消失", "外套遮挡内搭图案"),
        risk_level="conditional",
    ),
    "waistline_adjust_release": MotionAction(
        "waistline_adjust_release",
        "腰线轻理后释放",
        "detail",
        "从腰线与双手均清晰的稳定姿态开始，单手轻理已有腰头或腰带末端一次后自然放下；结束时上衣下摆、腰线和下装前片完整可见。",
        "展示上下装衔接、腰头或已有腰带结构。",
        ("garment_detail", "ootd_walk"),
        requirements=("输入中下装腰线或已有腰带清晰可见",),
        required_capabilities=(
            ActionCapability.WAISTLINE_VISIBLE,
            ActionCapability.FREE_HAND,
            ActionCapability.SAFE_HAND_PATH,
        ),
        avoid=("反复拉扯腰头", "新增或替换腰带", "手臂遮挡上衣图案"),
        risk_level="conditional",
    ),
    "lower_side_seam_smooth": MotionAction(
        "lower_side_seam_smooth",
        "下装侧缝轻抚",
        "detail",
        "从下装侧缝清晰的稳定站姿开始，单手沿已有侧缝向下轻抚至大腿中段后放下；结束时腰线、裤腿或裙身轮廓保持平整。",
        "展示下装侧缝、面料垂感与侧面版型。",
        ("garment_detail", "ootd_walk"),
        requirements=("输入中下装与侧缝区域清晰可见", "手部路径不经过敏感或遮挡区域"),
        required_capabilities=(
            ActionCapability.LOWER_GARMENT_VISIBLE,
            ActionCapability.FREE_HAND,
            ActionCapability.SAFE_HAND_PATH,
        ),
        avoid=("触碰裆部", "抓握紧身面料", "手部穿过下装"),
        risk_level="conditional",
    ),
    "trouser_cuff_adjust_release": MotionAction(
        "trouser_cuff_adjust_release",
        "坐姿裤脚轻理",
        "detail",
        "从输入中已有的稳定坐姿开始，单手轻理清晰可触及的一侧裤脚后沿原路径收回；结束时人物回到稳定坐姿，裤脚与鞋面边界清楚。",
        "展示裤长、裤脚结构及裤装与鞋履的衔接。",
        ("garment_detail", "mood_model"),
        requirements=("输入明确为坐姿且裤脚可自然触及", "裤脚、手部与鞋面均清晰"),
        required_capabilities=(
            ActionCapability.SEATED_POSE,
            ActionCapability.SEAT_VISIBLE,
            ActionCapability.TROUSER_CUFF_REACHABLE,
            ActionCapability.FREE_HAND,
            ActionCapability.SAFE_HAND_PATH,
        ),
        avoid=("站姿弯腰触碰裤脚", "改变卷边结构", "手脚与裤腿交叠"),
        risk_level="conditional",
    ),
    "knee_flex_settle": MotionAction(
        "knee_flex_settle",
        "单膝小幅屈伸",
        "outfit",
        "从全身稳定站姿开始，一侧膝盖小幅弯曲后重新伸直并站稳；结束时腰线、下装轮廓与鞋履完整可见。",
        "用低幅度屈伸展示下装活动空间和面料恢复状态。",
        ("ootd_walk", "mood_model"),
        requirements=("输入中下装、双腿与落脚位置完整可见",),
        required_capabilities=(
            ActionCapability.LOWER_GARMENT_VISIBLE,
            ActionCapability.LOWER_BODY_PATH_VISIBLE,
        ),
        avoid=("深蹲", "连续屈膝", "踮脚", "膝腿结构变形"),
        risk_level="conditional",
    ),
    "back_walk_settle": MotionAction(
        "back_walk_settle",
        "背面走动后停留",
        "back",
        "从可靠的背面站姿开始，背对镜头自然走一到两步后减速停稳；结束时后身版型、裤腿或裙摆与背面图案保持完整。",
        "展示服装后身在自然步态中的轮廓和垂坠。",
        ("ootd_walk", "mood_model"),
        requirements=("输入提供可靠背面参考", "画面具有一到两步纵深"),
        required_capabilities=(ActionCapability.BACK_REFERENCE, ActionCapability.WALK_DEPTH),
        avoid=("走出画面", "边走边回头", "背面图案被头发或道具遮挡"),
        risk_level="conditional",
    ),
    "skirt_slit_step_settle": MotionAction(
        "skirt_slit_step_settle",
        "开衩裙自然迈步",
        "outfit",
        "从裙身与开衩位置清晰的稳定站姿开始，以自然步幅向前迈一步后停稳；只让已有开衩随步态自然展开，结束时裙摆重新垂落。",
        "在不手动拉开裙摆的前提下展示已有开衩位置和行走空间。",
        ("ootd_walk", "mood_model"),
        requirements=("输入中已有开衩位置与落脚路径清晰",),
        required_capabilities=(
            ActionCapability.SKIRT_SLIT_VISIBLE,
            ActionCapability.LOWER_BODY_PATH_VISIBLE,
            ActionCapability.FORWARD_STEP_SPACE,
        ),
        avoid=("用手拉开开衩", "夸大步幅", "改变裙长或开衩高度"),
        risk_level="conditional",
    ),
    "footwear_forward_hold": MotionAction(
        "footwear_forward_hold",
        "前脚鞋型停留",
        "outfit",
        "从全身稳定站姿开始，一只脚向前半步并让脚掌落稳，可小幅向外调整脚尖后停留；结束时下装、裤脚与两只鞋均完整可见。",
        "展示鞋型侧面以及鞋履与整套穿搭的比例关系。",
        ("ootd_walk", "mood_model"),
        requirements=("输入中双脚、鞋履与落脚区域完整可见",),
        required_capabilities=(
            ActionCapability.FOOTWEAR_VISIBLE,
            ActionCapability.LOWER_BODY_PATH_VISIBLE,
            ActionCapability.FORWARD_STEP_SPACE,
        ),
        avoid=("把脚抬向镜头", "脚尖大幅扭转", "裁掉上身商品"),
        risk_level="conditional",
    ),
    "heel_raise_settle": MotionAction(
        "heel_raise_settle",
        "后脚跟轻抬复位",
        "outfit",
        "从双脚稳定着地开始，后脚脚跟轻抬一次后缓慢落回原位；上身不额外转动，结束时人物重新站稳并保持整套穿搭清晰。",
        "用极小动作补充鞋履动态并保持整体比例稳定。",
        ("ootd_walk", "mood_model"),
        requirements=("输入中双脚、鞋履与地面接触点完整可见",),
        required_capabilities=(
            ActionCapability.FOOTWEAR_VISIBLE,
            ActionCapability.LOWER_BODY_PATH_VISIBLE,
        ),
        avoid=("持续踮脚", "双脚同时离地", "身体大幅摇晃"),
        risk_level="conditional",
    ),
    "footwear_glance_return": MotionAction(
        "footwear_glance_return",
        "低头看鞋后回正",
        "interaction",
        "从稳定全身姿态开始，低头短暂看向已有鞋履后自然抬头回到原视线；身体和双脚保持稳定，结束时整套穿搭完整可见。",
        "用视线引导观众关注鞋履搭配，避免复杂抬脚动作。",
        ("ootd_walk", "mood_model"),
        requirements=("输入中面部、下装与鞋履完整可见且允许小幅视线变化",),
        required_capabilities=(
            ActionCapability.FOOTWEAR_VISIBLE,
            ActionCapability.FACE_GAZE_ADJUSTABLE,
        ),
        avoid=("大幅弯腰", "头发遮挡上衣图案", "抬脚靠近镜头"),
        risk_level="conditional",
    ),
    "stair_foot_tap": MotionAction(
        "stair_foot_tap",
        "低台阶脚尖轻点",
        "outfit",
        "从台阶前的稳定站姿开始，用前脚脚尖轻点已有低台阶后沿原路径收回并站稳；结束时双脚、台阶和全身服装保持连续。",
        "利用已有低台阶展示鞋履与下装比例，不改变人物所在高度。",
        ("ootd_walk", "mood_model"),
        requirements=("输入中已有低台阶且脚部往返路径完整清晰",),
        required_capabilities=(
            ActionCapability.FOOTWEAR_VISIBLE,
            ActionCapability.STAIR_VISIBLE,
            ActionCapability.STAIR_PATH_CLEAR,
        ),
        avoid=("凭空新增台阶", "跨级", "脚部与台阶穿插"),
        risk_level="conditional",
    ),
    "stair_ascend_settle": MotionAction(
        "stair_ascend_settle",
        "上一级台阶停稳",
        "outfit",
        "从已有台阶前开始，平稳走上一级台阶后双脚站稳并保持全身服装清晰；动作完成后不继续攀爬或回头。",
        "展示上下装与鞋履在一次受控抬步中的活动空间。",
        ("ootd_walk", "mood_model"),
        requirements=("输入中一级台阶、全身和落脚路径完整可见",),
        required_capabilities=(
            ActionCapability.STAIR_VISIBLE,
            ActionCapability.STAIR_PATH_CLEAR,
            ActionCapability.LOWER_BODY_PATH_VISIBLE,
        ),
        avoid=("连续上楼", "跨级", "上台阶同时转身或整理衣服"),
        risk_level="conditional",
    ),
    "stair_descend_settle": MotionAction(
        "stair_descend_settle",
        "下一级台阶停稳",
        "outfit",
        "从已有台阶上的稳定站姿开始，平稳走下一级台阶后双脚落地站稳；结束时人物保持居中，服装与鞋履完整可见。",
        "用一次受控落步展示下装活动空间和鞋履搭配。",
        ("ootd_walk", "mood_model"),
        requirements=("输入中一级台阶、全身和落脚区域完整可见",),
        required_capabilities=(
            ActionCapability.STAIR_VISIBLE,
            ActionCapability.STAIR_PATH_CLEAR,
            ActionCapability.LOWER_BODY_PATH_VISIBLE,
        ),
        avoid=("连续下楼", "跳下台阶", "下台阶同时回头或拿取道具"),
        risk_level="conditional",
    ),
    "seated_outfit_hold": MotionAction(
        "seated_outfit_hold",
        "坐姿正面稳定展示",
        "interaction",
        "保持输入中已有的椅面前部坐姿，背部自然直立并让双手远离主要商品区域；短暂停留后保持原坐姿结束，上衣正面与腰线持续清晰。",
        "为已有坐姿分镜建立稳定、可读的正面商品画面。",
        ("garment_detail", "mood_model"),
        requirements=("输入明确包含稳定坐姿与完整座位",),
        required_capabilities=(ActionCapability.SEATED_POSE, ActionCapability.SEAT_VISIBLE),
        avoid=("改变座位结构", "夸张挺胸", "手臂遮挡胸前图案"),
        risk_level="conditional",
    ),
    "seated_footwear_reveal": MotionAction(
        "seated_footwear_reveal",
        "坐姿前脚展示",
        "outfit",
        "从稳定坐姿开始，一只脚沿清晰地面路径向前半步并落稳，短暂停留后保持坐姿结束；下装、裤脚或裙摆与鞋履边界完整可见。",
        "在不站起的情况下展示下装长度与鞋履搭配。",
        ("garment_detail", "mood_model"),
        requirements=("输入中座位、下肢、鞋履与地面路径完整可见",),
        required_capabilities=(
            ActionCapability.SEATED_POSE,
            ActionCapability.SEAT_VISIBLE,
            ActionCapability.LOWER_BODY_PATH_VISIBLE,
            ActionCapability.FOOTWEAR_VISIBLE,
        ),
        avoid=("抬脚靠近镜头", "腿部交叠", "掀动裙摆"),
        risk_level="conditional",
    ),
    "seated_ankle_shift": MotionAction(
        "seated_ankle_shift",
        "坐姿脚踝轻换位",
        "interaction",
        "从双脚平稳着地的坐姿开始，让脚踝小幅错位后再自然回到平行位置；上身保持稳定，结束时下装和鞋履轮廓清晰。",
        "以低幅度下肢变化减少坐姿僵硬，同时展示下装与鞋履。",
        ("garment_detail", "mood_model"),
        requirements=("输入中座位、双腿与双脚完整可见",),
        required_capabilities=(
            ActionCapability.SEATED_POSE,
            ActionCapability.SEAT_VISIBLE,
            ActionCapability.LOWER_BODY_PATH_VISIBLE,
        ),
        avoid=("大幅交叉双腿", "脚部离地", "改变裙长"),
        risk_level="conditional",
    ),
    "seated_hand_rest_release": MotionAction(
        "seated_hand_rest_release",
        "坐姿双手轻放复位",
        "interaction",
        "从双手自然分开的稳定坐姿开始，将双手短暂轻放在大腿上后自然抬回原手位；结束时上衣、腰线与下装前片均无遮挡。",
        "为坐姿提供自然手位，并保持上下装商品区域可读。",
        ("garment_detail", "mood_model"),
        requirements=("输入中双手、大腿和下装前片清晰可见",),
        required_capabilities=(
            ActionCapability.SEATED_POSE,
            ActionCapability.FREE_HAND,
            ActionCapability.SAFE_HAND_PATH,
        ),
        avoid=("双手交叉", "拍打大腿", "手部遮挡腰线"),
        risk_level="conditional",
    ),
    "seated_angle_hold": MotionAction(
        "seated_angle_hold",
        "坐姿小角度侧转",
        "interaction",
        "从稳定坐姿开始，上身与膝部同向小幅转到约三十度后停留，再保持该稳定坐姿结束；上衣侧面、腰线和座位接触点清晰连续。",
        "补充坐姿中的正侧版型关系，避免腰部单独大幅扭转。",
        ("garment_detail", "mood_model"),
        requirements=("输入中座位边界、上身和下肢位置清晰",),
        required_capabilities=(
            ActionCapability.SEATED_POSE,
            ActionCapability.SEAT_VISIBLE,
            ActionCapability.LOWER_BODY_PATH_VISIBLE,
        ),
        avoid=("腰部单独扭转", "身体离开座位", "座位接触点漂移"),
        risk_level="conditional",
    ),
    "seated_lean_return": MotionAction(
        "seated_lean_return",
        "坐姿轻前倾后回正",
        "interaction",
        "从稳定坐姿开始，上半身小幅前倾后自然回到直立坐姿；双脚和座位接触点保持不变，结束时服装前片恢复平整清晰。",
        "用一次受控重心变化增加坐姿自然感并展示面料恢复。",
        ("garment_detail", "mood_model"),
        requirements=("输入明确包含稳定坐姿与完整座位",),
        required_capabilities=(ActionCapability.SEATED_POSE, ActionCapability.SEAT_VISIBLE),
        avoid=("大幅弯腰", "身体离开座位", "头发遮挡胸前商品"),
        risk_level="conditional",
    ),
    "seated_garment_settle": MotionAction(
        "seated_garment_settle",
        "坐姿衣摆轻理",
        "detail",
        "保持输入中的稳定坐姿，单手轻理可自然触及的上衣前下摆或裙摆一侧后立即放下；结束时服装长度、图案和座位接触关系保持连续。",
        "处理坐姿中的自然面料堆叠并恢复商品版型。",
        ("garment_detail", "mood_model"),
        requirements=("输入中坐姿稳定且待整理衣摆可自然触及",),
        required_capabilities=(
            ActionCapability.SEATED_POSE,
            ActionCapability.SEAT_VISIBLE,
            ActionCapability.FREE_HAND,
            ActionCapability.HEM_REACHABLE,
        ),
        avoid=("双手掀动裙摆", "改变服装长度", "遮挡主要图案"),
        risk_level="conditional",
    ),
    "sit_down_settle": MotionAction(
        "sit_down_settle",
        "落座后稳定展示",
        "interaction",
        "从背靠已有座椅的稳定站姿开始，沿清晰路径缓慢坐下；完全落座后保持上身服装清晰并停稳，座椅形状与人物接触点不变。",
        "用一次明确的站立到坐姿转换丰富开场或生活场景。",
        ("ootd_walk", "mood_model"),
        requirements=("输入中已有完整座椅且人物背靠座椅", "落座路径和下肢位置清晰"),
        required_capabilities=(
            ActionCapability.SEAT_VISIBLE,
            ActionCapability.SEAT_APPROACH_CLEAR,
            ActionCapability.LOWER_BODY_PATH_VISIBLE,
        ),
        avoid=("凭空新增座椅", "转身同时落座", "手脚与座位交叠"),
        risk_level="conditional",
    ),
    "companion_side_walk": MotionAction(
        "companion_side_walk",
        "同伴并肩受控走动",
        "interaction",
        "从输入中已有同伴并肩站立的状态开始，两人同向走一到两步后依次减速停稳；模特保持小步幅，结束时主要服装区域无遮挡。",
        "在已有双人场景中增加自然同行感，同时保留清晰商品停留。",
        ("ootd_walk", "mood_model"),
        requirements=("输入中已有同伴且两人之间边界清晰", "前方具有共享的一到两步空间"),
        required_capabilities=(
            ActionCapability.COMPANION_PRESENT,
            ActionCapability.SHARED_MOVEMENT_SPACE,
        ),
        avoid=("凭空新增人物", "牵手或拥抱", "两人交叉换位", "同伴遮挡商品"),
        risk_level="conditional",
    ),
    "companion_product_pause": MotionAction(
        "companion_product_pause",
        "同伴场景商品停留",
        "interaction",
        "保持输入中已有同伴的位置稳定，模特只做一次小幅重心变化后面向商品展示角度停留；结束时两人边界清楚，模特服装正面完整可见。",
        "在双人画面中把视觉重点重新落到模特与服装上。",
        ("ootd_walk", "mood_model"),
        requirements=("输入中已有同伴且模特商品区域未被遮挡",),
        required_capabilities=(ActionCapability.COMPANION_PRESENT,),
        avoid=("凭空新增人物", "同伴触碰或整理模特服装", "同伴遮挡图案"),
        risk_level="conditional",
    ),
    "companion_gaze_return": MotionAction(
        "companion_gaze_return",
        "看向同伴后回望",
        "interaction",
        "从输入中已有同伴的稳定双人姿态开始，模特小幅转头看向同伴，可轻点头或自然微笑一次，再缓慢回到原视线；身体与服装保持稳定。",
        "用低接触风险的视线交流建立真实同伴感。",
        ("ootd_walk", "mood_model"),
        requirements=("输入中已有同伴且人物面部允许小幅视线变化",),
        required_capabilities=(
            ActionCapability.COMPANION_PRESENT,
            ActionCapability.FACE_GAZE_ADJUSTABLE,
        ),
        avoid=("凭空新增人物", "大幅甩头", "夸张大笑", "身体转向导致商品离开正面"),
        risk_level="conditional",
    ),
    "companion_doorway_pass": MotionAction(
        "companion_doorway_pass",
        "同伴扶门自然经过",
        "interaction",
        "保持输入中已有同伴扶住已有门的状态，模特沿清晰通道自然经过门口后停稳；门、同伴和模特之间不发生穿插，结束时服装重新完整可见。",
        "为已有门口双人场景提供低接触的生活化通行动作。",
        ("ootd_walk", "mood_model"),
        requirements=("输入中已有同伴、门和明确通行路径",),
        required_capabilities=(
            ActionCapability.COMPANION_PRESENT,
            ActionCapability.DOORWAY_VISIBLE,
            ActionCapability.DOORWAY_PATH_CLEAR,
        ),
        avoid=("凭空新增人物或门", "人物与门体穿插", "边经过边回头或递物"),
        risk_level="conditional",
    ),
}


# Legacy IDs kept for persisted profiles, feedback records, and external API
# callers. Aliases are normalized before compatibility filtering and are not
# exposed as separate catalog entries.
ACTION_ALIASES: dict[str, str] = {
    "chest_print_pause": "print_detail_pause",
    "eye_contact_neutral": "controlled_gaze",
    "cool_detached_glance": "controlled_gaze",
}


def canonical_action_id(action_id: str) -> str:
    return ACTION_ALIASES.get(action_id, action_id)


def normalize_action_ids(action_ids: Iterable[str]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(canonical_action_id(action_id) for action_id in action_ids))


# Reviewed OOTD source items 296-360 are normalized to reusable action IDs.
OOTD_REVIEWED_ACTION_COVERAGE: dict[int, str] = {
    296: "lapel_open_hold",
    297: "lapel_open_hold",
    298: "lapel_open_hold",
    299: "layer_reveal_return",
    300: "layer_reveal_return",
    301: "hem_adjust",
    302: "sleeve_detail_pause",
    303: "torso_angle_hold",
    304: "three_quarter_turn",
    305: "back_reveal",
    306: "back_reveal",
    307: "pocket_insert_release",
    308: "cuff_adjust_release",
    309: "fastener_adjust_release",
    310: "fastener_adjust_release",
    311: "outer_layer_carry_hold",
    312: "waistline_adjust_release",
    313: "waistline_adjust_release",
    314: "pocket_insert_release",
    315: "pocket_insert_release",
    316: "stance_shift",
    317: "torso_angle_hold",
    318: "one_step_settle",
    319: "controlled_side_step",
    320: "knee_flex_settle",
    321: "lower_side_seam_smooth",
    322: "trouser_cuff_adjust_release",
    323: "back_reveal",
    324: "back_walk_settle",
    325: "waistline_adjust_release",
    326: "garment_sway_settle",
    327: "skirt_slit_step_settle",
    328: "garment_sway_settle",
    329: "footwear_forward_hold",
    330: "footwear_forward_hold",
    331: "heel_raise_settle",
    332: "stance_shift",
    333: "stance_shift",
    334: "footwear_glance_return",
    335: "controlled_walk",
    336: "stair_foot_tap",
    337: "stair_ascend_settle",
    338: "stair_descend_settle",
    339: "seated_outfit_hold",
    340: "seated_weight_shift",
    341: "seated_footwear_reveal",
    342: "seated_ankle_shift",
    343: "seated_hand_rest_release",
    344: "seated_angle_hold",
    345: "seated_lean_return",
    346: "seated_garment_settle",
    347: "seated_garment_settle",
    348: "stand_from_seat_settle",
    349: "sit_down_settle",
    350: "seated_prop_sip_return",
    351: "companion_side_walk",
    352: "companion_product_pause",
    353: "companion_gaze_return",
    354: "companion_gaze_return",
    355: "companion_gaze_return",
    356: "companion_product_pause",
    357: "companion_product_pause",
    358: "companion_gaze_return",
    359: "companion_side_walk",
    360: "companion_doorway_pass",
}


def list_motion_actions() -> tuple[MotionAction, ...]:
    return tuple(ACTION_LIBRARY.values())


def evaluate_action(
    action: MotionAction,
    context: ActionContext | None = None,
) -> ActionEligibility:
    """Return deterministic eligibility without guessing unknown material facts."""

    action_context = context or ActionContext()
    denied = tuple(
        capability
        for capability in action.required_capabilities
        if capability in action_context.denied
    )
    supported = action_context.supports(action.required_capabilities)
    missing = (
        ()
        if denied or supported
        else tuple(
            capability
            for capability in action.required_capabilities
            if capability not in action_context.denied
        )
    )
    return ActionEligibility(allowed=not denied and not missing, missing=missing, denied=denied)


def evaluate_action_with_base(
    action: MotionAction,
    context: ActionContext | None,
    library: Mapping[str, MotionAction],
) -> ActionEligibility:
    if action.base_action_id is None:
        return evaluate_action(action, context)
    base_action = library.get(action.base_action_id)
    if base_action is None:
        return ActionEligibility(allowed=False)
    capabilities = tuple(
        dict.fromkeys((*base_action.required_capabilities, *action.required_capabilities))
    )
    inherited = MotionAction(
        id=action.id,
        label=action.label,
        category=action.category,
        instruction=action.instruction,
        purpose=action.purpose,
        compatible_templates=action.compatible_templates,
        required_capabilities=capabilities,
    )
    return evaluate_action(inherited, context)


def compatible_action_ids(
    template_id: str,
    action_ids: tuple[str, ...],
    *,
    context: ActionContext | None = None,
    library: Mapping[str, MotionAction] | None = None,
) -> tuple[str, ...]:
    actions = ACTION_LIBRARY if library is None else library
    normalized_action_ids = normalize_action_ids(action_ids)
    return tuple(
        action_id
        for action_id in normalized_action_ids
        if action_id in actions
        and template_id in actions[action_id].compatible_templates
        and (
            actions[action_id].base_action_id is None
            or (
                actions[action_id].base_action_id in actions
                and template_id in actions[actions[action_id].base_action_id].compatible_templates
            )
        )
        and evaluate_action_with_base(actions[action_id], context, actions).allowed
    )


def render_action_ids(
    template_id: str,
    action_ids: tuple[str, ...],
    *,
    context: ActionContext | None = None,
    library: Mapping[str, MotionAction] | None = None,
) -> str:
    actions = ACTION_LIBRARY if library is None else library
    compatible = compatible_action_ids(
        template_id,
        action_ids,
        context=context,
        library=actions,
    )
    if not compatible:
        return "不额外添加站点专属动作，保持模板动作骨架"
    rendered: list[str] = []
    for action_id in compatible:
        action = actions[action_id]
        if action.base_action_id is None:
            rendered.append(action.instruction)
            continue
        base_action = actions[action.base_action_id]
        rendered.append(f"{base_action.instruction}；品牌风格差异：{action.instruction}")
    return "；".join(rendered)
