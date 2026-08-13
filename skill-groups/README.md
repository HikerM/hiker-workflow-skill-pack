# Skill Groups

本目录只存放仓库新增的第二组和第三组源码。第一组为了保持现有安装脚本和历史使用方式，继续保留在仓库根目录的 `.agents/skills/`。

| 组别 | 目录 | 内容 |
|---|---|---|
| 第一组 | `../.agents/skills/` | Hiker 工作流守护组，9 个 Skill |
| 第二组 | `ai-software-engineering-platform-enterprise/` | 智能软件工程平台 5.9，5 个插件、42 个 Skill |
| 第三组 | `desktop-app-reconstruction-zh/` | 桌面软件等价重建，1 个轻量路由和4个阶段原子Skill |

不要将智能软件工程平台的42个Skill平铺复制到第一组目录。该平台依赖插件清单、共享脚本、状态协议和Marketplace元数据，应保持完整插件包结构。桌面软件等价重建安装器会安装总路由和4个原子Skill，但共享 `references/`、`scripts/`、`assets/` 仍必须作为同一组保留。

详细说明见 [`../docs/THREE_SKILL_GROUPS_ZH.md`](../docs/THREE_SKILL_GROUPS_ZH.md)。
