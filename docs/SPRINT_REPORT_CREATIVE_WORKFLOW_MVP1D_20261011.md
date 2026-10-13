# Sprint Report · Creative Workflow MVP-1D

日期：2026-10-11
范围：Director Studio 离线人工审核与首帧选择
testing：`E:/Projects/libtv自动化生成`，`codex/testing`
实际 main：`C:/Users/Reel/Documents/libtv-auto-main-sync`，`main`

## 完成

在 MVP-1C 的 Fake 首帧候选上增加独立的人工审核和选择：

```text
生成 Fake 首帧
→ 人工审核合格 / 填写理由后拒绝
→ 合格候选单独选择 FIRST_FRAME
→ 服务端快照回显离线选择
→ 拒绝已选候选时撤回该选择
```

持续显示 `OFFLINE_SYNTHETIC_ONLY`、离线审核和离线选择，不将 Fake 的
`qualified=true` 显示为真实 QUALIFIED 或 Deliverable。
`UNKNOWN` / `WRITE_UNCERTAIN`、停止、错误阶段、旧包、非 FIRST_FRAME、
非 synthetic、非离线模式均禁用审核和选择。

## 修改

仅修改以下白名单文件，保留已有 MVP-1C 和其他协作者改动：

- `frontend/src/features/director-studio/DirectorStudio.tsx`
- `frontend/src/features/director-studio/directorApi.ts`
- `frontend/src/features/director-studio/directorModel.ts`
- `frontend/src/features/director-studio/directorApi.test.ts`
- `frontend/src/features/director-studio/directorModel.test.ts`
- `frontend/src/features/director-studio/DirectorStudio.browser-check.mjs`
- 本报告

复用既有 `review` / `select` 命令，发送 candidate_id、decision、
expected_version、command_key；拒绝要求非空理由，最多 500 字。
同任务/版本/动作/负载的失败重试复用命令键，提交中禁用重复操作。
失败不乐观写合格或选择；增加只读任务刷新，读取服务端版本及快照。
任务创建后锁定商品正面上传和重复创建入口，避免审核时更换占位原图。
授权到期时间在点击回调的局部 Date 对象中计算，保持点击后 1 小时有效，
通过 React purity 检查，没有增加规则豁免。

浏览器脚本仅为本包证据工具，不纳入 package 脚本或新增依赖。
脚本直接挂载 DirectorStudio，使用无 env、无代理的隔离 Vite 和 API fixture，
阻断外部请求，不写真实数据库或调用真实 Provider。

## 测试

testing 最终验证：

- `npm run build -- --outDir E:/Codex/director-mvp1d-evidence/testing-build`：通过。
- `npm run lint`：通过。
- Director 定向 Vitest：2 文件 / 14 项通过。
- Edge / Playwright：1440×900、390×844 两条隔离流程通过。
- 浏览器覆盖：输入→分析→选方向→授权→生成→审核失败→刷新→合格→
  选择失败→幂等键复用及键盘重试→已选→拒绝→选择撤回→UNKNOWN 禁用。
- 空白理由不能拒绝；合格前不能选择；审核提交中重复点击不增加命令；
  无页面横向溢出、无 pageerror、无外部请求。
- 查看桌面拒绝和移动已选截图；测试图片是 1×1 合成占位，
  截图只能证明控件布局和状态，不证明真实服装像素质量。
- testing 证据：`E:/Codex/director-mvp1d-evidence/testing-browser/report.json`
  及 `selected-1440.png`、`selected-390.png`、`rejected-1440.png`、
  `rejected-390.png`。

main 独立验证：

- `npm run build -- --outDir E:/Codex/director-mvp1d-evidence/main-build`：通过，
  构建输出位于仓库外，没有覆盖正式 dist。
- `npm run lint`：通过。
- Director 定向 Vitest：2 文件 / 14 项通过。
- Edge / Playwright：1440×900、390×844 两条隔离流程独立通过；
  `E:/Codex/director-mvp1d-evidence/main-browser/report.json` 保存浏览器版本、
  断言结果和源文件 SHA256；同目录保存选中/拒绝截图。
- 两侧本包白名单共 7 文件同步成功，最终逐文件 SHA256 一致，
  两侧分支仍分别是 `codex/testing` / `main`。
- tracked Director 文件的 `git diff --check` 通过；未还原、暂存或提交
  其他协作者已有改动。未执行全量 Vitest、本轮真实 API 集成或正式版验收。

证据工具执行方式（在相应仓库根目录，输出目录分别使用 testing-browser /
main-browser）：

```powershell
$env:PLAYWRIGHT_MODULE = 'E:/Codex/baseline-m0-1/playwright-runtime/node_modules/playwright/index.js'
$env:DIRECTOR_EVIDENCE_DIR = 'E:/Codex/director-mvp1d-evidence/testing-browser'
node frontend/src/features/director-studio/DirectorStudio.browser-check.mjs .
```

## SHA 与同步

没有创建新 Git 提交，本包保留在共享工作区。
HEAD 为入场基线，不能将其称为 MVP-1D 提交：

- testing HEAD：`7ac476a2446a70df341e449cb937920e36c66552`
- 实际 main HEAD：`07db236254b5a9b1686254a24231fff7f666b301`

最终核对时其他协作者提交了前端模块路由重构，Director 白名单文件未被提交，
本包文件 SHA256 未改变。最终 HEAD 为：

- testing：`7f6adf7cf46681855f97d710928e21ccf6d44313`
- 实际 main：`2fe8fd32fccd0ec89adc4ffb8a09b1fe58c849e2`

以下文件均位于 `frontend/src/features/director-studio/`，
交付身份使用最终文件 SHA256，两侧相同：

| 文件 | SHA256 |
| --- | --- |
| DirectorStudio.tsx | `6B03E7A48662B98F4F0D3F06132496FEA8E437802F38653A786F92DC9A274768` |
| directorApi.ts | `614E586BC97E73E8BD2DDB7884D76E8AED50E8CEBCE8078A7899BD634D16273C` |
| directorModel.ts | `EE8C6391A6C54B7338C9892813781C6BF30B96E34EAD87E844EBE98CF7FFEA28` |
| directorApi.test.ts | `302238349251150AF82E2BC4347DB1BB588EBD019869AA666A56ED2F3D20DC77` |
| directorModel.test.ts | `CE9F34E78B55908932DC3828B876712F5C3EF308661FC831782A412EF9EECBBE` |
| DirectorStudio.browser-check.mjs | `4FC7A41A2D80D3453C0CE1FD754699DEF05C77354FF04807B4BC8B728DB95921` |

报告自身 SHA256 由最终同步校验输出，不自引用写入本文。
同步前再次检查 main 的五个已有白名单文件均保持入场 SHA256，
确认没有生产专属差异或并发改动才复制；新增文件只限证据工具和报告。

## 发现问题与限制

- 后端 `review` 接收 reason，但 Review 记录不保存理由，任务快照也不提供
  REJECTED / UNVERIFIED 的区别。本包必须遵守“不改后端”边界：
  发送拒绝理由，并明确标注“本页备注，服务端未持久化”。
  只有当前页面确认成功的拒绝显示“已拒绝（本页确认）”；
  刷新任务后清除该本页确认，显示“未合格（快照未提供拒绝决定）”。
  理由没有形成完整持久审核审计，这一合同缺口仍待后端单独开发。
- 页面整页刷新后的任务恢复、多人同时审核、真实权限服务端集成、
  PostgreSQL、多 worker、真实 Provider/像素质量均未在本包验证。
  HTTP 409 场景和 UNKNOWN 禁用由浏览器 fixture 验证；
  未声称 fixture 是真实数据库/Provider 的集成验收。
- 保留 MVP-1C 的品牌/备注尚未进入服务端合同限制。
- 未执行迁移、部署、服务重启或付费调用，没有修改 .env、OpenAPI、
  frontend/src/api.ts、后端或其他页面。

## 下一步

后续独立后端合同包应持久化拒绝理由、返回人审决定和审核来源，
随后补充整页恢复及真实隔离服务集成验证。
本包仅交付离线 UI 最小闭环，不更新真实质量、生产就绪或人工上线接受状态。
