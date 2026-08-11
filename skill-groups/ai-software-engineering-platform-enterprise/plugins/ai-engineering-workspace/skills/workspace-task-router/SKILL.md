---
name: workspace-task-router
description: 将大型需求按B/S浏览器前端与服务端、C/S客户端与服务端、契约数据、审核、测试、文档、合并和发布控制拆成可追踪通道，并选择主任务、Subagent或Git Worktree。用于大型需求分流和多Agent执行规划。
---

# 工作区任务路由

先读取 `PROJECT_STATE.md`、`CURRENT_CONTEXT.md`、`CHANGELOG.md`、`ARCHITECTURE.md` 和 Git 状态，再运行：

```bash
python <plugin-root>/scripts/task_router.py --root . --request "需求文本"
```

## 路由规则

- B/S 必须同时存在 `bs-frontend`、`bs-backend` 与 `contract-data`，不能把后台页面误当成完整系统。
- C/S 必须同时存在 `cs-client`、`cs-backend` 与 `contract-data`，Unity/桌面客户端不能吞掉服务端工作。
- 混合项目同时保留两类前端/客户端，共享契约必须串行定版。
- 写入通道一任务一分支；修改同一文件或高风险资产时串行并获取文件锁。
- `review`、`testing` 必须由独立角色执行；`merge` 必须等待验收闭环通过。

输出 `.ai/workspace/task-map.json`。只有用户明确要求多 Agent 并行时才实际调度；否则生成可执行路由，由当前任务按依赖顺序推进。
