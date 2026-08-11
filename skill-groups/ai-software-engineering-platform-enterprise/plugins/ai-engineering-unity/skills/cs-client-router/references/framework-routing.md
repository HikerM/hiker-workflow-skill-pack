# C/S技术族路由表

只读取与当前 `family` 对应的小节。

- `unity`：UGUI、UI Toolkit、Prefab、Scene、meta/GUID；转用 `unity-*` 专项能力。
- `qt`：读取 [Qt客户端约束](cs-qt.md)。
- `dotnet-desktop`：读取 [.NET桌面客户端约束](cs-dotnet-desktop.md)。
- `electron-tauri`、`flutter`、`react-native`：读取 [跨平台客户端约束](cs-cross-platform.md) 中命中的小节。
- `android`、`apple-native`、`java-desktop`：读取 [原生与Java客户端约束](cs-native-java.md) 中命中的小节。
- `embedded-hmi`：读取 [嵌入式HMI约束](cs-embedded-hmi.md)。

所有技术族共同要求：沿用真实框架与版本，不强制迁移；客户端与后端通过版本化API/事件契约协作；视觉设计必须包含Design Token、间距、色彩、组件复用和完整状态，不输出千篇一律卡片或无层级的单调界面。
