# 中文使用手册

## 一、轻量路由与初始化

```text
@AI工程轻量路由
```

入口只识别项目模式、架构和当前阶段，然后加载最多两个原子Skill。无需把五个插件或全部原子Skill同时选中。

从空目录开始时先进入 `@0→1需求融合与选型`，生成：

```text
.ai/requirements/ledger.json
.ai/context/greenfield.json
REQUIREMENTS.md
```

新增需求按 `REQ-001` 等稳定ID增量合并；旧版本进入revision history，冲突和未知项必须显式保留。平台、架构、部署、数据、安全或核心技术栈在一个人工Checkpoint确认后再开始正式脚手架。

已有代码仓库才进入 `@项目智能初始化`，生成：

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

大型或多Agent项目由路由按需加载 `@项目状态与上下文管理`，生成 `PROJECT_STATE.md`、`CURRENT_CONTEXT.md`、`CHANGELOG.md`、`ARCHITECTURE.md` 和 `.ai/governance/project-state.json`。

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

长期、多会话或频繁压缩任务同时使用 `@有界上下文记忆`。01号把活动工作集限制在固定大小，04号把Task ID、Agent交接、Worktree和合并状态持久化。可随时检查：

```text
@有界上下文记忆
显示当前工作集字符数、保留/已收敛checkpoint数量、事实源和恢复下一步。
```

系统不承诺逐字永久保存完整聊天；它保证关键需求、决定、任务状态、风险、证据和Git事实在压缩前写入项目事实源。旧的冗余checkpoint只保留有界索引与哈希链，因此新会话无需重载全部历史。

## 三、建立Task ID与任务分流

```text
@工程任务生命周期
创建 KG-001，记录目标、影响文件、负责人、feature分支和验收条件。
```

```text
@任务分流与会话规划
把需求按B/S浏览器前端+服务端、C/S客户端+服务端、契约数据、审核、测试、文档、合并和发布控制拆分。只读探索用 Subagent；并行写入用独立 Worktree。
```

插件不能在普通 Chat 中凭空创建持久会话；在 Codex 中可使用 Subagent 线程和桌面端 Worktree 会话。主线程只保留需求、决策和汇总，原始日志留在子线程或 `.ai/logs/`。

## 四、并行开发

```text
@Worktree任务管理
为 KG-001 的不同写入任务创建独立 Worktree；feature/bugfix基于develop，hotfix基于main，分配所有权并输出路径。
```

不要让两个写入 Agent 在同一个物理工作树同时编辑。

修改Unity Scene/Prefab/ProjectSettings/meta、NodeTS核心Service、migration或API Contract前使用 `@多Agent文件锁`；合并前释放。

## 五、设计就绪与质量审核

编码前先执行独立复审：

```text
@设计就绪独立复审
从当前需求、工作流、路由、验收卡和测试映射动态构建追踪链，独立检查设计是否足以实现和验收。输出 P0/P1/P2、置信度、未知项和允许进入的下一阶段；存在 P0/P1 时不得进入编码。
```

设计自检不能替代这次独立复审。整改后只回归受影响链路，并再次独立复审，直到 P0/P1 清零或明确阻塞。

代码或设计发生变化后执行风险审核：

```text
@完整变更风险评估
评估暂存、未暂存和未跟踪文件，结合工程图谱生成风险报告；对需求或设计变化执行增量影响分析，并判断是否需要重新执行设计就绪独立复审。
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

发布前先用 `@功能验收闭环` 确认实现Commit、Review/Test PASS、截图或日志、CHANGELOG、ARCHITECTURE和项目状态均已闭合，再由Merge Agent执行合并预检。

## 七、全局自动应用与可见回执

个人安装器默认把 `templates/GLOBAL_AGENTS_AI_ENGINEERING.md` 安全合并到 `~/.codex/AGENTS.md`，软件工程任务会自动选择最小必要Skill。每次任务开头和结尾会显示实际使用的插件、Skill、触发原因、项目和执行模式；未使用的插件不会被冒充为“已应用”。安装完成后检查 `plugin_activation.status=activated`，再重启桌面端并新建任务。
