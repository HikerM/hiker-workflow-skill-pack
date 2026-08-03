# 从 v1.0.0 迁移到 v1.1.0

## 1. 迁移原则

- 先备份旧项目，不在原目录上直接批量改造；
- 新建 v1.1 项目骨架后迁移真实证据和成果；
- 不把旧版“完成”状态直接复制为 v1.1 的 `PASS`；
- 所有 P0/P1 项重新建立库存、追踪和测试结果；
- 目标技术栈重新执行精确版本与 POC 门禁。

## 2. 新增核心内容

| v1.1 内容 | 作用 |
|---|---|
| `SOURCE_TECH_FINGERPRINT.yaml` | 区分源软件技术证据、候选和未知项 |
| `TARGET_CONSTRAINTS.yaml` | 固化目标平台、架构、性能、安装和维护约束 |
| `TECH_STACK_CANDIDATES.csv` | 比较候选实现路线 |
| `TECH_STACK_LOCK.yaml` | 锁定语言、运行时、SDK、编译器、框架和工具精确版本 |
| `OFFICIAL_DOC_INDEX.csv` | 记录锁定版本对应的官方资料 |
| 完整库存文件 | 覆盖入口、页面、控件、交互、数据、权限、异常和依赖 |
| `DISCOVERY_ROUNDS.csv` | 证明范围内发现趋于饱和 |
| `COVERAGE_MATRIX.csv` | 量化规格、实现和测试覆盖 |
| `TRACEABILITY_MATRIX.csv` | 建立范围到交付物的端到端链路 |
| `DELIVERABLE_CHECKLIST.csv` | 定义不同模式和阶段的必需产物 |
| `DELIVERABLE_MANIFEST.yaml` | 记录产物状态、版本和 SHA-256 |

## 3. 推荐迁移步骤

1. 使用 v1.1 `init_project.py` 创建新目录；
2. 填写授权、项目和范围文件；
3. 复制旧截图、录屏、样例文件和原始性能数据到 `02_evidence/raw/`；
4. 运行 `index_evidence.py`，不要沿用旧证据编号而不校验文件；
5. 将旧页面/功能文档拆解为库存与正式规格；
6. 将旧源码任务映射到 `IMPLEMENTATION_TASKS.csv` 和 `IMPLEMENTATION_INDEX.csv`；
7. 将旧测试迁移到 `TEST_CASES.csv`，补充实际结果与缺陷编号；
8. 重新执行 G4-C、G5-T 和 G9-D；
9. 只有新门禁通过后才更新发布结论。

## 4. Skill 覆盖安装

v1.1 与 v1.0 使用同一内部名称。安装脚本默认把旧目录重命名为时间戳备份，然后安装并再次校验新版本。旧项目数据不会被安装脚本读取或修改。
