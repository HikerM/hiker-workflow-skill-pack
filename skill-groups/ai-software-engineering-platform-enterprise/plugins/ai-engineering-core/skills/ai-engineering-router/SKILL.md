---
name: ai-engineering-router
description: AI软件工程三十三个Skill的唯一轻量自动入口。收到从0开始、部分源码二次开发、接管现有项目、B/S、C/S、Unity、测试、审核、Git、多会话或发布请求时，先用确定性脚本识别项目模式、架构和阶段，只读取最多两个直接相关的原子Skill，并展示应用回执；不得扫描或预加载完整Skill目录。
---

# AI 工程轻量路由

## 目标

用一个小入口替代大量原子 Skill 同时参与隐式选择。路由阶段只做意图分类和最小项目证据检查，不执行完整仓库扫描。

## 必须执行

1. 将用户原始请求原样传给 [suite_router.py](../../scripts/suite_router.py)：

   ```powershell
   py -3 <plugin-root>\scripts\suite_router.py --root <repo> --request "<用户请求>"
   ```

2. 只读取输出 `load` 中的 `SKILL.md`，最多两个。不得为“可能有用”而遍历其他 Skill。
3. 先展示路由回执：项目模式、架构、阶段、实际应用 Skill、原因、置信度和待确认项。
4. 按已读取原子 Skill 执行。若原子 Skill 需要项目状态，则只读取它明确要求的状态文件。

## 路由约束

- 空仓库、无工程证据且用户要求新建产品：先进入 `greenfield-project-planning`，不得直接套脚手架。
- 已有部分源码、半成品或二次开发且要融合新需求：先进入 `project-bootstrap` 与 `brownfield-requirement-reconciliation`，不得重新套脚手架覆盖现有实现。
- 现有仓库首次接管或技术栈变化：进入 `project-bootstrap`。
- B/S、C/S、Unity、质量、工作区、多会话分别懒加载对应原子 Skill；一轮最多两个。
- 需求同时跨越多个阶段时，先选当前最早未通过门禁的阶段，不把设计、实现、审核、发布一次性全载入。
- 找不到可靠证据时显式输出 `unknown`，不得默认最新框架或把 Unity 当作所有 C/S。

## 性能预算

- 路由脚本不得递归扫描项目源码。
- Skill 加载数上限：2。
- 路由输出只保留当前轮需要的信息，不复制整个 Skill 清单或聊天历史。
- 简单问答、翻译和非工程任务返回空路由，不初始化 `.ai`。

## 禁止

- 不直接修改 `main`、push、merge、发布或部署。
- 不因已安装某插件就声称本轮已应用。
- 不把完整需求账本或 checkpoint 历史重复注入会话。
