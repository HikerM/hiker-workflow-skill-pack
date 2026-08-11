# 03 C/S客户端工程

本插件采用“轻量入口路由 + 按阶段懒加载的原子 Skill”，面向各类 C/S 客户端，而不再等同于 Unity 插件。

## 通用能力

- `cs-client-router`：只读取 `.ai/context/tech-stack.json`，识别技术族并选择当前阶段的一个 Skill。
- `cs-ui-design`：建立客户端设计系统、间距、色彩、组件复用、窗口/设备生命周期、离线和 API 契约。
- `cs-component-implementation`：在现有框架中实现，不擅自迁移技术栈。
- `cs-quality-review`：独立只读审核视觉、线程、生命周期、资源、API、平台、性能、打包和更新证据。

支持 Unity、Qt Widgets/QML、WPF、WinUI、WinForms、Avalonia、.NET MAUI、Electron、Tauri、Flutter、Android Views/Compose、SwiftUI/UIKit/AppKit、React Native、JavaFX/Swing、LVGL/嵌入式 HMI。未知框架会明确报告不确定项，不套用错误技术规范。

## Unity专项能力

原有 `unity-ui-design`、`unity-component-implementation`、`unity-quality-review` 完整保留，继续覆盖 UGUI、UI Toolkit、Prefab、Scene、meta/GUID、页面生命周期、资源引用、多分辨率、性能和平台兼容。

## 前后端协作

C/S 不是只有客户端。工作区路由会建立客户端、共享后端服务和契约/数据通道：03 插件负责客户端，后端开发由独立开发职责承担，浏览器端与客户端共享同一后端时不再生成两套重复服务通道；双方通过版本化 API/事件、数据库影响和兼容规则协作。

## 性能约束

- 一次项目识别，多次复用，不为每个 Skill 重扫全仓；
- 一次只启用设计、实现或审核中的当前阶段；
- 一次只读取命中技术族的参考小节；
- 默认排除依赖缓存和构建产物，不预加载全部框架资料；
- 路由收据必须显示实际启用与未启用能力。
