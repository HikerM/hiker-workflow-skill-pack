---
name: project-state-manager
description: 初始化、校验和同步PROJECT_STATE.md、CURRENT_CONTEXT.md、CHANGELOG.md、ARCHITECTURE.md及项目级机器状态；用于任务开始、接管、上下文恢复、阶段检查点和多仓库隔离。
---

# 项目状态管理

初始化：

```bash
python <plugin-root>/scripts/governance_state.py --root . init --project-id PROJECT-A --architecture hybrid --version 0.1.0 --database-version none --api-version v1
```

`PROJECT_STATE.md` 必须包含当前版本、当前分支、已完成功能、开发中功能、待处理问题、数据库版本、API版本、风险列表。根 `CURRENT_CONTEXT.md` 是总控有界摘要；每个活动Task另外维护 `.ai/runtime/task-contexts/<Task-ID>.md`，禁止并行Task互相覆盖上下文。项目目标以 `goal-contract.json` 的版本和指纹为机器事实源。

所有 Agent 开始任务都必须核对项目身份，并按需读取当前Task、四个根文档与 Git 状态。每个阶段结束、暂停、方向调整和交接时创建 checkpoint，并刷新有界可读状态。机器状态是事实源，Markdown 是固定大小审计视图；超出展示上限的条目必须指向 `.ai/tasks/` 或项目机器状态，不得丢弃或手工制造矛盾。

同一状态只能有一个机器可写事实源；Markdown、仪表和会话摘要只能派生生成。接管时必须先核对源码溯源：L1只更新热状态，L2使受影响模块基线失效，L3使候选和审核测试证据失效，L4隔离跨项目污染。禁止用 `.ai` 覆盖当前 Git/Manifest 证据，也禁止每轮扫描全部任务、检查点和冷归档。
