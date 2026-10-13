# Sprint Report · Creative Workflow MVP-3A

日期：2026-10-12
范围：真实图片/视频 Provider 执行前的 dry-run/replay 请求编译合同
testing：`E:/Projects/libtv自动化生成`，`codex/testing`
实际 main：`C:/Users/Reel/Documents/libtv-auto-main-sync`，`main`

## 完成

新增只读 `creative_provider_requests` 服务，复用 MVP-2B/2C bridge 的持久状态、
授权、人工审核/选择、Prompt/Preservation 和真实 batch/item/output 映射校验。
只编译不可变请求，不接入 API 或旧执行服务：

```text
现有 FIRST_FRAME / SHOT_01 bridge preflight
→ 再核对冻结文本合同、商品/账户状态和独立对象字节
→ 编译并冻结目标 Provider 参数、角色绑定和来源映射
→ 保存/恢复合同 JSON 后可重新读取持久证据执行 replay 校验
```

服务入口：

- `compile_creative_image_request`：图片请求编译。
- `compile_creative_video_request`：单镜 `director_fixed` 视频请求编译。
- `assert_creative_provider_request_current`：以原选项/运行模式重编译并比较合同。

图片合同包含 Provider、现有模型 ID、`mode=edit`、锁定 Prompt 及其 JSON SHA-256、
Preservation/锁项/文字合同哈希、Canonical Product 对象键及字节 SHA-256、
唯一 `PRODUCT → images` 角色/顺序绑定、task/package/candidate/batch/item/output 映射。
图片非媒体参数直接复用 `image_generations.build_prediction_payload`；
媒体对象键只用于判定 edit，返回前移除 `images`，避免把对象键伪装成媒体 URL。
未来 adapter 需要从独立 `references` 解析真实媒体，再补齐 `images`。

视频合同包含显式 Provider/model 选项、`execution_mode=director_fixed`、
锁定 `SHOT_01` storyboard Prompt、原商品/首帧/分镜对象键及哈希、双来源映射。
参考按现有官方 adapter 字段顺序冻结：
`FIRST_FRAME → first_frame_path`、`STORYBOARD → refer_image_paths`、
`PRODUCT → product_reference_paths`。
保留不同角色和输出 ID，不因当前 Fake 占位字节相同而去重角色。
非媒体参数沿用 `VideoGenerationRequest` 的 prompt/model/duration/aspect_ratio、
resolution/audio/multi_shot/fallback_mode/task_trace_id/external_task_id 字段；
没有调用旧 `compile_video_plan` 或 `apply_video_learning`，没有追加角色说明或改写 Prompt。

所有合同及嵌套参数/来源模型使用 frozen Pydantic；参考序列是 tuple，完整冻结文本
合同是 canonical JSON 字符串，避免嵌套 dict/list 可变。合同可序列化、恢复和比较。
`request_hash` 覆盖整个请求除其自身；`evidence_hash` 覆盖持久任务、商品/事实版本、
账户 role/is_active、CreativeRecord 与来源 batch/item/output 元数据。
对象存在性和真实字节哈希在重编译时复验，包括与原商品分离的分镜对象。

同一 `task/package/shot` 的逻辑身份固定，不加入时间或随机数，幂等键稳定。
选项、审核/选择、授权、锁定内容、状态或来源证据改变时，旧合同被拒绝或哈希改变；
相同幂等键的新内容不能自动当成第二次提交授权，未来入口须按现有 request-hash
冲突语义处理，并在正式提交前重新检查权限、授权、预算和能力。

`run_mode` 只接受 `dry-run` / `replay`；两种模式均固定：

- `actual_submitted=false`、`provider_submission_allowed=false`。
- `qualification_scope=OFFLINE_SYNTHETIC_ONLY`。
- `ordinary_output_qualified=false`、`deliverable_eligible=false`。
- `media_binding_required=true`、`provider_capabilities_verified=false`。
- 每个参考 `actual_submitted=false`、`provider_accepted=false`。

Fake/Replay 只是来源与合同验证。现有图片输出仍为 PENDING，不升级普通
QUALIFIED、不创建可交付结果、不生成假 URL、不创建新的任务/attempt/账本记录。
Canonical Product 许可仍为 UNVERIFIED，不声称已获得商用许可。

## 修改

仅新增三个白名单文件：

- `backend/src/libtv_agent/services/creative_provider_requests.py`
- `backend/tests/test_creative_provider_requests.py`
- `docs/SPRINT_REPORT_CREATIVE_WORKFLOW_MVP3A_20261012.md`

未修改 API、OpenAPI、数据库模型、migration、前端、`fixed_video_tasks.py`、
`image_generations.py`、bridge、共享协调表或 `.env`。两侧既有未提交改动均保留。
未进行提交、远程推送、生产数据库写入、迁移、服务重启或部署。

## 测试

testing：

- 初轮新测试 48 passed / 1 failed：视频 bridge 对授权过期使用既有合并错误码
  `AUTHORIZATION_SCOPE_INVALID`；修正测试期待，没有放宽拒绝条件或修改 bridge。
- 加固后组合选集 141 passed：新合同 56 项，既有相关回归 85 项。
- 最终新增独立分镜对象的缺失/错误字节两项后，新合同测试独立复验 58 passed。
  testing 最终证据为 58 项新合同和 85 项既有相关回归均通过。
- scoped Ruff：通过。
- `git diff --check` 及两个新增 Python 文件的 `git diff --no-index --check`：通过。

组合回归文件：

```text
backend/tests/test_creative_provider_requests.py
backend/tests/test_creative_image_bridge.py
backend/tests/test_creative_video_bridge.py
backend/tests/test_fixed_template_foundation.py
backend/tests/test_image_generation_batches.py
backend/tests/test_creative_workflow_storyboard.py
backend/tests/test_creative_media_isolation.py
```

测试通过现有 `scripts/run_creative_targeted_tests.py` 运行：隔离 SQLite/local
object store、独立临时运行目录、关闭真实付费开关并拒绝外网连接，不读取真实 `.env`。
新测试断言编译期间只有 SELECT、全表记录数不变，patch 旧生产入口、
Provider 上传/提交/验证及规划函数为负调用断言。
覆盖 dry-run/replay 的可重复编译和 JSON 恢复、深层不可变、Prompt/Preservation
篡改、存储文本合同替换、授权过期/变化、越权/停用账户、审核/选择变化、
UNKNOWN/stop/revocation、未物化、源哈希/映射/状态、普通资格非法提升、
源对象缺失/字节改变、事实许可状态改变及无版本号变化的来源元数据变化。

main：

- testing 通过后只同步三个白名单新增文件，在实际 main 源码上独立复验：
  143 passed（新合同 58 项，既有相关回归 85 项）。
- scoped Ruff、`git diff --check` 和三个白名单文件的
  `git diff --no-index --check` 均通过。
- 三个白名单文件 SHA-256 与 testing 一致，报告补齐证据后再次精确同步。
- 使用同一 Python 3.11 测试解释器，但 main 的测试路径、模块搜索路径、
  `pyproject.toml` 和隔离源码哈希独立来自实际 main。

testing 隔离证据：组合回归
`F:/Temp/creative-targeted-337khkxb/junit.xml`；
最终新合同复验 `F:/Temp/creative-targeted-5eukk9ra/junit.xml`。
main 独立证据：`F:/Temp/creative-targeted-9cu0ovv4/junit.xml`。

## 白名单与同步

同步已成功，testing 和实际 main 分支均已核对。只复制本包三个新增文件，
没有推广两侧其他窗口的未提交修改、密钥、缓存、运行时文件或测试生成物。
旧 `fixed_video_tasks.py` / `image_generations.py` 两侧源文件原本不同，
各自差异保持；bridge 源文件两侧一致且未改动。

源码 SHA-256（报告自身不写入其哈希，避免自引用）：

```text
creative_provider_requests.py
CD3BAE611EC5F834689DD2243A5071010BA3241B02D6523796C8DEA55C19A5B4
test_creative_provider_requests.py
B789334F5D4C284CEB800D7C6B42824AA381B9DD7C25268F68A40DB64B2FAAA9
```

## 发现问题

- image bridge 校验的首帧 text pointer 与 package_contracts 的存储位置不同；
  新模块额外校验将要绑定的存储文本合同及其不可变 CreativeRecord，避免从
  未验证的存储副本取出另一段 Prompt。旧模块未改。
- video bridge 的 validity token 不包含所有来源行元数据；新 evidence_hash 补齐
  这些字段，审核备注等仍合法的元数据变化也会使旧请求失效。
- ProductVersion 的既有事实摘要不包含 license/status，新增证据哈希包含实际
  商品/版本行；真实许可、Provider 能力和预算批准仍是后续真实提交的门。
- 全量历史迁移 integrity 的既存失败不属于本包；本轮未执行迁移或扩大修复范围。

## 下一步与限制

本包只是 dry-run/replay 请求合同。真实 Provider POST、真实上传/引用接收证据、
像素质量、费用/账本、生产部署及生产迁移均尚未完成。
视频选项是明确的拟提交配置，不声称所有列出的 Provider/model 已通过在线能力验证。
服务未持久化新的请求表，也没有真实提交的原子领取/预算预占/幂等落账；合同复验
不能代替未来提交时的事务门。PostgreSQL、多 worker 和跨进程崩溃尚未证明。
本轮无前端变更，不执行浏览器验收，不更新人工 Checkpoint 或生产就绪声明。

后续小包可在另行授权后实现 adapter 素材物化/绑定、能力/许可/预算预检、请求
持久化及真实提交边界；必须保留锁定 Prompt、来源、审核、UNKNOWN 和费用语义。
