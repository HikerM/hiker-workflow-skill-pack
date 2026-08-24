# 状态与任务模型

## 项目事实

- `.ai/governance/project-state.json`：项目身份、版本、架构、数据库/API版本和风险的机器事实源。
- `PROJECT_STATE.md`：当前版本/分支、已完成、开发中、待处理、数据库/API版本、风险的可读投影。
- `CURRENT_CONTEXT.md`：总控的当前目标、活动Task摘要、关键决定和禁止事项；执行角色读取 `.ai/runtime/task-contexts/<Task-ID>.md`。
- `.ai/governance/goal-contract.json`：项目目标ID、修订、结果、非目标、验收、不变量、约束和指纹；Task保存目标绑定，旧修订不得继续执行。
- `CHANGELOG.md`、`ARCHITECTURE.md`：发布历史和架构事实。

## 任务事实

`.ai/tasks/<TASK-ID>.json` 包含目标、状态、控制状态、负责人角色、分支、影响文件、Commit、审核、测试、证据、文档、风险、闭环和发布信息。

合法状态：`Created → Planning → Development → Review → Testing → MergedPendingCleanup → Merged → Released`。合并提交完成但 Worktree 尚未关闭时停留在 `MergedPendingCleanup`；暂停/恢复是控制状态，不倒退或跳过生命周期。方向调整必须写 checkpoint 和 decision；插入需求必须创建新 Task ID 并声明依赖，不能偷偷扩大旧任务。

## 上下文恢复

新 Agent 先核对项目 ID、目标指纹、绑定Task和所有权通道，再读该Task上下文、必要根文档、最新 checkpoint 和 Git 状态。聊天摘要只能作为线索，不能覆盖仓库事实。
