# Enterprise 4.0 本地验证报告

生成版本：4.0.0

## 确定性验证

- 插件清单：5 个
- Skill 数量：由验证器自动统计
- 插件结构与图标：通过
- Hook JSON：通过
- Python 编译：通过
- Eval 基础样例：每个插件至少 10 条并包含负向样例
- 单元测试：通过
- 集成 Smoke：通过
- 完整本地变更集：已验证暂存、未暂存、未跟踪同时存在
- Git Worktree：已验证创建、状态和安全移除
- 上下文保护：已验证任务初始化、PreCompact 检查点和恢复注入
- 图谱限流：已验证节点上限
- 测试命令发现：已验证读取项目真实 package scripts

## 验证器输出

```json
{
  "ok": true,
  "plugin_count": 5,
  "skill_count": 17,
  "errors": [],
  "warnings": []
}
```

## 集成测试输出

```json
{
  "ok": true,
  "checks": [
    {
      "name": "bootstrap",
      "ok": true
    },
    {
      "name": "precompact",
      "ok": true
    },
    {
      "name": "recovery",
      "ok": true
    },
    {
      "name": "worktree",
      "ok": true
    },
    {
      "name": "complete-change-set",
      "ok": true
    },
    {
      "name": "risk-tags",
      "ok": true
    },
    {
      "name": "graph-limit",
      "ok": true
    },
    {
      "name": "real-commands",
      "ok": true
    },
    {
      "name": "personal-install",
      "ok": true
    },
    {
      "name": "repo-install",
      "ok": true
    }
  ],
  "failed": []
}
```

## 未替代的真实环境验证

本地测试不能替代：ChatGPT/Codex 客户端中的实际安装、Hook 信任界面、账号可用性、真实 Unity Editor 构建和具体项目 CI。详见 `LIMITATIONS_CN.md`。
