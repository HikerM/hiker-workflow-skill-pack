---
name: ai-engineering-router
description: AI软件工程原子Skill的唯一轻量自动入口。收到从0开始、存量源码接管、B/S、C/S、后端、Unity、插件开发、测试、审核、Git、多会话或发布请求时，由ChatGPT结合用户语义和有界项目证据选择当前阶段最多两个原子Skill，再交给确定性守门器校验数量、阶段、架构证据、权限与源码身份；规则不得按关键词替代模型选择，也不得扫描或预加载完整Skill正文。
---

# AI 工程轻量路由

## 核心原则

由 ChatGPT 负责理解和选择，由脚本负责校验和拒绝。不得把用户原文交给关键词分类器决定原子 Skill；不得在校验失败后由脚本自动换选其他能力。

## 必须执行

1. 会话第一条助手输出先展示 `已应用：01 智能工程核心｜智能工程轻量路由`。该入口不计入原子 Skill 上限。
2. 运行只读项目检查，不传用户原文：

   ```powershell
   py -3 <plugin-root>\scripts\suite_router.py --root <repo> --inspect
   ```

3. 读取检查结果给出的 [原子 Skill 语义路由目录](../../references/semantic-routing-catalog.md)。只读取这份紧凑元数据，不遍历 Skill 目录，不预读任何原子 `SKILL.md`。
4. ChatGPT 根据当前用户目标、项目证据和会话状态形成语义提案，至少包括：
   - `current_action`：本阶段唯一主动作；
   - `project_mode`：`greenfield`、`brownfield`、`existing` 或 `unknown`；
   - `architecture`：`bs`、`cs`、`backend`、`hybrid`、`tooling` 或 `unknown`；
   - `stage`：当前阶段；
   - `candidates`：最多两个当前原子 Skill ID；
   - `deferred`：最多八个未来阶段 Skill ID；
   - `negated_terms`、`future_terms` 和 `follow_up_actions`：按需记录，防止禁止项、示例和未来计划污染当前选择。
5. 将模型提案交给守门器。优先使用逐项参数，避免把用户原文嵌入 Shell：

   ```powershell
   py -3 <plugin-root>\scripts\suite_router.py `
     --root <repo> `
     --project-mode existing `
     --architecture backend `
     --stage development `
     --current-action "实现当前服务端功能" `
     --candidate backend-technology-router `
     --candidate backend-component-implementation
   ```

6. 只有 `guard_decision=ACCEPT` 时才完整读取输出 `load` 中的 `SKILL.md`。守门器拒绝时，根据 `diagnostics` 由 ChatGPT 重新选择一次；仍无法通过时保持 `unknown` 并说明缺少的项目事实，不加载猜测能力。
7. 原子 Skill 完整读取成功后，使用 `statectl.py route-record` 登记真实 `loaded`，再展示它生成的中文 `application_receipt`。路由候选不等于已经应用，不得提前手写原子 Skill 回执。
8. 当前阶段门禁通过后，由 ChatGPT 根据最新目标和证据重新选择待执行能力；不得让旧路由结果长期控制后续阶段。

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

- 路由只读取一个紧凑目录、浅层 Manifest 和有界 `.ai` 技术栈状态。
- 当前阶段最多加载两个原子 `SKILL.md`；轻量路由不计入上限。
- Skill 正文不写入路由状态；只保存阶段、中文活跃名称、待执行名称和指纹。
- 同一阶段且目标、项目 HEAD 和候选未变化时复用路由指纹，不重复读取目录或回执。
