# Sprint Report：Creative Workflow CW-2 隔离包

日期：2026-10-10
范围：后端单正面 Fake、ProductVersion 事实锁、撤回/恢复、任务创建幂等、Prompt Registry 与真实图片批次映射

## 完成

- 素材撤回追加不可变事件，记录资产快照、SHA、操作者、服务端时间、原因、影响范围和版本；撤回后新执行、选图和对账恢复均保持 BLOCKED。
- 创建任务支持 owner 作用域客户端键和完整请求指纹；相同请求重放原响应，不同请求返回 `TASK_IDEMPOTENCY_CONFLICT`。
- 复用现有 Product/ProductVersion，支持 `USER_UPLOAD` 无网址版本；任务保存 ProductVersion 内容快照，后续追加版本使未执行任务返回 `PRODUCT_VERSION_STALE`。
- 结构化 `GroundedClaim`、五维方向差异占位和固定顺序 Reality 六维；Fake 明确为 `FAKE_NOT_IMAGE_ANALYSIS` / `PROPOSED_FAKE`，不把图片占位当事实。
- Prompt Registry、Preservation 哈希和绑定前结构检查；历史记录与 ProductVersion 事实由迁移触发器保护。
- Fake 生成持久化现有 `ImageGenerationBatch` / `ImageGenerationItem` / `ImageGenerationOutput`，保留 task/package/shot/attempt/selection 关联和原图 SHA；人工结果仍是 `OFFLINE_SYNTHETIC_ONLY`。

## 修改

- 新增 `d1e2f3a4b506_creative_isolated_integrity.py`，继承 `d0c1e2f3a405`。
- 增量修改 ProductVersion schema/API、Creative Workflow contract/service/API、现有图片批次映射。
- 新增 `services/product_versions.py`、CW-2 聚焦回归及本报告。
- OpenAPI 在 testing 独立生成；未修改前端、Provider、真实计费、生产数据或运行环境。

## 测试

- testing 聚焦 Creative Workflow + Product：23 项通过。
- 外部隔离 harness：115 项通过；SQLite 空库全链升级到 `d1e2f3a4b506`。
- scoped Ruff：通过。
- 实际 main 独立外部隔离 harness：115 项通过，迁移升级到 `d1e2f3a4b506`，合同制品 2 项通过。
- testing 合同制品 2 项通过；testing/main OpenAPI 分别独立生成，SHA-256 分别为
  `C910F7565F30B547AB68C1A51594E9C6733444D8F3043CFA915973F42979F6F2`
  和 `EDB7929EA025DE0EFCF4A2DB5EC9640A213FF8119E96DA60C6C84CC760E4DA61`。
- 迁移、测试使用仓库外临时 cwd/SQLite，未读取真实 `.env`，网络拦截保持开启；生产侧未执行迁移。

## 未实现与限制

- 仍是显式命令 Fake 闭环；没有真实 Provider、像素 Critic、真实质量结论、后台 worker、PG 带数据升级或多进程崩溃证明。
- Prompt Preservation 只机械证明已登记结构不变量与哈希；模型语义保真和输出像素保持仍是 `unverified`。
- Fake batch 使用离线占位媒体，不可流入正式视频生产；`director_fixed`、多分镜和前端均留后续包。

## 下一步

- 下一包补齐真实/Replay 媒体证据分轴、逐镜批次部分失败与物化恢复；先验证 PG/带数据升级和旧图片审核合同，再讨论导演视频入口。

## 同步

- CW-2 白名单源码、迁移、测试、合同和本报告已同步至实际 `main`；对应迁移 SHA-256 为
  `D7F2D97EDD55F9F0A7FD0417DE8141CF14A454AE20788ED820F5418CC5F77631`。
- 保留 main 的配额默认值 `5000` 及其他并行任务改动；未同步 `.env`、缓存、构建产物、运行状态或用户压缩包。

