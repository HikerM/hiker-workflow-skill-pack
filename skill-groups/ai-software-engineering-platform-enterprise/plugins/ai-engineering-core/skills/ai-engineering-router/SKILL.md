---
name: ai-engineering-router
description: AI软件工程原子Skill的唯一轻量自动入口。收到从0开始、部分源码二次开发、接管现有项目、B/S、C/S、后端、Unity、插件开发、测试、审核、Git、多会话或发布请求时，先用确定性脚本识别项目模式、架构和阶段，只读取最多两个直接相关的原子Skill，并展示一行中文应用回执；不得扫描或预加载完整Skill目录。
---

# AI 工程轻量路由

## 目标

用一个小入口替代大量原子 Skill 同时参与隐式选择。路由阶段只做意图分类和最小项目证据检查，不执行完整仓库扫描。

## 必须执行

1. 将用户原始请求原样传给 [suite_router.py](../../scripts/suite_router.py)：

   ```powershell
   py -3 <plugin-root>\scripts\suite_router.py --root <repo> --request "<用户请求>"
   ```

2. 会话的第一条助手输出必须先展示 `已应用：01 智能工程核心｜智能工程轻量路由`，不得把计划、分析、提问或工具调用放在它前面。该路由入口不计入原子 Skill 数量上限。
3. 只读取输出 `load` 中的 `SKILL.md`；同一阶段最多两个活跃原子 Skill。不得为“可能有用”而遍历其他 Skill。
4. 路由完成后，在首次实质动作前展示实际活跃原子 Skill 的中文插件名与中文 Skill 名。只有阶段、活跃项变化或上下文恢复时才再次展示，避免每轮重复刷屏。
5. 输出 `deferred` 中的能力不得静默丢失：当前阶段通过门禁后重新路由，按顺序激活下一批；只保存名称、阶段与指纹，不把 Skill 正文长期注入上下文。
6. 项目已初始化 `.ai` 时，把输出的 `stage`、活跃中文 Skill 名、待执行中文 Skill 名和 `route_fingerprint` 写入有界路由态：

   ```powershell
   py -3 <plugin-root>\scripts\statectl.py --root <repo> route-record --stage <stage> --route-fingerprint <fingerprint> --active-skill <名称> --deferred-skill <名称>
   ```

7. 按已读取原子 Skill 执行。若原子 Skill 需要项目状态，则只读取它明确要求的状态文件。

## 路由约束

- 空仓库、无工程证据且用户要求新建产品：先进入 `greenfield-project-planning`，不得直接套脚手架。
- 已有部分源码、半成品或二次开发且要融合新需求：先进入 `project-bootstrap` 与 `brownfield-requirement-reconciliation`，不得重新套脚手架覆盖现有实现。
- 用户提供系统架构、功能架构、模块拆分或技术方案思路时，不得把用户方案直接当成批准答案；按阶段进入「架构决策挑战与补全」，主动寻找反例、遗漏、隐性耦合和真正不同的替代方案。
- 现有仓库首次接管或技术栈变化：进入 `project-bootstrap`。
- B/S、C/S、Unity、质量、工作区、多会话分别懒加载对应原子 Skill；一阶段最多两个活跃原子 Skill，轻量路由不占额度。
- 同时涉及浏览器端、客户端或服务端的实现与审核先进入任务分流，不允许因分支顺序只处理其中一端。
- 跨模块、跨仓库、真实外部执行、部署回滚、同一目标反复修复，或出现新旧实现并存、旧结论失效、范围持续膨胀时，按需进入“长链路变更收敛”；普通局部修改不得额外加载它。
- 需求同时跨越多个阶段时，先选当前最早未通过门禁的阶段，不把设计、实现、审核、发布一次性全载入。
- 找不到可靠证据时显式输出 `unknown`，不得默认最新框架或把 Unity 当作所有 C/S。
- 插件、Skill、Marketplace、Codex扩展或桌面安装任务优先识别为工具链工程，不得因出现“桌面端、审核”而误路由到C/S客户端。
- `.csproj` 必须依据 Web SDK、ASP.NET Core、WPF、WinForms、WinUI、Avalonia 或 MAUI 等内容证据分类；不得仅凭文件扩展名认定为客户端或服务端。

## 性能预算

- 路由脚本不得递归扫描项目源码。
- 活跃原子 Skill 加载数上限：2；轻量路由不计入该上限。
- 第三个及之后的匹配项进入有界 `deferred` 队列，完成当前门禁后再加载，禁止静默截断。
- 超长会话只持久化 `.ai/runtime/skill-routing.json` 中的阶段、活跃名称、待执行名称与路由指纹，不持久化 Skill 正文。
- 路由输出只保留当前轮需要的信息，不复制整个 Skill 清单或聊天历史。
- 简单问答、翻译和非工程任务返回空路由，不初始化 `.ai`。

## 禁止

- 不直接修改 `main`、push、merge、发布或部署。
- 不因已安装某插件就声称本轮已应用。
- 不把完整需求账本或 checkpoint 历史重复注入会话。
