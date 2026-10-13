# Sprint Report：Creative Core / Sprint 1 Package

日期：2026-10-13
范围：Director → Creative Package 只读交接；真实样本仍留到 Sprint 4。
状态：testing 与实际 main 工程验收通过；源码同步完成，未部署。

## 完成

- 将新研发主线登记到 PRODUCT_SPEC、DEVELOPMENT_PLAN 和独立任务书。
- 提供九字段 Creative Package、provenance 和逐字段状态。
- 保留原始图片 Prompt、商品事实、来源 hash、锁项、Reality 和包版本。
- 从冻结方向派生人物行为、镜头参考和视频交接草案；标为 PROPOSED，
  Fake 来源继续写入草案。不猜测人物身份、外貌、受众或实物背面。
- 人工可复制完整交接文本、图片/视频 Prompt，或下载完整 JSON。
- 先验证现有 text contract；篡改、缺失合同、错误镜头映射不可导出。
- 历史包使用当时冻结上下文和父链，不混入新版本或无关分镜。
- API 响应附加只读导出；不持久化投影，不改变旧命令重放与执行状态。

## 修改

- 新增 creative/package_contract.py 及纯合同测试。
- 新增 services/creative_package_export.py，在现有离线任务 API 装饰响应。
- 新增独立前端导出组件、适配器和样式；仅在干净的
  DirectorPlanningViews.tsx 挂载，不改写原前端窗口的 DirectorStudio 等文件。
- 新增 API 回归与 ui-creative-package-check.mjs，复用既有离线交付验收。
- 无 ORM、数据库迁移、Canonical State、Provider、账本或生产配置变更。

## 测试

- testing 后端：纯合同及相关 API/工作流/文本合同组合 116 项通过。
- testing 前端：53 文件 / 329 项通过；lint、TypeScript 和外部目录 build 通过。
- testing Ruff 与 diff 检查通过。
- 独立浏览器：1440/1024/768/390 宽度，图片/视频/全文复制、JSON 内容、
  刷新、历史缺失合同、焦点和剪贴板失败恢复通过；无横向溢出。
- 原离线 Director → 视频准备流程：1440×900、390×844 和两项恢复边界通过。
- 浏览器只使用合成 fixture；无 Provider、付费调用或生产写入。
- 构建、截图、fixture 与报告存放 E:/Codex/verification/creative-package-sprint1，
  不同步到生产源码目录，不覆盖正式 dist。
- 实际 main 后端同组独立回归 116 项通过，Ruff 通过。
- 实际 main 前端独立回归 54 文件 / 325 项通过，lint、TypeScript、
  外部目录 build 通过；保留生产专属差异，未把 testing 数字当成 main 结果。
- 实际 main 同一四宽度导出浏览器验收通过，零页面错误、零外部请求。
- 本轮 16 个白名单源文件和文档局部同步；未同步其他窗口改动、秘密、
  本地数据库、runtime、缓存、构建或截图，未创建全树覆盖。

## 发现问题

- 现有 analyze 仍固定输出三个 Fake 方向，不是产品图真实理解。
- 真实当前包尚未提供受众、人物身份/外貌；导出保持空值与 UNRESOLVED。
- 视频 Prompt 是可复制的派生建议，尚未成为已批准的 Provider 执行 Prompt。
- FIRST_FRAME 与 SHOT_01 仍是现有离线流程；不证明真实图片/视频任务已执行。
- 因此本报告仅接受 Sprint 1 的工程交接能力，不宣称用户的球衣真实案例、
  Checkpoint 1、真实质量、完整生产闭环或上线接受已经通过。

## 下一步

- Sprint 2 复用现有 site-style-profiles 配置/读取 Brand DNA，稳定 ID 和版本优先。
- 当前品牌名、材质、视频类型只在前端 Brief；真正绑定任务及历史包需要
  明确的输入和冻结合同，不能通过导出时读取“最新品牌”改变旧包。
- Sprint 3 评价标签独立于 QUALIFIED/APPROVED，优先复用 AuditEvent，
  追加记录与只读导出；Fake 默认排除训练候选。
- 涉及实质的数据模型、架构或生产流程变化时，按用户要求停在具体差异评审。
- Sprint 4 最终执行受控真实样本；保留素材许可、Provider/model、预算、
  UNKNOWN 对账与人工授权门。
