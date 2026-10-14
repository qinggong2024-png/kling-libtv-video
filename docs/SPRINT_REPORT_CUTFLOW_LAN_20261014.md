# Sprint Report：Cutflow 局域网交接

日期：2026-10-14。范围：默认关闭的第一版源码及隔离验证。
用户已同意实施；真实部署、生产迁移和启用仍未执行。

## 完成

- LibTV 持久化交接、异步传输、Cutflow 接收/本地缓存、主动状态对账，
  以及独立待审核成片回传构成可验证的闭环。
- 原始生成结果、原技术/人工批准与剪辑版本保持独立；没有将剪辑文件
  写入原 DownloadArtifact 修订或自动批准交付。
- 复用现有结果卡、媒体下载鉴权、Modal、样式和 Cutflow 正常生产流程。
- scoped 源码从 codex/testing 同步到实际 main；没有覆盖正式 dist 或运行配置。

## 修改

- 新增 CutflowHandoff 表、迁移、owner-only API、独立传输进程、
  功能开关与安全环境样例。迁移接入现有 head，未形成额外分支。
- 原型中同步复制的 HTTP 请求改为 202 持久化排队；按用户+源文件版本
  防重复、短数据库事务、CAS 租约、心跳、退避和失败重试。
- 两端清单/文件 SHA-256、临时文件原子替换、路径包含检查、大小限制；
  ffprobe 超时/取消时回收子进程，回传以单线程 FFmpeg 完整解码验证。
- Cutflow 配套代码在 `E:/Codex/cut-architecture-v2-review`，
  分支 `codex/libtv-nas-bridge`，基线 `14bd20b`。新增 Bearer 控制接口、
  显式账号映射、持久接收记录、独立串行文件进程和不可变回传版本。
- 前端支持继续剪辑、展开查询、发送、刷新恢复、失败重试、打开 Cutflow、
  独立待审版本预览/下载；AUDITOR 禁止写入。默认不开入口，不新增工作区。
- 新增双仓库 HTTP/NAS/FFmpeg fixture 与浏览器验收脚本。
- OpenAPI 在两目录按各自源码重新生成；没有把 testing 的整个合同或
  其它进行中的导演源码复制到 main。

## 测试

| 范围 | codex/testing | 实际 main |
| --- | --- | --- |
| 后端选集：交接、媒体、合同、鉴权、下载/故障 | 41 passed | 40 passed |
| 前端 build | passed，输出到外部验证目录 | passed，输出到外部验证目录 |
| 前端 lint | passed，最终无新增警告 | passed |
| 前端已有单元选集 | 432 passed / 59 files | 428 passed / 60 files |
| 浏览器交接流程 | 390/1280px 各 9 项通过 | 390/1280px 各 9 项通过 |

后端包含 10 请求并发幂等、越权/只读、路径越界、哈希篡改/大小限制、
响应丢失重放、过期租约恢复、活租约拒重、真实可解码视频回传及版本隔离。
双仓库测试真实调用控制 HTTP、本地目录模拟 NAS，用 FFmpeg 裁切替代
真实 AI 排片，不连接生产/Provider。迁移测试在临时 SQLite 将旧 head
带一个用户记录升级，验证记录保留、单 head 和新增索引；不验证生产 PostgreSQL。

Cutflow：接收专项 6 项通过；stability/account-isolation/core 与本次专项
合计 100 项通过。最后补充同文件 ID 的返修版本恢复测试并重跑专项。
新增 Next routes 在全量 build 编译阶段通过，专项 TypeScript 与 ESLint 通过。
全量 build 未通过：仓库缺少忽略文件 `.openai/hosting.json`；
`npm ci` 另因已有 Codex SDK package/lock 版本不一致失败。
验证依赖用 `npm install --ignore-scripts --package-lock=false` 安装，
没有改动依赖清单、lock 或伪造 hosting 配置。

浏览器证据与构建产物：

- `E:/Codex/validation/cutflow-20261014/browser-testing/browser-report.json`
- `E:/Codex/validation/cutflow-20261014/browser-main/browser-report.json`
- 对应目录 `cutflow-390.png`、`cutflow-1280.png`；截图已人工检查。
- Cutflow 交付补丁：`E:/Codex/validation/cutflow-20261014/cutflow-libtv-bridge.patch`。

## 发现问题与修复

- 原型晚于 READY 才建数据库记录、网页执行大文件复制：改为先持久化排队。
- 幂等键原为整条 variant：改为源 artifact 版本，允许新来源重新交接。
- SQLite CAS 的 ORM 内存时间比较失败：关闭内存求值、以数据库条件竞争。
- Cutflow 导入后进程中断可能重拷并覆盖正在编辑的源：恢复时验证已存在
  批次来源并复用，不覆盖人工修改。
- 返修可能复用 output file ID：按更新/返修签名重新导出、哈希形成新版本。
- 前端重试与慢查询竞态：写操作期间和跨版本的旧查询不回写状态。
- 预览载入时按钮禁用导致焦点丢失：保存触发按钮，关闭预览后明确恢复焦点；
  两侧追加焦点断言后重跑浏览器流程。
- main 的环境样例、API 客户端和 RecordsView 有已有差异：逐处合并，
  保留生产额度样例、Product API 与记录页原有行为；不整文件覆盖。

## 同步与限制

测试入场 HEAD `2331145`，实际 main 入场 HEAD `9f22619`；
生产位置以实际目录 `C:/Users/Reel/Documents/libtv-auto-main-sync` 为准。
本轮在两个现有工作区留下 scoped 修改，保留正在进行的创意/导演、
安全规划及运行报告改动，没有把它们一并提交。独立新增源码与交接 API
块逐项核对一致；生产专属内容保留。两侧源码同步成功。

没有编辑真实 `.env`、迁移正式数据库、重启服务、写生产任务/审核、
调用付费模型或连接远程 Cutflow/NAS。源码同步不代表正式入口上线，
正式前端仍是 `http://192.168.30.126:5173/`。

尚未验证：远程实际版本/地址、Windows 服务账号共享权限、真实母版与
输入适配、NAS 吞吐、5–10 人负载和真实成片质量。没有自动独立剪辑交付
批准、多生成结果合并编排、自动 NAS 清理或远程批次深链接。

## 下一步

按 `CUTFLOW_LAN_IMPLEMENTATION_20261014.md` 提供远程地址、共享路径、
账号映射与母版，审阅远程源码差异后应用补丁。取得真实部署批准后执行
迁移与服务配置，从一条真实已生成视频进行 NAS 联通/剪辑/回传/人工
质量验收，再扩大用户规模和渲染并发。关闭默认开关可保留原流程。
