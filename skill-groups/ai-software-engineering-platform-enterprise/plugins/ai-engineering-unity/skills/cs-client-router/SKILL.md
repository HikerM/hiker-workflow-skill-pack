---
name: cs-client-router
description: 在C/S、桌面、移动、游戏客户端或嵌入式HMI任务开始时，从已初始化项目状态轻量识别Unity、Qt、.NET桌面、Electron/Tauri、Flutter、Android、Apple原生、React Native、Java桌面或LVGL等技术族，并只路由当前阶段需要的一个通用或专项Skill。用于防止广覆盖插件在每次会话全量加载；不得扫描整个仓库或擅自迁移技术栈。
---

# C/S客户端轻量路由

1. 先读取 `.ai/context/tech-stack.json`；不存在时调用 `project-bootstrap`，不要自行递归扫描全仓。
2. 运行 `python <plugin-root>/scripts/client_stack.py --root .`，使用其紧凑结果确定 `family`、语言/运行时/框架/SDK/构建工具版本、证据和不确定项。
3. 只选择当前阶段的一个能力：设计用 `cs-ui-design`，实现用 `cs-component-implementation`，审核用 `cs-quality-review`；Unity任务优先使用同阶段的 `unity-*` 专项 Skill。
4. 仅在需要框架差异时，先读 [技术族路由表](references/framework-routing.md)，再只读取其指向的一个原子参考：Qt、.NET桌面、跨平台桌面、原生移动/Java桌面或嵌入式HMI；不加载无关技术族资料。`hybrid-client` 必须先确定当前子项目，不能一次展开所有参考。
5. 涉及服务端、数据库或API实现时交给 `cs-backend` 与 `contract-data` 通道；本路由器不代替后端工程。

## 性能预算

- 默认只读技术栈摘要、当前任务和直接影响文件，不建立全仓知识图谱。
- 不同时激活设计、实现、审核、发布能力；阶段改变时再切换。
- 不因“可能有用”读取全部参考、全部源码、构建产物或依赖缓存。
- 无法可靠识别时输出 `unknown` 与所需最小证据，不猜测框架。
- 版本证据优先级为已安装清单或锁文件、工程/工具链文件、依赖声明范围；缺少精确版本时保留 `version_gaps`，不得写死版本、选择最新版或套用另一框架规则。

## 输出

输出一张紧凑路由收据：技术族、技术与版本证据、版本缺口、客户端范围、后端/API依赖、选用 Skill、读取的参考小节、未启用能力及原因。
