# Project Workflow

## Test And Production Synchronization

- Treat `codex/testing` as the test branch and `main` as the production branch.
- For every requested change to this project, implement and validate it on the test branch, then synchronize the same change to the production branch before completing the task.
- Skip production synchronization only when the user explicitly says to delay or omit it.
- Preserve production-only behavior when promoting changes; compare the branches and resolve differences instead of overwriting the production tree blindly.
- Never synchronize local secrets, runtime state, generated artifacts, caches, or the real `.env` file. Source files, safe configuration examples, tests, and relevant documentation should be synchronized.
- At the end of each change, verify both worktrees and report whether the production synchronization succeeded.
