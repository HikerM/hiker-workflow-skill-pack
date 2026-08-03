# Hiker Skill Collection

这是一个面向 ChatGPT/Codex 桌面应用的中文 Skill 集合仓库。仓库当前包含 **三组彼此独立的 Skill**，每组有不同的目标、安装方式和使用边界。

> 重要：这里的“三组”不是三个 Skill。第一组包含 9 个 Skill，第二组包含 5 个插件和 17 个 Skill，第三组包含 1 个大型 Skill，共计 27 个 Skill。

## 三组总览

| 组别 | 名称 | 版本 | 内容规模 | 主要用途 | 源码位置 |
|---|---|---:|---:|---|---|
| 第一组 | Hiker 工作流守护 Skill Pack | 0.3.0 | 9 个 Skill | 工程复核、阶段验收、证据测试、契约审计、NodeTs、Unity、设计交付和架构咨询 | [`.agents/skills`](.agents/skills) |
| 第二组 | AI Software Engineering Platform Enterprise | 4.0.0 | 5 个插件、17 个 Skill | 项目初始化、上下文恢复、Web/Unity 实现、质量门禁、Worktree 与多会话协作 | [`skill-groups/ai-software-engineering-platform-enterprise`](skill-groups/ai-software-engineering-platform-enterprise) |
| 第三组 | Desktop App Reconstruction ZH | 1.1.0 | 1 个大型 Skill | 已授权桌面软件的黑盒/灰盒/白盒等价重建、技术选型、实现、测试和交付 | [`skill-groups/desktop-app-reconstruction-zh`](skill-groups/desktop-app-reconstruction-zh) |

三组的详细说明和全部 Skill 清单见：[三组 Skill 中文详解](docs/THREE_SKILL_GROUPS_ZH.md)。

## 第一组：Hiker 工作流守护 Skill Pack

这一组解决“如何判断工程任务是否真的完成”的问题。它不替代具体框架开发，而是给 Codex 提供稳定的工程治理规则：先确认仓库、分支和范围，再检查真实证据，最后判断是否完成、能否进入下一阶段。

包含 9 个 Skill：

- `hiker-workflow-router`：根据任务选择最短、最匹配的工作流。
- `codex-thread-review`：复核 Codex 任务结果是否越界、缺证据或遗漏动作。
- `project-phase-review`：判断阶段门禁、里程碑和 P2.x 工作能否进入下一阶段。
- `evidence-first-testing`：设计 smoke、contract、异常输入、并发和性能等真证据测试。
- `contract-boundary-audit`：审计 OpenAPI、DTO、数据库、Provider 和前后端字段边界。
- `nodets-execution-pipeline-guardrails`：守护 NodeTs 的 quote → create → worker/provider → result → billing 统一链路。
- `unity-codex-guardrails`：保护 Unity Scene、Prefab、脚本、资源、`.meta` 和 GUID。
- `design-output-discipline`：约束 PPT、图片、SVG、PDF、Excel 等真实文件交付和视觉抽查。
- `agent-architecture-consultant`：输出架构路线、范围、风险、工期、报价和双方案建议。

适合：工程复核、阶段验收、复杂接口链路、Unity 修改、交付物 QA 和技术方案评估。

安装到具体项目：

```powershell
.\INSTALL.ps1 -TargetRoot C:\path\to\project -DryRun
.\INSTALL.ps1 -TargetRoot C:\path\to\project -Apply -Backup -Skills all -MergeAgents
```

## 第二组：AI Software Engineering Platform Enterprise 4.0

这一组是完整的软件工程插件平台，按职责拆成 5 个插件：

1. `ai-engineering-core`：识别真实技术栈，建立 `.ai/` 项目状态，生成版本对应规范，并支持长任务中断与上下文恢复。
2. `ai-engineering-web`：基于项目现有框架和组件库完成 Web UI 设计、组件实现和只读质量审核。
3. `ai-engineering-unity`：基于真实 Unity 版本和 UI 技术栈完成 UI 设计、组件实现和兼容性审核。
4. `ai-engineering-workspace`：负责大型任务路由、Subagent、Git Worktree、代码所有权和安全合并计划。
5. `ai-engineering-quality`：覆盖完整本地变更集、关系图谱、回归测试计划、风险审核和发布门禁。

它适合长期、跨模块或多人/多会话的软件工程项目。推荐先运行 `project-bootstrap`，让核心插件建立真实项目上下文，再由 Web、Unity、质量和工作区插件消费同一份 `.ai/` 状态。

该组使用“个人 Marketplace → 安装插件”的两阶段安装方式。仅复制目录并不会自动启用插件，必须再安装 5 个插件。完整命令见：[安装指南](docs/INSTALLATION.md#第二组ai-software-engineering-platform-enterprise-40)。

## 第三组：桌面软件等价重建 Skill

这一组只有一个大型 Skill：`desktop-app-reconstruction-zh`。它面向已经取得合法授权的 Windows、macOS 或 Linux 桌面软件重建项目，把可观察行为转化为可追踪的规格、实现、测试和交付物。

它覆盖：

- 授权和范围冻结；
- 截图、录屏、可执行程序、样例文件、接口和源码证据盘点；
- 原软件技术指纹与目标实现技术栈分离；
- 窗口、页面、控件、快捷键、功能、角色、异常、数据和性能库存；
- 精确版本锁定、代表性 POC 和官方文档核验；
- 代码实现、视觉差分、功能/数据回归、性能和稳定性测试；
- 安装、升级、卸载、迁移、回滚和最终交付门禁。

该 Skill 不用于破解许可证、绕过登录或 DRM、窃取源码/密钥/凭据，也不允许把未验证推断写成“完全一致”。

用户级安装：

```powershell
cd .\skill-groups\desktop-app-reconstruction-zh
py -3 -B .\scripts\install_skill.py --scope user
```

## 如何选择

| 你的任务 | 推荐组别 |
|---|---|
| 复核 Codex 是否真的做完、能否进入下一阶段 | 第一组 |
| 审计接口契约、NodeTs 链路、Unity 修改或设计交付物 | 第一组 |
| 初始化长期工程、维护 `.ai/` 状态、跨会话恢复 | 第二组 |
| 在真实 Web/Unity 技术栈中设计、实现并审核 | 第二组 |
| 多任务、Subagent、Worktree、风险和发布门禁 | 第二组 |
| 已授权桌面软件反推、迁移、国产化替代或等价重建 | 第三组 |

第一组和第二组可以同时使用：第一组负责“证据和验收判断”，第二组负责“工程执行和状态治理”。第三组本身已经定义完整的桌面重建阶段门禁，通常作为该类项目的主工作流。

## 仓库结构

```text
.
├─ .agents/skills/                              # 第一组：9 个 Hiker 工作流 Skill
├─ skill-groups/
│  ├─ ai-software-engineering-platform-enterprise/ # 第二组：5 插件 / 17 Skill
│  └─ desktop-app-reconstruction-zh/                # 第三组：1 个大型 Skill
├─ docs/
│  ├─ THREE_SKILL_GROUPS_ZH.md                  # 三组详细中文说明
│  ├─ SKILL_INDEX.md                            # 全部 Skill 索引
│  ├─ INSTALLATION.md                           # 三组安装方式
│  └─ USAGE.md                                  # 示例指令
├─ INSTALL.ps1                                  # 第一组项目级安装器
├─ UNINSTALL.ps1                                # 第一组卸载/恢复工具
└─ VALIDATE.ps1                                 # 仓库及三组结构校验
```

## 验证

在仓库根目录运行：

```powershell
.\VALIDATE.ps1 -Root .
```

验证器会检查第一组的 9 个 Skill、第二组的插件清单和 17 个 Skill，以及第三组的完整包结构。

## 安全默认值

- 第一组安装器默认 Dry Run，必须显式传入 `-Apply` 才会写文件。
- 不自动覆盖项目已有 `AGENTS.md`；`-MergeAgents` 只合并带标记的 Hiker 区块。
- 不默认执行生产数据库写入、真实 Provider 调用、计费、部署、服务重启、push 或 merge。
- 第二组中 `ai-engineering-core` 和 `ai-engineering-workspace` 包含生命周期 Hook，启用前应先审查并信任。
- 第三组必须先确认授权、资产许可和禁止操作边界。

## 更多文档

- [三组 Skill 中文详解](docs/THREE_SKILL_GROUPS_ZH.md)
- [完整 Skill 索引](docs/SKILL_INDEX.md)
- [安装指南](docs/INSTALLATION.md)
- [使用示例](docs/USAGE.md)
- [安全规则](docs/SAFETY_RULES.md)
