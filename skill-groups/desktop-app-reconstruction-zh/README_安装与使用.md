# 桌面软件等价重建 Skill：安装与使用

版本：1.3.0
语言：简体中文  
适用：ChatGPT 桌面端独立 Skill、Codex 用户级 Skill、Codex 项目级 Skill

> 1.3.0 采用“唯一隐式轻量总路由 + 4 个手动可见原子 Skill”。单次任务只由总路由懒加载当前门禁对应的一个阶段能力；备份保存在不可发现的 `skills-backup`，不会重复进入选择候选。

## 一、v1.3.0 解决什么问题

本 Skill 用于在已获授权的范围内，根据桌面软件的截图、录屏、可运行程序、样例数据、接口资料或既有源码，建立证据驱动的独立重建工程。它不把“做出几个相似页面”当作完成，而是强制处理三类核心问题：

1. **编程语言与版本**：分离原软件技术指纹和目标实现技术栈；目标语言、运行时、SDK、编译器、UI 框架、构建工具、安装器及依赖必须锁定精确版本并通过代表性 POC。
2. **功能、交互与性能完整性**：建立入口、窗口、页面、控件、交互、功能、数据、权限、异常、外部依赖和性能库存，通过发现饱和、覆盖率、追踪链和孤立项检查阻止遗漏。
3. **输出与交付**：按资料分析、代码实施、自动观测或混合模式生成不同产物，并用交付物清单、文件状态和 SHA-256 检查“声称完成但文件不存在”的问题。

完整阶段为：

```text
G0 授权与范围
→ G1 环境与证据
→ G1-T 原软件技术指纹
→ G2/G3 UI、入口和交互
→ G4-C 功能与覆盖完整性
→ G5-T 目标技术栈与精确版本
→ G6 实现
→ G7/G8 差分、性能和稳定性
→ G9-D 打包与交付物完整性
```

## 二、ChatGPT 桌面端安装

独立 Skills 可在 ChatGPT 桌面端使用。不同账号、版本和工作区看到的管理入口可能不同，因此按当前客户端实际界面操作：

1. 打开 ChatGPT 桌面端的 Skills 管理或创建入口；
2. 若界面提供“从电脑导入／上传 Skill”，选择整个 `desktop-app-reconstruction-zh-v1.3.0.zip`，不要只上传 `SKILL.md`；
3. 若当前客户端未显示本地导入入口，使用下方 Codex 用户级或项目级安装方式；
4. 安装或启用后，在新会话输入 `@`，选择 **桌面软件等价重建**；
5. 出现脚本或权限审查时，先查看本包的 `scripts/README.md`、安装脚本及权限范围，再决定是否启用。

安装包采用单一顶层目录：

```text
desktop-app-reconstruction-zh/
├── SKILL.md
├── agents/
├── references/
├── assets/
├── scripts/
└── evals/
```

## 三、Codex 安装

### 1. 用户级安装

解压 ZIP 后，在 Skill 根目录执行：

**Windows PowerShell**

```powershell
.\INSTALL_WINDOWS.ps1 -Scope user
```

**macOS / Linux**

```bash
./INSTALL_MAC_LINUX.sh --scope user
```

默认目标：

- Windows：`%USERPROFILE%\.agents\skills\desktop-app-reconstruction-zh`
- macOS / Linux：`~/.agents/skills/desktop-app-reconstruction-zh`

### 2. 项目级安装

**Windows PowerShell**

```powershell
.\INSTALL_WINDOWS.ps1 -Scope repo -RepoRoot "D:\项目目录"
```

**macOS / Linux**

```bash
./INSTALL_MAC_LINUX.sh --scope repo --repo-root /path/to/project
```

最终目录：

```text
项目根目录/.agents/skills/desktop-app-reconstruction-zh/
```

安装脚本会先校验源 Skill，再复制到暂存目录、二次校验并原子替换；覆盖旧版本时默认保留时间戳备份。只查看安装位置而不写入：

```powershell
.\INSTALL_WINDOWS.ps1 -Scope user -DryRun
```

```bash
./INSTALL_MAC_LINUX.sh --scope user --dry-run
```

也可直接复制完整目录，不得遗漏 `references`、`assets/project-template` 或 `scripts`。

## 四、从 v1.0.0 升级

主路由内部名称仍为 `desktop-app-reconstruction-zh`，因此 v1.3.0 可以覆盖旧版。安装脚本默认把旧版备份到 `.agents/skills-backup/`，并安装4个阶段原子Skill。

旧的重建项目不会被自动改写。处理旧项目时：

1. 先备份旧项目；
2. 使用 v1.3.0 初始化一个新项目骨架；
3. 迁移原证据、规格、源码和测试；
4. 补齐新库存、精确版本锁、覆盖矩阵、追踪矩阵和交付物清单；
5. 运行 v1.3.0 门禁，未通过前不要沿用旧版“完成”结论。

详细映射见 `MIGRATION_v1.0_to_v1.1.md`。

## 五、第一次使用

```text
@桌面软件等价重建

开始新项目。
目标：在已获授权范围内，对一个 Windows 桌面软件进行独立等价重建。
当前材料：安装包、主要页面截图、操作录屏、测试账号和样例文件。
目标平台：Windows 10 / Windows 11 x64。
要求：先冻结授权和范围，再建立证据、原软件技术指纹、完整库存和目标技术候选；未经 G4-C 与 G5-T 门禁，不进入大规模正式编码。
```

有现有源码时：

```text
@桌面软件等价重建
读取当前源码工程和项目状态。
先自动识别现有语言、框架、运行时、SDK、构建工具和锁文件，并区分“直接证据”和“推断”。
随后根据目标平台、性能、安装、离线和维护约束完成技术候选比较与精确版本锁定。
```

继续项目时：

```text
@桌面软件等价重建
继续。读取 00_control/STATUS.yaml，从当前未通过门禁开始，不重做已完成阶段。
```

## 六、四种运行模式

| 模式 | 可用材料/工具 | 主要输出 |
|---|---|---|
| 资料分析 | 截图、录屏、文档、样例文件 | 证据、库存、规格、缺口、技术候选、测试与实施任务 |
| 代码实施 | 可读写源码工程 | 上述内容，加源码、依赖锁、迁移、自动化测试和构建脚本 |
| 自动观测 | 桌面自动化、Computer Use 或 MCP | 自动操作记录、控件树、截图、文件差分和性能样本 |
| 混合 | 资料、代码和自动观测同时存在 | 从原软件观测到候选软件回归的完整闭环 |

仅安装 Skill 不会自动获得鼠标、键盘、窗口、进程或文件系统权限。没有桌面工具时，Skill 必须切换为资料分析模式，不能声称已自动点击或测量目标软件。

## 七、如何锁定编程语言与版本

### 原软件技术指纹

- 有源码时，从项目文件、清单、锁文件、CI、构建脚本和工具链文件识别；
- 只有安装包或二进制时，只输出候选技术、证据、置信度和限制；
- 黑盒情况下，无法证明内部精确语言版本时必须保留 `UNKNOWN`，不得猜测成事实。

只读探测：

```bash
python scripts/detect_project_stack.py <源码或安装目录> --json detected-stack.json
```

### 目标实现技术栈

目标技术不必与原软件相同。Skill 会基于目标 OS、CPU 架构、UI 复杂度、GPU/多媒体、系统集成、离线、性能、安装、团队能力、生命周期和许可证比较候选路线，并要求：

- 至少一个代表性核心页面 POC；
- 文件或数据读写；
- DPI 和窗口缩放；
- 冷启动与内存采样；
- 目标平台构建和安装；
- 精确版本与依赖锁；
- 对应锁定版本的官方文档索引；
- 可重复构建证据。

技术门禁：

```bash
python scripts/validate_toolchain.py <重建项目目录>
```

最终锁文件位于：

```text
05_technical_design/TECH_STACK_LOCK.yaml
```

最终值不得使用 `latest`、`stable`、`LTS`、`*` 或未解析的版本范围。

## 八、如何检查功能、交互和性能遗漏

Skill 不承诺发现一个从未暴露、无入口、无账号权限、无文档且无法触发的隐藏功能。它保证的是：在冻结范围内，所有已知项都有唯一 ID 和完整追踪链，残余未知必须进入风险报告。

完整链路：

```text
范围
→ 入口/页面/控件/交互/功能/数据/性能库存
→ 证据
→ 规格
→ 实施任务
→ 源码/配置
→ 测试
→ 实际结果
→ 缺陷或豁免
→ 交付物
```

四项覆盖检查：

```bash
python scripts/validate_discovery.py <项目目录>
python scripts/calculate_coverage.py <项目目录> --phase spec
python scripts/validate_traceability.py <项目目录> --phase spec
python scripts/detect_orphan_items.py <项目目录> --phase spec
```

实施阶段将 `--phase` 改为 `implementation`；发布阶段改为 `release`。发布时 P0/P1 要求 100% 完整追踪、100% 执行通过、开放 P0/P1 缺陷为零。

性能不是单独写一句“流畅”，而是把每个核心性能场景关联到功能、数据规模、硬件环境、缓存状态、原软件基线和候选结果，记录 P50/P95/P99、CPU、内存、GPU、磁盘、网络和长稳数据。

## 九、软件反推重建会输出什么

### 资料分析模式

- 授权和范围；
- 环境、证据和原软件技术指纹；
- 入口、窗口、页面、控件、交互、功能、数据、权限、异常和性能库存；
- 页面、交互、功能、数据、权限、错误与性能规格；
- 技术候选、POC 计划、精确版本锁定方案；
- 覆盖、追踪、缺口、残余未知风险、测试计划和实施任务。

### 代码实施模式

在资料模式基础上增加：正式源码、资源、配置、数据库迁移、外部接口适配、依赖锁、单元/集成/UI 自动化测试、构建脚本及工程文档。

### 自动观测/混合模式

增加：操作重放脚本、控件树快照、基准截图/录屏、文件/配置/日志差分、性能原始样本、自动差分和长稳记录。

### 发布交付

增加：安装包、升级和卸载、迁移与回滚、SBOM、许可证清单、校验值、用户/管理员/维护手册及发布准备报告。

完整目录见 `references/11_输出协议.md`。

## 十、初始化标准项目

需要 Python 3.10 或更高版本。

```bash
python scripts/init_project.py \
  --output ./workspace \
  --project-name "项目名称" \
  --source-app "目标软件" \
  --reconstruction-mode black_box \
  --execution-mode mixed
```

项目目录由控制、环境、证据、库存、规格、技术设计、实现、测试、构建、报告和交付十一部分组成。

证据入库：

```bash
python scripts/index_evidence.py ./workspace/项目名称/02_evidence/raw
```

基础结构检查：

```bash
python scripts/validate_project.py ./workspace/项目名称 --profile basic
```

聚合门禁：

```bash
python scripts/run_quality_gates.py ./workspace/项目名称 --phase spec
python scripts/run_quality_gates.py ./workspace/项目名称 --phase technology
python scripts/run_quality_gates.py ./workspace/项目名称 --phase implementation
python scripts/run_quality_gates.py ./workspace/项目名称 --phase release --write-checksums
```

## 十一、Skill 包自检

目录自检并执行回归测试：

```bash
python scripts/validate_skill_package.py . --self-test
```

ZIP 自检：

```bash
python scripts/validate_skill_package.py desktop-app-reconstruction-zh-v1.3.0.zip --self-test
```

独立回归自测：

```bash
python scripts/self_test.py --json self-test.json
```

自测包含正向和负向用例：空项目必须被覆盖/技术/发布门禁拒绝；完整最小项目必须通过；交付物被篡改后必须失败。自测只证明脚本闭环，不证明某个真实软件已重建完成。

## 十二、常用中文命令

```text
开始新项目
盘点现有材料
自动识别工程技术栈
分析原软件技术指纹
锁定编程语言和精确版本
反推这个页面
反推这个功能
检查功能、交互和性能有没有遗漏
生成追踪矩阵
进入正式实现
执行差分验收
执行全门禁
生成完整交付包
继续
```

## 十三、安全边界

本 Skill 适用于经授权的内部迁移、兼容替代、互操作实现、自有产品重构和 clean-room 独立实现。它不用于：

- 绕过许可证、激活、登录、DRM、付费或安全机制；
- 提取源码、密钥、令牌、凭据或未授权数据；
- 隐蔽监控键盘、屏幕或用户行为；
- 冒充原厂或复制无授权商标、字体、图片、音频、模型等资产；
- 通过删除失败测试、降低优先级或伪造文件状态制造“通过”。

脚本默认只处理用户明确指定的目录；工具链验证不执行项目自带的任意命令，只调用固定白名单的版本查询命令。
