---
name: multi-project-portfolio-manager
description: 注册、激活和检查多个Git仓库的项目身份与状态隔离，确保每个项目独立维护PROJECT_STATE、CURRENT_CONTEXT、CHANGELOG、ARCHITECTURE、任务和分支。用于多项目组合管理和切换防污染。
---

# 多项目组合管理

```bash
python <plugin-root>/scripts/portfolio_manager.py --registry ~/.codex/ai-engineering/projects.json register --project-id PROJECT-A --path D:/repos/project-a
python <plugin-root>/scripts/portfolio_manager.py --registry ~/.codex/ai-engineering/projects.json activate --project-id PROJECT-A
python <plugin-root>/scripts/portfolio_manager.py --registry ~/.codex/ai-engineering/projects.json check --project-id PROJECT-A --cwd D:/repos/project-a
```

每次切换先验证当前目录 Git 根、登记路径与 `.ai/governance/project-state.json` 的 `project_id` 三者一致。不得复制任务状态、文件锁、分支名或 CURRENT_CONTEXT 到另一项目；跨项目依赖只通过带版本的接口、包或显式交接文档表达。
