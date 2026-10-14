# Runtime Smoke Validation Report

日期：2026-10-13  
时区：Asia/Shanghai  
范围：只读运行态审查，目标是定位页面无法打开的 Blocking 问题  
审查时间：2026-10-13 17:49–17:51

## 1. Environment

```makefile
branch: codex/testing
audit_start_commit: 199a9031d18d68604533300d16668e1fc3b6871e
path: E:\Projects\libtv自动化生成
```

审查开始时工作区存在未提交修改：

- 6 个已修改的 Director Studio 文件；
- 1 个未跟踪 ZIP：`衣影工坊-codex-testing-20261008.zip`。

这些既有修改和未跟踪文件未被本次审查触碰。当前报告是本次唯一新增文件。

审查结束后的最终复核观察到一个非本任务创建的外部提交：

```makefile
post_audit_commit: 8524b895798cae86063952b905a9f508614e84b9
post_audit_subject: fix: clarify director decision card sources and mobile selection
post_audit_time: 2026-10-13 17:52:15 +08:00
```

该提交使前述 6 个 Director 文件不再显示为未提交修改；本任务没有创建、修改或回滚该提交。最终 testing 工作树仍保留未跟踪报告和原有 ZIP。

本次未读取根目录真实 `.env` 内容。该文件被 `.gitignore` 忽略；报告只记录代码、示例配置、进程和 HTTP 观测结果。

## 2. Frontend

```makefile
status: BLOCKED
port: 5173
command: cd frontend; npm run dev
problem: 5173 当前没有稳定可用的本工作区前端；目标访问连接被拒绝
```

静态配置：

- `frontend/package.json` 的开发命令是 `vite`。
- `frontend/vite.config.ts` 默认 host 为 `127.0.0.1`，开发端口为 `5173`，并设置 `strictPort: true`。
- Vite preview 端口为 `4173`。
- `/api` proxy 默认目标为 `http://127.0.0.1:8000`。
- `frontend/` 下没有 `.env*` 文件，因此没有发现前端目录级 `VITE_API_PROXY` 覆盖。

运行态观测：

- `http://127.0.0.1:5173/`：连接被拒绝。
- `http://localhost:5173/`：连接被拒绝。
- 浏览器访问 `http://127.0.0.1:5173/`：`net::ERR_CONNECTION_REFUSED`。
- `5174`、`4173`：未监听。
- `5175` 有一个来自当前 `frontend` 目录的 Vite 进程，页面返回 HTTP 200。
- 浏览器访问 `http://127.0.0.1:5175/` 可以显示页面，但页面显示“服务连接异常”和 `502 Bad Gateway`；模板和站点风格停留在加载状态。

`5175` 是测试栈脚本的默认前端端口，不是本项目规定的正式入口 `5173`。`scripts/start-test-stack.ps1` 同时将测试 API 默认设为 `8001`；本次检查中 `8001` 也未监听。

检查脚本在 17:49:52 曾短暂观察到 `5173` 被 PID `174768` 的外部 Node 进程占用，进程路径为 `D:\New Folder\node.exe`，工作区归属判定为失败；17:51:21 的最终快照中该端口已不再监听。因此不能把该短暂进程视为本项目的可用前端服务。

## 3. Backend

```makefile
status: BLOCKED
port: 8000
command: uv run uvicorn libtv_agent.app:create_app --factory --app-dir backend/src
host: 127.0.0.1
problem: 8000 未监听，健康接口无法访问
```

静态配置：

- `backend/src/libtv_agent/config.py` 默认 `app_host=127.0.0.1`、`app_port=8000`。
- `scripts/start-local-api.ps1` 使用 `uv run uvicorn libtv_agent.app:create_app --factory --app-dir backend/src` 启动本地 API。
- Windows 服务入口 `backend/src/libtv_agent/api_windows_service.py` 也配置为 `127.0.0.1:8000`，但该服务需要 Windows 服务环境和 `pywin32`。
- 根目录 `pyproject.toml` 要求 Python `>=3.11,<3.12`，核心依赖包括 FastAPI、Uvicorn、Pydantic Settings、SQLAlchemy async、asyncpg、Alembic 和 MinIO。
- 默认数据库配置是 PostgreSQL；本地测试栈脚本会显式切换到隔离 SQLite 和测试端口。
- 后端运行依赖 `DATABASE_URL`、对象存储配置、认证/Session 配置及相应运行时文件；本次未读取真实值。

服务观测：

- `8000`：未监听。
- `8001`：未监听。
- `8002`：未监听。
- 相关 LibTV API Windows 服务未发现运行中的服务。
- `scripts/check-local-services.ps1 -RequireFrontend` 返回 `FAIL`。
- 该只读脚本报告 Runner 服务未安装，本地 Runner 数量为 `0`。

只读数据库检查同时报告：

```text
current migration revision: c9f0a1b2c304
expected migration head:    e5f6a7b8c901
```

这表示当前诊断所访问的本地数据库 schema 落后于代码 head。该检查没有执行迁移。

## 4. API

### Health endpoints

```makefile
endpoint: /api/v1/health/live
status: NOT_REACHABLE
response: 127.0.0.1:8000 连接被拒绝
```

```makefile
endpoint: /api/v1/health/ready
status: NOT_REACHABLE
response: 127.0.0.1:8000 连接被拒绝
```

代码中健康路由为：

- `/api/v1/health/live`：进程存活检查。
- `/api/v1/health/ready`：执行数据库连接和 schema 检查；数据库不可用或 schema 落后时应返回 HTTP 503。

前端代理实际观测：

```makefile
endpoint: http://127.0.0.1:5175/api/v1/health/live
status: 502
response: Bad Gateway
```

```makefile
endpoint: http://127.0.0.1:5175/api/v1/health/ready
status: 502
response: Bad Gateway
```

`http://127.0.0.1:5175/api/v1/system/status` 和
`http://127.0.0.1:5175/api/v1/creative-workflow/tasks` 也返回 HTTP 502。

因此当前链路为：

```text
Browser → 5175 Frontend: 可达
5175 Frontend → Backend: 502
Backend 8000: 未监听
```

目标链路 `Browser → 5173 Frontend → 8000 Backend` 当前无法建立。

### CORS and proxy

- 前端通过同源 `/api/v1/...` 请求 API，Vite 负责 `/api` proxy。
- 默认 proxy target 是 `http://127.0.0.1:8000`。
- 后端默认公开 origin 是 `http://localhost:5173`。
- Windows 服务入口允许的正式 origin 是 `http://192.168.30.126:5173`。
- 测试栈脚本会按测试端口注入 `APP_PUBLIC_ORIGINS` 和 `VITE_API_PROXY`。

当前 502 的直接原因是后端没有可用监听；CORS 尚未成为本次实际失败点。服务恢复后仍需确认访问地址、前端端口、proxy target 和 `APP_PUBLIC_ORIGINS` 属于同一运行 profile。

### Director main flow

静态合同和路径匹配正常：

```text
Director Studio
  → /api/v1/products
  → /api/v1/creative-workflow/tasks
  → /api/v1/creative-workflow/tasks/{task_id}
  → /api/v1/creative-workflow/tasks/{task_id}/commands
  → Creative Package / Image / Video handoff
```

证据：

- `frontend/src/features/director-studio/directorApi.ts` 通过 `/api/v1` 前缀调用 `/products` 和 `/creative-workflow/tasks...`。
- 后端 `api/router.py` 将 products 和 creative-workflow router 挂载在 `/api/v1` 下。
- `openapi.yaml` 中存在上述路径。

运行态 404 尚不能判定，因为后端未启动；当前请求在到达路由前已被前端 proxy 返回 502。

## 5. Blocking Issues

### P0

1. **后端 8000 未启动。** `/api/v1/health/live` 和 `/api/v1/health/ready` 均无法连接，导致前端 `/api` proxy 返回 502，页面无法完成初始化。
2. **规定的前端 5173 不可用。** 5173 最终快照未监听，浏览器访问直接 `ERR_CONNECTION_REFUSED`。现存 5175 页面不能替代规定的 5173 运行入口。

### P1

1. **运行 profile 和端口没有成对启动。** 观测到 5175 前端，但 8001 测试 API和 8000 默认 API 都没有监听。
2. **数据库 schema 落后于当前代码 head。** 只读检查报告 `c9f0a1b2c304` 对比 `e5f6a7b8c901`。后端启动后，`/ready` 可能因 schema outdated 返回 503。
3. **后端服务运行状态不明确。** 未发现 API Windows 服务运行，未发现本地 Runner；无法证明服务是从当前 testing 工作树启动的。

### P2

1. **前端目录没有 `.env*`。** 在没有进程级环境变量覆盖时，Vite 会使用默认 proxy `127.0.0.1:8000`；测试栈则需要显式使用 `8001`。
2. **CORS origin 随运行 profile 改变。** `localhost:5173`、`127.0.0.1:<test-port>` 和正式局域网地址必须与实际访问入口一致。
3. **真实环境变量和外部依赖未核实。** 真实 `.env`、PostgreSQL/MinIO、Provider 凭据和服务日志未在本次报告中读取或修改。

## 6. Recommended Fix Order

1. 先确定本次要运行的 profile：标准 testing 本地链路使用 `5173 → 8000`，隔离测试栈使用脚本声明的 `5175 → 8001`；不要混用端口。
2. 在确认启动目录、环境变量和进程归属后启动对应后端，先验证 `/api/v1/health/live`，再验证 `/api/v1/health/ready`。
3. 按批准的数据库流程处理 schema revision 差异，完成后重新验证 `/ready`；本次没有执行迁移。
4. 启动与后端同一 profile 的 Vite 前端，验证首页 HTTP 200 和 `/api/v1/health/ready` proxy 返回。
5. 通过浏览器重新打开目标入口，确认服务连接状态、模板/站点风格加载和系统状态请求。
6. 在健康检查通过后，再做 Director Studio 的只读路径检查；本次不触发分析、生成、付费提交、审核写入或交付。

## Scope and Limitations

本次只做运行态和静态路径审查，未执行以下操作：

- 未修改代码、配置、环境变量或数据库；
- 未启动、停止、重启服务；
- 未执行数据库迁移；
- 未调用 Provider、AI 生成、计费、审核或交付；
- 未提交 commit；
- 未修复任何 Blocking 问题。

结论：当前系统未通过 Runtime Smoke Validation。最先需要处理的是 **后端 8000 未监听** 与 **前端 5173 不可访问**；在这两个问题解决前，Creative Pipeline 和 Director 主流程无法获得有效运行态证据。
