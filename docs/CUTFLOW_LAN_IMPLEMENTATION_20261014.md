# LibTV → Cutflow 局域网交接

日期：2026-10-14。当前为默认关闭的源码交付，未在真实 NAS 或远程电脑部署。

## 部署形态

```text
5–10 位用户 → LibTV 网页/API → 数据库交接队列
                               ↓ 独立传输进程
                  NAS / inbox / 交接编号 / 素材与清单
                               ↓
          Cutflow 接收队列 → 本机 SSD → 原有分析/剪辑/渲染/QA
                               ↓
                  NAS / outbox / 交接编号 / 版本成片
                               ↓ 主动查询与校验
              LibTV 独立剪辑版本 → 预览/下载 → 人工审核
```

网页创建交接仅写数据库，返回 202；不在请求中复制视频或执行 FFmpeg。
两边各启动一个传输进程，每个进程串行处理文件。剪辑电脑使用本地租户
目录保存输入和输出，渲染时不跨 NAS 读取原视频。NAS 保存交接包和归档，
两边的挂载名/盘符可以不同。控制 API 不承载视频、不接收任意绝对文件路径。

这能分离本机生成与远程渲染负载，但不是 5–10 人无卡顿的性能保证。
首次上线从一个 render worker 开始，保留现有 analyze/clip/render 任务队列；
观察 CPU、内存、SSD、NAS 吞吐和排队时间后再增加并发。不要同时启动旧
全功能 worker 和重复的分阶段 worker 处理同一队列。大文件传输、校验仍
消耗本机 I/O；保留原有下载/校验并发设置，不因用户人数直接开十路渲染。

## 已实现边界

- 每次交接一个已生成、已下载、技术通过或 WARNING 的视频结果。
  已标识的 fake/replay/offline/synthetic 素材禁止送入剪辑生产。
- 按用户和源文件版本幂等；10 个并发创建请求只得到一个交接。
  新源文件版本可创建新交接，剪辑返修在原 Cutflow 批次内完成。
- 先提交数据库记录，再由进程复制素材；校验源及目标 SHA-256、大小上限，
  清单原子写入后最后发布 READY。租约和短事务支持进程中断后恢复。
- Cutflow 控制接口仅校验凭证和持久化接收记录，独立 worker 复制到 SSD，
  利用原有文件锁创建一个租户批次；响应丢失重试不会重复创建。
- 明确映射 LibTV 用户到 Cutflow 活跃账号，拒绝客户端指定 Cutflow owner。
  不自动创建用户，不把所有人的素材塞入一个共享账户。
- 可预先为映射配置已就绪母版及 autoQueue；未配置母版时停在 uploading，
  在 Cutflow 内补样片等必要配置后继续。仍执行既有分组、素材和渲染 QA。
- 只回传 Cutflow 标记 qualityStatus=passed 的输出，输出按文件 ID 和哈希
  形成不可变版本；LibTV 再验证文件完整性、视频流、时长及完整解码。
- 回传独立保存，不增加原 DownloadArtifact 的修订、不继承原视频批准。
  页面显示“剪辑版本待审核”，允许预览和下载；尚不提供独立剪辑版本
  的正式批准/交付 API，不把下载当成交付。
- 本机主动查询结果，默认 15 秒；无需 Cutflow 向本机开放回调连接。
  传输/网络失败有退避，连续五次失败转人工重试。

一个生成视频不一定满足 Cutflow 母版的多镜头覆盖要求；不足时保留失败/
待配置状态，不能复制镜头或伪造五种角色来“凑通过”。本期没有多结果
合并成单个剪辑任务的编排，也没有重写母版、Scheduler 或交付引擎。

## 配置与启用顺序

先准备：Cutflow 地址、两台电脑访问同一 NAS 的路径、现有 Cutflow 账号 UUID、
必要的母版 ID。Web 服务和后台任务可能以不同 Windows 账号运行，均须有
共享目录权限；使用 UNC 路径，后台服务不要依赖交互登录映射的盘符。

1. 审阅本次源码并备份数据库。获准部署后，在 LibTV 所用数据库执行迁移，
   新增 head `c7d8e9f0a1b2`，父版本 `e5f6a7b8c901`。本次未执行生产迁移。
2. 将配套 Cutflow 补丁安装到远程实际仓库；核对远程版本和已有差异，
   不覆盖远程 data、storage、用户账号、运行配置或 Provider 凭证。
3. 两端配置下列环境项，服务 token 使用同一个新生成的随机凭证，
   与生成模型 API Key 分开。只在服务器保存，不写入 Git/浏览器。
4. 按已有发布流程启动相应 API 与后台进程；本次没有重启任何正式服务。
5. 一位用户、一条真实已生成视频试运行：发送→导入→配置/剪辑→QA→回传→预览。
   验证刷新、断网恢复和用户隔离后，再扩大到 5–10 位用户并测量负载。

LibTV 服务器真实环境文件配置项：

```dotenv
CUTFLOW_HANDOFF_ENABLED=true
CUTFLOW_HANDOFF_ROOT=\\NAS\media\libtv-cutflow
CUTFLOW_BASE_URL=http://CUT_COMPUTER_IP:3001
CUTFLOW_SERVICE_TOKEN=REPLACE_LOCALLY
CUTFLOW_REQUEST_TIMEOUT_SECONDS=15
CUTFLOW_POLL_SECONDS=15
CUTFLOW_MAX_MEDIA_BYTES=2147483648
```

从 LibTV 仓库运行独立进程（使用与 API 同一数据库/对象存储配置）：

```powershell
$env:PYTHONPATH = (Resolve-Path backend/src).Path
uv run python -m libtv_agent.runner.cutflow_worker
```

Cutflow `.env.local` 或服务环境：

```dotenv
LIBTV_BRIDGE_ENABLED=true
LIBTV_BRIDGE_ROOT=\\NAS\media\libtv-cutflow
LIBTV_BRIDGE_TOKEN=REPLACE_LOCALLY
LIBTV_BRIDGE_OWNER_MAP={"LIBTV_USER_UUID":{"ownerId":"CUTFLOW_OWNER_UUID","templateId":"READY_TEMPLATE_UUID","autoQueue":false}}
LIBTV_BRIDGE_MAX_MEDIA_BYTES=2147483648
```

初次先关闭 autoQueue，确认母版和输入适配后再为该映射打开。
没有母版时删除 templateId 字段，默认保留在 Cutflow 待配置状态。
Next.js 读取服务环境，Node worker 显式加载同一环境文件：

```powershell
node --env-file=.env.local worker/libtv-bridge-worker.mjs
```

## 使用与恢复

启用后，LibTV 视频结果卡或任务记录卡出现“继续剪辑”；展开后可发送、
读取持久化状态、重试交接、打开 Cutflow，并预览/下载独立的剪辑版本。
打开 Cutflow 使用现有首页，页面同时显示批次 UUID 供定位；
Cutflow 尚无经验证的单批次深链接。

交接重试只恢复传输/对账。剪辑或素材质量失败仍通过 Cutflow 原有配置、
返修/重新排队入口处理。取消在 Cutflow 原入口操作，本机下一次查询同步；
本期没有本机远程取消按钮。更改 owner 映射前应完成已有任务，避免旧批次
与新账号不一致。返回的是“待审核成片”，正式交付仍须人工另行确认。

停止接收新任务：关闭 LibTV 的 CUTFLOW_HANDOFF_ENABLED 并按发布流程应用；
处理完已有任务后停传输进程。不要删 inbox/outbox/数据库记录作为重试。
文件保留清理由运营按数据库记录和归档策略处理，本期不自动清理 NAS。

## 验证限制

隔离测试使用临时 SQLite、本地目录模拟 NAS，以及 FFmpeg 合成视频；
双仓库测试用确定性 FFmpeg 裁切替代真实 AI 剪辑，验证 HTTP、清单、复制、
哈希、回传和独立版本语义，不证明真实母版质量或网络吞吐。

浏览器检查覆盖 390/1280px、默认关闭、提交一次、刷新恢复、失败重试、
待审版本、可解码预览、Escape 和只读账号；证据在 Sprint Report。
真实远程版本、共享权限、渲染硬件容量、十人负载和成片人工质量尚待验收。
