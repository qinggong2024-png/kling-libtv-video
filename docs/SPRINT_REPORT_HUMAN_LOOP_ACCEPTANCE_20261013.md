# Sprint Report: Creative Core / Sprint 4 Isolated Acceptance

日期：2026-10-13
状态：隔离整合验收通过；真实人工生产验收未完成，未部署。

## 完成

- 使用合成球衣正面图调用现有 HTTP API，建立实际隔离任务与来源 hash。
- 配置并冻结 Brand DNA，返回卧室镜面、复古书店、夜间街道三个 Fake 方向。
- 选 B 后核对九字段 Package、原图片 Prompt、来源、品牌版本和字段状态。
- 明确授权 Fake 首帧后，核对实际 batch/item/output 与原包、任务及 hash。
- 从导演候选和旧图片输出两个入口追加 PASS/REWORK/FAIL，验证历史与重放。
- 默认导出排除合成评价；诊断显式导出保留 synthetic 标识。
- 视频预检保留 FIRST_FRAME/SHOT_01 独立映射，阻断真实提交及交付。

## 修改

- 新增 test_creative_human_loop_acceptance.py，只复用已有 API/服务与隔离 fixture。
- 更新本报告、研发主线状态和变更记录；没有新增运行接口或执行逻辑。
- 现有 Canonical State、旧执行引擎、Provider 和账本保持本轮之前的边界。

## 测试

- testing 及实际 main 独立各 3 项整合测试通过，Ruff 通过，新增文件哈希一致。
- 两侧重新执行 Package 浏览器：1440/1024/768/390 的复制、下载、刷新、
  剪贴板失败和历史兼容通过；1440/390 品牌稳定 ID/版本及冻结受众通过。
- 两侧重新执行 Director 交付准备浏览器：1440x900、390x844 及无效引用、
  网络失败恢复通过；不创建真实视频任务。
- Human Review 四视口真实评价 API、权限/事务、前端测试与构建见
  SPRINT_REPORT_HUMAN_REVIEW_20261013.md。
- 证据：E:/Codex/verification/human-loop-sprint4 和 human-review。
- 所有测试使用隔离 SQLite、合成图片及独立浏览器上下文；零 Provider、
  付费请求、生产数据写入、部署、迁移或服务重启。

## 发现问题

| 验收项 | 当前事实 |
| --- | --- |
| 产品输入 | 隔离上传、来源 hash、任务关联通过 |
| 产品理解 | 仍为 FAKE_NOT_IMAGE_ANALYSIS，不分析真实服装像素 |
| 三方向 | 品牌配置与 Fake 模板返回，不宣称模型真实创作 |
| Package | 九字段与来源可交接；未知身份保留未提供，视频是 PROPOSED 草案 |
| 图片生产 | Fake 输出为原商品图占位；既有图片记录接线通过，真实生成未验 |
| 视频生产 | 现有桥仅预检，provider_submission_allowed=false；真实任务创建未接通 |
| 人工评价 | 隔离真实持久化通过；真实成片质量和使用效率未验 |
| 正式入口 | 2026-10-13 探测 http://192.168.30.126:5173/ 拒绝连接 |
| 发布 | 源码已同步 main；正式实例版本、人工方向接受、上线批准未验 |

## 下一步

按用户“架构、数据模型或生产流程发生重大变化时停止”的要求，
在真实生产接线边界暂停对应实施。Sprint 1-3 的工程完成不等于整个项目交付。

建议后续批准一个最小真实执行接线包，先做源代码与隔离验收：

1. 核实并复用现有产品分析能力；区分真实观察、品牌建议和待确认字段，
   替换 Fake-only 规划路径，保留冻结包与来源校验。
2. 将已确认 Package 通过 Adapter 接到现有 image-generation-batches，
   保留原 Prompt、输入字节、授权、幂等、配额与 UNKNOWN 处理。
3. 将已合格图片通过 Adapter 接到现有 video-tasks；明确 director_fixed
   所需合同，保留最终审核，不重跑自动规划或注入学习。
4. 先证明各执行记录与素材、包、任务可追溯，再申请受控真实球衣样本。

这是待批准方案，不是已实现能力。不能只删除 offline_only 或把
provider_submission_allowed 改为 true。若旧记录/账本无法承载所需关系，
提交具体字段差异再决定，不静默增加表、迁移或第二套账本。

本方案审批只覆盖后续开发，不自动授权真实模型调用、付费样本、
生产写入、部署或服务重启；真实样本继续按 CRB5_SINGLE_SAMPLE_READINESS_20261013.md。
