# `.ai` 统一状态协议 1.0

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
│   ├── locked-decisions.json
│   └── ownership.json
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

## 事实优先级

锁定决策 > ADR/正式架构文档 > 测试证据 > 当前任务状态 > 历史经验 > 聊天摘要。

## 原子写入

所有脚本先写临时文件、`fsync` 后原子替换，避免中断造成半写状态。

## 压缩恢复

- `PreCompact`：复制关键状态、记录 Git HEAD/状态和校验和。
- 压缩后的 `SessionStart(source=compact)`：注入精简活动上下文和锁定决策。
- `context-validator`：状态无效或协议不兼容时阻止自动继续。
