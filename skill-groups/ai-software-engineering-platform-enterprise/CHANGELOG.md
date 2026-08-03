# CHANGELOG

## 4.0.0

- 将历史零散模块收敛为 5 个插件。
- 新增统一 `.ai` 状态协议和原子写入。
- 新增 SessionStart、PreCompact、Stop、SessionEnd、UserPromptSubmit Hook。
- 新增真实多语言/多框架/Monorepo 检测。
- 新增安全 Git Worktree 和分支租约。
- 修复风险分析遗漏 staged changes 的致命问题。
- 新增 SQLite 增量图谱，避免全量 JSON 图谱内存膨胀。
- 新增安装器、结构验证、单元和端到端测试。
