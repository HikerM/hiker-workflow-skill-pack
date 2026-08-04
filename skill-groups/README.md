# Skill Groups

本目录只存放仓库新增的第二组和第三组源码。第一组为了保持现有安装脚本和历史使用方式，继续保留在仓库根目录的 `.agents/skills/`。

| 组别 | 目录 | 内容 |
|---|---|---|
| 第一组 | `../.agents/skills/` | Hiker 工作流守护组，9 个 Skill |
| 第二组 | `ai-software-engineering-platform-enterprise/` | 企业软件工程平台，5 个插件、18 个 Skill |
| 第三组 | `desktop-app-reconstruction-zh/` | 桌面软件等价重建，1 个大型 Skill |

不要将第二组的 18 个 Skill 平铺复制到第一组目录。第二组依赖插件清单、共享脚本、Hook 和 Marketplace 元数据，应保持完整插件包结构。第三组也应作为单一 Skill 整体安装，不能把其 `references/`、`scripts/` 或 `assets/` 拆散。

详细说明见 [`../docs/THREE_SKILL_GROUPS_ZH.md`](../docs/THREE_SKILL_GROUPS_ZH.md)。
