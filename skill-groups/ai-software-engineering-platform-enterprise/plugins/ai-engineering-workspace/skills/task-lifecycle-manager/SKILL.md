---
name: task-lifecycle-manager
description: 创建和推进带Task ID的工程任务状态机，记录目标、影响文件、负责人、分支、Commit、审核、测试、证据和发布结果；用于Created到Released的全过程及暂停、调整、恢复。
---

# 任务生命周期

状态只能按 `Created → Planning → Development → Review → Testing → Merged → Released` 推进。角色负责状态：Planning、Developer、Review、Test、Merge、Master；禁止 Developer 自审、自测后直接合并。

```bash
python <plugin-root>/scripts/governance_state.py --root . task-create --task-id KG-001 --goal "学生登录" --owner-agent "Planning Agent" --branch feature/KG-001-login --affected-files src/auth.ts tests/auth.test.ts
python <plugin-root>/scripts/governance_state.py --root . transition --task-id KG-001 --to Planning --agent-role "Planning Agent"
```

使用 `record` 写入 commit/review/test/artifact/document/decision/risk；使用 `checkpoint` 保存阶段快照。`pause` 不改变生命周期状态，只把 `control_status` 设为 PAUSED；`adjust` 记录新方向；`insert` 必须创建新的Task ID并关联原任务；`resume` 从原状态继续。未满足阶段证据门禁时不得推进。

```bash
python <plugin-root>/scripts/governance_state.py --root . control --task-id KG-001 --action insert --new-task-id KG-002 --branch feature/KG-002-audit --instruction "插入审计日志需求"
```
