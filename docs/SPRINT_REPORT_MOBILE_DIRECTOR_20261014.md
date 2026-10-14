# Sprint 8 P0.5：Mobile Director Fix

日期：2026-10-14

## 完成

- 修复 390px 导演台商品输入动作区被底部导航遮挡的问题。
- 390×844 下空输入和上传后的按钮均完整可见；上传后按钮底部为 768px，导航顶部为 780px，保留 12px 间距。
- 390×664 等短屏使用正常文档流和滚动，避免吸附动作区遮盖输入。
- 保留高级设置入口、备注编辑、品牌必填条件和原分析按钮逻辑。

## 修改

- `frontend/src/features/director-studio/directorStudio.css`：仅增加宽度不超过 420px 的商品输入局部规则，复用 Foundation spacing；吸附间距包含现有 64px 导航及 safe-area。高度小于 780px 时取消吸附。
- `scripts/ui-director-mobile-check.mjs`：新增隔离浏览器检查，覆盖空输入、上传、品牌必填、高级设置、滚动、导航返回及桌面布局。
- 本报告及 `docs/CHANGELOG.md`。
- 未修改 JSX、App Shell、全局样式、API、Agent、Workflow、Provider、Prompt 或生产逻辑。

## 测试

| 检查 | codex/testing | main |
| --- | --- | --- |
| build | 通过 | 通过，产物输出到外部目录 |
| lint | 通过 | 通过 |
| unit | 61 文件 / 420 项通过 | 62 文件 / 416 项通过 |
| 专项浏览器 | 66 项通过 | 66 项通过 |

- 专项尺寸：390×844（27 项）、390×664（25 项）、1024×768（7 项）、1440×900（7 项）。
- 确认按钮几何范围及中心命中，无横向溢出；桌面 CTA 保持正常文档流。人工检查移动截图，确认高级设置和按钮不互相遮挡。
- 专项使用真实前端入口及隔离 fixture，禁止外部请求和非 GET/HEAD 请求；零写入、零外部请求，检查前后源码哈希一致。仅 trial 点击，不提交分析或真实生成。
- 两侧现有 creative-shell 回归均通过 1440/1024/768/390 及任务深链与滚动恢复。

## 发现与限制

- main 首次验证被并行 App 引用缺少 `getAllTaskHistory` 导出阻断。并行工作补齐该导出后，本轮重新运行 build/lint/unit 和专项浏览器全部通过；本任务未修改该 API。
- 两侧存在持续并行开发和未提交修改，以上结论对应各自已验证快照；单测数量差异不能视为同一源码快照。
- 本轮只处理窄屏导演商品输入动作区，不代表全产品移动端验收，也不验证真实工作流、AI 能力或付费生成。

## 同步

- 样式及新增专项检查已从 codex/testing 局部同步至实际 main 工作区 `C:/Users/Reel/Documents/libtv-auto-main-sync`，文件 SHA-256 分别一致。
- 样式：`459557562e43b869cf64ce001c1fb9967b96d4e64134026ac1aaf159e566704a`。
- 专项脚本：`0baf6bdc1f8244a796c2ef1ad91e6a53b8ec35265ec50cbfc1b8c3eb1cf90685`。
- 保留两侧并行文件和分支差异，未整目录覆盖。源码同步不等于线上部署；未重启服务、修改生产数据或执行真实生成。

## 证据

- testing：`E:/Codex/sprint8-mobile-director-20261014/testing/final/report.json`。
- testing 工作区回归：`E:/Codex/sprint8-mobile-director-20261014/testing/shell/report.json`。
- main 专项重验：`E:/Codex/sprint8-mobile-director-20261014/main/recheck/report.json`。
- main 工作区回归重验：`E:/Codex/sprint8-mobile-director-20261014/main/shell-recheck/report.json`。
- 两侧 build/lint/unit 日志位于各自证据目录的 `final-*.log`。

## 下一步

- 本次移动动作区缺陷已修复；后续 Task Center / Library / Settings 体验统一仍需单独确定范围。
