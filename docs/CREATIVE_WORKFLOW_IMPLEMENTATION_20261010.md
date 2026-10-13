# 衣影工坊 Creative Workflow v1.0 开发任务书

日期：2026-10-10
状态：用户已授权 CW-1 隔离骨架与单正面 Fake 首包；真实验证和上线门未通过
性质：Codex Implementation Specification，不是生产验收报告

## 0. 立项前置项（CW-0.5）

2026-10-10 用户接受“整体骨架 + 单正面 Fake 闭环、边测边改”，前置门拆为三层：隔离开发、真实验证、上线。工程合同/版本/权属/幂等审查允许增量 CW-1 骨架实现；真实素材许可、模型报价/预算和质量收益目标在真实验证前完成，生产迁移/发布与 Checkpoint 2 在上线前完成。不以尚缺业务样本阻塞 Fake 开发，也不以 Fake PASS 判真实质量通过。当前只授权 test 环境/local store/Fake-Replay；不允许创建付费生成任务、迁移生产数据库或扩大前端范围。

### 0.1 能力盘点与边界冻结

建立一份 `capability_matrix`，逐项标记 `EXISTS`、`ADAPTER_REQUIRED`、`NEW_BUILD`、`UNSUPPORTED`：

- 衣影工坊已有：图片批次、配额、幂等、部分失败/未知提交、对象存储、源图哈希、逐项人工审核、内容库风格/动作、固定视频工作流、Prompt 快照、历史任务恢复。
- 插件可吸收：Canonical Product 真值优先、Brand Routing、Product/Character/Scene/Reality/Composition 分层、Reality 六维、Photo Style 与 Scene DNA 分离、参考污染分级、Prompt Preservation、Compact Reality Compiler、Storyboard Continuity、四维像素复核、Recovery Capsule、证据状态分离。
- 必须明确新增：CreativeTask 编排、导演输入适配、持久化素材引用、Character/Scene 能力矩阵、Prompt Registry、导演视频执行分支、有限自主循环和逐轮审计。
- 暂不支持的能力必须显式列出，不得把插件中的文字规则包装成已有的人物资产、场景资产、参考图像权重隔离、视频渲染或视觉评分能力。

### 0.2 真实 Product 与素材持久化合同

在任何跨阶段开发前冻结 `Canonical Product` 和等价的 `CreativeAssetLink` 合同，至少包含：

- `source_type`、`source_id`、`owner_id`、对象存储定位、SHA-256、媒体类型、尺寸/格式；
- `role`（`PRODUCT`、`IDENTITY`、`SCENE`、`STYLE`、`FIRST_FRAME`、`STORYBOARD`）、`view`、顺序和 `canonical` 标记；
- `evidence_status`（`OBSERVED_REFERENCE`、`USER_ASSUMED`、`UNDECIDED`）、`access_status`、`qualification_status`、撤回/过期状态；
- 保留策略、物化状态、来源任务、上传会话和跨阶段复用规则。

一次性 `StagedUpload`、浏览器 `File`、IndexedDB、聊天窗口中的图片或生成图文件名均不能单独成为跨阶段真源。生成图转视频必须保留原商品、首帧、分镜的来源链、哈希、审核状态和物化位置。

### 0.3 导演执行隔离证明

立项时冻结隔离方案和测试入口；进入 CW-4 后以 Fake/Replay 和旧任务回归证明，完成证明前不得开放导演视频生成：

- 导演视频请求有明确的 `execution_mode=director_fixed` 或等价命令分支；
- 导演路径不调用旧 `compile_video_plan`、动作随机选择或 `apply_video_learning`；
- 旧 `automatic`、`custom` 和已提交历史任务的 Prompt、attempt、Provider 查询/恢复行为不改变；
- 导演路径只执行已确认生产包和可验证素材绑定，不在提交时重新规划或静默改写。

### 0.4 状态、动作、预算和授权矩阵

在实现 API 前冻结 `CreativeTask`、`ParentTask`、`ImageGenerationBatch`、attempt 和 output 的权威边界，并形成以下矩阵。`UNKNOWN/WRITE_UNCERTAIN` 是执行/持久化结果，不另造 CreativeTask 远端状态：

- 每个状态允许的动作、前置条件、版本校验、失败码和恢复目标；
- `ACTION_REQUIRED`、`BLOCKED`、`UNKNOWN`、`WRITE_UNCERTAIN` 的用户动作与服务端恢复规则；
- 分析、规划、首帧、分镜和视频的模型/版本、最大调用次数、超时、预算、授权时间和是否付费；
- 崩溃恢复、幂等重放、超时重试和未知提交均不得形成无限自动重试。

### 0.5 DNA、方向和 Prompt 真源

首个代码包前必须冻结：

- 事实来源键、`facts_revision`、`confidence_basis`、未知/假设边界和方向差异向量；
- A/B/C 的方向数量、连续索引、至少两项实质差异和单变量例外；
- Prompt key、版本、规则集版本、模型、输入/输出哈希、激活状态和不可变历史；
- 插件规则、团队知识、品牌卡和第三方参考的许可范围，未经授权的资料不得进入代码仓库或公开包。

Prompt 不得同时散落在代码、规则文件、JSON 和前端默认值中形成多个真源。规则版本更新不得原地修改已提交 Prompt 的历史。

### 0.6 真实性基线与立项成功指标

立项前选择至少一个有使用权的真实服装 SKU 和已有失败/基线图，设计小样本对照方案，冻结指标定义、阈值、样本范围、模型、参考输入、授权次数和停止条件。没有可用历史基线时标“待另行授权采样”，不为通过立项门擅自调用 Provider。真实生成验证在 CW-3 后另行授权执行，区分：

- `static_rule_validated`：合同和编排规则通过；
- `runtime_input_verified`：实际素材、Prompt 和 Provider 入参证据可核对；
- `pixels_reviewed`：真实输出像素完成逐项复核；
- `quality_A_B_verified`：与基线对照后，真实性改善达到预设阈值。

至少冻结首个合格首帧耗时、重复上传率、重复提交率、合格分镜率、人工操作分钟数、单任务成本、真实性缺陷率、自主循环平均迭代次数、停止原因分布和 `UNKNOWN` 占比。没有这些基线，不得以“Prompt 更完整”或“规则已加载”宣称真实度提升。

### 0.7 CW-0.5 通过条件

能力矩阵、数据合同、状态/动作/预算矩阵、Prompt Registry 方案、品牌/素材许可清单、旧模式隔离证明方案、真实度基线/采样计划和第一包测试计划均已评审；testing 与实际 `main` 的迁移 heads、运行配置边界和未提交改动已记录；没有必须依赖猜测或生产状态才能继续的关键项。通过后才进入 CW-1。

| 前置项 | 交付证据 | 通过责任 | 当前状态 |
| --- | --- | --- | --- |
| CW-P01 | testing/main 能力矩阵、已有服务/测试位置、Character/Scene 缺口及 Provider 输入限制 | 工程评审 | 源码证据已交付，待评审 |
| CW-P02 | Canonical Product、持久素材/撤回/保留/物化合同、shot_id 来源映射 | 工程评审 | 设计已交付，待 Product 对齐决策及评审 |
| CW-P03 | 完整状态迁移/动作/恢复矩阵和异步 attempt 权威边界 | 工程评审 | 设计/Fake 证据已交付，待评审 |
| CW-P04 | 付费分析/规划/生成/复核预算矩阵、循环授权/停止/恢复合同 | 产品负责人确认成本边界，工程评审并发与幂等 | 设计/Fake 已交付，金额/模型/有效期待确认 |
| CW-P05 | Grounded DNA schema、方向差异向量、Prompt Registry/规则归一化方案 | 工程评审 | 方案及来源哈希已交付，待评审 |
| CW-P06 | 品牌/人物/摄影参考许可清单和功能能力降级表 | 素材负责人确认使用范围，工程评审 | 台账已交付，真实许可/样本待确认 |
| CW-P07 | 两侧迁移 heads、隔离升级/回归计划、director_fixed 隔离验证计划 | 工程评审 | 空库 SQLite/选集已验证，对齐/PG/带数据/新分支待验证 |
| CW-P08 | 基线/采样计划、指标定义/目标阈值、真实质量验证预算与 CW-1 测试计划 | 产品负责人确认质量与收益目标，工程评审 | 候选目标/计划已交付，待确认及真实基线 |

2026-10-10 已启动 CW-0.5，证据见 `CREATIVE_WORKFLOW_PREFLIGHT_20261010.md`、`docs/contracts/creative-workflow-preflight.v1.json` 和本轮 Sprint Report。离线检查 PASS 不等于上述前置项通过；D01 至 D06 尚待处理，不进入 CW-1、不开放付费或自动修订。

## 1. 目标与执行边界

保留现有生图、生视频和任务中心，在生产引擎上增加智能导演编排层。

```text
上传商品正面（背面/详情可选）
→ 人工选择品牌 / 通用风格
→ 商品分析与 DNA 提取
→ A/B/C 创意方向
→ 选择方向并确认生产包
→ 明确授权生成首帧（可选择有界真实性修订）
→ 按模块顺序生成、复核、在授权内定向修订
→ 人工审核、选择首帧
→ 提示补充背面 / 确认纯色无印花背面
→ 明确授权生成指定分镜（可选择有界真实性修订）
→ 逐张人工审核、选择、排序
→ 自动拉取产品图及合格分镜
→ 明确授权创建视频任务
→ 视频技术校验、人工最终审核与交付
```

上传、选方向、确认方案、选择图片均不等于付费生成授权。
分析和规划如使用付费模型，也必须明确模型、调用预算、超时和授权，不宣称免费。
本任务书不授权付费调用、生产数据库迁移、服务重启、部署或上线。

继续使用 React/TypeScript/Vite、FastAPI、SQLAlchemy、Alembic 和已有 API 客户端。
不重构 Provider、Runner、计费、幂等、恢复或既有任务中心。
不启用参考性质的 `fashion_factory`，不引入无限自由的后台 Agent。允许本项目在明确授权、预算、调用次数、质量门槛和停止条件下运行有界自主导演/真实性改进循环；插件自身的“不做自主 Agent 循环”仅适用于插件交互宿主，不限制本项目的服务端编排能力。

## 2. 页面与人工检查点

智能导演台作为 `/studio/image` 中的“智能导演”模式，与原“自定义生图”并存。
不新增独立 `/director` 产品路由；保留四个工作区及现有 query-view 深链接。
`/studio/video` 面向用户只有“自定义生成”和“自动生成（导演任务）”两种模式。

本次规则修订不代表 Video Studio 的 Checkpoint 1 方向已被接受。
后端合同和隔离验证可先拆分；导演前端和其他工作区扩展仍在 Checkpoint 1 人工接受后实施。
Checkpoint 2 保留为人工上线验收，不由测试 PASS 替代。

## 3. 商品事实、背面策略与 DNA

商品正面为最低输入，背面与详情图可选，不得要求上传背面才能分析。
分析输出 `category`、`selling_points`、`locked_elements`、`target_user`，并分别记录事实来源、未知项和假设。
Canonical Product 来自用户上传的真实原图；生成图和外部摄影参考不能替代商品真值。

生成分镜前提示补充背面。已有背面时自动复用，不重复索要。
没有背面时，用户可确认按“背面无印花纯色”继续；不强制上传或额外生成背面参考图。
纯色默认使用正面可可靠识别的衣身底色，不复制正面印花到背面。
底色无法可靠判断时要求选择颜色或补图，不猜测。
不凭空增加背面文字、Logo、印花、装饰和无法观察到的结构细节。

```json
{
  "back_policy": {
    "mode": "user_assumed_plain",
    "base_color": "用户确认的衣身底色",
    "print": "none",
    "evidence_status": "USER_ASSUMED",
    "confirmed_by": "真实用户 ID",
    "confirmed_at": "服务端时间",
    "back_asset_id": null
  }
}
```

有真实背面图时使用 `mode=observed_reference`；尚未确认时使用 `mode=undecided`。
`USER_ASSUMED` 不是像素验证：可按确认合同生产并审核，但不得宣称已比对实物背面。
后续补背面或修改颜色必须产生新方案/生产包版本；旧任务继续使用原快照。
前端在确认处显示假设来源，不反复要求上传，不将假设隐藏为“背面已核验”。

导演台完成 Product、Character、Scene、Reality、Composition DNA 提取或设定。
每项标记 `OBSERVED`、`USER_LOCKED`、`LIBRARY_SNAPSHOT`、`PROPOSED` 或 `USER_ASSUMED`。
印花、文字、配色、版型为商品锁项；人物、动作、场景、镜头只有未被用户锁定时才可变化。
受众和购买理由属于待验证的创意假设，不作为销量或广告效果事实。
Reality 六维保持完整，允许适用项 N/A 和 imperfection=none，不使用固定百分比伪模型权重。

### 3.1 可溯源 DNA 与方向差异

每条商品结论采用 `GroundedClaim` 或等价结构，至少包含 `claim_id`、结论、`source_fact_keys`、`facts_revision`、`evidence_kind`、`confidence_basis` 和未知/假设说明；事实源定位到原素材哈希与可见区域或用户确认记录。模型自信不是证据，面料成分/舒适功效/尺寸不从图片编造。Product DNA 引用资产，不复制生成图为真值。

A/B/C 默认三方向，记录连续方向索引和 `DiversityVector = Human / Scene / Behavior / Camera / Emotion`；比较实质内容，至少两个未锁维度不同，换形容词或道具色不算。开放维度不足两个时明确差异限制，不强制解除用户锁项。当前任务最近三组可比较，历史不足如实标记；连续镜、局部修复、指定单变量测试豁免探索去重，不借多样性换脸换场。

### 3.2 背面证据与生产资格

背面证据与人工质量分轴：`OBSERVED_REFERENCE` 可对真实原图核验；`USER_ASSUMED` 只能评估是否符合已确认纯色假设；`UNDECIDED` 不允许产生/提交依赖背面细节的镜头。正面分析和正面首帧不因此被阻断。

`QUALIFIED` 不消除背面假设。图片、选择记录和视频包均保留 `back_evidence_status`、`qualification_scope`、用户确认记录与审核备注；不得将基于假设的背面标成实物保真。严格实物背面验证需真实背面图；后补图产生新版本，并重新审核受影响镜头，不能自动给旧图补证据。

## 4. 人工品牌选择与内容库

导演台提供“选择品牌”操作，打开品牌选择器；使用现有内容库，不另建站点分析系统。
用户确认的品牌优先于商品图推断、站点分析和插件内品牌猜测。
未选品牌可选择通用风格，记录 `brand_id=null`，不强行给商品归属品牌。
选定后拉取该品牌可用风格、人物/表演设定、动作、摄影语言和模板约束。

复用 `services/content_catalog.py` 的合并风格/动作库及现有模板。
库内“表演/表达风格”与具体人物图像身份分开；没有人物图时只生成文字人物设定，不虚构人物资产 ID。
不假设内容库已经存在完整 Character/Scene 资产 API：首个开发包审查真实能力，缺失项明确为用户输入或创意设定。
不可用、已退役或无权限条目不能进入新付费生产；允许查看历史快照。
动作按品牌归属、模板和实际素材能力过滤，用户锁项优先，不自动借用其他品牌私有配置。
保存条目 ID、版本（如提供）、内容哈希和实际内容快照，库更新不静默改变既有方案。
品牌或锁项改变时将当前未执行方案标为需重新确认，不自动重新生成已有图片/视频。
插件团队知识、人物资料和品牌卡不原样提交公开仓库；只吸收有权使用的规则和已确认内容。

## 5. 数据合同与状态

`CreativeTask` 是编排根，不替代 `ParentTask` 或 `ImageGenerationBatch`。

| 对象 | 必要内容 |
| --- | --- |
| CreativeTask | id、user_id、name、status、state_version、brand_id、error_code、created_at、updated_at |
| CreativeAssetLink | 所有者、创意任务、source_type/source_id、对象定位、角色、view、顺序、哈希、Canonical 标记、证据/资格/撤回/保留/物化状态 |
| CreativePlanRevision | creative_task_id、revision、facts_revision、analysis_json、directions_json、selected_direction_id、DNA/品牌/内容库/规则快照 |
| ProductionPackageRevision | plan_revision_id、revision、schema_version、ruleset_version/hash、content_hash、图/分镜/视频包和预检 |
| SelectionRecord | creative_task_id、package_revision_id、用途、shot_id、image_output_id、顺序、selected_by、created_at |
| CreativeStageAttempt（等价持久记录） | 阶段、revision、输入/输出哈希、Prompt/模型版本、授权、调用结果、费用、超时、恢复动作及错误分类 |
| RealityLoopRun / Iteration（等价持久记录） | scope、镜号、授权版本、轮次、父候选、修订包、实际 batch/item/output、缺陷证据、消耗、停止原因 |
| RealityReviewRecord（等价持久记录） | 原图/结果/参考证据哈希、shot_id、逐项结论、区域证据、建议修复、reviewer/模型/规则版本；非人工质量决定 |

选择用途分为 `FIRST_FRAME` 和 `VIDEO_STORYBOARD`，不将首帧候选与视频分镜混成一个列表。
图片/视频任务保存可空 `creative_task_id`、`production_package_id`；旧任务不强制补数据。
关联和 API 必须校验用户归属、真实输出身份、包版本和文件可访问性。

```text
DRAFT → ANALYZING → AWAITING_DIRECTION → PLAN_READY
→ IMAGE_GENERATING → IMAGE_REVIEW
→ STORYBOARD_GENERATING → STORYBOARD_REVIEW
→ VIDEO_GENERATING → VIDEO_REVIEW → COMPLETED
```

另有 `ACTION_REQUIRED`、`BLOCKED`、`CANCELLED`，记录原因与恢复阶段。
CreativeTask 是阶段汇总，不是第二套远端执行状态机。
底层未知提交、部分成功、失败、下载和账本状态仍由现有任务/attempt/batch 保持真实。
`COMPLETED` 仅在本任务要求的产物满足既有审核/交付合同后成立，不以创建视频任务或 Provider 成功判定。
状态更新使用版本校验；旧异步分析/规划结果不得覆盖新版本。

### 5.1 状态迁移与动作矩阵

| CreativeTask 状态 | 可执行动作及准入 | 下一阶段/恢复 |
| --- | --- | --- |
| `DRAFT` | 保存原图/锁项；分析授权、素材归属及版本一致后启动 | `ANALYZING` |
| `ANALYZING` | 查询、请求取消；不得并发重复分析 | 有效结果到 `AWAITING_DIRECTION`；失败到人工/阻塞态 |
| `AWAITING_DIRECTION` | 人工选方向；规划授权与版本匹配后编译；选方向不是生成授权 | 完整方案和预检落库后到 `PLAN_READY`，编译中由 stage attempt 标记 busy |
| `PLAN_READY` | 查看、确认包；授权首帧/循环范围；素材与能力预检通过后提交 | `IMAGE_GENERATING` |
| `IMAGE_GENERATING` | 查询、取消；仅运行已授权轮次的生成/复核/定向修订，不开启其他阶段 | 当前范围结束到 `IMAGE_REVIEW`；未知费用或关键冲突到人工态 |
| `IMAGE_REVIEW` | 人工逐图审核与首帧选择；确认背面策略、分镜镜号及预算；可另行授权首帧修订 | 合格已选首帧和版本化分镜包到 `STORYBOARD_GENERATING`；修订回图片生成态 |
| `STORYBOARD_GENERATING` | 查询、取消；按镜号保留成功、失败和未知项，有限循环不覆盖成功项 | 授权范围结束到 `STORYBOARD_REVIEW` |
| `STORYBOARD_REVIEW` | 人工审核、选择、排序；视频素材/数量/包校验及独立授权；可授权确定失败镜号修订 | 视频到 `VIDEO_GENERATING`；分镜修订回分镜生成态 |
| `VIDEO_GENERATING` | 查询、请求取消、已有 attempt 查询/下载恢复；禁止重规划或创建替代未知任务 | 实际视频可供审核到 `VIDEO_REVIEW`；未知结果到人工态 |
| `VIDEO_REVIEW` | 技术校验和人工最终审核；下载失败只恢复下载；重新生成需新授权 | 满足既有交付合同到 `COMPLETED` |
| `ACTION_REQUIRED` | 补素材/证据、确认方案/预算、已有任务对账；仅从记录的 resume_stage 和有效版本恢复 | 不因刷新/“继续”隐式付费；未知提交核实前只查询对账 |
| `BLOCKED` | 查看硬阻塞、修复权限/能力/结构冲突或取消 | 依赖满足并重新预检才回 resume_stage；不能绕过门禁 |
| `CANCELLED` | 查询历史；停止新调用，已提交 attempt 继续查询/结算 | 不复用取消授权；恢复生产需新命令/授权 |
| `COMPLETED` | 查看/交付；如需新创作派生新 revision 和生产范围 | 不把旧任务回退或自动重新执行 |

输入改变使未执行的方向/包标记 stale，回到分析/选择/编译相应阶段；生成中请求修订不覆盖在途快照，需停止新轮次后确认新 revision。所有生成态进入前均检查 `expected_state_version`；批次 busy、stage busy、未知费用未清理时拒绝新执行命令。

CreativeTask 只汇总编排，ParentTask/图片批次负责媒体执行，attempt 负责实际调用，账本/配额负责费用，输出人工审核负责资格。编排汇总失联时从持久关联重建，不从 UI 状态推断 Provider 已失败。

分析/规划 attempt 带 `task_id + revision + attempt_id + facts_revision`，持久化期限/worker lease 和输入快照；超时先核对实际调用，明确可重试且预算允许才继续。错误按 `RETRYABLE / HUMAN_REQUIRED / FATAL` 记录 `next_action`，失败半成品不得激活为有效 DNA/生产包。

## 6. Production Package 与 Prompt 所有权

生产包包含 `image_package`、`storyboard_package`、`video_package`。
每个 Shot 至少含 shot_id、顺序、purpose、时间区间、scene、action、camera、起止状态、商品锁项及完整 image_prompt/video_prompt。
存储真实层规则、人物/场景设定、参考图策略、连续性约束、背面策略和验证规则。
首帧与各镜图片 Prompt 在导演阶段编译完成，不在提交图片或视频时再次调用模型重写。
自主循环修订也必须先进入导演编译阶段，追加不可变包版本，再提交新候选；不是执行接口现场改 Prompt。详见第 12 节。

编译分为两步：

1. 导演编译：生成并锁定创意内容、每镜 Prompt、脚本及参考角色。
2. 执行绑定：将真实合格素材映射到 Provider 参考编号，做格式/能力/长度预检。

执行绑定不得替换台词、动作、镜头或加入自动学习指导。
包快照保留 `planned_prompt`；生产任务保留 `submitted_prompt`、绑定清单和两者哈希。
参考编号、服务必需角色说明等有界差异可见并可验证，不冒称二者逐字相同。
超出限制必须在付费前阻断，不截断商品文字或静默重写；用户在导演台修订后生成新包版本。
选方向和编译均不触发媒体生成；改变已确认方案不会修改已提交任务的 Prompt。

### 6.1 Prompt Registry 与 Preservation

采用统一版本索引，允许“经版本化的模板文件 + 持久化引用/哈希”实现，首版不建设独立 Prompt 管理平台。分析、方向、DNA、真实性批评器、Image/Video 编译模板都保存 `prompt_key/version`、正文哈希、规则 manifest 版本、输入 schema、模型版本和激活状态；新版本追加，正文不可原地修改。已提交任务和恢复继续引用原版本。

完整 DNA 在内部存储，实际 Image Prompt 使用插件四段逻辑：商品/硬锁 → 单个被拍瞬间与人物依据 → 机位/空间/焦点 → 现场光/接触/衣料受力。中文约 200–400 字只是软预算，复杂商品可更长，不能删印花原文和锁项。禁止全量规则灌入、随机词堆叠、噪点/失焦遮错。

`required_contract` 对照最终拟提交 Prompt 检查 Product/user locks、capture_geometry、focus_depth_response、local_light_contact、garment_force_projection、character_basis、reference_handoff。执行绑定后再核一次，缺失/冲突付费前修订或阻断。保留拟稿、实际 Adapter 提交内容及哈希，不能把可见请求体冒称 Provider 隐藏有效指令。

### 6.2 Shot 与分镜/对白交接

`shot_id` 必须有可查询的一等持久字段或强约束映射，关联包版本、item、output 和 SelectionRecord，不能只塞在 request_json。输出顺序不等于镜号；多候选、部分失败、修订和排序后仍可定位原镜。校验真实 output 属于对应镜号/包/用户，重排不改镜号，删镜/增镜派生新包。

逐镜 Composition DNA 保存 frame_type、裁切/占比、摄影者、前中后景尺度/遮挡、2–3 个空间锚点、焦点/光、起止状态和允许变化。身份固定不等于表情冻结；连续镜不为去重换场。图 Prompt 描写静态时点，视频 Prompt 描写 `Initial → Movement → Camera → Ending`，镜数服从目标时长而非默认四镜。

有对白才保存 speaker/listener、锁定原文、`shot_window` 与 `speech_window`、语速估计、静默动作及口型归属。可采用插件约 155–180 WPM 的成人英语自然对白规划目标，非引擎保证；容不下原文/动作则提示冲突，不拉慢填满整镜或擅改锁定台词。画外音不得让画内人物同步口型，未看真实视频/听音频不得标口型/语速通过。

恢复包可复制/导出任务版本、锁项、镜号、资产来源/资格、参考证据、实际完成项和下一动作；文本恢复不代表媒体已物化或 Provider 已接收。对象存储可访问时直接复用，缺失时只请求必要补充，导出不隐式生成广告文案或媒体。

## 7. 现有生图引擎与分镜适配

现有批次 `fusion/storyboard` 要求 `model.front + product.front`，不能直接满足“只有商品图”的导演入口。
新增受合同校验的导演输入适配/模式，复用既有批次持久化、配额、提交、轮询、下载和审核。
不删除或放宽旧模式所需角色，不把商品图充当 `model.front`。
导演首帧允许商品参考与文字人物/场景设定；可选人物来源必须是用户允许使用的真实素材。
分镜使用原始商品图和已合格、已选首帧建立连续性；每镜执行该镜已锁定 Prompt。
缺背面走第 3 节策略，不复用旧模式的自由背面推测；旧自定义生图默认值不变。
不把合格首帧升级为商品真值，不将第三方场景服装/人脸当商品或人物身份。
当前 API 的参考角色与文件数量不满足时应明确失败或回导演台修订，不能伪装适配成功。

生成首帧和分镜分别授权数量/镜号。没有授权不批量生成，不为填齐素材额外产生付费调用。
分镜适配器只组织既有 Image Generation 请求，不另建 Provider 或媒体执行队列。
返回真实 batch/item/output ID 与 shot_id 映射，部分失败逐镜保留。
必须通过现有人工质量决策得到 `QUALIFIED`，选择操作不能自动审核。

## 8. 视频两种模式与素材复用

### 自定义生成

只作为生视频工具，允许编辑 Prompt、素材、顺序及现有 Provider 支持的参数。
不要求先创建 CreativeTask，不偷偷规划或使用自动学习指导。
允许从导演任务带入初始素材和 Prompt 后切换自定义；编辑后的请求保存独立快照，不篡改原包。
如果仍关联导演任务，记录 `execution_mode=custom_override` 和偏离来源。

### 自动生成（导演任务）

接收 CreativeTask、已确认生产包版本和已审核分镜选择；使用显式 `execution_mode=director_fixed` 或等价新命令分支，不在视频页自动生成 Prompt。
导演台分配的是可确认的视频生产请求，不是上传或选图后立即后台扣费。
复用现有 Fixed Video Workflow，以 `ParentTask + workflow_kind=FIXED_TEMPLATE` 承载。
不会触发原 `compile_video_plan` 的重新规划、动作随机选择或已有反馈学习。
原自动模式历史任务仍按保存的 attempt/provider/Prompt 恢复和查询，不套新合同，不自动重提。
旧客户端/API 行为采用显式兼容策略；新 UI 的自动入口不能静默回退旧站点自动规划。
实现可采用新执行标记区分导演来源，不通过改旧枚举含义来破坏历史请求。

### 产品图和合格分镜自动拉取

服务端通过真实资产 ID、对象存储键和校验和读取已有原图及合格分镜，用户不重复上传。
首帧和最终分镜选择分开，视频采用已审核的最终分镜顺序；选中的首帧只有成为一个合格 Shot 时才加入。
原始正面/真实背面是 PRODUCT 参考，分镜是 STORYBOARD；无真实背面时不虚构背面资产。
自动绑定产品参考，不将仅有的商品图错误指定为某个真实人物身份图。
不要求服务端完全停止向 Provider 上传：Provider 必需的媒体物化/上传仍由已有 Adapter 执行。
遵守实际 Provider 能力和现有视频参考总数上限，原图与分镜均计入，必要时在提交前要求缩减镜数。

素材持久化不能仅依赖浏览器 File/IndexedDB 或一次性、会被领取的 StagedUpload。
复用对象存储与来源机制，创意任务须保有可重用的素材引用和明确保留策略。
兼容桥接需要 StagedUpload 时生成任务专属引用，不抢占或重置其他任务已领取的上传。
生成图片来源与哈希不得在转视频时丢失；每次提交重新检查所有者、文件存在和 `QUALIFIED`。
审核已撤回或素材已失效时阻断新的提交，不影响已提交任务按原快照恢复。
对象缺失提示恢复或补充，不把一切失败都转成要求重新上传。

## 9. API、幂等与付费边界

全部路由保持 `/api/v1` 前缀，下列为待实现合同，不代表接口已存在：

```text
POST /director/tasks
GET  /director/tasks
GET  /director/tasks/{id}
PUT  /director/tasks/{id}/inputs
POST /director/tasks/{id}/analyze
PUT  /director/tasks/{id}/direction
POST /director/tasks/{id}/compile
PUT  /director/tasks/{id}/selections
```

inputs 保存手选品牌、原图、背面假设和用户锁项；selections 保存用途、shot_id 和顺序。
导演服务封装首帧/分镜批次创建和视频创建请求，调用共享服务，禁止内部 HTTP 绕过权限或复制一套扣费流程。
将会跨进程执行的持久化请求身份、包版本、授权范围和子任务关联在 Provider 调用前固化。
生成入口具体采用既有批次/视频 API 扩展或薄导演命令路由，在首个代码包中冻结并导出 OpenAPI。
两种入口必须共享同一服务级权限、配额、授权和幂等合同，不能只在 UI 或旧路由实现门禁。

所有写入遵循现有认证/CSRF、归属和必要的 expected_state_version。
生成请求使用 Idempotency-Key，并将包哈希、素材哈希/顺序、镜号、数量、背面策略和执行模式计入请求指纹。
同键重放返回已有子任务；同键变更返回冲突，不重新上传/提交/消耗生成预算。
子任务创建与导演关联必须可恢复，不能发生“生产已经提交但导演找不到任务”后再次提交。
UNKNOWN/WRITE_UNCERTAIN 不创建替代付费任务，不自动换 Provider、退款或释放不确定费用。
部分成功保留成功结果；只对明确可再生成项使用新的授权，或在尚有效的循环授权范围内追加新迭代；新包版本、新候选有独立幂等身份，原成功项不随整批再次执行。
分析与规划使用结构化 schema、有限调用与超时；崩溃恢复不自动形成无限付费重试。

分析/规划/像素复核均保存模型及版本、Prompt 引用、`facts_revision`、`max_calls`、`timeout_ms`、任务总预算、阶段预算、币种/计量单位、`authorization_id/version`、授权时间/有效期、billable 和幂等身份。媒体预算与文字/VLM 预算分别限额，共同计入任务总上限；未确认计价或余额不足时不启动自主循环。

并发 worker 在实际提交前原子领取阶段 lease/迭代身份并预占调用次数和预算，完成后按既有账本结算。评估、生成、技术重试都占相应总调用额度；未知费用仍占预算，授权失效/用户停止后不再新提交。重启恢复已有调用不额外占一轮，模型调用成功但落库未知先对账，不重跑。预算只是授权上限，不与现有扣费/配额机制重复扣减。

除已有路由外需提供编排 attempt/循环记录查询、授权、停止和受控恢复命令（具体命名 CW-0.5 冻结）；停止只阻止新轮次，不承诺取消已接收远端任务，也不自动退款。所有入口共享现有认证/CSRF/归属/幂等服务门禁。

## 10. 修改文件与数据库迁移方案

以下是未来代码开发清单，本轮只修订文档：

| 文件/目录 | 改动 |
| --- | --- |
| backend/src/libtv_agent/domain/models.py | 编排模型、素材/事实/版本/选择、attempt/循环/复核记录、可空关联和约束 |
| backend/src/libtv_agent/domain/enums.py、schemas.py、director_contracts.py | 导演状态、请求/读取、生产包与来源合同 |
| backend/src/libtv_agent/services/director/ | analyzer、creative_planner、production_compiler、storyboard_generator、asset_binding、reality_critic、bounded_loop、workflow |
| backend/src/libtv_agent/api/director.py、router.py | 创意任务 API、归属与写入边界 |
| backend/src/libtv_agent/api/image_generations.py、services/image_generations.py | 导演输入适配，保留旧模式及共享安全门禁 |
| backend/src/libtv_agent/api/video_tasks.py、services/fixed_video_tasks.py | 导演执行绑定与两种模式的兼容路径 |
| backend/src/libtv_agent/services/content_catalog.py | 只读复用内容库和版本快照，不重建目录系统 |
| backend/src/libtv_agent/api/uploads.py、services/preprocessing.py | 仅必要时提取共享物化校验，保留来源审核/哈希 |
| backend/src/libtv_agent/services/prompt_compiler.py | 必要的执行校验复用，不让导演路径再次自动规划 |
| backend/src/libtv_agent/templates/director_rulesets/ | 经归一化和许可审查的规则 manifest、模块顺序、Prompt Registry 版本引用与哈希 |
| backend/alembic/versions/ | 增量迁移，适配两侧实际迁移图 |
| frontend/src/features/director/、features/image-center/、features/production/ | 导演模式、手选品牌、分镜审核、视频两种模式 |
| frontend/src/api.ts、types.ts、app/、domain/ | 类型、兼容导航、状态展示和服务端素材引用 |
| backend/tests/、frontend/src/、scripts/ | 合同、迁移、回归和隔离浏览器验收 |
| openapi.yaml、docs/ | 合同导出、变更与逐包 Sprint 报告 |

增量建立新表，给已有任务加可空关联；不为旧任务伪造 CreativeTask，不删除现有列。
版本表采用 task/revision 唯一约束，选择记录采用阶段/镜号/顺序约束，增加用户/任务查询索引。
迁移前核对 testing 和实际 main 的 Alembic heads，不根据另一个 Git 目录的 main 引用猜生产基线。
在隔离 SQLite/PostgreSQL 验证已有数据升级、外键/唯一约束和回滚边界；含新增数据的 downgrade 不承诺无损。
不在 API 启动时自动迁移生产数据库，推广迁移源码不等于执行迁移。

## 11. 分包开发、验收与停止规则

1. CW-0.5：完成 CW-P01 至 CW-P08 立项前置项，冻结合同/规则/预算/质量指标及独立真实验证计划。
2. CW-1：模型、持久素材/品牌/Grounded DNA/shot_id 合同、状态/attempt/循环授权、迁移和无真实 Provider 的 API 验证。
3. CW-2：按模块分析、A/B/C 差异、方向选择、内容库快照、Prompt Registry/Preservation、生产包编译和版本失效。
4. CW-3：单正面首帧、真实性批评器、有界循环、人工审核、背面确认、逐镜生成/选择与部分失败恢复；真实质量验证另行授权。
5. CW-4：director_fixed 两种视频模式、服务端素材复用、导演子任务绑定和历史任务兼容/隔离证明。
6. CW-5：人工 Checkpoint 1 接受后的导演前端、四视口浏览器回归及集成验收。

每包先审查实际源码并报告文件、迁移/API变化，再实现；不一次并行改完所有工作区。
每包 testing 验证后局部推广到实际 main，保留两侧原有差异和用户未提交修改。
每轮记录完成、修改、测试、发现问题、下一步；修复后重跑受影响测试。

| ID | 必须覆盖的验收 |
| --- | --- |
| CW-A01 | 只有商品正面可分析；背面不可访问标未知，受众和购买理由标假设 |
| CW-A02 | 人工品牌选择优先于模型猜测；通用模式不伪造品牌 |
| CW-A03 | 内容库真实条目/版本/哈希快照；无权限、退役条目与缺失人物资产正确处理 |
| CW-A04 | 没有背面提示上传或确认无印花纯色；底色不明需确认，不镜像正面印花 |
| CW-A05 | 后补真实背面、改品牌/锁项产生新包；旧任务快照不变 |
| CW-A06 | 商品单图首帧不伪造 model.front；旧融合/分镜角色校验与默认值不变 |
| CW-A07 | 第一帧/逐镜 Prompt 保真；执行绑定不重写内容、不注入自动学习、超长付费前拒绝 |
| CW-A08 | 首帧和分镜选择独立；未 QUALIFIED、审核撤回、哈希不符或越权不得创建视频 |
| CW-A09 | 自动模式拉取原商品与合格分镜，无重复用户上传；参考数量/角色/顺序正确 |
| CW-A10 | 自定义可编辑 Prompt，无隐式规划；切换模式不篡改原生产包 |
| CW-A11 | 刷新、双击、同键重放、进程中断和导演关联恢复均不重复提交/计预算 |
| CW-A12 | 部分分镜失败只处理授权失败项；UNKNOWN 保持对账，不重提成功或不确定项 |
| CW-A13 | 库更新/方案过期/素材失效可解释；可用素材不被一次性上传领取导致重复索要 |
| CW-A14 | 保留图片审核、视频最终审核、历史 Provider 查询/下载/恢复和任务中心 |
| CW-A15 | 两侧隔离迁移与回归、前端 build/lint/unit、1440/1024/768/390 浏览器交互 |
| CW-A16 | CW-P01 至 CW-P08 有证据和明确待办；没有用任务书存在、旧测试 PASS 代替立项评审 |
| CW-A17 | Product→方向候选→选定 DNA/六维 Reality→文字包→授权→绑定/生成/复核顺序可审计，缺前置不越级 |
| CW-A18 | 循环默认关闭；启用明确确认默认一次修订、每初稿硬上限两次；预算/过期/停止/无进步/未知费用到限停止且多 worker 不重复调用 |
| CW-A19 | 六维含具体本镜决定/N/A 原因，imperfection 可 none；商品硬锁优先，去 AI 味不靠伤图案、污渍或换脸 |
| CW-A20 | 参考 retrieved/displayed/materialized/submitted/accepted 分轴，高风险服装/陌生脸默认 DNA_only，不从输出相似度推断视觉已输入 |
| CW-A21 | Product/人拍/人衣景/卖点和 UGC authenticity/framing 各自 pass/fail/unverified，未知不冒充全项通过，模型复核不写 QUALIFIED |
| CW-A22 | 循环修订追加不可变包和幂等身份，锁项/权限未变才在授权内继续；失败候选不成为 Product/连续性母图 |
| CW-A23 | director_fixed 以 spy/断言证明 compile_video_plan/apply_video_learning 未调用；旧 automatic/custom、重启恢复回归保持 |
| CW-A24 | 源素材哈希、保留/撤回与一次性上传桥接、shot_id→item/output→selection 映射在排序/多候选/部分失败后不丢失 |
| CW-A25 | GroundedClaim 的来源/事实版本/置信依据可校验；方向至少两项实质差异，连续镜/单变量例外不破坏锁项 |
| CW-A26 | Prompt Registry 旧版本不可原地修改；编译和绑定后 Preservation 全检，actual submitted 与 Provider 接收证据分别报告 |
| CW-A27 | 分析/规划/复核付费、阶段总预算、attempt 超时/过期结果、错误分类和 UNKNOWN 对账均有隔离崩溃/重放验证 |
| CW-A28 | 背面假设与资格分轴；UNDECIDED 不生成背面，USER_ASSUMED 可按确认合同生产但不能声称实物核验 |
| CW-A29 | 逐镜构图/起止态/人景连续性、对白 shot_window/speech_window/说话者归属和文本恢复与实际媒体证据分离 |
| CW-A30 | 静态规则/运行输入/像素复核/质量对照四级证据分开；成本、合格率、缺陷率、人工耗时及循环次数/停止原因按预设口径记录 |

先用隔离 Fake/Replay 完成端到端工程验证，不把它称为真实图片质量或生产准备完成。
真实单件服装验证另行限定模型、素材、调用数、预算与停止条件，覆盖正反面和单正面两条路径。
本版本不做多 Agent、ROI 学习、跨任务复杂 Memory、广告数据接入或独立自动评分模型。允许任务内有界真实性修订循环，不做无限自动 Prompt 优化或跨任务自学习；循环及模型复核不能代替人工审核。

## 12. 插件优势吸收与真实性循环合同

### 12.1 参考基线与取舍

本轮实际审查用户提供的 `F:/Users/Reel/Downloads/plugin (2).zip`，manifest 为 `ai-fashion-creative-director v1.13.5`，SHA-256 为 `CE3BAC935CAE0C45479AFA68E948004BC9C08B4B862A7C74EC4959F122828F67`。压缩包是规则/Skill 集合，不是可直接部署的服务端 Agent 引擎；后续实现按下表归一化，不原样复制全包或私人团队资料。

| 来源优势 | 本项目吸收方式 | 不照搬/不宣称 |
| --- | --- | --- |
| 衣影工坊批次/配额/幂等/未知提交 | 导演命令调用既有共享服务；循环每候选真实 item/attempt，可恢复部分失败 | 不另建媒体 Provider/扣费队列，不重提未知项 |
| 衣影工坊对象存储/源图哈希/审核/固定视频 | 持久素材和来源链、QUALIFIED 人工门、director_fixed 执行、历史快照恢复 | 选择/AI 评审不能自动合格，推广不是部署 |
| 插件 23/24 号门 | Canonical 商品/手选品牌优先；A/B/C→人工选择→完整文字包→独立生成授权 | 不将上传、选方向或“继续”解释为生成许可 |
| 插件 27 > 26 摄影优先级 | P0 商品/用户锁 > P1 六维物理约束 > P2 可信参考事实 > P3 推断；六维常开 | 旧 60/40、100/0 权重叙述失效，不声称模型内部可控权重 |
| 01/08/10、Human Lite | 溯源商品/品牌事实、五维差异、身份与行为分开；新人物两项协调结构特征 | 不锁陌生参考脸，不为独特强制畸形，不把受众当出镜人 |
| 02、Photo Style、Scene 微补丁 | 六维具体摄影世界、布料受力/印花曲面、单个可拍状态、有限微变量 | 不默认所有图暗黑/镜自拍/抓拍，不靠噪点毛孔证明真实 |
| Reference Layer、15、24/26/27 | 方向旁真实参考/明确缺失，防第三方串衣、证据分轴和 DNA_only 降级 | 展示/下载不等于模型接收；不为图库填空自动生成照片 |
| 04、Compact Compiler、Preservation | 内部充分、最终紧凑；拟稿及绑定后校验锁项和摄影因果 | 不把大包全文灌入、不静默截断、不声称文本合规等于实图改善 |
| 07/18、26/27 Critic | 实际像素独立四维 + UGC/景别，区域证据与定点修复建议 | 不输出伪百分制，不把未核验判 pass，不自动人工审核 |
| 12/19/21、25 分镜对白 | 商品/身份/场景/光/起止态连续性，镜号、构图、对白归属、可恢复文本包 | 文字/示意布局不代表真实分镜，口型/语速不由 Prompt 保证 |
| 11/13/16/17/20/22 恢复/交付 | 本项目持久版本、真实子任务和阶段权限；必要时导出自包含恢复摘要 | 克服插件会话持久化/工具结束限制，但不自动渲染额外视频/文案 |
| 插件保守定点修复 | 升级为服务端有界循环，固定模块顺序、逐轮证据/预算/停止/恢复 | 插件“不后台自主/最多一次”不是项目架构限制；项目上限独立冻结 |

规则加载解释顺序固定为 27（覆盖旧比例）→ 26（运行证据）→ 24（商品/品牌/参考门）→ 23（先方案）→ 其余模块；模块编号不是执行阶段序号。规则 manifest 引用文件、来源版本、SHA-256、覆盖关系和模块 schema，不保留互相冲突的旧解释。

### 12.2 固定阶段与模块执行顺序

本项目沿用插件 v1.13.5 先方案后生成，而不是按旧 STATE 0–7 编号机械地先图后分镜。每阶段有结构化 I/O、来源/版本/哈希、适用性和门检结果：

| 顺序 | 阶段/模块 | 产物和准入 |
| --- | --- | --- |
| G0 | 加载规则优先级；Product/品牌/锁项、素材角色、权限门 | 正确原图、已确认品牌/通用、用户硬锁与参考来源边界 |
| D1 | Product Fact → Brand/Product DNA | 溯源事实、未知/假设、锁项、facts_revision；不补造背面 |
| D2 | A/B/C 探索：候选 Character/Scene → Reality 六维 → 可用参考发现/展示/提取 → 物理冲突/差异校验 | proposed 候选、五维差异、参考 Gallery 状态；只推荐不替人选择 |
| D3 | 人工选方向 → Product/Character/Scene 锁 → 本镜 Reality 六维 → Photo/Human Lite 可迁移参考事实/安全门 → 全局冲突裁决 | 新人物选角/已锁身份分开，具体摄影世界、场景锚点及安全证据路线 |
| D4 | 脚本 → Composition/Storyboard Continuity/对白时序 → Compact Image/Video Prompt → Preservation → Production Package | 完整文本方案在任何媒体调用前保存；文字分镜不是生成图 |
| H1 | 用户确认包、生成范围和是否授权真实性循环 | 初稿数量、镜号、修订允许范围、最大调用/预算/有效期；未授权停止 |
| E1 | 资产权限/资格/哈希复检 → Provider 能力/参考绑定 → Preservation/预算/幂等预检 | 明确 actual submitted；不改锁定内容、不新规划 |
| E2 | 既有图片服务实际生成/轮询/下载 → 技术校验 | 真实 batch/item/output/attempt；未知提交只对账，下载失败只恢复下载 |
| E3 | 输出像素 Critic → 定向修订决策或停止 → 人工审核/选择 | 可见原商品+实际候选+本镜合同；AI 结论非 QUALIFIED |
| R1 | 已授权修订回到失败涉及的 D3/D4 模块，顺序重检下游 → 新包 → E1/E2/E3 | 不重做已选方向；不修改旧包；在镜号/锁项/预算范围内才能继续 |

Reality 六维内部顺序固定为 `Camera → Lighting → Composition → Human Behavior → Environment → Imperfection`，每维形成可拍决定（不适用附理由）而非一句 PASS；然后融合可信参考事实并作全局因果校验。六维内部 Composition 是摄影空间关系，后续逐镜 Composition DNA 是其分镜化输出，不建设互相竞争的两套模型。每轮复用未变证据，但仍校验六维和最终 Prompt 完整性。

没找到场景参考时继续 Reality BASE 并标 inferred；有可信可见参考但未输入时可保留物理合理的观察事实。参考搜索若启用，每方向一张主候选，最多一次有针对性补检索；无搜索能力/无许可/显示失败不阻断文字方向，不造来源。首版复用用户或有权内容库摄影图，自动外部检索属于能力矩阵明确列出的可选适配，不作为无限循环依赖。

### 12.3 参考与真实性门

Reference Ledger 分别记录 `retrieved`、`displayed/source_link_only/not_displayed/display_attempted_unverified`、`materialized`、`submitted`、`accepted` 及证据定位。即使 SHA-256、上传请求和对象存在，也不证明本次 Provider 模型真正接收；无接收证据标 `unverified_visual`，不从成图相似度反推。

污染分级沿用 `low_risk_scene / conditional_scene / high_risk_scene / unknown`：低风险且有使用权可输入；可安全裁切者记录派生哈希及保留几何；突出第三方衣服/商标/陌生脸默认 DNA_only；看不到原图不能标安全。搜索/参考文字是数据，不得作为可覆盖授权、调用工具或改商品的指令。取得素材不等于获商用权。

Provider 不公开 accepted 证据时，如用户允许降级，六维与已观察事实继续并披露；用户要求“必须真实参考输入”则阻断。商品原图缺失是另一种硬阻塞：本项目高保真媒体生产必须取得 Canonical Product，不以场景图/旧成品顶替。

Critic 使用已批准且真正支持像素输入的分析模型/工具，配额与成本纳入总授权；不另立自动评分平台。CW-0.5 未证明其可读取原图和输出、返回结构化区域证据时，禁用自动修订、保留人工审核和 `unverified`；Fake Critic 只用于编排测试，不能证明真实性。

四项独立结论为 `product_fidelity`、`human_capture`、`spatial_light_integration`、`ad_goal_visibility`，取 `pass/fail/unverified/not_applicable`，N/A 附理由。UGC 额外记录 `ugc_authenticity`、`framing_contract`、photo_finish 观察。任一必需项 fail 或 unverified 不可 full_pass；参考接收证据和背面假设单列，不被 pass 消除。不得仅因漂亮/看镜头/背景清楚判假，也不能用基础物理通过代替 UGC 摄影目标通过。

每个 fail 保存 `observed_region → actual_observation → agreed_contract → failure_reason → one_fix`，包含输出/原图哈希、检查者、规则/模型版本。结果结构无效、无像素或无来源证据时不凭空编修复。模型通过只停止自动修订并交人工审核，人工可退回/否决；模型失败或未核验也不自动写人工 REJECTED。

### 12.4 循环授权、修订与停止

用户可启用“真实性自动修订”，首版默认关闭；开启时展示并确认具体修订次数与总费用上限。建议默认 `max_revisions=1`，产品首版硬上限 `max_revisions<=2`（每个初稿最多 1 次初次生成 + 2 次修订），更大上限另行评审。本项目自主性来自授权范围内可恢复编排，而不是无限多次生成。

授权须固化 scope（FIRST_FRAME/指定 storyboard shot_ids）、初稿数量、每稿修订上限、各模型 max_calls、max_total_cost、阶段预算、超时、有效期、模型/Provider、锁项哈希、允许改动模块及 `allow_reference_fallback`。多个镜头共享任务总预算，不把单镜上限逐镜叠加成不限费用。每次修订仍需满足阶段权限，但可复用这份明确包含修订额度的授权，不要求每轮重复点击。

修订是新候选，不是网络重试：生成 `loop_id + candidate_id + revision_index` 的幂等身份，保存父候选、失败证据、因果假设、改动模块、差异、Prompt/包版本、输入/输出哈希、实际调用 ID、消耗和停止原因。模型自报“更真实”不足以继续；优先只改一个最重要未锁因果变量，综合修复要标多变量，不宣称单变量增益。

商品文字/印花/版型错误回到原商品校准和参考污染门，不改商品事实；空间/曝光/贴图问题只修 Scene/Reality；身份已锁不得为去模板换脸。改变品牌/身份/场景硬锁、背面假设、对白或镜头目标须暂停交人确认，并使旧循环授权失效。修订包只在原允许差异范围内派生和再次预检；第 6 节的执行绑定仍禁止重写。

修订后技术/像素全项复核，既有通过项出现回归需记录；不能只检查修复的单项。每轮保留全部候选，不能自动撤回旧人工合格结果、覆盖选择记录，或将待修/商品错误首帧当下一镜视觉母图。只对人审合格并选中的首帧/Shot 建立连续性来源。

停止原因至少包含 `QUALITY_TARGET_MET`、`LIMIT_REACHED`、`BUDGET_EXHAUSTED`、`AUTH_EXPIRED`、`USER_STOPPED`、`NO_PROGRESS`、`LOCK_CONFLICT`、`UNVERIFIED_PIXELS`、`EXECUTION_UNKNOWN`、`DEPENDENCY_BLOCKED`。目标达成转人审；达到预算/次数或用户停止保留候选进入人审/待决定；同一核心缺陷连续两次未改善、存在用户锁冲突或无法实际复核转 ACTION_REQUIRED；权限/必需能力缺失转 BLOCKED。

`UNKNOWN/WRITE_UNCERTAIN` 不启动修订或替代生成；先按现有 attempt 处理查询/对账。循环中断恢复只能读取已有 iteration/子任务与授权，不从头跑；停止/授权过期在每次新调用前检查，已提交远端任务继续结算/查询，不承诺退款。服务端队列只编排模块，不取代既有媒体执行/账本真源。

## 13. 收益指标与投入开发判断

CW-P08 评审时填写基线、目标阈值、样本/分母、责任人和测量窗口；未填写不能判立项门通过。指标包括首个合格首帧耗时（分析授权至人审合格，另列模型等待与人工耗时）、重复上传次数/可复用素材数、重复提交/唯一逻辑命令数、合格已选分镜/目标镜号数、每任务人工操作分钟数、任务总实际/未知预占成本、真实性 fail/已复核候选数、unverified 比例、平均修订次数及停止原因、UNKNOWN 任务比例。

初稿合格率与循环后最终合格率分开，修订候选均计成本；被取消/失败/未交付任务不从成本和失败分母中静默删除。真实性问题按商品、人物、空间光、UGC、景别分别计数，并将背面假设从“实物已核验”样本中分离。

真实小样本比较同 SKU、方向、锁项、模型/参数/参考路径下的旧流程与新流程；一个 SKU 只证明该样本可行，不推断所有款型显著提升。建议再覆盖文字印花复杂款、纯色款、真实背面和单正面假设路径；规模和预算由人确认。无法控制 seed/多变量时记录混杂因素，不保证因果效果。

结论分级：

1. 本轮补齐任务书后，可启动 CW-0.5 调研/合同验证；不代表前置项通过。
2. CW-P01 至 CW-P08 通过后，可按 CW-1 至 CW-4 分包隔离开发；CW-5 仍等 Checkpoint 1。
3. Fake/Replay、迁移/兼容和真实授权样本达预设质量/成本目标后，才可提交人工上线评审。
4. Checkpoint 2、付费生产、数据库迁移、部署/重启仍需各自明确批准；源码推广不能代替。
