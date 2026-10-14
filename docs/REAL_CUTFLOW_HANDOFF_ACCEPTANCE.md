# REAL CUTFLOW HANDOFF ACCEPTANCE

日期：2026-10-14，时区：Asia/Shanghai（UTC+08:00）。
实查窗口：12:14–12:19。
目标：单用户、单条真实视频验证 `LibTV → NAS → Cutflow → NAS → LibTV`。

**验收状态：BLOCKED / NOT RUN。真实局域网闭环尚未执行，不能判定通过。**

2026-10-14 12:28–12:33 补充核查更正：服务注册的代码目录是
`C:\Users\Reel\Documents\libtv-auto-main-sync`，DataRoot 为独立数据目录，
handoff 源码已在代码目录中。实际配置使用 SQLite，直接只读查询确认
`cutflow_handoff` 表不存在。详见 `REAL_CUTFLOW_LAN_DEPLOYMENT_RESULT.md`。
下文原核查时刻的 HTTP 证据保留，目录及数据库类型结论按此更正。

## 1. 完成与执行边界

- 已检查本机配置、正式入口、实际 Windows 服务、运行配置目录及部署文件。
- 已记录阻塞原因、待测指标、文件完整性比对要求和人工质量判定项。
- 架构、业务代码、真实配置、数据库和运行服务均未修改。
- 没有上传、传输、创建交接/剪辑任务、渲染、回传或调用付费生成。
- 未选择测试用户/视频，未创建 handoff ID 或 Cutflow batch ID。
- 既有 localhost、本地目录模拟 NAS、合成视频和 FFmpeg 裁切测试，
  不计入本次真实验收，也不复用其耗时或视频哈希。

## 2. 真实配置核查

| 项目 | 本次实查结果 | 状态 |
| --- | --- | --- |
| 正式 LibTV 入口 | `http://192.168.30.126:5173/` | 可访问 |
| testing 源码 | `E:\Projects\libtv自动化生成`，`codex/testing` | 已核实 |
| main 源码 | `C:\Users\Reel\Documents\libtv-auto-main-sync`，`main` | 已核实 |
| 实际正式服务 | `LibTVProductionApi`，Running | 已核实 |
| 服务运行账号 | `NT SERVICE\LibTVProductionApi` | 已核实 |
| 服务实际数据目录 | `F:\Users\Reel\Documents\libtv-production` | 来自服务注册表 DataRoot |
| 服务配置文件 | 上述目录内 `.env` | 存在，仅提取相关非敏感字段 |
| 服务选定配置 | `APP_ENV=development`，`OBJECT_STORE_MODE=local`，`SHARED_AUTHENTICATION_ENABLED=true` | 已核实 |
| LibTV 实际 NAS UNC 路径 | 未提供；已检查配置未发现 NAS/CUTFLOW/BRIDGE 环境项 | 未配置 |
| Cutflow 机器 LAN 地址和端口 | 未提供；已检查配置无对应地址 | 未配置 |
| Cutflow 访问同一 NAS 的路径 | 未提供；没有远程运行环境可核查 | 未配置 |
| 服务 token | 已检查文件无对应环境项；未生成或输出凭证 | 未配置 |
| 用户映射、就绪母版 | 未提供 LibTV/Cutflow 账号 UUID、母版 ID | 未核实 |
| 远程部署与访问方式 | 未提供 Cutflow 实际部署目录或远程操作入口 | 未核实 |

检查了 testing `.env`、main 根目录 `.env`、Cutflow 本地审查克隆
`.env`/`.env.local`，以及实际服务 DataRoot 下 `.env`。
testing 文件存在但无交接环境项；main 根目录和 Cutflow 审查克隆的上述
文件不存在；实际服务配置无 NAS/CUTFLOW/BRIDGE 环境项。
当前工具进程环境中也未发现 `CUTFLOW_*` 或 `LIBTV_BRIDGE_*`。
这不能排除其他进程有独立环境覆盖，但未获得这样的配置证据。

`Get-SmbMapping` 未返回映射，文件系统盘符没有网络 DisplayRoot。
`Get-SmbConnection` 返回“拒绝访问”，因此 SMB 会话检查不完整。
**未发现映射不等于 UNC 不可访问**；没有真实路径，尚不能检测 NAS
存在性、读写权限、吞吐或服务账号访问权限。未猜测地址或扫描网段。

## 3. 正式入口实测证据

以下均是本次对正式 LAN 入口执行的只读 HTTP 请求。

| 时间（+08:00） | 请求 | HTTP | 结果 |
| --- | --- | --- | --- |
| 12:17:32.120 | `/` | 200 | 页面可访问 |
| 12:17:32.407 | `/api/v1/health/live` | 200 | `{"status":"ok"}` |
| 12:17:32.597 | `/api/v1/health/ready` | 503 | 通用连接检查项 postgresql=ok；schema outdated，实际类型后续核实为 SQLite |
| 12:18:43.514 | `/api/v1/cutflow-handoffs` | 503 | `MAINTENANCE_QUERY_ONLY` |
| 12:18:43.660 | `/api/v1/system/status` | 200 | `X-LibTV-Maintenance: query-only` |
| 约 12:18 | `/api/v1/auth/me`，无登录凭证 | 401 | 本次未取得用户会话 |

Readiness 响应：

```json
{
  "status": "degraded",
  "checks": {
    "postgresql": "ok",
    "databaseSchema": "outdated"
  },
  "databaseSchema": {
    "currentRevisions": ["e5f6a7b8c901"],
    "expectedRevisions": ["c7d8e9f0a1b2"],
    "missingTables": []
  }
}
```

不能根据该响应宣称缺少交接表；明确观测到的是修订不一致。
交接 GET 返回：

```json
{
  "detail": {
    "code": "MAINTENANCE_QUERY_ONLY",
    "message": "当前仅支持登录和查询已保存任务，生成暂不可用。"
  }
}
```

运行态 `/system/status` 返回 schema revision `e5f6a7b8c901`、
shared authentication `true`、runtime version `0.1.0`；
未返回 `cutflowHandoffEnabled` 字段，不能将字段缺失记成已启用。
sourceRevision 为
`6cf43913fc591a7a48d7d8796fe637af4722ee6e7f43df80ff91a7fc8b7b3d88`，
仅记录接口值，不将其解释为已验证的 Git 提交。

实际 DataRoot 数据目录内以下文件均不存在；该目录不是服务代码目录，
这一事实不能用于判断源码未部署：

```text
backend/src/libtv_agent/api/cutflow_handoffs.py
backend/src/libtv_agent/runner/cutflow_worker.py
backend/alembic/versions/c7d8e9f0a1b2_cutflow_handoffs.py
```

后续注册表核查确认正式服务代码来自 main，上述交接源码在 main 中存在。
当前 query-only 入口不可用；源码在磁盘存在不能证明运行进程已加载它。
本机 Cutflow 审查克隆也不能作为远程 Cutflow 已部署的证据。

## 4. 单用户真实视频指标

下表定义后续同一条视频的计时边界，**目前所有视频阶段均未执行**。
使用各端单调时钟测阶段耗时，同时记录带时区的开始/结束时间。
跨机器总耗时在 LibTV 一端计时；不直接相减未校时的两端时间。
记录文件大小和字节数，测量范围内的校验成本单独说明。

| 指标 | 测量边界 | 实测值 |
| --- | --- | --- |
| 源视频既有上传/下载耗时 | 原生成任务日志中的开始到本地源视频就绪；历史日志缺失则记 N/A | NOT RUN，未选择视频 |
| 上传耗时：LibTV → NAS | 开始复制源视频到 inbox，至目标大小/SHA-256 验证并发布 READY | NOT RUN |
| 传输耗时：NAS → Cutflow SSD | Cutflow 开始读取交接素材，至本地租户输入完整并校验通过 | NOT RUN |
| Cutflow 处理耗时 | 实际分析/分组/剪辑开始，至可提交 render 的编辑结果就绪；不含 render | NOT RUN |
| Render 耗时 | 渲染开始至成片文件生成；独立记录其后 QA 时间 | NOT RUN |
| QA 耗时 | 成片生成至 Cutflow 输出 QA 结论 | NOT RUN |
| 回传 A：Cutflow → NAS | 开始发布输出，至 outbox 成片及 manifest 完整可见 | NOT RUN |
| 回传 B：NAS → LibTV | LibTV 开始读取输出，至复制、hash/媒体/完整解码校验并持久化待审版本 | NOT RUN |
| 回传总等待 | Cutflow 成片通过 QA 至 LibTV 待审版本可预览，含轮询/排队 | NOT RUN |
| 全链总耗时 | LibTV 提交交接至 LibTV 独立剪辑结果可预览 | NOT RUN |
| 排队/轮询等待 | 分开记录各队列等待和结果发现延迟；不并入纯处理耗时 | NOT RUN |

页面/健康请求响应时间不是上述视频上传或传输耗时，不纳入视频指标。
阶段日志若不能区分分析、剪辑、渲染，必须记录“不可分离”，不能估算拆分。

## 5. 文件 Hash 与溯源

| 文件位置/版本 | SHA-256 | 文件大小 | 比对要求 |
| --- | --- | --- | --- |
| LibTV 原 DownloadArtifact | 未采集 | 未采集 | 绑定真实 task/variant/artifact/user ID |
| NAS inbox 输入 | 未采集 | 未采集 | 等于 LibTV 源文件 |
| Cutflow SSD 输入 | 未采集 | 未采集 | 等于 NAS inbox 输入 |
| Cutflow 渲染输出 | 未采集 | 未采集 | 绑定 batch/output/version ID |
| NAS outbox 输出 | 未采集 | 未采集 | 等于对应 Cutflow 输出 |
| LibTV 回传独立版本 | 未采集 | 未采集 | 等于对应 NAS outbox 输出 |
| inbox/outbox manifest | 未采集 | 未采集 | 留存清单版本和实际摘要 |

输入链三处内容一致；输出链三处内容一致。剪辑改变内容，
**不要求源视频与剪辑成片 hash 相同**。
既有补丁文件 hash 不能代替视频 hash。

## 6. 最终人工质量

**PENDING HUMAN REVIEW：没有真实成片，尚无人观看或给出验收结论。**

审核人、审核时间、成片版本均未确定。实际观看后逐项记录：

- 商品颜色、版型、印花和细节是否保持；
- 人物、场景、动作连续性与剪辑节奏；
- 黑帧、卡帧、跳变、裁切和音画同步；
- 字幕、音乐、人声、首尾完整性及母版要求；
- LibTV 内完整播放和下载是否正常；
- 最终结论：通过 / 需返修 / 拒绝，并附具体问题及对应时间码。

技术 QA 通过不能代替人工质量通过；回传版本保留待审语义。

## 7. 发现问题与下一步

1. 缺真实 Cutflow LAN URL、两端 NAS 路径和远程部署访问方式，无法配置或传输。
2. 正式服务为 query-only；当前入口阻断交接操作。
3. 数据库修订未对齐；后续只读查询确认交接表不存在。交接源码已在服务
   注册的 main 代码目录中，DataRoot 下缺少源码不构成部署缺失证据。
4. 缺用户映射、可用母版和已生成真实视频选择，不能创建有依据的单用户任务。
5. 没有阶段实测、视频 hash 或人工质量证据；本次验收不通过。

继续执行所需输入：Cutflow 的完整 LAN URL；LibTV 和 Cutflow 各自访问
同一 NAS 的真实路径；远程操作方式或远程管理员配合；测试用户和一条
已有真实视频；Cutflow 活跃账号及母版选择。
凭证在各端本地安全配置，不写进本报告。

输入齐备后先核实两端部署、服务账号权限、可用模板与真实视频，再按
现有发布流程处理运行部署和 schema 对齐，执行一条交接并补齐上表。
依照 AGENTS.md，源码推广不等于生产迁移或服务重启授权；若涉及这些
操作，先给出具体部署范围、备份/回退方式再取得对应授权。
不通过新增架构、关闭审核或合成输入绕过当前阻塞。

## 8. 修改、验证与源码同步

本轮仅新增本报告，并给 CHANGELOG 添加真实验收阻塞记录。
报告按完成、修改、测试、发现问题、下一步记录本轮工作。
testing 验证后，将同一报告和本轮 changelog 段落局部同步至实际 main；
不复制真实 `.env`、媒体、运行目录或无关并行修改。
两侧文档内容/hash 与差异检查见本轮交付验证；无需为纯文档变更重复
前端 build/lint/浏览器验收。文档同步成功也不改变 BLOCKED 状态。
