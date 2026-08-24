# `.ai` 统一状态协议 2.0

```text
.ai/
├── schema.json
├── context/
│   ├── project.json
│   ├── tech-stack.json
│   ├── architecture.json
│   └── standards.json
├── runtime/
│   ├── task.json
│   ├── control.json
│   ├── active-context.md
│   ├── checkpoint-ledger.json
│   └── checkpoints/
├── governance/
│   ├── project-state.json
│   ├── context-retention.json
│   ├── task-index.json
│   ├── locked-decisions.json
│   └── ownership.json
├── tasks/
│   └── KG-001.json
├── workspace/
│   └── task-map.json
├── quality/
│   ├── policy.json
│   └── evidence/index.json
├── knowledge/
│   ├── metadata.json
│   └── engineering.db
└── logs/
    └── execution.jsonl
```

仓库根同时维护 `PROJECT_STATE.md`、`CURRENT_CONTEXT.md`、`CHANGELOG.md` 和 `ARCHITECTURE.md`。Git common dir维护跨Worktree共享的 `ai-engineering/workspace.json` 与 `file-locks.json`。

## 事实优先级

项目ID/仓库根 > 锁定决策 > Git事实 > Task状态与checkpoint > ADR/正式架构文档 > 测试证据 > 历史经验 > 聊天摘要。

## 原子写入

所有脚本先写临时文件、`fsync` 后原子替换，避免中断造成半写状态。

## 压缩恢复

- 状态脚本以 `PreCompact` 事件调用时：先把关键需求、决定、任务、风险和证据写入事实源，再复制关键状态、记录 Git HEAD/状态和校验和。
- 恢复脚本以 `SessionStart(source=compact)` 调用时：只输出固定大小的活动工作集、最近决定和恢复回执。
- `context-retention.json` 默认限制活动上下文8000字符、会话注入4000字符、每节8项、近期checkpoint 8个、里程碑checkpoint 6个、已关闭任务摘要索引120项。
- 超过上限的冗余checkpoint写入 `checkpoint-ledger.json` 的有界索引和连续哈希链后移除；源码、Git提交、Task、正式决定和验收证据不属于清理对象。
- `task-index.json` 只服务日常状态渲染；旧已关闭任务摘要收敛为计数和哈希链，完整任务仍在 `.ai/tasks/*.json`，显式审计时再按需读取。
- 新会话按“项目身份 → Task/决定 → Git → 正式文档 → 最新checkpoint → 聊天摘要”恢复。聊天摘要永远不是唯一事实源。

当前插件 manifest 不自动注册这些事件；上述名称是脚本输入/输出协议，需由 Skill 或外部编排显式调用。
- `context-validator`：状态无效或协议不兼容时阻止自动继续。

新版项目使用 `Created → Planning → Development → Review → Testing → Merged → Released`。暂停、调整和恢复属于控制状态，不得跳过生命周期门禁；插入需求必须创建新的Task ID并记录依赖。
