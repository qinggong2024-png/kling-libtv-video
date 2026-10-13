# Sprint Report · Creative Workflow MVP-1E

日期：2026-10-11
范围：人工审核拒绝理由持久化与任务快照回显
testing：`E:/Projects/libtv自动化生成`，`codex/testing`
实际 main：`C:/Users/Reel/Documents/libtv-auto-main-sync`，`main`

## 完成

补齐 Creative Workflow 人工 `review` 的拒绝理由合同：

```text
REJECTED + 非空 reason（最多 500 字）
→ 不可变 CreativeRecord.review
→ task snapshot.latest_review 回显最新人工审核
```

`QUALIFIED` 可以不带理由；旧命令键幂等、版本 CAS、`UNKNOWN` /
`WRITE_UNCERTAIN`、stop、revoke 和选择撤回语义保持不变。没有修改 schema、
migration、API 路由、Provider 或部署配置。

## 修改

仅修改以下白名单文件：

- `backend/src/libtv_agent/creative/workflow.py`
- `backend/src/libtv_agent/services/creative_workflow.py`
- `backend/tests/test_creative_workflow.py`
- 本报告

`Review` 新增可选 `reason` 字段并限制为 500 字。`Command` 对人工拒绝做
非空校验并清理首尾空白；`QUALIFIED` 允许省略理由。执行人工审核时将完整
review payload 写入 append-only `CreativeRecord`，并更新
`snapshot.latest_review`。已有 `CreativeRecord` 唯一键和每次命令记录机制未改。

## 测试

testing：

- `.venv/Scripts/python.exe -m pytest backend/tests/test_creative_workflow.py`
  通过，21 项。
- `.venv/Scripts/python.exe -m ruff check` 通过，覆盖本包三个 Python 文件。
- `git diff --check` 通过。
- 新增覆盖：缺失理由、501 字拒绝理由、理由首尾空白、最新快照回显、
  `REJECTED` 与 `QUALIFIED` 两条不可变人工审核记录。

未执行 Provider、迁移、部署、服务重启、真实付费调用或正式版验收。

## 发现与限制

当前 `CreativeRecord` 继续使用既有唯一键 `(task_id, kind, record_key)`；
审核记录以 `command_key` 作为不可变记录键，因此同一候选可以保留多次审核
决定，snapshot 只回显最新人工审核。Fake Critic 的 `UNVERIFIED` 记录仍不带
人工拒绝理由，符合其非人工审核语义。

## 同步

testing 验证通过后，仅将上述四个白名单文件逐文件同步到实际 `main` 工作树，
再独立运行相同 pytest、Ruff 和 `diff --check`。同步不包含 secrets、runtime
state、generated artifacts、cache 或其他并行改动。

