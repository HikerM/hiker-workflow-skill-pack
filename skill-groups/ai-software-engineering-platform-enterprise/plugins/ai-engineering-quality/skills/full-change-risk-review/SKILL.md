---
name: full-change-risk-review
description: 评估暂存、未暂存、未跟踪和提交范围中的完整变更集。
---


# 完整变更风险评估

## 职责

1. 首选 `all-local` 收集当前全部本地变更；
2. 加载 `.ai/context/`、项目风险策略、代码所有权和可选图谱；
3. 输出事实、风险、置信度、未知项和控制建议；
4. 不修改源码，不自动合并，不宣称测试已执行。

## 输入

- 当前 Git 仓库，或明确的提交范围/文件清单；
- 可选 `.ai/quality/policy.json`；
- 可选 `.ai/governance/ownership.json`；
- 可选 `.ai/knowledge/engineering.db`。

## 输出

- `.ai/evidence/risk/latest.json`
- `.ai/evidence/risk/latest.md`

## 阻断事项

出现以下情况不得输出“低风险且可直接发布”：

- 变更集收集失败或不完整；
- 数据迁移、认证授权、密钥、发布配置等关键路径发生变化；
- 图谱过期但结论依赖图谱；
- 关键模块没有所有权或测试映射；
- 删除/重命名公共接口而没有兼容证据。
