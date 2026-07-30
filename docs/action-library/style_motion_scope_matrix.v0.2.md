# 站点风格、动作、机位与节奏矩阵 v0.2

- 日期：`2026-07-30`
- 批次：OrionRide、IronPandaFit、Tokyo-Tiger、BoldOversize
- 结构化观察：[action_observations_batch_002.json](./action_observations_batch_002.json)
- 来源清单：[source_manifest.v0.2.json](./source_manifest.v0.2.json)

## 证据等级

- `A`：官方视频已直接播放，并记录了可复查的时间点、机位和动作。
- `B`：官网目录、官网文案或官网社媒链接支持的品类与主题事实。
- `C`：由 A/B 证据推导的动作库或拍摄建议，仍需生成回放验证。
- 未完整播放的视频不补写动作；标题、封面、字幕和时长不能替代人体动作观察。

## 先分清四层

1. **通用人体动作**：不依赖站点、器械或文化符号，如自然站定、重心变化、三分之四转体。
2. **品类动作**：由服装结构触发，如背印展示、领口整理、球衣肩袖展示、长裙低幅摆动。
3. **场景条件动作**：依赖自行车、训练器械或特定环境，必须声明 `requiredProps` 与 `requiredEnvironment`。
4. **站点表达配方**：动作权重、表情、机位、节奏和剪辑组合；多数站点差异在这里，不需要复制一套同义动作 ID。

## 全站通用动作

| 动作 | 商品目标 | 执行限制 |
| --- | --- | --- |
| `front_neutral_hold` | 建立完整正面版型和图案 | 手臂自然下垂或轻微离开躯干，不遮胸腹图案 |
| `small_weight_shift` | 减少僵硬并展示自然垂坠 | 幅度小，不扭曲躯干或制造缩身效果 |
| `three_quarter_turn` | 同时确认正面、侧面和宽松量 | 15–30 度为主；硬切不能证明连续转体 |
| `controlled_front_approach_to_settle` | 一至两步进入后回到清晰商品画面 | 进入后至少停留 1–1.5 秒 |
| `controlled_walk_exit` | 自然结束完整穿搭片段 | 不跑跳，不让商品在结尾完全离开过早 |
| `back_facing_product_pause` | 展示背印和后身版型 | 必须有可靠背面参考 |
| `print_frame_open_palms` | 在不遮挡图案的前提下形成视觉框景 | 手掌位于印花下方；当前仍是候选 |

## 品类与场景条件动作

| 条件 | 动作/镜头 | 适用范围 | 状态 |
| --- | --- | --- | --- |
| 有大背印 | `back_facing_product_pause`、背面中近景 | 四站及批次 001 的背印商品 | 通用条件动作 |
| 领口、帽衫、Pump Cover | `bilateral_neckline_settle` | IronPandaFit 等结构适配商品 | 候选，仅 1 个直接来源 |
| 骑行服 + 自行车 | `side_ride_by`、`gravel_ride_away_rear`、`bike_side_back_reveal`、`push_bike_uphill` | OrionRide 条件场景 | 不进入无道具默认库 |
| 网眼球衣 | 正面停留后轻微转体，展示肩袖与宽松轮廓 | 四站均可能出现 | 品类高权重，非东京或骑行独占 |
| Aloha/纽扣衬衫 | 小幅袖口、侧缝或衣摆展示 | Tokyo-Tiger、OrionRide 等 | C 级建议，需视频复核 |
| 长裙/Maxi | 低幅侧向摆动后回到完整站姿 | BoldOversize、Tokyo-Tiger 等 | C 级建议，需视频复核 |

## 四站对照

| 站点 | 边界 | 动作权重 | 机位 | 节奏 | 站内表达 | 明确排除 |
| --- | --- | --- | --- | --- | --- | --- |
| OrionRide | 骑行生活方式、gravel/MTB/downhill 功能服和图形日常服；不等同纯公路竞赛 | 背面版型、口袋位置、侧身衣摆、骑行或推车条件动作 | 商品版用正面/三分之四中全景；场景版用侧面长景、后方长景、车旁背面中近景 | 商品版 `standard`；骑行蒙太奇 `standard_to_fast`；背印停留更慢 | 户外探索 + 彩色/复古骑行图形 + 真实骑行功能 | 自动添加车、头盔或护具；危险越野；只有手部拉伸、平铺或车辆占主体 |
| IronPandaFit | 力量训练和健身房文化；不是训练教程、极限挑战或健美比赛 | 正面力量站姿、受控步入后站定、印花清晰的手臂轮廓、条件领口整理 | 中大全身为商品确认；训练低机位和器械近景只能作氛围片段 | `standard_to_fast`，约 1–4 秒硬切；商品停留需单独保留 | 训练切片 → 正面印花停留 → 图形特写 → 恢复反应 | 杠铃/拳击/危险负重进入默认库；力竭、疼痛、赤膊、器械遮挡、从成人推导儿童动作 |
| Tokyo-Tiger | 日本文化与日常图形服装，含复古、幽默、动物、食物、城市、运动；不自动等于动漫、赛博或原宿夸张 | 正面图案停留、开放掌框景、球衣肩袖展示、衬衫低幅结构展示 | 竖屏膝上或中全景，正面优先；复杂图案追加中近景 | `standard_to_slightly_fast`，有效姿态约 1–1.8 秒；木版画式图案可更慢 | 高识别图形、复古/俏皮/文化图形与球衣、夏日衬衫的组合 | 武器道具；鞠躬/武士/角色扮演刻板化；手遮汉字与文化符号；未播放视频的推断 |
| BoldOversize | 大码是尺码、版型和人群，不是审美；实际横跨复古、幽默、塔罗、动物、运动和节日 | 自然错位站姿、小幅重心变化、小步前移、正面与三分之四真实版型确认 | 固定竖屏全身为主；相机约躯干高度；正面和侧面都保留 | `standard_to_slow`，约 3–5 秒一阶段或连续自然移动 | 身体中立地展示衣长、袖长、胸围余量和活动空间 | 吸腹、缩肩、踮脚、极端侧身、遮腹、胖瘦对比、指向“问题部位” |

## 通用、跨站高权重与站内特有

### 通用

- 正面自然站定、小幅重心变化、一步进入或退出、15–30 度三分之四转体。
- 手和道具不遮核心图案；每条短视频至少保留一次 1–1.5 秒可读商品画面。
- 背印、领口、袖口、衣摆动作只由商品结构触发，不由站点名称触发。
- 动作与镜头分开记录：图案近景、面料极近景、硬切、换装都是镜头/编辑语法。

### 跨站高权重

- **运动图形服**：OrionRide 与 IronPandaFit 都提高稳定落位、手臂轮廓和功能部位权重，但一个偏骑行户外，一个偏健身房。
- **球衣**：OrionRide、IronPandaFit、Tokyo-Tiger、BoldOversize 都可使用正面停留与肩袖转体；球衣动作不是某站独占。
- **复古图形**：Tokyo-Tiger 与 BoldOversize 的洗水/复古款可继承批次 001 的慢半拍图案停留。
- **宽松版型**：Pump Cover、oversized jersey、plus-size T 恤都要展示衣长和余量，但不得用拉扯或缩身姿势证明“宽松/显瘦”。

### 站内特有或强条件

- **OrionRide**：真实自行车与 gravel/outdoor 环境组成的骑行路径；这是道具和场景条件，不是无条件人体动作。
- **IronPandaFit**：目前没有独占人体动作；特征是健身切片与清晰商品停留的编辑组合。
- **Tokyo-Tiger**：目前没有独占人体动作；特征是文化/幽默图形的可读停留及球衣、Aloha 衬衫权重。
- **BoldOversize**：目前没有独占人体动作；特征是身体中立执行规范和严格禁止缩身、遮腹、胖瘦对比。

## 节奏基线

- `slow`：单个有效姿态约 2.5–5 秒，适合真实版型、长裙、复杂长文字。
- `standard`：单个动作块约 1.5–3 秒，适合大多数商品视频。
- `standard_to_fast`：训练或户外场景可用 0.8–2 秒切片，但必须插入至少 1–1.5 秒无遮挡商品确认。
- 不把快切当动作，也不因节奏快而省略正面、背面或图案可读性验证。

## 本批候选状态

| 候选 | 证据 | 当前结论 |
| --- | --- | --- |
| `controlled_front_approach_to_settle` | IronPandaFit `LfuPXgmEAfk`；与现有 `controlled_walk` 语义相近 | 先做命名合并评估，不新增生产动作 |
| `bilateral_neckline_settle` | IronPandaFit `hKbeWCmbkhU` | 1 个来源，条件候选 |
| `relaxed_staggered_weight_shift` | BoldOversize `lhdqaRR0Q-k` | 应优先映射现有 `stance_shift` |
| `small_step_front_hold` | BoldOversize `lhdqaRR0Q-k` | 应优先映射 `controlled_walk` + 停留 |
| `gravel_ride_away_rear` | OrionRide `tvAwCYDumyA` | 场景候选，必须有自行车与户外参考 |
| `ride_toward_low_angle` | OrionRide `tvAwCYDumyA` | 场景候选，生成风险高 |
| `side_ride_by` | OrionRide `4c74x_gWsvc` | 场景候选 |
| `bike_side_back_reveal` | OrionRide `4c74x_gWsvc` | 场景候选，车体可能遮挡 |
| `push_bike_uphill` | OrionRide `4c74x_gWsvc` | 场景候选，地形和车把接触风险高 |

本批不新增 `active` 或 `draft` 动作。所有新候选仍缺少三条独立视觉来源或生成回放；可映射既有动作的项应先去重。
