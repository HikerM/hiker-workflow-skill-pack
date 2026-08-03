---
name: regression-test-planner
description: 依据变更风险和真实项目脚本生成最低必要回归范围。
---


# 回归测试范围规划

## 职责

读取最新风险报告和当前项目配置，生成：

- 必须执行；
- 建议执行；
- 人工验证；
- 未映射缺口；
- 所需证据。

命令只能来自项目真实 `package.json`、测试配置、解决方案文件或项目策略。若无法发现可执行命令，应明确标记“待配置”，不得虚构命令。

## 输出

- `.ai/evidence/test-plan/latest.json`
- `.ai/evidence/test-plan/latest.md`
