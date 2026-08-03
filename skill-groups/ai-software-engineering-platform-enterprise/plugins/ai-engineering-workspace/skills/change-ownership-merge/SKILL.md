---
name: change-ownership-merge
description: 检查代码所有权、跨模块修改、分支冲突和合并前质量证据，生成安全合并计划。不得自动覆盖冲突或未经明确要求直接合并main。
---

# 代码所有权与合并治理

## 所有权

读取 `.ai/governance/ownership.json`。规则使用 glob、owner 和 allowed_roles。未映射文件不自动判定安全，而是标记 `UNOWNED`。

## 合并预检

```bash
python3 <plugin-root>/scripts/merge_guard.py --root . \
  --source feature/web-resource --target main
```

检查：

- 变更文件和所有权；
- source/target 是否存在；
- Merge base；
- 潜在文本冲突；
- 数据库、接口、共享契约和锁定文件；
- 风险/测试报告是否存在。

发现冲突时生成双方修改目的和候选解决方案，禁止直接选择一方覆盖。
