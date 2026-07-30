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
        version="0.1.0-research",
        status="draft",
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
        research_note="首页和公开社媒入口可直接观察；正式提示词仍待用户近期生产语料验收。",
    ),
    "guidingcross": SiteStyleProfile(
        id="guidingcross",
        version="0.1.0-research",
        status="draft",
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
        version="0.1.0-research",
        status="draft",
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
        version="0.1.0-research",
        status="draft",
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
        version="0.1.0-research",
        status="draft",
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
