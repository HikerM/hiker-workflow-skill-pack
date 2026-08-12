# 三组 Skill 安装指南

三组 Skill 的封装形式不同，必须分别安装。不要把第二组的插件 Skill 平铺复制到第一组目录，也不要拆散第三组的脚本、参考文件和模板。

安装后只有第二组 `ai-engineering-router` 参与全局自动选择；第一组和第三组保留在手动列表中，只有用户明确点名时才运行。

## 第一组：Hiker 工作流守护 Skill Pack

### 推荐范围

安装到具体项目，而不是默认覆盖全局配置。目标位置为：

```text
<project>/.agents/skills/
```

### Dry Run

```powershell
.\INSTALL.ps1 -TargetRoot C:\path\to\project -DryRun
```

### 安装核心 Skill

```powershell
.\INSTALL.ps1 -TargetRoot C:\path\to\project -Apply -Backup -Skills core -MergeAgents
```

### 安装全部 9 个 Skill

```powershell
.\INSTALL.ps1 -TargetRoot C:\path\to\project -Apply -Backup -Skills all -MergeAgents
```

### 安装指定 Skill

```powershell
.\INSTALL.ps1 `
  -TargetRoot C:\path\to\project `
  -Apply -Backup `
  -Skills codex-thread-review,project-phase-review,evidence-first-testing `
  -MergeAgents
```

### 参数说明

- `-TargetRoot`：目标项目根目录，必填。
- `-DryRun`：只显示计划；未传 `-Apply` 时默认也是 Dry Run。
- `-Apply`：允许实际写入。
- `-Skills core|all|comma-list`：选择核心、全部或指定 Skill。
- `-MergeAgents`：只追加或替换带标记的 Hiker `AGENTS.md` 区块。
- `-Force`：允许覆盖同名 Skill；非必要不使用。

安装器会在以下位置创建备份：

```text
<project>/.backups/hiker-workflow-pack/<timestamp>/
```

卸载或恢复：

```powershell
.\UNINSTALL.ps1 -TargetRoot C:\path\to\project -DryRun
.\UNINSTALL.ps1 -TargetRoot C:\path\to\project -Apply
.\UNINSTALL.ps1 -TargetRoot C:\path\to\project -Apply -RestoreBackup 20260624-210000
```

## 智能软件工程平台 5.7

### 推荐范围

这是 ChatGPT/Codex 桌面应用的个人插件套件，包含5个插件和40个Skill。个人安装器默认完成注册、全局轻量路由、桌面端启用、版本缓存和三层哈希核验。

1. 复制插件并注册个人 Marketplace；
2. 安全合并全局自动应用与插件回执规则；
3. 从该 Marketplace 安装并启用 5 个插件；
4. 校验源码、安装目录、版本缓存、启用配置和全局规则一致性。

### 第一步：注册个人 Marketplace

```powershell
cd .\skill-groups\ai-software-engineering-platform-enterprise
py -3 -B .\install_personal.py
```

该命令会：

- 复制插件到 `~/.codex/plugins/`；
- 合并 `~/.agents/plugins/marketplace.json`；
- 保留其他 Marketplace 条目；
- 更新同名插件时创建备份；
- 默认安全合并并备份 `~/.codex/AGENTS.md`；
- 直接写入桌面端启用配置并生成安装状态快照；CLI只作显式旧版兼容。

安装输出中的 `plugin_activation.status=activated` 且 `verification.ok=true` 才表示桌面端安装完成。可用 `--no-merge-global-agents` 退出全局规则，或用 `--no-activate-plugins` 只注册Marketplace。

### 第二步：确认5个插件已启用

新版安装器默认自动完成本步骤。仅当输出为 `manual-required` 时执行：

```powershell
codex plugin add ai-engineering-core@personal-ai-engineering-marketplace --json
codex plugin add ai-engineering-web@personal-ai-engineering-marketplace --json
codex plugin add ai-engineering-unity@personal-ai-engineering-marketplace --json
codex plugin add ai-engineering-workspace@personal-ai-engineering-marketplace --json
codex plugin add ai-engineering-quality@personal-ai-engineering-marketplace --json
```

也可以重启 ChatGPT 桌面应用，在 **Work 或 Codex → Plugins → Personal / 个人插件** 中逐个点击安装。全局自动选择与应用回执默认已由安装器写入；只有使用 `--no-merge-global-agents` 时才需要手工合并模板。

验证状态：

```powershell
codex plugin marketplace list --json
codex plugin list --available --json
```

五个插件的目标状态应为：

```text
installed: true
enabled: true
```

`ai-engineering-core` 和 `ai-engineering-workspace` 保留状态与工作区事件脚本，但当前插件 manifest 不注册已不受支持的 `hooks` 字段，因此不会出现 Hook 信任步骤。相关脚本由 Skill 或外部编排显式调用。

### 项目级安装

如果只想把插件 Marketplace 放入具体仓库：

```powershell
py -3 -B .\install_repo.py C:\path\to\repository
```

这会写入目标仓库的 `plugins/` 和 `.agents/plugins/marketplace.json`，不会修改用户级 Marketplace。

## 桌面软件等价重建 1.3

### 用户级安装

```powershell
cd .\skill-groups\desktop-app-reconstruction-zh
py -3 -B .\scripts\install_skill.py --scope user
```

目标位置：

```text
~/.agents/skills/desktop-app-reconstruction-zh/
```

使用 `-B` 是为了禁止 Python 生成 `__pycache__`，确保安装前的包结构校验保持干净。

### 项目级安装

```powershell
py -3 -B .\scripts\install_skill.py `
  --scope repo `
  --repo-root C:\path\to\repository
```

目标位置：

```text
<repository>/.agents/skills/desktop-app-reconstruction-zh/
```

### 只校验不安装

```powershell
py -3 -B .\scripts\install_skill.py --scope user --dry-run
```

安装器会执行源目录校验、暂存副本校验和安装后校验；已有版本默认备份，不静默覆盖。

## 仓库整体校验

在仓库根目录运行：

```powershell
.\VALIDATE.ps1 -Root .
```

该命令会验证：

- 第一组的包文件、9 个 Skill 和安全默认值；
- 智能软件工程平台的5个插件、40个Skill、清单和目录结构；
- 第三组的 Skill 元数据、脚本、参考资料、模板和包完整性。

## 生效时机

- Skill 文件更新后通常在新任务中生效；如果没有出现，重启桌面应用。
- 插件安装后必须新建任务，旧任务不会动态重新加载全部插件能力。
- 插件只在 ChatGPT Work、ChatGPT 桌面端 Codex 或 Codex CLI 的支持界面中出现；普通 Chat、移动端和 IDE 扩展不显示插件。
