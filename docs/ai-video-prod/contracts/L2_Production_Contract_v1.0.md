# AI 广告视频自动生产系统｜L2 Production Contract v1.0

**状态：RECOVERED / CANONICALIZED / FROZEN**  
**恢复日期：2026-08-11**  
**层级：L2｜生产流程、生命周期与运行规则合同**  
**上位约束：L1 Product & Scope Contract**  
**下位约束：L3 Domain Model + System Architecture Contract / L4 Production Acceptance Contract**

> 本文件补齐此前遗漏的 L2 独立正文。它恢复的是已经存在的生产语义，不重新发明产品范围。
> 具体 Provider、并发数、成本阈值等可随真实环境配置变化；业务不变量保持冻结。

## 0. L2 职责

L2 定义真实业务生产流程、生命周期、Candidate→Qualified→Video→Deliverable 运行约束、Provider 调用、Retry/Recovery/Idempotency、Human Gate、Partial Success、Runtime Revision、生产可追溯性及成本/付费调用保护。

## 1. End-to-End Production Flow｜FROZEN

```text
1. Intake
2. Source Asset Validation
3. Candidate Asset Production / Ingestion
4. Candidate Quality Decision
5. Qualified Asset Binding
6. Video Generation
7. Download / Artifact Persistence
8. Automatic Editing / Assembly
9. Technical QA
10. Human-required Quality Gates
11. Final Approval
12. Deliverable
13. Failure Collection / Metrics
```

每一步必须有 input、output、state、evidence、failure path、recovery path。

## 2. Intake｜FROZEN

任务至少绑定：

```text
job_id
production_requirement
source_assets[]
requested_variants[]
runtime/config context
```

所有源素材至少保留：

```text
asset_id
owner / job scope
source_type
version
sha256
storage reference
created_at
```

不得跨 Job / Variant 串用；不得静默重排需要顺序的素材；正式生产输入修改必须创建新版本或新 revision。

## 3. Candidate Asset Lifecycle｜FROZEN

候选素材状态至少表达：

```text
CREATED
AWAITING_REVIEW
QUALIFIED
REJECTED
```

```text
QUALIFIED → 可进入正式 Video Asset Binding
REJECTED  → 禁止进入正式 Video Asset Binding
```

Pilot 中，系统生成的候选输入必须有持久化 Ground Truth。

对于 REJECTED Asset，必须可证明：
- not in task asset binding
- not in assembly input
- not in final output provenance

## 4. Qualified Asset Binding｜FROZEN

正式绑定必须记录：

```text
job
variant
asset_id
asset_sha256
binding_revision
binding_time
```

从系统候选结果转为 Provider 可用输入时，保持：

```text
Candidate Output
→ Qualified Decision
→ Staged / Provider-ready Asset
→ Video Input
```

至少通过 ID + SHA-256 或等价内容身份机制证明没有被替换或串用。

## 5. Video Generation｜FROZEN

每一次真实付费生成对应独立 Attempt。

Attempt 必须可关联：

```text
job
variant
qualified input assets
provider
model
prompt / config revision
runtime revision
provider task id
result
cost / cost proxy
```

Provider 成功只表示 `GENERATION_SUCCEEDED`，不表示 `DELIVERABLE`。

## 6. Provider Boundary｜FROZEN PRINCIPLE

Provider 通过 Adapter / Integration Boundary 接入。

当前 Provider 可以改变，但不得改变以下语义：
- 正式付费调用可唯一识别；
- 请求参数可追溯；
- Provider Task ID 可追溯；
- Timeout / Rate Limit / Network Failure 分开处理；
- Provider 返回不确定时不得盲目重复付费；
- Provider 成功后仍必须经过后续生产 Gate。

不得为了更换 Provider 重写业务核心。

## 7. Download / Artifact Persistence｜FROZEN

```text
download
→ integrity check
→ sha256
→ media probe / decode
→ artifact persistence
```

Download Failure 应 `RETRY_DOWNLOAD`，不得默认 `REGENERATE_VIDEO`，除非远程结果已证明不存在或不可恢复。

## 8. Automatic Editing / Assembly｜FROZEN

Editing / Assembly 是业务生产链的一部分，不是可跳过的占位接口。

```text
correct Qualified Assets
→ editing / assembly runtime
→ render / encode
→ output artifact
```

必须记录：

```text
input asset ids
input hashes
editing config / revision
execution backend
output id
output sha256
runtime revision
```

若某任务类型无需 Editing / Assembly，可明确 `NOT_APPLICABLE`，不得假装执行。

## 9. Technical QA｜FROZEN FLOOR

Technical Critical 至少覆盖当前可靠、低成本的机器检查，例如：
- file exists / readable；
- container / stream decode；
- corruption；
- duration；
- resolution / aspect ratio；
- obvious black / frozen frame；
- obvious file truncation；
- 其他经真实验证的 cheap stable checks。

Technical QA 输出必须结构化并可追溯。Technical PASS 不得自动产生 Deliverable。

## 10. Human-required Gates｜FROZEN

在机器能力未验证阶段：

```text
PRODUCT_FIDELITY = HUMAN_REQUIRED
HUMAN_CRITICAL = HUMAN_REQUIRED
FINAL_APPROVAL = HUMAN_REQUIRED
```

人工判断必须持久化，记录结果、operator/timestamp，绑定具体 Asset/Output，并保留历史版本。

## 11. Final Approval & Delivery｜FROZEN

一个最终 Output 只有同时满足：

```text
Required Hard Gates satisfied
+
Final Approval satisfied
+
Delivery record created
```

才进入 `DELIVERABLE`。

允许 Partial Success；未通过 Variant 不得因为同 Job 其他 Variant 成功而被标记 Deliverable。

## 12. State Integrity｜FROZEN

系统必须阻止：

```text
无有效 Asset → QA PASS
REJECTED Asset → Video Binding
无 Final QA / Approval → Deliverable
Hard Fail 未解除 → Deliverable
失败 Attempt → 被当作成功 Asset
Runtime Revision 不明 → Production-ready Claim
```

状态变化应使用版本 / CAS / transaction / unique constraint 等方式防并发覆盖。

## 13. Idempotency｜FROZEN

所有会产生副作用或付费的动作必须具备幂等语义。

至少保护：
- 重复 API 请求；
- 网络超时重发；
- 重复 Provider Submit；
- 重复 Download；
- 重复 Repair；
- 重复 Delivery。

新的主动 Regeneration 必须 new attempt + new idempotency identity + new trace。

## 14. Retry Policy｜FROZEN

```text
Download Fail              → Download Retry
Transient Provider Failure → Provider Query / Limited Retry
Provider Submission Uncertain → Reconcile First
Quality Fail               → Decision Engine
Invalid Input              → Reject / Human Action
Low Confidence / High Risk → Human Review
```

任何 Retry 必须有 max_attempts、cost/call ceiling 和 terminal state。不得无限循环。

## 15. Recovery｜FROZEN

Process / Worker / Runner 异常后：

```text
已成功且有证据的工作
不得无条件重做
```

恢复顺序：

```text
read persisted state
→ reconcile provider/runtime evidence
→ resume unfinished safe work
→ isolate uncertain paid work
```

付费提交状态不确定时，进入 UNKNOWN / UNCERTAIN，优先对账，禁止自动复制付费 Attempt。

## 16. Partial Success｜FROZEN

```text
至少一个 Variant 已 Deliverable
+
其他 Variant 仍失败 / 待审
→ PARTIAL_SUCCESS / PARTIALLY_DELIVERABLE
```

用户可以获得已通过部分。系统不得为了“整体一致”而无条件重跑已成功 Variant。

## 17. Runtime Revision Integrity｜FROZEN

每个 production-equivalent / production 运行实例必须可提供：

```text
sourceRevision
schemaRevision
configRevision
runtimeVersion
provider
```

正式 Pilot 必须锁定已验证 revision。

若 runtime revision != validated revision：

```text
PILOT_BLOCKED_RUNTIME_DRIFT
```

本地测试不能替代运行环境版本证据。

## 18. Cost & Paid-call Guardrail｜FROZEN PRINCIPLE

至少记录：

```text
provider_call_count
successful_generation_count
retry_count
regeneration_count
deliverable_count
```

Provider 可返回准确账单则记录 actual cost；不能则记录 best available cost proxy，不得伪造精确成本。

异常 Retry 超出 Pilot / Production 上限时：

```text
PAUSE_PAID_EXECUTION
```

## 19. Failure Collection｜FROZEN MINIMUM

最小 Failure Pool：

```text
asset_id
error_category
severity
action_taken
final_outcome
```

Asset 必须能反查：

```text
job
variant
attempt
source assets
product reference
provider
model
prompt/config
runtime revision
result
delivery state
```

## 20. Production Metrics｜FROZEN

至少产生支持以下指标的证据：

```text
Deliverable Production Throughput
Human Minutes per Deliverable
Cost per Deliverable / best available proxy
Critical Quality Escape Rate
Product Fidelity Failure Rate
First-pass Deliverable Rate
Generation Success Rate
Retry Rate
Regeneration Rate
Average Time to Deliver
```

无法测量时标记 `MEASUREMENT_GAP`，不得编造。

## 21. Human Time｜FROZEN

至少区分：

```text
submit
download / retry
review
rework
manual decision
```

目标是减少 Human Minutes per Deliverable，而不是只减少某个局部步骤。

## 22. Production Pause Conditions｜FROZEN

以下情况应暂停新的付费生产或扩大运行：
- Runtime Revision Drift；
- 重复付费证据；
- 跨 Job / Variant Asset Binding；
- Data Integrity 风险；
- Provider/billing 状态无法可靠判断且风险持续扩大；
- Required Hard Gate 路径失效；
- Security / Authorization 高风险；
- Cost Guardrail 被突破。

## 23. Environment Separation｜FROZEN PRINCIPLE

至少区分：

```text
DEV
PRODUCTION-EQUIVALENT / STAGING
PRODUCTION
```

隔离数据、secrets、runtime config、provider/account scope（能隔离时）及 artifacts/logs。

验证 production-equivalent 不得默认修改 Production。

## 24. Current Production Stage

采用 L4 阶段体系：

```text
INFRASTRUCTURE_READY
→ PRODUCTION_LOOP_READY
→ PILOT_READY
→ PRODUCTION_READY
→ ZERO_TOUCH_ELIGIBLE
```

# FINAL L2 STATUS

```text
PRODUCTION FLOW: FROZEN
ASSET LIFECYCLE: FROZEN
PAID GENERATION SEMANTICS: FROZEN
HUMAN GROUND TRUTH PATH: FROZEN
IDEMPOTENCY / RECOVERY: FROZEN
RUNTIME REVISION: FROZEN
COST GUARDRAIL: FROZEN PRINCIPLE
```
