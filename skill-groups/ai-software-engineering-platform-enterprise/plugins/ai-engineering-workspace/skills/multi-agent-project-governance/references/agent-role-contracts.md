# 执行职责契约

| 权威职责 | 输入 | 输出 | 权限 | 禁止操作 |
|---|---|---|---|---|
| CONTROL | 用户目标、项目事实、适用Gate及风险 | 范围、调度/串并行决定、Checkpoint、集成或发布决定 | 管理Task与控制状态；仅在真实需要时创建/复用桌面任务和Worktree | 绕过适用Gate；直接修改受保护分支；为不存在的工作创建流程 |
| WRITE | 已确认范围、接口契约、所有权和锁 | 实现、范围内测试、Commit和交接证据 | 只写分配范围；申请必要资源 | 自批通过；扩大范围；覆盖其他writer；修改受保护分支 |
| ASSURE | 冻结候选、验收与风险事实 | Review/Test/Reverify证据和PASS/BLOCKED | 只读候选；写范围化保证证据 | 在要求独立时审核自己的实现；合并；伪造证据 |

旧标签仅作兼容映射：Master/Planning/Merge/Document → CONTROL，Developer → WRITE，Review/Test/Browser → ASSURE。它们不得成为新 Agent、新会话或新 Worktree 的创建理由。默认由当前 Agent 承担全部适用职责；只有写冲突或独立保证要求才分离运行时。
