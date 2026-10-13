# Sprint 5 Report: Controlled Production Adapter

日期：2026-10-13（Asia/Shanghai）  
范围：Creative Package 到既有图片/视频生产输入的受控适配与单样本验收  
状态：适配器和隔离合同完成；真实样本未执行，未部署。

## 完成

- 新增 `backend/src/libtv_agent/services/controlled_image_adapter.py`，把已确认
  Creative Package 和既有 `CreativeImageProviderRequest` 编译为一个
  `ImageBatchManifest` 输入。
- 新增 `backend/src/libtv_agent/services/controlled_video_adapter.py`，把一个
  已合格图片输出和既有 `CreativeVideoProviderRequest` 编译为一个
  `VideoTaskCreate` 输入。
- 新增纯合同模块 `backend/src/libtv_agent/creative/controlled_production.py`，
  固化两个适配器的单样本组合关系。
- 固化一个 Product、一个 image task 和一个 video task 的组合关系。
- 允许 image/video 两个 adapter entry 归属于同一个父 `CreativeTask`；通过
  不同 shot 和 idempotency key 保持两个生产请求可区分。
- 固定图片镜头为 `FIRST_FRAME`，视频镜头为 `SHOT_01`；批量、循环、多镜、
  Provider 执行、部署和付费副作用均在合同层阻断。
- 图片适配器保存 `creativeStateRevision`、`packageId`、`productAssetHash`、
  `promptSnapshot`、Brand DNA `profileId/version`、幂等键和 request hash。
- 视频适配器保存源图片 output ID/hash、`shotId`、package lineage、
  revision lineage 和 creative task ID。
- 单样本合同将图片/视频 adapter 的 request identity、package revision、shot、
  source mapping、idempotency key、bridge validity token、evidence hash 和
  request hash 组合成确定性的可审计 manifest。
- 没有修改数据库、API、任务状态、Provider executor、账本、配额或 offline
  boundary。

## 当前接线位置

Sprint 5 位于既有 Creative Workflow / human review / CRB5 准备证据之后，
处于 provider request 与未来受控执行之间的只读适配层：

```text
Creative Workflow + human review + bridge preflight
    -> creative_provider_requests.py
       CreativeImageProviderRequest
         -> controlled_image_adapter.py
            -> ImageBatchManifest input
       CreativeVideoProviderRequest
         + qualified image output
         -> controlled_video_adapter.py
            -> VideoTaskCreate input
    -> controlled_production.py lineage projection
       -> controlled-production-manifest.v1
    -> 未来另行批准的执行接线
```

`backend/src/libtv_agent/services/creative_provider_requests.py` 仍是
provider request 合同的唯一真源，继续拥有 provider/model、adapter 参数、
reference 顺序、request/evidence hash、幂等键以及固定的
`actual_submitted=false`、`provider_submission_allowed=false` 等边界。
两个 adapter 只生成旧 API 所需的输入形状；不调用旧 API，也不提交任务。
单样本合同只使用这些 request 的 identity projection 建立 lineage 关系，
不复制 provider request 字段，不重新定义生产状态，也不把 manifest 当成
提交许可。

图片旧 manifest schema 当前强制要求 `paidSubmissionConsent=true`。图片
adapter 保留这个字段只是为了满足旧输入模型，同时额外固定
`providerSubmissionAllowed=false`、`ordinaryOutputQualified=false` 和
`deliverableEligible=false`；adapter 不调用图片 API，因此该兼容字段不会
触发 Provider、扣费或任务创建。视频 adapter 直接输出
`paid_submission_consent=false`。

现有图片桥和 `director_fixed` 视频桥仍是只读 preflight；human review 的
QUALIFIED、普通 output qualification、最终批准和交付继续分开。当前
Fake/Replay 证据不能通过 Sprint 5 提升为真实生产资格。

## 输入契约

图片 adapter 输入：

- 一个已编译的 `CreativeImageProviderRequest`；
- 一个已确认的 Creative Package；
- 一个 owner、creative task 和可选的 creative state revision；
- 一个且仅一个 canonical product asset。

图片输出为一个 `controlled-image-batch-input.v1`，包含旧
`ImageBatchManifest`、一个 product reference、prompt snapshot、商品 hash、
Brand DNA snapshot、幂等键和 lineage 字段。

视频 adapter 输入：

- 一个已编译的 `CreativeVideoProviderRequest`；
- 一个资格为 `QUALIFIED`、scope 为 `PRODUCTION` 的图片输出；
- 一个且仅一个 `SHOT_01`；
- source image output ID/hash、candidate、batch/item、package lineage 和
  revision lineage。

视频输出为只读 `VideoTaskCreate` payload，并保留源图片 output ID/hash、
`SHOT_01`、package lineage、revision lineage 和 creative task ID。

顶层单样本输入为 `controlled-production-single-sample.v1`：

- `product`：单一 `product_id`、`product_version_id`、owner、原始来源 hash
  和来源引用；
- `image_task`：单一 image adapter lineage，必须是 `FIRST_FRAME`；
- `video_task`：单一 video adapter lineage，必须是 `SHOT_01`；
- `scope`：数量固定为 1，batch/loop/deploy/provider execution/paid 固定为
  false。

## 输出契约

校验成功返回 `controlled-production-manifest.v1`，包含：

- 单样本 ID 和 `SINGLE_SAMPLE` 范围；
- 单一 Product；
- image/video 两条 adapter lineage；
- 可重放的 source mapping 和 hash 关系；
- 对 manifest canonical JSON 计算的 `manifest_hash`。

该 manifest 是审计和后续接线输入，不是 API 响应、数据库记录、Provider
提交结果、计费凭证、资格结论或交付凭证。

## 测试

新增或更新：

- `backend/tests/test_controlled_image_adapter.py`
- `backend/tests/test_controlled_video_adapter.py`
- `backend/tests/test_controlled_production_contract.py`
- `backend/tests/test_controlled_production_adapter_integration.py`

覆盖：

- Creative Package 到图片 batch 输入的单产品、单任务、单 `FIRST_FRAME` 编译；
- 图片和视频 package/source/request 的 owner、task、hash、prompt、Brand DNA
  和 lineage 篡改阻断；
- 已合格图片到视频 task 输入的单 `SHOT_01` 编译；
- Package → image adapter → video adapter → single-sample manifest 的纯内存
  组合验收；
- 图片和视频适配器的 Fake、Replay、未合格、批量和多镜边界；
- 最小单样本成功、确定性 manifest hash 和 image/video lineage；
- 缺少必填任务字段；
- batch、loop、deploy、provider、paid scope 阻断；
- synthetic、paid、unknown input/cost/resolution 证据阻断；
- 顶层批量任务列表拒绝。

验证命令：

```powershell
$env:PYTHONPATH='backend/src'
python -m pytest `
  backend/tests/test_controlled_image_adapter.py `
  backend/tests/test_controlled_video_adapter.py `
  backend/tests/test_controlled_production_contract.py `
  backend/tests/test_controlled_production_adapter_integration.py `
  backend/tests/test_creative_provider_requests.py `
  backend/tests/test_creative_package_contract.py -q
python -m ruff check `
  backend/src/libtv_agent/services/controlled_image_adapter.py `
  backend/src/libtv_agent/services/controlled_video_adapter.py `
  backend/src/libtv_agent/creative/controlled_production.py `
  backend/tests/test_controlled_image_adapter.py `
  backend/tests/test_controlled_video_adapter.py `
  backend/tests/test_controlled_production_contract.py
```

testing 与实际 `main` 均完成上述专项复验：

- 图片适配器专项：16 passed；
- 视频适配器专项：12 passed；
- 单样本合同专项：14 passed；
- 合并专项命令：两侧各 122 passed；
- 两侧 scoped Ruff、`git diff --check` 和交付文件 SHA-256 校验通过。

## 未解决风险

- 真实 `CreativeImageProviderRequest` / `CreativeVideoProviderRequest` 的真实
  Provider、model、许可、quote、账本和 live 开关仍待 CRB5 请求级批准；本 Sprint
  没有制造这些值，也没有开启提交。
- 现有 provider request 合同当前仍是 dry-run/replay 与 offline-only 边界；
  lineage manifest 不替代未来真实执行合同，也不证明 at-most-once、UNKNOWN
  对账、崩溃恢复或输出物化。
- 真实输入的像素质量、人工资格、最终批准、交付和视频实产仍未验证。
- Product、package、task 和 output 的最终持久化关系仍由现有 adapter/service
  和数据库合同负责；本模块只校验传入的 identity projection。

## 人工测试步骤

1. 在隔离环境准备一个已确认 Product/ProductVersion、一个 image package、
   一个合格图片输出和一个 video package；确认 image 为 `FIRST_FRAME`、video
   为 `SHOT_01`。
2. 由现有 `creative_provider_requests.py` 生成图片和视频 request，保存各自
   request/evidence hash、幂等键和 source mapping。
3. 运行图片 adapter，检查 `ImageBatchManifest` 只有一个 product、一个 item、
   一个 FIRST_FRAME，并核对 state revision、package ID、商品 hash、prompt
   snapshot、Brand DNA version。
4. 将图片输出的 ID/hash、shot、package lineage 和 revision lineage 交给视频
   adapter，检查 `VideoTaskCreate` 只有一个 storyboard、一个 SHOT_01，并确认
   paid consent 为 false。
5. 将两个 adapter 的 identity projection 交给单样本合同，检查 manifest 中
   Product、两个 task、package revision、shot、source mapping 和
   `manifest_hash` 可审计且稳定。
6. 分别注入 batch、loop、deploy、provider、paid、multi-shot、synthetic、
   UNKNOWN 和字段缺失，确认校验失败且没有数据库/API/Provider 副作用。
7. 对照 human review、CRB5 readiness 和既有 image/video bridge 证据，确认
   manifest 不改变 QUALIFIED、交付、费用或 offline-only 语义。

真实样本未执行。未调用真实 Provider，未上传或付费，未写生产数据，未部署、
迁移或重启服务；当前结果仅是隔离纯合同与单元验收。

## 同步

本报告、三个 adapter/合同源码文件和四个对应测试文件按项目规则先在
`codex/testing` 验证，再逐文件同步到实际 `main`；同步时保留生产分支的其他
差异，不覆盖无关改动。最终同步结果已完成：八个文件均已逐文件复制到实际
`main`，SHA-256 一致；两侧专项测试、相关回归和 scoped Ruff 均通过。没有
同步其他源码、测试、文档、缓存、环境文件或生成物。
