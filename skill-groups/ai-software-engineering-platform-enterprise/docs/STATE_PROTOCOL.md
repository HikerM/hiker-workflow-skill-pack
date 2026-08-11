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
│   └── checkpoints/
├── governance/
│   ├── project-state.json
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

- 状态脚本以 `PreCompact` 事件调用时：复制关键状态、记录 Git HEAD/状态和校验和。
- 恢复脚本以 `SessionStart(source=compact)` 调用时：输出精简活动上下文和锁定决策。

当前插件 manifest 不自动注册这些事件；上述名称是脚本输入/输出协议，需由 Skill 或外部编排显式调用。
- `context-validator`：状态无效或协议不兼容时阻止自动继续。

新版项目使用 `Created → Planning → Development → Review → Testing → Merged → Released`。暂停、调整和恢复属于控制状态，不得跳过生命周期门禁；插入需求必须创建新的Task ID并记录依赖。
