---
name: multi-agent-project-governance
description: 面向大型B/S、C/S、Unity和NodeTS工程建立Master/Planning/Developer/Review/Test/Merge/Document七角色控制平面，协调项目状态、任务、Git、文件锁、验收和发布。用于长期多Agent工程总控，不用于绕过人工授权无限执行。
---

# 多 Agent 项目治理

这是本插件的 Master Agent 入口。先读取 [角色契约](references/agent-role-contracts.md)、[系统分层](references/system-lane-model.md)、[Git治理](references/git-governance.md) 与 [状态模型](references/state-and-task-model.md)。

## 启动顺序

1. 确认当前 Git 根目录与 `project_id`，不得引用其他项目状态。
2. 依次读取 `PROJECT_STATE.md`、`CURRENT_CONTEXT.md`、`CHANGELOG.md`、`ARCHITECTURE.md`、Git branch/status/log。
3. 未初始化时使用 `$project-state-manager` 初始化；需求使用 `$task-lifecycle-manager` 建立 Task ID。
4. 用 `$workspace-task-router` 生成 B/S 或 C/S 的前后端通道与依赖。
5. 写代码前用 `$worktree-task-manager` 隔离分支，并用 `$file-lock-manager` 锁定高风险文件。
6. Review、Testing、文档和 `$feature-acceptance-closure` 通过后，才允许 `$change-ownership-merge`。
7. Master Agent 决定是否进入发布门禁；用户可以随时暂停、调整、插入或恢复，所有动作先生成 checkpoint。

角色名称是职责契约，不要求运行环境必须存在同名预置 Agent。若用户明确要求多角色并行，可把契约分配给 Subagent；否则当前 Agent 串行履行，并保持 Review/Test 独立证据。
