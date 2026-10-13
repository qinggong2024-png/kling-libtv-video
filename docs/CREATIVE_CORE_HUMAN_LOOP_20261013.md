# Creative OS Core + Human Production Loop

日期：2026-10-13
依据：用户在主 PM 会话中提供的研发方向调整任务书。
状态：当前研发主线；取代继续扩展完整 Creative OS 的排程。

## 2026-10-13 工程状态

| 阶段 | 状态与证据 |
| --- | --- |
| Sprint 1 Package | testing/main 工程完成，见 SPRINT_REPORT_CREATIVE_PACKAGE_20261013.md |
| Sprint 2 Brand DNA | testing/main 工程完成，见 SPRINT_REPORT_BRAND_DNA_20261013.md |
| Sprint 3 Human Review | testing/main 工程完成，见 SPRINT_REPORT_HUMAN_REVIEW_20261013.md |
| Sprint 4 人工测试 | 合成球衣隔离验收通过，真实生产未验；见 SPRINT_REPORT_HUMAN_LOOP_ACCEPTANCE_20261013.md |

真实产品理解仍未接通，Director 图片/视频执行保持离线保护。
后续最小真实执行接线属于生产流程边界，先按上述 Sprint 4 报告提交决策；
不将工程测试或 main 源码同步称为完整交付、人工接受或上线。

## 目标

交付可人工生产验证的服装广告闭环：

```text
产品输入 → Creative Understanding → Creative Direction → Creative Package
→ 既有图片任务 → 既有视频任务 → 人工审核 → 经验记录
```

Canonical Creative State 保留为内部事实与智能层；Legacy Workflow 继续承担
执行；Adapter 连接两层。不要求旧模块全量迁移。

## 冻结

- 暂停继续扩展 State；已存在的基础能力保留。
- 不新增 Creative Memory / Spatial / Quality / Research Agent。
- 不重构 Kling pipeline 或 Provider abstraction。
- 不实施 CreativeTask 全量迁移或大规模数据库迁移。
- 不开发 ROI 自动优化、投放学习、全自动 Agent 或大规模自动生产。
- 真实样本执行留到 Sprint 4 / CRB-5；导出 Prompt 不授权付费提交。
- 既有身份、许可、幂等、预算、审核、UNKNOWN 和交付门继续有效。

## 顺序与验收

### Sprint 1：Creative Package

仅在选择一个服务端实际返回的方向后产生 Package。至少包含：

```text
direction, audience, characterDNA, sceneDNA, cameraDNA,
imagePrompt, videoPrompt, shotPlan, qualityChecklist
```

同时保留 package ID/revision、shot ID、商品事实版本、来源 SHA-256、
locks/preservation hash 和 origin evidence。

- 提供稳定 JSON 与团队可读文本，能复制给人工使用的 GPT Image、
  Nano Banana、Kling 工作流；不宣称完成上述 Provider 的 API 接入。
- 原始生产 Prompt 和哈希保持不变；派生建议须标注来源与待人工确认状态。
- 缺失字段如实保留，不猜测受众、产品事实或实物背面。
- FIRST_FRAME 与 VIDEO_STORYBOARD 的 package、选择、审核和来源独立。
- Fake/Replay 始终标记 OFFLINE_SYNTHETIC_ONLY，不提升为正式合格或交付。
- testing 验收后局部同步实际 main 并复验；不部署、不重启服务。

### Sprint 2：Brand Creative DNA

Sprint 1 验收后实施。先复用现有品牌/风格目录实现配置与读取，包括受众、
视觉场景、人物风格与禁用项，保留目录 ID、版本和内容快照。

- 不引入 Memory Agent 或自动学习。
- 人工品牌选择优先；目录更新不静默改变旧 Package。
- 若现有存储不能承载字段，先提交具体 API/数据合同差异，停止对应变更。

### Sprint 3：Human Review

Sprint 2 验收后实施：

- 图片：PASS / REWORK / FAIL；原因 FACE / GARMENT / REALISM / SPACE /
  LIGHTING / OTHER。
- 视频：PASS / FAIL；原因 MOTION / DEFORMATION / CAMERA / OTHER。
- 记录人工、时间、素材/任务/包版本和原因，保留历史，不自动学习。
- 反馈标签与生产资格分开；PASS 不自行替代 QUALIFIED 或 Deliverable。
- 优先复用既有审核记录。新增持久化字段/接口若超出旧合同，先明确评审，
  不静默迁移。

### Sprint 4：人工测试

用一个球衣案例检查三方向、选方向后的完整 Package、既有图片/视频任务
接线和人工反馈记录。

- 隔离测试可以先做；真实生成仍须精确样本、Provider/model、预算、
  许可、环境与人工授权。
- 真实费用和 UNKNOWN 对账规则明确后，才进行最终受控样本。
- 自动测试、源代码同步和离线测试不替代人工易用性及上线接受。

## 协作

- 本会话为主 PM，负责拆解、白名单、审查、验收和 testing → main 同步。
- 任务派到新独立窗口；不接管或改写原前端窗口的工作。
- Sprint 2/3 的只读审查可与 Sprint 1 并行；实现严格按 Sprint 顺序。
- API、数据模型或生产流程出现实质变化时停止对应实施，提交具体决策。
- 主 PM 按已完成行为和测试证据验收，不按文档数量或代码行数判断完成。
