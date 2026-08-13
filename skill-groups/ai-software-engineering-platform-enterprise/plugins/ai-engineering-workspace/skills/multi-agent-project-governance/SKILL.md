---
name: multi-agent-project-governance
description: 面向大型B/S、通用C/S、Unity、共享服务端和混合工程建立Master/Planning/Developer/Review/Test/Merge/Document七角色控制平面，协调项目状态、任务、Git、文件锁、验收和发布。用于长期多Agent工程总控，不用于绕过人工授权无限执行。
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

## 单一控制事实与派生视图

当前 Task、审批、所有权、会话绑定、Gate 和证据各自只能有一个机器可写事实源。`PROJECT_STATE.md`、`CURRENT_CONTEXT.md`、摘要表和对话回执只从事实源派生，不得成为需要手工同步的第二套真相；跨文件只引用稳定 ID、版本和指纹，不建立多份全文互锁。发现多份投影不一致时，修复生成器或引用关系，不继续添加新的对账投影。

独立审核失败后只创建一个有界修复任务；修复完成只复验受影响 Gate。架构、基线或公共合同未变化时，不重新执行完整架构审核，不重建所有控制文件，也不让实现→审核→修复→复验无限递归。

## 会话绑定与延迟启动防重

会话调度以 `Task ID + 角色 + repo root + base SHA` 为幂等键。只返回 `clientThreadId` 时记录 `SETUP_PENDING`，它既不是 RUNNING，也不是失败；在查询桌面任务状态、确认没有真实 `threadId` 且 pending lease 到期前，禁止创建恢复会话或第二个 writer。延迟启动的旧任务出现时，先冻结双方写入并按幂等键选出唯一会话，禁止两个会话在同一 Worktree“各自收敛”。

总控每次状态更新分开显示：业务价值进度、治理进度、当前阻断、是否真正修改业务源码、唯一下一业务门禁。不得把大量测试调用次数当成交付进度，不得在仍可能新增门禁时承诺“再过最后一步”。

默认并行预算是最多两个活动写任务、最多两个处于 Review/Testing 的待收敛任务。达到预算后先审核、测试和合并现有任务，不继续制造分支、Worktree 与上下文债务；可在项目状态中显式调小，扩大预算必须由用户或 Master Agent Checkpoint 确认。

复杂任务同时受治理预算约束：连续两个治理周期没有业务价值增量时，必须复用证据、缩小验证面或重新定方案；普通局部任务不得启用多会话控制账本、对抗矩阵或全套跨运行时复验。

角色名称是职责契约，不要求运行环境必须存在同名预置 Agent。若用户明确要求多角色并行，可把契约分配给 Subagent；否则当前 Agent 串行履行，并保持 Review/Test 独立证据。
