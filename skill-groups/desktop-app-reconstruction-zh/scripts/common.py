#!/usr/bin/env python3
"""Shared deterministic helpers for desktop-reconstruction project checks."""
from __future__ import annotations

import csv
import hashlib
import json
import re
from datetime import date
from pathlib import Path
from typing import Iterable, Iterator

PLACEHOLDER_RE = re.compile(r"\{\{[A-Z0-9_]+\}\}")
TEXT_EXTENSIONS = {
    ".md", ".yaml", ".yml", ".csv", ".json", ".txt", ".toml", ".xml",
    ".props", ".targets", ".csproj", ".fsproj", ".vbproj",
}
TRUE_VALUES = {"1", "true", "yes", "y", "是", "in_scope", "required"}
PASS_VALUES = {"pass", "passed", "通过", "verified", "ready", "complete", "completed", "locked", "accepted", "closed"}
WAIVED_VALUES = {"waived", "conditional", "豁免", "skipped_with_waiver", "wont_fix_with_waiver"}
FAIL_VALUES = {"fail", "failed", "失败", "blocked", "not_run", "unverified", "unknown", ""}
PRIORITIES = {"P0": 0, "P1": 1, "P2": 2, "P3": 3}
CORE_PRIORITIES = {"P0", "P1"}
ACTIVE_WAIVER_STATUSES = {"approved", "active", "pass", "conditional", "已批准", "生效"}
CLOSED_DEFECT_STATUSES = {"closed", "fixed", "resolved", "verified", "已关闭", "已修复", "已验证"}

INVENTORY_SOURCES: tuple[tuple[str, str, str], ...] = (
    ("03_inventory/ENTRY_POINT_INVENTORY.csv", "entry_id", "entry"),
    ("03_inventory/WINDOW_PAGE_INVENTORY.csv", "page_id", "page"),
    ("03_inventory/INTERACTIVE_CONTROL_INVENTORY.csv", "control_id", "control"),
    ("03_inventory/INTERACTION_INVENTORY.csv", "interaction_id", "interaction"),
    ("03_inventory/SHORTCUT_MENU_INVENTORY.csv", "item_id", "menu_or_shortcut"),
    ("03_inventory/FEATURE_INVENTORY.csv", "feature_id", "feature"),
    ("03_inventory/DATA_CONTRACT_INVENTORY.csv", "data_id", "data"),
    ("03_inventory/ROLE_PERMISSION_MATRIX.csv", "permission_id", "permission"),
    ("03_inventory/EXTERNAL_DEPENDENCY_MATRIX.csv", "dependency_id", "external_dependency"),
    ("07_tests/PERFORMANCE_SCENARIOS.csv", "scenario_id", "performance"),
)

SPEC_ID_KEYS = {
    "spec_id", "window_id", "page_id", "interaction_id", "feature_id", "data_id",
    "workflow_id", "performance_id", "scenario_id", "permission_id", "error_id",
}
SPEC_ID_RE = re.compile(
    r"^\s*(" + "|".join(sorted(map(re.escape, SPEC_ID_KEYS), key=len, reverse=True)) + r")\s*:\s*[\"']?([A-Z][A-Z0-9_-]+)",
    re.MULTILINE,
)


def resolve_root(project_dir: str | Path) -> Path:
    root = Path(project_dir).expanduser().resolve()
    if not root.is_dir():
        raise FileNotFoundError(f"项目目录不存在：{root}")
    return root


def read_csv_rows(path: Path) -> list[dict[str, str]]:
    if not path.is_file():
        return []
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        return [{str(k): (v or "").strip() for k, v in row.items()} for row in reader]


def csv_fieldnames(path: Path) -> list[str]:
    if not path.is_file():
        return []
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.reader(handle)
        return next(reader, [])


def write_csv_rows(path: Path, fieldnames: list[str], rows: Iterable[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({key: row.get(key, "") for key in fieldnames})


def unique(items: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        if item and item not in seen:
            seen.add(item)
            result.append(item)
    return result


def split_values(value: str | list[str] | None) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        result: list[str] = []
        for item in value:
            result.extend(split_values(item))
        return unique(result)
    return unique(item.strip() for item in re.split(r"[;,|\n]+", str(value)) if item.strip())


def normalize_status(value: str | None) -> str:
    return str(value or "").strip().lower().replace(" ", "_")


def is_true(value: str | bool | None) -> bool:
    if isinstance(value, bool):
        return value
    return normalize_status(str(value or "")) in TRUE_VALUES


def is_pass(value: str | None) -> bool:
    return normalize_status(value) in PASS_VALUES


def is_waived(value: str | None) -> bool:
    return normalize_status(value) in WAIVED_VALUES


def priority_of(row: dict[str, str]) -> str:
    value = (row.get("priority") or "P3").strip().upper()
    return value if value in PRIORITIES else "P3"


def is_core(row: dict[str, str]) -> bool:
    return priority_of(row) in CORE_PRIORITIES


def in_scope(row: dict[str, str]) -> bool:
    return is_true(row.get("in_scope", "true"))


def detect_execution_mode(root: Path) -> str:
    project = root / "00_control" / "PROJECT.yaml"
    if project.is_file():
        text = project.read_text(encoding="utf-8-sig", errors="replace")
        match = re.search(r"^\s*execution_mode\s*:\s*[\"']?([^\s#\"']+)", text, re.MULTILINE)
        if match:
            value = match.group(1).strip().lower()
            if value in {"analysis", "implementation", "automation", "mixed"}:
                return value
    return "analysis"


def project_setting(root: Path, key: str, default: str | float | int | bool) -> str | float | int | bool:
    path = root / "00_control" / "PROJECT.yaml"
    if not path.is_file():
        return default
    text = path.read_text(encoding="utf-8-sig", errors="replace")
    match = re.search(rf"^\s*{re.escape(key)}\s*:\s*([^#\n]+)", text, re.MULTILINE)
    if not match:
        return default
    raw = match.group(1).strip().strip('"\'')
    if isinstance(default, bool):
        return is_true(raw)
    if isinstance(default, int) and not isinstance(default, bool):
        try: return int(raw)
        except ValueError: return default
    if isinstance(default, float):
        try: return float(raw)
        except ValueError: return default
    return raw


def sha256_file(path: Path, chunk_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while True:
            chunk = handle.read(chunk_size)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def sha256_path(path: Path, *, exclude_names: set[str] | None = None) -> str:
    exclude_names = exclude_names or {".gitkeep", ".keep"}
    if path.is_file():
        return sha256_file(path)
    if not path.is_dir():
        raise FileNotFoundError(path)
    digest = hashlib.sha256()
    for child in sorted(p for p in path.rglob("*") if p.is_file() and p.name not in exclude_names):
        rel = child.relative_to(path).as_posix()
        digest.update(rel.encode("utf-8")); digest.update(b"\0")
        digest.update(sha256_file(child).encode("ascii")); digest.update(b"\n")
    return digest.hexdigest()


def safe_relative_path(root: Path, value: str) -> tuple[bool, Path]:
    candidate = (root / value).resolve()
    try:
        candidate.relative_to(root.resolve())
        return True, candidate
    except ValueError:
        return False, candidate


def find_placeholders(root: Path) -> list[dict[str, object]]:
    result: list[dict[str, object]] = []
    for path in root.rglob("*"):
        if not path.is_file() or path.suffix.lower() not in TEXT_EXTENSIONS:
            continue
        if ".example." in path.name:
            continue
        try:
            text = path.read_text(encoding="utf-8-sig")
        except (UnicodeDecodeError, OSError):
            continue
        matches = sorted(set(PLACEHOLDER_RE.findall(text)))
        if matches:
            result.append({"file": path.relative_to(root).as_posix(), "placeholders": matches})
    return result


def write_json(path: Path, data: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def format_rate(numerator: int, denominator: int) -> float:
    return round(numerator / denominator, 6) if denominator else 0.0


def markdown_table(headers: list[str], rows: list[list[object]]) -> str:
    def esc(value: object) -> str:
        return str(value).replace("|", "\\|").replace("\n", "<br>")
    lines = ["| " + " | ".join(headers) + " |", "|" + "|".join(["---"] * len(headers)) + "|"]
    for row in rows:
        lines.append("| " + " | ".join(esc(value) for value in row) + " |")
    return "\n".join(lines)


def non_placeholder_files(path: Path) -> list[Path]:
    if not path.is_dir():
        return []
    return [
        p for p in path.rglob("*")
        if p.is_file()
        and p.name not in {".gitkeep", ".keep"}
        and ".example." not in p.name
    ]


def collect_inventory_records(root: Path) -> list[dict[str, str]]:
    records: list[dict[str, str]] = []
    for rel, id_field, kind in INVENTORY_SOURCES:
        for row in read_csv_rows(root / rel):
            record_id = row.get(id_field, "")
            if not record_id:
                continue
            item = dict(row)
            item["record_id"] = record_id
            item["record_kind"] = kind
            item["record_file"] = rel
            records.append(item)
    # Structured error catalog is YAML; use a conservative regex for list entries.
    error_path = root / "03_inventory" / "ERROR_RECOVERY_CATALOG.yaml"
    if error_path.is_file():
        text = error_path.read_text(encoding="utf-8-sig", errors="replace")
        blocks = re.split(r"(?m)^\s*-\s+error_id\s*:\s*", text)[1:]
        for block in blocks:
            first, *rest = block.splitlines()
            error_id = first.strip().strip('"\'')
            body = "\n".join(rest)
            def field(name: str, default: str = "") -> str:
                match = re.search(rf"(?m)^\s+{re.escape(name)}\s*:\s*(.+)$", body)
                return match.group(1).strip().strip('"\'') if match else default
            def list_field(name: str) -> str:
                match = re.search(rf"(?m)^\s+{re.escape(name)}\s*:\s*\[([^\]]*)\]", body)
                if not match: return ""
                return ";".join(part.strip().strip('"\'') for part in match.group(1).split(",") if part.strip())
            records.append({
                "record_id": error_id, "record_kind": "error", "record_file": "03_inventory/ERROR_RECOVERY_CATALOG.yaml",
                "priority": field("priority", "P1"), "in_scope": "true", "status": field("status", "UNVERIFIED"),
                "evidence_ids": list_field("evidence_ids"), "spec_ids": list_field("spec_ids"),
                "task_ids": list_field("task_ids"), "implementation_ids": list_field("implementation_ids"),
                "test_case_ids": list_field("test_case_ids"), "test_result": field("test_result", ""),
                "defect_ids": list_field("defect_ids"), "waiver_id": field("waiver_id", ""),
                "rollback_behavior": field("rollback_behavior", ""), "retry_behavior": field("retry_behavior", ""),
            })
    return records


def collect_spec_records(root: Path) -> dict[str, dict[str, str]]:
    result: dict[str, dict[str, str]] = {}
    spec_root = root / "04_specifications"
    if not spec_root.is_dir():
        return result
    for path in spec_root.rglob("*"):
        if not path.is_file() or path.suffix.lower() not in {".yaml", ".yml", ".json", ".md"}:
            continue
        if ".example." in path.name:
            continue
        text = path.read_text(encoding="utf-8-sig", errors="replace")
        priority_match = re.search(r"(?m)^\s*priority\s*:\s*[\"']?(P[0-3])", text, re.I)
        priority = priority_match.group(1).upper() if priority_match else "P3"
        matches = SPEC_ID_RE.findall(text)
        # If a file declares an explicit spec_id, domain IDs such as feature_id
        # are related subjects, not additional specification records.
        explicit = [(key, value) for key, value in matches if key == "spec_id"]
        selected = explicit or matches
        for key, value in selected:
            result.setdefault(
                value,
                {
                    "spec_id": value,
                    "id_key": key,
                    "priority": priority,
                    "path": path.relative_to(root).as_posix(),
                },
            )
    return result


def active_waiver_rows(root: Path) -> dict[str, dict[str, str]]:
    result: dict[str, dict[str, str]] = {}
    for row in read_csv_rows(root / "07_tests" / "WAIVERS.csv"):
        waiver_id = row.get("waiver_id", "")
        if not waiver_id or normalize_status(row.get("status")) not in ACTIVE_WAIVER_STATUSES:
            continue
        expires = row.get("expires_at", "")
        if expires:
            try:
                if date.fromisoformat(expires[:10]) < date.today():
                    continue
            except ValueError:
                continue
        result[waiver_id] = row
    return result


def referenced_by_waiver(waiver: dict[str, str], subject_id: str) -> bool:
    return subject_id in split_values(waiver.get("related_ids"))


def document_status(path: Path) -> str:
    if not path.is_file() or path.suffix.lower() != ".md":
        return ""
    head = path.read_text(encoding="utf-8-sig", errors="replace")[:1000]
    match = re.search(r"<!--\s*document_status\s*:\s*([A-Z_]+)\s*-->", head, re.I)
    return match.group(1).upper() if match else ""


def csv_data_row_count(path: Path) -> int:
    return len(read_csv_rows(path))
