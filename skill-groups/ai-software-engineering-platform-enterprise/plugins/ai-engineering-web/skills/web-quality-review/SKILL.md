---
name: web-quality-review
description: 只读审核现有Web实现的组件复用、依赖边界、TypeScript、样式Token、响应式和视觉状态。不得自行修改代码后宣布通过。
---

# B/S质量审核

先运行：

```bash
python3 <plugin-root>/scripts/web_audit.py --root . --output .ai/quality/web-audit.json
```

审核维度：

- 技术栈和现有架构符合度；
- 组件重复、职责和依赖方向；
- 页面直接请求、`any`、超大文件和硬编码样式；
- 加载、空、错误、权限和边界状态；
- 1366×768、1440×900、1920×1080、2560×1440；
- 实现截图、参考图和 Diff；
- 实际构建与测试证据。

结果只有：`PASS`、`PASS_WITH_WARNINGS`、`FAIL`、`BLOCKED`。未运行的测试不能算通过。
