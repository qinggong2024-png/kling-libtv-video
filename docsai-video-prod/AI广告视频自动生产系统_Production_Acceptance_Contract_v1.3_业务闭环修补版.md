# AI 广告视频自动生产系统｜Production Acceptance Contract v1.3

**版本定位：业务生产闭环修补版**

**状态：PRODUCT NORTH STAR FROZEN / BUSINESS LOOP RE-ANCHORED / SUPPORTING CAPABILITIES EVIDENCE-GATED**

**上位约束：L1 Product & Scope Contract > L2 Production Contract > L3 Domain Model + System Architecture Contract > 本合同**
**替代关系：本 v1.3 在与 v1.2 冲突处取代 v1.2；未修改内容继续继承 v1.2。**

---

# 0. 本次修补只解决什么

本次不重新设计产品，不新增 QA 平台、Benchmark 平台或 Annotation 平台。

仅修复以下结构性漏洞：

1. 防止 Mainline 从“业务生产闭环”漂移为“工作流基础设施自动化”；
2. 给 `Deliverable` 一个可执行定义；
3. 让 `Critical Quality Escape Rate` 真正进入 BASELINE-0；
4. 冻结最小 Required Hard Gates，避免技术 QA 被错误等同于可自动交付；
5. Pilot 阶段为尚未机器验证的质量 Gate 强制产生人工 Ground Truth；
6. 将 Stage 1 的“基础设施可用”和“完整生产链路可用”分开声明；
7. 保证 Failure 可以反查真实生成上下文，而不是只形成一个错误排行榜。

除上述修补外，不扩大项目范围。

---

# 1. Product North Star｜FROZEN

唯一主目标：

> **让跨境服装广告团队以更少人工、更合理成本、更稳定的方式生产更多真正可交付的 AI 广告视频，并随着真实生产证据逐步实现 Normal Case Zero-touch。**

项目不以以下内容为最终目标：

- QA 平台；
- Benchmark 平台；
- Annotation 平台；
- 学术级视频评测；
- 为新模型而扩展架构；
- 为架构完整而建设暂时无生产价值的能力；
- 仅仅把 API 调用、下载、队列和重试自动化。

---

# 2. Canonical Business Mainline｜PATCHED / FROZEN

## 2.1 主线定义

产品 Mainline 必须代表“从业务输入到最终广告视频交付”的真实生产链路，而不是只代表底层任务编排。

当前业务主链路冻结为：

```text
Product / Source Assets
+
Production Requirements
↓
Multi-image / Candidate Asset Generation
↓
Per-asset Quality Decision
↓
Qualified Assets Only
↓
Video Generation
↓
Automatic Editing / Assembly
↓
Final QA / Approval
↓
Deliverable
```

如果 L1 / L2 对具体资产阶段已有更精确的冻结定义，以 L1 / L2 为准，但不得把 Mainline 缩减成单纯的：

```text
Job Creation
→ Queue
→ Retry
→ Download
→ Recovery
```

## 2.2 基础设施的正确位置

以下能力是 **Production Enablement / Infrastructure**：

```text
Job Creation
Asset Binding
Prompt / Parameter Handling
Generation Submission
Queue / Waiting
Download
Failure Retry
State Tracking
Recovery
Partial Success
Traceability
Result Organization
```

这些能力非常重要，但它们的作用是支撑 Mainline。

因此：

> **Infrastructure Ready ≠ Production Loop Ready ≠ Production Ready**

---

# 3. Mainline / Supporting / Assurance 层级｜FROZEN

```text
PROJECT GOAL
更多真正可交付视频
+ 更少人工
+ 合理成本
+ 关键质量受控
↓
BUSINESS MAINLINE
Source Assets
→ Candidate Assets
→ Quality Decision
→ Qualified Assets
→ Video Generation
→ Auto Editing
→ Final Delivery
↓
PRODUCTION ENABLEMENT
Job / Queue / Retry / Recovery / State / Provider / Download / Traceability
↓
SUPPORTING
QA / Decision / Repair / Regeneration / Editing optimization / Provider optimization
↓
ASSURANCE
Benchmark / Annotation / Regression / Shadow / Acceptance
```

规则：

- 下层不得反向定义上层；
- 基础设施不能替代业务闭环；
- QA / Benchmark 不能替代产品；
- Supporting / Assurance 若连续扩张，触发 Project Re-anchor。

---

# 4. Deliverable Definition｜NEW / FROZEN

## 4.1 状态必须严格区分

```text
GENERATED
≠
TECHNICALLY_VALID
≠
QUALITY_CHECKED
≠
APPROVED
≠
DELIVERABLE
```

## 4.2 Deliverable 正式定义

`DELIVERABLE` 仅表示：

```text
满足当前任务类型全部 Required Hard Gates
AND
通过当前阶段规定的最终批准机制
AND
结果已进入正式交付集合
```

## 4.3 Ground Truth 规则

当某 Required Hard Gate 尚未达到 `MACHINE_VERIFIED`：

```text
Final Human Approval
=
该 Gate 的当前 Delivery Ground Truth
```

因此：

- 技术 QA PASS 不能自动等价于 Deliverable；
- 文件可播放不能自动等价于 Deliverable；
- 模型生成完成不能自动等价于 Deliverable；
- 只有已验证的机器 Gate 才能逐步替代人工批准。

---

# 5. Required Hard Gates｜NEW / FROZEN FLOOR

所有服装广告任务至少包含：

```text
1. PRODUCT_FIDELITY
2. HUMAN_CRITICAL
3. TECHNICAL_CRITICAL
```

任务类型需要时追加：

```text
4. TEMPORAL_CRITICAL
5. TASK_SPECIFIC_CRITICAL
```

Cinematic / aesthetic preference 默认不是全局 Hard Gate，除非 L1 / L2 对某任务类型明确规定。

## 5.1 Gate 状态

每个 Gate 只能是：

```text
MACHINE_VERIFIED
HUMAN_REQUIRED
NOT_APPLICABLE
UNAVAILABLE
```

规则：

- 没有可靠机器能力，不得伪造 PASS；
- `HUMAN_REQUIRED` 必须进入人工批准；
- `UNAVAILABLE` 若属于 Required Hard Gate，则禁止 Zero-touch；
- `ZERO_TOUCH_ELIGIBLE` 只对指定任务类型成立，不得全局泛化。

## 5.2 PRODUCT_FIDELITY 最小语义

Product Fidelity 至少覆盖对商品事实有重大影响的错误，例如：

- 主要颜色明显错误；
- 印花 / 图案明显错误；
- Logo / 文字明显错误；
- 服装结构、版型或关键部件被错误改变；
- 商品主体被替换或严重变形；
- 与 Product Source of Truth 明显冲突的关键外观。

不要求在开发前把所有商品语义 QA 自动化。

在机器能力未验证前：

```text
PRODUCT_FIDELITY = HUMAN_REQUIRED
```

即可。

---

# 6. Stage Model｜PATCHED

## Stage 0｜BASELINE READY

建立改造前真实基线，并完成必要 measurement instrumentation。

## Stage 1A｜PRODUCTION INFRASTRUCTURE READY

证明底层生产基础设施可可靠运行：

```text
Job Creation
Asset Binding
Prompt / Parameter Handling
Submission
Queue
Download
Retry
State Tracking
Recovery
Partial Success
Traceability
Result Organization
```

Stage 1A 目标：

> **让人不再充当 API 操作员。**

但 Stage 1A 不得声明 `Production Loop Ready` 或 `Production Ready`。

## Stage 1B｜PRODUCTION LOOP READY

必须用真实或生产等价任务跑通：

```text
Input / Source Assets
↓
Candidate Asset Production
↓
Per-asset Quality Decision
↓
Qualified Assets Only
↓
Video Generation
↓
Automatic Editing / Assembly
↓
Final QA / Approval
↓
Deliverable
```

最低要求：

- 不合格资产不能无条件进入后续视频生成；
- 资产选择结果可追溯；
- 视频生成使用的资产与对应 Job / Variant 一致；
- 自动剪辑真实执行，而非占位接口；
- 最终结果进入明确 Deliverable 状态；
- 尚未 Machine Verified 的 Hard Gate 有人工批准路径。

## Stage 2｜ASSISTED QUALITY READY

加入经过验证、低成本、高确定性的 QA，主要目标：

- 减少坏结果进入交付；
- 减少人工检查时间。

## Stage 3｜AUTOMATED REWORK READY

只对已验证场景开放：

```text
BASIC_EDIT
REGENERATE_VIDEO
REGENERATE_SEGMENT（仅有真实经济价值时）
FINAL_QA
```

## Stage 4｜ZERO-TOUCH ELIGIBLE

仅当指定任务类型全部 Required Hard Gates 已满足：

```text
MACHINE_VERIFIED
or
NOT_APPLICABLE
```

且真实 Pilot 证明质量、成本、可靠性可接受，才能开放。

---

# 7. BASELINE-0｜PATCHED / FROZEN

最低记录：

```text
Production Job Count
Generated Asset / Video Count
Final Deliverable Count
First-pass Deliverable Rate

Human Submit Time
Human Download / Retry Time
Human Review Time
Human Rework Time
Human Minutes per Deliverable

Average Waiting Time
Failure Rate
Regeneration Rate

Generation Cost
Cost per Deliverable

Critical Quality Escape Rate
Product Fidelity Failure Rate
```

## 7.1 两个质量基线怎么得到

如果历史系统没有结构化 QA 数据：

- 不得伪造；
- 从一批真实当前生产结果抽样；
- 使用当前业务人员的实际交付判断作为 Ground Truth；
- 记录样本量、判断规则和时间范围；
- 样本只需足以形成可比较的 Baseline，不要求先建设完整 Benchmark。

如果旧数据不足：

```text
BASELINE_DATA_MISSING
```

同时在新 Pilot 建立 measurement instrumentation。

## 7.2 没有完整基线时

可以继续实施 Production Core Automation，但：

- 不得宣称效率已经提升；
- 不得宣称质量没有退化；
- 不得冻结虚假的改善百分比。

---

# 8. P0 Metrics｜FROZEN

四个一等指标保持：

```text
P0-1 Deliverable Production Throughput
P0-2 Human Minutes per Deliverable
P0-3 Cost per Deliverable
P0-4 Critical Quality Escape Rate
```

补充诊断指标：

```text
Product Fidelity Failure Rate
First-pass Deliverable Rate
Average Time to Deliver
Regeneration Rate
```

这些用于解释问题，但默认不反向扩张架构。

---

# 9. Production Core Acceptance｜PATCHED

## 9.1 Infrastructure Acceptance

至少证明：

- 批量 Job 正常运行；
- 素材不串任务；
- Variant 失败隔离；
- Provider timeout / rate limit / network failure 正确落状态；
- Download failure 独立重试；
- Idempotency 防止无控制重复付费；
- Process Restart 不无条件重做已完成生成；
- Partial Success 正确交付；
- Attempt / Asset / Provider Result 可追溯；
- 自动结果整理完成。

## 9.2 Business Loop Acceptance

至少证明：

- 真实资产生产链路完整跑通；
- Per-asset QA / Approval 有真实执行；
- Failed / Rejected Asset 不会进入 Qualified Asset Pool；
- Qualified Asset 才能进入对应视频生成；
- 自动剪辑 / Assembly 真正完成；
- Final Approval 产生正式 Deliverable；
- Deliverable 指标来自真实批准结果，而不是技术成功状态。

两组验收都通过，才允许：

```text
PRODUCTION_LOOP_READY
```

---

# 10. Pilot Ground Truth Rule｜NEW / FROZEN

Real Batch Pilot 阶段：

> **所有尚未 `MACHINE_VERIFIED` 的 Required Hard Gate，必须通过人工审核产生 Ground Truth。**

因此 Pilot 同时产生：

```text
Production Evidence
+
Quality Ground Truth
+
Failure Evidence
+
Human Minutes
+
Cost Evidence
```

禁止：

```text
机器不会检测某类错误
→ Failure Pool 没记录
→ 推断该类错误不存在
```

这是 measurement blind spot，必须避免。

---

# 11. Failure-driven Improvement｜PATCHED

最小 Failure Pool：

```text
asset_id
error_category
severity
action_taken
final_outcome
```

保持不膨胀。

但 `asset_id` 必须可稳定反查：

```text
Job
Variant
Attempt
Source Assets
Product Reference
Prompt / Config Version
Provider
Model Version
Generation Result
Final Delivery State
```

上述信息可存在主数据模型 / Traceability 中，不要求重复写入 Failure 表。

Failure Pareto 仍按：

```text
Frequency
Deliverable Loss
Human Minutes
Extra Cost
Extra Latency
Critical Quality Risk
Improvement Feasibility
```

每轮只选择 Top 1–3。

---

# 12. QA / Benchmark Policy｜FROZEN

早期优先便宜、稳定、可机械验证的 Technical QA：

- file readable；
- corruption；
- black / frozen frame；
- duration；
- resolution；
- FPS；
- decode failure；
- cheap stable anomalies。

Product / Human / Temporal 自动 QA：

只有当以下之一成立时进入开发：

1. Pilot 表明它是高价值人工成本来源；
2. Failure Pareto 表明它是高价值质量风险；
3. 当前人工 Gate 是 Zero-touch 的主要阻塞；
4. 候选机器方案能被最小 Controlled Benchmark 验证。

Benchmark 永远是决策工具，不是主产品。

---

# 13. Advanced Capability Entry Gate｜FROZEN

VLM、Garment QA、Human Anomaly、复杂 Temporal QA、VTON、Segment Regeneration、Dynamic Provider Routing 等只有同时满足：

```text
1. Failure Pareto / Human Cost 证明它是高价值缺口
2. Cheap / Existing 方法明显不足
3. 候选方案可验证改善
4. 成本、时延、误报、维护复杂度可接受
5. 没有更简单的 Prompt / Rule / Provider / Full Regeneration 替代
```

否则：

```text
DEFER / BACKLOG
```

---

# 14. Repair vs Regenerate｜FROZEN

```text
cheap + stable + low-risk edit
→ BASIC_EDIT

full regeneration cheaper / faster / more reliable
→ REGENERATE_VIDEO

segment regeneration has proven economic value
→ REGENERATE_SEGMENT

low confidence / high risk / repeated failure
→ HUMAN_REVIEW
```

任何 Repair / Regeneration 后必须 Final QA。

---

# 15. Business Acceptance｜PATCHED

BASELINE-0 后再冻结具体数字。

正式结构：

```text
至少一个 P0 效率指标达到预设改善目标
AND
Critical Quality Escape Rate 不超过允许预算
AND
Product Fidelity Failure Rate 不发生不可接受退化
AND
其他 P0 指标退化不超过允许预算
```

所有“Deliverable”必须使用本合同第 4 节定义。

禁止：

- “视频生成数增加”直接等同“可交付产能增加”；
- “Technical QA PASS”直接等同 Deliverable；
- “整体感觉不错”作为商业验收。

---

# 16. Completion Claim Gate｜PATCHED

统一状态：

```text
TASK_DONE
FUNCTIONALLY_VERIFIED
INTEGRATION_VERIFIED
INFRASTRUCTURE_READY
PRODUCTION_LOOP_READY
PILOT_READY
TARGETED_QUALITY_VERIFIED
PRODUCTION_READY
ZERO_TOUCH_ELIGIBLE
```

含义：

- `TASK_DONE`：实现完成 + 对应自动测试；
- `FUNCTIONALLY_VERIFIED`：真实功能与关键失败路径通过；
- `INTEGRATION_VERIFIED`：关键模块、状态、恢复通过；
- `INFRASTRUCTURE_READY`：Stage 1A 通过；
- `PRODUCTION_LOOP_READY`：Stage 1B 业务链路真实跑通；
- `PILOT_READY`：可进入真实小批量；
- `TARGETED_QUALITY_VERIFIED`：指定质量能力通过对应验证；
- `PRODUCTION_READY`：目标生产负载下 P0、可靠性、完整生产链和必要质量约束通过；
- `ZERO_TOUCH_ELIGIBLE`：指定任务类型 Required Hard Gates 已可机器可靠判断。

严格禁止：

```text
Code Complete == Production Ready
Infrastructure Ready == Production Ready
Generated == Deliverable
Technical QA PASS == Deliverable
```

---

# 17. Existing System Audit｜CURRENT ENTRY

下一阶段仍然从 Existing System Audit 开始。

重点检查：

```text
1. L1–L4 最新冻结合同是否能定位
2. 当前真实业务生产链是否与合同一致
3. Job / Variant / Attempt / Asset 关系
4. Source Asset / Product Reference 绑定
5. Candidate → Qualified Asset 的真实状态
6. QA / Human Approval 是否真实执行
7. Qualified Assets 是否才进入 Video Generation
8. Auto Editing 是否真正实现
9. Final Delivery 状态与 Deliverable 定义
10. Queue / Retry / Recovery / Idempotency
11. Provider / Model / Prompt / Config Traceability
12. 当前 BASELINE 数据是否存在
13. 是否已有未被发现的 Measurement Blind Spot
14. 测试是否只验证 Mock
15. secrets / security / data integrity 风险
```

先审计，不重写。

---

# 18. Gap Analysis｜FROZEN

每个 Gap：

```text
Contract Requirement
vs
Existing Evidence
vs
Gap
vs
Risk Scope
vs
Action
```

风险：

```text
BLOCKING
GUARDED
NON_BLOCKING
```

动作：

```text
KEEP
ADAPT
REPLACE
REMOVE
DEFER
```

优先规则：

- 已可靠工作的默认 KEEP；
- 小修改能满足合同则 ADAPT；
- 结构性不满足且替换收益明显才 REPLACE；
- 重复 / 废弃 / 危险才 REMOVE；
- 非当前 Mainline 高级能力 DEFER。

---

# 19. Current Critical Path｜FROZEN

```text
Locate Contracts
↓
Existing System Audit
↓
BASELINE-0 / Measurement Instrumentation
↓
Gap Analysis
↓
KEEP / ADAPT / REPLACE / REMOVE
↓
Stage 1A Infrastructure
↓
Stage 1B Business Production Loop
↓
Functional / Integration / Recovery Verification
↓
Pilot Readiness
↓
Real Batch Pilot with Human Ground Truth
↓
Failure Pareto
↓
Top 1–3 Improvement Tasks
↓
Controlled Benchmark only when a decision needs it
↓
Expand Automation Authority
```

---

# 20. Stop Rule｜FROZEN

当：

```text
当前阶段 Acceptance 已达到
+
不存在更高价值 Critical Path blocker
+
新增研究 / 模型 / QA / Benchmark 不会显著改变 P0 或 Critical Quality
```

立即停止继续扩展。

以下不是继续开发的理由：

- 又发现一个模型；
- 又发现一个 GitHub 项目；
- 架构还能更漂亮；
- QA 还能更完整；
- Benchmark 还能更大；
- 文档还能更复杂。

---

# FINAL STATUS

```text
PRODUCT NORTH STAR: FROZEN
BUSINESS MAINLINE: RE-ANCHORED
INFRASTRUCTURE ROLE: CORRECTED
DELIVERABLE DEFINITION: FROZEN
REQUIRED HARD GATE FLOOR: FROZEN
BASELINE QUALITY METRICS: PATCHED
PILOT HUMAN GROUND TRUTH: REQUIRED
FAILURE TRACEABILITY: PATCHED
ADVANCED QA / BENCHMARK: EVIDENCE-GATED
NEXT ACTION: EXISTING SYSTEM AUDIT
```
