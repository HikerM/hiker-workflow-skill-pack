---
name: feature-acceptance-closure
description: 将需求、实现、独立审核、自动与回归测试、截图或日志证据、文档和项目状态串成Feature Closed Loop。用于合并及发布前验收，禁止把代码生成成功或单次构建成功当作完成功能。
---

# 功能验收闭环

只有 Gate Applicability 把 merge 判为 `REQUIRED` 时才执行合并门禁。门禁要求任务已完成所有适用工作、至少一个实现 Commit、所需 ASSURE 证据为 PASS、存在与变更范围匹配的测试及可验证证据、适用文档已更新或有不适用事实、当前分支与任务一致、工作区干净、文件锁已释放。`NOT_APPLICABLE` 的 Review、Testing、Documentation 或 Merge 不得被风险凭空创建。

```bash
python <plugin-root>/scripts/closure_gate.py --root . --task-id KG-001 --phase merge
```

只有 release 为 `REQUIRED` 时才执行发布门禁，并要求适用的集成事实、发布证据、回滚/迁移说明均通过。失败项必须回到对应责任范围修复；禁止 CONTROL 或 WRITE 手工把 FAIL 改成 PASS。旧版 Master/Review/Test/Merge 标签只作为兼容职责名，不代表必须创建独立 Agent。

若任务已启用「长链路变更收敛」，合并门禁还必须确认：每个稳定验收 ID 已达到声明的证据层级；没有证据矛盾、被推翻策略或未结真实实验；同一职责不存在多个活动实现路径；迁移路径已经退役且带删除或不可达证据。发布门禁还必须确认源码 HEAD、远程主线和部署版本一致，并有当前部署版本的上线后证据。静态测试、合同测试、运行时测试、用户可见效果和生产证据不得互相冒充。
