# 原生与Java客户端约束

## Android

- 从 Gradle、AGP、Kotlin、Compose/Views 与 SDK 清单确认版本；保持 Activity/Fragment/Compose 导航和状态所有权。
- 覆盖配置变更、进程重建、后台限制、权限拒绝、离线和生命周期取消；避免持有失效 Context/View。

## Apple Native

- 从 Xcode工程、Swift工具链与部署目标确认 SwiftUI/UIKit/AppKit；保持 State/Observable、Scene/Window 和并发隔离边界。
- 覆盖任务取消、主线程/UI隔离、后台切换、权限和多窗口；公共模型变化做迁移与消费者回归。

## Java Desktop

- 区分 JavaFX 与 Swing 及运行时/打包版本；保持 JavaFX Application Thread 或 EDT 边界。
- 后台任务不得阻塞 UI 线程；FXML、Controller、Model 和服务职责清晰，窗口关闭时释放订阅与资源。

共同要求：遵循目标平台原生行为和可访问性，不用统一配置抹平生命周期差异；只共享稳定的业务契约和视觉语义。
