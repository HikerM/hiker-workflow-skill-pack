---
name: release-readiness-review
description: 结合任务闭环、风险、构建、测试、截图或日志、文档、迁移和回滚证据独立审核发布状态；适用于大型B/S、C/S、Unity和NodeTS项目，缺少PROJECT_STATE或发布门禁时不得判定就绪。
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
- 对应 Task ID 已处于 `Merged`，存在 merge commit；
- Feature Closed Loop 合并门禁为 PASS；
- `PROJECT_STATE.md`、`CHANGELOG.md` 与 `ARCHITECTURE.md` 同步；
- 发布验证、数据库/API兼容与回滚证据为 PASS；
- 当前项目 ID 与所有证据一致，未混入其他仓库上下文。

缺少执行证据时只能写“未验证”，不能把计划状态当成通过状态。
