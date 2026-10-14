# Sprint Report：导演台商品背面上传

日期：2026-10-14
范围：Director Studio 商品输入增加可选背面参考，并接入任务证据链。

## 完成

- 正面保持必填，背面作为可选输入；正面单图流程保持可用。
- 前端上传预览、替换入口、禁用状态和移动端布局已完成。
- 后端接收 `back` 文件，复用正面文件校验规则，分别保存对象引用和哈希。
- 任务快照保留 `product_assets.front/back`；产品版本来源、幂等指纹和分析 Grounded Claim 包含背面证据。
- 分镜产品参考解析优先复用导演任务已上传的背面，旧的 `StagedUpload` 路径保持兼容。

## 修改

- `frontend/src/features/director-studio/DirectorStudio.tsx`
- `frontend/src/features/director-studio/directorApi.ts`
- `frontend/src/features/director-studio/directorModel.ts`
- `frontend/src/features/director-studio/directorEvidence.ts`
- `frontend/src/features/director-studio/directorStudio.css`
- `backend/src/libtv_agent/api/creative_workflow.py`
- `backend/src/libtv_agent/creative/workflow.py`
- `backend/src/libtv_agent/services/creative_workflow.py`
- `backend/src/libtv_agent/services/creative_provider_requests.py`
- `backend/tests/test_creative_workflow.py`
- `frontend/src/features/director-studio/directorApi.test.ts`
- `frontend/src/features/director-studio/DirectorStudio.browser-check.mjs`
- `docs/contracts/creative-workflow-api.v1.md`

## 测试

- 前端导演台定向测试：3 个文件 / 25 项通过。
- 后端 `test_creative_workflow.py` 正面闭环与背面上传用例：2 项通过。
- 后端 `test_director_keyframe_execution.py` 原始展示面证据保护用例：3 项通过。
- 前端 lint、TypeScript build 通过。
- 导演台隔离浏览器检查：1440、1024、768、390 四个视口通过；每个视口 19 个命令，外部请求为 0。
- 浏览器证据目录：`E:/Codex/visualizations/2026/10/14/director-back-upload-testing-3/`。

## 发现与限制

- 默认 Python 环境没有 `pytest`；后端用项目现有隔离环境执行。
- 当前流程仍遵守离线 Fake 与人工审核边界；本次没有调用真实 Provider、写入生产数据或部署服务。
- 已上传背面会随任务锁定；任务创建后不提供覆盖旧快照的替换操作，后续版本化修改仍应创建新任务。

## 下一步

- 在正式 API 连接环境中复核任务恢复后的背面证据展示。
- 若要让已完成任务补传背面，需要单独设计版本化更新合同和受影响镜头重新审核流程。
