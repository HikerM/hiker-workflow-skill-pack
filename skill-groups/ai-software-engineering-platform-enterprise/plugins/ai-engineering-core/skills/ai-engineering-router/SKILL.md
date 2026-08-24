---
name: ai-engineering-router
description: AI软件工程的唯一轻量自动入口；由ChatGPT语义选择当前阶段最多两个原子Skill，脚本只校验项目证据、阶段、版本和权限。简单问答不运行脚本，项目动作按证据一次准入或最多一次检查后准入。
---

# AI 工程轻量路由

## 核心原则

由 ChatGPT 负责理解和选择，由脚本负责校验和拒绝。不得把用户原文交给关键词分类器决定原子 Skill；不得在校验失败后由脚本自动换选其他能力。

## 必须执行

1. 会话第一条助手输出先展示 `已应用：01 智能工程核心｜智能工程轻量路由`。该入口不计入原子 Skill 上限。
2. 先判定性能路径：
   - `FAST`：解释、状态查询、简单诊断且不要求读取或修改项目，直接回答；不得运行脚本、读取 `.ai` 或加载原子 Skill。
   - `PROJECT`：普通设计、实现、审核或测试。已有当前 Git、Manifest 和可信热状态证据时，ChatGPT直接提交候选做一次守门；证据不足才运行一次只读检查。
   - `GOVERNED`：多会话、合并、发布、跨仓库或长链路任务，才启用状态机与完整治理。
3. 证据不足时运行只读项目检查，不传用户原文：

   ```powershell
   py -3 <plugin-root>\scripts\suite_router.py --root <repo> --inspect
   ```

   检查结果给出有界预算、`.ai` 一致性和五插件版本指纹。不得为得到“更多把握”重复检查。

   没有 `.ai` 时返回 `STATELESS_UNMANAGED`，直接以最新用户请求和当前 Git 轻量推进，不得强制初始化治理。存在旧任务状态但缺少可信源码指纹，或仓库身份/历史冲突时返回隔离策略：普通设计、实现、审核和测试可继续，但禁止恢复旧 Task、旧路由、旧 PASS、旧锁、创建多会话/Worktree、合并或发布；不得通过补写来源指纹把旧状态自动变成可信。

4. 读取 [原子 Skill 语义路由目录](../../references/semantic-routing-catalog.md)。只读取紧凑元数据，不遍历 Skill 目录。
5. ChatGPT 形成语义提案，至少包括：
   - `current_action`：本阶段唯一主动作；
   - `project_mode`：`greenfield`、`brownfield`、`existing` 或 `unknown`；
   - `architecture`：`bs`、`cs`、`backend`、`hybrid`、`tooling` 或 `unknown`；
   - `stage`：当前阶段；
   - `candidates`：最多两个当前原子 Skill ID；
   - `deferred`：最多八个未来阶段 Skill ID；
   - `negated_terms`、`future_terms` 和 `follow_up_actions`：按需记录，防止禁止项、示例和未来计划污染当前选择。
   同一目标修订、源码身份、HEAD、脏状态、Manifest、阶段、动作和候选未变化时，复用已有准入指纹，不重复读取目录或 Skill 正文。
6. 将模型提案交给守门器。证据已经充分时直接执行本命令，不再先运行 `--inspect`：

   ```powershell
   py -3 <plugin-root>\scripts\suite_router.py `
     --root <repo> `
     --project-mode existing `
     --architecture backend `
     --stage development `
     --goal-revision 7 `
     --current-action "实现当前服务端功能" `
     --candidate backend-technology-router `
     --candidate backend-component-implementation
   ```

7. `guard_decision=ACCEPT` 后才读取 `load`。五插件完整版本不一致时禁止加载；项目路由记录来自旧版本时，只允许「上下文恢复」「有界上下文记忆」或「可中断任务控制」保存 Checkpoint 并迁移，新旧版本不得共同继续写源码。
8. Skill 读取后用 `statectl.py route-record` 登记真实加载项、路由指纹和套件版本，再显示中文回执。缓存命中时不重复读取或显示。
9. 阶段或目标修订变化后重新语义选择；需求调整不得自动新建会话、Worktree 或总控。

## 语义选择要求

- 区分“采用 C/S”“不是 C/S”“禁止 Android”“过去误判成 C/S”“未来可能增加客户端”。只有当前正向目标参与候选选择。
- 区分当前动作与完整生命周期。例如“实现、测试、审核、推送”当前只选择最早未完成阶段，后续动作进入待执行队列。
- 用户方案是待验证候选，不是批准答案；架构相关任务按需选择「架构决策挑战与补全」。
- 已有源码先根据工程证据建立能力基线；从零项目先融合需求；不因出现技术名就生成脚手架。
- 项目证据与模型提案冲突时服从守门器拒绝，修正模型提案；不得覆盖工程事实。
- 简单问答、翻译和非工程任务不应进入本入口；如果已误触发，不提交原子候选。

## 守门器职责

守门器只执行确定性约束：候选存在性、最多两个活跃项、待执行队列上限、阶段兼容、Manifest/`.ai` 架构证据、源码身份冲突和安全边界。它不得：

- 按关键词推断架构、阶段或 Skill；
- 把否定词、示例、历史错误或未来计划当成当前意图；
- 校验失败后擅自换成另一个 Skill；
- 读取完整聊天历史或递归扫描源码；
- 扩大 push、merge、部署、发布或生产写入权限。

## 性能预算

- `FAST` 路径回答前零次 Shell 调用；`PROJECT` 已有证据时最多一次准入工具往返，证据不足时最多一次检查加一次准入。
- 路由只读取紧凑目录、浅层 Manifest 和有界 `.ai` 热状态；准入缓存绑定目标修订、源码身份、HEAD、脏状态、Manifest、阶段与候选。
- 当前阶段最多加载两个原子 `SKILL.md`；轻量路由不计入上限。
- Skill 正文不写入路由状态；只保存阶段、中文活跃名称、待执行名称和指纹。
- 本地路由 P95 目标不超过200ms；普通单工具建议不超过30秒，大型工程45秒，发布分片60秒。
- 小项目优先直接读取当前任务、差异、契约和测试；大型或长寿命项目只从有界索引进入受影响分片。风险只会提升预算层级，不会取消文件、日志和 Skill 上限。
- 用户、公司、仓库和业务名称不得写入插件模板、Eval、发布包或示例；项目运行时状态只保存在项目自身 `.ai`，对外证据使用摘要、哈希和通用 ID。
