# Creative Workflow CW-3 小包并行调度

日期：2026-10-10
性质：任务分发与文件归属，不是功能验收或上线批准。

用户授权多个新窗口并行执行，总 PM 负责下发、监督、指导、验收。CW-2 已由实施窗口报告完成；独立审查发现预算、文字完整性、离线媒体资格和迁移验证缺口，尚不能宣布整体通过。

## 本轮四包

| 包 | 单一交付目标 | 独占写入范围 | 完成证据 |
| --- | --- | --- | --- |
| CW-3A | 修复现有 Fake 命令的预算、停止与重放一致性，贯穿实际事实版本 | `services/creative_workflow.py`、`api/creative_workflow.py`、新增 `test_creative_workflow_accounting.py`、本包报告 | UNKNOWN 对账释放两级预占；显式零预算；停止不被对账清除；任务推进后创建重放返回原响应；facts_revision 不写死 |
| CW-3B | 可接入现有包的纯函数文字完整性模块 | 新增 `creative/text_contract.py`、`test_creative_text_contract.py`、本包报告 | 原冻结包对照；事实版本/快照/锁项/实际六维/Prompt/Registry 身份变化被拒；重新计算自带哈希不能绕过；明确未接线 |
| CW-3C | 阻止离线候选被旧图片入口升级或送往真实 Provider | `api/image_generations.py`、`api/uploads.py`、`services/image_generations.py`、新增 `creative/media_qualification.py`、`test_creative_media_isolation.py`、本包报告 | Fake/占位来源不丢失、不升级普通 QUALIFIED、不经来源上传进入视频；公共刷新不调用真实适配器；普通旧图片流程不回归 |
| CW-3D | 用实际 Alembic 验证带旧数据升级与不可变约束 | 新增 `test_creative_migration_integrity.py`、`scripts/run_creative_targeted_tests.py`、本包报告 | 临时 SQLite 旧数据升级前后行数/哈希一致；直接 SQL 验证事实与历史触发器；两侧结果单列；PG 未验证如实记录 |

表中源码路径相对 `backend/src/libtv_agent/`，测试路径相对 `backend/tests/`。各报告使用 `docs/SPRINT_REPORT_CREATIVE_WORKFLOW_CW3A_20261010.md` 等独立文件。

CW-3A 不做后台 worker、事务边界重构、真实计费或通用状态机。CW-3B 不做完整五维创意提取、模板平台或自由修订语义证明。CW-3C 不做新媒体表、多分镜或完整物化恢复。CW-3D 不建设完整沙箱、连接未知 PostgreSQL 或修改历史迁移。

## 并行与串行

```text
CW-3A 小修复 ───────┐
CW-3B 纯函数模块 ───┼─ 首轮交接 → PM 指定单窗口接线 → 整体回归 → 最终验收
CW-3C 旧入口隔离 ───┤
CW-3D 迁移验证 ─────┘
```

四包可以独立编写、聚焦验证。CW-3B 通过只代表模块可用；D4/E1 接线后才能证明运行路径受完整性门保护。接线由 PM 在 CW-3A 释放核心文件后另发窄包，不由多个窗口争写。

本轮保留模块顺序 G0→D1→D2→D3→D4→H1→E1→E2→E3、Canonical Product、Reality 六维与人工资格边界。有限自主真实性循环仍是目标，待文字/媒体证据与停止条件接线后分包推进；插件宿主的禁止自主循环不作为项目限制。

## 文件与同步责任

- testing 为 `E:/Projects/libtv自动化生成` 的 `codex/testing`。
- 实际 main 为 `C:/Users/Reel/Documents/libtv-auto-main-sync` 的 `main`，不能使用 testing 的 main 引用代替。
- 每包只有一个实施窗口，负责该包独占白名单的 testing 验证、实际 main 增量同步和独立复验。禁止推广其他包尚未完成的改动。
- PM 独占本调度文档、协调表、本轮调度报告和后续共享接线。共享 ORM、schema、enums、迁移、OpenAPI、产品规范和 CHANGELOG 在本轮保持锁定。
- 禁止全树同步、切换共享工作树分支、重置、全量暂存、覆盖已有用户改动。若独占文件出现外部修改，先比较再增量合并。
- 有依赖的检查串行：OpenAPI 生成完成后才检查合同。各窗口不得同时重写 OpenAPI；新增定向 runner 不包含 export。
- 不读取真实 `.env`，不连接生产数据库，不调用付费 Provider、不执行生产迁移、部署或重启。正式前端仍是用户指定的 `http://192.168.30.126:5173/`，本轮不修改前端或运行服务。

## 测试与停止扩展

各包先复现自己的缺陷，再实施最小修复，跑聚焦测试和相关旧流程回归。通过后只因新增变化、失败或具体未决风险重跑；不为增加通过数量反复扩大选集。

新增测试不直接在仓库 cwd 启动可能加载 `.env` 的应用。采用仓库外独立 cwd、显式临时 SQLite、`_env_file=None`、Fake、网络阻断和独立产物目录。定向 runner 完成前可使用本包专属外部入口；不要改共享旧 harness。

每个窗口报告：本包文件、行为变化、测试命令/退出码/通过失败跳过数、源码哈希、两侧同步范围、保留差异、未证明事项。首轮实现结束即交接，不自主追加下一包、不再创建窗口。

## 已登记的剩余工作

- 完整事务意图、跨进程崩溃恢复及 PG 竞争测试：后续独立小包。
- 商品 confirm/block 和版本变更并发：需专项动态复现，不作为本轮顺带扩展。
- 导演审核与 Output 审核统一、真实/Replay 媒体证据和物化恢复：后续媒体小包。
- 实际 main 的 PointsQuotaRead 当前默认 100，与此前报告的 5000 不一致；config 仍为历史配置。来源尚未确认，各窗口不得擅自改回或同步 schema。
- Fake PASS、数据库迁移 PASS、模块存在均不证明真实像素质量改善；导演前端和上线门仍保留人工验收。

## 执行登记

验收状态依次为已下发、实施中、待独立验收、通过；失败与剩余依赖单独记录，不把任务启动计为完成。

| 包 | 实施窗口 ID | 当前状态 |
| --- | --- | --- |
| CW-3A | `01a12506-f17c-7bc2-8da0-b75eee6c6208` | PM 独立验收通过；两侧 28 项回归、Ruff 通过；PG/跨进程崩溃仍未证明 |
| CW-3B | `01a12506-f727-7e53-a563-54303c369ca2` | 模块验收通过；两侧 44 项通过、Ruff 通过；D4/E1 接线待后续小包 |
| CW-3C | `01a12506-fd44-71f1-bf9a-0bbcb708c5b4` | PM 第二轮独立验收通过；两侧 5 项聚焦、22 项旧回归和 Ruff 通过 |
| CW-3D | `01a12507-040c-70c2-a642-050b57db634a` | 验证包完成；两侧各 2 项通过、2 项严格失败，暴露历史迁移触发器缺口 |
| CW-3E | `01a12738-81d4-7592-9df5-e8039ee91de7` | PM 独立验收通过；两侧 Ruff 和 3 项修复测试通过 |

PM 窗口为 `01a123cc-2aae-7562-a206-7a39d999a985`。任务书允许实施窗口向 PM 发送入口交付或最终交接，PM 后续消息明确授权指导该包；实施窗口不自行向无关窗口广播。

### CW-3C 首轮独立复核

- 实施窗口报告两侧聚焦 3 项、旧图片/权限 22 项及 Ruff 通过；PM 尚未将这些数量登记为自己的复跑结果。
- PM 核对新增模块/测试/报告两侧 SHA 一致；既有图片 API 的当前两侧差异为保留的配额注释，服务来源隔离增量一致。
- PM 在仓库外 cwd 纯内存实际复现：普通 Provider 批次和普通 URL、仅 output `quality_gates_json` 含 `synthetic=true` / `qualification=OFFLINE_SYNTHETIC_ONLY`，当前判定仍返回 false。
- 已向原 CW-3C 窗口下发同白名单修复与 API 负例：任何明确输出离线证据不能被普通审核覆盖，历史误合格输出的来源上传仍须阻断；不另造数据层或扩大媒体包。
- CW-3D 定向 runner 尚在实施；PM 已指出环境继承、pytest 配置和临时 JUnit 被删除的证据缺口，要求原白名单内修正后才共用。
- CW-3C 第二轮复核：testing/main 各自运行 5 项聚焦测试和 22 项旧图片/审核权限回归，均通过；scoped Ruff 均通过。纯内存复核确认 output 级四种离线标记与 item 别名均能阻断，`HUMAN_REQUIRED` 不误判。
- CW-3C 验收结论：通过并释放白名单。无来源 header 的手动重新上传完整来源链、Replay 证据、导演 snapshot/Output 审核统一接线仍未证明。
- CW-3B 第二轮复核：testing/main 各自 44 项纯模块测试通过，Ruff 通过，三文件 SHA 一致。冻结上下文、实际 Reality 六维、事实/锁/Prompt/Registry 对照及自算哈希绕过负例均有证据。
- CW-3B 验收结论：模块通过并释放白名单；D4/E1 尚未接线，现有服务中的 Preservation 检查不能视为已替换。接线必须在 CW-3A 释放共享服务后由单一窗口完成。
- CW-3A 第二轮复核：testing/main 各自运行 `test_creative_workflow_accounting.py`、`test_creative_workflow.py`、`test_products.py` 共 28 项，均通过；scoped Ruff 均通过，四个白名单文件 SHA 一致。
- CW-3A 验收结论：通过并释放白名单。PostgreSQL 并发、跨进程崩溃恢复、真实账本事务边界仍作为后续专项，不因本包通过而宣称。
- CW-3D 结果：两侧定向 runner/Ruff 通过，但迁移测试各 2 项失败。失败均是既有迁移缺口：`product_version` 删除未被 SQLite 阻断，`creative_command` 删除未被阻断；旧事实保留、USER_UPLOAD 空 URL、唯一约束和 downgrade 拒绝通过。
- CW-3E 已登记为独立修复包：只追加新 Alembic migration 和迁移回归，禁止修改 `d1e2f3a4b506` 或把验证失败改成跳过。

| CW-3E | 新增迁移 `d2f3a4b5c607`，补齐 ProductVersion 删除保护和 CreativeCommand 不可变保护 | 新迁移、迁移专项测试、报告 | 两侧从 `d1e2f3a4b506` 升级到新 head；UPDATE/DELETE 直接 SQL 均拒绝；旧数据和 downgrade 边界保持 |
