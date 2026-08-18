# 安装指南

仓库只包含“智能软件工程平台”和“桌面软件等价重建”。两者独立安装，不要把插件目录平铺复制，也不要把桌面重建的参考、脚本和模板拆散。

## 智能软件工程平台 5.14

包含5个插件和42个Skill。它是普通软件工程任务唯一允许自动进入的能力包。

```powershell
Set-Location .\skill-groups\ai-software-engineering-platform-enterprise
py -3 -B .\install_personal.py
py -3 -B .\tools\verify_desktop_install.py
```

安装器会备份并更新个人 Marketplace、插件源码、桌面端启用配置、版本缓存和全局轻量路由规则。重复执行是幂等更新。安装完成后，新任务立即使用最新能力；已打开任务需要重新载入能力或新建任务，不必重启整个桌面应用。

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
