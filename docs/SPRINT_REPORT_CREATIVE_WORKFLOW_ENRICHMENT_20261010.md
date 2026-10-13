# Sprint Report：Creative Workflow 优势吸收与立项门补齐

日期：2026-10-10
范围：用户要求的任务书补齐、插件实审与自主循环合同；仅文档，不是功能开发/真实质量验收

## 完成

- 实际读取 `F:/Users/Reel/Downloads/plugin (2).zip`；manifest 为 ai-fashion-creative-director v1.13.5，SHA-256 为 `CE3BAC935CAE0C45479AFA68E948004BC9C08B4B862A7C74EC4959F122828F67`。
- 建立衣影工坊已有引擎/审核/来源/恢复和插件模块/真实性门的优势吸收表，区分已有、适配、新建、不可用能力。
- 明确采用插件先方案→授权→生成→像素复核顺序，六维 Reality 常开，规则优先级 27 > 26 > 24 > 23，旧比例叙述不沿用。
- 将插件宿主的“不后台自主”替换为本项目有界自主真实性修订合同：固定模块顺序、失败证据、不可变新包、授权次数/总预算/有效期和停止/恢复。
- 新增 CW-0.5 与 CW-P01 至 CW-P08 前置交付/通过责任；新增 CW-A16 至 CW-A30。前置评审和所有功能验收均尚未执行。

## 修改

- 修改 `CREATIVE_WORKFLOW_IMPLEMENTATION_20261010.md`、`PRODUCT_SPEC.md`、`DEVELOPMENT_PLAN.md`、`QA_CHECKLIST.md`、`CHANGELOG.md`，新增本报告。
- 完整补充 GroundedClaim/事实版本、方向差异、素材保留/撤回、状态/动作、Prompt Registry/Preservation、shot_id 映射、背面证据/资格、director_fixed 和真实质量指标。
- 原 `SPRINT_REPORT_CREATIVE_WORKFLOW_SPEC_20261010.md` 保留上一轮范围与证据，不修改旧报告的历史结论。
- 续作基线 testing HEAD 为 `a9db2d6`，实际生产目录 `C:/Users/Reel/Documents/libtv-auto-main-sync` 的 main HEAD 为 `02e2e5d`；两个 Git 元数据不同，不根据 testing 的 main 引用猜生产基线。
- 两侧有既有未提交 UI/文档/原型；仅推广本轮六份文档，不同步 `.env`、ZIP、插件包、缓存、运行数据或构建产物，不回滚/覆盖无关修改。

## 测试

- testing 的 72 项文档检查通过：CW-P01 至 CW-P08/CW-A01 至 CW-A30 唯一连续、章节/阶段顺序、JSON 示例、模块引用/插件哈希、循环授权/预算/停止、Prompt/素材/状态和产品/计划/QA 一致性。检查脚本存放在仓库外 `E:/Codex/plugin-audit-creative-workflow-20261010/check-workflow-docs.mjs`，不进入生产源树。
- testing 的相关已跟踪文档 `git diff --check` 通过；新增/未跟踪文档另用脚本检查行尾、编码、代码围栏和终止换行，未发现格式错误。
- 推广前核对 main 六份目标文件未被并发修改；四份既有规范两侧基线一致。任务书两侧基线差异仅为本任务中断前的 CW-0.5/循环表述补丁，其他内容一致，适合逐文件局部推广。
- 续作基线哈希审计：testing 范围外 547 个文件未变；main 范围外 535 个文件未变，另一个 `backend/src/libtv_agent/templates/motion_actions.py` 出现非本轮操作的变化，保留不动，不同步/回滚该文件。
- 六份文档已逐文件局部同步至实际 main，SHA-256 逐文件一致；main 独立运行同一 72 项检查通过，两侧目标文档 `git diff --check` 均通过。Git 仅提示部分 LF 后续转换 CRLF，未报告格式错误。
- 本轮不提交、不推送 Git，不宣称两侧工作区干净；源码同步不是上线或运行服务更新。
- 文档-only：不运行 frontend build/lint/unit/browser，不更新页面验收状态；旧测试通过记录不代表本合同已实现。
- 不读取真实 `.env`，不连接数据库，不调用分析/生图/视频/复核 Provider，不迁移、部署、重启或写生产业务数据。

## 发现问题

- 插件旧 STATE 编号和旧参考比例存在历史叠加，需要以 v1.13.5 的先方案和 27 号规则归一化，不能机械按编号执行。
- 自主修订与“提交时不重写 Prompt”须隔离：修订走导演编译新版本，执行仅绑定；明确包含修订额度的授权可复用，未知提交不可当修订。
- 参考图显示/下载/提交不证明模型接收；Provider 无 accepted 证据时可按用户允许降级，原商品不可访问则高保真生产阻断。
- 自动 Critic 能否真实读像素、其成本与 schema 尚未验证；能力不足时禁用自动修订，人工审核不受影响。
- 人物/场景资产 API、迁移 heads、成本/指标阈值、素材许可及旧路径隔离验证仍是 CW-0.5 待办，不由本轮文字补齐追认为完成。

## 下一步

- 开展 CW-P01 至 CW-P08 前置调研/合同评审，明确各交付证据、预算/指标阈值和 Fake/Replay 测试计划。
- 前置项通过后，按 CW-1→CW-4 小包实现/测试/局部推广；导演前端仍等 Checkpoint 1。
- CW-3 后另行授权真实 SKU 小样本验证，区分规则/运行输入/像素复核/质量 A/B；无改善或成本收益不达阈值不扩大自动循环。
