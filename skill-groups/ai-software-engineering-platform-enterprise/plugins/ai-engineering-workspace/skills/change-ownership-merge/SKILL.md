---
name: change-ownership-merge
description: 由Merge Agent只读检查分支流向、Conventional Commit、代码所有权、冲突、文件锁和Review/Test/闭环证据，并生成可审计合并决策；只有用户明确授权且门禁通过后才执行非强制Git合并。禁止直接修改main、绕过门禁或强制选择一方覆盖冲突。
---

# Git 合并治理

允许流向：`feature/*|bugfix/* → develop`、`develop → release`、`release/* → main`、`hotfix/* → main`。提交消息使用 `feat:`、`fix:`、`refactor:`、`docs:`、`test:`，也允许 `chore/perf/build/ci` 及 scope。

```bash
python <plugin-root>/scripts/merge_guard.py --root . --task-id KG-001 --source feature/KG-001-login --target develop
```

只有结果为 `PASS` 或经人工接受的 `PASS_WITH_WARNINGS`，并且用户已经明确授权合并时，才能由 Merge Agent 执行非强制合并。执行后记录 merge commit，再把任务推进至 `Merged`。冲突时输出双方目的和候选方案，禁止 `ours/theirs` 无审查覆盖。
