---
name: context-recovery
description: 在新会话、Agent接管或上下文压缩后，从项目身份、四个根状态文档、.ai任务状态和最新检查点恢复事实，并验证目标、锁、分支和下一步。不得依赖旧聊天摘要或其他仓库状态作为唯一依据。
---

# 上下文恢复

## 恢复顺序

1. 确认当前 Git 根目录与 `.ai/governance/project-state.json` 的 `project_id`；
2. `PROJECT_STATE.md`；
3. `CURRENT_CONTEXT.md`；
4. `CHANGELOG.md`；
5. `ARCHITECTURE.md`；
6. 当前任务 `.ai/tasks/<TASK-ID>.json` 与最新 `.ai/runtime/checkpoints/*.json`；
7. `.ai/context/project.json`、`tech-stack.json`、`locked-decisions.json` 和旧版运行状态（如存在）；
8. 当前 Git 分支、HEAD、status、diff 与 Worktree；
9. Git common dir 中的工作区租约和文件锁。

运行：

```bash
python3 <plugin-root>/scripts/statectl.py --root . validate
python3 <plugin-root>/scripts/statectl.py --root . status
```

## 恢复验证

继续写代码前必须能明确回答：

- 当前目标和任务状态；
- 当前有效计划版本；
- 已完成和待完成；
- 锁定决策与禁止修改；
- 当前分支/Worktree；
- 最近验证结果；
- 未解决风险。

任何关键状态或项目身份冲突时标记 `BLOCKED_CONTEXT_CONFLICT`，不得自行选择旧聊天或另一仓库的方案覆盖正式状态。存在新版多Agent治理状态时，以其任务状态机为主，旧版 `task.json` 仅作迁移线索。
