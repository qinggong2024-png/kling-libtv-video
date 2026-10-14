# Sprint Report：Sprint 8 P0 稳定性收尾

日期：2026-10-14

范围：AI Quota 前端绑定、素材库回归、桌面详情返回与滚动恢复。
状态：本轮限定修复和离线验收完成；不代表全产品、移动端或真实生产验收。

## 完成

- 补齐 main 缺失的既有额度读取 API 和类型，解除前端全量验证阻塞。
- 按两侧实际页面分别验证素材库，不强行推广 testing 的导航和内容库重组。
- 验证任务搜索、筛选、详情关闭、浏览器 Back、详情刷新后返回和滚动位置。
- 验证 testing 的生成资产打开任务详情后返回原来源页面及浏览位置。

## 修改

- `frontend/src/api.ts`：main 同步 testing 已有 `getAIQuota(signal?)`，
  保留既有 request 的认证、超时、取消和结构化错误语义。
- `frontend/src/types.ts`：main 同步既有 `AIQuotaUsage`、`AIQuota`，
  美元字段保持字符串，不新增额度计算或状态推断。
- `scripts/ui-stabilization-check.mjs`：两侧新增隔离验收；
  显式区分 `generated-assets` 与 `catalog`，不使用宽泛选择器掩盖差异。
- `docs/CHANGELOG.md`、本报告：两侧增加本轮记录。
- 本轮没有修改 App、导航恢复、素材库组件、Studio 布局或后端源码；
  两侧原有及并行修改均保留。

## 测试

| 已执行的验证快照 | codex/testing | 实际 main |
| --- | --- | --- |
| build | 通过，外部输出目录 | 通过，外部输出目录 |
| lint | 最终通过 | 通过 |
| 全量 Vitest | 61 文件 / 420 项通过 | 61 文件 / 413 项通过 |
| 额度与导航聚焦测试 | 3 文件 / 11 项通过 | 包含于全量测试 |
| P0 浏览器 | 1440×900、1024×768；46 项通过 | 相同视口；44 项通过 |

- 额度：浏览器调用真实前端客户端、模拟响应；验证美元字符串和 UNKNOWN 保留、
  503 `AI_PRICE_NOT_CONFIGURED`、401 `AUTH_REQUIRED` 不被显示为成功余额。
- 任务：25 条合成记录，`filter=active&q=Stabilization`；
  Escape、Back、详情刷新后 Escape 均保留搜索与筛选，滚动恢复误差小于 4px。
- testing：生成资产查看详情后回到 `view=library`，恢复原浏览位置。
- main：保留“内容与主体库”；风格库搜索空状态、清空搜索和当前 tab 均正常。
- 两侧素材库无横向页面溢出，没有未捕获浏览器异常。
- 最终浏览器报告记录源码 SHA-256，运行前后源码一致。
- 浏览器阻断外部请求和非 GET/HEAD 请求；外部请求、写入请求及 fixture 写入均为 0。
- 期间 testing 的并行分页代码和素材库测试曾分别导致 lint/单测失败；
  并行更新消除失败后重新运行 build、lint、全量单测与浏览器。
  这些并行修正不计为本轮补丁，也没有由本轮推广到 main。

证据目录：

- testing 最终浏览器：`E:/Codex/sprint8-stabilization-20261014/testing/final-current-p0/`
- main 最终浏览器：`E:/Codex/sprint8-stabilization-20261014/main/final-p0-stable/`
- testing 最终命令日志：上述 testing 目录的同级 `build.log`、`lint.log`、`unit.log`。
- 两侧构建输出在证据目录内，未覆盖正式 frontend/dist。

## 发现问题

- 原素材库失败断言针对旧 DOM；testing 已有“生成资产”实现，
  main 保留原目录页面，两者不是同一页面合同。
- 更强滚动测试初次失败时，后台 lazy 页面尚在加载，加载占位消失导致页面高度变化。
  回归改为等待页面完成加载后记录浏览位置；稳定页面的返回缺陷未复现，
  因此没有盲改恢复逻辑。冷启动期间交互及慢网加载仍未纳入本次验收。
- 两侧既有 creative-shell 检查在 1440、1024、768 通过；
  390 的导演动作与移动导航重叠检查失败。保留证据，
  不把桌面 P0 通过宣称为移动端通过。
- testing 在验收后继续发生 App/API 的并行更新。以上结果适用于已记录的
  测试快照，不构成持续变化工作目录的冻结验收；新历史分页、图片资产接入等
  功能仍由其开发范围独立验证。本轮没有继续把这些改动推广到 main。
- 隔离合成 API 不能证明正式额度服务、真实资产、真实付费生成或生产数据质量。

## 同步

- 实际 main 目录：`C:/Users/Reel/Documents/libtv-auto-main-sync`。
- API/type 采用局部补齐；验收脚本和报告精确同步，Changelog 仅追加同一条目。
- 保留 main 的既有 API、导航、内容库和其他生产差异，
  不覆盖 dirty worktree，不提交并行任务文件。
- 不同步 `.env`、运行状态、缓存、构建产物、截图或压缩包。
- 源码同步不等于部署；没有推送远程、重启正式服务、迁移或写入生产数据。

## 下一步

- 单独处理 390px 导演按钮遮挡，完成移动端验收后再关闭该问题。
- testing 的素材库/任务分页等并行功能由各自范围完成验收和同步，
  不混入本轮额度绑定修复。
- Task Center、Library、Settings 进一步体验统一仍属 Sprint 8 P1；
  本轮不重做已接受的三个 Studio。
