---
name: worktree-task-manager
description: 按受保护分支、任务状态、角色和文件锁规则创建、暂停、恢复及清理Git Worktree。用于并行写代码；禁止直接修改main/develop/release、在同一分支并行写入或未合并强制清理。
---

# Worktree 任务管理

## 允许创建

- 已存在 Task ID，且任务处于 `Planning` 或 `Development`；
- `feature/*`、`bugfix/*` 基于 `develop`，`hotfix/*` 基于 `main`；
- `release/*` 仅 Merge Agent 可创建并基于 `develop`；
- 并行任务写入不同模块，锁检查通过。

```bash
python <plugin-root>/scripts/git_workspace.py --root . create --task-id KG-001 --branch feature/KG-001-login --agent-role "Developer Agent"
```

## 禁止创建

- 直接使用 `main`、`develop` 或 `release`；
- 同文件、高耦合模块、Unity Scene/Prefab/ProjectSettings 或数据库迁移并行写入；
- 项目未初始化、任务不存在、任务已进入 Review 之后；
- 只读分析、单个微小且无需隔离的任务。

暂停只更新租约并保留目录与未提交内容。删除前检查脏文件与目标分支合并关系；禁止自动删分支或用强制覆盖解决冲突。
