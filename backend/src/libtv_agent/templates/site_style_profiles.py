from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Literal

SiteProfileStatus = Literal["draft", "active", "retired"]
EvidenceLevel = Literal["verified_site", "restricted_site"]
LibraryScope = Literal["general", "brand"]


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
    expression_language: str = "自然、克制并服务于商品展示"
    library_scope: LibraryScope = "brand"
    brand_id: str | None = None

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
        value["expressionLanguage"] = value.pop("expression_language")
        value["libraryScope"] = value.pop("library_scope")
        brand_id = value.pop("brand_id")
        value["brandId"] = (brand_id or self.id) if self.library_scope == "brand" else None
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
        tone="轻快、聪明、带怀旧科幻玩味感，但保留商品陈列的清晰度",
        expression_language=(
            "人物轻松、好奇、带一点机灵玩味；允许短暂挑眉、自然微笑或发现感掠视，"
            "动作轻快但不滑稽，始终让印花和文字成为视线重点。"
        ),
        audience="喜欢 geek、nerdy、复古音乐和科幻文化的消费者",
        palette=("white", "black", "vintage accent colors"),
        typography="Space Mono / Ubuntu 风格的等宽与几何无衬线",
        camera_language="明亮平视观察为主，允许一次轻快推进、一次小幅横向跟随和利落细节切换，不用高速甩镜",
        opening_rule="前 3 秒先以整身中景建立服装与人物，再开始位移",
        middle_rule="以机灵掠视或自然微笑配合一次三分之四转身，并给印花、文字或袖口一次稳定细节停留",
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
        expression_language=(
            "人物真诚、平和、带希望感；使用温和直视、自然轻微微笑或安静低头回望，"
            "避免布道式手势、夸张虔诚表演和遮挡信仰文字。"
        ),
        audience="基督信仰服饰和日常穿搭用户",
        palette=("white", "deep navy gray", "washed garment tones"),
        typography="Poppins 风格的清楚无衬线",
        camera_language="柔和眼平正面观察与缓慢推进，镜头保持尊重、安定且不做突兀视角跳变",
        opening_rule="以正面或轻三分之四中景开场，让信仰文字先被读清",
        middle_rule="用平和视线和一次低幅度姿态变化展示水洗质感、衣摆或袖口，不遮挡核心文字",
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
        version="1.0.0",
        status="active",
        name="暗黑 / NerdyWave",
        site_url="https://www.nerdywave.com/",
        source_urls=(
            "https://www.nerdywave.com/",
            "https://www.instagram.com/nerdywave_apparel/",
            "https://www.tiktok.com/@nerdywave_apparel",
            "https://www.youtube.com/channel/UCqHz2Agwp4JCUh3pxD-6eYw",
        ),
        retrieved_at="2026-08-17",
        evidence_level="verified_site",
        tone="暗黑另类、复古 fandom、恐怖与神秘学母题并存；以黑色材质层次和图形可读性为核心",
        expression_language=(
            "人物自信、冷感并可带轻微玩味，使用稳定直视、短促掠视或微压下颌；"
            "姿态有张力但不龇牙、不吼叫，不用身体变形制造暗黑感。"
        ),
        audience="偏好恐怖、神秘学、cryptid、cult film、游戏与暗黑街头图形服饰的用户",
        palette=("black", "white", "muted red", "washed gray"),
        typography="Instrument Sans 主体字，搭配高对比衬线展示字和手写标志",
        camera_language="以眼平或极轻低机位的侧面、三分之四中景建立张力；允许一次克制推进，清楚轮廓后再切印花近景",
        opening_rule="先以侧面或三分之四中景建立暗色轮廓和完整上装，不用闪烁特效",
        middle_rule=(
            "沿用受控转身或走动骨架，以稳定直视和明确肩线展示 mesh、水洗层次与图形，"
            "并保留印花可读停留"
        ),
        ending_rule="停在清晰轮廓与低饱和层次仍可辨认的稳定画面",
        preferred_shots=("侧面中景", "有限低机位", "印花近景"),
        preferred_actions=(
            "controlled_walk",
            "three_quarter_turn",
            "controlled_gaze",
            "print_detail_pause",
        ),
        pacing="slow_to_standard；商品姿态保留 2–3.5 秒，氛围切镜不得牺牲图形可读性",
        product_priorities=(
            "mesh jersey 与水洗材质",
            "黑白/暗红层次",
            "恐怖与 fandom 图形可读性",
            "完整轮廓",
        ),
        forbidden_mismatches=("身体变形", "过度闪烁", "纯赛博霓虹", "特效遮挡图形或材质"),
        research_note=(
            "2026-08-17 通过 Chrome MCP 直访首页复核：黑底高对比、Instrument Sans、mesh jersey、"
            "水洗单品及 occult/cryptid/horror/gaming/film 分类均可直接观察；"
            "动作仍只继承已验证通用骨架。"
        ),
    ),
    "pagewings": SiteStyleProfile(
        id="pagewings",
        version="1.0.0",
        status="active",
        name="泛读书 / PageWings",
        site_url="https://www.pagewings.com/",
        source_urls=(
            "https://www.pagewings.com/",
            "https://www.instagram.com/pagewings_brand/",
            "https://www.youtube.com/watch?v=8t6Rbf0K4BU",
            "https://www.youtube.com/watch?v=E3HB8sxEe2c",
        ),
        retrieved_at="2026-08-17",
        evidence_level="verified_site",
        tone="明亮、活泼、彩色复古图形感；文学、公共图书馆与人权是商品主题，不等于安静学院风",
        expression_language=(
            "人物自然亲和、明快并带轻松自信，使用开放视线、自然微笑和低幅度完整动作；"
            "只有输入已存在书本时才建立阅读关系，不凭空增加书本或眼镜。"
        ),
        audience="书迷、公共图书馆支持者、文学与人权主题图形服饰用户",
        palette=(
            "white",
            "ink black",
            "sunflower yellow",
            "garden green",
            "colorful vintage graphics",
        ),
        typography="Lato 正文，搭配大号紧凑展示字和手写式主题字",
        camera_language="以明亮眼平的正面中景和中近景清楚切换；允许低幅走动、轻推与图形近景，每次近景后回到完整商品",
        opening_rule="先以正面中景建立完整上装和核心书籍、图书馆或人权主题图形",
        middle_rule="用一次低幅走动或三分之四转身衔接印花近景；已有书本时才允许简短阅读关系镜头",
        ending_rule="回到整件商品与主题文字都清晰可读的正面或轻侧中景",
        preferred_shots=("正面中景", "印花中近景", "整身或侧背商品确认", "已有书本关系镜头"),
        preferred_actions=(
            "stance_shift",
            "controlled_walk",
            "print_detail_pause",
            "print_indicate_release",
        ),
        pacing="standard_to_fast；每套造型 2–4 秒，印花至少稳定停留 1–1.5 秒",
        product_priorities=(
            "书籍/图书馆/人权主题可读性",
            "彩色复古图形",
            "水洗材质与完整版型",
            "正背面商品确认",
        ),
        forbidden_mismatches=(
            "擅自新增书本或眼镜",
            "默认套用安静学院风",
            "道具遮挡核心图形",
            "高频切镜导致文字不可读",
        ),
        research_note=(
            "2026-08-17 通过 Chrome MCP 直访首页复核：Book Lovers、Banned Books、Public Libraries、"
            "Human Rights、Lato 字体和彩色生活方式横幅均可直接观察；"
            "官方样片已纠正旧的安静学院风假设。"
        ),
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
        tone="热情洋溢、活泼、明亮、亲和，同时保留教师日常的可信与实用感",
        expression_language=(
            "人物精神饱满、热情自信，使用明亮直视、自然大方的微笑和开放肩线；"
            "动作活泼完整但不蹦跳卖萌，不把教师表达幼儿化。"
        ),
        audience="教师和教育主题周边消费者",
        palette=("warm cream", "black", "soft classroom accents"),
        typography="Almarai / Arapey，正文清楚、标题有一点编辑感",
        camera_language="明亮有活力的朋友记录视角，允许短距离自然跟随、轻快横移和一次胸前细节推进",
        opening_rule="以热情对视、自然站姿或一到两步轻快走动建立整件服装和亲和感",
        middle_rule="以明亮微笑配合轻快三分之四侧身，让胸前图案朝向镜头，再展示一次袖口或下摆",
        ending_rule="停在教育主题文字清晰可读的中景，以自然微笑或放松表情结束",
        preferred_shots=("整身中景", "胸前图案中近景", "袖口/下摆细节"),
        preferred_actions=(
            "controlled_walk",
            "three_quarter_turn",
            "chest_print_pause",
            "hem_adjust",
        ),
        pacing="standard_to_fast，镜头活泼但动作完整，文字停留清楚且不幼稚",
        product_priorities=("教育主题文字", "可穿着的版型", "胸前印花", "实用细节"),
        forbidden_mismatches=("幼儿园式蹦跳", "暗黑低照度", "过度性感姿态", "道具堆砌"),
        research_note="首页分类 Math/Literature/Music/Art/Science 与暖奶油色、字体可直接观察。",
    ),
    "goodnurselife": SiteStyleProfile(
        id="goodnurselife",
        version="0.2.0-research",
        status="draft",
        name="护士 / GoodNurseLife",
        site_url="https://www.goodnurselife.com/",
        source_urls=(
            "https://www.goodnurselife.com/",
            "https://www.facebook.com/profile.php?id=61559705181293",
            "https://www.instagram.com/nursehutshop/",
        ),
        retrieved_at="2026-08-17",
        evidence_level="verified_site",
        tone="柔和、亲切、带职业幽默与小型配件的轻快感；专科和职称信息必须清楚",
        expression_language=(
            "人物亲切、可靠、精神状态良好，使用友善直视、放松微笑和利落站姿；"
            "不表演诊疗、疲惫崩溃或英雄化护理情节。"
        ),
        audience="护士、影像科、牙科、检验科等医疗岗位及其职业主题周边用户",
        palette=("warm ivory", "pastel pink", "soft blue", "floral green", "charcoal text"),
        typography="ABeeZee 正文，搭配高对比粗体标题和圆润品牌字",
        camera_language="清洁明亮的眼平观察、稳定跟随与短距离推进，节奏利落但避免医疗情节化运镜",
        opening_rule="用清晰中景建立服装轮廓与职业主题文字",
        middle_rule="以友善直视或自然微笑配合一次向前停稳或重心变化，衔接胸前文字、肩线和袖口细节",
        ending_rule="回到干净稳定的商品确认镜头，不增加器械或操作场景",
        preferred_shots=("清晰中景", "胸前文字近景", "肩线/袖口细节"),
        preferred_actions=(
            "stance_shift",
            "chest_print_pause",
            "sleeve_detail_pause",
        ),
        pacing="standard，商品信息优先",
        product_priorities=(
            "职业文字与专科标识",
            "徽章扣/配件真实尺寸",
            "scrub 与上装结构",
            "柔和配色和清晰对比",
        ),
        forbidden_mismatches=("擅自增加医疗器械", "危险操作示范", "夸张舞蹈", "不真实制服替换"),
        research_note=(
            "2026-08-17 通过 Chrome MCP 直访首页复核："
            "Shop By Department/Title/Specialty、badge reels、"
            "scrub sets、ABeeZee 与粉蓝柔和配色均可直接观察；因仍缺合格真人穿着样片，保持 draft。"
        ),
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
        expression_language=(
            "人物自信、挑衅、带一点冷幽默；允许直接盯镜、轻微侧笑、压低下颌和不对称肩线，"
            "用姿态制造怪诞感，不依赖面部扭曲或失控动作。"
        ),
        audience="喜欢怪诞、迷幻、反常规图形服饰的消费者",
        palette=("near_black", "neon_magenta", "high_contrast_graphic"),
        typography="Poppins / Jost / Dela Gothic One 的粗体展示感",
        camera_language="允许有张力的不对称取景、有限低机位和短促推进，但始终回到商品轮廓",
        opening_rule="用不对称中景和短暂停格快速建立强图形印花",
        middle_rule="以挑衅直视或冷感侧笑配合一次有限侧移、头肩轻倾，制造受控怪诞节奏",
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
        expression_language=(
            "人物放松、亲切、带轻微怀旧喜悦；使用自然微笑、从容侧望和舒展站姿，"
            "避免模仿年代人物的夸张表演或僵硬摆拍。"
        ),
        audience="喜欢 Americana、年代图形和复古棒球衫的消费者",
        palette=("white", "wine_red", "dark_green", "navy", "black"),
        typography="Figtree，现代清晰字体承载复古商品",
        camera_language=(
            "温暖、慢半拍的稳定 lookbook 观察，允许有限横移、柔和推进和广告式定格，"
            "不叠加遮字胶片噪点"
        ),
        opening_rule="以静态整身或一步停稳建立年代配色与完整轮廓",
        middle_rule="以从容侧望或轻松微笑配合一次半转展示滚边、背面或侧面，再给领口袖口稳定停留",
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
        version="1.1.0",
        status="active",
        name="骑行 / OrionRide",
        site_url="https://www.orionride.com/",
        source_urls=(
            "https://www.orionride.com/",
            "https://www.instagram.com/orionrideofficial/",
            "https://www.youtube.com/@orionrideofficial",
            "https://www.youtube.com/watch?v=tvAwCYDumyA",
            "https://www.youtube.com/watch?v=4c74x_gWsvc",
            "https://www.trustpilot.com/review/www.orionride.com",
        ),
        retrieved_at="2026-08-18",
        evidence_level="verified_site",
        tone="充满能量、自由、专注、功能明确，兼顾复古骑行图形和户外生活方式色彩",
        expression_language=(
            "人物专注、清醒、带户外运动后的轻快自信；站姿有准备感，视线坚定但不凶狠，"
            "只有输入支持骑行场景时才增加运动中的专注表情。"
        ),
        audience="gravel、MTB、downhill 与城市骑行生活方式用户",
        palette=("high_visibility_color", "outdoor_green", "earth_neutral", "graphic_accent"),
        typography="清晰运动无衬线，图形款允许复古骑行海报感",
        camera_language=(
            "商品片以稳定正面和三分之四中全景为主；输入已有自行车和户外环境时，"
            "允许短距离平行跟拍、低幅推进和更开阔的环境镜头。"
        ),
        opening_rule="先建立完整上装和骑行版型；无自行车参考时保持自然站姿，不补入车辆或护具",
        middle_rule="以专注视线和有准备感的肩线确认肩袖、后摆和背面图形；骑行或推车仅在道具与环境已存在时使用",
        ending_rule="回到清晰的正面或背面商品停留，避免让车轮、车把或装备遮住服装",
        preferred_shots=("正面中全景", "三分之四侧面", "背面中近景", "条件化户外长景"),
        preferred_actions=(
            "stance_shift",
            "three_quarter_turn",
            "back_reveal",
            "sleeve_detail_pause",
        ),
        pacing="standard；骑行情境可 standard_to_fast，但输入已提供的商品面与版型至少停留一秒半",
        product_priorities=("完整骑行版型", "肩袖和后摆", "背面图形", "口袋与功能结构"),
        forbidden_mismatches=(
            "无参考时新增自行车、头盔或护具",
            "危险越野或跳跃",
            "车辆占主体导致服装不可读",
            "拉伸印花证明面料性能",
        ),
        research_note=(
            "2026-08-18 复核到官网 gravel shirt、downhill jersey、cycling jersey 品类和"
            "官方 Instagram 的自行车、户外穿着及用户骑行内容；Trustpilot 为已认领档案，"
            "359 条评价、4.1 分，只用于身份与履约交叉验证。官网当前可视层触发 Access Denied，"
            "因此真实骑行动作继续作为自行车与户外环境条件动作，不进入无道具默认动作库。"
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
        expression_language=(
            "人物坚定、有力量、训练状态积极，使用自信直视、收紧但不过度的肩背姿态，"
            "可有一次轻松短笑；不怒吼、不力竭、不把肌肉表演凌驾于商品。"
        ),
        audience="力量训练、健身房文化和日常训练穿搭用户",
        palette=("black", "washed_charcoal", "white", "high_contrast_graphic"),
        typography="粗体运动无衬线和高对比口号字体",
        camera_language="以正面中大全身确认印花和手臂轮廓；允许短促低机位制造力量感，但必须回到商品停留",
        opening_rule="用稳定站姿或一步停稳建立上衣轮廓，不自动添加器械、拳击手套或训练带",
        middle_rule="以坚定直视和低幅肩部打开强化力量感，手臂离开核心印花；输入手位支持时可轻整领口",
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
        expression_language=(
            "人物轻松、俏皮、好奇，使用灵动视线、自然笑意和小幅不对称停姿；"
            "活泼来自人物节奏，不模仿动漫角色，也不表演刻板文化姿态。"
        ),
        audience="喜欢日本城市、动物、食物、幽默、运动和复古图形服饰的用户",
        palette=("washed_neutral", "artwork_color", "sport_accent", "summer_print"),
        typography="清晰日常无衬线，复杂图形与文化文字保留足够阅读空间",
        camera_language="明快眼平的正面膝上或中全景优先，允许小幅横向跟随、轻快推进和一次三分之四转体",
        opening_rule="先给胸前图形完整正面停留，不从站点名称推断动漫、赛博或传统表演",
        middle_rule="以灵动掠视或自然笑意带动一次轻快转体；复杂图形追加稳定中近景，球衣或衬衫只做低幅细节展示",
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
        tone="自信、舒适、自然、身体中立，带真实轻松的愉悦感，不制造修饰身体的表演",
        expression_language=(
            "人物放松、自信、愉快，允许自然微笑、开放视线和符合自身习惯的舒展姿态；"
            "不吸腹缩肩、不羞怯遮挡，也不把身体当成需要被修正的对象。"
        ),
        audience="需要包容尺码与多种日常、复古、幽默和图形风格的消费者",
        palette=("washed_color", "americana_accent", "graphic_color", "everyday_neutral"),
        typography="清楚易读的日常无衬线，图形和幽默文字优先",
        camera_language="诚实眼平的固定竖屏全身为主，允许自然跟随与轻三分之四角度，不用斜拍或局部裁切制造缩身效果",
        opening_rule="以自然正面全身建立衣长、袖长和宽松量，允许人物按自身习惯舒适站立",
        middle_rule="以自信微笑和开放视线配合前后脚轻错位、小幅重心变化或一步停稳，展示真实活动空间且不遮胸腹",
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
    "magicstation": SiteStyleProfile(
        id="magicstation",
        version="1.0.0",
        status="active",
        name="魔法 / PurpleHecate",
        site_url="https://www.purplehecate.com/",
        source_urls=(
            "https://www.purplehecate.com/",
            "https://www.instagram.com/purplehecateofficial/",
            "https://www.tiktok.com/@purplehecate_official",
            "https://www.youtube.com/@purplehecate/shorts",
            "https://www.trustpilot.com/review/purplehecate.com",
        ),
        retrieved_at="2026-08-18",
        evidence_level="verified_site",
        tone="神秘、梦幻、明亮而俏皮，以紫色魔法氛围承托可读的服装图案",
        expression_language=(
            "人物自信、好奇、带轻微神秘感，可用柔和直视、侧望和自然笑意；"
            "神秘感来自光色与停顿，不使用施法手势、惊恐表情或角色扮演。"
        ),
        audience="喜欢 witchy、塔罗、星座、奇幻生物和灵性图形服饰的消费者",
        palette=("deep_purple", "electric_violet", "black", "moonlight_white", "pink_glow"),
        typography="优雅高对比衬线标题配清晰正文；商品文字和图形优先保持完整可读",
        camera_language=(
            "以稳定正面和三分之四中景展示图案与轮廓，允许低幅柔和推进、轻微横移和一次"
            "紫色光感转场；光效只能存在于背景或边缘，不覆盖人物、文字和商品结构"
        ),
        opening_rule="先用正面或轻三分之四中景建立完整服装，再以紫色环境光或图形色彩引出神秘氛围",
        middle_rule="以柔和侧望、自然笑意和一次受控转身展示前后图形；复杂塔罗、星座或奇幻图案追加稳定停留",
        ending_rule="回到图案无遮挡的完整商品画面，以安静直视或自然侧望结束，不加入施法结果或虚构道具",
        preferred_shots=("正面中全景", "轻三分之四中景", "图形中近景", "背面图案中景"),
        preferred_actions=(
            "stance_shift",
            "three_quarter_turn",
            "print_detail_pause",
            "back_reveal",
        ),
        pacing="standard_to_slow，以柔和推进和一到两秒图案停留营造神秘感",
        product_priorities=(
            "塔罗与星座图形",
            "奇幻生物印花",
            "完整轮廓",
            "文字可读性",
            "前后图案关系",
        ),
        forbidden_mismatches=(
            "施法、召唤或夸张角色扮演",
            "无参考时新增法杖、水晶、塔罗牌或魔法书",
            "紫色烟雾、粒子或闪光遮挡商品",
            "把日常印花服装改造成戏服或盔甲",
            "快速故障闪烁导致图形和文字不可读",
        ),
        research_note=(
            "2026-08-18 复核官网紫色魔法主视觉、witchy/塔罗/星座/奇幻服装品类及官方"
            "Instagram 的商品帖、轮播与竖屏 Reel；Trustpilot 为已认领档案，447 条评价、"
            "3.7 分，只用于身份、商品和履约交叉验证，不作为视觉或动作证据。"
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
