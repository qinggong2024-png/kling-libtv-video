# Sprint Report：Creative Workflow CW-3C 媒体来源隔离

日期：2026-10-10
范围：旧图片审核、来源上传和公共图片批次刷新入口的离线 Fake 隔离

## 完成

- 新增持久来源判定模块，结合 `ImageGenerationBatch.provider`、批次/条目的离线标记、Fake provider task、输出 URL 与证据标记判断离线合成来源。
- 旧图片质量审核入口不再把明确 Fake / `OFFLINE_SYNTHETIC_ONLY` 输出升级为普通 `QUALIFIED`；离线拒绝允许写入，并保留原离线来源与证据范围。
- 带 `X-Source-Image-Output-Id` 的上传在资格状态检查前拒绝离线来源，即使历史数据曾错误写成 `QUALIFIED`。
- `refresh_batch` 与 `refresh_active_batches` 对明确离线批次不调用 WaveSpeed 查询、不下载远端图片、不结算；真实 WaveSpeed 批次继续走原刷新路径。

## 修改

白名单实际修改：

- `backend/src/libtv_agent/api/image_generations.py`
- `backend/src/libtv_agent/api/uploads.py`
- `backend/src/libtv_agent/services/image_generations.py`
- `backend/src/libtv_agent/creative/media_qualification.py`
- `backend/tests/test_creative_media_isolation.py`
- `docs/SPRINT_REPORT_CREATIVE_WORKFLOW_CW3C_20261010.md`

未修改导演服务/API/合同、ORM/schema、迁移、OpenAPI、前端、公共测试和共享文档。

## 测试

testing（`E:\Projects\libtv自动化生成`，`codex/testing`）：

- `python -m pytest backend/tests/test_creative_media_isolation.py -q`：5 passed。
- `python -m pytest backend/tests/test_image_generation_batches.py backend/tests/test_review_permissions.py -q`：22 passed。
- `.venv\Scripts\python.exe -m ruff check`，范围为本包五个源码/测试路径：通过。
- 测试使用仓库外 pytest 临时目录、临时 SQLite、`Settings(..., _env_file=None)` 和 Fake adapter；未读取真实 `.env`，未连接生产库、未调用真实 Provider、未下载真实媒体。

实际 `main`（`C:\Users\Reel\Documents\libtv-auto-main-sync`，`main`）：

- 已同步同一白名单增量后独立复跑上述 3 项命令：均通过，结果为 5 passed、22 passed、Ruff 通过。
- 新增模块、聚焦测试和本报告在两侧 SHA-256 一致；三个已有 API/服务文件保留 `main` 的生产专属差异，仅核对并同步本包来源隔离增量。未同步运行时状态、缓存、密钥、构建产物或压缩包。

## 发现问题

- 本轮确认并修复旧审核覆盖质量 JSON、来源上传只信资格状态、公共刷新按活动状态误轮询 Fake 三条路径。
- 补强输出级显式离线证据：即使 batch/provider/task/URL 看似普通 WaveSpeed，`synthetic`、`qualification`、`qualificationScope` 或 `qualification_scope` 仍阻止升级；历史 `QUALIFIED` 同类输出仍阻止来源上传。
- 判定模块不会证明没有来源 header 的手动重新上传具备完整来源链；本轮只收紧带 `X-Source-Image-Output-Id` 的兼容路径。
- Replay 是否具备足够真实证据未作推断，本轮未新增 Replay 执行。
- 导演 snapshot 选择、导演审核与 Output 审核统一接线、视频入口和多分镜仍是后续缺口。

## 下一步

本包首轮修复交付结束。保留真实生产像素质量、Replay 证据、PG 带数据升级、视频/导演链路和人工 Checkpoint 作为后续独立验收范围；本报告不宣称全链统一或生产就绪。

## 同步

- `codex/testing` 验证完成。
- 实际 `main` 已按独占白名单增量同步并独立验证成功。
- 未修改其他并行包文件；本包文件释放给父 PM 做整体接线与验收。
