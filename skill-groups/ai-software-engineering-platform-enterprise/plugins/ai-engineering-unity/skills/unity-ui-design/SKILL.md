---
name: unity-ui-design
description: 为已初始化的Unity客户端、电子教材、虚拟仿真或数字孪生项目设计UI、Prefab层级、Anchor、页面生命周期和交互状态。不得生成Web页面结构。
---

# Unity UI与交互设计

## 前置

读取：

- `.ai/context/tech-stack.json` 中 Unity 精确版本和 Packages；
- 当前 UI 系统（UGUI/UI Toolkit/混合）；
- Canvas、分辨率、输入方式和页面注册体系；
- 锁定决策和已有 Prefab 注册表。

## 设计产物

- 页面目标、输入方式、导航和生命周期；
- Hierarchy/VisualTree 层级；
- Anchor、Pivot、Layout、CanvasScaler 或 PanelSettings 规则；
- 基础、组合、领域和页面 Prefab/VisualElement 拆分；
- 默认、加载、空、错误、无权限和资源失败状态；
- 1366×768、1440×900、1920×1080、2560×1440；
- 中文字体、长文本、窗口化和全屏；
- 资源 Viewer 的加载、操作和释放；
- 工程可实现性与验收标准。
- 下拉、选择器、模态层、Tooltip、手柄/键盘焦点和页面叠加等隐藏交互的稳定 ID、状态转换、输入作用域、父子关闭和非默认状态证据；存在冲突风险时交给 `interaction-conflict-governance` 按当前 UI 模块检查。

## 禁止

- 把网页后台直接套进 Unity；
- 用固定坐标适配全部分辨率；
- 设计无法在目标 Unity 版本稳定实现的大量实时模糊效果；
- 绕过现有 PageRegistry/导航体系创建第二套系统。
