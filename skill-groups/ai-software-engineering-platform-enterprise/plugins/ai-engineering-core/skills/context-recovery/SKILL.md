---
name: context-recovery
description: 在新会话、Agent接管或上下文压缩后，从项目身份、有界工作集、.ai任务状态、正式文档和最新检查点恢复事实，并验证目标、锁、分支和下一步。不得依赖旧聊天摘要或其他仓库状态作为唯一依据。
---

# 上下文恢复

## 恢复顺序

1. 确认当前 Git 根目录与 `.ai/governance/project-state.json` 的 `project_id`；
2. 当前任务 `.ai/tasks/<TASK-ID>.json`、锁定决定和控制状态，只读取当前字段与最近事件；
3. 当前 Git 分支、HEAD、status、diff 与 Worktree；
4. `PROJECT_STATE.md` 与 `CURRENT_CONTEXT.md` 的有界工作集；
5. `CHANGELOG.md`、`ARCHITECTURE.md` 和当前阶段证据；
6. 最新相关 `.ai/runtime/checkpoints/*.json` 与 `checkpoint-ledger.json`；
7. `.ai/runtime/skill-routing.json`；先核对阶段与路由指纹，再恢复最多两个活跃原子 Skill，待执行项不预加载；
8. `.ai/context/project.json`、`tech-stack.json` 和旧版运行状态（如存在）；
9. Git common dir 中的工作区租约和文件锁；
10. 冷归档只按 Task ID、checkpoint名或时间点精确读取，禁止扫描整个 `.ai/archive/`；
11. 旧聊天摘要只用于发现可能缺口，不得覆盖以上事实。

运行：

```bash
python3 <plugin-root>/scripts/statectl.py --root . validate
python3 <plugin-root>/scripts/statectl.py --root . status
python3 <plugin-root>/scripts/statectl.py --root . memory-status
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
- 活动工作集字符数、checkpoint保留/收敛数量和完整事实源。
- 当前阶段、活跃原子 Skill、待执行 Skill 与路由指纹。

任何关键状态或项目身份冲突时标记 `BLOCKED_CONTEXT_CONFLICT`，不得自行选择旧聊天或另一仓库的方案覆盖正式状态。存在新版多Agent治理状态时，以其任务状态机为主，旧版 `task.json` 仅作迁移线索。恢复时先再次显示轻量路由回执；路由指纹与当前请求不一致时重新计算，不得照搬压缩前的原子 Skill。
