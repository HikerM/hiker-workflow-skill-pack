---
name: change-ownership-merge
description: 在真实合并适用时，由CONTROL只读检查分支、提交、所有权、冲突、锁和适用证据，生成可审计决策；仅在用户授权且门禁通过后执行非强制Git合并。禁止直接修改main、绕过门禁或强制覆盖冲突。
---

# Git 合并治理

允许流向：`feature/*|bugfix/* → develop`、`develop → release`、`release/* → main`、`hotfix/* → main`。提交消息使用 `feat:`、`fix:`、`refactor:`、`docs:`、`test:`，也允许 `chore/perf/build/ci` 及 scope。

```bash
python <plugin-root>/scripts/merge_guard.py --root . --task-id KG-001 --source feature/KG-001-login --target develop
```

只有 Gate Applicability 把 merge 判为 `REQUIRED`，结果为 `PASS` 或经人工接受的 `PASS_WITH_WARNINGS`，且用户已经明确授权合并时，获授权的 WRITE 执行实体才能执行非强制合并。执行后记录 merge commit，再更新兼容状态坐标。冲突时输出双方目的和候选方案，禁止 `ours/theirs` 无审查覆盖。旧版 Merge Agent 仅是兼容责任标签，不是必须创建的 Agent 或 Session。
