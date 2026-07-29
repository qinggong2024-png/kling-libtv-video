# 受控 MVP 运维 Runbook

本文仅覆盖第二阶段 1–2 名用户的受控 MVP。禁止公网暴露、Funnel、Exit Node、全局 16/20、多主机 Runner 和 WARNING 自动确认。

## 1. 环境与发布

每个环境从对应模板创建本地文件，真实 Secret 只写入 `.env.development`、`.env.staging` 或 `.env.production`，不得提交：

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\validate-environment-isolation.ps1 -UseLocalFiles
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\environment.ps1 -Environment staging -Action Up
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\environment.ps1 -Environment staging -Action Migrate
```

PostgreSQL、MinIO 和 MinIO Console 默认仅绑定 `127.0.0.1`。若改为私网地址，发布前用 Windows Firewall 明确限定来源网段；不得绑定公网接口。

发布门禁：

1. `scripts/check.ps1` 全绿。
2. `scripts/verify-online.ps1` 状态为 `PASS`，API readiness 为 200。
3. LibTV 只读 canary 通过，CLI 必须为 1.1.1。
4. Runner Service 为 Running，command-host 目录 ACL 仅允许 SYSTEM、Administrators 和服务账号。
5. `paidSubmissionsPaused=true`，真实调用集中授权尚未获得时不得解除。
6. `autoConfirmLevels` 必须严格等于 `["PASS"]`。

## 2. Windows Runner

管理员 PowerShell：

```powershell
uv sync --extra dev --extra windows-runner
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\install-runner-service.ps1 -Action Preflight
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\install-runner-service.ps1 -Action Install
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\install-runner-service.ps1 -Action Start
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\install-runner-service.ps1 -Action Status
```

`Preflight` 不需要管理员权限，也不会修改服务、ACL 或运行状态。安装脚本将服务固定配置为 `NT SERVICE\LibTVProductionRunner`，设置 Automatic 启动和三段 SCM 自动重启，并输出 ACL。Service 重启或主机重启后，只按 manifest 中的 commandId、nonce、PID 创建时间、可执行文件 Hash 和命令 Hash 观察原 command-host。身份不匹配、终态文件 nonce 不匹配、PID 消失或主机重启均不得重新提交，进入 UNKNOWN/审计。

验证顺序：启动 Service，运行无付费 command-host 恢复测试，重启 Service，确认原 PID 仍被识别为 RUNNING；再重启 Windows，确认丢失的已启动进程进入 UNKNOWN。日志盘低于 warning 阈值告警，低于 stop 阈值自动暂停新领取和付费确认。

## 3. 停止

1. 在 Operations 页面先启用 `PAID_SUBMISSIONS` 暂停。
2. 再启用 `GLOBAL` 暂停，停止领取新 generation command。
3. 不终止已经运行的 `libtv node --run`；继续观察 command-host、下载和只读对账。
4. 等待 RUNNING 收敛；UNKNOWN 保持积分 UNCERTAIN。
5. 需要维护时再停止 Runner Service、API/Worker，最后停止 MinIO/PostgreSQL。

任何真实异常均先执行以上 1–2 步。不得通过杀进程后自动重提来恢复吞吐。

## 4. 恢复

1. 先恢复 PostgreSQL、MinIO，执行 readiness 和迁移检查。
2. 启动 API/Worker，再启动 Runner Service。
3. 核对 Runner heartbeat、孤儿进程、磁盘、UNKNOWN、积分 UNCERTAIN 和隔离画布。
4. 保持付费暂停，先解除 GLOBAL 暂停并观察查询/下载/对账。
5. 仅在 UNKNOWN 收敛、余额能力可用、无 P0/P1 且获得付费授权后解除付费暂停。

## 5. UNKNOWN 对账

1. 记录 attemptId、projectUuid、videoNodeKey、taskId、intentHash、commandId、nonce 和积分预占。
2. 仅通过官方 LibTV CLI Adapter 读取 node taskInfo、远程状态、视频 URL、poster、输出节点和 taskId。
3. 可确认时归类 RUNNING、SUCCEEDED 或 FAILED_TERMINAL，并更新可归属的扣费证据。
4. 无可归属扣费证据时 `chargeStatus=UNKNOWN`、积分 `UNCERTAIN`，禁止释放。
5. 连续只读对账仍不明确时转人工；禁止自动创建替代 attempt。
6. 原 attempt 明确终态、NOT_CHARGED、原 node 无活动/成功结果且用户重新发起时，才允许用新 idempotency key、node 和 intent version 创建新 attempt。

同时存在 2 条 UNKNOWN 或 UNKNOWN 占全局生成槽超过 10% 时为 P0，系统自动冻结新付费提交。

## 6. 回滚

运行配置回滚不会覆盖历史版本，而是创建新版本并写审计。Operations API 使用当前版本 CAS 回滚到目标版本。应用回滚使用上一个已验证构建产物；数据库迁移默认向前修复，只有演练确认无数据损失时才执行 Alembic downgrade。

回滚后保持 `paidSubmissionsPaused=true`，执行 readiness、SSE、Runner heartbeat、对象下载和 UNKNOWN 核对后再决定恢复。

## 7. 备份与恢复演练

每日备份 PostgreSQL 自定义格式 dump、`.env` 所引用的 Secret 版本号（不备份 Secret 明文）、MinIO 数据卷快照和运行配置/审计。备份写入 `var/backups` 或受控备份盘，不进入 Git。

恢复演练必须在独立 Compose project 和独立对象前缀完成：恢复数据库，恢复 MinIO 快照，运行 Alembic，校验 artifact Hash、签名 URL、积分账本、审计和 remote restore 记录。恢复环境不得绑定生产 LibTV workspace/project。

执行入口：

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\backup.ps1 -Environment production -ComposeProjectName libtv-production-agent
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\restore-drill.ps1 -BackupDirectory .\var\backups\production-YYYYMMDDTHHMMSSZ
```

`backup.ps1` 生成 PostgreSQL custom dump、MinIO 逻辑镜像和逐文件 SHA-256 manifest，不写入 Secret 明文。`restore-drill.ps1` 只接受 `libtv-restore-drill-*` Compose project，强制 Fake AI/LibTV、独立端口/目录/对象前缀和 `paidSubmissionsPaused=true`；Docker 不可用或任一恢复校验未完成时报告必须为 `BLOCKED/FAIL`，不得视为通过。

## 8. Canary 与扩容

付费授权后严格执行：真实 OpenAI 1 套素材且 LibTV Fake；再 1 用户、1 父任务、Stable/Dynamic 各 1 条、同画布/全局均为 1。之后同画布 1→2→4、全局逐级到 12。每级必须无 P0/P1、重复提交、跨任务连接和未收敛 UNKNOWN。

30 套/60 条/4 小时和真实指标只能由报告中的真实证据计算，禁止用 Fake/Replay 结果代替。
