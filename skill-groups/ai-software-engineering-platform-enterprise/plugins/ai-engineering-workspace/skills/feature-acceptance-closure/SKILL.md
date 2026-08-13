---
name: feature-acceptance-closure
description: 将需求、实现、独立审核、自动与回归测试、截图或日志证据、文档和项目状态串成Feature Closed Loop。用于合并及发布前验收，禁止把代码生成成功或单次构建成功当作完成功能。
---

# 功能验收闭环

合并门禁要求：任务处于 Testing、至少一个实现 Commit、Review Agent 为 PASS、Test Agent 有 PASS 记录、存在可验证截图或日志、`CHANGELOG.md` 已更新、`ARCHITECTURE.md` 已更新或带理由标记不适用、当前分支与任务一致、工作区干净、文件锁已释放。

```bash
python <plugin-root>/scripts/closure_gate.py --root . --task-id KG-001 --phase merge
```

发布门禁要求任务为 Merged、存在 merge commit、发布证据为 PASS，并有回滚/迁移说明。失败项必须回到相应角色修复；禁止 Master 或 Merge Agent手工把 FAIL 改成 PASS。

若任务已启用「长链路变更收敛」，合并门禁还必须确认：每个稳定验收 ID 已达到声明的证据层级；没有证据矛盾、被推翻策略或未结真实实验；同一职责不存在多个活动实现路径；迁移路径已经退役且带删除或不可达证据。发布门禁还必须确认源码 HEAD、远程主线和部署版本一致，并有当前部署版本的上线后证据。静态测试、合同测试、运行时测试、用户可见效果和生产证据不得互相冒充。
