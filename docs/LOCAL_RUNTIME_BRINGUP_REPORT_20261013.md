# Local Runtime Bring-up Report

日期：2026-10-13  
时区：Asia/Shanghai  
范围：Sprint 6.5 Local Runtime Bring-up  
目标：验证已有代码能否按标准开发 profile 启动并访问

## 1. Runtime Profile

本次选择标准开发 profile：

```yaml
frontend:
  host: 127.0.0.1
  port: 5173
backend:
  host: 127.0.0.1
  port: 8000
api_proxy: http://127.0.0.1:8000
```

实际执行的启动命令：

```powershell
# Backend
.venv\Scripts\python.exe -m uvicorn libtv_agent.app:create_app `
  --factory --app-dir backend/src `
  --host 127.0.0.1 --port 8000

# Frontend
npm.cmd run dev --prefix frontend -- `
  --host 127.0.0.1 --port 5173 --strictPort
```

仓库已有的 `scripts/start-local-api.ps1` 本次没有使用，因为该脚本会自动执行：

```text
uv run alembic -c backend/alembic.ini upgrade head
```

这与本次“只分析数据库 revision、不自动迁移”的约束冲突。

环境要求来自项目配置：

- Python `>=3.11,<3.12`；
- Uvicorn、FastAPI、Pydantic Settings；
- SQLAlchemy async、asyncpg、Alembic；
- `DATABASE_URL`；
- 对象存储配置；
- Session、认证和公开 origin 配置；
- Provider 配置由现有 `.env` 和运行时配置文件提供，本次未输出任何密钥值。

## 2. Environment

```makefile
branch: codex/testing
commit: 8524b895798cae86063952b905a9f508614e84b9
path: E:\Projects\libtv自动化生成
```

当前工作区存在外部未提交修改，未由本次任务创建或修改：

- `frontend/src/features/director-studio/DirectorStudio.browser-check.mjs`
- `frontend/src/features/director-studio/DirectorStudio.tsx`
- `frontend/src/features/director-studio/contracts.ts`
- `frontend/src/features/director-studio/directorAdapters.ts`
- `frontend/src/features/director-studio/directorModel.ts`
- `frontend/src/features/director-studio/directorRecovery.test.ts`
- `frontend/src/features/director-studio/directorRecovery.ts`
- `frontend/src/features/director-studio/directorStudio.css`
- `frontend/src/features/image-studio/ImageStudio.tsx`
- `scripts/ui-creative-shell-check.mjs`

已有未跟踪 ZIP 也保留未动。本报告是本任务新增的唯一文件。

## 3. Backend Bring-up

```makefile
status: PARTIAL
listener: 127.0.0.1:8000
process: uvicorn child process, PID 185340
```

### Liveness

```makefile
endpoint: http://127.0.0.1:8000/api/v1/health/live
status: PASS
http: 200
response: {"status":"ok"}
```

### System status

```makefile
endpoint: http://127.0.0.1:8000/api/v1/system/status
status: PASS
http: 200
environment: development
schemaRevision: c9f0a1b2c304
paidGenerationEnabled: false
paidGenerationAuthorized: false
```

系统状态接口可以正常响应，说明应用 import、Uvicorn、路由挂载和部分运行时配置均已建立。

### Readiness

```makefile
endpoint: http://127.0.0.1:8000/api/v1/health/ready
status: BLOCKED
http: 503
```

实际响应：

```json
{
  "status": "degraded",
  "checks": {
    "postgresql": "ok",
    "databaseSchema": "outdated"
  },
  "databaseSchema": {
    "currentRevisions": ["c9f0a1b2c304"],
    "expectedRevisions": ["e5f6a7b8c901"],
    "missingTables": [
      "creative_command",
      "creative_creation",
      "creative_prompt_registry",
      "creative_record",
      "creative_task"
    ]
  }
}
```

本次没有执行任何 Alembic upgrade 或 migration。

应用启动会读取数据库并执行正常的运行时初始化；启动日志还显示了 Provider availability check。没有执行图片生成、视频生成、付费提交、审核写入或交付操作。

## 4. Database Revision Analysis

只读检查结果：

```makefile
current: c9f0a1b2c304
head: e5f6a7b8c901
```

从代码中的 Alembic 链分析，当前至少缺失以下 Creative Workflow migration：

| Revision | Down revision | 作用 |
| --- | --- | --- |
| `d0c1e2f3a405` | `c9f0a1b2c304` | 创建 `creative_task`、`creative_record`、`creative_command` |
| `d1e2f3a4b506` | `d0c1e2f3a405` | 创建 `creative_creation`、`creative_prompt_registry`，并调整 ProductVersion |
| `d2f3a4b5c607` | `d1e2f3a4b506` | 修复 Creative 完整性和不可变 command 约束 |
| `e4f5a6b7c809` | 前置迁移 | 创建 Provider submission ticket 持久化结构 |
| `e5f6a7b8c901` | `e4f5a6b7c809` | 创建 Creative Provider input lease 持久化结构 |

因此，当前数据库不是只缺一张表或一个末端 revision，而是从 `d0c1e2f3a405` 开始落后于当前代码 head。

迁移建议：

1. 先确认当前数据库是本地开发库还是测试数据环境；
2. 确认备份、数据保留和回滚方案；
3. 评估从 `c9f0a1b2c304` 顺序升级到 `e5f6a7b8c901`；
4. 由下一次明确授权的数据库任务执行迁移；
5. 迁移完成后重新验证 `/api/v1/health/ready`。

本次没有自动迁移，也没有把 schema mismatch 当作已解决。

## 5. Frontend Bring-up

```makefile
status: PASS_WITH_READINESS_WARNING
listener: 127.0.0.1:5173
```

### Frontend page

```makefile
endpoint: http://127.0.0.1:5173/
status: PASS
http: 200
content-type: text/html
title: 衣影工坊 - 可灵官方 API 视频生产
```

浏览器验证结果：

- 页面可以打开；
- Video Studio 页面完整渲染；
- 视频模板列表可以读取；
- 站点风格可以读取；
- 页面没有此前的 `502 Bad Gateway`；
- 页面没有“服务连接异常”阻塞状态；
- 生成按钮按真实素材约束保持禁用，未触发生成。

### Frontend API proxy

```makefile
endpoint: http://127.0.0.1:5173/api/v1/health/live
status: PASS
http: 200
response: {"status":"ok"}
```

```makefile
endpoint: http://127.0.0.1:5173/api/v1/health/ready
status: BLOCKED
http: 503
response: databaseSchema=outdated
```

```makefile
endpoint: http://127.0.0.1:5173/api/v1/system/status
status: PASS
http: 200
```

Frontend → Backend proxy 已经连通。当前 proxy 的失败只剩后端 readiness 真实返回的 503，不再是连接拒绝或 502。

## 6. Director Studio

只读打开：

```text
http://127.0.0.1:5173/?view=images&pane=director
```

结果：

- Director Studio 页面 HTTP 200；
- 商品输入 Product Brief 可见；
- 品牌归属选择可见；
- 页面显示 `离线 Fake 模式 · 不可交付`；
- 页面没有触发上传、分析、创意方向生成或 Provider 调用；
- Director 页面可访问，但不应进入真实样本测试，因为后端 readiness 仍为 503。

## 7. Blocking Issues

### P0

当前没有页面连接阻塞。标准开发 profile 已能启动并访问：

```text
Browser → Frontend 5173 → Backend 8000
```

### P1

数据库 schema readiness 仍阻塞真实样本测试：

- `/api/v1/health/live`：200；
- `/api/v1/health/ready`：503；
- 当前 revision：`c9f0a1b2c304`；
- 目标 head：`e5f6a7b8c901`；
- 缺少五张 Creative Workflow 表。

这意味着系统已经从“服务未启动”推进到“服务可启动但数据库合同未就绪”。真实样本测试仍不能开始。

### P2

- 本次只启动了 API 和 frontend，没有启动独立 Runner 服务；
- API 启动时执行了正常 Provider availability check，但没有执行 Provider 生成或付费提交；
- 真实 `.env`、数据库用途、备份策略和迁移授权仍需人工确认；
- 当前 working tree 的外部未提交修改未纳入本次 bring-up 判断。

## 8. Real Test Readiness

```makefile
frontend_startup: PASS
backend_startup: PASS
health_live: PASS
frontend_api_proxy: PASS
health_ready: FAIL
director_page: PASS
real_sample_test: NOT_READY
```

当前不满足真实样本测试条件。还需要完成数据库用途确认和经授权的 migration 评估/执行，再使 `/api/v1/health/ready` 返回 200。

## 9. Recommended Next Step

下一步应单独建立数据库迁移任务，先完成：

1. 确认当前 `DATABASE_URL` 对应的是本地开发库还是测试数据环境；
2. 备份并记录当前 `c9f0a1b2c304` 数据库；
3. 审查 `d0c1e2f3a405` 到 `e5f6a7b8c901` 的升级链；
4. 获得明确授权后执行迁移；
5. 重新验证 `/api/v1/health/ready`、前端 proxy 和 Director Studio；
6. readiness 通过后，再安排真实样本测试。

## 10. Scope

本次执行：

- 启动并验证标准开发 profile；
- 启动 Backend `8000`；
- 启动 Frontend `5173`；
- 只读验证 health、system status、proxy、页面和 Director 入口；
- 只读分析 Alembic revision chain。

本次未执行：

- 未修改业务代码；
- 未修改 API、Router、Creative Workflow、Adapter 或 Provider contract；
- 未修改配置文件或真实环境变量；
- 未执行数据库 migration；
- 未执行真实 AI 生成、Provider POST、付费、审核写入或交付；
- 未提交 commit。

结论：**Local Runtime Bring-up 部分成功。系统已经可以启动和访问，但数据库 readiness 未通过，因此仍不能进入真实样本测试。**
