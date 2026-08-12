# Hiker 中文工程 Skill 与插件仓库

<!-- repository-facts: repo=0.8.0; engineering=5.6.0; plugins=5; engineering-skills=39; hiker-skills=9; desktop=1.3.0; desktop-skills=5; total-skills=53 -->

这是面向 ChatGPT/Codex 桌面应用和长期软件工程项目的中文能力仓库。

> 仓库版本：`0.8.0`
>
> 当前规模：共 `53` 个 Skill
>
> 自动应用边界：只有“智能工程轻量路由”允许隐式触发；其他能力只由用户手动选择，或由已选择的路由按需加载。

## 当前能力集合

| 能力集合 | 当前版本 | 规模 | 适用范围 | 默认使用方式 |
|---|---:|---:|---|---|
| Hiker 工作流守护包 | 0.8.0 | 9 个 Skill | 结果复核、阶段门禁、证据测试、契约审计、NodeTs 链路、Unity 保护和交付审核 | 手动选择 |
| 智能软件工程平台 | 5.6.0 | 5 个插件、39 个原子 Skill | 从零开发、存量源码接管、B/S、C/S、多会话、大型工程、Git、质量和发布 | 一个轻量自动入口，其余按需加载 |
| 桌面软件等价重建 | 1.3.0 | 5 个 Skill | 已授权桌面软件的发现、技术方案、实现、验证和发布 | 手动选择或手动进入阶段路由 |

三套能力彼此独立，不会因为安装在同一仓库就同时进入每轮会话。详细清单见 [全部 Skill 索引](docs/SKILL_INDEX.md)。

## 智能软件工程平台 5.6.0

这是当前主要的 ChatGPT/Codex 桌面端软件工程插件套件。它使用一个小型入口识别项目模式、真实技术栈、版本和当前阶段，每轮最多加载两个直接相关的原子 Skill，不预读完整能力目录。

### 五个中文插件

| 插件名称 | 原子 Skill | 主要职责 |
|---|---:|---|
| 智能工程核心 | 8 | 轻量路由、项目初始化、从零需求融合、存量源码需求对账、有界上下文、压缩恢复和可中断控制 |
| 浏览器端与服务端工程 | 8 | 非模板化界面设计系统、浏览器端实现、服务端技术识别、API/事件契约、数据库迁移、功能实现与质量审核 |
| 客户端工程 | 7 | Unity、Qt、.NET 桌面、Electron/Tauri、Flutter、Android、Apple 原生、React Native、Java 桌面和嵌入式 HMI |
| 工作区与多会话协作 | 11 | 大型工程总控、项目状态、任务生命周期、文件锁、多项目隔离、Worktree、合并控制和功能验收闭环 |
| 质量、风险与发布 | 5 | 独立设计就绪复审、完整变更风险、工程图谱、回归范围和发布就绪审核 |

### 5.6 的关键能力

- **唯一源码身份**：Git 项目只使用已跟踪工程清单识别技术栈；旧副本、嵌套 Worktree 和未登记源码不会污染判断。
- **Worktree 安全收敛**：快速清单不扫描源码；历史 Worktree 先登记、分类，再经过计划与确认两阶段关闭，禁止批量强制删除。
- **合并后必须收敛**：任务合并后先进入待清理状态，对应 Worktree 安全关闭后才算正式完成。
- **从零开发先融合需求**：先建立稳定需求 ID、冲突、未知项、验收条件和技术 Checkpoint，再选择技术方案和生成代码。
- **存量源码先对账**：先以代码和测试证据建立现有能力基线，再把需求分为新增、修改、替换或移除，禁止无依据重建脚手架。
- **B/S 与通用 C/S**：从工程证据识别真实框架、运行时和版本；证据不足明确返回 unknown，不默认最新版，也不把 Unity 当成全部 C/S。
- **防止大型项目失控**：每个 Task 声明允许范围、原有行为不变量、消费者和最低回归；公共表面、依赖方向、文件增长与合并债务受门禁保护。
- **多会话有界记忆**：完整需求、决定、任务和证据落入项目 `.ai` 状态；会话只加载当前工作集和必要 Checkpoint，不重复注入完整聊天历史。
- **中文透明回执**：实际执行前只显示本轮真正应用的中文插件名称和中文 Skill 名称，不显示内部分类、未使用项或英文内部标识。

### 自动应用规则

只有“智能工程轻量路由”参与全局自动选择。它按确定性规则完成轻量识别，并最多加载两个原子 Skill。其他插件和 Skill 不会因为已安装就自动进入上下文。

自动应用不会扩大权限。未经用户明确授权，不会自动：

- 修改 `main`；
- push、merge、部署或发布；
- 写入生产数据；
- 删除源码、分支或 Worktree；
- 强制清理未确认的历史工作目录。

### ChatGPT/Codex 桌面端安装

```powershell
cd .\skill-groups\ai-software-engineering-platform-enterprise
py -3 -B .\install_personal.py
```

安装器会：

1. 复制五个插件到桌面端插件目录；
2. 注册个人 Marketplace；
3. 合并托管的全局轻量路由与中文回执规则；
4. 启用五个插件；
5. 校验仓库源码、安装目录和版本缓存哈希一致性；
6. 保留安装前备份，并限制历史缓存增长。

安装输出同时满足以下条件才算成功：

```text
ok=true
plugin_activation.status=activated
verification.ok=true
```

再次核验：

```powershell
py -3 -B .\tools\verify_desktop_install.py
```

新建桌面任务即可加载当前版本；只有新任务仍显示旧注册时才需要重启应用。完整说明见 [安装指南](docs/INSTALLATION.md)。

## Hiker 工作流守护包 0.8.0

该能力包面向具体项目安装，负责判断“任务是否真的完成”，不会替代具体框架开发。它覆盖结果复核、阶段门禁、证据优先测试、契约边界、NodeTs 执行链、Unity 高风险资产、文件交付质量和架构咨询。

先查看安装计划：

```powershell
.\INSTALL.ps1 -TargetRoot C:\path\to\project -DryRun
```

确认后安装全部 9 个 Skill：

```powershell
.\INSTALL.ps1 -TargetRoot C:\path\to\project -Apply -Backup -Skills all -MergeAgents
```

安装器默认 Dry Run，不会自动覆盖项目已有 `AGENTS.md`；托管区块、备份、卸载和恢复方式见 [安装指南](docs/INSTALLATION.md)。

## 桌面软件等价重建 1.3.0

该能力包用于获得合法授权的 Windows、macOS 或 Linux 桌面软件重建。它按发现、技术方案、实现、验证与发布阶段工作，要求证据分级、版本锁定、视觉与功能差分、性能验证、安装升级、迁移和回滚。

它不能用于破解许可证、绕过登录或 DRM、窃取源码、密钥或凭据，也不能把未经验证的推断写成“完全一致”。

用户级安装：

```powershell
cd .\skill-groups\desktop-app-reconstruction-zh
py -3 -B .\scripts\install_skill.py --scope user
```

## 仓库结构

```text
.
├─ .agents/skills/                                  # Hiker 工作流守护包：9 个 Skill
├─ skill-groups/
│  ├─ ai-software-engineering-platform-enterprise/ # 智能软件工程平台：5 个插件、39 个原子 Skill
│  └─ desktop-app-reconstruction-zh/                # 桌面软件等价重建：5 个 Skill
├─ docs/
│  ├─ SKILL_INDEX.md                                # 全部 53 个 Skill 索引
│  ├─ THREE_SKILL_GROUPS_ZH.md                      # 三套能力的详细中文说明
│  ├─ INSTALLATION.md                               # 安装、更新和生效方式
│  ├─ USAGE.md                                      # 示例指令
│  └─ SAFETY_RULES.md                               # 安全边界
├─ scripts/validate_skills.py                       # 根包与公开文档一致性验证
├─ INSTALL.ps1
├─ UNINSTALL.ps1
└─ VALIDATE.ps1
```

## 验证

在仓库根目录运行：

```powershell
.\VALIDATE.ps1 -Root .
```

验证覆盖：

- 9 个工作流守护 Skill 的结构与安全默认值；
- 5 个工程插件、39 个原子 Skill、中文可见名称、轻量路由和行为 Eval；
- 5 个桌面重建 Skill 的阶段资源与包完整性；
- 根 README 中的仓库版本、插件版本、数量和总 Skill 数是否与真实清单一致；
- 公开安装和说明文档是否残留已经失效的版本与数量。

## 版本与发布记录

- [仓库 Changelog](CHANGELOG.md)
- [智能软件工程平台 Changelog](skill-groups/ai-software-engineering-platform-enterprise/CHANGELOG.md)
- [智能软件工程平台 5.6 验证报告](skill-groups/ai-software-engineering-platform-enterprise/VALIDATION_REPORT_CN.md)
- [发布包哈希](skill-groups/ai-software-engineering-platform-enterprise/SHA256SUMS.txt)
