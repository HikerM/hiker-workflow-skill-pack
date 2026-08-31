---
name: worktree-task-manager
description: 按真实库存预算、受保护分支、任务状态、租约、角色和文件锁规则创建、暂停及恢复 Git Worktree。用于受控并行写代码；创建前阻断嵌套工作目录和超额活动任务，历史接管与关闭交给工作目录安全收敛。
---

# Worktree 任务管理

## 允许创建

- 先运行快速库存；不存在嵌套 Worktree，且活动写 Worktree 少于项目预算；
- 已存在 Task ID，Gate Applicability 证明当前有 WRITE 工作，且任务处于允许写入的兼容状态坐标；
- `feature/*`、`bugfix/*` 基于 `develop`，`hotfix/*` 基于 `main`；
- `release/*` 仅在真实集成/交付事实要求隔离时由获授权的 WRITE 执行实体创建，并基于 `develop`；
- 并行任务写入不同模块，锁检查通过。

```bash
python <plugin-root>/scripts/git_workspace.py --root . create --task-id KG-001 --branch feature/KG-001-login --agent-role "WRITE"
```

## 禁止创建

- 直接使用 `main`、`develop` 或 `release`；
- 同文件、高耦合模块、Unity Scene/Prefab/ProjectSettings 或数据库迁移并行写入；
- 项目未初始化、任务不存在、当前没有适用的 WRITE 工作或已经越过允许写入的状态边界；
- 存在嵌套 Worktree、活动写 Worktree 已达预算或租约过期未复核；
- 只读分析、单个微小且无需隔离的任务。

暂停只更新租约并保留目录与未提交内容；租约到期只要求复核，不自动删除。历史接管、分类、合并后关闭或登记清理必须切换到「工作目录安全收敛」。

旧版 Developer/Merge 标签只用于 CLI 兼容映射；责任不是 Agent、Session、Worktree 或创建理由。默认复用当前执行实体，只有真实写冲突或隔离要求才创建 Worktree。
