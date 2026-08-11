# AI 广告视频自动生产系统｜L1 Product & Scope Contract v1.0

**状态：RECOVERED / CANONICALIZED / FROZEN**  
**恢复日期：2026-08-11**  
**层级：L1｜最高产品与范围合同**  
**优先级：L1 > L2 > L3 > L4 > Implementation Notes > Existing Code Behavior**

> 本文件用于补齐此前交付遗漏的 L1 独立正文。它不是重新设计产品。
> 内容依据历史正式综合合同《固定视频生产Agent正式方案_V4.3.1_生产合同修订版》、
> 后续 Acceptance / Production Acceptance 冻结规则及当前已验证项目主线恢复。
> 若旧综合合同与后续明确冻结规则冲突，以后续冻结规则为准。

## 0. 合同职责

L1 只回答：产品为谁解决什么问题、产品主目标、当前范围、明确不做事项、真正业务交付定义，以及不可被下层反向改写的边界。

L1 不负责数据库表结构、Provider SDK/CLI 细节、测试样例、Benchmark 设计或具体质量模型选择。

## 1. Product North Star｜FROZEN

唯一一级目标：

> **让跨境服装广告团队以更少人工、更合理成本、更稳定的方式生产更多真正可交付的 AI 广告视频，并随着真实生产证据逐步实现 Normal Case Zero-touch。**

“更多视频”必须解释为更多真正 Deliverable 的广告视频，而不是更多 API 成功、更多生成任务完成或更多技术检测 PASS。

## 2. 目标用户与使用场景｜FROZEN

主要用户：跨境电商服装广告创意 / 视频生产团队。

当前典型使用：

- 批量处理商品 / 场景 / 分镜等生产素材；
- 生成候选视觉素材；
- 对候选素材做必要质量判断；
- 只允许合格素材进入视频生成；
- 调用真实视频生成 Provider；
- 自动执行必要的 Editing / Assembly；
- 完成 Technical QA 与当前 Required Human Gates；
- 输出最终可交付广告视频；
- 记录失败、人工时间、成本和质量结果，用真实生产证据持续减少人工。

## 3. Canonical Business Mainline｜FROZEN

```text
Product / Source Assets
+
Production Requirements
↓
Candidate / Multi-image Asset Generation
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

规则：

1. 这是业务 Mainline；
2. Job / Queue / Retry / Recovery / Download / State / Traceability 属于 Production Enablement；
3. QA / Repair / Regeneration 属于 Supporting Capability；
4. Benchmark / Annotation / Regression 属于 Assurance；
5. 下层不得替代或扩大 Product Mainline。

## 4. Deliverable｜FROZEN

```text
GENERATED
≠ TECHNICALLY_VALID
≠ QUALITY_CHECKED
≠ APPROVED
≠ DELIVERABLE
```

`DELIVERABLE` 仅表示：

```text
满足该任务类型全部 Required Hard Gates
AND
通过当前阶段要求的最终批准机制
AND
正式进入交付集合
```

在机器质量能力尚未验证的阶段，Final Human Approval 是对应 Required Gate 的 Ground Truth。

严禁：

```text
Technical QA PASS == Deliverable
Provider Success == Deliverable
File Downloaded == Deliverable
```

## 5. Required Hard Gate Floor｜FROZEN

所有服装广告任务至少包含：

```text
PRODUCT_FIDELITY
HUMAN_CRITICAL
TECHNICAL_CRITICAL
```

按任务类型需要时追加：

```text
TEMPORAL_CRITICAL
TASK_SPECIFIC_CRITICAL
```

每个 Gate 的能力状态只能是：

```text
MACHINE_VERIFIED
HUMAN_REQUIRED
NOT_APPLICABLE
UNAVAILABLE
```

机器未被真实 Pilot / Controlled Benchmark 证明可靠时，不得自行升级为 `MACHINE_VERIFIED`。

Product Fidelity 至少覆盖：
- 主色明显错误；
- 印花 / 图案明显错误；
- Logo / 文字明显错误；
- 服装结构、版型或关键部件明显改变；
- 商品主体被替换或严重变形；
- 与已提供 Product / Source of Truth 明显冲突的关键外观。

## 6. 产品优先级｜FROZEN

```text
1. 真正可交付产能
2. 人工时间降低
3. 单条可交付成本
4. 关键质量不逃逸
5. 稳定性 / 可恢复性
6. 其他局部优化
```

核心 P0：

```text
P0-1 Deliverable Production Throughput
P0-2 Human Minutes per Deliverable
P0-3 Cost per Deliverable
P0-4 Critical Quality Escape Rate
```

局部技术指标不得反向成为产品目标。

## 7. 当前范围｜FROZEN

当前项目范围包括：

### 7.1 输入与生产准备
- 接收当前业务需要的 Product / Source Assets；
- 保存素材身份、归属、版本和 Hash；
- 记录生产要求；
- 形成可追溯的任务 / Variant / Attempt。

### 7.2 候选素材
- 支持系统产生或接收候选素材；
- 候选素材必须能进入明确的 `QUALIFIED / REJECTED` 判断；
- `REJECTED` 不得进入后续正式资产绑定。

### 7.3 视频生产
- 使用 Qualified Assets 调用当前批准的真实 Provider；
- Provider / Model / Config 必须版本化并可追溯；
- Provider 成功与业务交付状态分离。

### 7.4 Editing / Assembly
- 自动完成当前业务链所需的剪辑 / 拼接 / 编码 / Assembly；
- 必须存在真实 production-equivalent 执行路径；
- 不允许以占位接口代替实际执行。

### 7.5 QA / Approval / Delivery
- Technical Critical 可由已验证机器规则执行；
- Product Fidelity / Human Critical 等未机器验证 Gate 保持人工；
- Final Approval 产生正式 Deliverable；
- 支持 Partial Success，但只交付已满足 Gate 的结果。

### 7.6 可恢复生产
- 幂等；
- Retry 分类；
- Crash Recovery；
- Partial Success；
- 来源追溯；
- Runtime Revision 证据；
- 成本 / Provider Call 记录。

## 8. 当前明确不做｜FROZEN

除非真实 Pilot / Failure Pareto 触发，不进入当前 Critical Path：

- 完整 QA 平台；
- 完整 Benchmark 平台；
- 通用 Annotation 平台；
- 学术级视频质量评测；
- VLM 全量检测；
- VTON；
- Advanced Segment Regeneration；
- Dynamic Provider Routing；
- 自动学习全部 Prompt 策略；
- 通用 Agent 工具调用；
- 多 Agent 产品能力；
- 为架构完整而拆微服务；
- 与当前 P0 无明显关系的高级 Motion / Action 优化；
- 为使用新模型而增加模块。

## 9. Zero-touch 边界｜FROZEN

长期方向：`Normal Case Zero-touch`，但它不是当前 Pilot 的强制验收条件。

只有某一任务类型的全部 Required Hard Gates 均为 `MACHINE_VERIFIED` 或 `NOT_APPLICABLE`，且真实 Pilot 已证明质量、成本、人工介入和 Reliability 可接受，才允许标记 `ZERO_TOUCH_ELIGIBLE`。不得全局泛化。

## 10. 产品演进原则｜FROZEN

```text
Production
→ Ground Truth
→ Failure Collection
→ Failure Pareto
→ Top 1–3 High-value Gaps
→ Minimum Sufficient Improvement
→ Controlled Benchmark only if decision requires
→ Expand Automation Authority
```

禁止先建设完整 QA / Benchmark / 模型研究，再最后验证生产价值。

## 11. Authority Boundary｜FROZEN

Codex / PM 可自主决定普通技术实现、低风险重构、Retry/Repair 局部实现、测试、任务拆分及 KEEP/ADAPT/REPLACE/REMOVE/DEFER。

必须升级用户：
- Product Goal 改变；
- Scope 显著扩大；
- Required Hard Gate 被重新定义；
- 不可逆高影响生产操作；
- 高风险 Security / Authorization；
- Data Integrity 风险；
- 需要业务事实但没有可靠证据；
- 多次自主修复失败且会影响最终交付。

## 12. Completion Boundary｜FROZEN

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

禁止：

```text
Code Complete == Production Ready
Infrastructure Ready == Production Ready
Generated == Deliverable
```

# FINAL L1 STATUS

```text
PRODUCT NORTH STAR: FROZEN
BUSINESS MAINLINE: FROZEN
DELIVERABLE: FROZEN
SCOPE: FROZEN
NON-GOALS: FROZEN
REQUIRED HARD GATE FLOOR: FROZEN
ZERO-TOUCH AUTHORITY: EVIDENCE-GATED
```
