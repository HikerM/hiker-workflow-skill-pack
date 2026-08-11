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
2. 原子写入 `~/.codex/plugins/cache/<Marketplace>/<插件>/<版本>/`，同版本覆盖前保留缓存备份，避免必须等待桌面端自行刷新；
3. 备份并合并 `~/.agents/plugins/marketplace.json`；
4. 不覆盖其他 Marketplace 条目；
5. 默认安全合并并备份 `~/.codex/AGENTS.md` 中的自动应用与插件回执规则；
6. 默认直接写入 ChatGPT/Codex 桌面端的五个 `[plugins] enabled = true` 配置，不依赖 CLI；只有显式传入 `--codex-cli` 时才尝试兼容旧版命令；
7. 对源目录、安装目录、版本缓存、启用配置和全局规则做逐插件哈希核验，并写入 `~/.codex/plugin-install-state.json`；
8. 输出结构化安装、缓存、启用、核验和后续操作结果。

安装输出中的 `plugin_activation.status=activated`、`method=desktop-config` 且 `verification.ok=true` 表示桌面端启用状态与三层文件已一致；旧版显式兼容时也可能显示 `method=cli`。完成后新建任务以创建新的能力快照；只有新任务仍显示旧版本时才需要重启桌面端。

可选参数：

```powershell
# 不修改全局AGENTS.md
py -3 -B .\install_personal.py --no-merge-global-agents

# 只注册Marketplace，不启用桌面端插件配置
py -3 -B .\install_personal.py --no-activate-plugins

# 仅兼容仍支持 plugin add 的旧版CLI；桌面端通常不需要
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

重启并新建 Codex 任务后，软件工程请求会先进入唯一轻量入口。也可以显式调用：

```text
@AI工程轻量路由
识别当前是0→1还是已有工程，只加载最多两个直接相关原子Skill并显示应用回执。
```

空项目会先建立需求账本和技术决策 Checkpoint；已有项目才识别真实技术栈。无需手动同时选择多个插件。

## CLI添加本地Marketplace

解压后也可以在终端运行：

```bash
codex plugin marketplace add /absolute/path/to/ai-software-engineering-platform-enterprise
```

然后新建任务并从个人工程插件来源检查所需插件；若列表仍显示旧版本，再重启桌面端。

## 全局自动应用与应用回执

个人安装器默认把 `templates/GLOBAL_AGENTS_AI_ENGINEERING.md` 中带标记的区块合并到 `C:\Users\<用户名>\.codex\AGENTS.md`。之后软件工程任务只自动进入“智能工程轻量路由”，正常回执仅显示实际应用的中文插件名称和中文 Skill 名称；其他入口只有手动点名才启用。安装器只替换自己的标记区块，禁止覆盖用户已有全局规则。

自动选择不意味着自动获得外部写权限；push、merge、部署、发布和生产数据写入仍按用户授权与门禁执行。

这里的“显示”是任务对话中的文本回执，不是桌面插件列表新增一个实时监控徽章。插件列表显示安装/启用状态，应用回执显示本次任务实际采用的插件和Skill。
