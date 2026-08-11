---
name: project-bootstrap
description: 首次接管或技术栈发生变化时，从锁文件、工程文件和工具链证据识别B/S及Unity、Qt、.NET桌面、Electron/Tauri、Flutter、Android、Apple原生、React Native、Java桌面、嵌入式HMI等C/S项目的真实语言、运行时、框架、SDK、构建工具、版本、包管理器和子项目，并建立统一.ai状态。不得写死技术版本或用于普通页面修改。
---

# 项目智能初始化

## 使用条件

- 新项目首次使用本套件；
- 旧项目首次接管；
- Monorepo 增加或删除子项目；
- 框架、语言或主要版本发生变化。

## 执行

1. 先运行脚本 [detect_project.py](../../scripts/detect_project.py)，不要凭文件名猜技术栈。
2. 再运行 [bootstrap_project.py](../../scripts/bootstrap_project.py) 写入统一 `.ai` 状态。
3. 输出并核对：
   - 项目根和 Git 根；
   - 每个子项目路径；
   - 语言、运行时、框架、SDK、构建工具、版本、包管理器和测试脚本；
   - 每项版本的证据来源；优先锁文件或已安装清单，其次工程/工具链文件，最后才是声明范围；
   - 未能确定的版本与原因；
   - 需要在线核验的官方文档清单。
4. 不修改业务源码，不自动升级依赖，不替换框架。

## 命令示例

```bash
python3 <plugin-root>/scripts/bootstrap_project.py --root .
```

Windows：

```powershell
py -3 <plugin-root>\scripts\bootstrap_project.py --root .
```

## 完成门禁

- `.ai/schema.json` 存在且协议版本兼容；
- `.ai/context/tech-stack.json` 至少包含一个检测结果或明确标记 unknown；
- 已有 `.ai` 数据未被无理由覆盖；
- 未将“无法确定”写成确定事实。
- 未把任一B/S或C/S技术、版本或最新版写成默认答案。
