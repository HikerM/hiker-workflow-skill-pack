from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
MAX_DEFAULT_PROMPTS = 3
MAX_PROMPT_CHARS = 160
MAX_SKILL_BYTES = 16 * 1024
MAX_TEXT_FILE_BYTES = 256 * 1024
MAX_TEST_REPORT_BYTES = 128 * 1024
MAX_GLOBAL_TEMPLATE_BYTES = 4 * 1024
MAX_SKILL_DESCRIPTION_BYTES = 360
MAX_TOTAL_SKILL_DESCRIPTION_BYTES = 10_000
MAX_TOTAL_SKILL_BODY_BYTES = 160 * 1024
TEXT_SUFFIXES = {".md", ".json", ".yaml", ".yml", ".py", ".csv", ".txt"}


def audit(root: Path = ROOT) -> dict[str, Any]:
    root = root.resolve()
    errors: list[str] = []
    warnings: list[str] = []
    metrics: dict[str, Any] = {"plugins": {}, "skill_count": 0, "skill_description_bytes": 0, "skill_body_bytes": 0}
    global_template = root / "templates" / "GLOBAL_AGENTS_AI_ENGINEERING.md"
    template_bytes = global_template.stat().st_size if global_template.is_file() else 0
    metrics["global_agents_template_bytes"] = template_bytes
    if not global_template.is_file():
        errors.append("缺少全局性能内核模板")
    elif template_bytes > MAX_GLOBAL_TEMPLATE_BYTES:
        errors.append(f"全局性能内核模板超过 {MAX_GLOBAL_TEMPLATE_BYTES} 字节")
    for plugin in sorted(path for path in (root / "plugins").iterdir() if path.is_dir()):
        manifest_path = plugin / ".codex-plugin" / "plugin.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        prompts = manifest.get("interface", {}).get("defaultPrompt") or []
        if not isinstance(prompts, list):
            errors.append(f"{plugin.name}: interface.defaultPrompt 必须是数组")
            prompts = []
        if len(prompts) > MAX_DEFAULT_PROMPTS:
            errors.append(f"{plugin.name}: defaultPrompt {len(prompts)} 条，超过桌面支持的 {MAX_DEFAULT_PROMPTS} 条")
        if any(len(str(item)) > MAX_PROMPT_CHARS for item in prompts):
            errors.append(f"{plugin.name}: defaultPrompt 单条超过 {MAX_PROMPT_CHARS} 字符")
        hook_files = [path for path in (plugin / "hooks").rglob("*") if path.is_file()] if (plugin / "hooks").exists() else []
        if hook_files:
            errors.append(f"{plugin.name}: 禁止打包高频生命周期 Hook: {[p.name for p in hook_files]}")
        text_total = 0
        largest_text = 0
        for path in plugin.rglob("*"):
            if not path.is_file() or path.suffix.lower() not in TEXT_SUFFIXES:
                continue
            size = path.stat().st_size
            text_total += size
            largest_text = max(largest_text, size)
            if size > MAX_TEXT_FILE_BYTES:
                errors.append(f"{plugin.name}: 单个文本资源超过 {MAX_TEXT_FILE_BYTES} 字节: {path.relative_to(plugin).as_posix()}")
        skills = sorted((plugin / "skills").glob("*/SKILL.md"))
        metrics["skill_count"] += len(skills)
        for skill in skills:
            skill_bytes = skill.stat().st_size
            metrics["skill_body_bytes"] += skill_bytes
            if skill_bytes > MAX_SKILL_BYTES:
                errors.append(f"{plugin.name}/{skill.parent.name}: SKILL.md 超过 {MAX_SKILL_BYTES} 字节")
            text = skill.read_text(encoding="utf-8", errors="ignore")
            match = re.search(r"(?m)^description:\s*(.+)$", text)
            description_bytes = len((match.group(1) if match else "").encode("utf-8"))
            metrics["skill_description_bytes"] += description_bytes
            if description_bytes > MAX_SKILL_DESCRIPTION_BYTES:
                errors.append(f"{plugin.name}/{skill.parent.name}: 前置描述超过 {MAX_SKILL_DESCRIPTION_BYTES} 字节")
        metrics["plugins"][plugin.name] = {
            "default_prompt_count": len(prompts),
            "hook_file_count": len(hook_files),
            "skill_count": len(skills),
            "text_bytes": text_total,
            "largest_text_bytes": largest_text,
        }
    if metrics["skill_description_bytes"] > MAX_TOTAL_SKILL_DESCRIPTION_BYTES:
        errors.append(f"Skill前置描述合计超过 {MAX_TOTAL_SKILL_DESCRIPTION_BYTES} 字节")
    if metrics["skill_body_bytes"] > MAX_TOTAL_SKILL_BODY_BYTES:
        errors.append(f"Skill正文合计超过 {MAX_TOTAL_SKILL_BODY_BYTES} 字节")
    report_path = root / "test-results.json"
    if report_path.is_file():
        size = report_path.stat().st_size
        metrics["test_report_bytes"] = size
        if size > MAX_TEST_REPORT_BYTES:
            errors.append(f"test-results.json 超过 {MAX_TEST_REPORT_BYTES} 字节，会放大工具回传")
        report = json.loads(report_path.read_text(encoding="utf-8"))
        if any("output" in item for item in report.get("results", [])):
            errors.append("test-results.json 禁止内嵌完整测试输出")
    else:
        warnings.append("尚未生成当前版本 test-results.json")
    return {"ok": not errors, "errors": errors, "warnings": warnings, "metrics": metrics}


def main() -> int:
    parser = argparse.ArgumentParser(description="Codex 桌面插件崩溃放大因子门禁")
    parser.add_argument("--root", default=str(ROOT))
    args = parser.parse_args()
    result = audit(Path(args.root))
    print(json.dumps(result, ensure_ascii=False, separators=(",", ":")))
    return 0 if result["ok"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
