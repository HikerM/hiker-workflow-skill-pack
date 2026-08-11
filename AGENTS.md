# Hiker 工作流轻量规则

<!-- hiker-workflow-pack start -->

- 默认中文回答；代码、命令、文件路径、API、包名和框架名保持原文。
- 工程专项复核先使用 `hiker-workflow-router`，只读取它返回的一个原子 Skill；普通开发交给 `ai-engineering-router`，已授权桌面等价重建交给 `desktop-app-reconstruction-zh`。不得同时预加载三组。
- 修改前确认仓库根、Git 分支/状态、用户边界与现有改动；结论必须区分已运行证据、静态审计和未验证项。
- API、数据库、队列、Provider、计费、Unity Scene/Prefab/meta 等高冲突边界按所选原子 Skill 门禁处理。
- 未经明确授权不得 push、merge、发布、部署、修改生产数据、强制覆盖冲突或直接修改 main。
- UI/文档/图片等交付必须产出真实文件并报告绝对路径；不得伪造结果。

<!-- hiker-workflow-pack end -->
