# 第二阶段机器证据口径

本文件只适用于第二阶段“受控 MVP 收口”。它不授权进入第三、第四阶段，也不授权任何 OpenAI 或 LibTV 付费操作。

## 证据边界

- `scripts/collect_phase2_evidence.py` 只把当前 `deploymentId`、`libtvAdapterMode=real` 且由 `WINDOWS_COMMAND_HOST` 启动的记录计入真实平台指标。
- Fake/Replay、暂停期间、其他部署和无 Runner 启动证据的数据不得进入 30 套、60 条、4 小时或正式指标。
- Runner 每个轮询周期写入 `operational_metric_sample`，固化宿主、时间、部署、Adapter 模式、积压、运行数、槽位、暂停状态、孤儿进程和磁盘余量。
- readiness 只能读取 `var/reports` 中的机器报告、数据库证据和 Git 命令输出；跳过、缺失或不可用均不得记为 PASS。

## 计算口径

- 持续运行小时：按同一 Runner 排序心跳。全局暂停、付费暂停或相邻间隔大于 `max(30 秒, 3 * RUNNER_POLL_SECONDS)` 时切断，取最长连续区间。
- 有积压槽位利用率：仅计算有效连续区间中起始样本 `backlogCount > 0` 的时段，按区间秒数对 `slotUtilization` 加权。
- 低风险自动完成率：分母是 PASS 且至少有一次真实 `WINDOWS_COMMAND_HOST` 启动的父任务；分子还必须同时存在 `AUTO_CONFIRM_TASK` 审计并最终进入 `DELIVERABLE`。
- 重复正式生成、跨任务连线和 Runner 孤儿进程分别从已启动 intent 分组、引用关系连接查询和 manifest/本机进程表核对计算。

## 完成门槛

readiness 必须同时满足：1–2 名真实用户、至少 30 套真实父任务、Stable/Dynamic 各至少 30 条且总计至少 60 条、同画布并发 4、全局并发 12、连续运行至少 4 小时，以及正式方案第 36.3 节全部指标。

Docker 不可用时 PostgreSQL/MinIO 在线验收和独立恢复演练保持 `BLOCKED`。LibTV CLI 无法提供余额证据时保持外部阻塞，禁止通过网页、私有 HTTP 或手填数据伪造通过。

所有无付费门禁通过后才提出一次集中付费授权。授权必须明确模型、OpenAI 请求数、视频数、Stable/Dynamic 数量、积分上限、素材、用户、时间窗口、停止条件和回滚方式。
