---
name: multi-agent-project-governance
description: 面向大型B/S、通用C/S、Unity、共享服务端和混合工程按需绑定CONTROL/WRITE/ASSURE三类职责，协调项目状态、任务、Git、文件锁、验收和发布。默认复用当前Agent与会话，仅在真实隔离边界存在时创建额外执行槽。
---

# 多 Agent 项目治理

这是本插件的长期工程 CONTROL 入口。`Master/Planning/Developer/Review/Test/Merge/Document` 仅是旧版兼容标签，不是七个必须存在的 Agent、会话或进程。默认新增 Agent 数和新增 Provider Session 数均为零。

## 按需加载

- 作为风险审核、测试或发布的辅助 Skill 时，不加载下列参考文件；只核对项目身份、当前 Task、控制状态和最新证据。
- 首次接管或需要分离 CONTROL/WRITE/ASSURE 职责时，只读取 [职责契约](references/agent-role-contracts.md)。
- 拆解前后端、客户端、后端、数据和基础设施通道时，只读取 [系统分层](references/system-lane-model.md)。
- 涉及 Branch、Worktree、Commit、Merge 或冲突处理时，只读取 [Git治理](references/git-governance.md)。
- 涉及状态迁移、Task 记录、上下文恢复或 Checkpoint 时，只读取 [状态模型](references/state-and-task-model.md)。
- 涉及桌面任务分派、角色会话复用、任务终态归档或运行时释放时，只读取 [会话与运行时生命周期](references/session-runtime-lifecycle.md)。
- 单轮通常读取零到一份参考文件；请求确实同时跨越两个治理域时最多读取两份，禁止预读全部五份。

## 按需启动条件

- Preconditions：确认当前 Git 根目录、项目身份与最新用户目标；只读有界当前事实，不默认扫描历史。
- Applicability：由 Gate Applicability 判断本任务真实存在的 planning、development、review、testing、documentation、merge、release 工作。状态名称的排列顺序不是强制执行清单。
- Isolation：只有重叠写入、独立保证、外部运行时或真实 Worktree 边界需要隔离时，才调用任务、会话、Worktree 或文件锁能力。
- Required Evidence：只生成当前适用 Gate 的范围化证据；相同候选与指纹的有效证据直接复用。
- Acceptance：适用 Gate 全部闭合且没有活动写冲突；merge/release 仅在真实集成或交付事实存在且用户权限允许时执行。

模型可自由决定分析、实现、诊断与工具顺序；Runtime 只验证上述边界，不规定固定思考步骤。

## 单一控制事实与派生视图

当前 Task、审批、所有权、会话绑定、Gate 和证据各自只能有一个机器可写事实源。`PROJECT_STATE.md`、`CURRENT_CONTEXT.md`、摘要表和对话回执只从事实源派生，不得成为需要手工同步的第二套真相；跨文件只引用稳定 ID、版本和指纹，不建立多份全文互锁。发现多份投影不一致时，修复生成器或引用关系，不继续添加新的对账投影。

独立审核失败后只创建一个有界修复任务；修复完成只复验受影响 Gate。架构、基线或公共合同未变化时，不重新执行完整架构审核，不重建所有控制文件，也不让实现→审核→修复→复验无限递归。

## 按需职责绑定

只有当前 CONTROL 负责桌面任务与 Worktree 的创建、复用和终态回收。默认所有适用职责绑定当前 Agent/Provider Session；WRITE 仅在真实写边界存在时按稳定 `ownership_lane` 分离，ASSURE 仅在独立性 Gate 要求时分离。所有权通道由当前变更契约和真实模块边界动态提出，不能只按固定技术栈命名。Task ID、候选版本和 base SHA 是绑定内工作项，不作为新建会话理由。

会话防重键为 `project_id + repo root + execution family`；execution family 只能是 CONTROL/WRITE/ASSURE 的运行时投影。旧 `role family` 输入先映射到该键，不得并行维护第二套绑定身份，也不得因旧角色标签不同创建重复 Session。

只有 Gate 适用且需要独立运行时的职责才运行 `dispatch_guard.py observe --ownership-lane <lane>`。只有 `CREATE_THREAD` 才能创建并立即绑定；只返回客户端ID的创建请求登记为 `SETUP_PENDING`，未确认真实任务不存在前不得再建。查询失败或超时只禁止新建替代任务，不需要新隔离运行时的已有工作降级为 `CURRENT_THREAD_BOUNDED` 继续。默认不预建常驻槽；活动 WRITE 上限为两个，同一时刻最多一个 pending create。

普通任务完成后，总控自动保存 Checkpoint、释放文件锁和外部资源、确认 writer Worktree 为 CLEAN/CLOSED，并把槽位置为 `IDLE_REUSABLE`，无需用户确认。项目终态、用户明确停止或角色槽不再需要时，总控自动归档任务并验证本地运行时已释放；归档但无法证明运行时释放时保持 `ARCHIVED_RUNTIME_UNVERIFIED` 并阻止继续创建。不得用强杀进程、强删 Worktree 或丢弃未提交修改冒充自动回收；这三类破坏性处置仍服从安全门禁。

长期或多会话总控默认最多两个同时活动 Turn，常驻槽只能复用，不能全部同时流式运行。宿主计数显示活动 Turn、流式任务、加载项目、增量事件或单任务状态体积进入压力区时，自动停止新建与重发，先 Checkpoint 并排空到一个有界工作集。`codex` 后端在 Turn 终态前消失时，将原分派标记为中断未确认；应用重启后必须用原 operation ID 和 Checkpoint 对账，再重新准入，禁止把未知状态直接当失败重跑。

调度查询必须通过 `dispatch_guard.py` 归一化：API 错误、查询超时和明确空结果是三个不同状态；前两者失败关闭，不能创建替代任务。每个任务先生成环境预检计划，确认项目上下文、运行时、浏览器/设备与并发预算满足后才分派，避免任务创建后才发现环境不兼容。

总控每次状态更新分开显示：业务价值进度、治理进度、当前阻断、是否真正修改业务源码、唯一下一业务门禁。不得把大量测试调用次数当成交付进度，不得在仍可能新增门禁时承诺“再过最后一步”。

默认并行预算是最多两个活动写任务、最多两个待收敛 ASSURE 工作项。总控主动识别安全并行机会，不要求用户重复说“并行”；只有文件/模块所有权、共享契约、迁移、核心服务、Unity受保护资产和测试环境均可证明独立时才同时运行。

复杂任务同时受治理预算约束：连续两个治理周期没有业务价值增量时，必须复用证据、缩小验证面或重新定方案；普通局部任务不得启用多会话控制账本、对抗矩阵或全套跨运行时复验。

责任标签不是执行实体，不要求运行环境必须存在同名预置 Agent。环境支持并行时，CONTROL 按依赖图和预算自动分派；环境不支持、查询失败或所有权不能证明独立时在当前有界任务中串行，不得停留在治理阶段等待一个并不存在的会话。

CONTROL 不承载完整日志、diff 或所有 Task 全文；执行实体只返回有界结果包和证据指针。每个总控纪元达到会话健康阈值后自动 Checkpoint 并轮换，任一时刻仍只有一个活动 CONTROL。根 `CURRENT_CONTEXT.md` 是总控摘要，执行实体读取自己的 Task 上下文。项目目标由 `.ai/governance/goal-contract.json` 提供版本与指纹；目标修订后旧 Task 必须重绑定。

跨 Agent、跨会话或外部评审交接前运行 `handoff_redactor.py scan`。原始密码、令牌、私钥和带凭据 URL 一律阻断导出；需要交付时先生成脱敏副本并复扫，报告只记录类型、位置和指纹，不回显秘密值。
