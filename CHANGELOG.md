# Changelog

## Unreleased

- 智能软件工程平台升级到 `5.13.0`：原子 Skill 改为由 ChatGPT 结合用户语义和有界项目证据选择，确定性脚本退化为数量、阶段、架构证据、权限和源码身份守门器。
- 核心入口与工作区大型任务路由统一为单一模型选择权威；工作区脚本只展开已校验的架构通道，不再保留另一套B/S、C/S或技术栈关键词决策。
- 删除关键词路由的决定权；否定项、历史错误、示例和未来计划不再因出现技术名而触发错误能力，守门拒绝后由模型重选且不自动替换候选。
- 新增紧凑中文语义目录、模型提案协议、无提案安全退化、架构/阶段冲突测试和守门器性能基准；保持42个原子 Skill、最多两个活跃项和唯一隐式入口。
- 智能软件工程平台的架构与技术决策 Checkpoint 改为自动非阻塞记录；完成候选、证据、风险、回退和选择记录后继续，不再为平台、架构、部署、数据、安全或核心技术栈变化弹出审批。
- 智能软件工程平台升级到 `5.12.0`：总控按项目/仓库/角色族复用固定会话槽，实现/修复不再重复开 writer，审核/测试/复验不再重复开 assurance。
- 普通任务终态由总控自动 Checkpoint、释放锁和资源并进入可复用状态；项目终态自动归档并验证本地运行时释放，无需人工确认，且不授权强杀进程或强删 Worktree。
- 智能软件工程平台升级到 `5.10.0`：增加超长单会话路由态、上下文压缩恢复、第三个及之后 Skill 的待执行队列，以及 `.ai` 热状态/有界索引/压缩冷归档。
- 明确轻量路由不占两个原子 Skill 额度；会话第一条助手输出先显示中文路由回执，阶段路由后再显示实际活跃 Skill。
- 根 README、安装说明和验证报告同步到 5.10，并明确桌面端安装文件可立即刷新，但已经打开的任务不能强制热替换能力快照，需新建任务完成无重启切换。
- 智能软件工程平台升级到 `5.9.0`，新增「架构决策挑战与补全」，将用户架构思路视为待验证假设，主动发现反例、遗漏、冲突和演进风险，并新增覆盖五个插件全部42个 Skill 的发布级一致性审计。
- 智能软件工程平台升级到 `5.8.0`，新增「长链路变更收敛」，总计5个插件、41个原子 Skill；仓库总 Skill 数更新为55。
- 复杂改造新增分层验收、唯一活动实现、迁移退出条件、真实实验预算、连续失败换轨、部署哈希一致性和去重中文工程健康告警，防止同一功能多次修改后新旧代码长期并存。
- 轻量路由只在复杂长链路信号出现时加载该能力，继续保持最多两个原子 Skill 的性能上限；普通局部修改不增加额外负担。
- GitHub README、平台说明和使用指南补充UI设计/实现/修改的两阶段自动触发规则，明确普通交互不加载、高风险交互按模块升级及中文应用回执。
- 智能软件工程平台升级到 `5.7.0`，新增「交互状态与冲突治理」，总计 5 个插件、40 个原子 Skill；仓库总 Skill 数更新为 54。
- 大型界面改为按模块治理隐藏表面、状态机、浮层、焦点、快捷键、异步乱序和重复提交；零配置时不扫描源码，避免普通会话越来越重。
- 重写 GitHub 仓库首页，完整同步仓库 `0.8.0`、智能软件工程平台 `5.7.0`、桌面软件等价重建 `1.3.0` 和 54 个 Skill 的当前事实。
- 首页改用中文插件名称，补齐源码身份、Worktree 安全收敛、从零需求融合、存量源码对账、大型工程保护、多会话有界记忆与自动应用边界。
- 根验证器现在从 VERSION、插件 manifest 和实际 Skill 目录动态计算版本与数量；README、安装指南、详细说明或索引发生漂移时直接阻断发布。

## 0.8.0

- 自动策略收敛为仅第二组 `ai-engineering-router` 可隐式触发；第一组与第三组全部改为手动选择，减少无关任务的候选匹配和上下文干扰。
- 其余46个Skill保留手动可见，原子Skill由已明确选择的路由懒加载，降低发送消息时的候选选择开销。
- Enterprise 5.3 新增 `ai-engineering-router` 与 `greenfield-project-planning`，从零项目先融合稳定需求ID、冲突、验收和技术决策Checkpoint。
- 需求完整历史落盘、聊天只加载有界活动切片，新增需求增量合并而非覆盖旧约束。
- 桌面重建安装备份移至不可发现的 `.agents/skills-backup`，避免备份目录被当成重复Skill。
- 全局规则压缩为三个入口和关键安全边界，不再列举大量原子Skill。

## 0.7.0

- Added `bounded-context-memory` to plugin 01 and coordinated it with plugin 04 for durable multi-session handoff without loading full chat history.
- Bounded active context, session injection, per-section items, recent checkpoints, milestone checkpoints, and the pruning ledger through a project-level retention policy.
- Preserved essential requirements, decisions, task state, evidence and Git facts in canonical stores; compacted redundant checkpoint copies into a capped index and continuous hash chain.
- Added a bounded task-summary index so routine status rendering does not rescan every historical task while full task facts remain available on demand.
- Increased Enterprise to 30 Skills and the three-group repository total to 44 Skills.

## 0.6.0

- Expanded plugin 03 from Unity-only coverage to a general C/S client layer for Unity, Qt, .NET desktop, Electron/Tauri, Flutter, Android, Apple native, React Native, Java desktop, and embedded HMI.
- Added evidence-based C/S language, runtime, framework, SDK, build-tool, and version detection; missing exact versions remain explicit gaps instead of hard-coded defaults.
- Added four C/S atomic Skills and preserved all three Unity-specific Skills, increasing Enterprise to 29 Skills.
- Applied lightweight routing and lazy phase loading across all three repository groups; the desktop reconstruction group now has one router plus four atomic phase Skills.
- Added cross-group routing receipts and performance budgets so installed capabilities are not all loaded into one conversation.

## 0.5.1

- Made the Enterprise personal installer automatically merge the managed global Codex governance block while preserving and backing up existing `~/.codex/AGENTS.md` content.
- Added automatic five-plugin activation through a discovered or explicitly supplied Codex CLI, with honest manual-command fallback when no runnable CLI is available.
- Added idempotent reinstall, opt-out flags, and safe uninstall of only the installer-owned global instruction block.
- Extended integration coverage for automatic routing rules, visible plugin receipts, reinstall idempotency, opt-out behavior, and safe uninstall.

## 0.5.0

- Upgraded AI Software Engineering Platform Enterprise to 5.0.0 with 5 plugins and 25 Skills while preserving all three independent groups.
- Rebuilt workspace collaboration as a seven-role multi-Agent engineering control plane with project/task state, context snapshots, file locks, Git governance, multi-project isolation, acceptance closure, and visible plugin receipts.
- Added global Codex/ChatGPT Desktop auto-application instructions without expanding push, merge, deploy, or production-write authority.

## 0.4.0

- Upgraded AI Software Engineering Platform Enterprise to 4.2.0 while preserving the repository's three independent Skill groups.
- Added enforceable anti-template UI rules: no generic admin-dashboard skeletons, Bootstrap-style default visuals, or repetitive card soup.
- Required project-specific design systems, semantic color tokens, spacing scales, component reuse contracts, visual focus, rhythm, signature elements, and purposeful micro-interactions before implementation.
- Extended independent design readiness and read-only Web quality review to block monotonous or template-driven UI, and enhanced `web_audit.py` with Bootstrap, repeated-card, hardcoded-spacing, decorative-effect, and Token-evidence signals.
- Fixed Python 3.10 TOML detection compatibility and made root `VALIDATE.ps1` resolve the repository root correctly when invoked from another directory.

## 0.3.1

- Upgraded AI Software Engineering Platform Enterprise to 4.1.0 with 5 plugins and 18 Skills.
- Enhanced `web-ui-design` for requirement-driven page discovery, dynamic complexity assessment, deep contracts for complex surfaces, identifier isolation, and lifecycle consistency.
- Added the independent, read-only `design-readiness-review` gate with semantic traceability, P0/P1 blocking, confidence, unknowns, and next-stage decisions.
- Enhanced `full-change-risk-review` with incremental design impact analysis, re-review triggers, and cross-layer remediation checks.
- Added simple CRUD and complex editor/publishing forward-validation scenarios and refreshed repository indexes, documentation, validation evidence, and plugin archives.

## 0.3.0

- Expanded the repository from one pack into three clearly separated Skill groups.
- Preserved the original Hiker workflow group at `.agents/skills/` with 9 Skills and backward-compatible project installers.
- Added AI Software Engineering Platform Enterprise 4.0 as an independent group with 5 plugins and 17 Skills.
- Added Desktop App Reconstruction ZH 1.1 as an independent, validated desktop reconstruction Skill.
- Added detailed Chinese documentation, a 27-Skill index, separate installation procedures, usage examples, and group-selection guidance.
- Extended repository validation to run the native validators for all three groups.

## 0.2.0

- Reworked the pack into a project-level Hiker Workflow Skill Pack.
- Renamed the router skill to `hiker-workflow-router`.
- Added `nodets-execution-pipeline-guardrails`.
- Standardized every `SKILL.md` with required sections and `owner: Hiker`.
- Added project-safe `INSTALL.ps1`, `UNINSTALL.ps1`, `VALIDATE.ps1`, and dependency-free `scripts/validate_skills.py`.
- Added docs and examples for installation, usage, skill routing, safety rules, thread review, phase review, and NodeTs execution pipeline checks.
- Added dry-run-first install behavior, backup support, merge-only `AGENTS.md` handling, install marker, validation, and rollback flow.
