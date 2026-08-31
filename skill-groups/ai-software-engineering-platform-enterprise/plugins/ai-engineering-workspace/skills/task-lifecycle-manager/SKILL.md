---
name: task-lifecycle-manager
description: 创建和推进带Task ID的工程状态，记录目标、适用Gate、影响范围、Commit和证据；状态顺序只提供单调恢复坐标，实际工作由结构化Gate Applicability决定。
---

# 任务生命周期

状态词汇按 `Created → Planning → Development → Review → Testing → MergedPendingCleanup → Merged → Released` 单调排序，但不要求每个 Task 依次执行全部阶段。ChatGPT 先提交结构化 Gate Applicability，Runtime 只验证 `REQUIRED / NOT_APPLICABLE`、工作事实和证据；未解析的 `CONDITIONAL` 不能执行。风险只提高已存在工作的保证深度，不能凭空创建 architecture、merge 或 release 工作。

```bash
python <plugin-root>/scripts/governance_state.py --root . task-create --task-id KG-001 --goal "统一账户登录" --owner-agent "CONTROL" --branch feature/KG-001-login --affected-files src/auth.ts tests/auth.test.ts --gate-plan-file .ai/runtime/current-gate-plan.json
python <core>/scripts/hikerctl.py transition --task-id KG-001 --to Planning --agent-role "CONTROL" --operation-id KG1-T1
python <plugin-root>/scripts/governance_state.py --root . contract-set --task-id KG-001 --agent-role "CONTROL" --allowed-files src/auth.ts tests/auth.test.ts --behavior-invariants "现有登录方式继续可用" --required-tests "认证单测" "登录回归"
```

`task-create` 可直接消费模型生成的Gate计划；若尚未提供，只能进入Planning，并在`contract-set`时依据CONTROL提交的结构化范围生成最小计划，绝不退化为“新任务全部Gate必选”。`contract-set`记录允许范围、不变量与最低回归；merge仅来自结构化计划或真实source/target集成事实，不能由`repository_change`自动推出。使用`record`和`checkpoint`只保存适用Gate的证据。

生命周期状态之外单独维护会话绑定子状态：`SETUP_PENDING → BOUND → RUNNING → IDLE_REUSABLE / RELEASE_PENDING → RELEASED`。writer 槽按项目、仓库和稳定所有权通道区分，默认最多两个；同一通道仍只有一个活动writer。`clientThreadId` 不能当作真实 `threadId`，pending不能通过换Task ID制造替代会话。

当Review/Testing/Merge适用时，WRITE在交付保证前生成与当前Git HEAD、工作区指纹一致的架构守卫证据，并运行`governance_state.py candidate-freeze --task-id <TASK-ID> --agent-role "WRITE" --candidate-id <CANDIDATE-ID>`冻结候选。后续ASSURE/CONTROL只消费该`candidate_id`；候选指纹变化才使受影响证据`STALE`。Gate不适用时不创建对应证据或会话。

跨模块、跨仓库、真实外部执行、部署回滚、同一目标反复修复或用户推翻既有结论时，必须同时启用「长链路变更收敛」。用户纠正、验收范围变化或策略失效会使旧证据失效；不得保留原 PASS 继续推进。合并与发布前必须确认同一职责只有一个活动实现路径，迁移兼容代码已经收敛，未结实验为零。

同一 Task 只有一个当前候选、一个 writer 会话槽和一个权威实现方向。修复不得不断追加新入口、新服务或版本后缀；若必须并行迁移，应登记目标、兼容边界、唯一写入者、退出条件与最迟删除 Gate。达到退出条件后先删除或隔离旧实现，再推进合并。

每个阶段状态必须区分 `governance_progress` 与 `business_progress`。校验器、控制账本或测试工具修复不等于业务 Development 已开始；验证工具失败标为 `INVALID`，只有真实产品断言失败才标记业务测试 `FAIL`。相同 Gate、源码/合同指纹和范围已有 PASS 时复用证据，禁止为了“更保险”无条件从头重跑全部矩阵。

进入 Development 前还必须服从项目并行预算和目标契约指纹。连续两个治理周期后，若范围、不变量和最低测试已满足，应直接进入首个安全业务切片；治理周期上限不得反向阻止 Development。日常状态和quick对账只读取活动Task索引，只有显式deep/full审计才扫描全部历史Task。

桌面任务或 Subagent 调度前先运行 `dispatch_guard.py observe`。查询异常和超时分别记录为 `API_ERROR`、`QUERY_TIMEOUT`，都必须失败关闭；只有 `EMPTY_CONFIRMED` 才允许创建。复用已有桌面任务时还必须运行 `turn-guard`，同时提交宿主外层状态和最新 Turn 状态：只有两者均证明可复用且 Turn 已终态才预留一次分派；发送成功后立即 `turn-ack --accepted`。活动、未知或状态不一致时禁止发送和重发，只允许一次有界复查，仍不一致就 Checkpoint 并暂停。随后运行 `environment-plan`：仓库、容器或设备任务继承项目环境，纯分析任务使用无项目环境，浏览器任务留在当前宿主。状态告警通过 `notify` 指纹去重，状态或证据变化时才再次显示。

```bash
python <core>/scripts/hikerctl.py transition --task-id KG-001 --control-action insert --new-task-id KG-002 --branch feature/KG-002-audit --instruction "插入审计日志需求" --operation-id KG1-I1
```
