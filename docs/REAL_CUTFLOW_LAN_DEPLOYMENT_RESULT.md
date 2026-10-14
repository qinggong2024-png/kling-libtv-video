# REAL CUTFLOW LAN DEPLOYMENT RESULT

日期：2026-10-14。首轮核查：12:28–12:33；真实地址复查：12:52–12:54。
登录态复查：约 14:26–14:31；14:29–14:30 的 HTTP 时刻单独记录。
时区：Asia/Shanghai（UTC+08:00）。
目标：`衣影工坊 → NAS → Cutflow → NAS → 衣影工坊`，单用户真实视频闭环。
边界：衣影工坊负责调度与审核，Cutflow 独立执行剪辑，NAS 交换与归档。

**结果：BLOCKED / PRECHECK FAILED。真实 handoff 提交次数：0。**

本轮仅核查环境并输出文档；未修改架构或业务代码，未填写真实配置、
迁移数据库、重启服务、生成视频、创建剪辑任务或渲染。
收到真实地址后，另按授权创建 NAS test 子目录和一个探测文本文件，
完成本机账号读取/hash/删除测试；测试文件已删除，test 子目录保留。
发现阻塞后仅定位原因，没有继续开发或绕过审核。

最新结果：本机账号访问真实交接目录的单文件测试通过；Cutflow 登录态
界面确认同一 UNC、可列出 test 目录，普通生产服务显示在线。
bridge 根路径 GET/OPTIONS 及无凭证空 POST 探针均返回 HTML 404。
衣影工坊仍为 query-only、readiness 503。bridge worker 和远程写权限
未验证；这些检查不构成真实视频闭环通过，见第 9、10 节。

## 1. 完成：衣影工坊运行环境

| 项目 | 实查结果 |
| --- | --- |
| 正式入口 | `http://192.168.30.126:5173/` |
| API 服务 | `LibTVProductionApi`，Running，PID 130060 |
| API 服务账号 | `NT SERVICE\LibTVProductionApi` |
| 注册的代码入口 | `C:\Users\Reel\Documents\libtv-auto-main-sync\backend\src\libtv_agent\api_windows_service.ApiService` |
| 实际服务代码目录 | `C:\Users\Reel\Documents\libtv-auto-main-sync`，main 工作树 |
| 数据与配置目录 | `F:\Users\Reel\Documents\libtv-production`，来自注册表 Parameters/DataRoot |
| 服务配置文件 | 数据目录下 `.env`，存在 |
| 前端宿主 | `LibTV Frontend Host` 计划任务，Running，账号 SYSTEM，工作目录为 main |
| 本机监听 | `0.0.0.0:5173`；`127.0.0.1:8000` |
| 服务选定配置 | `APP_ENV=development`，`SHARED_AUTHENTICATION_ENABLED=true` |
| 对外 API 模式 | 响应头 `X-LibTV-Maintenance: query-only` |

注册表 PythonClass 与服务入口代码分别确定代码目录和 DataRoot。
**DataRoot 是数据/配置目录，不是源码部署目录。**
该结论纠正上一份 `REAL_CUTFLOW_HANDOFF_ACCEPTANCE.md` 对目录的推断。

main 代码目录中以下文件均存在：

```text
backend/src/libtv_agent/api/cutflow_handoffs.py
backend/src/libtv_agent/services/cutflow_handoff.py
backend/src/libtv_agent/runner/cutflow_worker.py
backend/alembic/versions/c7d8e9f0a1b2_cutflow_handoffs.py
frontend/src/features/production/CutflowControl.tsx
```

main 的 API router 已注册 handoff 路由。因此交接源码已落到服务注册的
代码目录；不能再根据 DataRoot 下没有源码判断“未部署”。
但运行态 `/system/status` 未返回当前源码的 `cutflowHandoffEnabled` 字段，
尚未证明存活进程已加载当前磁盘版本。没有为此重启服务。

## 2. 测试：数据库只读结构核查

服务 DataRoot 的配置使用 `sqlite+aiosqlite`，实际配置文件路径：

```text
F:\Users\Reel\Documents\libtv-production\var\development.db
```

以 SQLite URI `mode=ro` 打开已存在文件，并启用 `PRAGMA query_only=ON`；
只查询 alembic_version、sqlite_master 及列/索引/外键元数据。
未执行 create_all、upgrade、DDL、修订号修改或业务数据写入。

| 检查 | 实测 |
| --- | --- |
| query_only | 1 |
| alembic 当前修订 | `e5f6a7b8c901` |
| main 源码新增修订 | `c7d8e9f0a1b2`，父修订为上述当前版本 |
| `cutflow_handoff` 表 | 不存在 |
| 对应 22 个列 | 全部不存在 |
| 对应索引、唯一约束、外键 | 表不存在，因而没有对应结构 |
| 是否迁移 | 否；按用户要求仅记录差异 |

预期结构包括账号/任务/variant/artifact 关联、源版本幂等约束、
交接状态、输入清单、Cutflow batch、回传版本、租约、退避及时间戳。
实际差异是整张交接表尚未建立，不只是 alembic 修订号落后。
不应直接执行已有 create_table 迁移前跳过备份与部署评估。

健康接口的检查项名字 `postgresql` 返回 `ok`，但这是通用连接检查的标签；
**不能据此判断实际数据库是 PostgreSQL**。本轮以真实配置和只读连接
确认 SQLite，纠正旧报告中的数据库类型推断。
首轮使用 PostgreSQL 专用只读语句探测返回 OperationalError；
识别 SQLite 后改用以上只读方式成功核查，未尝试迁移。

## 3. 测试：正式入口

| 时间（+08:00） | 请求 | HTTP | 实测结论 |
| --- | --- | --- | --- |
| 12:28:01.663 | `/` | 200 | 前端可访问 |
| 12:28:01.922 | `/api/v1/health/live` | 200 | status ok；query-only |
| 12:28:02.056 | `/api/v1/health/ready` | 503 | schema outdated；当前 e5f6a7b8c901，预期 c7d8e9f0a1b2 |
| 12:28:02.219 | `/api/v1/system/status` | 200 | query-only；无 cutflowHandoffEnabled 字段 |
| 12:28:02.352 | `/api/v1/cutflow-handoffs`，GET | 503 | `MAINTENANCE_QUERY_ONLY` |

没有提交 POST handoff。维护模式在正常交接流程前就阻断了 API。
ready 返回 `missingTables=[]` 不等于交接表存在；
该接口本次没有报告它，而本轮直接读取数据库确认该表不存在。

## 4. 首轮测试：NAS 路径与权限

本机工具身份为 `REEL\Reel`，与 API 虚拟服务账号不同。
资源管理器 TypedPaths 历史记录包含以下实际 UNC 共享：

```text
\\192.168.120.60\内容创意部-fb广告成片交付
\\192.168.120.60\新成片交付
```

只读取历史路径与共享根目录属性，没有枚举业务文件内容。

| 检查 | 实测 |
| --- | --- |
| `NAS` DNS 查询 | 未解析到地址 |
| `NAS:445` 连接 | “不知道这样的主机” |
| `\\NAS\creative-handoff` 目录读取 | “找不到网络路径” |
| 发现的 `192.168.120.60:445` | TCP 连接成功 |
| 上述两个历史 UNC 共享根目录 | 获取目录属性成功 |
| `\\192.168.120.60\creative-handoff` | “找不到网络名” |
| `Get-SmbMapping` / `net use` 初始检查 | 无映射记录 |
| `Get-SmbConnection` | 拒绝访问，不能从此核实 SMB 会话 |
| 衣影工坊实际交接 UNC | 首轮未确定；后续用户提供真实路径并通过本机测试，见第 9 节 |
| Cutflow 实际交接 UNC | 后续登录界面确认同一 UNC，见第 10 节 |
| 两端访问同一目录 | Cutflow 列出本机新建 test 子目录；跨端同一文件内容/hash 未验证 |
| API/worker 服务账号读写权限 | 未验证 |

`192.168.120.60` 是有本机历史路径和 SMB 可达证据的 NAS 候选，
尚不能据此证明 Cutflow 也登录了该 NAS。
不使用映射盘符，不用其他业务共享替代用户指定的交接共享。

首轮按用户给出的 `\\NAS\creative-handoff\test` 检查。
父共享当前不可访问；在已发现 NAS IP 上同名共享也不可访问，
因此测试目录未建立。失败可能需要确认真实服务器名、共享名、
SMB 导出方式或账号权限；未擅自创建 NAS 共享。

| 测试动作 | 衣影工坊端 | Cutflow 端 |
| --- | --- | --- |
| 建立 test 目录 | NOT RUN，父共享不可访问 | NOT RUN，未取得远程入口 |
| 创建唯一测试文件 | NOT RUN | NOT RUN |
| 对端读取并核对内容/hash | NOT RUN | NOT RUN |
| 删除本次测试文件 | NOT RUN，没有创建测试文件 | NOT RUN |

根目录属性可访问不能代替文件读写测试。桌面账号已登录也不能代替
服务账号权限证明。共享确认后须在两端真实执行身份下验证同一文件。
只删除本次唯一测试文件，保留既有目录和业务素材。

## 5. Cutflow 节点核查

| 项目 | 状态 |
| --- | --- |
| Cutflow LAN URL / 服务端口 | 后续已提供 `http://192.168.30.35:3001/`；首页 200，见第 9 节 |
| 远程代码目录、版本、部署状态 | 未核实 |
| bridge 启用标志、root、token 是否设置 | 未核实 |
| 活跃 owner 映射、就绪母版 | 登录名 REEL，8 个界面可用母版；owner UUID/归属及映射未核实 |
| bridge worker / 分析剪辑 worker / render worker | 普通 Worker 和三类服务界面显示在线；bridge worker 未核实 |
| 本地 SSD 工作目录及空间 | 未核实 |
| 接收衣影工坊 handoff 的接口 | GET/OPTIONS 和空 POST 配置探针均 HTML 404；未提交有效 handoff |

本机可读取的进程命令行未发现 `libtv_agent.runner.cutflow_worker` 或
`libtv-bridge-worker.mjs`；部分进程命令行不可读，这不证明 worker 已停止，
也不能代替远程 Cutflow 检查。

`E:\Codex\cut-architecture-v2-review` 只是本机源码审查克隆：
bridge 源码存在，只有安全配置示例，没有 `.env`/`.env.local`。
不将其当作远程部署。需核实的既有控制路由为
POST `/api/integrations/libtv` 和 GET
`/api/integrations/libtv/{handoffId}?userId=...`。
不通过构造虚假 handoff 或猜测地址试探远程生产系统。

## 6. 配置准备：人工填写项

以下是填写清单，尚未应用到任何环境；不包含真实 token。

| 端 | 配置项 | 待填写/核实内容 |
| --- | --- | --- |
| 衣影工坊 | `CUTFLOW_BASE_URL` | `http://192.168.30.35:3001` |
| 衣影工坊 | `CUTFLOW_HANDOFF_ROOT` | `\\192.168.120.60\新成片交付\批量剪辑素材`，本机账号测试已通过，服务账号待验证 |
| 衣影工坊 | `CUTFLOW_SERVICE_TOKEN` | 仅在服务本地安全填写，与 Cutflow token 相同 |
| 衣影工坊 | `CUTFLOW_HANDOFF_ENABLED` | 部署/结构/权限齐备后按发布流程启用 |
| Cutflow | `LIBTV_BRIDGE_ROOT` | `\\192.168.120.60\新成片交付\批量剪辑素材`，普通界面已确认；bridge 执行账号读写待验 |
| Cutflow | `LIBTV_BRIDGE_TOKEN` | 仅在服务本地安全填写，不复用生成 API Key |
| Cutflow | `LIBTV_BRIDGE_OWNER_MAP` | 真实 LibTV 用户 UUID → 活跃 Cutflow owner UUID |
| Cutflow | 映射内 `templateId` | 属于该 Cutflow owner 的就绪母版 UUID |
| Cutflow | 映射内 `autoQueue` | 首次导入核实前保持 false，随后由既有剪辑流程启动 |
| Cutflow | `LIBTV_BRIDGE_ENABLED` | 核查通过后按发布流程启用 |

根目录用于保存 `inbox/<handoffId>` 和 `outbox/<handoffId>`。
`test` 是权限验证子目录，不将两端配置成互不相通的临时目录。
真实 `.env`、token、用户素材和运行状态不进入 Git 或同步到另一工作树。
两端路径可使用不同服务器别名，但必须证明确实指向同一文件。

## 7. 一次真实测试记录

**NOT RUN。预检已失败，按停止条件未执行真实测试。**
后续仅使用一个已有真实 AI 视频，不重新生成付费样本。

| 绑定项 | 实际值 |
| --- | --- |
| LibTV user / product / task / variant / artifact | 未选择 |
| Cutflow owner / templateId | 未选择 |
| `handoff_id` | 未创建 |
| Cutflow `batch_id` | 未创建 |
| 独立回传版本 ID | 未创建 |
| 最终人工观看结果 | PENDING HUMAN REVIEW，没有成片可观看 |

| 阶段 | 耗时 | 输入/输出 SHA-256 | 字节大小 |
| --- | --- | --- | --- |
| 已生成视频就绪（复用既有结果） | 未采集，历史日志缺失时记 N/A | 未采集 | 未采集 |
| 继续剪辑 / 创建 handoff | NOT RUN | 清单未创建 | 未采集 |
| 衣影工坊 → NAS inbox 上传及 READY 发布 | NOT RUN | 源文件与 inbox 输入未采集 | 未采集 |
| NAS → Cutflow SSD 导入 | NOT RUN | inbox 与 SSD 输入未采集 | 未采集 |
| Cutflow 分析/分组/剪辑 | NOT RUN | 未采集 | 未采集 |
| Render | NOT RUN | SSD 渲染输出未采集 | 未采集 |
| Cutflow QA | NOT RUN | 未采集 | 未采集 |
| Cutflow → NAS outbox | NOT RUN | SSD 输出与 outbox 输出未采集 | 未采集 |
| NAS → 衣影工坊校验/导入 | NOT RUN | outbox 与本地独立版本未采集 | 未采集 |
| 衣影工坊待审版本预览 | NOT RUN | 未采集 | 未采集 |

执行时记录各阶段本端单调计时及带时区时间，单列排队/轮询延迟和 QA；
Render 与分析剪辑分开。日志不可拆分的阶段明确记“不可分离”。
输入链三处 hash/大小一致，输出链三处 hash/大小一致；
剪辑前后文件不要求同 hash。人工完整观看结果独立于技术 QA。
没有沿用模拟 NAS、合成视频或确定性裁切测试数据。

## 8. 发现问题、修改与下一步

优先阻塞：正式服务为 query-only，交接表不存在。
后续独立阻塞：Cutflow bridge 根路径包括 POST 探针返回 404，远程部署、
bridge worker 和两端服务账号写权限未核实。普通生产服务界面显示在线。
真实 NAS/Cutflow 地址已由用户补齐；登录后的额外证据见第 10 节。

需要人工补齐：

1. 在 Cutflow 实际执行账号及衣影工坊 worker 运行账号下复验真实
   UNC 的读写；当前通过的只是 `REEL\Reel` 本机账号测试。
2. 提供 Cutflow 电脑的远程操作方式或管理员配合入口，核对现有
   bridge 的部署/服务加载与 bridge worker 状态，定位 HTML 404 原因；
   已有网页登录只能完成现有界面核查，不能替代服务器部署访问。
3. 选择一个测试用户、一个产品的已有真实 AI 视频、活跃 Cutflow owner
   和一个就绪母版；token 在两端本地填写。
4. 单独确认后续部署/服务模式应用和数据库迁移的具体范围；
   当前只记录差异，不自动迁移、不解除维护模式或重启。

配置和预检完成后才提交一次真实测试；失败即记录错误与具体阶段，
不追加开发、批次、样本或重新付费生成。

本轮文档修改：新增本报告，更正旧验收报告的目录/数据库类型推断，
更新 CHANGELOG；没有业务代码变更。
在 testing 检查内容与格式后，仅同步这些文档至实际 main 工作树，
比较两侧内容/hash；保留无关并行改动。
文档检查和同步不代表运行部署或真实闭环验收通过。

## 9. 真实地址复查与 NAS 单文件证据

用户提供的地址已记录，UNC 开头按 Windows 标准两个反斜杠规范化：

```text
NAS root: \\192.168.120.60\新成片交付\批量剪辑素材
NAS test: \\192.168.120.60\新成片交付\批量剪辑素材\test
Cutflow:  http://192.168.30.35:3001/
```

没有建立映射盘符，没有将业务共享替换为新的 NAS 服务。
12:52:50 本机以 `REEL\Reel` 成功获取真实根目录属性；
12:53:19 创建此前不存在的 test 子目录。

唯一探测文件：

```text
test/libtv-cutflow-nas-probe-20261014-1253.txt
```

| 检查项 | 实测结果 |
| --- | --- |
| 创建文件 | PASS，NAS 上实际写入一个不含凭证/业务素材的文本文件 |
| 读取 | PASS，12:53:55 读取并核对 run 标识 |
| 文件大小 | 174 bytes |
| SHA-256 | `0A4991126FDDA774120F3A9A8EBE99229281EEFF2D60E61CD4F23E032D86E778` |
| 删除 | PASS，12:54:28 确认唯一探测文件不存在 |
| 留存 | test 子目录保留；未删除既有文件或业务素材 |
| 覆盖身份 | 本机 `REEL\Reel`；不覆盖 API 虚拟服务账号和远程 Cutflow 账号 |
| 对端读取同一文件 | NOT RUN；尚未获得 Cutflow 登录/远程操作入口 |

该 SHA-256 属于 NAS 探测文本，**不是视频输入/输出 hash**。
未将创建到读取之间的工具调用间隔解释为视频传输耗时。

| 时间（+08:00） | 节点/请求 | HTTP | 证据 |
| --- | --- | --- | --- |
| 12:52:50.750 | Cutflow `/`，GET | 200 | 标题 `GC Cutflow · 统一剪辑工作台` |
| 12:52:50.980 | Cutflow `/api/integrations/libtv`，GET | 404 | Content-Type 为 text/html |
| 12:53:18.845 | Cutflow 同路径，OPTIONS | 404 | Content-Type 为 text/html；未返回 Allow |
| 12:53:19.225 | 衣影工坊 `/api/v1/health/ready` | 503 | 当前 e5f6a7b8c901，预期 c7d8e9f0a1b2 |
| 12:53:19.328 | 衣影工坊 `/api/v1/cutflow-handoffs`，GET | 503 | `MAINTENANCE_QUERY_ONLY` |
| 12:53:55.160 | Cutflow `/api/health`，GET | 401 | 要求登录，未获得 worker 健康数据 |
| 12:53:55.507 | Cutflow `/api/nas/directories`，GET | 401 | 要求登录，未获得远程实际 NAS root |
| 12:53:55.651 | Cutflow `/api/auth/me`，GET | 200 | 本次请求无用户会话；bootstrapRequired=false |

本机已完成 bridge 源码的根路由只有 POST；OPTIONS 是无任务写入的路由
可用性检查。两次 HTML 404 表明该入口当前未暴露可用 bridge 路由，
具体是未部署、未加载还是路由/代理差异仍需远程确认；不能仅据此断言
远程磁盘没有补丁。没有发送 POST 或伪造 handoff 来验证。

配置值已整理到第 6 节；真实 `.env` 尚未修改。
token、owner 映射和 templateId 仍待两端本地安全配置与核实。
按停止条件保持真实视频测试 NOT RUN，不追加开发、迁移或重启。

## 10. 已登录 Cutflow：同源 NAS、服务与母版核查

用户在右侧浏览器登录后，使用该现有会话只读核查。
页面登录名为 `REEL`，Private workspace；没有读取或导出 cookie、密码、
token。未登出、创建账户或修改账号权限。

工作台展开“系统状态”后的界面显示：

| 项目 | 页面显示 | 证据边界 |
| --- | --- | --- |
| Worker | 在线 | 普通工作进程状态，不能证明 bridge worker 在线 |
| 分析服务 / 剪辑服务 / 渲染服务 | 均在线；各等待 0、运行 0、失败 0 | 页面健康投影，不证明本次剪辑可完成 |
| 流水线 | V2 Pilot | 当前界面值 |
| Codex | 需要重新连接 | 未执行 reconnect 或付费分析 |
| Model Service / Executor | 未知 / 在线 | 模型可用性尚需核实 |
| 批次 | 0 | 未创建任何批次 |
| 母版库 | 8 个，全部“可直接使用” | 库可见不等于属于当前 bridge 映射账号 |

打开“新建批次”只检查已有控件，未改字段或点击提交：
固定素材根目录为
`\\192.168.120.60\新成片交付\批量剪辑素材`。
一级目录选择框列出 `暗黑`、`GC`、`test`、`TT`。
这补充证明 Cutflow 的现有 NAS 功能能够读取用户指定根目录，
并能看到本机新建的 test 子目录；不证明远程写权限或跨端文件 hash。
没有点击“检查并扫描”或“创建批次并识别产品”，退出后批次仍为 0，
浏览器留在已登录工作台。

读取已渲染母版下拉框的候选 ID：

| 母版名称 | templateId |
| --- | --- |
| AI ootd | `1527e301-7707-449d-8e7c-d27014080c8d` |
| 泛读书 | `d43bdcb3-ce10-4a72-b9b1-c956e7abb1c5` |
| 暗黑 | `798ecfce-3b48-4009-932e-58327bc9e529` |
| AI 开箱 | `2318ccb7-a729-495c-8d0c-ea3b30de2236` |
| 街头服装 13秒母版 | `bbe0234c-3efd-4fb9-8106-6e1d9da62432` |
| 纯展 | `7e3ed86b-5a92-450f-aa69-d9c9d89baaa0` |
| 健身房 | `fd6de53e-cc3a-41a3-ba6b-9947c559af9e` |
| GC街头服装 · 13秒样片母版 | `50417cee-bc5f-42a3-953c-da41e85427e9` |

AI ootd 是表单默认值，本次没有将其选定为验收母版。
页面说明母版库是登录账号共享可见；现有 bridge 要求 template 属于映射
owner 且 ready，因此仍须核对 owner UUID、母版归属及视频覆盖是否相容。
不根据默认选中、8 个可用母版或登录名推断映射已经配置完成。

浏览器访问 `/api/nas/directories` 的直接导航被客户端阻止，
未绕过限制；改从正常新建批次界面读取 NAS 信息。
会话不等于远程 shell 或服务配置权限。

为区分方法不匹配与实际 bridge 路由不可用，另以终端发送一次空 POST
`{}`，没有 Authorization、userId、manifest 或素材。
现有 bridge 源码先校验配置/凭证与 descriptor，此空请求不是有效交接，
不具备创建任务参数。实测：

| 时间（+08:00） | 请求 | HTTP | 结果 |
| --- | --- | --- | --- |
| 14:29:10.198 | Cutflow POST `/api/integrations/libtv`，空配置探针 | 404 | text/html，Next.js 404 页面；未返回 bridge 的 JSON 401/409 |
| 14:30:55.895 | 衣影工坊 `/api/v1/health/ready` | 503 | 当前 e5f6a7b8c901，预期已为 c8e9f0a1b2c3 |
| 14:30:56.284 | 衣影工坊 GET `/api/v1/cutflow-handoffs` | 503 | MAINTENANCE_QUERY_ONLY |

空 POST 仅为路由诊断，不计入真实 handoff 提交次数；未得到 batch_id。
HTML 404 仍需远程区分部署、运行构建或代理原因。
源码新增 AI 风险额度迁移后，当前预期 head 已变化；第 2、3、9 节的
c7d8e9f0a1b2 为对应核查时刻记录，不是本次最新 head。
不能不评估新增迁移就执行全量 upgrade；本轮按用户要求没有迁移。

当前真实视频测试仍为 NOT RUN。只更新报告和 CHANGELOG 并局部同步
main；未安装 bridge、改业务代码、填 token、重启或修复 Codex 连接。

## 11. 单次发送部署包准备

用户要求形成可一次发送的完整执行入口。本轮仅增加部署交付脚本与指令，
不修改 Bridge 业务功能，不执行两端迁移、配置或重启。
完整操作范围和停止条件见 `CUTFLOW_ONE_MESSAGE_DEPLOYMENT.md`。

NAS 包目录：

```text
\\192.168.120.60\新成片交付\批量剪辑素材\test\cutflow-bridge-deployment-20261014
```

`scripts/package-cutflow-bridge.ps1` 从已完成审查克隆机械复制 8 个指定文件，
保留完整补丁、部署指令、报告和哈希清单；不会包含账号、真实配置或媒体。
输出目录已存在时拒绝覆盖。其创建部署包操作不是安装 Cutflow。

本轮验证：PowerShell 语法检查通过；既有 bridge 离线测试 6/6 通过。
NAS 包已生成，8 个 payload hash/大小及全部 12 个文件白名单检查通过；
重复生成时正确拒绝覆盖，manifest hash 未变化。
manifest SHA-256：
`B300B158462A2196C36CC4591F170FA044CD16E08686930E8ED6BD76B5260ECE`。
局部同步脚本/文档至 main，并核对双方文件一致。
这些离线测试不计入真实视频验收，单次真实 handoff 次数仍为 0。

远端收到指令后，核查实际目录/托管方式、应用已有文件、配置私有环境并验证
服务；无法构建、映射不明或凭证缺失时报告具体阶段，不自行开发或伪造批次。
衣影工坊迁移和维护模式应用仍须另行批准具体范围。
人工观看也无法由自动命令代替；不能承诺一次发送必然完成真实视频闭环。
