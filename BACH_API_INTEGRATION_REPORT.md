# Bach API 接入衣影工坊调研报告

更新时间：2026-08-06

## 结论

Bach 适合以新的视频 provider 接入衣影工坊，而不是在现有 Kling/WaveSpeed adapter 中增加分支。仓库已经有通用的 `VideoProviderAdapter`、异步任务轮询、输出下载和 provider recovery 机制，Bach 可以复用这些边界。

建议先做视频链路，再扩展图片/主体资产链路：

1. **P1：Image-to-Video**，覆盖衣影工坊当前最明确的首帧、尾帧和服装展示场景。
2. **P2：Elements-to-Video + Batch Uploads**，覆盖人物/服装/商品/场景多元素一致性。
3. **P3：Text-to-Video、Montage**，用于无参考图创意和完整叙事视频。
4. **P4：Text-to-Image、Text-to-Subject**，作为图片中心和主体资产库的独立 provider 能力。

当前文档未提供可用于余额/鉴权的只读健康接口，也未提供回调签名校验方案。因此首版应采用服务端 JWT + 轮询为主，回调作为可选加速通道；回调地址使用随机不可猜测路径，并保留轮询兜底。

## API 基础信息

来源：<https://www.bach.art/docs/v1/general>

| 项目 | 内容 |
|---|---|
| Base URL | `https://api-gen-na.bach.art/api/vdr` |
| 协议 | HTTPS |
| 请求格式 | `application/json`（文件上传除外） |
| 鉴权 | `Authorization: Bearer <API_TOKEN>` |
| Token | `AccessKey` + `SecretKey` 生成 HS256 JWT |
| Token claims | `iss=AccessKey`、`nbf=now-5s`、`exp=now+10d` |
| 图片输入 | 必须是 Bach 服务可访问的 HTTP/HTTPS URL |
| 异步状态 | `TASK_PENDING`、`TASK_PROCESSING`、`TASK_SUCCEEDED`、`TASK_FAILED` |

JWT 必须在后端生成。`SecretKey` 不进入 React、浏览器、日志或仓库；Token 可在服务端内存缓存至过期前重新生成。

## 视频接口清单

### Image-to-Video（P1）

文档（由 Bach API Docs 导航进入）：<https://assets.bach.art/bach/api/docs/source/2026-08/6679b41a-3726-4f77-aa15-661daf578803.md>

| 方法 | 路径 | 作用 |
|---|---|---|
| POST | `/videos/image2video` | 创建任务 |
| GET | `/videos/image2video/{task_id}` | 查询任务 |

请求字段：

| 字段 | 规则 |
|---|---|
| `model_name` | 可选，当前只有 `bach-1.0` |
| `image_url` | 首帧；与 `end_image_url` 至少提供一个 |
| `end_image_url` | 尾帧；两者都提供时做首尾帧自然过渡 |
| `prompt` | 可选，最多 10,000 字符 |
| `resolution` | 必填：`720p` 或 `1080p` |
| `duration` | 首帧单独使用支持 1-8 秒；尾帧单独或首尾帧支持 1-6 秒 |
| `generate_audio` | 默认 `false` |
| `audio_prompt` | 最多 200 字符 |
| `enable_moderation` | 默认 `true` |
| `callback_url` | 可选，HTTP/HTTPS，最多 500 字符 |

衣影工坊映射建议：`first_frame_path -> image_url`、`last_frame_path -> end_image_url`、`prompt -> prompt`、`resolution/aspect_ratio/duration/audio -> 对应字段`。Bach 的 Image-to-Video 文档没有 `aspect_ratio` 字段，首版不能把现有比例配置无条件传给该接口；比例应通过输入图尺寸和产品侧预检处理，或等待服务方确认是否支持隐藏字段。

### Elements-to-Video（P2）

文档（Elements to Video）：<https://assets.bach.art/bach/api/docs/source/2026-08/4946068e-6bf1-4084-98d1-1e3e14257def.md>

| 方法 | 路径 | 作用 |
|---|---|---|
| POST | `/videos/elements2video` | 创建任务 |
| GET | `/videos/elements2video/{task_id}` | 查询任务 |

核心字段：

| 字段 | 规则 |
|---|---|
| `reference_inputs` | 必填，最多 9 个；每项类型为 `image` 或 `subject` |
| `reference_inputs[].type=image` | 需要 `url` |
| `reference_inputs[].type=subject` | 需要 2-4 张 `images`，以及 `subject.subject_name`；可选 `subject_desc/style/type` |
| `prompt` | 必填，最多 10,000 字符 |
| `resolution` | 必填：`720p` 或 `1080p` |
| `duration` | 默认 6，范围 1-6 秒 |
| `aspect_ratio` | 默认 `16:9`，支持 `16:9`、`9:16`、`1:1` |
| `fps` | 默认 24，支持 24/30 |
| `generate_audio/audio_prompt` | 音频开关及最多 200 字符描述 |
| `callback_url` | 可选 |
| `seed` | 可选，0-10,000,000 |

现有 `VideoElementReference` 是 Kling 的持久化 element/content ID，不能直接传给 Bach。Bach 版本需要在 adapter 中把衣影工坊的本地素材上传后构造成 `reference_inputs`，并从素材元数据生成 subject 描述；不要假设两家 provider 的 ID 可互通。

### Text-to-Video（P3）

文档（由 Bach API Docs 导航进入）：<https://assets.bach.art/bach/api/docs/source/2026-08/27a756b1-dfe6-407f-9743-7299ff61831c.md>

| 方法 | 路径 | 作用 |
|---|---|---|
| POST | `/videos/text2video` | 创建任务 |
| GET | `/videos/text2video/{task_id}` | 查询任务 |

关键约束：`resolution` 必填（720p/1080p），`aspect_ratio` 支持 16:9/9:16/1:1，`duration` 为 1-8 秒，`cfg_scale` 为 1.0-15.0，`prompt` 与 `negative_prompt` 最多 10,000 字符；可选音频和 `enhance_prompt`。

### Montage（P3）

文档（由 Bach API Docs 导航进入）：<https://assets.bach.art/bach/api/docs/source/2026-08/eec242dd-4665-4ff1-b756-768ac6a7a1e1.md>

| 方法 | 路径 | 作用 |
|---|---|---|
| POST | `/videos/montage` | 创建完整叙事视频 |
| GET | `/videos/montage/{task_id}` | 查询任务 |

Montage 支持最多 20 张参考图、10/15/20/25/30/45 秒，比例 16:9/9:16/1:1，并有 BGM、SFX、旁白开关。它更适合品牌故事、活动预告和完整商品叙事，不建议直接替换当前固定模板的单镜头生成。

## 资产接口

来源：<https://www.bach.art/docs/v1/batch_uploads>

### URL 批量上传

`POST /batch-upload/submit`，JSON：

```json
{
  "upload_type": "url",
  "batch_id": "衣影工坊内部批次 ID",
  "images": [
    {"image_data": "https://public.example/a.jpg", "image_name": "a.jpg"}
  ]
}
```

`upload_type` 支持 `url`/`base64`，最多 300 张，单张最多 10 MB，格式为 JPG/JPEG/PNG。响应返回 `batch_id`，需要通过 `GET /batch-upload/status/{batch_id}` 轮询；完成后从 `results[].image_url` 读取 Bach 可用 URL。

### 文件批量上传

`POST /batch-upload/submit-with-files` 使用 `multipart/form-data`，字段为 `files[]`、可选 `image_names[]` 和 `batch_id`。这条链路适合衣影工坊已有的本地素材，不需要先把用户文件暴露为公网 URL。

上传状态需要单独建模，至少处理 `pending/processing/completed/failed` 及每张图的 `results[].status/error_message`。不要把上传提交成功误当成图片已经可用于视频生成。

## 统一响应与错误处理

普通成功响应示例：

```json
{
  "code": 200,
  "data": {
    "task_id": "...",
    "status": "TASK_PENDING",
    "created_at": 1778313600
  },
  "timestamp": 1778313600
}
```

业务成功必须同时满足 **HTTP 2xx 且 body.code == 200**。Bach 明确存在 HTTP 200 但业务失败的情况，不能只看 HTTP 状态码。

| 情况 | 处理 |
|---|---|
| 400 / code 1000 | 参数/范围/格式错误，不自动重试 |
| 400 / code 1001 | 内容安全失败，修改输入后重试 |
| 401 / code 1100-1103 | Token 无效、未生效或过期，重新生成；不重试原请求 |
| 402 / code 1302 | 资源包额度不足，停止提交 |
| 403 / code 1301 | 分辨率不在当前资源包支持范围，提示可用分辨率 |
| 404 / code 1200 | 任务/批次不存在或已过期，标记不可恢复 |
| 429 / code 1800 | 队列/并发容量满，指数退避后重试 |
| 500 / code 5000 或 code 500 | 临时服务错误，有限次指数退避并保留“不确定提交”状态 |

提交 POST 出现超时或 5xx 时，不能直接重新提交付费任务。应先记录 `WRITE_UNCERTAIN`，若 Bach 没有外部幂等键，则只能通过本地状态和人工/查询确认后决定是否恢复。

## 与现有仓库的接入边界

当前代码已经具备：

- `backend/src/libtv_agent/adapters/video_provider.py` 的统一视频 provider 协议。
- Kling/WaveSpeed 的 `submit -> query -> download` 异步生命周期。
- provider 名称持久化、历史任务 recovery、对象存储落地和媒体技术校验。
- provider capacity、轮询间隔、超时和提交不确定状态保护。

建议新增 `backend/src/libtv_agent/adapters/bach_provider.py`，不要修改 Kling adapter 的语义。适配器内部拆成：

1. JWT token signer/cache。
2. Bach JSON 请求/响应和错误分类。
3. Image-to-Video / Elements-to-Video 的 payload builder。
4. Batch Upload 文件提交和状态轮询。
5. Bach 状态到统一状态的映射：`TASK_PENDING -> queued`、`TASK_PROCESSING -> running`、`TASK_SUCCEEDED -> succeeded`、`TASK_FAILED -> failed`。
6. 成功后立即下载 `video_url` 到现有 object store，避免远端 URL 过期。

现有 provider routing 的 `ProviderKind` 目前只有 `libtv|kling`。首版可以把 `bach` 纳入新的独立 kind，避免在产品/UI 中把 Bach 错标为 Kling；同时在 `RunnerSupervisor` 中增加 Bach adapter registry 和独立并发配置。

## 建议配置项

不把 SecretKey 放进前端配置响应。建议服务端环境变量或加密管理员配置至少包含：

```text
BACH_ENABLED=false
BACH_ACCESS_KEY=
BACH_SECRET_KEY=
BACH_API_BASE_URL=https://api-gen-na.bach.art/api/vdr
BACH_PROVIDER_NAME=bach
BACH_MODEL=bach-1.0
BACH_RESOLUTION=720p
BACH_ASPECT_RATIO=9:16
BACH_DURATION=6
BACH_GENERATE_AUDIO=false
BACH_POLL_INTERVAL_SECONDS=10
BACH_MAX_POLL_INTERVAL_SECONDS=60
BACH_TASK_TIMEOUT_SECONDS=1800
BACH_REQUEST_TIMEOUT_SECONDS=60
BACH_DOWNLOAD_TIMEOUT_SECONDS=300
BACH_MAX_SUBMIT_CONCURRENCY=1
BACH_MAX_POLL_CONCURRENCY=4
BACH_CALLBACK_URL=
```

`BACH_CALLBACK_URL` 只在服务端可被 Bach 访问时启用；否则留空并使用轮询。回调文档没有签名字段，接收端必须按本地任务 ID/随机路径做关联，并把回调视为“触发刷新”的提示，不作为唯一事实来源。

## 分阶段验收

### P1：只做视频 provider

- Token 生成单测：`iss/nbf/exp/HS256`，不记录 SecretKey。
- `code != 200` 的 HTTP 200 响应被判定为失败。
- Image-to-Video 首帧、尾帧、首尾帧三种 payload 单测。
- `TASK_PENDING/PROCESSING/SUCCEEDED/FAILED` 映射单测。
- 提交超时进入 `WRITE_UNCERTAIN`，不会自动重复付费 POST。
- 结果视频下载到 object store，远端 URL 不直接作为最终资产地址。
- 使用真实 Bach 账号做一次最小时长、720p 的付费 smoke test，并保存脱敏原始响应。

### P2：一致性和资产

- 文件批量上传 1 张和多张测试。
- 上传状态未完成时禁止提交生成任务。
- `reference_inputs` 的 image/subject schema 和 9 项上限校验。
- 本地素材尺寸、格式、10 MB 限制在提交前拦截。

### P3/P4：扩展能力

- Montage 音频/旁白参数在产品配置中显式呈现。
- Text-to-Image 输出多图、部分成功和 MIME 类型落库。
- Text-to-Subject 四张 `split_images` 写入主体资产库。

## 接入前需要确认的外部条件

1. Bach 控制台的 `AccessKey/SecretKey` 和可用资源包/分辨率权限。
2. 当前 NA Base URL 从衣影工坊运行机器所在网络是否可达，是否有区域限制。
3. 结果视频和图片 URL 的有效期，以及是否要求下载前带额外请求头。
4. 回调是否支持签名、重试次数和超时；当前公开文档没有这些字段。
5. 是否允许生产环境使用 `enable_moderation=false`；文档注明该开关需要管理员侧配置。
6. 首版产品范围：只接 Image-to-Video，还是同时开放 Elements-to-Video。
