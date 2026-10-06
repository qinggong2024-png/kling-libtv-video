# AI 广告视频自动生产系统｜L3 Domain Model + System Architecture Contract v1.0

**状态：RECOVERED / CANONICALIZED / FROZEN**  
**恢复日期：2026-08-11**  
**层级：L3｜领域模型与系统架构合同**  
**上位约束：L1 Product & Scope Contract > L2 Production Contract**  
**下位约束：L4 Acceptance / Implementation**

> 本文件补齐此前遗漏的 L3 独立正文。
> 它定义架构边界和领域语义，不强迫当前已可靠运行的实现为了“文档一致”重写。
> Existing System Audit 证明可靠的部分默认 KEEP。

## 0. Architecture Principles｜FROZEN

1. 业务状态与 Provider 状态分离；
2. Provider 通过 Adapter Boundary 接入；
3. 数据库 / 持久状态是正式业务事实源；
4. 文件内容身份通过 SHA-256 或等价 Hash 可验证；
5. 付费 Attempt 必须可追溯和幂等；
6. Worker / Runner 重启不能丢失正式状态；
7. Machine QA 与 Human Approval 是独立证据；
8. Infrastructure 不得反向定义 Product Mainline；
9. 优先模块化单体 / 最小充分架构；
10. 不为了新模型或“架构漂亮”拆微服务。

## 1. Logical Architecture｜FROZEN BOUNDARY

```text
Web / Operator UI
↓
Application API
↓
Production Orchestrator
├── Job / Variant Service
├── Asset Service
├── Candidate Qualification
├── Provider Adapter
├── Generation / Attempt Service
├── Download / Artifact Service
├── Editing / Assembly
├── Technical QA
├── Human Approval
├── Delivery Service
├── Retry / Recovery / Reconciliation
├── Metrics / Audit
└── Runtime Revision / Config Evidence

Persistence
├── Relational Database
├── Object / File Storage
└── Logs / Evidence

Execution
├── Worker(s)
└── Runner / Provider Execution Backend
```

具体目录、框架和进程数量可以按现有可靠实现保持。

## 2. Core Domain Entities｜FROZEN SEMANTICS

### 2.1 ProductionJob
代表一次业务生产任务，至少关联：

```text
id
owner / user
requirements
status
source assets
variants
created_at
updated_at
```

### 2.2 ProductionVariant
Job 下的独立视频目标/版本。每个 Variant 独立 Attempt、Input Binding、Output、QA、Approval 和 Delivery State。

### 2.3 GenerationAttempt
一次独立 Provider 生成尝试，至少关联：

```text
variant_id
provider
model
runtime revision
config / prompt revision
provider task id
status
cost evidence
error
```

### 2.4 Asset
所有生产资产的统一身份：

```text
asset_id
asset_type
owner scope
sha256
storage reference
version
created_at
```

### 2.5 SourceAsset
用户 / 商品 / 生产链提供的事实输入，用于商品事实、分镜/场景、Prompt/生成参考及 Product Source of Truth（适用时）。

### 2.6 CandidateAsset
系统生成或进入候选池的中间视觉资产，至少有：

```text
AWAITING_REVIEW
QUALIFIED
REJECTED
```

### 2.7 QualifiedAssetBinding
记录某 Variant 实际使用哪些 Qualified Assets：

```text
variant_id
asset_id
asset_sha256
order / role
binding_revision
```

REJECTED Asset 不允许存在有效正式 Binding。

### 2.8 Staged / ProviderInputAsset
Provider 需要上传/转码/staging 时保存：

```text
source_asset_id
staged_asset_id
source_sha256
staged_sha256 / content identity
provider reference
```

### 2.9 GeneratedVideoAsset
Provider 生成的原始视频 Artifact：

```text
attempt_id
provider result
sha256
duration
resolution
decode state
storage reference
```

### 2.10 AssemblyResult
Editing / Assembly 输出：

```text
input_asset_ids
editing_config_revision
execution_backend
output_asset_id
output_sha256
status
```

### 2.11 ValidationResult
机器 QA 结果：

```text
asset / output id
gate / validation type
status
rule/model version
evidence
created_at
```

### 2.12 HumanApproval
人工 Ground Truth / Approval：

```text
entity id
gate
result
operator
reason / notes optional
created_at
revision
```

### 2.13 DeliveryRecord
只有正式 Deliverable 才创建/激活：

```text
job
variant
final asset id
approval evidence
delivery state
delivered_at
```

### 2.14 RuntimeRevision

```text
sourceRevision
schemaRevision
configRevision
runtimeVersion
provider
```

### 2.15 CostRecord / CostEvidence

```text
attempt
provider call
billing source
actual cost if available
cost proxy if actual unavailable
```

不得把估算写成实际账单。

### 2.16 FailureRecord

```text
asset_id
error_category
severity
action_taken
final_outcome
```

通过关系反查完整上下文。

### 2.17 AuditEvent
记录高影响人工 / 管理 / 状态操作。

## 3. Canonical Relationships｜FROZEN

```text
ProductionJob 1 ── * ProductionVariant
ProductionJob 1 ── * SourceAsset
ProductionVariant 1 ── * GenerationAttempt
ProductionVariant 1 ── * QualifiedAssetBinding
Asset 1 ── * ValidationResult
Asset / Output 1 ── * HumanApproval
GenerationAttempt 1 ── * GeneratedVideoAsset
AssemblyResult * ── * Input Asset
AssemblyResult 1 ── 1 Final Output Asset
ProductionVariant 0..1 ── 1 DeliveryRecord
```

DeliveryRecord 必须有 Required Gate Evidence + Final Approval + Final Output Asset。

## 4. State Separation｜FROZEN

至少分离：

```text
generation status
download / artifact status
editing / assembly status
technical validation status
human approval status
delivery status
```

禁止一个字段同时表达所有阶段。

## 5. Persistence｜FROZEN

正式业务状态必须持久化。

关系数据库保存 Job/Variant/Attempt、Asset metadata、Binding、QA、Human Approval、Delivery、Runtime Revision、Retry/Recovery、Idempotency、Audit 和 Cost Evidence。

对象/文件存储保存 Source Assets、Candidate Assets、Generated Videos、Assembly Outputs、QA Evidence 和 Logs/Reports。

Redis/Queue 等不能作为唯一正式事实源。

## 6. Data Integrity｜FROZEN

必须防止：

```text
cross-job asset binding
cross-variant result confusion
rejected asset binding
duplicate active paid attempt
delivery without required approval
runtime revision ambiguity
silent overwrite of human ground truth
```

优先使用 foreign keys、unique constraints、transactions、CAS/optimistic version、immutable/append-only audit 和 content Hash。

## 7. Idempotency Model｜FROZEN

需要幂等保护的操作至少包括：
- 创建付费生成；
- Provider Submit；
- Download；
- Delivery；
- 关键状态变更。

推荐存在：

```text
idempotency_key
payload_hash
operation_type
owner scope
result reference
```

相同 key + 不同 payload 必须拒绝或冲突。

## 8. Provider Adapter｜FROZEN

业务层不能依赖某 Provider 的任意返回形状。

统一内部语义至少包括：

```text
submit
query status
get result
download / resolve artifact
classify provider error
billing evidence
```

当前 Provider 属于 runtime/config 事实，不属于永久产品定义。

更换 Provider：

```text
Adapter change
+
Controlled Validation
```

不得强迫重写 Job/Asset/Approval/Delivery 核心。

## 9. Runner / Execution Boundary｜FROZEN PRINCIPLE

长时间/付费生成应具备：
- 持久 command / attempt 身份；
- 可恢复观察；
- stdout/stderr/provider task evidence；
- process/runner failure reconciliation；
- 不确定状态隔离；
- 重启后不盲目重复提交。

具体实现可以是 systemd、独立 Runner、受控进程或等价机制。

## 10. Editing / Assembly Module｜FROZEN

必须是真实可执行模块。

```text
assemble(inputs, config, runtime_context)
→ AssemblyResult
```

要求：
- 输入只能来自允许的 Asset；
- 产出 Hash；
- 记录 execution backend；
- 失败可分类；
- 不把调用成功当作质量成功；
- 结果继续进入 QA / Approval。

## 11. QA Architecture｜FROZEN BOUNDARY

```text
Technical Machine QA
Human-required Quality Gates
Targeted Machine Semantic QA（仅证据触发）
```

早期不建设统一“大而全 QA 平台”。

每个 Gate 必须知道 capability status、evidence 和 decision authority。

## 12. Human Review / Approval UI｜FROZEN

前端/Operator UI 至少能够：
- 查看具体 Asset / Output；
- 给 Candidate 标记 QUALIFIED / REJECTED；
- 执行 Product Fidelity Review；
- 执行 Human Critical Review；
- Final Approval / Rejection；
- 显示当前是否仍有 Required Human Gate；
- 不把 Machine PASS 伪装成人工批准。

人工动作必须写入持久证据。

## 13. API Boundary｜FROZEN PRINCIPLE

API 必须支持当前生产流程，具体 URI 可以随现有实现保持。

业务能力至少需要：

```text
create / read job
manage assets
qualify / reject candidate
submit / observe generation
query output
perform / observe assembly
technical QA
human approval
final delivery
retry / recover
runtime revision
metrics / audit
```

OpenAPI 应与实际运行实现同步。

## 14. Observability｜FROZEN

至少可观察：

```text
job / variant / attempt status
provider task
queue / latency
retry
download
assembly
QA
human review
delivery
runtime revision
cost / cost proxy
failure category
```

P0/P1 生产指标应能由结构化数据计算。日志不得替代数据库正式状态。

## 15. Security｜FROZEN

至少要求：
- secrets 不进入仓库；
- Provider Credential 最小权限；
- 对象归属校验；
- 用户只能访问授权 Job / Asset；
- 审核 / 管理动作按角色授权；
- 日志脱敏；
- 签名 URL / token 不长期暴露；
- 高风险配置变更可审计；
- 正式环境与测试环境隔离。

## 16. Configuration & Revision｜FROZEN

高影响运行配置必须版本化，至少覆盖：

```text
provider
model
prompt / generation config
editing config
QA rule version
runtime config
concurrency / retry policy
```

每次 Pilot / Acceptance 可以解析到精确版本。

## 17. Migration Contract｜FROZEN

Schema Migration 必须：
- 可重复验证；
- 新环境可 fresh migrate；
- 当前支持的生产数据库可升级；
- 不静默丢失历史 Ground Truth；
- 不破坏 Asset/Attempt/Delivery Traceability；
- 高风险不可逆迁移必须显式升级。

SQLite 可用于允许的开发/测试场景；正式目标数据库以项目当前生产合同为准。

## 18. Testability Boundary｜FROZEN

架构必须允许：
- Unit Test；
- Integration Test；
- Failure Injection；
- Fake / Replay Provider；
- Production-equivalent E2E；
- Real Provider Scoped Test。

Mock PASS 不能替代真实 Provider / Assembly / Runtime Revision 证据。

## 19. Deployment Boundary｜FROZEN

至少区分：

```text
DEV
PRODUCTION-EQUIVALENT / STAGING
PRODUCTION
```

每个环境应有可识别：

```text
sourceRevision
schemaRevision
configRevision
runtimeVersion
```

未经明确授权，不因测试需要修改 Production。

## 20. Architecture Change Gate｜FROZEN

只有真实 Critical Path blocker、Data Integrity/Security、可靠性无法在现有架构内解决，或 Failure Pareto 证明高价值时，才进行结构性替换。

否则 `KEEP / ADAPT` 优先于 `REWRITE`。

## 21. Deferred Architecture｜FROZEN

当前默认 DEFER：
- 微服务拆分；
- 多 Provider 动态路由；
- 多 Runner 高可用复杂调度；
- 完整 Annotation UI；
- 完整 Benchmark Platform；
- 通用 Agent Runtime；
- 多 Agent 产品架构；
- 无真实需求触发的高级 AI QA 服务。

# FINAL L3 STATUS

```text
DOMAIN SEMANTICS: FROZEN
ARCHITECTURE BOUNDARIES: FROZEN
PROVIDER BOUNDARY: FROZEN
DATA INTEGRITY: FROZEN
HUMAN APPROVAL EVIDENCE: FROZEN
RUNTIME REVISION: FROZEN
REWRITE-BY-DEFAULT: PROHIBITED
```
