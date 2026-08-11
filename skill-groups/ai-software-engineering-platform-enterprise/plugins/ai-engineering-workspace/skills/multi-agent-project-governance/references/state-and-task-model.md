# 状态与任务模型

## 项目事实

- `.ai/governance/project-state.json`：项目身份、版本、架构、数据库/API版本和风险的机器事实源。
- `PROJECT_STATE.md`：当前版本/分支、已完成、开发中、待处理、数据库/API版本、风险的可读投影。
- `CURRENT_CONTEXT.md`：当前目标、完成修改、未完成事项、关键决定、禁止事项。
- `CHANGELOG.md`、`ARCHITECTURE.md`：发布历史和架构事实。

## 任务事实

`.ai/tasks/<TASK-ID>.json` 包含目标、状态、控制状态、负责人角色、分支、影响文件、Commit、审核、测试、证据、文档、风险、闭环和发布信息。

合法状态：`Created → Planning → Development → Review → Testing → Merged → Released`。暂停/恢复是控制状态，不倒退或跳过生命周期。方向调整必须写 checkpoint 和 decision；插入需求必须创建新 Task ID 并声明依赖，不能偷偷扩大旧任务。

## 上下文恢复

新 Agent 先核对项目 ID，再读四个根文档、任务 JSON、最新 checkpoint 和 Git 状态。聊天摘要只能作为线索，不能覆盖仓库事实。
