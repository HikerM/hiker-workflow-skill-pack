---
name: multi-agent-project-governance
description: 面向大型B/S、C/S、Unity和NodeTS工程建立Master/Planning/Developer/Review/Test/Merge/Document七角色控制平面，协调项目状态、任务、Git、文件锁、验收和发布。用于长期多Agent工程总控，不用于绕过人工授权无限执行。
---

# 多 Agent 项目治理

这是本插件的 Master Agent 入口。默认只建立有界控制平面，不一次性读取全部治理资料。

## 按需加载

- 作为风险审核、测试或发布的辅助 Skill 时，不加载下列参考文件；只核对项目身份、当前 Task、控制状态和最新证据。
- 首次接管或分配七类角色时，只读取 [角色契约](references/agent-role-contracts.md)。
- 拆解前后端、客户端、后端、数据和基础设施通道时，只读取 [系统分层](references/system-lane-model.md)。
- 涉及 Branch、Worktree、Commit、Merge 或冲突处理时，只读取 [Git治理](references/git-governance.md)。
- 涉及状态迁移、Task 记录、上下文恢复或 Checkpoint 时，只读取 [状态模型](references/state-and-task-model.md)。
- 单轮通常读取零到一份参考文件；请求确实同时跨越两个治理域时最多读取两份，禁止预读全部四份。

## 启动顺序

1. 确认当前 Git 根目录与 `project_id`，不得引用其他项目状态。
2. 只读取有界启动事实：`PROJECT_STATE.md`、`CURRENT_CONTEXT.md`、当前 Task 与 Git branch/status；仅在架构、发布或历史核验阶段读取 `ARCHITECTURE.md`、`CHANGELOG.md` 和必要提交记录。
3. 大型项目或恢复长期任务时，先运行 `task_reconciler.py --mode quick`；它只解析 Git 元数据。只有发现异常、准备创建、合并或发布时才使用 `standard/deep`，不得在普通消息中扫描全部工作目录源码。
4. 未初始化时使用 `$project-state-manager` 初始化；需求使用 `$task-lifecycle-manager` 建立 Task ID。
5. 用 `$workspace-task-router` 生成 B/S 或 C/S 的前后端通道与依赖。
6. 写代码前用 `$worktree-task-manager` 隔离分支，并用 `$file-lock-manager` 锁定高风险文件。
7. Review、Testing、文档和 `$feature-acceptance-closure` 通过后，才允许 `$change-ownership-merge`；合并后的任务进入待清理状态，使用「工作目录安全收敛」关闭 Worktree 后才能完成。
8. Master Agent 决定是否进入发布门禁；用户可以随时暂停、调整、插入或恢复，所有动作先生成 checkpoint。

默认并行预算是最多两个活动写任务、最多两个处于 Review/Testing 的待收敛任务。达到预算后先审核、测试和合并现有任务，不继续制造分支、Worktree 与上下文债务；可在项目状态中显式调小，扩大预算必须由用户或 Master Agent Checkpoint 确认。

角色名称是职责契约，不要求运行环境必须存在同名预置 Agent。若用户明确要求多角色并行，可把契约分配给 Subagent；否则当前 Agent 串行履行，并保持 Review/Test 独立证据。
