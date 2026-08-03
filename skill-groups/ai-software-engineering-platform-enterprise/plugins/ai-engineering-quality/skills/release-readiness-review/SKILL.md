---
name: release-readiness-review
description: 结合风险、构建、测试、迁移和回滚证据审核发布状态。
---


# 发布就绪审核

## 职责

只读取证据并给出：`PASS`、`PASS_WITH_WARNINGS`、`BLOCKED`。

## 必需证据

- 风险报告；
- 测试计划及执行结果；
- 构建结果；
- 关键变更的迁移与回滚说明；
- 未解决阻断问题。

缺少执行证据时只能写“未验证”，不能把计划状态当成通过状态。
