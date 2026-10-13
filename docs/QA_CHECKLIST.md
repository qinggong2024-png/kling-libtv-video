# 衣影工坊 V1 QA Checklist

版本：V1.0
日期：2026-10-08
状态：开发与交付验收标准冻结

内部 MVP 例外：5–10 人局域网阶段采用 `docs/INTERNAL_MVP_DELIVERY_PROFILE_20261011.md` 的轻量验收门槛。任务书功能要求不变；未执行的 PostgreSQL、多 worker、灾备和真实质量统计验证必须在报告中明确标注，不能作为已完成能力。

## 1. 自动化门禁

每次前端变更至少执行：

```powershell
cd frontend
npm run build
npm run lint
npm run test
```

涉及页面交互时追加：

```powershell
npm run smoke:ui
```

上述 npm 脚本均在 `frontend` 目录运行。UI smoke 需要显式指定已授权的测试入口；默认 localhost 不是正式版。现有 smoke 主要覆盖页面可见性，不能替代下述 Playwright 生成流程测试。

`build`、`lint` 或相关测试失败时，不得宣称页面完成。

## 2. 组件验收

基础组件：

- Button：默认、悬停、禁用、进行中、危险操作、键盘焦点；
- Input：标签、错误、占位、键盘输入；
- Badge：语义颜色和文本不溢出；
- Drawer / Modal：打开、关闭、Escape、焦点恢复、滚动锁定；
- EmptyState：空数据和下一步动作；
- Thumbnail：缺图、加载、contain / cover、固定比例。

业务组件：

- AssetCard；
- TemplateCard；
- ShotCard；
- ResultCard；
- TaskCard；
- Gallery；
- AssetDetailDrawer；
- GenerationPanel。

业务组件不得自行发明 API 成功、审核通过、正式交付或费用信息。

## 3. Video Studio 主流程

### Happy Path

- [ ] 打开 Video Studio；
- [ ] 选择产品；
- [ ] 选择人物、场景或其他允许素材；
- [ ] 选择模板；
- [ ] 上传区内唯一分镜网格正确显示素材，模板要求可见，按需检查支持缩放与大图；
- [ ] 上传区内支持拖拽及键盘排序、删除，不存在独立分镜序列区；
- [ ] Generate 按钮在输入完整时可用；
- [ ] 创建任务只发生一次；
- [ ] 页面显示 Preparing assets；
- [ ] 页面显示 Generating；
- [ ] 页面显示 Validating；
- [ ] 页面显示 Completed 或 Failed；
- [ ] 结果区显示真实结果或真实错误；
- [ ] 结果详情可从当前工作区打开，不丢失上下文。

### Failure / Recovery

- [ ] 无素材时无法提交；
- [ ] 无模板时显示可执行提示；
- [ ] 网络失败显示可重试状态；
- [ ] Provider 结果未知时不自动重新付费；
- [ ] 重复点击不会创建重复任务；
- [ ] 任务详情刷新后状态来自服务端；
- [ ] 失败任务可进入 Task Center；
- [ ] 下载失败不会被误显示为重新生成；
- [ ] 页面刷新后不丢失可恢复的任务详情链接。

## 4. Image Studio 主流程

- [ ] Product、Character、Scene 选择器可区分类型；
- [ ] 生成图片前展示预计输出信息；
- [ ] 生成中每个阶段可感知；
- [ ] VariationGrid 使用固定媒体比例；
- [ ] 选择结果不会自动写入 QUALIFIED 或 Approval；
- [ ] 审核失败要求理由；
- [ ] 合格结果才可以进入 Create Video；
- [ ] 图片任务完成通知不会因离开页面而丢失；
- [ ] 账户切换不会展示另一账户的本地草稿或任务。

## 5. Task Center

产品展示层六态：

```text
queued
preparing
running
validation
completed
failed
```

- [ ] 六态均有中文可读标签；
- [ ] 后端更细 phase 通过单一映射层展示；
- [ ] 原始 phase 仍可在技术详情查看；
- [ ] FilterTabs 与查询参数保持一致；
- [ ] 列表、详情、返回和滚动恢复可用；
- [ ] Drawer 打开与关闭不丢失筛选条件；
- [ ] 重试动作遵守服务端 actionCapabilities；
- [ ] 未知结果不显示为 completed；
- [ ] 结果审核、最终批准和 Deliverable 有明确区分。

## 6. Library

- [ ] Character、Product、Scene、Template 分类可切换；
- [ ] 资源卡片显示真实名称、缩略图和类型；
- [ ] 空状态提供下一步动作；
- [ ] DetailDrawer 可打开、关闭和恢复焦点；
- [ ] 删除、编辑和选择遵守现有权限；
- [ ] 资产选择后可返回 Studio 并保持上下文；
- [ ] 不生成虚假的版本、来源、费用或审核元数据。

## 7. 视觉与响应式验收

每个完成页面检查：

视口：

```text
1440 × 900
1024 × 768
768 × 1024
390 × 844
```

检查项：

- [ ] 没有页面横向溢出；
- [ ] 视觉中心是画布、素材或结果；
- [ ] 栏宽依据任务优先级而非固定三栏，移动端与 DOM 动线一致；
- [ ] 文字适配容器，不遮挡相邻内容；
- [ ] 卡片、面板、按钮圆角符合 Design System；
- [ ] 状态颜色使用语义 token；
- [ ] 不出现无意义渐变、装饰性光球或后台式统计墙；
- [ ] Loading 文案不是单独的 `Loading...`；
- [ ] 空、错误、进行中、完成四类状态均有设计；
- [ ] 资源图片和视频不被错误裁切；
- [ ] 低宽度下按钮和状态标签仍可操作。
- [ ] Video Studio 不设置永久空源图画布，每个分镜默认只出现一次；
- [ ] 空上传区不渲染分镜占位，七张图在桌面与移动端换行，操作无需横向滚动；
- [ ] 模板名称不重复展示，摘要保留真实状态、画幅和数量约束，完整配方可打开；
- [ ] 素材、创意、提交纵向排列；桌面仅创意区内部并列模板和生成方式，移动端 DOM 顺序一致；
- [ ] 可选主体默认收起且键盘可展开，收起保留选择并显示真实摘要；种子参考图存在时默认展开；
- [ ] 两图缩略网格保持紧凑高度，1440×900 两图配置后生成结果区起点在首屏内；该场景不含待处理或进行中任务；
- [ ] 上传区没有遗留 hover 阴影，不把整块素材准备区包装为浮动卡片；
- [ ] 1440×900 配置两张图与历史主体后，付费提交按钮无需滚动可见；
- [ ] 放大检查关闭后返回原分镜焦点，保留拖拽、键盘排序与删除；
- [ ] 1102px 中间宽度提交摘要不挤成竖排，所有宽度付费确认文案可见；
- [ ] 记录任务权重假设和人工测量缺口，不将测试桩流程通过等同于效率验证。

## 8. 可访问性

- [ ] 主要操作可通过键盘完成；
- [ ] 图标按钮有 `aria-label`；
- [ ] Drawer / Modal 有标题和正确关闭行为；
- [ ] 动态状态使用 `role=status` 或等价语义；
- [ ] 错误使用 `role=alert` 或等价语义；
- [ ] 焦点不会进入已关闭的浮层；
- [ ] `prefers-reduced-motion` 下不依赖动画传递信息；
- [ ] 颜色不是传达状态的唯一手段。

## 9. 浏览器流程

使用现有 Playwright 和离线 fixture；API 写入仅允许隔离测试桩，禁止落到正式后端或真实付费 Provider。现有 `scripts/ui-pages-offline-check.mjs` 可作页面回归入口，但其当前覆盖不包含生成/批准操作。

记录报告目录、source HEAD/文件 hash、浏览器版本、视口、截图、断言和测试限制。Playwright 未可用时报告缺口，不能用静态组件渲染测试替代浏览器操作证明。

Video Studio：

```text
open page
→ select asset
→ select template
→ create task
→ observe status
→ open result
```

Image Studio：

```text
open page
→ choose Product / Character / Scene
→ generate fixture
→ select output
→ review
→ transfer qualified output to video
```

Task Center：

```text
open page
→ filter
→ search
→ open detail drawer
→ close and restore list context
```

## 10. 发布前声明门槛

允许声明：

```text
TASK_DONE
FUNCTIONALLY_VERIFIED
INTEGRATION_VERIFIED
```

必须有对应测试和浏览器证据。

不允许仅凭代码存在、Mock PASS 或静态截图声明：

```text
INFRASTRUCTURE_READY
PRODUCTION_LOOP_READY
PRODUCTION_READY
ZERO_TOUCH_ELIGIBLE
```

这些状态还需要后端、真实生产链、审核/交付证据和必要的运行环境证据。

本次仅固化文档：运行 build/lint/unit 基线；不执行浏览器生成流程，不更新页面验收状态，不宣称效率或生产质量改善。

## 11. Creative Workflow 待实现验收

CW-2 隔离实现已覆盖以下工程回归，但不更新真实质量、生产就绪或 Checkpoint 状态：

- [x] 撤回追加事件、UNKNOWN 后撤回再对账仍 BLOCKED；
- [x] owner 作用域任务创建幂等和请求指纹冲突；
- [x] ProductVersion 上传来源、快照哈希、追加版本失效；
- [x] Prompt Registry/Preservation 结构哈希和现有 batch/item/output 映射；
- [x] testing 空 SQLite 迁移到 `d1e2f3a4b506`、隔离选集与 scoped Ruff。

2026-10-10 增量标准，详见 `CREATIVE_WORKFLOW_IMPLEMENTATION_20261010.md` 的 CW-P01 至 CW-P08、CW-A01 至 CW-A30。以下均未执行，不继承旧 Studio 的验收结果。

- [ ] 商品正面单图可分析；背面未知和受众假设不伪造为视觉事实。
- [ ] 人工品牌选择覆盖模型/站点猜测，通用风格不强行归属品牌；内容库权限与条目快照可验证。
- [ ] 分镜前提示补背面或确认无印花纯色；已有背面不重复索要，缺背面不镜像正面图案，底色不明要求确认。
- [ ] 单商品首帧支持文字人物设定，不伪造人物图；旧自定义生图角色、推测默认值和审核不变。
- [ ] 选方向不生图；首帧、指定镜号分镜、视频及付费分析分别满足授权和数量预算。
- [ ] 原始商品和合格首帧角色区分；首帧/分镜选择分别持久化，逐项审核才得到 QUALIFIED。
- [ ] 已锁生产包不在提交时重新生成 Prompt；只做可验证参考绑定，不自动加入学习指导。
- [ ] 视频新自动模式读取导演 Prompt、原商品图和合格分镜，不重复用户上传；参考数量与顺序预检。
- [ ] 自定义模式可编辑 Prompt，带入导演素材后编辑不篡改原包；旧任务原 Provider 恢复正常。
- [ ] 无权、未合格、审核撤回、素材缺失/哈希不匹配或过期包均在新付费提交前拒绝。
- [ ] 同键重放、双击、部分失败、进程重启及导演子任务关联恢复不重复提交/预算；UNKNOWN 不自动重提。
- [ ] 后补真实背面、改品牌或锁项产生新版本；内容库更新不静默改变旧任务。
- [ ] testing/main 隔离迁移、回归、前端 build/lint/unit 和四视口浏览器有独立证据；正式付费验收单独授权。
- [ ] CW-0.5 的能力、素材/shot_id、状态/恢复、预算/授权、DNA/Prompt、许可、迁移/兼容和指标阈值均有评审证据，不仅有要求文本。
- [ ] 插件 v1.13.5 来源版本/哈希与归一化 manifest 可追溯；27 > 26 > 24 > 23 优先级正确，不残留 60/40 或 100/0 伪模型权重。
- [ ] Product→方向候选→人工选择→锁定 DNA/六维/参考门→文字方案→授权→绑定/生成/复核顺序可追溯；旧先图后分镜编号不覆盖先方案门。
- [ ] Camera→Lighting→Composition→Human Behavior→Environment→Imperfection 每维有本镜决定/N/A 原因；imperfection=none 合法，新人物两项协调结构特征不覆盖已锁脸。
- [ ] Canonical Product 来源可访问；GroundedClaim 的 source_fact_keys/facts_revision/confidence_basis 可核对；A/B/C 至少两项实质差异，锁项不足、连续镜和单变量例外正确。
- [ ] 摄影参考检索/展示/物化/提交/接收证据分轴；无权、高风险第三方服装/脸或未知安全不能默认视觉输入；DNA_only 保留可信观察，不冒称 accepted。
- [ ] 无参考默认仍完整执行六维；Provider 不提供 accepted 证据时如实降级，用户不允许降级则阻断；原商品缺失不能以类似图补齐。
- [ ] Prompt Registry/模板版本不可原地修改；拟稿及绑定后 Preservation 不丢商品锁、摄影几何/焦点/光/衣料受力；新规则不覆盖历史 Prompt。
- [ ] 逐镜 shot_id 在多候选/部分失败/修订/排序后映射包、item/output、选择；无权或错镜输出拒绝，文字分镜与真实图、口型与对白规划分开。
- [ ] 四维 Product/人拍/空间光/卖点与 UGC authenticity/framing 独立结论；每个 fail 有区域/现象/合同/最小修复，无像素或原图只能 unverified；AI 不写 QUALIFIED/REJECTED。
- [ ] 自动复核模型实际支持原图与输出像素和结构化证据，未证实时禁用自动修订；Fake Critic 通过不等于真实图通过。
- [ ] 自主循环默认关闭；启用须确认 scope、镜号、修订次数、可改模块、模型总调用/预算/有效期；默认 1 次修订、首版硬上限 2 次，不授权额外分镜/视频。
- [ ] 循环回失败模块重检下游，追加包/候选/幂等身份；不得改商品事实、用户锁、背面假设、对白或镜头目标，不覆盖既有人工合格候选和选择。
- [ ] 全项复核发现修复回归能记录；同核心缺陷连续两次未改善、到限、缺像素、授权过期、用户停止、锁冲突和 UNKNOWN 各有停止原因/可恢复阶段。
- [ ] 分析/规划/生成/复核全部计入总预算，阶段上限与现有配额/账本不双扣；并发 worker 原子预占/领取，崩溃、旧结果、超时与未知费用不绕过总额度。
- [ ] director_fixed 负断言证明未调用 compile_video_plan/apply_video_learning，旧 automatic/custom、历史 Provider 查询/下载/attempt 恢复不变。
- [ ] USER_ASSUMED 背面与 qualification_scope 分开；按假设人审合格不声称实物背面核验，UNDECIDED 不生成背面镜，后补原图不追认旧图。
- [ ] 商品/首帧/分镜来源、哈希、保留/撤回/物化和任务专属 StagedUpload 桥接正确；导出/文本恢复不假称素材已传，缺失只索要必要资产。
- [ ] 静态规则、运行输入、像素复核、质量 A/B 四级证据独立；样本/分母、初稿与循环后合格率、人工分钟、总费用、缺陷/未核验比例及停止原因均按预设口径记录。
- [ ] 一个 SKU 小样本结果只代表该样本，不承诺所有款型提升；Checkpoint 1/2、真实调用、上线/迁移仍须明确批准。

上轮文档修订只检查合同一致性、引用、格式和局部同步；本轮前置验证如下，仍不执行新导演功能或更新上述功能勾选状态。

### CW-0.5 工程证据

后续用户已批准 CW-1 隔离骨架与单正面 Fake 开发；成本/许可/真实质量门在真实验证前，发布门在上线前。下列未勾选项不等于隔离开发禁止，Fake 验证也不改变真实功能验收状态。首包证据见 `SPRINT_REPORT_CREATIVE_WORKFLOW_CW1_20261010.md`。

- [x] 形成 `CREATIVE_WORKFLOW_PREFLIGHT_20261010.md`、离线设计合同与检查/测试入口，明确 PASS 不是立项批准。
- [x] AST 校验两侧迁移 graph/head；仓库外临时 SQLite 空库分别升级到当前 head，不读取真实 `.env`。
- [x] Fake 验证授权/版本/owner/锁项/模块顺序、预算与未知费用、逐镜选择/哈希/人工资格、回放与停止边界。
- [ ] 生产商品基础窄范围回移 testing，评审源差异后冻结统一迁移 head。
- [ ] 隔离 PostgreSQL、含旧数据升级及多 worker/崩溃证明；顺序 Fake CAS 不代替数据库证明。
- [ ] 成本/币种/模型/有效期、素材许可/SKU、质量阈值/采样计划完成负责人确认。
- [ ] 真实像素 Critic 支持与结构化区域证据验证；当前 UNVERIFIED，自动修订禁止启用。
- [ ] CW-P01 至 CW-P08 正式评审通过，才允许 CW-1；Checkpoint 1/2 保持人工门。

本轮已修正内容库四处旧字符串错误断言，继续断言许可/品牌/跨品牌的 422 拒绝及具体 message，不改变接口或放宽条件。最终两侧选集数量、检查与同步结果见 `SPRINT_REPORT_CREATIVE_WORKFLOW_PREFLIGHT_20261010.md`。
