# Sprint Report：Creative Workflow CW-0.5 前置验证

日期：2026-10-10
范围：响应“启动”，交付工程调查/合同证据与隔离基线验证；不是 CW-1 实现

## 完成

- 核实两侧源码能力、真实 Product 差异、迁移图、Provider 输入/参考限制与旧模式接入风险。
- 交付 CW-P01 至 CW-P08 评审证据包、D01 至 D06 待决清单；记录工程已交付与待确认，不追认通过。
- 将插件规则研究落为来源哈希、固定模块顺序、六维、预算/授权、定向修订与证据分轴设计。
- 全程使用离线 Fake/临时数据库；真实调用数/费用为零。

## 修改

- 新增 `docs/CREATIVE_WORKFLOW_PREFLIGHT_20261010.md`。
- 新增 `docs/contracts/creative-workflow-preflight.v1.json`，包含 13 份关键规则来源哈希及 synthetic fixture。
- 新增 `scripts/check_creative_preflight.py`、`scripts/test_creative_preflight.py`，仅离线设计检查/顺序模拟，不接应用或 Provider。
- 修正 `backend/tests/test_content_catalog_editing.py` 四处旧错误断言，只读取 `detail.message`，保留拒绝语义。
- 更新任务书前置状态、开发计划、QA、CHANGELOG；保留入场全部 UI、文档及用户 ZIP 改动。
- 未修改业务模型/API/Provider/迁移、前端或真实配置；Product 回移尚未执行。

## 测试

- testing 入场 HEAD `a9db2d6daf215f919b64af36f38855ad5aa638e1`；实际 main `4cc509f90dadee9ad57142d60318d105bf1b9e2b`。未创建提交或推送。
- AST 图：testing 25 份 / `c8d4e6f1a203`；main 27 份 / `c9f0a1b2c304`。
- 临时空库 SQLite `upgrade head` 两侧通过；未连接生产，不证明 PostgreSQL/带数据/downgrade。
- testing 现有隔离后端选集 85 项通过；首次有两条用例在旧错误格式处失败，四处断言修正后整组选集重跑通过。
- main 独立现有后端选集 95 项通过，含额外 10 项 Product/CreativeHandoff 测试；首次同样两条旧断言失败，推广修复后整组选集重跑通过。
- 新 Fake 合同测试两侧各 27 项通过；Ruff 两侧通过。校验循环默认/上限、未知费用与回放、禁止模型资格、scope/shot/锁项、模块顺序、素材与选图、迁移图循环/缺父等边界。
- 两侧离线合同/来源检查均通过；用户 ZIP 和 13 份关键规则文件 SHA 核验通过，真实 Critic 仍 UNVERIFIED。
- 25 份公共迁移规范化行尾后内容一致，4 份原始 SHA 差异仅来自 LF/CRLF；相关共同服务差异为行尾或相邻字符串排版，未覆盖生产侧文件。
- 本轮 10 文件机械白名单推广至实际 main；最终逐文件 SHA 一致，范围外入场文件哈希未变化，生产 Product/API/迁移和已有 UI/文档/ZIP 保留。推广不是部署。
- `git diff --check` 两侧范围内通过；新增 UTF-8/JSON/文档引用与尾部空白检查通过。未提交、推送或改动服务。
- 选集覆盖 OpenAI analysis adapter、object store/retention、review permissions、content catalog、image batches/quota、fixed video foundation；main 另含 products/handoff。
- 外部 harness 在临时 cwd/数据库运行，显式 Fake/禁止真实调用，网络拦截非 loopback 连接；不读取真实 `.env`。本轮临时证据/缓存留仓库外，不推广。
- 生成的两侧来源/迁移证据快照位于 `E:/Codex/plugin-audit-creative-workflow-20261010/preflight-source-testing.json` 和 `preflight-source-main.json`，可由仓库检查器重新生成。
- 无前端变更，未运行 build/lint/browser；不更新页面验收，不拿旧 Studio 测试作导演验收。

## 发现问题

- main 已有 Product 基础和合并 head，testing 缺失；未经对齐不能新增第二套 Product 或盲推新迁移。
- 现有 Product URL 必填、source_asset_references 为字符串、max+1 版本号尚不足以满足上传真源/并发/幂等要求。
- 分析适配能组装 input_image，但 detail=low 与固定旧 schema 不等于真实 Critic/完整 DNA；真实能力 UNVERIFIED。
- automatic 视频会重编 Prompt/学习，director_fixed 必须另设明确分支并做负断言；目前尚未实现。
- 内容库错误响应已结构化，旧测试断言失配；本轮修复并保留许可/品牌/跨品牌拒绝覆盖。
- Fake ledger 不证明数据库原子性、多 worker、网络提交/崩溃恢复、真实图像质量或商业收益。

## 下一步

- 工程评审 D01 对齐与数据/Prompt/状态方案；安排隔离 PG/带数据/并发验证，按真实证据完成 CW-P07。
- 产品/素材负责人确认 D02 至 D04：模型报价/费用/有效期、有权 SKU/参考、质量收益目标及采样预算。
- 评审 D05 Critic 能力与降级，不在未验证时启用自主修订。
- 八项前置正式通过后才启动 CW-1；前端仍等 Checkpoint 1，真实质量采样/付费/迁移/部署分别批准。
