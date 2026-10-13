# Sprint Report：Reality Evidence Rules

日期：2026-10-13
状态：testing 实现、专项验证和实际 main 局部同步完成；未部署、未调用 Provider、未写生产数据。

## 完成

- 保留现有 Reality 六维和 Reality Loop 顺序：
  `Camera → Lighting → Composition → Human Behavior → Environment → Imperfection`。
- 新增版本化 `reality-evidence.v1` 规则库，作为 Creative Package 的知识层：
  每维包含所需上下文、生成约束、判断标准、质量复修模块和因果变量。
- 将 Nano Banana 实测规律吸收到六维：
  人物行动因果、摄影者意图、主体与环境空间关系、环境使用痕迹，以及相机/人物/材料/场景四类可解释缺陷。
- 将规则快照、版本和内容哈希冻结进新 Package 的 Prompt Registry。
- 将规则约束带入新 Package Prompt 和 `qualityChecklist`；旧包仍使用已有冻结合同。
- 修复 E1 Preservation 校验重建默认 Reality 决策的问题：校验已冻结的 Camera/Reality 决定，避免丢失方向中的摄影者意图。

## 边界

- 规则是生成指导和人工审查标准，不是观测事实、像素质量结论或自动 `QUALIFIED`。
- `imperfection=none` 继续合法；不会默认给商品添加污渍、褪色、磨损、模糊或滤镜颗粒。
- 没有新增 Reality Layer、Spatial Layer、Agent、数据库表、迁移、Provider 调用或生产提交。
- 旧 Registry 没有新规则 manifest 时保持兼容，状态仍是未证明；新包若声明规则却发生缺失、漂移或哈希不一致则阻断合同。

## 修改

- 新增 `backend/src/libtv_agent/creative/reality_evidence.py`。
- 扩展现有 `creative/workflow.py`、`text_contract.py`、`package_contract.py`、
  `creative_workflow.py` 和 `creative_reality_loop_gate.py`。
- 新增 `backend/tests/test_reality_evidence.py`，补充规则顺序、哈希冻结、规则漂移和 Registry 合同测试。
- 更新 Creative Package 合同测试和本报告；未扩展前端工作区。

## 测试

- testing 专项后端回归：118 项通过。
- testing scoped Ruff：通过。
- testing scoped `git diff --check`：通过；仅有 Windows LF/CRLF 转换提示。
- 未执行真实 Nano Banana、图片 Provider、付费调用或正式站点浏览器验收。

## 发现与限制

- 当前规则来源是 2026-10-13 用户提供的 Nano Banana 实测总结，快照明确标记为启发式、未独立像素验证。
- 规则会改善 Prompt 和人工检查的结构化程度，但不能据此承诺所有商品、人物或场景的真实性提升。
- Canonical Creative State 继续遵守 2026-10-13 排程冻结；本轮未增加 State 字段。

## 下一步

- 在真实样本获得人工方向和预算授权后，观察这些规则是否能减少 `human_capture`、
  `spatial_light_integration` 和商品细节相关返工；记录样本、缺陷和停止原因。
- 若要把规则用于真实 Critic，仍需先验证模型能接收原图/输出像素并返回区域证据。
