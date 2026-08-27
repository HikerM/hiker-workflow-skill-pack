# 智能工程核心

<!-- engineering-current-facts: version=5.18.0; plugins=5; skills=42; tests=309 -->

本插件是 Hiker Engineering Capability System（Hiker 工程能力系统）的轻量前置底座；ChatGPT Desktop / Codex 继续提供 Agent Runtime。本插件不启动独立 Runtime、不调用外部模型，也不要求常驻后台服务。首次接管需要正式治理的项目时才运行“项目智能初始化”；无状态快速路径不写 `.ai`。后续领域 Skill 读取有界项目证据，不重复扫描整个仓库。长期任务使用“有界上下文记忆”：关键事实进入Task、决定、文档和Git，当前会话只加载固定大小工作集，checkpoint按近期与里程碑限额保留。

当前轻量路由由 ChatGPT 读取紧凑中文目录和有界项目证据，语义区分当前动作、否定项、历史错误和未来阶段，再选择最多两个原子 Skill。`suite_router.py` 同时输出规模预算和 `.ai` 源码一致性级别，只校验候选、阶段、架构证据、权限和源码身份；没有提案时保持空加载，冲突时要求模型重选，不按关键词擅自替换。实际应用回执由 Skill 完整读取后的加载遥测生成；路由候选不能冒充已应用项。

状态与兼容入口只能由当前 Skill 或宿主编排显式调用，manifest 不注册自动 Hook。语义理解由宿主模型完成；本地脚本只做确定性校验和有界记录，不读取完整 Prompt、聊天或助手输出，也不依据关键词替代模型选择。
