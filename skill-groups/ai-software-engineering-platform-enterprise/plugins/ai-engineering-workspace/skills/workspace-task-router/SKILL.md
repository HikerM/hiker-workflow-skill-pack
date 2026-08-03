---
name: workspace-task-router
description: 将大型需求拆成架构、Web、Unity、后端、测试、审核和发布通道，并选择主会话、Subagent或Git Worktree；用于防止所有问题堆在一个会话中。
---

# 任务分流与会话规划

## 原则

- 主线程只保留目标、约束、决策和最终汇总；
- 只读探索、测试、日志、资料分析优先交给 Subagent；
- 两个以上并行写任务必须使用不同 Git Worktree；
- 高耦合、同文件或同模块写任务保持串行；
- 子任务结果写入 `.ai/workspace/task-map.json` 和 Handoff，而不是把原始日志全部塞回主会话。

运行：

```bash
python3 <plugin-root>/scripts/task_router.py --root . --request "需求文本"
```

## 分流结果

每个 lane 包含：职责、输入、输出、读写范围、依赖、推荐执行方式和阻塞关系。

## 用户控制

用户可以暂停或调整某个 lane，不影响其他无依赖 lane。方向变化时重新计算受影响 lane，不重建全部任务。
