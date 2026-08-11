---
name: project-state-manager
description: 初始化、校验和同步PROJECT_STATE.md、CURRENT_CONTEXT.md、CHANGELOG.md、ARCHITECTURE.md及项目级机器状态；用于任务开始、接管、上下文恢复、阶段检查点和多仓库隔离。
---

# 项目状态管理

初始化：

```bash
python <plugin-root>/scripts/governance_state.py --root . init --project-id PROJECT-A --architecture hybrid --version 0.1.0 --database-version none --api-version v1
```

`PROJECT_STATE.md` 必须包含当前版本、当前分支、已完成功能、开发中功能、待处理问题、数据库版本、API版本、风险列表。`CURRENT_CONTEXT.md` 必须包含当前目标、完成修改、未完成事项、关键决定和禁止事项。

所有 Agent 开始任务都必须读取四个根文档与 Git 状态。每个阶段结束、暂停、方向调整和交接时创建 checkpoint，并刷新可读状态。机器状态是事实源，Markdown 是审计视图；不得手工制造互相矛盾的状态。
