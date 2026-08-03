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
- 动态内容使用 Layout/虚拟化，不堆固定坐标；
- 资源加载有失败、取消、缓存和释放；
- 不自动新增原生插件或生产 Package。

## 完成证据

编译、EditMode/PlayMode、分辨率截图、Console、新增引用、资源释放、目标平台构建状态和未验证范围。
