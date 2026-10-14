# Sprint Report：P0 身份安全

日期：2026-10-14
范围：`SECURITY_PROTECTION_PLAN_20261014.md` 的 P0 身份隔离与启动配置校验。
PM 复验追加真实 Provider 付费准入和现有 pilot 白名单/预算防护修复。
不含 AI 风险额度、新 Provider 引擎、数据库迁移或部署。

## 完成

- 核对并验证既有 staging/production 自动会话鉴权，以及显式
  `shared_authentication_enabled=true` 的 development/test 会话鉴权。
- 共享请求只以有效会话查询 Actor；无会话、未知/过期/撤销会话、停用账号
  均不能回退至 `X-User-Id`。Header 不能覆盖已登录身份或提升管理员角色。
- 增加统一 `offline_authentication` 条件，固定开发身份、Header 身份及
  自动建开发用户只在 development/test 非共享离线路径生效。
- 系统状态只在该离线路径返回 `phaseOneUserId` / `phaseOneAdminId`。
- 非 test 环境开启任一真实 Provider、付费生成或 live 执行而不使用
  共享鉴权时，启动校验拒绝；API 与 Runner 加载管理员配置后再次校验。
- 反馈学习的真实模型开关也纳入身份校验，即配置 OpenAI key 且
  `feedback_learning_enabled` / `feedback_learning_llm_enabled` 同时开启。
- 保留 test 中 Fake/Replay/Mock 配置兼容，以及既有 test 付费禁令。
- 已先在 `codex/testing` 修改和验证，再完成实际 main 工作树局部同步。

## 修改

| 文件 | 本包变更 |
| --- | --- |
| `backend/src/libtv_agent/config.py` | 真实 Provider 判定、离线身份准入、启动组合校验 |
| `backend/src/libtv_agent/api/dependencies.py` | Actor 离线身份防护及开发自动建用户条件 |
| `backend/src/libtv_agent/api/system.py` | 固定开发 ID 仅在离线身份模式展示 |
| `backend/src/libtv_agent/app.py` | 管理员配置加载后复验身份配置 |
| `backend/src/libtv_agent/runner/service_runtime.py` | 视频管理员配置加载后复验身份配置 |
| `backend/tests/test_identity_safety.py` | 99 项聚焦回归 |
| `docs/CHANGELOG.md` | 追加实际完成范围和两侧验证结果 |
| 本报告 | 完成、修改、测试、发现问题、下一步 |

KEEP：现有会话查询、角色判断、CSRF、用户管理、付费禁令和计费合同。
ADAPT：离线身份与真实 Provider 启动组合校验。
DEFER：AI 风险额度、登录限流、HTTPS 和生产发布。

## 测试

测试使用现有 Python 3.11 / pytest 8.4.2 / Ruff 0.16.0。
从仓库外验证目录执行，各自通过 `-c <工作树>/pyproject.toml` 和工作树绝对路径
加载被测源码；不读取真实 `.env`，不调用真实 Provider，不重启服务。
新增 API 测试只连接隔离 SQLite，不进入应用生产恢复循环。

验证目录：
`E:/Codex/visualizations/2026/10/14/01a13879-12ae-7cf0-b777-5e55396c9760/identity-safety-verification`

两侧执行同一组八个 pytest 文件：

```text
backend/tests/test_identity_safety.py
backend/tests/test_auth.py
backend/tests/test_config.py
backend/tests/test_shared_auth_and_logging.py
backend/tests/test_user_management.py
backend/tests/test_health.py
backend/tests/test_review_permissions.py
backend/tests/test_windows_service.py
```

| 工作树 | 聚焦身份测试 | 完整相关选集 | Ruff |
| --- | --- | --- | --- |
| `E:/Projects/libtv自动化生成`，`codex/testing` | 99 passed | 137 passed，24.21s | 通过 |
| `C:/Users/Reel/Documents/libtv-auto-main-sync`，`main` | 99 passed | 136 passed，24.49s | 通过 |

main 少一项的原因：testing 既有
`test_runner_loads_every_video_provider_admin_config` 未存在于 main。
本包不推广该既有分支差异；新增的 99 项测试及其测试文件两侧一致。

Ruff 检查本包五个源码文件和上述八个测试文件，两侧均通过。
两侧本包文件 `git diff --check` 通过。
JUnit 证据为上述仓库外目录的 `testing-identity-safety.xml` 和
`main-identity-safety.xml`，未同步为生产源码。

测试覆盖：

- staging/production，以及显式共享的 development/test 无会话读取业务接口拒绝。
- 合法普通用户会话保持本人身份，伪造管理员/开发 ID/非法 UUID 不覆盖身份。
- 缺失、未知、过期、撤销和停用账号的会话不能回退 Header。
- 空用户库中，共享请求不会自动创建开发用户或开发管理员。
- development/test 离线模式正常创建两类固定开发账号；无 Header/非法 Header 拒绝。
- 所有真实 Provider/模型调用、live/付费开关的非共享启动拒绝矩阵。
- 真实 Provider 配置在合法共享模式下通过，test Mock 兼容，test 付费仍拒绝。
- API/Runner 加载配置后打开 Provider，以及 API 加载反馈模型 key 时拒绝不安全组合。
- 运行中启用真实模型能力后，已有离线身份入口也立即拒绝，不自动建用户。

## 发现问题

- 既有共享会话主路径已经正确；缺口主要是 development 的真实 Provider
  组合未约束，不能把 staging/production 既有防护描述为本包新实现。
- 反馈学习会绕过 `ai_adapter_mode` 直接根据 key 和学习开关启用模型，
  已纳入本包校验；没有为此调用模型或实现额度系统。
- 管理员配置在初次校验后加载，可能才启用真实 Provider，已增加加载后复验。
- 新测试初次 Ruff 发现长断言，修正后重新执行并通过。
- 工作期间另一任务并行修改/同步 Cutflow；保留其所有改动。
  main 的 config/system 身份片段已出现时逐段核对，不重复写入或覆盖整文件。
- 保留 main 的下载 helper 路径、5000/120 额度默认值，以及 testing 的
  100/1 计数默认值和 pilot 配置；不改变任何分支专属计费行为。
- 初始和执行期间的已有未提交改动均保留，没有提交、回滚或清理无关文件。

剩余风险与限制：

- 源码同步不等于在线服务已经采用新防护；本包没有部署、迁移或服务重启。
- 未读取真实配置或访问正式业务数据库，不能据此声明生产运行时配置已验收。
- test Provider 兼容供隔离 Mock 使用，不是允许 test 付费调用的授权。
- AI 风险额度、登录限流、HTTPS 等仍按原安全计划后续处理，本包不扩大范围。

## 下一步

- 在单独授权的发布窗口检查实际配置并加载本包源码，完成运行时身份验收。
- 由主任务安排安全方案后续阶段；本包不继续实现额度或 Provider 新能力。
- 本包源码同步成功，两侧相关 pytest 和 Ruff 已独立通过。

## PM 复验：两个 P0 阻塞修复

日期：2026-10-14。以下为首轮身份安全之后的追加修复，不覆盖首轮验证记录。

### 完成

- `real_provider_submission_authorized()` 始终使用既有
  `paid_generation_authorized()`，不再根据 `libtv_adapter_mode=fake/replay`
  或 `app_env=test` 直接放行真实 Provider。
- 检查所有调用链：runtime_control 的提交/claim 门及 Runner 执行门直接
  使用该函数；确认与固定视频创建通过 runtime_control 的提交门。
  Kling、WaveSpeed、Bach 都要求非 test、live 执行、付费开关和精确确认短语。
- LibTV synthetic 路径保留独立行为，纯本地 development/test 的
  Fake/Replay 不需要真实付费授权；真实 Provider 在 test 中仍被拒绝。
- `reserve_internal_pilot_budget()` 仅对离线身份且未开启任何真实 Provider
  能力的本地 synthetic 配置跳过。共享或具备真实 Provider 能力的
  development/test 同样检查 `internalPilotEnabled`、`pilotUserIds`、
  `pilotBudgetLimit` 和 `pilotSubmittedCount`。
- 复用现有 RuntimeConfigVersion，以最早配置行的 no-op UPDATE 取得稳定
  事务锁，再读取最新配置并追加版本；不同允许用户并发预占不会超支。
  成功版本的 `changed_by` 和 AuditEvent `actor_id` 都记录实际用户。
- 计数和 actor 审计仍处于同一调用事务中，rollback 不留下预占或审计。
  没有新建风险额度系统，也没有修改收费、UNKNOWN 或查询/对账合同。

### 修改

| 文件 | 本轮内容 |
| --- | --- |
| `backend/src/libtv_agent/services/generation_safety.py` | 移除无关 LibTV synthetic/test 环境对真实 Provider 的豁免 |
| `backend/src/libtv_agent/services/runtime_control.py` | 缩小 pilot 跳过条件、稳定行锁、实际 actor 审计 |
| `backend/tests/test_runtime_control.py` | Provider 提交/claim/Runner 负断言、pilot 拒绝/并发/actor/rollback/synthetic 回归；旧熔断 fixtures 使用显式合法授权 |
| `backend/tests/test_paid_acceptance_safety.py` | real Provider 独立授权矩阵和 test 禁令；旧锁测试使用临时目录 |
| `docs/CHANGELOG.md` | 追加本轮实际修复与最终结果 |
| 本报告 | 追加复验范围、结果及限制 |

### 测试

两侧均从仓库外验证目录运行，使用各自工作树的 `pyproject.toml` 和源码。
没有读取真实 `.env`、付费 Provider 调用、服务重启或生产数据写入。

本轮两侧运行同一组：

```text
backend/tests/test_runtime_control.py
backend/tests/test_paid_acceptance_safety.py
backend/tests/test_identity_safety.py
backend/tests/test_config.py
```

| 工作树 | Runtime Control | Paid Acceptance | Identity Safety | Config | 最终结果 |
| --- | --- | --- | --- | --- | --- |
| codex/testing | 68 passed | 48 passed | 99 passed | 15 passed | 230 passed，51.35s |
| main | 68 passed | 48 passed | 99 passed | 15 passed | 230 passed，47.80s |

两侧 Ruff 检查本轮两个源码文件和上述四个测试文件，均通过。
本轮文件 `git diff --check` 通过；四个源码/测试文件逐文件推广并核对一致，
行尾格式保留各工作树原有约定；main 的其他未提交改动保留。

新增 89 项聚焦测试：

- production + Fake/Replay LibTV + Kling/WaveSpeed/Bach 分别缺 live、
  付费开关、确认短语或正确短语时，提交与 claim 均拒绝。
- test + Fake/Replay LibTV 仍不能授权真实 Provider。
- 合法授权可打开上述三种 Provider；无需把无关 LibTV adapter 切换成 real。
- Runner 直接执行未经授权的真实 Provider 时，submit、localize 和
  launch commit 调用次数为零。
- shared development、real-provider development、两者同时开启及真实分析
  能力，均拒绝未开启 pilot、非白名单和超预算请求。
- 合法用户成功预占，版本和审计绑定本人；三个不同允许用户争用一个名额，
  一人成功、两人收到 `PILOT_BUDGET_EXCEEDED`，计数和审计都只有一份。
- rollback 同时回滚计数与审计，纯本地 development/test 的 Fake/Replay
  保持既有行为；原有 UNKNOWN circuit 和手动暂停合同继续通过。

证据目录：
`E:/Codex/visualizations/2026/10/14/01a13879-12ae-7cf0-b777-5e55396c9760/identity-paid-gates-verification`

JUnit：`testing-paid-gates.xml`、`main-paid-gates.xml`，保留在仓库外，
不作为生产源码推广。

### 发现问题

- 首轮身份隔离没有封住真实 Provider 的 synthetic-adapter 授权豁免，
  PM 发现属实，本轮已移除并测试提交、claim 和 Runner 执行路径。
- pilot 原来以环境名直接跳过，而且审计 actor 为 None；共享 development
  可以绕过白名单/预算，现已收紧并绑定实际用户。
- 原版本 append 不能仅靠 SQLite 的 SELECT FOR UPDATE 说明并发安全；
  本轮增加稳定写锁，隔离 SQLite 的多会话、不同用户竞争测试通过。
- 三个合法 Provider 正向测试首轮因 fixture 仍保持默认付费暂停而失败；
  已显式配置解除暂停，不放宽业务门，最终整组选集全部通过。
- 旧熔断/暂停测试曾依赖 test/synthetic 绕过真实授权，本轮改为隔离的
  development + shared + 显式 paid/live/确认配置；仍不调用 Provider。
- 旧验收锁拒绝测试使用仓库运行路径，已改用 `tmp_path`。

剩余限制：并发证据来自隔离 SQLite，本轮未验证 PostgreSQL、多进程
或正式运行时；源码同步不代表部署。本轮没有 AI 风险额度、迁移、付费
调用、服务重启或查询/对账行为改造。

### 下一步

- 本轮两个 P0 阻塞已修复，testing/main 同组选集和 Ruff 均通过，同步成功。
- 发布窗口、真实配置和正式运行时验收仍需单独授权；不继续扩大本轮范围。
