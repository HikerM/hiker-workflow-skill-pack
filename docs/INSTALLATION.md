# 安装指南

仓库只包含“智能软件工程平台”和“桌面软件等价重建”。两者独立安装，不要把插件目录平铺复制，也不要把桌面重建的参考、脚本和模板拆散。

<!-- engineering-current-facts: version=5.18.0; plugins=5; skills=42; tests=309 -->

## 智能软件工程平台 5.18.0

Hiker Engineering Capability System（Hiker 工程能力系统）运行在 ChatGPT Desktop / Codex 提供的 Agent Runtime 之上；它不是独立 Runtime，也不接入第二个模型。当前工程套件包含 5 个插件、42 个 Skill，发布源码对应 309 项源码测试。它是普通软件工程任务唯一允许自动进入的能力包。

```powershell
Set-Location .\skill-groups\ai-software-engineering-platform-enterprise
py -3 -B .\install_personal.py
py -3 -B .\tools\verify_desktop_install.py
```

安装器会备份并更新个人 Marketplace、插件源码、桌面端启用配置、版本缓存和全局轻量路由规则。重复执行是幂等更新。安装后必须以验证脚本显示的版本为准；新任务会从最新安装读取能力，已打开任务须先保存 Checkpoint，再显式重新载入能力或由新任务接管。宿主若仍持有旧任务缓存，应刷新对应任务；不要用“文件已复制”冒充任务已经切换版本。

## 桌面软件等价重建 1.3

仅在用户明确选择桌面等价重建时使用。

```powershell
Set-Location .\skill-groups\desktop-app-reconstruction-zh
.\INSTALL_WINDOWS.ps1 -Scope user
```

macOS/Linux 使用同目录的 `INSTALL_MAC_LINUX.sh`。项目级安装使用 `-Scope repo -RepoRoot <路径>`。

## 安装前验证

```powershell
.\VALIDATE.ps1
```

验证失败时不要复制缓存或发布。公开仓库只允许 Hiker 作为作者标识，不得包含个人、公司、真实项目、会话、凭据或本机路径。

`release-versions.json` 是仓库、工程平台和桌面重建版本的唯一发布版本源。执行 `python scripts/audit_release_facts.py --root . --sync` 可据此同步 `VERSION`、五个 Manifest 和当前文档事实；同步不会自动升版。测试数量、任务生命周期、ZIP 内容与 checksum 仍从当前源码和候选包确定性推导，CHANGELOG 等历史记录及带分类标记的 Checkpoint 不会被误当成当前版本说明。

Hiker 自身的发布前门禁统一由以下命令执行：

```powershell
python skill-groups/ai-software-engineering-platform-enterprise/tools/self_governance.py --root .
```

固定顺序为 Architecture → Privacy → Version Facts → Tests → Performance → Package Facts → Release Gate。任一阶段 `BLOCKED` 时，后续阶段标记为 `NOT_RUN`，`package_release.py` 不得构建或写入正式 `dist`；候选包必须先在临时目录通过逐文件源码哈希、ZIP 完整性和 `SHA256SUMS.txt` 精确校验，才允许发布器写入正式目录。
