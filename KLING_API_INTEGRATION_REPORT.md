# Kling 官方 API 2.0 接入报告

更新时间：2026-07-30

## 实施基线与代码审查

本次修改直接建立在本地分支 `codex/testing` 的未提交测试版上。没有执行 reset、checkout、
旧目录复制或旧代码包覆盖。

当前链路为：

`HTTP/UI 创建任务 → 分析/固定模板编译提示词 → prepare_kling_task → GenerationAttempt /
GenerationCommand → RunnerSupervisor → VideoProviderAdapter → 轮询 → 原子下载 → ffprobe
技术检查 → 对象存储和数据库账本`

可以复用的关键模块包括：

- `VideoProviderAdapter`：统一提交、查询、下载和能力检查合同。
- `kling_preparation.py`：稳定素材顺序、指纹、幂等意图和 attempt 创建。
- `RunnerSupervisor`：命令领取、并发、恢复、轮询、账本更新和下载。
- `media.py`：下载重试及 ffprobe 技术检查。
- 当前 UI、HTTP API、任务表、输出命名和对象存储路径。

原有耦合点主要是业务服务和 Runner 直接依赖 `KlingOfficialCliAdapter`，以及状态页写死
`KLING_CLI_READY`。这些位置已改为依赖现有 Provider 协议，并按 attempt 中持久化的真实
provider 选择适配器。

## 官方文档核验结论

本次采用 Kling 开发者平台 API 2.0 的 Kling 3.0 Omni：

- 国际版 Base URL：`https://api-singapore.klingai.com`
- 鉴权：`Authorization: Bearer <API Key>`
- 创建：`POST /omni-video/kling-3.0-omni`
- 查询：`GET /tasks?task_ids=...` 或 `GET /tasks?external_task_ids=...`
- 精确状态：`submitted`、`processing`、`succeeded`、`failed`
- 视频字段：`data[].outputs[].url`，且 `outputs[].type == "video"`
- 幂等/外部关联：`options.external_task_id`
- 回调：`options.callback_url`

官方当前认证页明确把 Access Key + Secret Key 生成 JWT 标为旧版鉴权。本实现因此没有混入
旧版 JWT，也没有新增 `KLING_ACCESS_KEY` / `KLING_SECRET_KEY`；只从服务端环境读取
`KLING_API_KEY`。这与原任务文本里的 JWT 要求不同，是依据“以本次最新官方文档为准”的要求
做出的有意调整。

参考：

- [API 2.0 Authentication](https://app.klingai.com/global/dev/document-api/api/get-started/authentication)
- [Kling 3.0 Omni API](https://app.klingai.com/global/dev/document-api/api/video/3-0-omni/video-omni)
- [Developer pricing](https://app.klingai.com/global/dev/pricing)
- [Kling VIDEO 3.0 model guide](https://app.klingai.com/cn/quickstart/klingai-video-3-model-user-guide)

当前映射：

- 用户确认后的 prompt 原文放入首个 `contents` 项，不翻译、不润色、不追加文本。
- 第 1 张有序分镜图映射为 `first_frame` / `image_1`。
- 其余有序分镜图和产品参考图依次映射为 `refer_image` / `image_2...`。
- 图片以原始 Base64 传输；摘要和日志不输出 Base64。
- 仅接受 JPG/JPEG/PNG；每边至少 300px；宽高比在 1:2.5 到 2.5:1；本类请求总图数最多 7。
- 时长 3–15 秒，画幅 `16:9` / `9:16` / `1:1`，分辨率 `720p` / `1080p` /
  `4k`，音频 `native` / `off`，支持 `multi_shot`。

当前业务没有独立“尾帧”或官方 element 素材实体，因此本次不猜测转换为 `last_frame` 或
`element`。这些能力需在业务模型明确表达对应语义后再接入。

## 可靠性与安全

- `external_task_id` 使用稳定的本地 intent hash；请求超时或 5xx 后先按 external ID 查询，
  找到即恢复，不重复创建。
- 明确 429 按 `Retry-After` 与指数退避/抖动重试；网络和 5xx 可重试；鉴权、参数、余额及
  权限错误不做无意义重试。
- 未知官方状态严格映射为 `unknown`，保留原响应，不猜测为成功或失败。
- 任务超过配置等待时间后进入 `UNKNOWN_AFTER_SUBMIT`，不会自动重新扣费。
- 下载使用 `.part` 临时文件、流式写入、HTTP/Content-Type/非空检查和原子替换。
- API Key、Authorization、Base64 和完整签名 URL 不进入请求摘要。
- API 默认关闭；CLI 只保留历史 attempt 的查询和下载恢复，不能接收新提交。

## 配置

管理员现在可以在“管理中心 → Provider 与账号”直接维护以下配置：

- 启停正式 API；新生产任务不能切换回 CLI；
- 写入、替换或清除 API Key（响应与审计不回显明文）；
- 修改 API 模型、时长、比例、分辨率、音频、多镜头和提交/查询并发。

Windows 部署使用 DPAPI machine scope、受限 ACL 和原子文件替换，将共享配置提供给 API 与
独立 Runner。API 进程保存后立即刷新；Runner 在下一调度周期按文件签名加载并替换活动
adapter。已提交 attempt 继续按其持久化 provider 查询和恢复。

仅配置 Key 时状态为 `KLING_API_CONFIGURED_UNVERIFIED`。系统使用正式 API 的任务查询端点做
只读鉴权校验；该边界不会创建媒体或消耗生成额度。只有真实查询成功后才标记
`KLING_API_READY`。网络错误、鉴权失败或缺少 Key 都保持不可提交，不会以“已配置”冒充
“已验证”。

下列环境变量仍是首次启动默认值；后台首次保存后，以共享安全配置文件为准：

```dotenv
KLING_PROVIDER_BACKEND=api
KLING_API_ENABLED=true
KLING_API_KEY=<仅放在部署环境，不提交>
KLING_API_BASE_URL=https://api-singapore.klingai.com
KLING_API_MODEL=kling-3.0-omni
KLING_API_DURATION=10
KLING_API_ASPECT_RATIO=9:16
KLING_API_RESOLUTION=1080p
KLING_API_AUDIO=off
KLING_API_MULTI_SHOT=true
KLING_API_CALLBACK_URL=
KLING_API_REQUEST_TIMEOUT_SECONDS=60
KLING_API_TASK_TIMEOUT_SECONDS=1800
KLING_API_DOWNLOAD_TIMEOUT_SECONDS=300
KLING_API_MAX_SUBMIT_CONCURRENCY=1
KLING_API_MAX_POLL_CONCURRENCY=4
KLING_API_POLL_INTERVAL_SECONDS=20
KLING_API_MAX_POLL_INTERVAL_SECONDS=60
KLING_API_MAX_RETRIES=3
KLING_API_ENABLE_PAID_INTEGRATION_TEST=false
```

API 创建并发默认 1。官方说明并发额度按账号、模型和资源包计算，账号的所有 API Key 共享；
实际额度应以开发者后台为准，不应照搬固定值。

## Dry Run

Dry Run 不需要真实 API Key，不发网络请求；它会按文件名稳定扫描目录、校验图片、完整构建请求，
然后只打印 prompt/素材哈希和脱敏后的结构：

```powershell
uv run python scripts/kling_api_dry_run.py `
  --storyboard-dir C:\path\to\storyboards `
  --product-dir C:\path\to\product-images `
  --prompt-file C:\path\to\prompt.txt `
  --duration 10 --aspect-ratio 9:16 --resolution 1080p --audio off
```

## 测试、启动与历史恢复

```powershell
uv run ruff check .
uv run pytest
npm --prefix frontend test
npm --prefix frontend run build
```

按现有项目方式启动：

```powershell
.\scripts\start-local-stack.ps1
```

推荐在管理后台配置 API：API 进程立即生效，Runner 在下一调度周期生效，无需重启，也不需要
迁移或改写历史任务。首次启动或后台不可用时，可通过 `KLING_API_ENABLED` 和对应凭据配置后
重启 API 与 Runner。只有需要恢复已提交的旧 CLI attempt 时才设置
`KLING_CLI_ENABLED=true`；它不会重新开放 CLI 新提交。

## 尚未验证

- 未执行任何真实付费提交，也未验证具体账号的余额、授权模型和实际并发额度。
- 官方回调入口尚未在本项目暴露；当前只保留可配置 callback URL，任务完成仍以持久化轮询为准。
- 产品图目前映射为普通参考图；若要使用正式 element 库，需要新增明确的业务素材类型和 element
  创建/管理流程，不能自动猜测。
- API 返回下载 URL 有保留期；系统会在成功后立即下载，但过期恢复仍受官方 URL 是否可用影响。
