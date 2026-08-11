# Git Governance Layer

## 长期分支

- `main`：已发布、可回滚基线；禁止 Agent 直接写。
- `release`：发布候选集成分支，仅 Merge Agent 管理。
- `develop`：日常集成分支，功能和缺陷分支的目标。

## 短期分支

- `feature/<task-id>-<slug>`：基于 develop。
- `bugfix/<task-id>-<slug>`：基于 develop。
- `hotfix/<task-id>-<slug>`：基于 main。
- `release/<version>`：基于 develop，仅 Merge Agent。

提交采用 Conventional Commit：`feat:`、`fix:`、`refactor:`、`docs:`、`test:`，允许 scope 与破坏性变更标记。一个提交保持一个可解释目的，并把 Commit ID 写回任务。

合并顺序：Developer Commit → Review Agent → Test Agent → Feature Closed Loop → Merge Agent预检/处理冲突 → 非强制合并 → 状态更新。禁止 Developer 直接合并 main，禁止跳过失败门禁。
