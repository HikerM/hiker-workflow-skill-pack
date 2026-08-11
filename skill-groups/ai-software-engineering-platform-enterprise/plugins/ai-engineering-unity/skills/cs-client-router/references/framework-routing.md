# C/S技术族路由表

只读取与当前 `family` 对应的小节。

- `unity`：UGUI、UI Toolkit、Prefab、Scene、meta/GUID；转用 `unity-*` 专项能力。
- `qt`：Qt Widgets/QML，含C++或Python绑定；保持信号槽、对象所有权、线程亲和性和资源系统。
- `dotnet-desktop`：WPF、WinUI、WinForms、Avalonia、.NET MAUI；保持MVVM/现有绑定模式、Dispatcher和窗口生命周期。
- `electron-tauri`：保持主进程/渲染进程或Rust命令边界、IPC白名单、CSP、权限和安装更新策略。
- `flutter`：保持现有状态管理、Widget组合、平台通道和桌面/移动生命周期。
- `android`：Views/Compose；保持Activity/Fragment/导航、生命周期、权限、后台限制和配置变更。
- `apple-native`：SwiftUI/UIKit/AppKit；保持状态所有权、Scene/Window生命周期、并发隔离和平台人机规范。
- `react-native`：保持导航、状态管理、原生模块边界、Hermes与平台差异。
- `java-desktop`：JavaFX/Swing；保持UI线程、FXML/组件边界和打包方式。
- `embedded-hmi`：LVGL或设备UI；保持内存、刷新率、输入设备、显示分辨率、实时性与硬件抽象边界。

所有技术族共同要求：沿用真实框架与版本，不强制迁移；客户端与后端通过版本化API/事件契约协作；视觉设计必须包含Design Token、间距、色彩、组件复用和完整状态，不输出千篇一律卡片或无层级的单调界面。
