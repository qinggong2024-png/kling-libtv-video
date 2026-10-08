# 项目技术审查报告

日期：2026-10-08
范围：AI Creative Studio V1.0 规范冻结前的仓库审查，不是线上系统验收

## 当前状态

测试目录 `E:/Projects/libtv自动化生成`，分支 `codex/testing`，审查基线 `0e3d1c8`。
生产目录 `C:/Users/Reel/Documents/libtv-auto-main-sync`，实际分支 `main`，审查基线 `70aadee`。
两个目录的实际 Git 元数据不同，测试仓库记录的 main 引用不能替代生产目录实际 HEAD。
测试目录有用户未跟踪 ZIP，生产目录入场干净；保留 ZIP，不同步。

| 审查项 | 仓库证据 | 结论 |
| --- | --- | --- |
| package.json | `frontend/package.json` | React、TypeScript、Vite、lucide-react、Vitest、ESLint；没有 Next.js/Tailwind/shadcn |
| 目录 | `frontend/src/app`、`features`、`shared`、`domain` | 已有模块化页面，不是从零创建 |
| 基础组件 | `shared/components/ui.tsx`、`ui.test.tsx` | 已有 Drawer、Thumbnail、Alert、EmptyState 等；没有独立 ui 目录 |
| 业务组件 | `features/production/MaterialCard.tsx`、`ResultCard.tsx`、`ProductionComposer.tsx` | 可适配为新组件体系；不能凭名字差异判断缺失 |
| 导航 | `app/useAppNavigation.ts`、对应测试 | query-view 导航、任务深链接、返回和滚动恢复已存在 |
| API | `frontend/src/api.ts`、`backend/src/libtv_agent/api`、`openapi.yaml` | 已有类型化客户端、FastAPI 路由和接口合同 |
| 后端栈 | `pyproject.toml` | Python 3.11、FastAPI、Pydantic Settings、SQLAlchemy、Alembic、pytest |
| 数据库 | `backend/src/libtv_agent/db.py`、`domain/models.py`、`backend/alembic/versions` | 异步 SQLAlchemy；PostgreSQL 默认配置和 SQLite 兼容路径；Task/Variant/Attempt/Asset/审核/幂等等已有模型 |
| 环境变量 | `backend/src/libtv_agent/config.py`、`.env*.example` | 从运行目录读取 .env；配置环境、数据库、对象存储、认证、Provider 和付费开关 |
| 状态 | `domain/workflowStates.ts`、`backend/contracts/state-machines.json` | 14 个 parent phase 和独立 attempt 状态；六态只能作为展示模型 |
| 页面测试 | `docs/runbooks/ui-pages-acceptance-20261008.md` | 既有 66 个离线页面用例记录，未覆盖真实生成或全量性能 |

未读取真实 `.env` 内容，未连接数据库，未核实线上 schema/config/runtime revision。以上数据库和环境结论是代码结构审查，不是运行环境证明。

## 风险与修改计划

| 风险 | 影响 | 计划 |
| --- | --- | --- |
| 直接更换 Next.js/Tailwind/shadcn | 扩大回归、失去既有页面挂载和导航语义 | KEEP React/Vite；新依赖单独论证 |
| 六态覆盖真实后端 phase | 丢失未知结果、待审、部分成功、取消语义 | ADAPT 集中 presentation 映射，保留原状态和能力 |
| 直接删除 admin/settings | 丢失运营、权限和 Provider 配置入口 | 保留支撑入口，不扩大产品范围 |
| 按产品路由名直接改导航 | 旧深链接、详情返回与滚动恢复回归 | 增量兼容迁移，补刷新和 back/forward 测试 |
| 条件卸载图片页面 | 离开页面后轮询与通知丢失 | 保留当前挂载约束，先建立测试再迁移 |
| 文档存在等同功能交付 | 错误完成声明 | 每个 Sprint 绑定测试、浏览器证据和人工检查点 |
| 旧 PM board 进度滞后 | 重复开发或夸大验收 | 以实际源码和较新的限定证据为准，旧记录仅作为历史 |
| 旧 `docs/环境隔离.md` 写 5178 | 错认正式入口 | 本次用户和 AGENTS 指定的正式入口为 `http://192.168.30.126:5173/`；不据旧文档改变服务 |
| 测试仓库 main 元数据与实际生产目录不同 | 错误同步位置或覆盖生产专属内容 | 以实际生产目录为准，逐文件比较，只推广本次修改 |
| package.json 多个依赖使用 latest | 后续重装可能引入版本漂移 | 本轮不改依赖；继续使用 lockfile，升级时单独回归 |

## 执行顺序

本轮固化五份规范、强制阅读入口、审查和 Sprint Report。
下一实际开发单元为 Design System + Video Studio，复用现有组件和 API；通过 Checkpoint 1 后才扩展其他工作区。
新增功能必须证明提高效率、降低人工或提升质量。

## 验证限制

本轮执行前端 build、lint、unit 基线，并验证两目录的文档同步。没有执行生产浏览器验收、付费调用、服务重启、迁移、真实数据写入或产品易用性测量。
审核、幂等、权限、计费、重试和 Deliverable 仍遵守既有 L1-L4，不因视觉规范冻结而改变。
