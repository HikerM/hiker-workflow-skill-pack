---
name: worktree-task-manager
description: 按真实库存预算、受保护分支、任务状态、租约、角色和文件锁规则创建、暂停及恢复 Git Worktree。用于受控并行写代码；创建前阻断嵌套工作目录和超额活动任务，历史接管与关闭交给工作目录安全收敛。
---

# Worktree 任务管理

## 允许创建

- 先运行快速库存；不存在嵌套 Worktree，且活动写 Worktree 少于项目预算；
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
- 存在嵌套 Worktree、活动写 Worktree 已达预算或租约过期未复核；
- 只读分析、单个微小且无需隔离的任务。

暂停只更新租约并保留目录与未提交内容；租约到期只要求复核，不自动删除。历史接管、分类、合并后关闭或登记清理必须切换到「工作目录安全收敛」。
