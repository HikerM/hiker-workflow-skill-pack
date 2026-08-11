# Enterprise 5.3 本地验证报告

生成版本：5.3.0
生成日期：2026-08-11

## 结构与官方校验

- 插件：5 个；Skill：33 个。
- `validate_bundle.py`：通过，并强制只有 `ai-engineering-router` 允许隐式调用。
- 官方 `quick_validate.py`：三组全部 47 个 Skill 通过。
- 官方 `validate_plugin.py`：5/5 插件通过。
- 第三组 `validate_skill_package.py --self-test`：PASS；顶层路由隐式、四个原子Skill非隐式策略通过。
- 第一组 `validate_skills.py`：PASS；顶层路由隐式、八个原子Skill非隐式策略通过。

## 功能与回归

- 单元测试：Core 14、Quality 11、C/S与Unity 7、Web 6、Workspace 10，共 48/48 通过。
- 集成 Smoke：15/15 通过，包括初始化、上下文压缩/恢复、有界记忆、Worktree、完整变更集、风险、图谱限流、真实命令、个人安装、全局规则幂等与安全卸载。
- 0→1路由：空项目优先进入 `greenfield-project-planning`，不会直接套脚手架。
- 存量源码路由：半成品、二次开发或部分源码项目依次进入 `project-bootstrap` 和 `brownfield-requirement-reconciliation`；源码能力、需求差异和影响矩阵均有机器可验事实源。
- 需求融合：稳定 Requirement ID、增量 revision history、冲突记录、活动切片和校验通过。
- C/S路由：WPF等客户端先进入版本证据识别，再按当前实现/设计/审核阶段加载一个原子Skill；每轮上限两个。
- 有界多会话：活动上下文、会话注入、每节条目、近期/里程碑checkpoint和压缩账本均有上限；正式Task、决定、Git与验收证据保留在事实源。
- B/S视觉：设计系统、语义色彩、间距尺度、组件复用、视觉焦点与反模板门禁保留，未因性能优化删除。

## 本机安装结果

- 第一组：0.8.0，9个Skill，只有1个隐式入口。
- 第二组：5个插件均为5.3.0，`installed: true`、`enabled: true`；33个Skill，只有1个隐式入口。
- 第三组：1.3.0，5个Skill，只有1个隐式入口。
- 三组总计47个Skill、3个隐式入口、44个按需原子Skill。
- `.agents/skills` 下可见的 `*.backup-*` 目录：0；旧备份已迁移到 `.agents/skills-backup`，内容可恢复。

## 自定义指令与性能

- `C:\Users\Administrator\.codex\AGENTS.md` 从5333字节/73行精简为2275字节/26行，保留中文、`@`手选、多角色合并、三个路由、回执和权限边界。
- `C:\Users\Administrator\AGENTS.md` 从5516字节/98行的乱码长规则修复为944字节/15行轻量规则。
- 路由脚本以独立Python进程运行200次的本机平均耗时为72.73ms；脚本不递归扫描源码，只检查有限项目标记。
- 候选减少和指令缩短能够减少本地前置工作，但不能把截图中的29秒全部归因于插件；模型排队、网络、任务创建和客户端版本仍需在重启后的新任务中实测。

## 分发包

- 已生成5个 `5.3.0` ZIP，并更新 `SHA256SUMS.txt`。
- 安装器已验证保留用户规则、托管区块幂等、可选择退出全局合并、CLI自动启用和安全卸载。
- 第三组安装器把备份写入不可发现的 `skills-backup`，避免后续重复索引。

## 边界

本地验证不能替代其他账号/客户端版本的真实安装、特定项目的Unity Editor构建、CI、真实Provider和生产发布验收。新版本必须在重启ChatGPT/Codex并新建任务后才会进入该任务的Skill目录快照。
