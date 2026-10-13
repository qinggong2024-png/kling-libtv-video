# Sprint Report：Director Studio V2 Sprint 5

日期：2026-10-13
范围：Production Package 展示层与信息层级；不增加生产能力
状态：本轮指定自动化验收通过；最终交接体验仍由产品负责人接受

## 完成

- 第三阶段优先显示当前方案摘要：已确认方向、冻结首帧包版本、状态和 Fake / 规划标识。
- 主体依次展示制作要求、图片生成提示词、视频创作提案、镜头规划和质量检查。
- 复用现有 Creative Package 交接组件及其复制 / JSON 导出。
- 提示词用途、来源和字段状态来自已有包 / provenance / fieldStatus；缺失来源保持未提供。
- 图片提示词以冻结包原文为准；视频内容称为创作提案，不升级为已验证执行合同。
- 提示词全文在有限高度的可滚动区域展示，复制调用仍使用完整原始字符串。
- 镜头规划区分本地空间 / 人物运动提案与冻结父包关联记录；不称为完整或已完成分镜。
- 质量检查只显示现有要求和可展开的判断标准，不产生自动通过结论。
- 技术详情默认收起；保留 Package ID、Hash、Evidence、Bridge、Contract、
  分析轨迹、空间规划编辑与原有 Fake 授权 / 生成 / 审核操作。
- 同一不可变包内刷新状态不重置技术详情的展开状态，便于继续既有验证操作。
- 保留方向卡只选择、确认才调用 select_direction、确认后锁定及既有恢复和生成规则。

## 修改

源码 / 测试八个文件：

- `frontend/src/features/director-studio/DirectorStudio.tsx`：
  方案摘要、主体交接组件及技术内容层级；没有修改命令函数。
- `frontend/src/features/director-studio/CreativePackageExportView.tsx`：
  制作要求、提示词、镜头规划、质量检查及默认折叠技术内容。
- `frontend/src/features/director-studio/DirectorPlanningViews.tsx`：
  生产包证据只负责技术展示，交接内容由上层独立组织。
- `frontend/src/features/director-studio/creativePackageExport.ts`：
  中文交接名称及已有来源 / 状态的展示映射；保持 JSON 导出与复制底层函数。
- `frontend/src/features/director-studio/creativePackageExport.css`：
  交接文档层级、有限高度提示词、44px 图标操作及移动端纵向布局。
- `frontend/src/features/director-studio/creativePackageExport.test.tsx`：
  缺项、来源、状态、折叠层级、历史包与合同不变性。
- `frontend/src/features/director-studio/DirectorStudio.browser-check.mjs`：
  新展示层级及原有 Fake workflow 四视口回归。
- `scripts/ui-creative-package-check.mjs`：
  原有真实编译器合成包检查，适配 V2 确认流程，增加四视口交接及完整复制检查。

文档：`docs/CHANGELOG.md` 和本报告。

没有修改后端 workflow、package contract、Prompt 生成、Agent、Provider、API、
数据结构或生产资格。局部前端读取已有记录，不产生新的后端写入。
本地镜头提案没有写入或合并到冻结 JSON 合同中。

## 测试

- testing 原共享工作区初次 build / lint 被并行 Image Studio 重构阻断，
  报错来自该模块的临时引用 / 导出和未使用变量；没有撤销或修复无关改动。
- 从 testing 入场提交 `b0367c3` 建立隔离验证工作区，只叠加本轮八个文件：
  build、lint 通过，Vitest 57 文件 / 404 项通过。
- main 源码同步后独立 build、lint 通过，Vitest 57 文件 / 397 项通过；
  两侧原有代码 / 测试数量差异保留，没有盲目覆盖生产树。
- 并行 Image Studio 提交完成后，testing 共享工作区最终 build、lint 通过，
  Vitest 57 文件 / 405 项通过。
- 两侧交接组件检查均通过 1440、1024、768、390：
  技术详情默认隐藏、Fake 明显、无横向页面溢出、缺项诚实展示、
  独立图片 / 视频全文复制、整包复制、JSON 下载、刷新和旧包无合同分支。
- 两侧 V2 确认到交接检查均通过
  1440x900、1024x768、768x1024、390x844：
  卡片选择不执行命令，确认才进入第三阶段，第三阶段首屏优先显示方案摘要，
  制作 / 提示词 / 镜头 / 检查顺序正确，复制不会追加 workflow 命令。
- 复制检查同时比对传给 clipboard.writeText 的原始字符串和实际剪贴板全文；
  Windows 剪贴板读取的 CRLF 仅在测试比较时归一化，生产代码不改写 Prompt。
- 复制失败分支通过，保留可再次复制及 JSON 下载出口；下载 JSON 与原合同深度相等。
- 两侧原 Director workflow 均通过四视口、每个视口 18 个既有 Fake 命令：
  确认锁定、首帧 / SHOT_01 授权、审核拒绝、幂等重试、刷新及 UNKNOWN 禁用。
- 两侧 smoke 均通过九个现有页面入口；服务器不加载 .env、无代理，
  屏蔽非 GET / HEAD 请求，不访问正式后端。
- testing 额外全站 shell 脚本在四个视口的旧“批量创作”入口断言处失败；
  导演空态 / 上传、导航和布局段已执行通过，任务深链 / 返回通过。
  这是并行 Image Studio 工作完成前的检查结果；没有放宽断言或扩展本轮修改范围。
- 并行工作完成后重新运行 testing 共享工作区完整 shell 脚本：
  1440、1024、768、390 全部通过，任务深链及记录滚动通过；
  无横向页面溢出。该检查仍为隔离 UI，不替代正式版本真实商品验收。
- 已人工复核四个视口首屏及移动端长文截图。
- 证据目录：`E:/Codex/director-v2-sprint5-20261013/`，
  内含 testing-package、testing-workflow、testing-smoke、testing-shell
  和 main-package、main-workflow、main-smoke、shared-final-shell。
- 没有真实 Provider、数据库写入、付费生成或正式版本运行验收。

## 同步

- testing 源码提交：`25af3e2`。
- main 源码提交：`ef7dde7`。
- 同步前逐文件确认 main 的八个本轮源文件与 testing 入场基线一致；
  同步后再次检查文件一致性与两侧状态。
- 只同步本轮源码 / 测试和文档，保留并行任务、生产专属行为及用户未跟踪文件。
- 构建产物、合成数据、截图和缓存保存在仓库外，未覆盖运行目录 dist。
- 源码同步不代表正式入口 `http://192.168.30.126:5173/` 已部署；
  没有服务重启、迁移、远程推送或上线操作。

## 发现问题

- 当前合同没有独立商品约束摘要；页面显示未提供，具体保留要求仍以冻结提示词原文为准。
- 本地多镜头规划与服务端包链属于不同数据层；没有新增完整视频时间线或镜头执行合同。
- 镜头时长、已审核媒体、视频型号 / 入口和真实质量仍可能缺失；本轮不补造。
- 历史包缺少服务端 Creative Package 投影时，不创建虚构交接合同，
  既有技术证据和 Fake 操作仍可展开查看。
- 四视口生产方案首屏证据来自隔离 DirectorStudio + 现有样式，
  不是当前正式服务的真实商品任务验收。

## 下一步

- 人工接受生产方案主体与状态表达。
- Sprint 6 验证完整人工流程，再按真实商品失败案例决定能力补充。
- 本轮不扩大高级输入、生产引擎或真实生成范围。
