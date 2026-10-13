# Sprint Report：CW-1 隔离骨架与单正面闭环

日期：2026-10-10
状态：首包隔离实现；不代表完整 CW-1、真实质量或生产就绪

## 完成

- 用户确认后将门禁分为隔离开发、真实验证、上线；实现只开放 test/local-store/Fake-Replay，不由前置样本缺失阻塞骨架。
- 单商品正面上传、分析占位方向、人工选方向、六维包、独立授权、Fake 候选、离线人审及选图贯通 G0 到 E3。
- 修订校验 scope/锁项/当前包、可改模块、次数/调用/费用/停止；追加新包、候选和父链。循环默认关闭、启用默认一次、最多两次。
- 同键保存请求哈希和原响应，版本 CAS 串行化 root 下的预算及候选变更；未知结果保留费用，仅声明式 Fake 对账恢复。
- 商品基础从实际 main 窄范围回移，不新增第二套 Product；新增迁移继承原生产合并 head。

## 修改

- 新增 `creative/workflow.py`：AssetLink、PlanRevision、PackageRevision、Authorization、StageAttempt、Iteration、Review、Selection、Command 类型合同。
- 新增 `services/creative_workflow.py` 与 `api/creative_workflow.py`；新增三个表 CreativeTask/CreativeRecord/CreativeCommand。九类边界采用带 kind/key/hash 的 append-only 记录和 root 当前指针，不为每类强行新增表。
- 测试侧回移 `api/products.py`、原 Product 模型/schema/enums、handoff 合同与对应测试、两份原商品/合并迁移；handoff 只修三处既有 Ruff 格式/注解问题，语义不变。
- 新增 `d0c1e2f3a405_creative_offline_foundation.py`、`test_creative_workflow.py`。不改旧 fixed_video_tasks、image_generations、quota、审核或 Provider 执行路径。
- 更新任务书/前置包/计划/QA/变更与 JSON 的开发门和当前 heads；真实批准字段保持 false/额度 0。

所有源路径相对 `backend/src/libtv_agent/`。API：

| 方法/路径 | 合同 |
| --- | --- |
| POST `/api/v1/creative-workflow/tasks` | multipart product_id + 单正面 front；真实字节校验/哈希/持久化，复用已有 Product owner；不要求网址或 model.front |
| GET `/api/v1/creative-workflow/tasks/{id}` | owner-only snapshot、版本、候选/选择/trace |
| POST `/api/v1/creative-workflow/tasks/{id}/commands` | command_key、expected_version；分析/选方向/授权/生成/人审/选择/修订/停止/撤回/Fake 对账 |

API 一律仅 app_env=test、local 对象存储、fake/replay、paid_generation_enabled=false；development/staging/production 不可使用。可识别为普通 image 的输入在保留原始 bytes 后校验 PNG/JPEG/WebP、10MiB/40MP 上限。临时物化通过已有 ObjectStore 接口。

## 测试

- 隔离测试 harness：`E:/Codex/plugin-audit-creative-workflow-20261010/run-preflight-isolated.py`，指定 repository + tests/migration/export/contracts；仓库外 cwd 和 SQLite、禁非 loopback、Fake，不加载真实 `.env`。
- 最终 testing：111 项选集通过（95 项已有+16 项新测试，41.03 秒）；main 独立运行同组选集：111 项通过（41.45 秒）。
- pytest 新用例含实际两请求并发 CAS、重复/冲突命令、预算拒绝回滚、两种未知费用、原图 SHA/撤回、人审来源、修订包与停止、scope/过期、重启读取持久响应。
- testing/main 分别在仓库外空 SQLite 完成 28 份全链迁移，升级到 `d0c1e2f3a405`；这不证明 PG、带数据升级、真实多进程远端崩溃或无损 downgrade。
- 两侧分别生成 OpenAPI，保留各自 schema 默认值；两侧合同制品测试各 2 项通过。原离线前置检查单测各 27 项通过，检查器分别以 testing/main 角色通过，真实批准保持关闭。
- 两侧本包 API、模型、creative、service、新测试及迁移的 scoped Ruff 均通过；testing 增量修改的 schemas/enums 也通过。
- 无前端变更，未跑浏览器/build；不给旧 Studio/Checkpoint 新验收结论。

复现命令（PowerShell；`<repo-root>` 分别取 testing 和 main 的绝对路径，`<mode>` 分别取 tests、migration、export、contracts）：

```powershell
& 'E:/Projects/libtv自动化生成/.venv/Scripts/python.exe' 'E:/Codex/plugin-audit-creative-workflow-20261010/run-preflight-isolated.py' '<repo-root>' '<mode>'
```

## 源码同步

- 已将本包 13 份白名单文件同步至 `C:/Users/Reel/Documents/libtv-auto-main-sync`，模型和 router 按各侧基线增量修改；OpenAPI 在各侧独立生成，不跨侧整文件覆盖。
- main 原 schema/enums 保留，testing 复用 main 原 Product 基础；并行任务的内容库、动作、提示词、前端和文档改动均未回退。
- 本轮未提交或推送 Git，未操作生产数据、运行生产迁移、部署、重启服务或实际付费生成。源码同步完成不代表正式版已运行本包。

## 发现问题

- 两侧原 schema 存在独立配额默认值（testing 100 / main 5000）；本包保留，不全文件覆盖 schema/enums。模型只增量加 Creative 表，Product 定义与生产一致。
- Fake 分析不读像素语义，候选引用原商品字节作为明确占位；四轴全 UNVERIFIED，人工 QUALIFIED 只标 OFFLINE_SYNTHETIC_ONLY。不存在真实生成/质量收益证明。
- batch/item/output 是带 fake 前缀的合成标识，不是真实 ImageGenerationBatch 子任务；真实桥接、批次部分失败、多分镜、导演视频均留后续包，不声称本包已接入生产媒体服务。
- 目前是显式命令驱动 Fake 修订边界，不是后台自主 Critic/循环 worker；真实能力未核实时不可启用自主修订。replay 设置在本入口同样执行确定性 Fake，不冒称完整媒体 Replay。
- 无独立不可变 Prompt Registry、Grounded DNA schema/真实 Preservation；六维为结构化摄影决定占位，后续需要 CW-2 编译器。
- 暂引用 Product id + 原素材 hash，不创建伪 URL 或 ProductVersion；旧商品版本接口仍要求 URL，版本号 max+1 并发问题未改。真实生产接入必须冻结 ProductVersion/事实/用户锁快照及许可。
- root JSON 适合首包合同边界，尚无后台 lease/outbox、创建任务幂等、原图垃圾回收/pin 清理、阶段独立预算/真实账本、PG 证明；不得直接开放真实调用。
- Fake 对账声明不构成 Provider 未提交/未收费证据；真实恢复需复用既有 attempt。新代码只显式挂载离线路由，director_fixed 留接口边界不实现。

## 下一步

- 建议进入第二个隔离包：Grounded DNA/Prompt Registry/Preservation 与真实媒体服务的 Fake 绑定；先消除 synthetic mapping 和版本锁/阶段预算缺口，再做 worker/crash 注入。
- 在真实首帧验证前单独确认 SKU/许可、模型支持与报价/预算、Critic 区域证据/效果；在上线前验证 PG/带数据、权限/审核交付与 Checkpoint 2。
- 导演前端继续等 Checkpoint 1。本轮源码推广不构成生产迁移、部署、重启或付费授权。
