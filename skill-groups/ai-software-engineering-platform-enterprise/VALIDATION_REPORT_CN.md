# Enterprise 4.1 本地验证报告

生成版本：4.1.0

## 确定性验证

- 插件清单：5 个
- Skill 数量：由验证器从插件目录动态统计为 18 个
- `web-ui-design`、`design-readiness-review`、`full-change-risk-review`：`quick_validate.py` 全部通过
- 无 Hook 的 Web、Quality、Unity 插件：`validate_plugin.py` 全部通过
- 插件结构与图标：通过
- Hook JSON：通过
- Python 编译：通过
- Eval 基础样例：每个插件至少 10 条并包含负向样例
- 单元测试：通过
- 单元测试明细：Core 6、Quality 11、Unity 4、Web 4、Workspace 4，共 29/29 通过
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
  "skill_count": 18,
  "errors": [],
  "warnings": []
}
```

## 设计收敛前向验证

审查者只获得 Skill、模拟项目目录和只读审核任务，没有收到预期问题、预期等级或预期结论。

- 简单 CRUD 管理系统：首次独立复审发现 P1=5，增量整改后仍自行发现 P1=1，再次定向整改后达到 P0=0、P1=0 并 `PASS`；验证轮数由问题是否清零决定。
- 复杂编辑/画布/实时/发布系统：动态识别高复杂度表面，独立复审得到 P0=4、P1=7、P2=1 并 `BLOCKED`，主动发现数据丢失、服务端授权、内部标识泄露、发布/回滚边界和计数型自检盲区。
- 新增批量导入要求的增量风险场景：识别旧设计 `PASS` 已失效，只重开导入链及共享消费者，得到 P0=2、P1=6、P2=2，并发现只更新 UI、未同步数据/API/权限/测试的表面整改。

前向验证同时确认：简单项目可在一轮或少量定向整改后结束；复杂项目持续到 P0/P1 清零或明确阻塞；自检不能替代独立复审；新增要求不会默认使无关设计全量失效。

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
