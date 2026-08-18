---
name: task-lifecycle-manager
description: 创建和推进带Task ID的工程任务状态机，记录目标、影响文件、负责人、分支、Commit、审核、测试、证据和发布结果；用于Created到Released的全过程及暂停、调整、恢复。
---

# 任务生命周期

状态只能按 `Created → Planning → Development → Review → Testing → MergedPendingCleanup → Merged → Released` 推进。合并后必须安全关闭任务 Worktree 才能进入 Merged；角色负责状态：Planning、Developer、Review、Test、Merge、Master，禁止 Developer 自审、自测后直接合并。

```bash
python <plugin-root>/scripts/governance_state.py --root . task-create --task-id KG-001 --goal "统一账户登录" --owner-agent "Planning Agent" --branch feature/KG-001-login --affected-files src/auth.ts tests/auth.test.ts
python <plugin-root>/scripts/governance_state.py --root . transition --task-id KG-001 --to Planning --agent-role "Planning Agent"
python <plugin-root>/scripts/governance_state.py --root . contract-set --task-id KG-001 --agent-role "Planning Agent" --allowed-files src/auth.ts tests/auth.test.ts --behavior-invariants "现有登录方式继续可用" --required-tests "认证单测" "登录回归"
```

使用 `contract-set` 记录本次允许文件/模块、公共契约变化、原有行为不变量和最低回归；没有范围、不变量和测试不得进入 Development。使用 `record` 写入 commit/review/test/artifact/document/decision/risk；使用 `checkpoint` 保存阶段快照。`pause` 不改变生命周期状态，只把 `control_status` 设为 PAUSED；`adjust` 记录新方向；`insert` 必须创建新的Task ID并关联原任务；`resume` 从原状态继续。未满足阶段证据门禁时不得推进。

生命周期状态之外单独维护会话绑定子状态：`SETUP_PENDING → BOUND → RUNNING → IDLE_REUSABLE / RELEASE_PENDING → RELEASED`。只有 Master Agent 管理该状态；角色槽以项目、仓库和角色族为稳定身份，Task ID 是槽内工作项。`clientThreadId` 不能当作真实 `threadId`，`SETUP_PENDING` 不能触发第二个同族会话；任何时刻一个项目仓库只能有一个活动 writer 槽。普通任务结束自动回到 `IDLE_REUSABLE`，项目终态由总控自动归档并验证运行时释放，不要求用户确认。

Development 进入 Review 前必须生成与当前 Git HEAD、工作区指纹一致的架构守卫证据，并运行 `governance_state.py candidate-freeze --task-id <TASK-ID> --agent-role "Developer Agent" --candidate-id <CANDIDATE-ID>` 冻结只读审核候选。Review、Testing 与 Merge 只可消费该 `candidate_id`；候选提交、索引、源文件集合或工作区指纹发生任何变化即 `STALE`，必须生成新候选并重新取得受影响证据。普通局部任务只需最小变更契约，不要求维护全量模块、依赖或运行拓扑配置。

跨模块、跨仓库、真实外部执行、部署回滚、同一目标反复修复或用户推翻既有结论时，必须同时启用「长链路变更收敛」。用户纠正、验收范围变化或策略失效会使旧证据失效；不得保留原 PASS 继续推进。合并与发布前必须确认同一职责只有一个活动实现路径，迁移兼容代码已经收敛，未结实验为零。

同一 Task 只有一个当前候选、一个 writer 会话槽和一个权威实现方向。修复不得不断追加新入口、新服务或版本后缀；若必须并行迁移，应登记目标、兼容边界、唯一写入者、退出条件与最迟删除 Gate。达到退出条件后先删除或隔离旧实现，再推进合并。

每个阶段状态必须区分 `governance_progress` 与 `business_progress`。校验器、控制账本或测试工具修复不等于业务 Development 已开始；验证工具失败标为 `INVALID`，只有真实产品断言失败才标记业务测试 `FAIL`。相同 Gate、源码/合同指纹和范围已有 PASS 时复用证据，禁止为了“更保险”无条件从头重跑全部矩阵。

进入 Development 前还必须服从项目并行预算：默认最多两个活动写任务；当 Review/Testing 待收敛任务达到上限时，禁止继续开启写任务。恢复长期项目时先运行 `task_reconciler.py --root .`，用 Task/Branch/Worktree/文件锁对账结果识别孤儿工作区、丢失分支和合并债务。

桌面任务或 Subagent 调度前先运行 `dispatch_guard.py observe`。查询异常和超时分别记录为 `API_ERROR`、`QUERY_TIMEOUT`，都必须失败关闭；只有 `EMPTY_CONFIRMED` 才允许创建。随后运行 `environment-plan`：仓库、容器或设备任务继承项目环境，纯分析任务使用无项目环境，浏览器任务留在当前宿主。状态告警通过 `notify` 指纹去重，状态或证据变化时才再次显示。

```bash
python <plugin-root>/scripts/governance_state.py --root . control --task-id KG-001 --action insert --new-task-id KG-002 --branch feature/KG-002-audit --instruction "插入审计日志需求"
```
