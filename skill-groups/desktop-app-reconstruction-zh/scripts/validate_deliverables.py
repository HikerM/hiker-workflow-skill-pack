#!/usr/bin/env python3
"""Validate mode/phase-specific deliverables against checklist and manifest."""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

from common import (
    PLACEHOLDER_RE, csv_data_row_count, detect_execution_mode, document_status,
    is_true, markdown_table, non_placeholder_files, read_csv_rows, resolve_root,
    safe_relative_path, sha256_path, split_values, write_json,
)
from lib_recon import parse_simple_yaml

SELF_MANIFEST_PATH = "00_control/DELIVERABLE_MANIFEST.yaml"
SELF_REPORT_PATH = "09_reports/DELIVERABLE_VALIDATION_REPORT.md"


def q(value: object) -> str:
    return json.dumps(str(value if value is not None else ""), ensure_ascii=False)


def mode_required(value: str | list[str], mode: str) -> bool:
    values = {item.lower() for item in split_values(value if isinstance(value, str) else value)}
    return "all" in values or mode in values


def phase_active(row: dict[str, str], mode: str, phase: str) -> bool:
    if not mode_required(row.get("required_for_mode", "all"), mode):
        return False
    modes = set(split_values(row.get("required_for_mode", "all")))
    if phase == "release":
        return True
    if "all" in modes:
        return True
    if phase == "implementation":
        return row.get("stage") in {"G5-T", "G5", "G6"}
    # spec phase only activates automation additions; implementation/release artifacts are not yet required.
    return mode in {"automation", "mixed"} and row.get("required_for_mode") in {"automation", "automation|mixed", "mixed|automation"}


def parse_manifest(path: Path) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    data = parse_simple_yaml(path)
    if not isinstance(data, dict):
        raise ValueError("DELIVERABLE_MANIFEST.yaml 顶层不是映射")
    items = data.get("items", [])
    if not isinstance(items, list):
        raise ValueError("DELIVERABLE_MANIFEST.items 不是列表")
    normalized = [item for item in items if isinstance(item, dict)]
    return data, normalized


def write_manifest(path: Path, top: dict[str, Any], items: list[dict[str, Any]]) -> None:
    lines = [
        'schema_version: "1.1"',
        f'project_id: {q(top.get("project_id", ""))}',
        f'execution_mode: {q(top.get("execution_mode", "analysis"))}',
        f'manifest_status: {q(top.get("manifest_status", "DRAFT"))}',
        f'generated_from: {q(top.get("generated_from", "00_control/DELIVERABLE_CHECKLIST.csv"))}',
        'items:',
    ]
    for item in items:
        modes = item.get("required_modes", ["all"])
        if isinstance(modes, str): modes = split_values(modes)
        mode_text = ", ".join(q(value) for value in modes)
        lines.extend([
            f'  - id: {q(item.get("id", ""))}',
            f'    path: {q(item.get("path", ""))}',
            f'    kind: {q(item.get("kind", "file"))}',
            f'    required_modes: [{mode_text}]',
            f'    stage: {q(item.get("stage", ""))}',
            f'    status: {q(item.get("status", "DRAFT"))}',
            f'    version: {q(item.get("version", ""))}',
            f'    sha256: {q(item.get("sha256", ""))}',
            f'    checksum_required: {str(bool(item.get("checksum_required", True))).lower()}',
            '    related_ids: [' + ', '.join(q(v) for v in (item.get("related_ids", []) if isinstance(item.get("related_ids", []), list) else split_values(item.get("related_ids")))) + ']',
            '    evidence_ids: [' + ', '.join(q(v) for v in (item.get("evidence_ids", []) if isinstance(item.get("evidence_ids", []), list) else split_values(item.get("evidence_ids")))) + ']',
            f'    waiver_id: {q(item.get("waiver_id", ""))}',
            f'    owner: {q(item.get("owner", ""))}',
            f'    notes: {q(item.get("notes", ""))}',
        ])
    path.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")


def validate(root: Path, mode: str, phase: str, write_checksums: bool) -> dict[str, object]:
    checklist_path = root / "00_control" / "DELIVERABLE_CHECKLIST.csv"
    manifest_path = root / SELF_MANIFEST_PATH
    checklist = read_csv_rows(checklist_path)
    errors: list[str] = []
    if not checklist:
        return {"schema_version": "1.1", "gate": "FAIL", "errors": ["DELIVERABLE_CHECKLIST.csv 为空"], "results": []}
    try:
        top, manifest_items = parse_manifest(manifest_path)
    except Exception as exc:
        return {"schema_version": "1.1", "gate": "FAIL", "errors": [f"交付清单解析失败：{exc}"], "results": []}

    checklist_ids = [row.get("deliverable_id", "") for row in checklist if row.get("deliverable_id")]
    manifest_ids = [str(item.get("id", "")) for item in manifest_items if item.get("id")]
    for label, values in (("检查表", checklist_ids), ("清单", manifest_ids)):
        duplicates = sorted({value for value in values if values.count(value) > 1})
        errors.extend(f"{label}交付物 ID 重复：{value}" for value in duplicates)
    manifest_map = {str(item.get("id", "")): item for item in manifest_items if item.get("id")}

    active_rows = [row for row in checklist if phase_active(row, mode, phase)]
    results: list[dict[str, object]] = []

    for row in active_rows:
        deliverable_id = row.get("deliverable_id", "")
        rel = row.get("path", "")
        item = manifest_map.get(deliverable_id)
        issues: list[str] = []
        if not item:
            results.append({"deliverable_id": deliverable_id, "path": rel, "stage": row.get("stage", ""), "status": "FAIL", "issues": ["DELIVERABLE_MANIFEST 缺少此项"]})
            continue
        if str(item.get("path", "")) != rel:
            issues.append(f"manifest path 不一致：{item.get('path', '')}")
        if str(item.get("kind", "file")) != row.get("kind", "file"):
            issues.append("manifest kind 与检查表不一致")

        ok, target = safe_relative_path(root, rel)
        if not ok:
            issues.append("路径越出项目根目录")
        kind = row.get("kind", "file").lower()
        is_self_manifest = rel == SELF_MANIFEST_PATH
        if kind == "dir":
            if not target.is_dir():
                issues.append("目录不存在")
                files: list[Path] = []
            else:
                files = non_placeholder_files(target)
                try: minimum = int(row.get("min_non_placeholder_items", "") or 0)
                except ValueError: minimum = 0
                if len(files) < minimum: issues.append(f"非占位文件数量 {len(files)} < {minimum}")
        else:
            if not target.is_file():
                issues.append("文件不存在")
            else:
                try: minimum_size = int(row.get("min_size_bytes", "") or 0)
                except ValueError: minimum_size = 0
                if target.stat().st_size < minimum_size: issues.append(f"文件大小 {target.stat().st_size} < {minimum_size}")
                raw_min_rows = row.get("min_data_rows", "") or row.get("min_non_placeholder_items", "") or 0
                try: minimum_rows = int(raw_min_rows)
                except ValueError: minimum_rows = 0
                if target.suffix.lower() == ".csv" and csv_data_row_count(target) < minimum_rows:
                    issues.append(f"CSV 数据行 {csv_data_row_count(target)} < {minimum_rows}")
                try:
                    text = target.read_text(encoding="utf-8-sig")
                except UnicodeDecodeError:
                    text = ""
                if is_true(row.get("placeholder_forbidden")) and text and PLACEHOLDER_RE.search(text):
                    issues.append("仍含模板占位符")
                if not is_self_manifest:
                    for marker_value in split_values(row.get("forbidden_markers")):
                        if marker_value and marker_value in text:
                            issues.append(f"仍含禁止标记：{marker_value}")
                    for marker_value in split_values(row.get("required_markers")):
                        if marker_value and marker_value not in text:
                            issues.append(f"缺少完成标记：{marker_value}")
                if is_true(row.get("document_status_required")):
                    marker = document_status(target)
                    if marker not in {"READY", "PASS"}:
                        issues.append(f"document_status 不是 READY/PASS：{marker or '缺失'}")

        manifest_status = str(item.get("status", "DRAFT")).upper()
        is_self_generated = rel == SELF_REPORT_PATH
        if not is_self_generated and not is_self_manifest and manifest_status not in {"READY", "PASS"}:
            issues.append(f"manifest status 不是 READY/PASS：{manifest_status}")

        checksum_required = is_true(row.get("checksum_required")) and rel != SELF_MANIFEST_PATH
        actual_hash = ""
        if ok and target.exists() and checksum_required:
            actual_hash = sha256_path(target)
            declared_hash = str(item.get("sha256", ""))
            if write_checksums and manifest_status in {"READY", "PASS"}:
                item["sha256"] = actual_hash
                declared_hash = actual_hash
            if not is_self_generated and not declared_hash:
                issues.append("manifest sha256 为空")
            elif not is_self_generated and declared_hash.lower() != actual_hash.lower():
                issues.append("manifest sha256 与实际文件不一致")

        results.append({
            "deliverable_id": deliverable_id, "path": rel, "kind": kind,
            "stage": row.get("stage", ""), "manifest_status": manifest_status,
            "status": "PASS" if not issues else "FAIL", "issues": issues,
            "actual_sha256": actual_hash,
        })

    # Build the report from all non-self results, then make the self-report a verified output.
    non_self_failures = [row for row in results if row["path"] != SELF_REPORT_PATH and row["status"] == "FAIL"]
    provisional_gate = "PASS" if active_rows and not errors and not non_self_failures else "FAIL"
    report_rows = [[row["deliverable_id"], row["stage"], row["path"], ";".join(row["issues"])] for row in results if row["status"] == "FAIL" and row["path"] != SELF_REPORT_PATH]
    report = (
        "<!-- document_status: " + provisional_gate + " -->\n"
        "# 交付物完整性报告\n\n"
        f"- 执行模式：{mode}\n- 验证阶段：{phase}\n- 门禁：**{provisional_gate}**\n"
        f"- 激活交付物：{len(active_rows)}；非自检失败：{len(non_self_failures)}\n\n"
        "## 缺失或不完整\n\n" + (markdown_table(["ID", "阶段", "路径", "问题"], report_rows) if report_rows else "无。") + "\n"
    )
    report_path = root / SELF_REPORT_PATH
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(report, encoding="utf-8")

    self_item = next((row for row in results if row["path"] == SELF_REPORT_PATH), None)
    manifest_self = next((item for item in manifest_items if str(item.get("path", "")) == SELF_REPORT_PATH), None)
    if manifest_self is not None:
        manifest_self["status"] = "READY" if provisional_gate == "PASS" else "BLOCKED"
        manifest_self["sha256"] = sha256_path(report_path) if provisional_gate == "PASS" else ""
    if self_item is not None:
        self_item["status"] = provisional_gate
        self_item["issues"] = [] if provisional_gate == "PASS" else ["其他必需交付物未通过"]
        self_item["manifest_status"] = "READY" if provisional_gate == "PASS" else "BLOCKED"
        self_item["actual_sha256"] = sha256_path(report_path)

    manifest_result = next((row for row in results if row["path"] == SELF_MANIFEST_PATH), None)
    manifest_entry = next((item for item in manifest_items if str(item.get("path", "")) == SELF_MANIFEST_PATH), None)
    if manifest_result is not None:
        manifest_result["issues"] = [item for item in manifest_result.get("issues", []) if "manifest status" not in item and "完成标记" not in item and "禁止标记" not in item]
        manifest_result["status"] = "PASS" if not manifest_result["issues"] else "FAIL"
    if manifest_entry is not None:
        manifest_entry["status"] = "READY" if provisional_gate == "PASS" else "BLOCKED"
        manifest_entry["sha256"] = ""

    final_failures = [row for row in results if row["status"] == "FAIL"]
    gate = "PASS" if active_rows and not errors and not final_failures else "FAIL"
    top["manifest_status"] = "VERIFIED" if gate == "PASS" else "UNVERIFIED"
    if write_checksums or manifest_self is not None:
        write_manifest(manifest_path, top, manifest_items)

    checksum_lines = []
    for row in results:
        if row["status"] == "PASS" and row.get("actual_sha256") and row["path"] != SELF_MANIFEST_PATH:
            checksum_lines.append(f"{row['actual_sha256']}  {row['path']}")
    checksum_path = root / "08_build" / "checksums" / "deliverables.sha256"
    if write_checksums and checksum_lines:
        checksum_path.parent.mkdir(parents=True, exist_ok=True)
        checksum_path.write_text("\n".join(sorted(set(checksum_lines))) + "\n", encoding="utf-8")

    return {
        "schema_version": "1.1", "project_dir": str(root), "execution_mode": mode,
        "phase": phase, "checked_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "gate": gate, "active_count": len(active_rows), "failure_count": len(final_failures),
        "errors": errors, "checksum_file": str(checksum_path), "results": results,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="检查执行模式和阶段对应的完整交付物")
    parser.add_argument("project_dir")
    parser.add_argument("--mode", choices=["analysis", "implementation", "automation", "mixed"], default=None)
    parser.add_argument("--phase", choices=["spec", "implementation", "release"], default="spec")
    parser.add_argument("--write-checksums", action="store_true")
    parser.add_argument("--json", dest="json_path", default=None)
    parser.add_argument("--no-fail", action="store_true")
    args = parser.parse_args()
    try:
        root = resolve_root(args.project_dir)
    except FileNotFoundError as exc:
        print(str(exc), file=sys.stderr); return 2
    mode = args.mode or detect_execution_mode(root)
    result = validate(root, mode, args.phase, args.write_checksums)
    json_path = Path(args.json_path).expanduser().resolve() if args.json_path else root / "09_reports" / "deliverable-results.json"
    write_json(json_path, result)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["gate"] == "PASS" or args.no_fail else 1


if __name__ == "__main__":
    raise SystemExit(main())
