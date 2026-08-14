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
- 涉及桌面任务分派、角色会话复用、任务终态归档或运行时释放时，只读取 [会话与运行时生命周期](references/session-runtime-lifecycle.md)。
- 单轮通常读取零到一份参考文件；请求确实同时跨越两个治理域时最多读取两份，禁止预读全部五份。

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

## 总控强制执行的固定角色槽

只有 Master Agent 负责桌面任务与 Worktree 的创建、复用和终态回收。会话槽位以 `project_id + repo root + role family` 为稳定身份，Task ID、候选版本和 base SHA 是槽内工作项，不再作为新建会话的理由。固定角色族为：`master`、`writer`、`assurance`、`control`、`browser`；实现、修复和返工复用同一 writer，Review、Testing 与 Reverify 复用同一 assurance。独立审核依靠只读权限和冻结候选证据，不依靠无限创建审核会话或审核 Worktree。

每次分派先运行 `dispatch_guard.py observe`。返回 `REUSE_THREAD`、`CONTINUE_EXISTING` 或 `QUEUE` 时禁止创建；只有 `CREATE_THREAD` 才能创建一次，并立即 `bind`。只返回 `clientThreadId` 时记录 `SETUP_PENDING`；查询失败、超时、pending 未到期或已有活动槽位时一律失败关闭。默认每项目最多四个常驻角色槽、同一时刻最多一个 pending create。

普通任务完成后，总控自动保存 Checkpoint、释放文件锁和外部资源、确认 writer Worktree 为 CLEAN/CLOSED，并把槽位置为 `IDLE_REUSABLE`，无需用户确认。项目终态、用户明确停止或角色槽不再需要时，总控自动归档任务并验证本地运行时已释放；归档但无法证明运行时释放时保持 `ARCHIVED_RUNTIME_UNVERIFIED` 并阻止继续创建。不得用强杀进程、强删 Worktree 或丢弃未提交修改冒充自动回收；这三类破坏性处置仍服从安全门禁。

调度查询必须通过 `dispatch_guard.py` 归一化：API 错误、查询超时和明确空结果是三个不同状态；前两者失败关闭，不能创建替代任务。每个任务先生成环境预检计划，确认项目上下文、运行时、浏览器/设备与并发预算满足后才分派，避免任务创建后才发现环境不兼容。

总控每次状态更新分开显示：业务价值进度、治理进度、当前阻断、是否真正修改业务源码、唯一下一业务门禁。不得把大量测试调用次数当成交付进度，不得在仍可能新增门禁时承诺“再过最后一步”。

默认并行预算是最多两个活动写任务、最多两个处于 Review/Testing 的待收敛任务。达到预算后先审核、测试和合并现有任务，不继续制造分支、Worktree 与上下文债务；可在项目状态中显式调小，扩大预算必须由用户或 Master Agent Checkpoint 确认。

复杂任务同时受治理预算约束：连续两个治理周期没有业务价值增量时，必须复用证据、缩小验证面或重新定方案；普通局部任务不得启用多会话控制账本、对抗矩阵或全套跨运行时复验。

角色名称是职责契约，不要求运行环境必须存在同名预置 Agent。若用户明确要求多角色并行，可把契约分配给 Subagent；否则当前 Agent 串行履行，并保持 Review/Test 独立证据。

跨 Agent、跨会话或外部评审交接前运行 `handoff_redactor.py scan`。原始密码、令牌、私钥和带凭据 URL 一律阻断导出；需要交付时先生成脱敏副本并复扫，报告只记录类型、位置和指纹，不回显秘密值。
