---
name: context-recovery
description: 在新会话、会话恢复或多次上下文压缩后，从 .ai 状态和最新检查点恢复项目事实，并验证当前目标、锁定决策、分支和下一步。不得依赖旧聊天摘要作为唯一依据。
---

# 上下文恢复

## 恢复顺序

1. `.ai/schema.json`
2. `.ai/context/project.json`
3. `.ai/context/tech-stack.json`
4. `.ai/governance/locked-decisions.json`
5. `.ai/runtime/task.json`
6. `.ai/runtime/active-context.md`
7. 最新 `.ai/runtime/checkpoints/*.json`
8. 当前 Git 分支、HEAD 和工作区状态

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

任何关键状态冲突时标记 `BLOCKED_CONTEXT_CONFLICT`，不得自行选择旧聊天中的方案覆盖正式状态。
