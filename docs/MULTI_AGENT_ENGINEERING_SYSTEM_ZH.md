# Hiker 工程能力系统：大型软件工程多角色协作

<!-- engineering-current-facts: version=5.18.0; plugins=5; skills=42; tests=309 -->

## 1. 系统定位

Hiker Engineering Capability System（Hiker 工程能力系统）不是“让多个 Agent 一起写代码”的提示词集合，也不是独立 Agent Runtime。ChatGPT Desktop / Codex 提供 Agent Runtime、桌面任务和工具调用；本能力系统提供可安装的 Plugin、Skill 与本地确定性脚本，把项目事实、任务生命周期、角色权限、Git分支、Worktree、共享文件锁、审核测试证据和发布门禁连成一套可恢复、可审计的工程约束。

适用架构：

- B/S：Browser Frontend + Server Backend + API/Data Contract；
- C/S：Desktop/Unity Client + Server Backend + Protocol/Data Contract；
- Hybrid：Web、桌面/Unity客户端共享或连接多个后端；
- NodeTS、Unity、大型Monorepo、多Git仓库和多Codex任务。

## 2. 目录结构

```text
ai-engineering-workspace/
├─ .codex-plugin/plugin.json
├─ skills/
│  ├─ multi-agent-project-governance/
│  │  ├─ SKILL.md
│  │  ├─ agents/openai.yaml
│  │  └─ references/
│  │     ├─ agent-role-contracts.md
│  │     ├─ system-lane-model.md
│  │     ├─ git-governance.md
│  │     ├─ state-and-task-model.md
│  │     └─ closed-loop-example.md
│  ├─ project-state-manager/
│  ├─ task-lifecycle-manager/
│  ├─ workspace-task-router/
│  ├─ worktree-task-manager/
│  ├─ worktree-safe-convergence/
│  ├─ file-lock-manager/
│  ├─ feature-acceptance-closure/
│  ├─ long-chain-change-convergence/
│  ├─ change-ownership-merge/
│  ├─ multi-project-portfolio-manager/
│  └─ plugin-application-receipt/
├─ scripts/
│  ├─ governance_state.py
│  ├─ task_router.py
│  ├─ git_workspace.py
│  ├─ file_lock.py
│  ├─ closure_gate.py
│  ├─ merge_guard.py
│  └─ portfolio_manager.py
└─ tests/test_workspace.py
```

项目启用治理后生成：

```text
<repo>/
├─ PROJECT_STATE.md
├─ CURRENT_CONTEXT.md
├─ CHANGELOG.md
├─ ARCHITECTURE.md
└─ .ai/
   ├─ governance/project-state.json
   ├─ tasks/KG-001.json
   ├─ workspace/task-map.json
   ├─ evidence/
   └─ runtime/checkpoints/

<git-common-dir>/ai-engineering/
├─ workspace.json
└─ file-locks.json
```

文件锁与Worktree租约放在Git common dir，因此同一仓库的所有Worktree看到同一份冲突状态。

## 3. Agent 角色体系

### Master Agent

- 输入：用户目标、PROJECT_STATE、CURRENT_CONTEXT、任务状态、风险、门禁结果、Git事实。
- 输出：任务拆解、角色分配、优先级、依赖、checkpoint、合并与发布决策。
- 权限：维护项目/任务控制状态，调度角色，批准恢复和发布。
- 禁止：直接承担普通功能实现；绕过Review/Test；直接修改main；因“自动治理”擅自push或发布。

### Planning Agent

- 输入：需求、架构、历史决定、技术栈、限制和风险。
- 输出：可验收需求、技术方案、工作量、任务边界、影响文件和依赖。
- 权限：写计划、任务范围、验收条件和ADR草案。
- 禁止：写生产实现、合并或发布。

### Developer Agent

- 输入：已批准计划、Task ID、分支、文件范围、接口契约和文件锁。
- 输出：单功能实现、单元测试、Commit ID、变更说明。
- 权限：只修改任务授权范围；申请和释放锁；提交功能分支。
- 禁止：直接写main/develop/release；修改他人锁定文件；自审通过；无Task ID扩大范围。

### Review Agent

- 输入：Diff、架构、代码所有权、风险、测试设计。
- 输出：P0/P1/P2、PASS/BLOCKED、修复建议与审核证据。
- 权限：只读审查并写审核报告。
- 禁止：一边修复一边批准自己的实现；合并；隐瞒未验证项。

### Test Agent

- 输入：验收条件、构建、Review结果、测试环境。
- 输出：自动测试、回归、功能验证、日志、截图和PASS/BLOCKED。
- 权限：运行测试、在授权范围补测试、写证据。
- 禁止：改写验收条件；把“计划运行”写成“已通过”；合并。

### Merge Agent

- 输入：Review PASS、Test PASS、闭环PASS、分支Diff、锁状态、冲突预检。
- 输出：合并决定、冲突解决记录、merge commit、CHANGELOG和任务状态。
- 权限：只按允许分支流向执行非强制合并。
- 禁止：强推main；跳过门禁；无分析采用ours/theirs；替Developer补大段功能再直接合并。

### Document Agent

- 输入：批准的需求、架构、实现、测试和发布结果。
- 输出：CHANGELOG、ARCHITECTURE、架构图、迁移/运维文档和知识库。
- 权限：更新文档与可追踪图表。
- 禁止：无任务改变运行行为；复制旧状态冒充当前状态；虚构证据。

## 4. Git Governance Layer

### 分支规则

| 分支 | 用途 | 创建/写入权限 | 合并目标 |
|---|---|---|---|
| `main` | 已发布基线 | 禁止Agent直接写 | 无 |
| `release` | 发布候选集成 | Merge Agent | `main`或发布流程 |
| `develop` | 日常集成 | Merge Agent合并 | `release` |
| `feature/*` | 新功能 | Developer，基于develop | `develop` |
| `bugfix/*` | 普通缺陷 | Developer，基于develop | `develop` |
| `hotfix/*` | 生产紧急修复 | 授权Developer，基于main | `main`并回灌develop |
| `release/*` | 版本准备 | Merge Agent，基于develop | `main` |

提交使用 Conventional Commit：`feat:`、`fix:`、`refactor:`、`docs:`、`test:`，并允许 `chore/perf/build/ci` 和 scope。

### Worktree规则

允许：任务已建立并处于Planning/Development；需要并行写入不同模块；分支前缀和基线正确；锁检查通过。

禁止：受保护分支；同文件或强耦合模块并行；Unity Scene/Prefab/ProjectSettings/meta未锁；migration/API Contract并行；只读任务；任务已进入Review后才临时拆新写分支。

### 合并流程

```text
Developer完成 → Conventional Commit → Review PASS → Test PASS
→ 证据/文档/状态闭环 → Merge Guard → Merge Agent非强制合并
→ merge commit写回任务 → PROJECT_STATE更新
```

## 5. 项目状态与上下文保护

每个Agent开工顺序固定为：确认Git根和Project ID → 当前Task/锁定决定 → Git branch/status/diff → PROJECT_STATE/CURRENT_CONTEXT有界工作集 → 当前阶段所需CHANGELOG/ARCHITECTURE/证据 → 最新相关Checkpoint → Worktree/锁。

`PROJECT_STATE.md` 强制包含当前版本、分支、已完成、开发中、待处理、数据库版本、API版本和风险。`CURRENT_CONTEXT.md` 强制包含当前目标、已完成修改、未完成事项、关键决定和禁止事项。

会话压缩或Agent接管时，聊天摘要只能提供线索；仓库状态、checkpoint和Git事实优先。01号 `bounded-context-memory` 默认限制活动上下文8000字符、会话注入4000字符、每节8项，并分开保留近期8个和里程碑6个checkpoint；旧冗余快照进入有界索引和连续哈希链。04号继续保存Task ID、Agent、Worktree、锁、合并和发布状态。冲突时进入 `BLOCKED_CONTEXT_CONFLICT`，不得自行采用旧聊天结论。

“不丢失”指关键需求、决定、任务状态、风险、证据和Git事实在压缩前进入正式事实源，不代表逐字永久保存所有聊天。新会话只加载当前任务的固定大小工作集，完整事实按指针按需读取，因此不会因轮次增加而线性变重。

## 6. 任务状态模型

<!-- task-lifecycle: Created → Planning → Development → Review → Testing → MergedPendingCleanup → Merged → Released -->

合法主路径：`Created → Planning → Development → Review → Testing → MergedPendingCleanup → Merged → Released`。

```text
Created → Planning → Development → Review → Testing
                         ↑          │          │
                         └──────────┘          ↓
                 MergedPendingCleanup → Merged → Released
```

任务记录：Task ID、目标、状态、控制状态、负责人角色、Git branch/base、影响文件、Commit ID、审核、测试、截图/日志、文档、决定、禁止事项、风险、闭环和发布结果。

暂停、调整、插入和恢复是控制动作：暂停保留Worktree与修改；调整建立checkpoint并只废弃受影响计划；插入需求新建Task ID和依赖；恢复重新验证项目、Git和锁后继续。

## 7. 冲突防护

- Unity：Scene、Prefab、ProjectSettings、`.meta` 必须加锁；资产与对应meta视为同一资源；ProjectSettings全局互斥。
- NodeTS：核心 `*Service.ts` 文件互斥；数据库migration和API Contract分类全局互斥。
- 锁只允许Development/Review/Testing的ACTIVE任务持有；任务交接更新心跳；合并前必须释放。
- 冲突不使用强制覆盖。Merge Agent记录双方修改目的、影响和可验证的解决方案，解决后重新测试。

## 8. 自动验收闭环

“代码已生成”不是完成。合并门禁同时要求：实现Commit、独立Review PASS、Test PASS及命令记录、可打开的截图或日志、CHANGELOG已更新、ARCHITECTURE已更新或给出不适用理由、分支正确、工作区干净、锁已释放、状态一致。合并提交已经产生但任务 Worktree 尚未安全关闭时，任务必须停留在 `MergedPendingCleanup`，不能提前写成 `Merged`。

发布再增加：Merged状态、merge commit、构建/部署/迁移/回滚证据、数据库/API兼容检查和发布验证PASS。

## 9. 多项目管理

每个仓库独立保存四个根文档、Project ID、任务、证据、分支和Git common-dir锁。全局组合注册表只保存项目ID与根路径映射，不复制项目内容。切换项目时三重校验：活动项目ID、登记根路径、仓库project-state一致；任何一项不一致就阻断写入。

## 10. 从需求到发布示例

需求：“浏览器管理端和游戏引擎客户端增加统一登录，TypeScript后端提供接口。”

1. Master读取状态，创建KG-001。
2. Planning定义登录、401、锁定、刷新令牌、离线、权限和验收条件；估算前端、客户端、后端、契约、测试工作。
3. Router生成浏览器前端、客户端、共享后端服务、契约/数据、审核、测试、文档、合并和发布控制通道；浏览器端与客户端共享同一后端时不创建重复服务通道。
4. Developer分别在feature分支/Worktree开发；契约先定版；Unity和NodeTS共享文件加锁。
5. 每个实现提交 `feat(auth): implement KG-001 ...` 并记录Commit ID。
6. Review独立审核安全、架构、兼容和Unity生命周期；问题返回Development。
7. Test运行API、Web E2E、Unity PlayMode/设备回归，保存截图和日志。
8. Document更新CHANGELOG和ARCHITECTURE或不适用理由。
9. Closure Gate通过；Merge Agent预检并合并到develop，写回merge commit和PROJECT_STATE。
10. 发布候选完成迁移、回滚、冒烟和风险审核后，Master推进Released。

## 11. 为什么适合这些场景

- Unity大型项目：文件锁理解Scene/Prefab/meta耦合，避免YAML/GUID并发损坏；独立客户端通道保留生命周期、分辨率和平台测试。
- NodeTS后端：Service、migration和API Contract有独立锁与版本证据，避免多个Agent同时破坏核心链路。
- 多Agent协作：角色权限、状态机和门禁是机器可检查的，不依赖Agent“记得配合”。
- ChatGPT Desktop/Codex：符合插件manifest、SKILL.md、agents/openai.yaml和个人Marketplace结构；Skill可隐式触发，AGENTS全局规则负责自动选择和可见回执，新任务可加载更新后的插件能力。

### 大型工程结构保护

- Planning为每个任务写最小变更契约：允许文件/模块、原有行为不变量、最低回归、公共契约变化和消费者。
- 架构守卫自动核对范围漂移、受保护模块、依赖方向、公共表面指纹、消费者回归、图谱影响半径和文件增长；证据绑定当前提交与工作区指纹。
- 超过400行或单次增长80行默认警告，超过700行或单次增长200行默认阻断；项目可按技术栈调整，但不能用调大阈值代替职责拆分。
- 文件拆分以职责、依赖方向和公共表面为依据，不按行数机械切片；公共服务变化必须先补特征测试，再验证反向消费者。
- 模块表、依赖规则、公共表面和运行拓扑均允许为空。普通局部改动依赖自动发现；只有高复用、跨模块、受保护或无法静态推断的边界才显式登记，避免治理配置与源码形成双向耦合。

## 12. 全局自动应用与可见回执

运行个人安装器后，它会默认安装启用五个插件，并把 `templates/GLOBAL_AGENTS_AI_ENGINEERING.md` 的标记区块安全合并到 `~/.codex/AGENTS.md`。它只允许“智能工程轻量路由”自动触发，其他入口保持手动；首次实质动作前只用一行中文显示实际使用的插件和 Skill，结束时不重复显示未变化的回执。重复安装不会重复追加，原文件会备份，可用 `--no-merge-global-agents` 退出。

这只影响选择与透明度，不赋予额外外部写权限。push、merge、部署、生产数据写入仍需用户请求或既有明确授权。

桌面任务归档与本地工具运行时释放由 ChatGPT Desktop / Codex 宿主显式执行；本地脚本只验证并记录结果。脚本不得伪造“已归档”或“已释放”，宿主动作未完成或证据不足时保留未验证状态并阻止创建替代任务，但不应让无须新隔离运行时的已有工作退回治理空转。
