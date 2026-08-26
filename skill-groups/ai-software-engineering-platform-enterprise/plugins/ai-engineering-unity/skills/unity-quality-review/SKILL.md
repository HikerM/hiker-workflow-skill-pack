---
name: unity-quality-review
description: 只读审核Unity代码、Prefab、Scene、meta/GUID、页面生命周期、多分辨率、资源、GC和平台兼容。不得自行修改后宣布通过。
---

# Unity质量审核

Unity 视觉与呈现结论复用通用 C/S/Assurance 的 UI IR、Presentation/Error、Fidelity 与 Candidate/STALE；本审核在其上独立核验 UGUI/UI Toolkit、Prefab/Scene、CanvasScaler、Input、GC、资源引用、构建目标和平台约束，不以通用 PASS 代替 Unity 专项证据。

运行：

```bash
python3 <plugin-root>/scripts/unity_audit.py --root . --output .ai/quality/unity-audit.json
```

审核：

- Unity/Package/渲染管线与目标平台；
- 页面注册、Prefab复用和层级；
- `GameObject.Find`、过度 `Update`、`async void`、事件泄漏和 UI 直连数据；
- `.meta` 缺失、重复 GUID、Missing Script 和序列化风险；
- Scene/Prefab/Addressables/原生库变更；
- 遮挡、重叠、裁切、滚动、字体和弹窗；
- 下拉、选择器、模态层、Tooltip 和焦点导航是否实际展开验证；父子关闭、页面销毁、输入作用域、异步乱序和重复操作是否安全；高风险时执行 `interaction-conflict-governance` 的当前模块检查；
- FPS、GC Alloc、内存、DrawCall、加载和释放；
- Windows、macOS、Linux x64/ARM64 的实际证据。
- 正式构建是否残留演示场景、Mock服务、测试存档、占位或样例身份，是否向用户暴露本机路径、堆栈和内部诊断，以及同一页面能力是否存在多个活动控制器或权威写入者。

未在目标平台运行的构建只能标记 `NOT_VERIFIED`。
