# Sprint Report：Director Analysis Contract v1

日期：2026-10-13
范围：吸收 AI Fashion Creative Director v1.13.7–v1.13.13 的规划能力，并验证智能导演分析链路的必经步骤

## 完成

- 新增 `director-analysis.v1` 服务端合同，固定八步顺序：
  Product/Brand/Audience DNA、Scene/Reality/Spatial、Storyboard/Shot Mix Precheck、
  Key Visual Selector、Image Prompt/Motion-Ready、Model-Aware Video Strategy、
  Emotion/Video Prompt、Video QA/One-Fix。
- 每步保存 `status`、`depends_on`、`evidence` 和 `outputs`；合同校验固定 trace、
  连续序号、完整依赖链、商品哈希、事实版本和方向内容哈希。
- `analyze` 生成完整分析快照；方向选择产生新快照；授权和 `generate/revise`
  重新校验分析合同，缺失、重排、篡改、来源变化或方向不一致直接阻断；
  两次快照以 append-only 记录保存。
- 吸收空间规划、Reality 六维、商品展示、景别节奏、关键视觉、首帧可动性、
  视频情绪节拍和时间轴 One-Fix 的规则摘要。
- 视频策略保持 `strategy_unresolved`，要求后续提供具体型号、入口、账号能力和
  实际媒体证据；不会因为插件规则文件存在就宣称当前模型可用。
- 导演台显示八步服务端链路、每步状态和视频策略证据。

## 修改

- `backend/src/libtv_agent/creative/director_analysis.py`
- `backend/src/libtv_agent/services/creative_workflow.py`
- `backend/tests/test_director_analysis.py`
- `backend/tests/test_creative_workflow.py`
- `frontend/src/features/director-studio/directorApi.ts`
- `frontend/src/features/director-studio/DirectorPlanningViews.tsx`
- `frontend/src/features/director-studio/DirectorStudio.tsx`
- `frontend/src/features/director-studio/directorStudio.css`
- `docs/CHANGELOG.md`
- 本报告

## 测试

- 前端 `npm run build`：通过。
- 前端 `npm run lint`：通过。
- 前端 `npm run test`：56 个测试文件、398 项通过。
- 前端导演定向测试：11 个测试文件、68 项通过。
- 后端导演分析、Creative Workflow、Orchestrator、Reality Loop：58 项通过。
- `git diff --check`：通过；Windows 行尾转换提示不影响内容。
- 导演台隔离浏览器检查：1440、1024、768、390 四视口均通过，每个 18 个命令；
  检查八步面板、策略待核和证据展开。未调用 Provider、未扣费、未写生产数据。

## 发现问题

- 插件 v1.13.13 的模型能力表仍然是官方资料和规则快照，不能证明当前账号入口开放；
  因此服务端默认保留 `strategy_unresolved`。
- 当前工作流仍为 `OFFLINE_FAKE_ONLY`，Fake 候选、规划状态和静态规则不能提升为真实
  图片/视频质量、QUALIFIED 或 Deliverable。
- 八步合同保证分析顺序和前置依赖，不等于真实视觉模型已经执行每一步；真实模型调用
  与像素/视频时码 QA 仍需单独接入和授权。
- Ruff 已执行并通过；若生产目录依赖未安装，生产侧只能报告实际可运行的检查结果。

## 下一步

- 在人工确认和真实样本授权后，补充具体 Provider/型号/入口的能力快照。
- 真实视频可访问时接入时间码 QA 证据和 one-fix 反馈，保持一次只改一个主变量。
- 继续保留 Checkpoint 1、预算、许可、人工审核和旧视频模式兼容门。
