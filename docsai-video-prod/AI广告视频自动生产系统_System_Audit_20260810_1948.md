# AI 广告视频自动生产系统｜System Audit / Gap / Critical Path

**审计时间：** 2026-08-10 19:48 +08:00

**恢复来源：** `AI-VIDEO-PROD-20260810-1712`

**执行治理：** UAP-AE/2.1（UAP-AE/2.0 作为项目历史输入）
**当前结果：** `PARTIAL / BUSINESS MAINLINE ADAPTED / PILOT NOT YET READY`

## 1. CONTRACT_STATUS

- 已定位并校验一致副本：L4 Production Acceptance v1.3、Codex Master Execution Prompt v1.1、Checkpoint 1712。
- 已定位并读取：UAP-AE/2.0 / `AE-DUALAXIS-EVENTGATE-20260809`；当前工作区上位 frozen canonical 为 UAP-AE/2.1。
- L1 Product & Scope、L2 Production、L3 Domain Model + Architecture 正文未存在于仓库、patched package 或 `C:\Users\Reel\Documents` 可检索范围，记录 `CONTRACT_GAP`。不得凭模型记忆补写。
- L4 v1.3 已冻结目标、业务主线、Deliverable、Hard Gates 与 Pilot Ground Truth，足以继续当前 Audit/ADAPT；L1–L3 缺失限制更强的 Production/Pilot 完成声明。

## 2. REANCHOR_RESULT

- Canonical Goal：以更少人工、合理成本、关键质量受控，生产更多真正可交付服装广告视频。
- Business Mainline：Source/Product Assets → Candidate Assets → Per-asset Quality Decision → Qualified Assets Only → Video Generation → Editing/Assembly → Final QA/Approval → Deliverable。
- Infrastructure（Job/Queue/Retry/Recovery/Download/State/Provider/Traceability）仅为 Enablement。
- 当前阶段：Stage 0 instrumentation + Stage 1B business-loop correction；不扩展 VLM、Benchmark、Annotation 或 Segment Regeneration。

## 3. EXISTING_SYSTEM_STATUS

### contract_map / repository_map / runtime_map

- FastAPI + SQLAlchemy/Alembic + React/Vite；372 个后端收集测试、146 个前端测试。
- 仓库已有 ParentTask → Variant → Attempt → Command/Artifact/Validation 的基础设施关系，以及 Image Batch → Item → Output 的图片生产关系。
- 正式版 `http://192.168.30.126:5173/` 的 `/api/v1/system/status` 可访问，但运行 `sourceRevision=3422174e...`、provider=`bach`；当前仓库 HEAD=`fe96e9c0...` 且含未提交修补，两者不是同一部署状态。
- 正式实例报告 `libtvExecutionMode=live`、付费开关开启，但当前仓库未被部署；本次未调用任何生成/写接口。

### business_production_flow / asset_lifecycle

- 图片中心可批量生成 Candidate Output，并由操作员在前端选片后送入视频制作。
- 审计前选片仅保存在前端草稿，没有持久化 Qualified/Rejected Ground Truth。
- 视频生成使用上传后的分镜/主体素材；Prompt/Config/Provider/Model/Attempt/Artifact 可追溯。
- 审计前 `aggregate_parent_phase()` 将“生成成功 + 下载 READY + 技术校验 PASSED/WARNING”直接聚合为 `DELIVERABLE`。
- 审计前点赞/点踩发生在交付之后，不能作为最终批准 Gate。

### infrastructure_flow / queue_and_concurrency / retry_and_recovery

- KEEP：幂等创建、Intent Hash、GenerationCommand、Runner claim、Unknown-after-submit、下载独立恢复、Partial/Failure isolation、积分预留与审计事件。
- 证据：相关模型、Runner Supervisor、恢复服务和现有集成测试均存在；本次没有将其升级为 Product Mainline。

### provider_integrations / editing_flow

- 仓库支持 LibTV/Kling/WaveSpeed 等适配路径；固定视频计划持久化 `cutMode`、`smartStoryboard`/`multiShot` 和编译 Prompt。
- 未发现独立、本地可验证的自动剪辑/Assembly 成品阶段；正式实例 provider 报告不支持多图。该项对 `PRODUCTION_LOOP_READY` 为 `BLOCKING_FOR_PILOT`，但不阻塞本次代码级业务 Gate 修补。

### persistence / partial_success / traceability

- KEEP：Asset/Variant/Attempt/Provider Result/Model/Prompt/Config/Artifact 关联可形成生成上下文。
- ADAPT：新增候选图片质量决定和视频最终批准字段，使 Failure/Ground Truth 可反查主体。
- Partial Deliverable 现在只计入已批准的变体；仅技术完成但未批准的变体不能形成 Deliverable。

### tests / observability / security_and_secrets

- 前端 lint、20 个测试文件 / 146 项测试、生产构建通过。
- 新鲜 SQLite 与 PostgreSQL offline migration 通过。
- 业务关键 JUnit 套件 49/49 通过，覆盖候选图片审核、强来源门禁、最终视频批准、状态聚合、BASELINE 指标及 OpenAPI；全量 372 项因集成测试耗时超过 20 分钟未取得完整 JUnit，不得声称全量 PASS。
- 当前正式运行实例与工作区版本漂移，且公开 system status 暴露较多运行配置；在部署/真实 Pilot 前必须完成受控部署身份核验和权限检查。

## 4. BUSINESS_MAINLINE_STATUS

- Candidate 质量决定：已由无持久状态 ADAPT 为 `PENDING / QUALIFIED / REJECTED`，并记录 Required Hard Gate Ground Truth、reviewer、时间和备注。
- Qualified Assets Only：图片中心送入视频队列前要求 `QUALIFIED`；服务端再次校验输出归属、人工状态与原始 SHA-256，并将 ImageOutput 外键延续到 StagedUpload/Asset。
- Final Approval：技术完成进入 `AWAITING_FINAL_APPROVAL`；Product Fidelity、Editing/Assembly 与 Human Critical 人工 PASS，加 Technical Critical machine PASS 后才写入 `DELIVERABLE`。Editing 人工 Ground Truth 不替代“自动执行路径”的生产证据。
- Deliverable 指标：改为从正式批准状态计数。
- Editing/Assembly：证据不足，未通过。

## 5. BASELINE_STATUS

历史 `var/development.db` 没有可查询业务表；正式实例数据库不可由当前仓库只读访问。因此：

```text
Production Job Count: BASELINE_DATA_MISSING
Generated Asset / Video Count: BASELINE_DATA_MISSING
Final Deliverable Count: BASELINE_DATA_MISSING
First-pass Deliverable Rate: BASELINE_DATA_MISSING
Human Submit / Download / Retry / Review / Rework Time: BASELINE_DATA_MISSING
Human Minutes per Deliverable: BASELINE_DATA_MISSING
Average Waiting Time / Failure / Regeneration: BASELINE_DATA_MISSING
Generation Cost / Cost per Deliverable: BASELINE_DATA_MISSING
Critical Quality Escape Rate: BASELINE_DATA_MISSING
Product Fidelity Failure Rate: BASELINE_DATA_MISSING
```

新增 `businessBaseline` instrumentation 自动输出上述可计算字段；无人工审核样本时明确返回 `BASELINE_DATA_MISSING`，不伪造 0% 质量失败。

## 6. MEASUREMENT_BLIND_SPOTS

- 历史人工 Submit/Download/Retry/Rework 时间没有结构化事件。
- 当前“成本”只能以 provider credits 记录，尚无稳定人民币/美元换算 Source of Truth。
- Critical Escape 当前只能由“已批准后收到带关键 reason 的 DISLIKE”识别；真实 Pilot 必须要求人工复核并写 Ground Truth。
- ImageOutput → StagedUpload → Video Asset 已形成强外键 provenance；浏览器上传的字节必须匹配已人工 QUALIFIED 输出的 SHA-256。
- 自动剪辑/Assembly 没有独立 artifact/evidence。

## 7. GAP_SUMMARY

| Contract Requirement | Existing Evidence | Gap / Risk Scope | Action |
|---|---|---|---|
| Technical PASS 不等于 Deliverable | 状态机直接写 DELIVERABLE | `BLOCKING_FOR_PRODUCTION_LOOP` | ADAPT（已实现） |
| Required Hard Gates + Human Ground Truth | 仅事后反馈 | `BLOCKING_FOR_PILOT` | ADAPT（已实现） |
| Candidate per-asset decision | 前端临时勾选 | `BLOCKING_FOR_PRODUCTION_LOOP` | ADAPT（已实现） |
| Qualified only | 前端可任意选择输出 | `BLOCKING_FOR_PRODUCTION_LOOP` | ADAPT（UI + 服务端归属/状态/哈希 Gate + 强 provenance 已实现） |
| BASELINE quality metrics | 无字段/历史数据 | `GUARDED_FOR_IMPLEMENTATION / BLOCKING_FOR_IMPROVEMENT_CLAIM` | ADAPT（instrumentation 已实现） |
| Auto Editing/Assembly | Prompt/cut settings，无独立成品证据 | `BLOCKING_FOR_PILOT` | DEFER implementation until L1–L3/production-equivalent path is confirmed; do not invent editor |
| Formal deployment identity | 正式实例 revision/provider 不同 | `BLOCKING_FOR_FORMAL_PILOT` | ADAPT deployment/re-audit |
| L1–L3正文 | 不存在 | `CONTRACT_GAP` | DEFER; blocks stronger architecture/acceptance claims only |

## 8. KEEP / ADAPT / REPLACE / REMOVE / DEFER

- KEEP：现有 Job/Variant/Attempt、Provider adapter、idempotency、retry/recovery、download、points、audit、auth、object store、technical validation。
- ADAPT：Candidate quality decision、Final Approval、Deliverable aggregation、Partial semantics、Ground Truth fields、BASELINE metrics、UI approval path、OpenAPI。
- REPLACE：无；未发现需要结构性重写的当前关键路径。
- REMOVE：无；未删除用户现有能力。
- DEFER：VLM/VTON/Benchmark/Annotation/Segment Regeneration/Dynamic routing；无 Pilot/Pareto 证据不进入 DAG。

## 9. ACTIVE_BLOCKERS

- `BLOCKING_FOR_FORMAL_PILOT`：正式实例不是当前工作区版本，尚未完成受控部署与迁移。
- `BLOCKING_FOR_PRODUCTION_LOOP/PILOT`：Automatic Editing/Assembly 的真实执行与证据未确认。
- `BLOCKING_FOR_PILOT_METRICS`：无真实批次及人工 Ground Truth 样本。
- 无需要立即询问用户的 Objective/Scope blocker。

## 10. PRODUCTION_CORE_TASK_DAG

```text
T01 Contracts/Re-anchor                       DONE
T02 Existing System Audit                    DONE
T03 BASELINE instrumentation                 DONE
T04 Candidate Quality Ground Truth           FUNCTIONALLY_VERIFIED
T05 Final Video Hard Gates + Approval         FUNCTIONALLY_VERIFIED
T06 Deliverable/Partial state correction      FUNCTIONALLY_VERIFIED
T07 Migration + OpenAPI + Frontend build      FUNCTIONALLY_VERIFIED
T08 Critical regression suite                PASS_WITH_LIMITATION (full suite timeout)
T09 Strong candidate→video provenance         FUNCTIONALLY_VERIFIED
T10 Editing/Assembly production-equivalent    BLOCKED_BY_EVIDENCE
T11 Formal deployment identity + migration    BLOCKED_FOR_FORMAL_PILOT
T12 Real Batch Pilot + human Ground Truth      BLOCKED_BY_T10_T11
T13 Failure Pareto / Top 1–3                  BLOCKED_BY_T12
```

## 11. MODEL / REASONING ROUTING

- Repository/contract audit：E3/A3，确定性搜索、diff、schema、runtime GET。
- State/data migration：E3/A3，SQLite fresh migration + PostgreSQL offline SQL + targeted integration tests。
- UI approval：E2/A2，沿用现有 React/design system，显式 Gate、不可误批准、可访问标签。
- Pilot quality：E2/A4，必须人工 Ground Truth；机器未验证 Gate 不得升级。

## 12. ACCEPTANCE_PLAN

1. 关键回归与 OpenAPI/迁移/前端检查稳定通过。
2. 在 production-equivalent provider 路径证明 Editing/Assembly 真正执行。
3. 受控部署当前 revision，迁移前备份并执行 restore rehearsal。
4. 小批量真实任务：每个非 MACHINE_VERIFIED Hard Gate 人工审核，记录 review minutes、cost、failure、deliverable。
5. 输出 Failure Pareto，只处理 Top 1–3。

## 13. NEXT_AUTONOMOUS_ACTION

```text
NEXT_AUTONOMOUS_ACTION = CONFIRM_EDITING_ASSEMBLY_EXECUTION_EVIDENCE
THEN = CONTROLLED_FORMAL_DEPLOYMENT_AND_RE_AUDIT
FORMAL PILOT = NOT AUTHORIZED BY CURRENT EVIDENCE
```
