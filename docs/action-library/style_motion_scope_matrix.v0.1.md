# 站点风格、动作、机位与节奏矩阵 v0.1

- 日期：`2026-07-30`
- 范围：GeeksOutfit、GuidingCross、NerdyWave、PageWings、Teachersgram、GoodNurseLife、ClassyOutlaw、TheRetroTee
- 原始视频：不入库
- 结构化观察：[action_observations_batch_001.json](./action_observations_batch_001.json)

## 证据等级

- `V`：视频已经直接播放并按时间轴观察。
- `S`：官网或官方账号可验证的品类、主题与视觉事实。
- `P`：专业推导或生产安全规则，不能写成已观察动作。
- `H`：继承假设；在该站没有合格真人样本前，不得升级成站内规则。

## 先分清三层

1. **动作语义层**：动作本身尽量跨站复用，例如重心变化、三分之四转身、印花停留。
2. **站点表达层**：站点只调整动作权重、表情、幅度、构图、光线和节奏。
3. **镜头/剪辑层**：硬切、换装、局部推进、闪切属于镜头语法，不写成 `MotionAction`。

当前没有证据证明某个基础人体动作只能属于单一站点。真正的站点差异主要来自动作组合和参数，而不是复制八套同义动作。

## 全站通用动作

下列动作适用于多个站点，但仍需服装、场景和输入参考满足条件。

| 动作 | 当前状态 | 通用商品目的 | 条件与限制 |
| --- | --- | --- | --- |
| `stance_shift` | 生产库已有 | 建立整身轮廓，减少僵硬站姿 | 肩线和印花保持稳定 |
| `controlled_walk` | 生产库已有 | 展示整体穿搭与垂坠 | 只走 2–3 步；空间不足时禁用 |
| `three_quarter_turn` | 生产库已有 | 同时展示正面和侧面版型 | 硬切到侧面不能证明连续转身 |
| `print_detail_pause` | 生产库已有 | 让印花或文字获得可读停留 | 不重绘图案；局部后必须回整件 |
| `print_detail_pause` | 生产库已有 | 胸前文字或印花正对镜头 | 手、字幕、书、杯子不得遮挡 |
| `hem_adjust` | 生产库已有 | 整理衣摆或显示宽松量 | 仅触碰无印花区一次并立即放下 |
| `sleeve_detail_pause` | 生产库已有 | 展示袖口、肩线、raglan/滚边 | 不拉伸袖部图案 |
| `controlled_gaze` | 生产库已有 | 建立人镜交流或冷感视线 | 表情强度由站点控制 |
| `back_reveal` | 生产库已有，条件动作 | 展示背印与背面版型 | 必须有可靠背面参考 |
| `asymmetric_pause` | 生产库已有，风格加权 | 形成轻微肩胯错位 | 不扭曲人体与衣物 |

研究语料已经定义但尚未进入生产 `ACTION_LIBRARY` 的通用原子包括：
`one_step_settle`、`torso_angle_hold`、`print_indicate_release`、`hem_open_release`、
`sleeve_display`、`over_shoulder_back`、`eye_contact_soft_smile`、`controlled_gaze`。
它们应先完成命名合并和生成回放，避免与现有动作语义重复。

## 通用镜头语法

| ID | 路径 | 适用范围 | 规则 |
| --- | --- | --- | --- |
| `shot_full_detail_return` | 完整上装/整身 → 印花或材质近景 → 回完整商品 | 全站 | 近景不能作为结尾唯一商品画面 |
| `shot_front_angle_confirm` | 正面建立 → 三分之四角度 → 正面或完整商品确认 | 全站 | 一次只做一个身体动作 |
| `shot_front_back_confirm` | 正面 → 背面 → 背印停留 | 有背面参考的商品 | 硬切与连续转身要分开记录 |
| `shot_multi_look_blocks` | 每套造型 2–4 秒独立动作块 | PageWings、Teachersgram、TheRetroTee | 换装是剪辑，不是人体动作 |
| `shot_narrative_ugc` | 人物建立 → 对话移视 → 角色/印花硬切 | GeeksOutfit 特有模板 | 不进入默认服装动作模板 |
| `shot_product_only_macro` | 完整商品 → 局部宏观 → 回完整商品 | 无人物产品库 | 不混入人体动作库 |

## 新动作候选

| 候选 | 证据来源 | 适用范围 | 当前状态 |
| --- | --- | --- | --- |
| `print_frame_open_palms` | ClassyOutlaw `DbLvn0nME_d`；TheRetroTee `Da5ubLhuFgE` | 跨站通用，偏大胸印 | 已有 2 个独立来源；还需 1 个来源和生成回放 |
| `held_garment_front_hold` | Teachersgram `DbYuWywpIjx` | 已有未穿衣物的开箱/赠样 UGC | 1 个来源；持衣和穿衣必须分镜 |
| `back_print_hip_frame` | GuidingCross `C8551q67UJI` | 有可靠大背印参考的商品 | 1 个来源；手保持在背印下方 |
| `single_arm_flex_print_hold` | TheRetroTee `Da5ubLhuFgE` | 文案明确表达 tough/strong 的款式 | 1 个来源；不是站点默认动作 |

## 八站对照

| 站点 | 主题与审美边界 | 动作权重 | 角度与景别 | 节奏 | 站内特有表达 | 证据边界 |
| --- | --- | --- | --- | --- | --- | --- |
| GeeksOutfit | geek、流行文化幽默、怀旧图形；不是纯科技或赛博 | `controlled_gaze`、稳定坐姿或站姿、胸印停留 | 眼平固定中景；默认商品片仍需整身/完整上装 | 商品片 `standard`；叙事 UGC 可 8–15 秒一角色 | 坐姿分角色吐槽，不同图案作为角色标记 | `DbXB7D3T0p0` 为喜剧广告，默认动作模板排除 `V` |
| GuidingCross | 信仰是内容主题；视觉可为水洗街头、健身、日常 OOTD | `controlled_walk`、背面停留、`over_shoulder_back`、文字停留 | 眼平整身；正面、三分之四背面、完整背面 | 信仰文字款 `slow_to_standard`；街头/健身子线 `standard_to_fast` | 大背印是主展示面；手位可在背印下方形成框景 | 硬切只验证姿态，不验证连续转身 `V` |
| NerdyWave | dark alt、复古 fandom、恐怖/神话/游戏母题；不是泛哥特或纯赛博 | `controlled_gaze`、`three_quarter_turn`、印花停留；材质条件化动作 | 眼平或极轻低机位的侧/三分之四中景，清晰轮廓后再近景 | 商品版每姿态 2–3.5 秒；氛围版可 1.5–2.5 秒一切 | 黑白/暗红氛围、mesh jersey 与水洗层次 | 已看样本均未产出站内新人体动作 `V/S` |
| PageWings | 文学是受众主题；实际可为高饱和、活泼、彩色复古图形 T | 印花停留、指示后放下、低幅走动 | 正面中近景、印花近景、整身/侧背确认 | `standard_to_fast`；每造型约 2–4 秒，印花至少停 1–1.5 秒 | 有书输入可建立文学 UGC 分支；无书不得加书或眼镜 | 官方 `8t6Rbf0K4BU` 修正“安静学院风”假设 `V` |
| Teachersgram | 教师/学科/年级是受众主题；审美为明亮、亲和、工作休闲 | 胸印停留、短衣摆动作、重心变化、亲和视线、袖肩展示 | 固定竖屏正面，中景到近全身，课堂环境 | `standard`；每件约 2.5–4 秒 | 课堂语境和“持衣 → 穿着”的赠样 UGC 分镜 | `DbYuWywpIjx` 为合格真人赠样样本 `V` |
| GoodNurseLife | 护士是受众主题；日常、清爽、友好仍是待验证审美 | 暂无站内已验证动作；只能继承低风险通用骨架 | 建议清晰正面中景和文字近景，但当前仅为 `P/H` | 建议 `standard`，当前无真人节奏实证 | 当前只有负规则：不擅自加听诊器、针具、病房操作或制服 | 已看样本均为配饰、挂拍或平铺，无合格人体动作 `V` |
| ClassyOutlaw | grotesque/surreal、怪物/眼睛/迷幻/挑衅文案；不等同 NerdyWave | `asymmetric_pause`、头肩轻倾、侧移、印花框景 | 偏心中景、正面全身、三分之四/背面、短印花近景 | `standard_to_fast`；0.8–1.8 秒一节拍，总长 8–12 秒 | 强图形、不对称和“整身 → 局部 → 整身”权重更高 | 第一套 `DbLvn0nME_d` 合格，第二套遮挡段排除 `V` |
| TheRetroTee | 年代数字、Americana、raglan/ringer、复古广告感；不默认加胶片噪点 | 重心、胸印停留、袖肩展示、亲和微笑、轻俏皮手势 | 眼平固定，大腿以上中景加少量整身/胸印近景 | 每套 5–7 秒，含 2–3 个 1.5–3 秒姿态节拍 | 年代造型蒙太奇、raglan 对比袖展示、广告式定姿 | `Da5ubLhuFgE` 只有正面，不能验证背面动作 `V/S` |

## 哪些是通用，哪些是站内特有

### 通用

- 稳定建立商品、一次低幅动作、可读停留、回到完整商品确认。
- 手、字幕和道具不覆盖核心印花或文字。
- 正面、背面、袖口和材质使用对应动作，背面动作必须有背面参考。
- 一条 8–15 秒商品视频只保留 1–2 个主动作。
- 连续舞蹈、危险道具、复杂换装、配饰主导、无人物内容不进入首批人体动作库。

### 跨站风格簇

- **亲和信息型**：PageWings、Teachersgram；正面中景与中近景交替，2–4 秒动作块，轻微位移和自然人镜交流。
- **暗黑图形型**：NerdyWave、ClassyOutlaw；冷感视线、清晰轮廓、侧角和短停格。NerdyWave 更克制，ClassyOutlaw 更高对比、更快。
- **复古俏皮型**：GeeksOutfit、TheRetroTee；图形与年代感优先。Geeks 更偏叙事吐槽，Retro 更偏定姿和袖部结构。
- **文字/背印型**：GuidingCross 与部分职业主题商品；文字可读性高于表演，背印动作严格依赖参考。

### 站内特有

- GeeksOutfit：分角色对话和角色化印花的 `narrative_ugc`。
- GuidingCross：街头/健身子线的大背印快速前后构图。
- NerdyWave：horror/occult/cryptid/fandom 母题与黑色材质层次。
- PageWings：已有书本时的文学 UGC 分支，以及彩色活泼商拍。
- Teachersgram：真实课堂语境和多款赠样的持衣/穿着分镜。
- GoodNurseLife：目前无已验证站内人体动作，只有禁止医疗情节化的负规则。
- ClassyOutlaw：怪诞强图形、不对称停格和印花框景的高权重组合。
- TheRetroTee：raglan/ringer 对比袖、年代造型蒙太奇和文案匹配的俏皮手势。

## 节奏基线

- `slow_to_standard`：每个姿态约 2–3.5 秒；适合信仰文字、暗黑商品确认和长文字。
- `standard`：每个动作块约 2–4 秒；适合教师、护士安全基线和日常商品片。
- `standard_to_fast`：每节拍约 0.8–1.8 秒或每造型约 2–4 秒；适合 ClassyOutlaw、PageWings 活泼商拍和 GuidingCross 街头/健身子线。
- 无论速度如何，核心印花或文字都应至少保留约 1–1.5 秒无遮挡可读画面。

## 尚不能做的升级

- `print_frame_open_palms` 只有 2 个独立视频来源。
- 其余新候选都只有 1 个来源。
- GoodNurseLife 没有合格真人穿着视频。
- 未完成真实生成回放。

因此本轮不新增 `active` 或 `draft` 动作。
