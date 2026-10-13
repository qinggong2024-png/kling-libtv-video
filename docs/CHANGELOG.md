# Changelog

## 2026-10-13

### Image Studio 信息架构

- 首屏依次展示图生图、文生图、批量生产，记录作为次要入口；手机首屏完整显示三个创作入口。
- 图生图直接上传、填写提示词并复用现有单套编辑生成；批量生产下设批量创作、产品套装与分镜生产，原复杂流程迁至第三级。
- 实际拆出批量表单、记录列表、上传、审核和选片展示；保留持续挂载、原任务合同及旧模块导出兼容。
- 修复子页面与主导航、浏览器历史的同步。文生图保存账号范围的创意草稿，明确现有 API 尚未开放纯文本生成。
- testing build、lint、405 项单测及五视口隔离流程通过；验证与限制见 `SPRINT_REPORT_IMAGE_STUDIO_IA_20261013.md`。

## 2026-10-13

### Director Analysis Contract · Plugin v1.13.7–v1.13.13 Absorption

- 将插件升级能力收口为 `director-analysis.v1` 八步服务端分析合同：
  Product/Brand/Audience DNA → Scene/Reality/Spatial → Storyboard/Shot Mix →
  Key Visual → Motion-Ready → Model-Aware Video Strategy → Emotion/Video Prompt
  → Video QA/One-Fix。
- 每步保存固定顺序、依赖、证据、输出和状态；分析快照篡改、重排或缺失时，
  方向确认、授权和生成命令均阻断，继续复用 state version、幂等、素材哈希、
  Prompt Preservation、人工审核和 UNKNOWN 恢复门。
- 视频策略默认 `strategy_unresolved`，记录具体型号、入口、能力证据、分段映射、
  fallback 和 benchmark 状态；不把官方文档、模型系列名或规划文本当成当前账号
  可用能力、真实媒体交接或视频 QA 通过。
- 智能导演台新增八步链路和视频策略证据展示；不新增产品工作区、不调用 Provider、
  不授予生成授权、不改变旧 automatic/custom 视频路径。

## 2026-10-13

### Director Studio V2 Sprint 4

- 阶段主标题改为“商品输入 / 创意方向 / 生产方案”，保留英文辅助名称；导演模式只显示一个“导演台”主标题。
- 移除商品名称输入；高级创作设置默认收起，材质、视频类型、模特性别、年龄范围、时长、比例和备注均标为“计划支持”。
- 七项设置只记录前端创作意向，不进入现有分析请求；新增四个可选草稿字段并复用项目元数据映射和恢复。
- 修复步骤数字对齐及移动端主按钮被导航遮挡；保持方向确认、生产方案、后端和生成逻辑不变。
- testing/main 独立 build、lint、单测、四视口浏览器与隔离 smoke 通过，详见 `SPRINT_REPORT_DIRECTOR_STUDIO_V2_SPRINT4_20261013.md`；仅同步本轮源码。

### Director Studio V2 Sprint 3

- 将 Creative Direction 的场景/行为与镜头/情绪整合到三张创意决策卡，移除独立对比及重复 DNA / Reality 摘要。
- 摘要保留现有值并标注为结果整理；名称、镜头、情绪明确为本地创意提案，来源详情区分 Fake 结果、提案、用户输入与未提供能力。
- 保留点击只选择、确认才调用 `select_direction`、确认后锁定及既有 Production Package 流程，未改后端、Agent、Provider 或生成逻辑。
- testing/main 的 build、lint、单测及四视口隔离浏览器通过，详见 `SPRINT_REPORT_DIRECTOR_STUDIO_V2_SPRINT3_20261013.md`。

### Spatial Blocking + Key Visual Shot Selector

- 吸收 AI-Fashion-Creative-Director v1.13.7 的空间关系、场景平面、机位轴线、人物运动轨迹和关键视觉选择规则。
- Director Studio 新增规划级 Spatial Director：记录空间锚点、世界光源、C1/C2/C3 机位、180° 轴线、人物起止状态和接触转移。
- 新增 Key Visual Shot Selector，先建立完整镜头时间线，再以 `keep / optional / merge` 选择最少充分关键图；分别显示镜头、关键视觉、计划、授权和已生成数量。
- 规划状态保持 `planned_not_verified` / `planned_not_rendered`，不授予生成权限、不伪造像素复核、不替代人工审核。
- 代码、单元测试和浏览器 fixture 记录见 `SPRINT_REPORT_SPATIAL_BLOCKING_KEY_VISUAL_20261013.md`。

### Reality Evidence Rules

- 保留现有 Reality 六维与 Reality Loop，不新增 Reality Layer。
- 新增版本化 `reality-evidence.v1` 知识库，把人物行动因果、摄影者意图、
  主体/环境空间关系、环境使用痕迹和四类可解释 Imperfection 规则吸收到六维。
- 新 Package 冻结规则快照、版本与内容哈希，并将生成约束和判断标准带入
  Prompt 与人工 `qualityChecklist`；旧包保持原冻结合同。
- `imperfection=none` 继续有效，不默认改商品颜色、印花、文字、轮廓或状态。
- 修复 E1 Preservation 校验重建默认 Reality 决策而丢失已冻结 Camera/Reality
  意图的问题。没有 Provider、付费调用、生产写入或自动质量结论。
- 详细范围、测试和限制见 `SPRINT_REPORT_REALITY_EVIDENCE_20261013.md`。

### Canonical Provider Adapter Boundary

- 新增只读 Provider adapter，将 `ImageGenerationRequest` 编译为 `ProviderRequestPreview`，保留 creative state identity、shot、prompt、preservation/locks hash 与 Product/Character/Scene/Spatial/Camera references。
- 提供显式 execution context 时可生成现有 `CreativeImageProviderRequest`；task、source mapping、evidence、text contract 和幂等字段必须由执行层提供，adapter 不猜测、不伪造。
- 没有 context 时只输出 dry-run preview；Spatial blocked、manifest 不一致或 Character/Scene reference 缺失会明确返回 `BLOCKED` / `UNRESOLVED`。
- 未调用 Provider、Kling、billing、task execution，未修改 Provider contract、数据库或前端；详细结果见 `SPRINT_REPORT_CANONICAL_PROVIDER_ADAPTER_BOUNDARY_20261013.md`。

### Creative Core / Sprint 4 Isolated Acceptance

- 合成球衣 HTTP 整合验收覆盖 Brand DNA、三个 Fake 方向、Package、
  旧图片记录关联及追加人工评价，两侧各 3 项通过。
- 两侧 Package 与导演交付准备浏览器回归通过；Fake 不提升为真实生产。
- 真实产品理解、图片/视频执行与正式人工验收仍未完成；按用户要求停在
  生产流程边界，具体下一包见 `SPRINT_REPORT_HUMAN_LOOP_ACCEPTANCE_20261013.md`。

### Creative Core / Sprint 3 Human Review

- 新增图片 PASS/REWORK/FAIL、视频 PASS/FAIL 及媒介原因码，人工记录与
  QUALIFIED、最终批准、计费、交付和自动学习保持独立。
- 复用 AuditEvent 与已有幂等事务；保存不确定时保留原请求，支持刷新核对
  和同键重试，默认训练导出排除 Fake/Replay。
- 增加图片、视频与导演候选评价入口，无数据库迁移或 Provider 改造。
- testing/main 独立测试及四视口真实评价 API 浏览器通过，报告见
  `SPRINT_REPORT_HUMAN_REVIEW_20261013.md`；源码已同步，未部署。
- 旧 Canonical Image Generation Adapter 扩展任务已停止，未同步产物
  保留待审，不计入当前 Creative Core 主线完成项。

### Canonical Image Generation Adapter

- 新增 provider-neutral image adapter，将 validated `CreativeStateRevision` 与选定 `ShotState` 编译为 `ImageGenerationRequest`。
- Image request 保留 Product/Character/Scene/Spatial/Camera/Shot canonical 内容，并附带 `creative_state_id`、revision、shot ID、source reference manifest 和 preservation hash。
- 编译前校验 revision integrity、shot identity、继承 revision、素材引用、action capability、prompt revision 和 Spatial submission gate；缺失状态明确返回 `UNRESOLVED` 或 `BLOCKED`，不填充虚构事实。
- 保持 `provider_submission_allowed=false`；没有修改 Provider contract/execution、Kling、数据库、前端或 Quality 自动审核。
- 详细结果见 `SPRINT_REPORT_CANONICAL_IMAGE_GENERATION_ADAPTER_20261013.md`。

### Creative Core / Sprint 2 Brand DNA

- 复用现有品牌目录配置，新增稳定 ID、版本和内容哈希的只读 Brand DNA 投影。
- 新导演任务可绑定品牌目录快照；分析及 Package 读取冻结建议，目录后续
  修改或退役不改变旧任务与旧包。通用模式和无品牌旧请求保持兼容。
- 新任务拒绝未知、过期、draft/retired 目录；前端按 ID 选择同名品牌，
  展示目录建议与任务绑定状态，不推断人物身份。
- 无数据库迁移、新 Agent 或 Provider 改造；Fake 分析仍不是产品真实理解。
- 验收见 `SPRINT_REPORT_BRAND_DNA_20261013.md`。

### Creative Core Human Loop / Sprint 1

- 研发主线调整为 Creative OS Core + Human Production Loop，严格按 Package、
  Brand DNA、Human Review、人工测试顺序收敛；保留现有 State 与执行层边界。
- 新增 Creative Package 只读导出投影，在已有导演任务响应中附加九字段、
  来源与字段状态；不新增持久化字段或迁移，不改写原生产 Prompt。
- 新增团队文本复制、图片/视频 Prompt 复制和 JSON 下载；从冻结方向派生
  待人工确认的视频交接草案，保留其与原执行 Prompt 的区别。缺失视频
  Prompt 不显示复制操作；Fake、模板建议、待补充和不可交付状态保持可见。
- 验证结果与交付限制见 `SPRINT_REPORT_CREATIVE_PACKAGE_20261013.md`。

### Canonical Storyboard Integration

- 将 Director snapshot 编译为结构化 `StoryboardState` 与显式有序 `ShotState[]`，保留 campaign intent、hook、情绪推进、商品证据、CTA 和选定方向。
- Shot 适配器保留旧 storyboard 的时长、镜头语言、entry/exit state、动作和 source binding，并记录动作能力检查与连续性锁。
- 新增 unresolved validation；缺失 Character/Scene/Camera 会显式保留 unresolved，缺失或未验证 Spatial 会将 canonical state 标记为 `BLOCKED`，不创建虚构创意事实。
- 未修改 Kling、Provider request/execution、数据库迁移、前端页面或质量自动审核。

### Canonical Creative State Foundation

- 新增 `creative-state.v1` 后端不可变状态模型，覆盖 Product、Character、Scene、Spatial、Camera、Storyboard、Shot 和 Quality。
- 新增只读投影，将现有 `CreativeTask`、ProductVersion、Director snapshot、CreativeRecord 和质量记录组合为统一 CreativeState。
- 新增 revision/content/locks/source snapshot 哈希与篡改检测；保留现有任务、Provider、计费、配额和交付边界。
- 新增 Phase 1 专项测试；未新增 API、迁移、Provider 调用或前端状态写入。

## 2026-10-12

### Creative Workflow MVP-4A

- 新增 Provider 提交边界合同：将当前有效的 MVP-3B 预检和独立人工授权收口为不可变 `ProviderSubmissionTicket`。
- 票据绑定请求/证据/预检哈希、素材 manifest、费用额度、Provider、模型、镜头和幂等键；图片保留 `image_edit`，视频保留 `director_fixed`。
- 新增进程内幂等领取和 `SUBMITTED` / `UNKNOWN` / `FAILED` 结果合同。`UNKNOWN` 只允许对账，`FAILED` 必须使用新的幂等键。
- 本包不调用 Provider、不上传、不扣费、不写 quota/ledger/attempt；`READY_TO_SUBMIT` 仍不等于已生成、已人工合格或可交付。
- testing/main 各 303 项组合回归通过。后续真实提交前仍需补持久化票据、数据库唯一约束、额度原子领取、崩溃恢复和 Provider UNKNOWN 对账。

### Creative Workflow MVP-4B

- 新增持久化 `provider_submission_ticket` 合同，保存票据快照、请求/证据/预检哈希、素材 manifest、费用额度、状态和 Provider 结果摘要。
- 新增数据库唯一幂等键和事务性 claim；同键重放返回原票据，同键不同哈希冲突，过期、UNKNOWN、FAILED 和停止状态不可再次领取。
- testing/main 独立组合回归各 214 项，MVP-4A/MVP-4B 专项各 27 项通过；未调用 Provider、未扣费、未写 quota/ledger/attempt，未执行生产迁移。
- 后续进入默认关闭、人工授权、单样本的真实图片 Provider 接线；PostgreSQL 多 worker、崩溃恢复、真实费用原子化和像素收益仍未证明。

### Creative Workflow MVP-5A / MVP-5B / MVP-6A

- MVP-5A：新增图片 `FIRST_FRAME/image_edit` Provider executor 边界，dry-run/replay/test-double 与 live 双重授权门分离，Fake/Replay 保持不可交付。
- MVP-5B：新增 durable input lease/materialization，绑定 owner、任务、镜头、哈希、许可和媒体输入，支持重放、撤回、过期和字节篡改阻断。
- MVP-6A：新增默认关闭、人工授权、有界次数/费用、锁项冲突、六维 Reality、Prompt Preservation 和 UNKNOWN 对账的真实性循环运行门，固定插件吸收后的模块顺序。
- 三包均未调用真实 Provider、未扣费、未写 quota/ledger/attempt；5B 报告保留两个历史迁移触发器失败，另行修复。

### Creative Workflow MVP-7A / MVP-7B / Migration Repair

- MVP-7A：将 durable submission ticket、durable input lease 和 `FIRST_FRAME/image_edit` executor 串为单样本编排边界；dry-run/replay/test-double 可审计，live 仍由安全闸拦截。
- MVP-7B：将真实性循环运行门接入独立编排器，按插件吸收后的固定模块顺序输出下一步命令、revision 摘要、等待/停止原因和审计事件，不调用模型或 Provider。
- 迁移修复包：保留历史 migration 不变，以后续 migration 修复 product_version 删除保护和 creative_command 不可变触发器。
- 三包均已在 testing/main 独立验证并同步；真实 Provider、费用、像素复核和交付资格仍未执行。
- 当前进入业务确认门：需要 SKU/素材许可、Provider/model、预算、管理员 live 开关和人工确认后，才能进行真实图片单样本验证。

## 2026-10-11

### Creative Workflow MVP-2B / MVP-2C

- MVP-2B：新增 Creative 首帧到现有图片入口的桥接前置计划，校验人工资格、选择、授权、哈希和 batch/item/output 映射；不提交 Provider。
- MVP-2C：新增 `director_fixed` 视频前置计划，校验首帧与 `SHOT_01` 分镜的人工资格、选择、来源和锁定 Prompt；不创建视频任务或 Provider attempt。
- 两包均已在 testing 验证并同步实际 main 独立复验；Fake/Replay 仍为 `OFFLINE_SYNTHETIC_ONLY`，不可交付。
- 下一包 MVP-3A 只编译真实 Provider 请求合同并支持 dry-run/replay，真实 POST、费用和像素质量另行授权。

### Creative Workflow MVP-3A

- 新增图片与 `director_fixed` 视频 Provider 请求合同编译，支持 `dry-run` / `replay`，冻结 Prompt、Preservation、素材角色顺序、对象哈希、来源映射和稳定幂等键。
- 合同固定 `actual_submitted=false`、`provider_submission_allowed=false`、`OFFLINE_SYNTHETIC_ONLY`，不生成 URL、不创建 Provider attempt、不升级普通 QUALIFIED 或 Deliverable。
- testing/main 独立回归通过；真实 Provider POST、素材物化绑定、费用/账本、像素质量和部署仍未完成。

### Creative Workflow MVP-3B

- 新增 Provider 提交前只读预检：重新验证请求/证据哈希、权限、人工审核选择、商品事实和许可状态。
- 新增临时素材物化与 adapter input manifest，检查 Provider 能力声明、角色顺序、报价、额度、人工授权和暂停开关。
- 结果固定为 `READY_FOR_HUMAN_SUBMIT`，仍不执行 Provider POST、不预占费用、不创建 attempt，不升级 Fake/Replay 为正式素材。
- testing/main 组合回归通过；真实提交原子门、费用落账、远端 UNKNOWN 对账和人审 API 仍待实现。

### Creative Workflow MVP-1F / MVP-2A

- MVP-1F：Director Studio 读取并优先展示服务端 `snapshot.latest_review`，刷新后保留人工审核决定和拒绝理由，移除“服务端未持久化”的过时提示。
- MVP-2A：在人工合格并选择的 `FIRST_FRAME` 后补齐单镜 `VIDEO_STORYBOARD / SHOT_01` 离线合同，支持授权、Fake 候选、首帧/分镜独立审核与选择，以及 shot → batch/item/output 映射。
- 两包均已在 `codex/testing` 验证并局部同步实际 `main` 独立复验；未修改 Provider、迁移、OpenAPI 或旧 automatic/custom 视频行为。
- Fake/Replay 仍明确为 `OFFLINE_SYNTHETIC_ONLY`，不可交付；真实图片入口、`director_fixed` 视频执行和有界自主循环接线仍是后续开发包。
- 详细结果见 `SPRINT_REPORT_CREATIVE_WORKFLOW_MVP1F_20261011.md` 与 `SPRINT_REPORT_CREATIVE_WORKFLOW_MVP2A_20261011.md`。

### 内部 MVP 交付收敛

- 明确 5–10 人局域网阶段继续按任务书实现功能，只降低工程验证和发布等待，不删减导演、Reality、Prompt、审核和有限循环能力。
- 新增只读 `scripts/check-internal-mvp.ps1`，检查 API、前端、代理和关键目录，不启动进程、不迁移、不读取 `.env`。
- stop 现在写入独立 `CreativeRecord(kind="stop")` 审计事件，保持原有停止与幂等语义。
- MVP-1A 两侧 `2 passed`；MVP-1B 异常端口验证返回非零；后续继续推进导演规划接入。

### Creative Workflow CW-4 并行小包验收

- 将大包拆为 D4/E1 文字合同接线、有界自主真实性循环纯策略、事务/恢复证据三个独占小包。
- CW-4A 两侧各 75 项、CW-4B 两侧各 25 项、CW-4C 两侧各 5 项及 scoped Ruff 均通过。
- D4 冻结和 E1 执行前校验已接入；循环策略仍未接入服务运行路径，SQLite 恢复证据不代表 PostgreSQL/生产就绪。
- 记录 stop 不单独追加 `CreativeRecord`、PostgreSQL 多 worker、真实 Provider/像素质量等后续风险。
- PM 调度与验收见 `SPRINT_REPORT_CREATIVE_WORKFLOW_CW4_DISPATCH_20261011.md`。

## 2026-10-10

### CW-2 隔离包：事实锁、撤回、幂等与 Fake 批次映射

- 新增 ProductVersion `USER_UPLOAD` 来源、事实快照哈希和追加式版本幂等；后续版本会使未执行创意任务失效，保留旧历史。
- 新增 owner 作用域任务创建键和完整请求指纹；重复请求返回原任务，不同请求冲突。
- 撤回写入不可变事件，查询/对账保留审计，撤回后继续阻断新执行、选图和恢复。
- 新增结构化 GroundedClaim、Reality 六维顺序、Prompt Registry/Preservation 哈希和不可变迁移触发器。
- Fake 首帧绑定现有 ImageGenerationBatch/item/output；占位媒体明确 `OFFLINE_SYNTHETIC_ONLY`，不代表真实质量。
- 新增迁移 `d1e2f3a4b506`；testing 外部隔离选集 115 项通过。实际 main 同步与独立验证见 CW-2 报告。

### CW-1 隔离骨架与单正面 Fake 闭环

- 按用户确认拆分隔离开发、真实验证、上线门；真实业务样本不阻塞 Fake 开发。
- 窄范围回移生产 Product 基础与两份迁移，新增三张导演任务/不可变记录/幂等命令表；Product 模型不重复。
- 新增 test/local-store/Fake-only API，覆盖单正面输入、方向选择、六维/生产包、授权、占位候选、离线人审/选择、有限显式修订和未知对账。
- 候选 batch/item/output 为 `fake:` 来源标识，媒体为商品原图占位，AI review 全为 UNVERIFIED；禁止用于真实生产或交付。
- 对齐后两侧迁移 head 为 `d0c1e2f3a405`；只推广源码，不执行生产迁移。
- 测试、局部同步及实际限制见 `SPRINT_REPORT_CREATIVE_WORKFLOW_CW1_20261010.md`。

### Creative Workflow CW-0.5 前置验证启动

- 交付前置评审包、机器可读离线设计合同、规则来源哈希 manifest、检查器与 Fake 测试；不实现导演 API 或前端。
- 核实实际 main 已有 Product/ProductVersion 和创意交接基础，testing 缺失；记录窄范围回移/合并迁移建议，不重复建模型、不执行回移或生产迁移。
- 核实两侧 25/27 份迁移与不同 heads，仓库外临时 SQLite 全链空库升级通过；未验证 PG、带数据升级或线上配置。
- 建立预算/调用/未知费用、不可变包/逐镜来源、插件按序六维/定向修订、许可/降级、Prompt 真源、质量候选目标与独立采样计划。
- 隔离选集发现内容库旧错误断言，修正四处为结构化 message，保留所有拒绝与跨品牌隔离要求；不修改业务接口。
- D01 至 D06 尚待决策/验证，CW-0.5 未通过，不进入 CW-1；真实调用额度为零，未部署或扩展 Checkpoint 1 前端。
- 最终测试与 testing/main 局部推广证据见 `SPRINT_REPORT_CREATIVE_WORKFLOW_PREFLIGHT_20261010.md`。

### Creative Workflow 插件吸收与立项前置补齐

- 实际审查用户 `plugin (2).zip` 的 ai-fashion-creative-director v1.13.5，记录来源哈希与优势吸收映射，不把插件文字规则称为已有引擎。
- 新增 CW-0.5 / CW-P01 至 CW-P08：能力、持久素材/shot_id、状态恢复、预算/授权、Grounded DNA/Prompt Registry、许可、两侧迁移/兼容和质量收益基线；均仍待评审。
- 按插件先方案→授权→生成/复核顺序与常开六维 Reality 实施，归一化 27 > 26 > 24 > 23 优先级、参考污染和显示/接收证据、Compact Compiler/Preservation、分镜构图/对白/恢复。
- 允许本项目服务端有界自主真实性循环，不照搬插件宿主的“不做后台自主”；默认关闭，启用默认每初稿 1 次修订、首版硬上限 2 次，逐调用控制总预算/有效期/停止与未知提交。
- 修订追加不可变包与候选，不在执行绑定时重写 Prompt；像素 Critic、人工 QUALIFIED、背面证据/资格、director_fixed 和旧 automatic/custom 行为分轴。
- 补充 CW-A16 至 CW-A30，同步产品、开发计划和 QA；本轮仅改文档，不调用 Provider、不执行迁移/部署，不更新功能验收状态。
- 本轮检查和 testing/main 局部同步结果见 `SPRINT_REPORT_CREATIVE_WORKFLOW_ENRICHMENT_20261010.md`；上一轮任务书报告保留历史范围。

### Creative Workflow 开发合同修订

- 新增 `CREATIVE_WORKFLOW_IMPLEMENTATION_20261010.md`，固化用户确认的范围及逐包实施/验收标准，功能尚未实现。
- 正面单图可分析；分镜前补背面或确认无印花纯色生产假设，区分实物证据与用户设定。
- 导演台提取 DNA，人工选择品牌并复用内容库风格/人物表演/动作快照，不依据站点猜测强行归属品牌。
- 视频目标收口为自定义工具与导演自动执行；后者使用已锁 Prompt，自动拉取原产品与已审核分镜，不重复用户上传。
- 保留生产引擎、幂等/预算/审核/恢复、旧客户端与历史任务；不增加独立 `/director`，不越过 Checkpoint 1。
- 同步更新产品、开发计划和 QA；本轮为文档修订，不运行新功能/浏览器/付费调用，不执行生产迁移或部署。
- 文档检查及实际 testing/main 局部同步证据见 `SPRINT_REPORT_CREATIVE_WORKFLOW_SPEC_20261010.md`。

## 2026-10-09

### Video Studio 完成度重做 · 方向仍待接受

- 用户拒绝前一候选“成熟度不够，像是毛坯房”；本轮重做1120px工作边界、素材/上传邻接、紧凑生成方式、字段层级与统一提交收束。
- 只改Studio视觉CSS，保留纵向业务流程、真实文案和前轮交互保护；新增320/800/820等6视口照片/长文本检查。
- testing/main build、lint与240/236项单元测试通过；最终流程、动效与同步证据见 `SPRINT_REPORT_STUDIO_MATURITY_20261009.md`。
- 修改的设计系统只标记新候选，未获方向接受，不扩展其他工作区、不部署或真实付费生成。

### Video Studio 视觉与交互细化 · Checkpoint 1

- 完成 impeccable 源码/截图评审，形成优先级与 interface-design / UI/UX Pro Max 视觉规范候选；保留浅色/蓝色品牌与真实文案。
- Video Studio 连续白色工作区、轻导航/浅色输入、44px操作、强化付费说明；修复移动安全核对换行、键盘radio/焦点、方案原生弹窗和上传busy反馈。
- emil-design-eng 操作动效区分键盘/指针并支持reduced-motion；共享组件修复惠及既有页面，其他工作区视觉推广等待方向验收。
- testing/main build、lint、240/236项单元测试，各13项Studio、4项交互动效、66项页面回归与图片审核/比较检查通过；源码精确同步保留生产差异。
- 正式入口拒绝连接，使用当前源码隔离预览；没有上线、服务重启或真实付费生成。详见 `SPRINT_REPORT_VISUAL_UPGRADE_20261009.md`、`VISUAL_UPGRADE_REVIEW_20261009.md`、`STUDIO_VISUAL_PLAN_20261009.md`。

### 第二轮视觉探索

- 根据用户对第一轮机械感的反馈，新增安静工作台、工具面板、阶段流程三个独立样稿，保留旧稿。
- 统一中性视觉、轻量控件和排版；第三版探索渐进步骤，不覆盖正式布局规范。
- testing/main 各 15 组原型浏览器检查通过，样稿源码局部同步；正式 frontend 未变，未部署。
- 详见 `SPRINT_REPORT_VISUAL_V2_20261009.md`；视觉成熟度等待人工评价。

### Sprint 1：纵向操作区

- 将 Video Studio 改为纵向素材整理、创意配置、统一提交和结果；排序、删除和大图检查仍在上传处。
- 可选主体默认收成一行，保留选择与摘要；标准表单保持原布局。修复桌面工具栏换行及局部按钮样式。
- testing/main build、lint 和 240/236 项单元测试通过；各 13 项 Studio 流程通过。testing 最终追加 10 项 make 回归，main 最终 66 项全页面回归通过。
- testing `2d462c6` → main `83a9729` scoped promotion 成功，保留生产接口差异。安全预览恢复，实际标签刷新核查；没有正式部署。
- 依据与限制见 `VIDEO_STUDIO_BANDS_REVIEW_20261009.md`，验证见 `SPRINT_REPORT_VIDEO_STUDIO_BANDS_20261009.md`；停在 Checkpoint 1，效率与方向仍需人工验收。

### 全站升级：三方向视觉探索

- 新增明亮精密、深色剪辑台、素材工作台三个独立 HTML 原型及来源说明。
- 覆盖字体栈、颜色、背景、控件、导航、双区布局和本地交互状态；不替换正式设计系统或页面。
- 使用本机 UI/UX 数据库、Lucide、Playwright；等待用户选定方向后实施。
- 初轮与修订后各 15 组原型浏览器检查通过；最终 testing/main 检查和推广结果见 `SPRINT_REPORT_VISUAL_DIRECTIONS_20261009.md`。
- 不部署、不重启、不调用真实生成或写入审核。原型检查不替代正式页面验收。

### Sprint 1：上传区整理

- 根据用户再次反馈合并上传、排序、删除和大图检查，不再单列分镜序列区。
- 桌面采用素材准备与生成配置两个工作区，统一提交位于两区之后；七图换行，空态不占位。
- 模板紧凑摘要保留真实约束，配方按需打开；标准图片转视频表单保持原布局。
- 记录新的布局依据、未测量假设和 Checkpoint 1 人工验收边界；详见 `SPRINT_REPORT_VIDEO_STUDIO_UPLOAD_20261009.md`。
- testing/main build、lint 与 238/234 项单元测试通过；各 13 项 Studio、66 项页面回归、图片审核及 14 项 fixture/smoke 检查通过。最终阴影修复后 testing 受影响 make 页面追加 10 项通过。
- testing `f3a36a6` → main `d31bcde` 局部推广成功，保留生产差异，正式目录 dist 未覆盖。安全本地预览恢复，浏览器连接不可用，未声称当前标签已核查；没有正式部署或付费调用。

## 2026-10-08

### Sprint 1：布局修订

- 记录 Video Studio 任务优先级、动线、方案取舍和可测验收，明确缺少真实用户研究与效率测量。
- 改为紧凑输入侧栏 + 主生产区；移除永久源图大画布和重复缩略表示。
- 源图缩放/大图按需打开；保留分镜拖拽、键盘移动、删除、批量只读检查与提交安全边界。
- 增加四视口布局几何、结果数控件、按需检查和焦点恢复验收；详见 `SPRINT_REPORT_VIDEO_STUDIO_LAYOUT_20261008.md`。
- 实际浏览器检查补修 1102px 付费摘要挤压，加入中间宽度及付费说明可见性断言；测试/生产分支最终 11 项 Studio、10 项受影响页面回归均通过。
- testing/main build、lint 与 236/232 项单元测试通过；本轮各完成 66 项全页面回归和图片审核检查。代码分两次 scoped promotion 同步，保留生产差异，正式目录 dist 未覆盖。
- 安全本地预览已恢复，用户当前页已确认；正式服务没有部署或重启。
- 仍停在 Checkpoint 1；不扩展其他工作区，不将布局门禁等同于人工方向验收或上线批准。

### Sprint 1：Video Studio

- 实现 Canvas 优先的 Video Studio、模板选择/配方、分镜排序、队列、结果和任务抽屉。
- 新增可复用 UI/素材/模板/分镜/任务组件与六态展示适配，不替换后端状态和交付语义。
- 修复重复提交、未知提交禁用、批量约束和部分失败后成功组重复创建的风险。
- 增加模板读取恢复、嵌套视频 Modal、真实设置时长和来源 ID 保留。
- testing build/lint、234 项单元测试、10 个 Studio 浏览器用例通过；既有 66 个页面回归及图片审核检查通过。
- 新增隔离 fixture 和本地安全预览入口；不调用真实 Provider，不加载 .env，不代理请求。
- main 已同步并独立通过 build/lint、230 项单元测试、10 个 Studio 流程、66 个页面回归及图片审核检查；保留生产差异，构建产物存放在外部验证目录。
- 源码提交 testing `70b90cd` → main `e3ae81d`；详见 `SPRINT_REPORT_VIDEO_STUDIO_20261008.md`。
- 当前停止在 Checkpoint 1，等待人工方向确认；未扩展其余三个工作区。

### Added

- 固化《衣影工坊 AI Creative Studio》V1 产品范围与产品原则。
- 固化 `/studio/image`、`/studio/video`、`/tasks`、`/library` 四个产品工作区。
- 固化 Video Studio → Image Studio → Task Center → Library 的开发顺序。
- 固化 Design Token、基础组件、业务组件和 Canvas 优先的视觉规则。
- 固化生成状态的六态展示模型，并明确它不替代后端真实 phase、审核和交付状态。
- 固化组件、页面、浏览器、响应式和可访问性 QA Checklist。
- 记录当前 React + TypeScript + Vite 项目的 KEEP / ADAPT / DEFER 技术决策。
- 新增项目技术审查报告和 Sprint Report，并在 AGENTS.md 固化开发前阅读与人工检查点。

### Not Changed

- 未改动后端 API、数据库、Provider、计费、认证或状态机。
- 未把当前生产导航强行迁移为新的 URL 路由。
- 未同步 `.env`、运行时状态、缓存、构建产物或未跟踪压缩包。
- 未把 `Generated`、`Technical PASS` 或 Provider 成功提升为 `Deliverable`。

### Next

- Sprint 0：统一基础 UI 导出、状态展示映射和页面验收 fixture。
- Sprint 1：实现并验收 Video Studio + Design System。
- Checkpoint 1：人工确认 Video Studio 方向。

### Verification

- testing：build/lint 通过，31 个测试文件、209 项测试通过。
- main：build/lint 通过，32 个测试文件、205 项测试通过；构建产物在外部验证目录。
- 规范已从 `codex/testing` 局部推广至实际 `main` 目录，并检查文档一致性；不代表线上发布或页面完成。
