# Creative Workflow CW-0.5 前置评审包

日期：2026-10-10
状态：前置工程证据已交付；用户随后授权隔离 CW-1 首包，真实验证/上线仍待评审
范围：合同、Fake 模拟、已有能力回归和临时 SQLite 迁移；不是导演功能实现或生产验收

## 1. 结论与待决项

本报告记录前置调查时点。用户随后于 2026-10-10 接受整体骨架和单正面 Fake 闭环，批准把前置门分为隔离开发/真实验证/上线，因此可以开始隔离 CW-1。下表及 D01-D06 为原调查待决证据，不再作为一刀切的代码开发阻塞；真实素材、价格/预算、Critic 和质量收益仍须在相应真实验证前核实。首包结果见 `SPRINT_REPORT_CREATIVE_WORKFLOW_CW1_20261010.md`，不追认真实能力。

| 前置项 | 已交付 | 未通过原因 |
| --- | --- | --- |
| CW-P01 | 两侧源码/测试能力矩阵、Provider 输入限制 | 待工程评审确认；真实 Provider 能力/当前价格未验证 |
| CW-P02 | Product 接入决策、持久素材/撤回/保留/shot_id 合同 | D01 对齐方案待接受；对象/审核/许可证据接口仍待 CW-1 实现 |
| CW-P03 | 任务书 5.1 状态动作矩阵、下述 attempt/版本/恢复边界 | 设计待评审；Fake 不证明数据库并发和崩溃安全 |
| CW-P04 | 总任务预算、阶段/模型调用限额、授权及循环预占合同 | D02 金额、币种、报价、有效期由产品确认；真实调用额度为零 |
| CW-P05 | DNA/方向/Prompt 真源、13 份关键规则来源哈希、模块顺序 | 设计待评审；现有分析 schema 不能直接作为导演/Critic schema |
| CW-P06 | 许可台账和能力降级表 | D03 未提供有权真实 SKU/品牌/人物/摄影参考及保留期限 |
| CW-P07 | 两侧迁移图、空库 SQLite 升级、旧工作流选集回归、隔离计划 | 生产 Product 未回移；PostgreSQL/带数据升级及 director_fixed spy 待验证 |
| CW-P08 | 指标口径、候选阈值、分层采样和 CW-1 测试计划 | D04 质量/收益目标、样本、负责人和预算未确认；尚无真实对照数据 |

待决编号以 `docs/contracts/creative-workflow-preflight.v1.json` 为机器可读清单：

- D01（工程）：接受窄范围回移生产 Product 基础及迁移合并图，不新增第二套商品模型。
- D02（产品）：确认各阶段模型/Provider、报价证据、币种、单任务及阶段费用上限、授权有效期。文档中的调用数/超时只是设计候选。
- D03（素材负责人）：确认原商品、品牌卡、人物身份/肖像、摄影参考的使用范围、证明位置、撤回机制和保留期限。收到插件 ZIP 不等于获得所有第三方资料使用权。
- D04（产品）：接受或调整第 8 节的候选目标与采样方案，提供至少一个可使用的 SKU/历史失败基线。没有历史基线时另行批准采样。
- D05（工程）：像素 Critic 输入与区域证据合同须经隔离适配验证；真实支持仍需批准后核验，未证实时自动修订不可启用。
- D06（工程）：补齐带数据升级、隔离 PostgreSQL、旧模式完整回归与恢复计划。已有内容库错误断言已修正，不将该修复当成导演路径隔离证明。

## 2. 两侧源码基线

| 项 | testing | 实际 main |
| --- | --- | --- |
| 目录 | `E:/Projects/libtv自动化生成` | `C:/Users/Reel/Documents/libtv-auto-main-sync` |
| 分支 | `codex/testing` | `main` |
| 入场 HEAD | `a9db2d6daf215f919b64af36f38855ad5aa638e1` | `4cc509f90dadee9ad57142d60318d105bf1b9e2b` |
| Alembic 文件数 / head | 25 / `c8d4e6f1a203` | 27 / `c9f0a1b2c304` |
| 入场工作区 | 已有 UI、规范文档、原型及用户 ZIP 改动 | 已有 UI、规范文档与原型改动 |

main 有额外商品迁移 `c8e4f1a2b907`（父 `b7d9e1f3a502`），通过 `c9f0a1b2c304` 合并商品和配额 heads。不能在 testing 的旧 head 上新增 Creative 迁移后直接复制到 main。AST 图检查不导入 `alembic/env.py`；实际升级只在仓库外空白目录运行，显式临时 SQLite URL，不读真实 `.env`。

两侧临时空库全链 `upgrade head` 均通过。25 份公共迁移规范化行尾后内容一致，其中 4 份仅 LF/CRLF 导致原始 SHA 不同，未改写它们。此结果不证明 PostgreSQL、存量数据迁移、生产 schema 或无损 downgrade 已通过。迁移及源文件哈希可由检查器重新输出；任何基线漂移均需重审。

## 3. 能力矩阵

`EXISTS` 指代码及相关隔离证据存在，不是线上能力验收；`ADAPTER_REQUIRED` 为保留已有能力并适配；`NEW_BUILD` 为当前缺失；`UNSUPPORTED` 为首版不承诺。

| 能力 / 源码证据 | testing / main | 吸收或缺口 |
| --- | --- | --- |
| 图片批次、item/output、幂等及未知提交：`services/image_generations.py` 的 `submit_batch`、`find_idempotent_batch` | EXISTS / EXISTS | 复用真实 batch/item/output/attempt，不另建 Provider 执行队列 |
| 配额预占/结算：`services/image_quota.py` 的 `reserve_image_quota`、`settle_image_quota` | EXISTS / EXISTS | 导演额度是授权上限，不另扣现有图片配额或账本 |
| 对象存储：`adapters/object_store.py`；输出来源：`domain/models.py` 的 `ImageGenerationOutput` | EXISTS / EXISTS | 新增跨阶段 pin/引用/撤回合同；当前 `retention.py` 仅到期下载产物 |
| 人工图片审核：`api/image_generations.py` 的 `put_image_quality_decision`、`test_review_permissions.py` | EXISTS / EXISTS | 模型 Critic 不写人审资格；选择前重验审核版本、撤回和文件哈希 |
| Pixel input transport：`adapters/openai_analysis.py` 的 `AnalysisImageInput`、`OpenAIAnalysisAdapter` | ADAPTER_REQUIRED / ADAPTER_REQUIRED | 已传 input_image 并结构化 parse，但 detail=low、固定 AnalysisResult 2.2；不等于完整 DNA/像素 Critic |
| 分析领取/心跳/旧结果隔离：`services/analysis_lifecycle.py` 的 `claim_analysis_run` | EXISTS / EXISTS | 增加导演 scope/授权预算，不把 lease 当付费授权 |
| 风格/动作静态+DB 合并：`services/content_catalog.py` | EXISTS / EXISTS | 保留品牌 scope、版本与退役；无完整 Character/Scene 图像资产 API |
| Product/ProductVersion API：`api/products.py`、`domain/models.py` | NEW_BUILD / ADAPTER_REQUIRED | testing 缺失，应回移生产基础，不重复建商品模型 |
| 创意交接合同：`creative/handoff.py` 的 `CreativeHandoffManifest` | NEW_BUILD / EXISTS | 复用 owner/product version/asset hash/shot/order/许可审核字段；不新增 CutFlow 模块 |
| 视频固定服务：`services/fixed_video_tasks.py` 的 `create_fixed_video_task` | ADAPTER_REQUIRED / ADAPTER_REQUIRED | 旧 automatic 会调用学习与编译；新增明确 director_fixed 分支，保留 custom/历史恢复 |
| 图片商品单图：`api/image_generations.py` 的 `_expand_manifest`、`_require_roles` | ADAPTER_REQUIRED / ADAPTER_REQUIRED | 旧融合/分镜要求 model.front+product.front，不能给新导演入口伪造 model.front |
| PromptPreset：`services/prompt_presets.py` | ADAPTER_REQUIRED / ADAPTER_REQUIRED | 可变用户默认值，不是不可变 Prompt Registry |
| CreativeTask/持久素材/Grounded DNA/Prompt Registry/循环编排 | NEW_BUILD / NEW_BUILD | 仅在 CW-0.5 通过后增量实现 |
| 参考图角色权重隔离、模型内部百分比权重、自动商用许可识别 | UNSUPPORTED / UNSUPPORTED | 不宣称 60/40、100/0 控制；高污染图降级 DNA_only |
| 外部摄影自动搜索、真实像素 Critic、自动质量收益证明 | ADAPTER_REQUIRED / ADAPTER_REQUIRED | 搜索可选；真实 Critic 未验证时禁自动修订；收益只能经真实对照评审 |

上述 `services/`、`api/`、`adapters/`、`domain/`、`creative/` 均相对 `backend/src/libtv_agent/`。已有模型 ID 是源码静态映射，不证明当前 Provider 支持、运行配置或价格。

Provider 约束候选：现有固定视频参考总量不超过 7，Prompt 与角色说明总长不超过 3072 字符；导演应在绑定后、付费前校验，不静默截断。Provider 上传、提交、接收证据分轴；SDK 提交重试和模型 fallback 必须纳入调用上限，不允许隐式付费重试。

## 4. 商品与持久素材合同

### 4.1 Product 对齐建议

生产基础已含 Product(user_id, internal_sku_id) 唯一键、ProductVersion(product_id, version_number) 唯一键、truth_fields/immutable_fields/allowed_variation/source_asset_references 和许可/审批状态。版本修订追加，不原地改事实。

CW-1 之前先评审一个独立且窄的对齐包：生产商品模型、schema/enums、API 路由、对应测试及两个迁移回移 testing；确认公共迁移内容未漂移，再在合并 head 上追加 Creative 迁移。禁止逆向全量覆盖测试分支，禁止改旧 revision 内容。

对齐后导演接入必须解决两项风险：`product_page_url` 当前必填，不适合单图无站点输入，建议增量支持上传来源及可空 URL，保留旧 URL 客户端；版本号采用 `max+1`，需原子领取/唯一冲突处理及幂等命令。两项都应新增隔离测试，不制造假商品 URL。

`source_asset_references` 目前是字符串列表，不能直接满足真实对象、SHA、权限和保留证据；关联 `CreativeAssetLink` 后才能作为生产真源。ProductVersion 的事实不可变与审批状态可变分轴；许可 VERIFIED 必须可追溯真实证据，不由用户传入字符串单独证明。

### 4.2 CreativeAssetLink 与选择

字段下限见 JSON 的 `asset_required`，按上传、生成输出、内容库快照分别约束 source_type/source_id。服务端读取真实对象、检测媒体/尺寸、计算 SHA、验证源对象 owner 和原审核版本；客户端 metadata 不构成证明。

Canonical 只能来自已验证用户商品原图。人物身份、场景、风格、首帧和分镜用独立角色；生成图不升格为实物真值。SOURCE_VALIDATED 不是生成图 QUALIFIED。背面 USER_ASSUMED 必须绑定用户确认 ID、事实版本、颜色与包，不追认实物。

不可变来源关系：`creative_task + package_revision + shot_id → batch_id/item_id/output_id → selection`。候选可多个；每次选定快照每镜仅一个 output，排序变更只改 order 不改 shot_id，替换选图产生新选择版本。FIRST_FRAME 与 VIDEO_STORYBOARD 用途独立。禁止用列表位置/文件名猜镜号。

提交视频前重新查 owner、输出所属镜号/包、人工 QUALIFIED、审核未撤回、当前文件 SHA/存在性。ProductionPackage 中记录参考绑定清单及哈希；仅人审合格且已选的候选可成为连续性母图。

每个未终结的包/执行/选择建立素材 pin；下载 URL 过期只重签名，不让用户重传。撤回后阻断新调用和交付资格，但保留允许的审计元数据，已提交远端继续查询/结算。删除由保留期限、仍被引用/执行和许可撤回策略共同裁决，不能从 DownloadArtifact 到期推断原图可删。

StagedUpload 仍是一任务一次领取；持久对象复用时创建任务专属物化/绑定记录，不重复领取旧 upload，不依赖浏览器 File/IndexedDB。进程恢复从持久 link 和对象定位读取，只缺真实对象时请求补必要素材。

## 5. 状态、授权与恢复设计

完整可执行动作矩阵采用任务书 5.1 与 JSON `state_actions`；此处冻结权威边界，不另造第二套远端状态：

| 层 | 权威 / 更新规则 | 异常与恢复 |
| --- | --- | --- |
| CreativeTask | 阶段汇总、state_version、resume_stage；命令 CAS | 旧 facts/package/run_id 结果留历史但不推进新版本 |
| CreativeStageAttempt | analysis/plan/critic 等 run_id、lease、输入输出、授权/消耗 | busy 同键重放；取消只停止新调用；不明费用先对账 |
| ParentTask/attempt | 视频提交、Provider 查询、下载、审核交付 | 继续既有 attempt，不因导演刷新重建远端任务 |
| ImageGenerationBatch/item/output | 图片提交/部分成功/未知/物化 | 保留成功候选，仅对确定失败且有新授权的镜号修订 |
| RealityLoopRun/iteration | scope、候选父链、新包、模块差异与停止原因 | 从真实 iteration 恢复，不从头跑模块或扩大 scope |
| 人工 QualityDecision | 审核人、审核版本、范围、资格/撤回 | 模型 pass 只转人审，不能写 QUALIFIED/REJECTED |

命令身份包含 task、scope/shot、candidate、revision、package、授权及输入哈希。每次新调用在同一数据库事务中校验版本/授权/锁项/素材、领取 lease、原子预占总与阶段预算和模型调用数，写出绑定既有子任务的意图记录；并发靠唯一约束+CAS/行锁，不靠先查询再提交。

`UNKNOWN/WRITE_UNCERTAIN` 保留最坏费用预占，禁止替代生成/修订。确认未提交且未收费才能释放；已提交按真实费用结算，不双扣。下载错误不调用生成 API。超时响应不能直接当未提交；价格未知/报价过期/实际超额转待对账，阻断后续新调用。

付费分析、规划、Critic、修订编译也计入同一总授权，不仅算图片。币种用每授权单一币种整数微单位，禁止无报价的隐式汇率；最坏费用包括 Provider 额外费用与授权允许调用。原系统配额/账本仍是实际扣减真源，导演预占只是限制和关联。

设计候选：analysis/plan 各 1 调用、180 秒；媒体等待 1800 秒、Critic 180 秒；循环默认关闭、每初稿启用默认 1 次修订、硬上限 2。超时、模型组合、具体报价、token/尺寸/张数费用与有效期必须在 D02 冻结，不能拿这些设计数字当真实可用参数。逐模块不必各调一次模型，但模块工件及 I/O 顺序必须可审计。

## 6. 插件吸收与 Prompt 真源

归一化关键规则来源/哈希见 JSON `plugin.source_manifest`；只记录来源与项目合同，不复制 Team_Knowledge、品牌卡、人物资料或第三方图片。解释优先级 27 > 26 > 24 > 23。

执行 G0→D1→D2→D3→D4→H1→E1→E2→E3；真实性修订回涉及的 D3 模块并重检 D4/E1/E2/E3，保留已选方向。Reality 固定 Camera→Lighting→Composition→Human Behavior→Environment→Imperfection，允许 N/A 附理由和 imperfection=none；去 AI 味不得损坏商品、加污渍或换脸。

GroundedClaim 定位 canonical SHA/可见区域或用户确认，facts_revision 更新使未执行包 stale。A/B/C 五维 Human/Scene/Behavior/Camera/Emotion 至少两个开放维度实质不同；连续镜、单变量实验和锁项不足明确豁免/限制，不强制解锁。

Prompt Registry 使用 `(key, version)` 唯一、规则 schema/版本/哈希、模型、输入/输出/内容哈希和激活状态；禁止 UPDATE 历史文本。代码只引用 key/version，包存完整渲染快照。团队规则更新只影响新包。Registry 不是前端默认文本或可变 PromptPreset。

编译顺序为事实/锁项→本镜六维→可信参考因果→脚本/构图/连续性/对白→Compact→Preservation→生产包。Preservation 在拟稿和 Provider 绑定后各检查；长度超限回编译新包重新确认，不截断。执行只绑定角色/素材，不做学习或新规划。

RealityReviewRecord 四轴独立 pass/fail/unverified/N/A，UGC 额外 authenticity/framing；fail 包含区域、观察、约定、原因、one_fix 和原图/输出 SHA。无像素、区域证据/schema 无效或模型能力未证实时停 UNVERIFIED_PIXELS，保留人工路径。Fake 不证明真实模型看到了图片。

每修订追加父候选、新包与幂等键，只动授权未锁模块；全项复核防回归，核心缺陷连续两轮无改善停止。按停止原因转人审、ACTION_REQUIRED 或 BLOCKED；不覆盖人工合格候选、不把错误首帧当母图。这是本项目有界自主能力，不沿用插件宿主的禁止自主循环限制。

## 7. 许可与降级台账

| 素材/能力 | 本轮实际证据 | 首版门与降级 |
| --- | --- | --- |
| 插件 v1.13.5 ZIP | 来源路径、archive SHA、关键规则 SHA | 规则结构研究完成；第三方内容许可未确认，不复制私人原文或资产 |
| 真实 SKU 正反面/详情 | 未提供可确认的真实样本和使用范围 | Canonical 缺失阻断媒体；正面可分析，未确认背面只阻断依赖背面的镜号 |
| 品牌/人物身份 | 现有内容库字段/作用域，不是本轮使用许可 | 人工选品牌；无有权身份图使用文字人物设定，不伪造 ID |
| 摄影/场景参考 | 未提供本轮有权原图 | Reality BASE/inferred；低风险有权可输入，高风险/陌生脸/第三方衣服用 DNA_only |
| 外部检索 | 未验证可用适配/许可 | 可选，不为 gallery 空缺自动生照片，不让检索文本覆盖工具授权 |
| Provider accepted 证据 | 静态适配，不是运行接收记录 | 分 retrieved/displayed/materialized/submitted/accepted；无接收证据写 unverified_visual，严要求则阻断 |
| 自动 Critic/修订 | 仅 Fake 编排 | 真实能力未证实禁用自动修订；保留逐图人工审核 |

待负责人逐项填写 `owner / source / permission_scope / evidence_id / expires_at / withdrawal / retention_days`。许可范围变更使未执行包需要重新预检；对象存在与审核合格均不等于商用权。

## 8. 质量收益与采样候选

以下为待产品接受的目标，不是已测结果；基线值、责任人、测量窗口和费用仍待填写。

| 指标 | 口径 / 候选目标 |
| --- | --- |
| 首个合格首帧耗时 | 分析授权到人审合格；另分 Provider 等待、人工操作；总耗时先记录，人工分钟希望减少至少 20% |
| 重复上传率 | 已有可复用素材被再次要求上传数 / 可复用素材引用数；可用服务端素材目标 0 |
| 重复提交率 | 重复远端提交数 / 唯一逻辑命令数；工程硬目标 0，UNKNOWN 不以重提“清零” |
| 分镜合格率 | 人审合格已选镜号 / 目标镜号；初稿/循环后分开，候选目标不低于旧流程，期望提高 15 个百分点 |
| 商品真实性缺陷 | 印花/文字/配色/版型重大 fail / 已逐项复核候选；已选交付图重大缺陷目标 0，整体 fail 希望比基线减少 30% |
| 未核验比例 | 四轴 required 的 unverified 候选 / 总候选；正式质量样本 required 轴不允许未核验，accepted/背面假设另列 |
| 总成本 | 初稿+修订+分析+规划+Critic+失败/取消/未知预占；不得超过 D02 总授权，成本收益比待接受 |
| 循环收益 | 每初稿修订次数均值、首次/最终人审合格率、全项回归、停止原因占比；不能只报告最佳图 |
| UNKNOWN 占比 | 未对账真实调用数 / 所有提交尝试；小样本记录，不声称生产长期占比为 0 |

分层候选：先一个文字/印花复杂 SKU；在同 SKU/方向/锁项/模型参数下比较旧流程与新流程，真实正反面及单正面假设两路径各两次重复，即 8 张初稿、仅新流程最多 4 张一次修订。另计分析/规划/Critic 调用，不将“12 张图”误当全部模型调用数。初稿/修订保持相同参考路线并记录可控 seed；不可控随机性/多变量写为混杂因素。有限样本只作可行性与缺陷分析，不宣称统计显著。

保留全部失败/取消/未知候选；随机呈现顺序，由人按冻结 rubrics 逐项复核，背面假设不计实物背面通过。下一批再覆盖纯色/不同版型与光照。没有历史样本时旧流程基线也属于新付费采样，单独授权。

本轮真实调用数/费用上限均为 0；真实采样在 CW-3 后另外批准。`static_rule_validated`、`runtime_input_verified`、`pixels_reviewed`、`quality_A_B_verified` 分别验收，前一级不得推定后一级。

## 9. CW-1 文件边界与验证计划

先独立评审 Product 对齐包，再冻结新增 `creative_tasks`、持久资产 link、facts/plan/package revision、stage attempt、loop authorization/iteration、selection/review 表/API；图片及视频仅增加可空关联，旧任务不补造 CreativeTask。新增迁移继承实际已对齐合并 head，CW-1 不实现前端、不启用真实 Provider。

| 测试层 | CW-1 / 后续必须证明 |
| --- | --- |
| Pydantic/schema | 额外字段拒绝、owner/SHA/role/shot/version/许可来源、背面确认与未知分轴 |
| SQLite/PostgreSQL | 原子版本/预算/CAS、并发同键、唯一冲突、空库及含旧数据升级；新表外键/索引；不承诺含新数据 downgrade 无损 |
| Fake/Replay API | 单正面无网站、真实来源链接、刷新/双击、错误 owner/包/镜号、旧 run 结果、素材撤回、费用未知和到限停 |
| 崩溃注入 | 预占前后、提交前后、子任务落库前后、下载前后、循环新包与候选提交边界；真实并发多 worker 不重复调用 |
| director_fixed（CW-4） | spy 证明 compile_video_plan/apply_video_learning/随机动作未调用；旧 automatic/custom 与已提交 Provider 查询/下载恢复不变 |
| UI（CW-5） | Checkpoint 1 接受后，再做四视口交互/视觉与现有审核/交付回归 |

本轮检查器只是离线候选合同和顺序 CAS 模拟，不是完整 API schema，不证明多 worker、数据库锁、真实对象内容或像素质量。源文件 symbol/迁移 head 检查用于发现基线漂移，不证明函数全部语义。

## 10. 本轮验证入口

```powershell
& .venv/Scripts/python.exe -B scripts/check_creative_preflight.py --role testing
& .venv/Scripts/python.exe -B scripts/test_creative_preflight.py -v
& .venv/Scripts/python.exe -B -m ruff check --no-cache scripts/check_creative_preflight.py scripts/test_creative_preflight.py backend/tests/test_content_catalog_editing.py
```

在实际 main 目录用可用 Python 运行同一检查器，role 设 `main`；不在仓库 cwd 直接运行普通 Alembic 命令。隔离回归/迁移的本轮外部 harness 为 `E:/Codex/plugin-audit-creative-workflow-20261010/run-preflight-isolated.py`，显式临时 cwd/数据库、Fake 和网络拦截，不含凭证、不推广运行产物。

最终两侧各 27 项新合同测试、testing 85 项/main 95 项已有后端选集、Ruff 均通过；插件 ZIP 与 13 份关键规则哈希核验通过。局部源码推广记录见 `SPRINT_REPORT_CREATIVE_WORKFLOW_PREFLIGHT_20261010.md`。未运行前端 build/浏览器，因为本轮无前端改动；既有 Checkpoint 1/2 验收状态不更新。
