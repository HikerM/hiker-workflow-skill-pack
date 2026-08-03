#!/usr/bin/env python3
"""Index evidence files with stable IDs, metadata and SHA-256 hashes."""
from __future__ import annotations

import argparse
import mimetypes
import re
import sys
from datetime import datetime
from pathlib import Path

from common import read_csv_rows, sha256_file, write_csv_rows

FIELDNAMES = [
    "evidence_id", "file_path", "evidence_type", "source_channel", "mime_type", "size_bytes",
    "captured_at", "source_app_version", "environment_id", "operator",
    "action_or_state", "sha256", "related_scope_ids", "related_inventory_ids", "related_spec_ids",
    "classification", "privacy_level", "notes",
]


def classify(path: Path) -> str:
    ext = path.suffix.lower()
    if ext in {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tif", ".tiff"}:
        return "screenshot_or_image"
    if ext in {".mp4", ".mov", ".mkv", ".avi", ".webm"}:
        return "recording_or_video"
    if ext in {".csv", ".json", ".jsonl", ".log", ".txt", ".xml"}:
        return "log_or_data"
    if ext in {".pdf", ".docx", ".xlsx", ".pptx", ".md"}:
        return "document"
    if ext in {".zip", ".7z", ".rar", ".tar", ".gz"}:
        return "archive"
    if ext in {".exe", ".dll", ".msi", ".app", ".dmg", ".deb", ".rpm", ".so"}:
        return "binary_or_installer"
    return "file"


def next_sequence(existing: list[dict[str, str]], date_part: str) -> int:
    pattern = re.compile(rf"^EV-{re.escape(date_part)}-(\d{{4,}})$")
    values = [int(m.group(1)) for row in existing if (m := pattern.match(row.get("evidence_id", "")))]
    return max(values, default=0) + 1


def main() -> int:
    parser = argparse.ArgumentParser(description="生成或更新桌面软件重建证据索引")
    parser.add_argument("evidence_dir", help="原始证据目录，例如 02_evidence/raw")
    parser.add_argument("--output", default=None, help="输出 CSV；默认写入原始目录上级的 EVIDENCE_INDEX.csv")
    args = parser.parse_args()

    evidence_dir = Path(args.evidence_dir).expanduser().resolve()
    if not evidence_dir.is_dir():
        print(f"错误：目录不存在：{evidence_dir}", file=sys.stderr)
        return 2

    output = Path(args.output).expanduser().resolve() if args.output else evidence_dir.parent / "EVIDENCE_INDEX.csv"
    existing = read_csv_rows(output)
    existing_by_path = {row.get("file_path", ""): row for row in existing if row.get("file_path")}
    paths = sorted(
        p for p in evidence_dir.rglob("*")
        if p.is_file() and p.name not in {".gitkeep", ".keep"} and p.resolve() != output.resolve()
    )
    date_part = datetime.now().strftime("%Y%m%d")
    sequence = next_sequence(existing, date_part)
    rows: list[dict[str, str]] = []

    for path in paths:
        rel = path.relative_to(evidence_dir.parent).as_posix()
        prior = dict(existing_by_path.get(rel, {}))
        if not prior.get("evidence_id"):
            prior["evidence_id"] = f"EV-{date_part}-{sequence:04d}"
            sequence += 1
        stat = path.stat()
        prior.update({
            "file_path": rel,
            "evidence_type": classify(path),
            "source_channel": prior.get("source_channel") or classify(path),
            "mime_type": mimetypes.guess_type(path.name)[0] or "application/octet-stream",
            "size_bytes": str(stat.st_size),
            "sha256": sha256_file(path),
        })
        prior.setdefault("captured_at", datetime.fromtimestamp(stat.st_mtime).astimezone().isoformat(timespec="seconds"))
        prior.setdefault("source_app_version", "")
        prior.setdefault("environment_id", "")
        prior.setdefault("operator", "")
        prior.setdefault("action_or_state", "")
        prior.setdefault("related_scope_ids", "")
        prior.setdefault("related_inventory_ids", "")
        prior.setdefault("related_spec_ids", "")
        prior.setdefault("classification", "UNVERIFIED")
        prior.setdefault("privacy_level", "internal")
        prior.setdefault("notes", "")
        rows.append(prior)

    output.parent.mkdir(parents=True, exist_ok=True)
    write_csv_rows(output, FIELDNAMES, rows)
    current_paths = {row["file_path"] for row in rows}
    removed = len(set(existing_by_path) - current_paths)
    print(f"已索引 {len(rows)} 个文件：{output}")
    if removed:
        print(f"注意：{removed} 个旧路径已不在原始证据目录，未写入本次索引。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
