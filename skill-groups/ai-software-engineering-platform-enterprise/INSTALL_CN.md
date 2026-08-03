# 安装说明

## 支持范围

插件可用于 ChatGPT 桌面端的 **Work** 或 **Codex**，以及 Codex CLI 的插件浏览器。普通 Chat、移动端和 IDE 扩展不提供插件安装入口。

## 方法一：个人 Marketplace（推荐）

解压后运行：

```bash
python install_personal.py
```

Windows：

```powershell
py -3 .\install_personal.py
```

脚本会：

1. 将 5 个插件复制到 `~/.codex/plugins/`；
2. 备份并合并 `~/.agents/plugins/marketplace.json`；
3. 不覆盖其他 Marketplace 条目；
4. 输出安装结果。

完成后重启 ChatGPT 桌面端，进入 **Work 或 Codex → Plugins** 安装需要的插件。

## 方法二：安装到具体仓库

在解压目录运行：

```bash
python install_repo.py /path/to/your/repository
```

它会复制到：

```text
<repo>/plugins/
<repo>/.agents/plugins/marketplace.json
```

## Hook 信任

核心插件和工作区插件包含生命周期 Hook。安装/更新后，Codex 会要求审查并信任 Hook；未信任前 Hook 会被跳过。Hook 只在当前项目目录写入 `.ai/` 或 Git 公共目录中的 AI 工作区状态，不执行网络请求。

## 第一次使用

新建 Codex 会话后显式调用：

```text
@项目智能初始化
读取当前工程，识别真实语言、框架、版本、包管理器和子项目，建立 .ai 状态，不修改业务源码。
```

然后按项目类型启用 B/S 或 Unity 插件。

## CLI添加本地Marketplace

解压后也可以在终端运行：

```bash
codex plugin marketplace add /absolute/path/to/AI-Software-Engineering-Platform-Enterprise-4.0-Converged
```

然后重启桌面端，从“AI软件工程平台 Enterprise 4.0”来源安装所需插件。
