# G1 接入验收纠偏

批准依据：2026-09-25 用户要求按供应商文档优先、检查本地接入责任的口径执行。
本文件覆盖旧 PM 看板与证据索引中要求穷举故障的工作安排；历史证据保留，不自动改为通过。

## 执行边界

- 暂停新增通用故障研究、历史 CLI 全矩阵、真实账单验证和监控平台扩建。
- 先确认实际供应商和文档版本，再核对对应适配器。代码默认值不代表生产运行配置。
- 不重新验证供应商平台可靠性；只修复本地实现与文档不符或已复现的业务问题。
- 已批准的回调默认拒绝策略继续有效；原供应商轮询、下载、结算路径保留。
- 不读取生产密钥或生产数据，不自行付费调用、重启、迁移或推送。

## 已定位资料

| 接入 | 仓库资料 | 文档来源 | 当前判断 |
| --- | --- | --- | --- |
| Kling API | `KLING_API_INTEGRATION_REPORT.md` | https://app.klingai.com/global/dev/document-api/api/video/3-0-omni/video-omni | 报告记录 API 2.0；须按当前使用版本核对，不能将旧报告当作最新合同 |
| Bach API | `BACH_API_INTEGRATION_REPORT.md` | https://www.bach.art/docs/v1/general | 已记录请求、查询、状态、上传与业务错误约定；当前是否启用待确认 |
| WaveSpeed | `backend/src/libtv_agent/adapters/wavespeed.py`、`wavespeed_video.py` | 待确认实际模型对应的供应商文档 | 代码支持不等于当前启用 |
| 历史 CLI | `backend/src/libtv_agent/adapters/kling_provider.py` | 历史恢复边界 | 默认工厂不创建 CLI；仅保留既有 attempt 恢复，不扩展新提交验收 |

上述链接来自仓库报告，本轮未将其标记为已完成当前在线版本核验。

## 有限收尾清单

1. 确认实际供应商、模型、API 版本和文档地址，不收集密钥。
2. 对照文档核对鉴权形式、提交字段、返回任务 ID、查询状态、错误码和重试规则。
3. 核对本地任务保存供应商和远端 ID，确认/重试不会重复发起付费生成。
4. 复用已有测试走通一条代表性流程：创建、确认、提交、查询、下载、业务记录；只为发现的缺陷补定向测试。
5. 核对本地用户/任务隔离、未知结果处理与原供应商收尾；已复现的安全问题不得以供应商成熟为由忽略。
6. 输出明确的接入结论、剩余实际问题及双分支同步结果；没有文档依据的扩展验证移出本轮，不作为隐性门槛。

真实供应商账单、正式部署、历史事件回放、所有历史 CLI 故障、浏览器 SSE 接入以及外部指标导出不属于本轮关闭条件。若应用实际使用 REST 轮询，就验证轮询恢复，不为验收而新增 SSE。

## 既有改动复核

保留回调拒绝、原供应商路由、幂等和账务保护，不批量回滚。后续逐项复核只针对会影响代表性业务流程的代码。
前端 `Promise.allSettled` 刷新改动需要优先定向复核：任一请求返回 401 时必须优先清除用户与任务数据，不能只处理列表中的第一个错误。已有通用测试通过不代表该认证分支已验证。

## 已确认的实际接入（2026-09-25）

用户确认使用可灵官方 Kling 3.0 Omni。当前验收以以下官方在线文档为准，不再将供应商选择列为待办：

- 入口：https://klingai.com/document-api/guides/get-started/overview
- 鉴权及国内域名：https://klingai.com/document-api/guides/get-started/quick-start
- Omni 提交与查询：https://klingai.com/document-api/api/video/3-0-omni/video-omni
- 错误码：https://klingai.com/document-api/api/get-started/error-codes

本轮已读取当前在线正文并核对 `kling_official_api.py`：Bearer API Key、北京域名默认值、`POST /omni-video/kling-3.0-omni`、`contents/settings/options`、提交返回 `data.id`、`GET /tasks` 的两种 ID 查询、四种任务状态、`outputs[].url` 均与主链路实现相符。模型 3.0 不等于接口版本号，不据此改为旧版 JWT 或旧版请求结构。

定向修复两处本地问题：HTTP 429 / 业务码 1304 是 IP 白名单策略错误，不应限流重试；提交超时后查询为空或查询失败不能证明未提交成功，必须保留 uncertain，不再次 POST。官方只承诺 external_task_id 可查询且账号内唯一，未承诺重复提交幂等。

高级素材组合尚有本地预校验缺口：参考视频的音频/首尾帧/多镜头限制，以及不同主体类型的数量组合。当前不将供应商对非法组合的参数拒绝当成安全失败；实际启用这些组合时按官方规则定向补齐。主体管理的旧接口不在本轮视频主链路核对结论内。

当前状态：供应商、模型和文档已确认，主链路合同核对已完成；这不等于真实付费联调、正式部署或整个 G1 已通过。回调继续默认拒绝，按原供应商轮询、下载、结算。
