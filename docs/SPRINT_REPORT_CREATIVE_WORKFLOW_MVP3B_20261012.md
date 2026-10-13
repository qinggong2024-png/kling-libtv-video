# Sprint Report · Creative Workflow MVP-3B

日期：2026-10-12
范围：MVP-3A image/video 请求合同的只读 Provider 提交前预检与临时素材物化
testing：`E:/Projects/libtv自动化生成`，`codex/testing`
实际 main：`C:/Users/Reel/Documents/libtv-auto-main-sync`，`main`

## 完成

新增 `creative_provider_preflight` 服务，不接入 API 或旧图片/视频执行服务：

```text
MVP-3A 冻结请求
→ 验证 request_hash、重新读取持久来源并重编译 evidence_hash
→ 复核 owner/权限、ProductVersion、许可、人工 QUALIFIED + select、包与授权有效期
→ 检查离线能力声明和适配器本地限制
→ 检查独立人工 Provider 授权、报价、实际付费/暂停开关与数据库额度
→ 按 role/order 安全物化到临时目录，生成 adapter input manifest
→ 再次复核审批、来源与额度状态
→ READY_FOR_HUMAN_SUBMIT，仍不允许真实提交
```

入口：

- `preflight_creative_provider_request`：接收 MVP-3A image/video 冻结合同与服务端
  Settings、静态能力声明、独立审批 manifest 路径，返回结果和临时目录 lease。
- `assert_creative_provider_preflight_current`：重做预检与物化，核对旧结果的语义哈希、
  元数据和参考角色/顺序；旧临时目录关闭后也可以重新物化，不能继续使用失效路径。
- 调用方使用 `with` / `async with` 或显式 `close()` 清理 lease。每个角色使用独立
  临时文件，不因商品、首帧和分镜 Fake 占位字节相同而合并角色。

物化只使用已复验的对象键，不把本地路径、对象键或 `fake://` 伪装成 HTTP URL。
manifest 使用显式 `path` 字段，包含原角色、顺序、adapter 字段、object_key 和
SHA-256。兼容 LocalObjectStore 返回原文件及远端存储下载到指定目标的两种语义，
不修改或删除源对象。目录创建后的失败会清理本包临时目录。

`request_hash` 与 MVP-3A 当前合同比较；`evidence_hash` 由 MVP-3A 重新读取 task、
ProductVersion、账户、CreativeRecord、来源 batch/item/output 与对象字节计算。
因此审核/选择撤回、UNKNOWN、stop、源对象变化、许可/版本/账户或其他证据变化会
拒绝旧请求。额外要求商品事实版本 APPROVED 且许可 VERIFIED；不能以许可确认
代替事实审批。

新 `preflight_hash` 包含请求/证据哈希、完整能力声明、审批、费用输入、许可、
角色/哈希及当前 RuntimeConfig 与业务日额度。临时路径不进入语义哈希，因此重复
预检具有稳定幂等身份和哈希。审批、声明或额度状态改变时旧预检失效。
结果的 `expires_at` 记录 Provider 审批、报价和逐角色许可中的最短有效期；
原包/离线授权有效期继续由每次 source replay 检查，不替代提交前重验。

### 人工审批与许可真源

MVP-3A 的证据哈希覆盖整个 CreativeTask 快照和全部 CreativeRecord。新 Provider
授权需要绑定该哈希，若写回同一快照会形成循环依赖并使旧请求立即失效。因此本包
使用独立的 `creative-provider-approval.v1` 文件合同，不修改旧共享模型或迁移：

- 服务端提供可信的审批 manifest 路径；本包只读取，不创建/修改审批文件。
- 审批包含独立身份、revision、ACTIVE/REVOKED、人工授权、报价和逐角色许可。
- 人工 Provider 授权明确确认人/owner、task/package/shot、provider/model、
  request_hash/evidence_hash、确认时间、有效期、费用上限和币种。
- 报价明确绑定 provider/model 和两个哈希；包括上传费用、零提交重试、费用估计、
  币种、额度输入及有效期。费用超限、币种不匹配、费用未知或额度不足均阻断。
- 每个参考必须有独立角色许可，绑定 owner、确认人、对象键/哈希、provider、许可
  证据、输入用途和有效期。许可确认不会给 Fake 像素补真实质量或交付资格。

该文件是服务层独立审批真源的最小适配，不是已上线的人审 API、数字签名服务或
审批 UI。本包没有暴露接受任意客户端路径/声明的 API；后续接线必须从可信服务端
位置加载并保护审批写权限，不得把客户端上传 JSON 当成人工授权证据。

### 能力与预算

能力声明必须显式 VERIFIED，匹配 request kind/provider/model；检查参考数量、
完整角色和顺序、adapter 字段、Prompt 长度、画幅、分辨率、输出格式/质量，以及
视频 duration/audio。未知声明或缺失 duration 范围阻断，不做在线 discovery。

声明不能突破本地适配器约束：Kling 必须使用 `kling-3.0-omni`、明确支持的分辨率
和当前合同可表达的 `off` 音频；WaveSpeed 必须为 reference-to-video 模型，拒绝
会被旧适配器静默忽略的显式分辨率；Bach 不支持本合同的三角色输入，直接阻断。
这些检查不代表 Provider 已在线验证或实际接收素材。

不采用既有 Fake/test 快捷放行作为真实 Provider 授权。检查实际
`paid_generation_authorized`、Provider enable、Settings 与最新 RuntimeConfig 暂停
状态。图片使用现有业务日图片用量查询；视频检查同业务日 consumed/reserved/
uncertain 总量及配置额度，不写 reservation/ledger。AUDITOR、停用账户或越权阻断。
通过 `session.no_autoflush` 防止只读预检触发调用方未提交记录的隐式写入。

所有结果仍固定：

- `actual_submitted=false`、`provider_submission_allowed=false`。
- `qualification_scope=OFFLINE_SYNTHETIC_ONLY`。
- `ordinary_output_qualified=false`、`deliverable_eligible=false`。
- `capability_declaration_verified=true` 只表示静态声明校验；
  `provider_capabilities_verified=false` 保留未在线验证的事实。

## 修改

仅新增三个白名单文件：

- `backend/src/libtv_agent/services/creative_provider_preflight.py`
- `backend/tests/test_creative_provider_preflight.py`
- 本报告

没有修改共享文件、旧 image/video service、bridge、API、OpenAPI、模型、migration、
前端、协调表或 `.env`。两侧已有其他窗口改动保留。本包未提交/远程推送，也未
执行生产数据写入、生产数据库迁移、服务重启、部署或任何 Provider POST。

## 测试

隔离测试使用已有 `scripts/run_creative_targeted_tests.py`：独立 SQLite/local object
store、外部临时运行目录、关闭应用真实付费开关、外网连接拒绝，不读取真实 `.env`。
有效路径使用一个未挂载到应用/适配器的合成 Settings 输入检验开关；不改变实际
运行配置。测试 patch Provider 提交/上传/校验/discovery、旧生产入口、规划和账本/
预占函数为负调用断言，并验证 SQL 只有 SELECT、全表记录数不变。

testing 初轮：

- fixture 缺 RuntimeConfig 导致拒绝；只补隔离测试 fixture，不在预检中自动写库。
- 133 项新测试通过。
- 加入适配器/未知配置/no-autoflush 回归后，285 项组合测试通过。
- 商品事实 APPROVED 门与最终格式化之后的最终组合结果：286 passed，其中
  新预检 143 项、MVP-3A/bridge/fixed video/image 等既有相关回归 143 项。
- 新预检/MVP-3A/两个 bridge 的服务与测试 scoped Ruff：通过。
- `git diff --check` 与三个新增文件的 `git diff --no-index --check`：通过。
- testing 最终隔离证据：`F:/Temp/creative-targeted-yjyf3921/junit.xml`。
- main 初轮独立复验发现 fixture 写死视频额度单位 1；testing 配置为每次 1、每日
  100，main 原配置为每次 120、每日 5000。服务按实际配置阻断，未改共享配置或
  放宽门检。仅修正新测试 fixture，按各自配置生成报价和耗尽额度样本。
- 修正 fixture 后 testing 新测试再次独立 143 passed；证据：
  `F:/Temp/creative-targeted-28jkeufu/junit.xml`。服务源码保持最终 286 项组合复验
  时版本，既有 143 项相关回归不受仅测试 fixture 的调整影响。

组合回归白名单：

```text
backend/tests/test_creative_provider_preflight.py
backend/tests/test_creative_provider_requests.py
backend/tests/test_creative_image_bridge.py
backend/tests/test_creative_video_bridge.py
backend/tests/test_fixed_template_foundation.py
backend/tests/test_image_generation_batches.py
backend/tests/test_creative_workflow_storyboard.py
backend/tests/test_creative_media_isolation.py
```

main 独立复验：

- 使用实际 main 的 `.venv` Python 3.11.15、测试文件、模块搜索路径和
  `pyproject.toml`，完整组合 286 passed：新预检 143 项、既有相关回归 143 项。
- main 新预检/MVP-3A/两个 bridge 的服务与测试 scoped Ruff：通过。
- main `git diff --check` 与三个白名单新增文件的
  `git diff --no-index --check`：通过。
- main 最终隔离证据：`F:/Temp/creative-targeted-jdb2de1d/junit.xml`。
- 三个白名单文件与 testing SHA-256 一致，报告补齐结果后再次同步并校验。

## 白名单与同步

源码同步成功，仅推广上述三个新增文件。两侧真实分支已核对：testing 为
`codex/testing`，实际生产目录为 `main`。未推广密钥、真实 `.env`、缓存、运行时
状态、生成素材、临时测试目录或其他窗口的改动。

main 的 `image_generations.py` 与 `fixed_video_tasks.py` 在本包推广前后的源文件
SHA-256 保持一致；两侧这些旧服务原有差异与视频额度配置差异保留。共享
MVP-3A/bridge 文件没有修改。新增文件仍作为工作树源码交接，本包没有 Git 提交、
远程推送或部署。

源码 SHA-256：

```text
creative_provider_preflight.py
FB5D17ECD483DEA736A5ACAB4E8D693EE031053BC72E2AC35884E364B430B601
test_creative_provider_preflight.py
E4CE3EA3EDAF748BF4FED6E1EB8843203A22C1C64FCD82C78311AE64C03716FF
```

报告自身不记录其 SHA-256，避免自引用。

## 发现问题

- MVP-3A 全量证据哈希与新请求授权存在循环绑定风险；独立审批文件避免回改共享
  模型或绕过旧 evidence_hash。
- LocalObjectStore 返回原文件，远端存储返回目标路径，必须显式复制/避免同文件
  copy；测试证明 lease 关闭后源对象保留。
- 已有视频选项合同比个别 adapter 接受的模型/音频/分辨率宽；本包按本地真实
  adapter 约束阻断，不静默更改锁定配置。
- 缺 RuntimeConfig 和未知暂停值必须失败，不把 Fake 环境默认视为真实付费放行。
- 两分支视频额度的单位/默认数不同；通过读取各自 Settings 和数据库额度保留差异，
  不能把 testing 的每次额度值覆盖到 main。

## 下一步与限制

真实 Provider POST、费用扣除/真实账本事务、真实素材上传/接收证据、像素质量、
生产部署和生产迁移仍未完成。本包也没有创建 batch/task/attempt 或普通 QUALIFIED/
Deliverable，不把 Fake/Replay 升级成真实结果。

本包只提供可复验的预检和临时 adapter input manifest，不负责真实提交的原子领取、
预算预占、幂等落账、提交持久化、远端 UNKNOWN 对账或多 worker 并发一致性。
READY_FOR_HUMAN_SUBMIT 不是付费提交许可，后续入口必须重新检查当前授权/素材/
开关/额度并在原子提交门内处理幂等与预算。可信审批文件管理与人审交互尚未接线。

本轮无前端变更，不进行浏览器验收，不更新人工 Checkpoint 或上线就绪结论。
