---
name: unity-component-implementation
description: 在现有Unity版本和UI体系中实现Prefab、VisualElement、Renderer或页面组件；遵守现有导航、数据层和资源生命周期。不得用于Web前端或擅自升级Unity。
---

# Unity组件与页面实现

## 实现前

1. 读取 `.ai/context/tech-stack.json` 和锁定决策；
2. 运行 [unity_registry.py](../../scripts/unity_registry.py) 盘点现有页面、Prefab 和 UI 脚本；
3. 明确允许修改目录、目标平台和验证场景；
4. 优先复用已有组件和页面注册方式。

## 职责边界

- MonoBehaviour/VisualElement 负责生命周期、引用、输入和呈现；
- 应用服务负责用例；
- Domain 不依赖 UnityEngine；
- Infrastructure 负责文件、数据库、网络和资源实现；
- Renderer 不直接写 SQL 或复杂业务规则。

## 强制规范

- 禁止 `GameObject.Find` 获取核心依赖；
- `OnEnable` 订阅必须有对应解除；
- 普通 UI 不使用 `Update` 轮询状态；
- 异步任务处理取消、销毁和异常；
- 下拉、选择器、模态层和输入焦点按当前模块交互契约实现；出现叠加、快捷键/手柄、异步乱序或重复操作风险时执行 `interaction-conflict-governance`，不建立第二套全局事件系统；
- 动态内容使用 Layout/虚拟化，不堆固定坐标；
- 资源加载有失败、取消、缓存和释放；
- 不自动新增原生插件或生产 Package。
- 正式构建不默认启用演示场景、Mock服务或测试存档，不把占位数据、样例身份、本机路径、堆栈或内部诊断显示给玩家或用户。
- 旧Prefab、旧页面控制器和旧数据通道只允许作为有退出条件的迁移路径；同一能力只能有一个权威活动实现和一个权威状态写入者。

## 完成证据

编译、EditMode/PlayMode、分辨率截图、隐藏表面展开/关闭/异常状态、输入焦点与快速重复操作、Console、新增引用、资源释放、目标平台构建状态和未验证范围。
