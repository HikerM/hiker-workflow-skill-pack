---
name: release-readiness-review
description: 结合任务闭环、风险、构建、测试、截图或日志、文档、迁移、部署版本和回滚证据独立审核多技术栈软件的发布状态；适用于B/S、通用C/S、Unity、共享服务端和混合工程，缺少PROJECT_STATE或当前版本发布门禁时不得判定就绪。
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
- `delivery_hygiene.py --mode release` 为 PASS：无默认启用的 Demo/Mock/Fixture，无用户可见占位数据、样例身份、本机路径、堆栈或数据库内部错误。
- 对存在新旧实现、迁移入口或多写入者的能力，`implementation_guard.py` 为 PASS，且只保留一个权威活动实现和一个权威状态写入者。
- 若存在 `.ai/ui/project-ui.json`，`product_release_gate.py` 必须 PASS：当前 Design/Registry 指纹、默认态 Runtime Evidence、Candidate/Goal binding、Architecture Profile、Presentation、Content 与 Error 证据必须齐全；无 UI IR 的旧项目为 `NOT_APPLICABLE`。

缺少执行证据时只能写“未验证”，不能把计划状态当成通过状态。
