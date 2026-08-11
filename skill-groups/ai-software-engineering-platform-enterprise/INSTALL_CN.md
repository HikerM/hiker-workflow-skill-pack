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
4. 默认安全合并并备份 `~/.codex/AGENTS.md` 中的自动应用与插件回执规则；
5. 自动发现 Codex CLI 并安装启用五个插件；
6. 输出结构化安装、启用和后续操作结果。

安装输出中的 `plugin_activation.status` 为 `activated` 才表示五个插件已经自动启用。若为 `manual-required`，执行输出中的 `manual_commands`。完成后重启 ChatGPT 桌面端并新建任务。

可选参数：

```powershell
# 不修改全局AGENTS.md
py -3 -B .\install_personal.py --no-merge-global-agents

# 只注册Marketplace，不调用Codex CLI
py -3 -B .\install_personal.py --no-activate-plugins

# 显式指定桌面端Codex CLI
py -3 -B .\install_personal.py --codex-cli C:\path\to\codex.exe
```

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

## 状态脚本

核心插件和工作区插件包含状态快照、恢复和工作区事件脚本。当前 Codex 插件规范不接受 manifest 中的 `hooks` 字段，因此安装后不会出现 Hook 信任步骤，也不会自动注册生命周期事件。脚本由对应 Skill 或外部编排显式调用，只在当前项目目录写入 `.ai/` 或 Git 公共目录中的 AI 工作区状态，不执行网络请求。

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
codex plugin marketplace add /absolute/path/to/ai-software-engineering-platform-enterprise
```

然后重启桌面端，从“AI软件工程平台 Enterprise 5.0”来源安装所需插件。

## 全局自动应用与应用回执

个人安装器默认把 `templates/GLOBAL_AGENTS_AI_ENGINEERING.md` 中带标记的区块合并到 `C:\Users\<用户名>\.codex\AGENTS.md`。之后软件工程任务会自动选择最小必要插件/Skill，并在开始和结束时展示实际应用项、触发原因、项目和执行模式。安装器只替换 `ai-engineering-global-governance` 标记区块，禁止覆盖用户已有全局规则。

自动选择不意味着自动获得外部写权限；push、merge、部署、发布和生产数据写入仍按用户授权与门禁执行。

这里的“显示”是任务对话中的文本回执，不是桌面插件列表新增一个实时监控徽章。插件列表显示安装/启用状态，应用回执显示本次任务实际采用的插件和Skill。
