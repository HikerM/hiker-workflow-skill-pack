---
name: unity-quality-review
description: 只读审核Unity代码、Prefab、Scene、meta/GUID、页面生命周期、多分辨率、资源、GC和平台兼容。不得自行修改后宣布通过。
---

# Unity质量审核

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
- FPS、GC Alloc、内存、DrawCall、加载和释放；
- Windows、macOS、Linux x64/ARM64 的实际证据。

未在目标平台运行的构建只能标记 `NOT_VERIFIED`。
