# Sprint Report：上传区整理与布局修订

日期：2026-10-09
范围：Checkpoint 1 返工，尚未获得人工方向验收

## 完成

- 上传、排序、删除、大图检查合并到上传区，移除独立分镜序列区。
- 桌面改为素材准备与生成配置两区，提交横跨两区之后；移动端同序纵向排列。
- 七张图自动换行，空状态不预留分镜占位；取消上传区遗留阴影。
- 模板默认展示紧凑摘要，完整配方按需打开，标准表单保留完整模板卡。

## 修改

- ProductionComposer 仅调整展示结构，不修改 API、幂等、计费、UNKNOWN 锁、批量部分失败恢复或来源 ID。
- Storyboard 作为上传区内的可编辑网格，保留拖拽、键盘移动、删除、只读保护和检查焦点恢复。
- TemplateSelector 新增可选 compact 模式，仍显示真实状态、画幅和分镜约束。
- 更新产品、设计、开发与 QA 文档，并记录用户否定、关联任务分组、空间依据及测量缺口。

## 测试

- testing：build、lint、238 项单元测试通过。
- 初轮 Studio 13 项通过；覆盖五种宽度主流程、UNKNOWN、无模板、模板恢复、批量及明确拒绝、七图桌面/移动端排序删除。
- 初轮全页面离线回归 66 项、图片审核检查、fixture/smoke 14 项通过。
- 截图发现旧上传阴影后已修复；最终 build/lint/238 项单元测试、Studio 13 项及受影响 make 页面 10 项重新通过。
- 最终 testing 两图 + 历史主体 + 自动化配置的提交按钮纵向坐标：1440px 为 694.11–742.11px，1102px 为 708.78–756.78px，1024px 为 697.91–745.91px；768px 为 1358.62–1406.62px，390px 为 1352.11–1400.11px。移动端需滚动，不声称全视口首屏提交。
- main：独立 build、lint、234 项单元测试、Studio 13 项、全页面回归 66 项、图片审核检查及 fixture/smoke 14 项通过；构建输出在外部 `upload-main-build`，正式目录 dist 未覆盖。
- 外部证据根目录：`E:/Codex/visualizations/2026/10/08/01a11aa7-388c-7c00-857f-b320ea54a013`。
- testing 最终 Studio：`upload-layout-testing-final`；全页面：`upload-pages-testing`；最终受影响页：`upload-make-testing-final`；图片审核：`upload-review-testing`。Studio 报告绑定实际文件 hash，历史初轮截图保留。
- main 证据：`upload-layout-main`、`upload-pages-main`、`upload-review-main`。源码推广 testing `f3a36a6` → main `d31bcde`，仅 13 个安全源码、测试和文档文件。
- 推广后 12 个文件 Git blob 一致；ProductionComposer 仅保留既有主体重新读取接口与错误去重差异。main 的任务错误展示和 Required Hard Gates 文案未改动。
- testing 工作区仅保留用户未跟踪 ZIP；main 工作区干净。未同步 .env、缓存、运行时状态、构建产物、媒体或 ZIP。
- 安全预览进程已恢复在 5187，HTTP 返回 200，使用 main 源码和外部合成媒体，不连接真实后端。Codex 浏览器打开请求返回 queued；浏览器连接报告 auth token 不可用，未宣称已核查用户当前标签。隔离 Playwright 截图与流程已验证。

## 发现问题

- 上轮把上传和排序拆到两区，用户明确不认可，本轮修正操作归属而非仅缩小预览。
- 旧全局样式给上传区留下卡片阴影；视觉检查后已局部覆盖，不修改其他页面。
- 素材多时提交随内容后移；移动端需要滚动，不用固定付费按钮覆盖内容。
- 没有真实用户计时、点击对照、Provider 质量证据或上线批准。

## 下一步

- 本轮源码已同步实际 main 并独立验证；记录更新随后作同范围文档推广。
- 本地安全预览：`http://127.0.0.1:5187/studio/video`；只模拟生成。正式入口仍为 `http://192.168.30.126:5173/`，本轮没有部署或重启正式服务。
- 继续停在 Checkpoint 1，未经方向确认不扩展其余三页。
