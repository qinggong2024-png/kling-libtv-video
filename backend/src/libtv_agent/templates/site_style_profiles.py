from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Literal

SiteProfileStatus = Literal["draft", "active", "retired"]
EvidenceLevel = Literal["verified_site", "restricted_site"]


@dataclass(frozen=True)
class SiteStyleProfile:
    id: str
    version: str
    status: SiteProfileStatus
    name: str
    site_url: str
    source_urls: tuple[str, ...]
    retrieved_at: str
    evidence_level: EvidenceLevel
    tone: str
    audience: str
    palette: tuple[str, ...]
    typography: str
    camera_language: str
    opening_rule: str
    middle_rule: str
    ending_rule: str
    preferred_shots: tuple[str, ...]
    preferred_actions: tuple[str, ...]
    pacing: str
    product_priorities: tuple[str, ...]
    forbidden_mismatches: tuple[str, ...]
    research_note: str

    def to_public_dict(self) -> dict[str, object]:
        value = asdict(self)
        value["siteUrl"] = value.pop("site_url")
        value["sourceUrls"] = value.pop("source_urls")
        value["retrievedAt"] = value.pop("retrieved_at")
        value["evidenceLevel"] = value.pop("evidence_level")
        value["cameraLanguage"] = value.pop("camera_language")
        value["openingRule"] = value.pop("opening_rule")
        value["middleRule"] = value.pop("middle_rule")
        value["endingRule"] = value.pop("ending_rule")
        value["preferredShots"] = value.pop("preferred_shots")
        value["preferredActions"] = value.pop("preferred_actions")
        value["productPriorities"] = value.pop("product_priorities")
        value["forbiddenMismatches"] = value.pop("forbidden_mismatches")
        value["researchNote"] = value.pop("research_note")
        return value


_RETRIEVED_AT = "2026-07-30"


SITE_STYLE_PROFILES: dict[str, SiteStyleProfile] = {
    "geeksoutfit": SiteStyleProfile(
        id="geeksoutfit",
        version="1.0.0",
        status="active",
        name="极客 / GeeksOutfit",
        site_url="https://www.geeksoutfit.com/",
        source_urls=(
            "https://www.geeksoutfit.com/",
            "https://www.instagram.com/geeksoutfitstore/",
            "https://www.tiktok.com/@geeksoutfitstore",
            "https://www.youtube.com/channel/UCYftwHKqZQuA9BDRUaatzaA",
        ),
        retrieved_at=_RETRIEVED_AT,
        evidence_level="verified_site",
        tone="轻快、聪明、怀旧科幻，但保留商品陈列的清晰度",
        audience="喜欢 geek、nerdy、复古音乐和科幻文化的消费者",
        palette=("white", "black", "vintage accent colors"),
        typography="Space Mono / Ubuntu 风格的等宽与几何无衬线",
        camera_language="稳定观察为主，允许一次轻推进和一次利落景别切换，不用高速甩镜",
        opening_rule="前 3 秒先以整身中景建立服装与人物，再开始位移",
        middle_rule="完成一次三分之四转身，并给印花、文字或袖口一次稳定细节停留",
        ending_rule="回到整件商品清晰可见的中景，以轻松定姿结束",
        preferred_shots=("整身中景", "三分之四中近景", "印花局部特写"),
        preferred_actions=(
            "controlled_walk",
            "three_quarter_turn",
            "print_detail_pause",
            "hem_adjust",
        ),
        pacing="standard_to_fast，但每次印花展示保留稳定停留",
        product_priorities=("整件版型", "印花和文字可读性", "复古色彩", "袖口和下摆"),
        forbidden_mismatches=("庄严宗教仪式感", "医疗工作流", "无意义高速旋转", "用特效遮挡印花"),
        research_note="首页和公开社媒入口可直接观察；已按用户确认的不变量边界纳入生产。",
    ),
    "guidingcross": SiteStyleProfile(
        id="guidingcross",
        version="1.0.0",
        status="active",
        name="基督 / GuidingCross",
        site_url="https://www.guidingcross.com/",
        source_urls=(
            "https://www.guidingcross.com/",
            "https://www.instagram.com/guidingcrossofficial",
            "https://www.tiktok.com/@guidingcrossclothing",
            "https://www.youtube.com/@guidingcross",
        ),
        retrieved_at=_RETRIEVED_AT,
        evidence_level="verified_site",
        tone="克制、温和、尊重信仰，文字先于动作",
        audience="基督信仰服饰和日常穿搭用户",
        palette=("white", "deep navy gray", "washed garment tones"),
        typography="Poppins 风格的清楚无衬线",
        camera_language="稳定、克制的正面观察与缓慢推进，减少切镜和视角跳变",
        opening_rule="以正面或轻三分之四中景开场，让信仰文字先被读清",
        middle_rule="用一次低幅度姿态变化展示水洗质感、衣摆或袖口，不遮挡核心文字",
        ending_rule="回到正面稳定停留，或自然低头后抬眼结束",
        preferred_shots=("正面中景", "稳定三分之四中景", "胸前文字近景"),
        preferred_actions=(
            "stance_shift",
            "controlled_walk",
            "three_quarter_turn",
            "chest_print_pause",
        ),
        pacing="slow_to_standard，避免高频跳切",
        product_priorities=("信仰文字可读性", "水洗面料质感", "完整穿搭", "版型稳定"),
        forbidden_mismatches=("讽刺怪诞语气", "夜店霓虹节奏", "夸张舞蹈", "手部遮挡核心文字"),
        research_note=(
            "首页 mission 与产品主题可直接观察；宗教动作不默认加入，只使用自然站姿和有限手部动作。"
        ),
    ),
    "nerdywave": SiteStyleProfile(
        id="nerdywave",
        version="0.1.0-research",
        status="draft",
        name="暗黑 / NerdyWave",
        site_url="https://www.nerdywave.com/",
        source_urls=("https://www.nerdywave.com/",),
        retrieved_at=_RETRIEVED_AT,
        evidence_level="restricted_site",
        tone="待验证的暗黑/另类方向；仅作为保守的研究占位",
        audience="待站内证据确认",
        palette=("low_saturation", "black", "shadowed_neutral"),
        typography="待验证",
        camera_language="暂定为低幅度侧向观察与有限低机位，正式启用前需样片验证",
        opening_rule="以侧面或三分之四中景建立暗色轮廓，不用闪烁特效",
        middle_rule="用克制掠视和一次缓慢转身制造冷感，并保留印花可读停留",
        ending_rule="停在清晰轮廓与低饱和层次仍可辨认的稳定画面",
        preferred_shots=("侧面中景", "有限低机位", "印花近景"),
        preferred_actions=(
            "controlled_walk",
            "three_quarter_turn",
            "controlled_gaze",
            "print_detail_pause",
        ),
        pacing="slow_to_standard，先验证再放大动作",
        product_priorities=("轮廓", "黑色/低饱和层次", "印花可读性"),
        forbidden_mismatches=("恐怖特效", "身体变形", "过度闪烁", "未经证据确认的赛博或哥特符号"),
        research_note="2026-07-30 站内自动化访问返回 403；当前内容只能作为用户标签下的保守占位。",
    ),
    "pagewings": SiteStyleProfile(
        id="pagewings",
        version="0.1.0-research",
        status="draft",
        name="泛读书 / PageWings",
        site_url="https://www.pagewings.com/",
        source_urls=("https://www.pagewings.com/",),
        retrieved_at=_RETRIEVED_AT,
        evidence_level="restricted_site",
        tone="待验证的读书/文学气质；安静、叙事化、不过度表演",
        audience="待站内证据确认",
        palette=("paper_neutral", "ink_black", "muted_accent"),
        typography="待验证",
        camera_language="暂定为安静观察、轻推近景与较长停留，不凭空补入文学道具",
        opening_rule="先建立人物与现有环境的关系，以稳定中景留出叙事空间",
        middle_rule="通过视线移动、轻微重心变化和文字细节停留推进画面",
        ending_rule="在安静的中景或文字仍可读的近景自然停留",
        preferred_shots=("环境中景", "轻推近景", "已有物件关系镜头"),
        preferred_actions=(
            "stance_shift",
            "controlled_walk",
            "controlled_gaze",
            "print_detail_pause",
        ),
        pacing="slow_to_standard，保留阅读式停留",
        product_priorities=("文字/插画可读性", "材质和版型", "人与环境关系"),
        forbidden_mismatches=(
            "擅自新增书本或眼镜",
            "高速跳切",
            "夸张舞蹈",
            "把推断的学院风当成事实",
        ),
        research_note="2026-07-30 站内自动化访问返回 403；需补充首页或产品样片后再激活。",
    ),
    "teachersgram": SiteStyleProfile(
        id="teachersgram",
        version="1.0.0",
        status="active",
        name="教师 / Teachersgram",
        site_url="https://www.teachersgram.com/",
        source_urls=(
            "https://www.teachersgram.com/",
            "https://www.instagram.com/teachersgramofficial/",
        ),
        retrieved_at=_RETRIEVED_AT,
        evidence_level="verified_site",
        tone="明亮、亲和、实用的日常工作感",
        audience="教师和教育主题周边消费者",
        palette=("warm cream", "black", "soft classroom accents"),
        typography="Almarai / Arapey，正文清楚、标题有一点编辑感",
        camera_language="明亮稳定的朋友记录视角，允许自然跟随与一次胸前细节推进",
        opening_rule="以自然站姿或一到两步走动建立整件服装和亲和感",
        middle_rule="用轻三分之四侧身让胸前图案朝向镜头，再展示一次袖口或下摆",
        ending_rule="停在教育主题文字清晰可读的中景，以自然微笑或放松表情结束",
        preferred_shots=("整身中景", "胸前图案中近景", "袖口/下摆细节"),
        preferred_actions=(
            "controlled_walk",
            "three_quarter_turn",
            "chest_print_pause",
            "hem_adjust",
        ),
        pacing="standard，动作完整而不幼稚",
        product_priorities=("教育主题文字", "可穿着的版型", "胸前印花", "实用细节"),
        forbidden_mismatches=("幼儿园式蹦跳", "暗黑低照度", "过度性感姿态", "道具堆砌"),
        research_note="首页分类 Math/Literature/Music/Art/Science 与暖奶油色、字体可直接观察。",
    ),
    "goodnurselife": SiteStyleProfile(
        id="goodnurselife",
        version="0.1.0-research",
        status="draft",
        name="护士 / GoodNurseLife",
        site_url="https://www.goodnurselife.com/",
        source_urls=("https://www.goodnurselife.com/",),
        retrieved_at=_RETRIEVED_AT,
        evidence_level="restricted_site",
        tone="待验证的清洁、可靠、功能导向",
        audience="待站内证据确认",
        palette=("clean_light", "medical_blue_or_teal_pending", "garment_neutral"),
        typography="待验证",
        camera_language="暂定为清洁明亮的稳定跟随与短距离推进，避免医疗情节化运镜",
        opening_rule="用清晰中景建立服装轮廓与职业主题文字",
        middle_rule="以一次向前停稳或重心变化衔接胸前文字、肩线和袖口细节",
        ending_rule="回到干净稳定的商品确认镜头，不增加器械或操作场景",
        preferred_shots=("清晰中景", "胸前文字近景", "肩线/袖口细节"),
        preferred_actions=(
            "stance_shift",
            "controlled_walk",
            "chest_print_pause",
            "sleeve_detail_pause",
        ),
        pacing="standard，商品信息优先",
        product_priorities=("职业文字/图标", "肩线和袖口", "舒适版型", "清晰对比"),
        forbidden_mismatches=("擅自增加医疗器械", "危险操作示范", "夸张舞蹈", "不真实制服替换"),
        research_note="2026-07-30 站内自动化访问返回 403；护理主题规则必须等待站内或用户样片确认。",
    ),
    "classyoutlaw": SiteStyleProfile(
        id="classyoutlaw",
        version="1.0.0",
        status="active",
        name="怪诞 / ClassyOutlaw",
        site_url="https://www.classyoutlaw.com/",
        source_urls=(
            "https://www.classyoutlaw.com/",
            "https://www.instagram.com/classyoutlaw_official/",
            "https://www.youtube.com/@classyoutlaw",
        ),
        retrieved_at=_RETRIEVED_AT,
        evidence_level="verified_site",
        tone="叛逆、超现实、强图形，但动作仍受控",
        audience="喜欢怪诞、迷幻、反常规图形服饰的消费者",
        palette=("near_black", "neon_magenta", "high_contrast_graphic"),
        typography="Poppins / Jost / Dela Gothic One 的粗体展示感",
        camera_language="允许不对称取景、短促推进和一次利落切镜，但始终回到商品轮廓",
        opening_rule="用不对称中景和短暂停格快速建立强图形印花",
        middle_rule="通过一次有限侧移、头肩轻倾或克制视线变化制造怪诞节奏",
        ending_rule="从近景返回整身商品确认镜头，以强轮廓定格结束",
        preferred_shots=("不对称中景", "短暂近景", "回到整身的商品确认镜头"),
        preferred_actions=(
            "asymmetric_pause",
            "controlled_side_step",
            "head_shoulder_tilt",
            "print_detail_pause",
        ),
        pacing="standard_to_fast，短停格替代无意义甩镜",
        product_priorities=("强图形印花", "黑色与荧光对比", "轮廓", "主题分类气质"),
        forbidden_mismatches=("身体变形", "长时间模糊", "故障滤镜遮挡文字", "无返回整身的连续特写"),
        research_note=(
            "首页主题 Depression/Lust/Destroy/Yokai/Reincarnation/Illusion、"
            "深色背景和洋红强调色可直接观察。"
        ),
    ),
    "theretrotee": SiteStyleProfile(
        id="theretrotee",
        version="1.0.0",
        status="active",
        name="怀旧 / TheRetroTee",
        site_url="https://www.theretrotee.com/",
        source_urls=("https://www.theretrotee.com/",),
        retrieved_at=_RETRIEVED_AT,
        evidence_level="verified_site",
        tone="温暖、复古、像旧广告一样有记忆点",
        audience="喜欢 Americana、年代图形和复古棒球衫的消费者",
        palette=("white", "wine_red", "dark_green", "navy", "black"),
        typography="Figtree，现代清晰字体承载复古商品",
        camera_language="慢半拍的稳定 lookbook 观察，有限横移与柔和推进，不叠加遮字胶片噪点",
        opening_rule="以静态整身或一步停稳建立年代配色与完整轮廓",
        middle_rule="用一次半转展示滚边、背面或侧面，再给领口袖口一次稳定停留",
        ending_rule="像旧广告一样回到整身或三分之四中景定格结束",
        preferred_shots=("复古整身中景", "背面/滚边中近景", "领口袖口细节"),
        preferred_actions=("controlled_walk", "three_quarter_turn", "back_reveal", "hem_adjust"),
        pacing="slow_to_standard，结尾保留广告式定格",
        product_priorities=("年代主题文字", "raglan/滚边结构", "复古配色", "完整轮廓"),
        forbidden_mismatches=("未来科技 HUD", "强烈霓虹", "高速甩镜", "噪点滤镜遮挡印花"),
        research_note=(
            "首页 Nostalgic Favorites、1970s/1981 商品命名和酒红/深绿/海军蓝色系可直接观察。"
        ),
    ),
    "orionride": SiteStyleProfile(
        id="orionride",
        version="1.0.0",
        status="active",
        name="骑行 / OrionRide",
        site_url="https://www.orionride.com/",
        source_urls=(
            "https://www.orionride.com/",
            "https://www.instagram.com/orionrideofficial/",
            "https://www.youtube.com/@orionrideofficial",
            "https://www.youtube.com/watch?v=tvAwCYDumyA",
            "https://www.youtube.com/watch?v=4c74x_gWsvc",
        ),
        retrieved_at=_RETRIEVED_AT,
        evidence_level="verified_site",
        tone="户外、自由、功能明确，兼顾复古骑行图形和生活方式色彩",
        audience="gravel、MTB、downhill 与城市骑行生活方式用户",
        palette=("high_visibility_color", "outdoor_green", "earth_neutral", "graphic_accent"),
        typography="清晰运动无衬线，图形款允许复古骑行海报感",
        camera_language="商品片以稳定正面和三分之四中全景为主；只有输入已有自行车和户外环境时才使用骑行情境镜头",
        opening_rule="先建立完整上装和骑行版型；无自行车参考时保持自然站姿，不补入车辆或护具",
        middle_rule="优先确认肩袖、后摆和背面图形；骑行或推车动作仅在对应道具与环境已经存在时使用",
        ending_rule="回到清晰的正面或背面商品停留，避免让车轮、车把或装备遮住服装",
        preferred_shots=("正面中全景", "三分之四侧面", "背面中近景", "条件化户外长景"),
        preferred_actions=(
            "stance_shift",
            "three_quarter_turn",
            "back_reveal",
            "sleeve_detail_pause",
        ),
        pacing="standard；骑行情境可 standard_to_fast，但背印与版型停留至少一秒半",
        product_priorities=("完整骑行版型", "肩袖和后摆", "背面图形", "口袋与功能结构"),
        forbidden_mismatches=(
            "无参考时新增自行车、头盔或护具",
            "危险越野或跳跃",
            "车辆占主体导致服装不可读",
            "拉伸印花证明面料性能",
        ),
        research_note=(
            "官网品类和官方公开视频均已复核；真实骑行动作继续作为自行车与户外环境条件动作，"
            "不进入无道具默认动作库。"
        ),
    ),
    "ironpandafit": SiteStyleProfile(
        id="ironpandafit",
        version="1.0.0",
        status="active",
        name="健身 / IronPandaFit",
        site_url="https://www.ironpandafit.com/",
        source_urls=(
            "https://www.ironpandafit.com/",
            "https://www.instagram.com/ironpanda_fitness/",
            "https://www.tiktok.com/@official_ironpanda",
            "https://www.youtube.com/channel/UCZz9gUB4QTZ3zPpqbzDxPlQ",
            "https://www.youtube.com/watch?v=hKbeWCmbkhU",
            "https://www.youtube.com/watch?v=LfuPXgmEAfk",
        ),
        retrieved_at=_RETRIEVED_AT,
        evidence_level="verified_site",
        tone="有力量、直接、略带幽默和洗水街头感，但商品信息始终清晰",
        audience="力量训练、健身房文化和日常训练穿搭用户",
        palette=("black", "washed_charcoal", "white", "high_contrast_graphic"),
        typography="粗体运动无衬线和高对比口号字体",
        camera_language="以正面中大全身确认印花和手臂轮廓；训练低机位只作短氛围片段，不能代替商品停留",
        opening_rule="用稳定站姿或一步停稳建立上衣轮廓，不自动添加器械、拳击手套或训练带",
        middle_rule="保持手臂离开核心印花，允许低幅肩部打开或在输入手位支持时轻整领口",
        ending_rule="训练氛围后必须回到双臂放松、印花无遮挡的正面商品画面",
        preferred_shots=("正面中大全身", "胸前图形中近景", "肩臂轮廓中景"),
        preferred_actions=(
            "stance_shift",
            "one_step_settle",
            "chest_print_pause",
            "collar_frame_release",
        ),
        pacing="standard_to_fast；训练切片可短，但商品确认至少保留一到一点五秒",
        product_priorities=("胸前图形", "Pump Cover 宽松轮廓", "肩臂和领口", "训练服垂坠"),
        forbidden_mismatches=(
            "杠铃、拳击或重型器械进入默认动作",
            "力竭、疼痛、倒地或危险挑战",
            "赤膊或只展示肌肉",
            "双臂发力拉伸文字和印花",
            "从成人健身样片推导儿童动作",
        ),
        research_note=(
            "官网目录和三条官方视频已复核；站点特征是训练切片与商品确认的编辑组合，"
            "暂不注册独占人体动作。"
        ),
    ),
    "tokyotiger": SiteStyleProfile(
        id="tokyotiger",
        version="1.0.0",
        status="active",
        name="东京 / Tokyo-Tiger",
        site_url="https://www.tokyo-tiger.com/",
        source_urls=(
            "https://www.tokyo-tiger.com/",
            "https://www.instagram.com/tokyotigerfashion/",
            "https://www.instagram.com/tokyotiger.official/",
        ),
        retrieved_at=_RETRIEVED_AT,
        evidence_level="verified_site",
        tone="日常、俏皮、复古且重视文化图形可读性，不把日本主题表演化",
        audience="喜欢日本城市、动物、食物、幽默、运动和复古图形服饰的用户",
        palette=("washed_neutral", "artwork_color", "sport_accent", "summer_print"),
        typography="清晰日常无衬线，复杂图形与文化文字保留足够阅读空间",
        camera_language="正面膝上或中全景优先，以一次轻微三分之四转体补充肩袖和宽松轮廓",
        opening_rule="先给胸前图形完整正面停留，不从站点名称推断动漫、赛博或传统表演",
        middle_rule="复杂图形追加稳定中近景；球衣或衬衫只做低幅肩袖、侧缝和衣摆展示",
        ending_rule="回到图形无遮挡的完整商品画面，以自然放松表情结束",
        preferred_shots=("正面膝上景", "正面中全景", "三分之四中景", "图形中近景"),
        preferred_actions=(
            "stance_shift",
            "three_quarter_turn",
            "print_detail_pause",
            "sleeve_detail_pause",
        ),
        pacing="standard_to_fast；有效姿态保留一到一点八秒，复杂木版画式图形适当放慢",
        product_priorities=("文化与幽默图形", "文字和符号可读性", "球衣肩袖", "衬衫版型"),
        forbidden_mismatches=(
            "擅自加入鞠躬、武士表演或动漫角色扮演",
            "无参考时生成霓虹赛博或原宿夸张造型",
            "武器和危险道具",
            "手部遮挡汉字、图案中心或文化符号",
            "快切导致图形不可读",
        ),
        research_note=(
            "官网目录和官方社媒入口已核验；嵌入 Reel 未完成全片复核，因此正式画像只使用"
            "官网可证实的品类、主题边界与跨站通用动作。"
        ),
    ),
    "boldoversize": SiteStyleProfile(
        id="boldoversize",
        version="1.0.0",
        status="active",
        name="大码 / BoldOversize",
        site_url="https://www.boldoversize.com/",
        source_urls=(
            "https://www.boldoversize.com/",
            "https://www.instagram.com/boldoversize_shop/",
            "https://www.youtube.com/@boldoversize/shorts",
            "https://www.youtube.com/shorts/3gQRntK_0hc",
            "https://www.youtube.com/shorts/lhdqaRR0Q-k",
        ),
        retrieved_at=_RETRIEVED_AT,
        evidence_level="verified_site",
        tone="舒适、自然、身体中立，真实展示版型而不制造修饰身体的表演",
        audience="需要包容尺码与多种日常、复古、幽默和图形风格的消费者",
        palette=("washed_color", "americana_accent", "graphic_color", "everyday_neutral"),
        typography="清楚易读的日常无衬线，图形和幽默文字优先",
        camera_language="固定竖屏全身为主，同时保留正面和轻三分之四角度，不用斜拍或局部裁切制造缩身效果",
        opening_rule="以自然正面全身建立衣长、袖长和宽松量，允许人物按自身习惯舒适站立",
        middle_rule="使用前后脚轻错位、小幅重心变化或一步停稳展示真实活动空间，不遮胸腹",
        ending_rule="回到完整正面或轻三分之四站姿，保持图案、衣摆和侧缝可判断",
        preferred_shots=("固定竖屏正面全身", "轻三分之四全身", "无遮挡图形中景"),
        preferred_actions=(
            "stance_shift",
            "one_step_settle",
            "three_quarter_turn",
            "garment_sway_settle",
        ),
        pacing="standard_to_slow，连续自然移动，约三到五秒完成一个阶段",
        product_priorities=("真实衣长", "袖长和侧缝", "胸围余量", "活动空间", "图案可读性"),
        forbidden_mismatches=(
            "吸腹、缩肩、踮脚或极端侧身",
            "用手、包或外套遮腹遮胸",
            "胖瘦或穿前穿后对比",
            "指向、拍打或拉扯所谓问题部位",
            "只拍脸或局部导致整体版型不可判断",
        ),
        research_note=(
            "官网目录和两条官方 Shorts 已直接复核；大码作为尺码与人群条件处理，"
            "不创建只面向大码人物的特殊动作体系。"
        ),
    ),
}


def list_site_style_profiles(*, include_retired: bool = False) -> tuple[SiteStyleProfile, ...]:
    return tuple(
        profile
        for profile in SITE_STYLE_PROFILES.values()
        if include_retired or profile.status != "retired"
    )


def get_site_style_profile(profile_id: str, *, require_active: bool = False) -> SiteStyleProfile:
    profile = SITE_STYLE_PROFILES.get(profile_id)
    if profile is None:
        raise ValueError(f"unknown site style profile: {profile_id}")
    if require_active and profile.status != "active":
        raise ValueError(f"site style profile is not active: {profile_id}")
    return profile
