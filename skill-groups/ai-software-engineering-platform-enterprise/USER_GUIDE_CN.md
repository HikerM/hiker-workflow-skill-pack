# 中文使用手册

## 一、初始化

```text
@项目智能初始化
```

生成：

```text
.ai/context/project.json
.ai/context/tech-stack.json
.ai/context/standards.json
.ai/runtime/task.json
.ai/runtime/active-context.md
.ai/governance/locked-decisions.json
.ai/governance/ownership.json
.ai/quality/policy.json
```

## 二、开始一个长期任务

```text
@可中断任务控制
开始任务 REQ-RESOURCE-001：实现教材资源管理。连续执行；用户中途插入调整时保留已完成工作并修订计划。
```

自然语言控制：

- `暂停当前任务`
- `查看当前状态`
- `调整方向：Viewer 改为统一 Renderer 模式`
- `继续执行`
- `创建检查点：组件完成`
- `请求回滚到 checkpoint-003`（默认只生成回滚计划，不自动破坏代码）

## 三、任务分流

```text
@任务分流与会话规划
把需求拆为架构、Web、Unity、测试和审核通道。只读探索用 Subagent；并行写入用独立 Worktree。
```

插件不能在普通 Chat 中凭空创建持久会话；在 Codex 中可使用 Subagent 线程和桌面端 Worktree 会话。主线程只保留需求、决策和汇总，原始日志留在子线程或 `.ai/logs/`。

## 四、并行开发

```text
@Worktree任务管理
为 web-resource 和 unity-viewer 创建独立 Worktree，基于 main，分配所有权并输出路径。
```

不要让两个写入 Agent 在同一个物理工作树同时编辑。

## 五、质量审核

```text
@完整变更风险评估
评估暂存、未暂存和未跟踪文件，结合工程图谱生成风险报告。
```

随后：

```text
@回归测试范围规划
根据风险报告和真实 package scripts / Unity 配置生成测试计划，不要把未执行测试写成已通过。
```

## 六、发布

```text
@发布就绪审核
检查构建、测试、迁移、回滚、版本和已知风险证据，输出 PASS / WARNING / FAIL。
```
