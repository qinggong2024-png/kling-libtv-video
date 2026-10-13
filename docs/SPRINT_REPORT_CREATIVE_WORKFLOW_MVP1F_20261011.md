# Sprint Report · Creative Workflow MVP-1F

日期：2026-10-11
范围：Director Studio 服务端最新人工审核回显
分支：`codex/testing` → 实际 `main`

## 完成

Director API 适配 `snapshot.latest_review`，Director Studio 按
`candidate_id` 优先显示服务端最新人工审核决定和拒绝理由：

```text
REJECTED + reason
→ 刷新任务
→ 服务端审核：已拒绝
→ 服务端拒绝理由：...
```

服务端记录存在时不会被旧的本页状态或拒绝草稿覆盖。Fake 候选仍明确限定为
`OFFLINE_SYNTHETIC_ONLY`，不会显示为真实 QUALIFIED 或 Deliverable。
移除 MVP-1D 中“服务端未持久化”的过时提示。

## 修改

仅修改 Director 白名单文件及本报告：

- `frontend/src/features/director-studio/DirectorStudio.tsx`
- `frontend/src/features/director-studio/directorApi.ts`
- `frontend/src/features/director-studio/directorApi.test.ts`
- `frontend/src/features/director-studio/DirectorStudio.browser-check.mjs`
- 本报告

`rejectionReasons` 仍作为拒绝输入草稿保留；旧的本页拒绝决定状态已移除，
避免它覆盖服务端较新的 `latest_review`。

## 测试

testing（`E:/Projects/libtv自动化生成`）：

- `npm test -- src/features/director-studio/directorApi.test.ts src/features/director-studio/directorModel.test.ts`：2 文件 / 14 项通过。
- `npm run lint`：通过。
- `npm run build -- --outDir E:/Codex/director-mvp1f-evidence/testing-build`：通过。
- `DirectorStudio.browser-check.mjs`：1440×900 与 390×844 均通过；fixture 回放拒绝、刷新、服务端审核决定和拒绝理由回显，阻断外部请求。

main（`C:/Users/Reel/Documents/libtv-auto-main-sync`）：

- `npm test -- src/features/director-studio/directorApi.test.ts src/features/director-studio/directorModel.test.ts`：2 文件 / 14 项通过。
- `npm run lint`：通过。
- `npm run build -- --outDir E:/Codex/director-mvp1f-evidence/main-build`：通过。
- `DirectorStudio.browser-check.mjs`：1440×900 与 390×844 均通过。

未调用真实 Provider、未部署、未迁移、未修改后端或 `.env`。

## 限制

本包只消费 MVP-1E 已提供的 `snapshot.latest_review`；多个候选同时存在时，
单个 `latest_review` 只对同候选显示，其他候选继续显示自身候选状态。
真实 API 集成和正式版浏览器验收未执行。

## 白名单与同步

本包只改动：

- `frontend/src/features/director-studio/DirectorStudio.tsx`
- `frontend/src/features/director-studio/directorApi.ts`
- `frontend/src/features/director-studio/directorApi.test.ts`
- `frontend/src/features/director-studio/DirectorStudio.browser-check.mjs`
- `docs/SPRINT_REPORT_CREATIVE_WORKFLOW_MVP1F_20261011.md`

同步前已比较 testing 与实际 main 的同名 Director 文件；未覆盖 main
已有差异。同步后将逐文件校验 SHA256，并在实际 main 独立运行同一组定向检查。

最终白名单 SHA256（testing/main 一致）：

- `DirectorStudio.tsx`: `30DFAFECA7862A8F37A9919AB133E0BF0F47090FF24FBB6BD2BF65A6F87DDB44`
- `directorApi.ts`: `B6DE3C6F366C3083380333EDA42769D9CCB6C876DBF774546015A3863C15B832`
- `directorApi.test.ts`: `E5345EE6D91D9B0569581A96C993E307481D23B309CEEC4E5A9FCB6991E58F3B`
- `DirectorStudio.browser-check.mjs`: `28E0DF1A2AFEF38FD9D80E04E23BCAA5A0874355EA1018D2070E92D305E9800A`
- 报告自身未写入 SHA，避免自引用造成不稳定值。
