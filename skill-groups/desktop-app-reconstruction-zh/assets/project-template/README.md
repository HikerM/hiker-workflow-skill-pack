<!-- document_status: DRAFT -->
# {{PROJECT_NAME}}

项目 ID：{{PROJECT_ID}}  
源软件：{{SOURCE_APP_NAME}}  
执行模式：{{EXECUTION_MODE}}

这是由“桌面软件等价重建”Skill v1.1.0 初始化的证据驱动项目。

## 首次步骤

1. 填写 `00_control/AUTHORIZATION.md`、`PROJECT.yaml` 和 `SCOPE_MATRIX.csv`。
2. 填写 `01_environment/SOURCE_APPLICATION_PROFILE.yaml` 和 `TARGET_CONSTRAINTS.yaml`。
3. 把截图、录屏、样例文件和性能原始数据放入 `02_evidence/raw/`。
4. 运行 `index_evidence.py` 建立证据索引。
5. 有源码或安装目录时运行 `detect_project_stack.py`。
6. 按 `STATUS.yaml` 当前门禁推进；不要直接跳到正式编码。

## 常用校验

```bash
python <skill>/scripts/validate_project.py . --profile basic
python <skill>/scripts/calculate_coverage.py .
python <skill>/scripts/validate_traceability.py .
python <skill>/scripts/detect_orphan_items.py .
python <skill>/scripts/validate_deliverables.py .
```
