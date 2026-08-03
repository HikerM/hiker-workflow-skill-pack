# v1.1.0 脚本说明

所有脚本使用 Python 标准库；`compare_screenshots.py` 额外需要 Pillow。建议 Python 3.10 或更高版本。除初始化、索引、报告和显式写入校验值外，脚本默认只读。任何机器检查都不能替代授权确认、业务判断、人工视觉审查或真实目标环境测试。

## 1. 项目与安装

### `init_project.py`

```bash
python scripts/init_project.py --output <父目录> --project-name <名称> \
  [--source-app <软件名>] [--project-id <ID>] \
  [--reconstruction-mode black_box|gray_box|white_box_migration] \
  [--execution-mode analysis|implementation|automation|mixed] [--force]
```

复制 `assets/project-template`，替换项目令牌，并根据交付检查表生成逐项 `DELIVERABLE_MANIFEST.yaml`。

### `install_skill.py`

```bash
python scripts/install_skill.py \
  [--source <Skill目录>] [--scope user|repo] [--repo-root <仓库>] \
  [--destination <skills根目录>] [--no-backup] [--dry-run] [--json <结果文件>]
```

安装前、暂存后和安装后均执行包校验；默认备份旧版本。不会修改任何重建项目。

## 2. 证据与技术识别

### `index_evidence.py`

```bash
python scripts/index_evidence.py <证据目录> [--output <EVIDENCE_INDEX.csv>]
```

递归建立证据索引，记录相对路径、类型、大小、时间和 SHA-256；不会解析凭据或绕过目标软件保护。

### `detect_project_stack.py`

```bash
python scripts/detect_project_stack.py <源码或安装目录> \
  [--output <JSON>] [--max-depth 8] [--max-files 5000]
```

只读识别 .NET、Node/Electron/Tauri、Rust、Python、Java、C++/Qt、Unity、Go、Flutter、Swift、Unreal 等项目或运行时指纹。二进制指纹只是候选，不等于源语言证明。

### `validate_toolchain.py`

```bash
python scripts/validate_toolchain.py <项目目录> \
  [--json <JSON>] [--report <Markdown>] [--no-fail]
```

验证 G5-T：候选比较、精确版本、POC、平台矩阵、官方文档、依赖锁、许可证/安全状态和可重复构建。它不执行项目定义的任意命令，只运行内置白名单的版本查询。

## 3. 发现、覆盖与追踪

### `validate_discovery.py`

```bash
python scripts/validate_discovery.py <项目目录> [--json <JSON>] [--no-fail]
```

检查独立发现渠道及连续无新增 P0/P1 的饱和轮次。

### `calculate_coverage.py`

```bash
python scripts/calculate_coverage.py <项目目录> \
  [--phase spec|implementation|release] [--json <JSON>] \
  [--allow-conditional] [--no-fail]
```

`--level` 是 `--phase` 的兼容别名。按阶段计算证据、规格、任务、实现、测试设计、测试执行与通过率。

### `validate_traceability.py`

```bash
python scripts/validate_traceability.py <项目目录> \
  [--phase spec|implementation|release] [--json <JSON>] [--no-fail]
```

`--level` 是兼容别名。检查范围到库存、证据、规格、任务、实现、测试、缺陷/豁免和交付物的链路。

### `detect_orphan_items.py`

```bash
python scripts/detect_orphan_items.py <项目目录> \
  [--phase spec|implementation|release] [--json <JSON>] [--no-fail]
```

发现未被追踪的库存、规格、任务、实现、测试、缺陷和交付物引用。

## 4. 视觉和交付

### `compare_screenshots.py`

```bash
python scripts/compare_screenshots.py <基准图> <候选图> \
  [--output <差异图>] [--json <指标JSON>] [--pixel-threshold 10]
```

要求两图尺寸一致。输出基础像素差异，不替代区域几何、动态遮罩、文本、控件和人工视觉验收。

### `validate_deliverables.py`

```bash
python scripts/validate_deliverables.py <项目目录> \
  [--mode analysis|implementation|automation|mixed] \
  [--phase spec|implementation|release] [--write-checksums] \
  [--json <JSON>] [--no-fail]
```

同时读取 `DELIVERABLE_CHECKLIST.csv` 和 `DELIVERABLE_MANIFEST.yaml`，检查模式/阶段、路径安全、文件存在、最小内容、占位符、状态、必需标记和 SHA-256。

## 5. 聚合门禁

### `validate_project.py`

```bash
python scripts/validate_project.py <项目目录> \
  [--profile basic|technology|coverage|implementation|release] \
  [--write-checksums] [--json <JSON>]
```

- `basic`：结构、字段和未替换令牌；
- `technology`：基础 + G5-T；
- `coverage`：基础 + 发现、覆盖、追踪和孤立项；
- `implementation`：技术和实施阶段门禁；
- `release`：全门禁与交付物。

### `run_quality_gates.py`

```bash
python scripts/run_quality_gates.py <项目目录> \
  [--phase spec|technology|implementation|release] \
  [--write-checksums] [--json <JSON>]
```

聚合调用 `validate_project.py` 并生成质量门禁摘要。

## 6. Skill 自检

### `validate_skill_package.py`

```bash
python scripts/validate_skill_package.py <Skill目录或ZIP> \
  [--json <JSON>] [--self-test] [--strict]
```

检查单顶层 ZIP、`SKILL.md` 前置区、VERSION、一致的 OpenAI 元数据、引用文件编号、脚本语法、缓存/临时文件、可疑密钥文件和回归自测。

### `self_test.py`

```bash
python scripts/self_test.py [--skill-root <目录>] [--json <JSON>] [--keep-temp]
```

创建临时正向和负向项目，验证接口契约及门禁不会把缺证据、未锁版本或交付物篡改错误地判为通过。

## 7. 退出码

- `0`：命令成功或门禁通过；
- `1`：脚本正常运行，但门禁不通过；
- `2`：路径、参数、解析或环境错误；
- 个别工具可使用 `3` 表示特定输入问题，例如初始化目录冲突或截图尺寸不一致。

使用 `--no-fail` 时，门禁失败仍写报告并返回 `0`，报告中的 `gate` 仍保持 `FAIL`，不得据此伪造通过。
