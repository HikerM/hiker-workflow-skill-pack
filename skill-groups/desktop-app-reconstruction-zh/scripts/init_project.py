#!/usr/bin/env python3
"""Initialize a deterministic v1.1 desktop-reconstruction project."""
from __future__ import annotations

import argparse
import csv
import json
import re
import shutil
import sys
from datetime import datetime
from pathlib import Path

TEXT_SUFFIXES = {".md", ".yaml", ".yml", ".csv", ".json", ".txt", ".toml", ".xml"}


def safe_slug(value: str) -> str:
    value = value.strip()
    value = re.sub(r'[\\/:*?"<>|]+', "-", value)
    value = re.sub(r"\s+", "-", value)
    value = re.sub(r"-+", "-", value).strip("-._")
    return value or "reconstruction-project"


def replace_tokens(root: Path, tokens: dict[str, str]) -> None:
    for path in root.rglob("*"):
        if not path.is_file() or path.suffix.lower() not in TEXT_SUFFIXES:
            continue
        try:
            text = path.read_text(encoding="utf-8-sig")
        except (UnicodeDecodeError, OSError):
            continue
        for key, value in tokens.items():
            text = text.replace("{{" + key + "}}", value)
        path.write_text(text, encoding="utf-8", newline="\n")


def split_modes(value: str) -> list[str]:
    return [part.strip() for part in re.split(r"[|;,]+", value) if part.strip()]


def q(value: object) -> str:
    return json.dumps(str(value if value is not None else ""), ensure_ascii=False)


def generate_manifest(project_dir: Path, project_id: str, execution_mode: str) -> None:
    checklist = project_dir / "00_control" / "DELIVERABLE_CHECKLIST.csv"
    with checklist.open("r", encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))

    lines = [
        'schema_version: "1.1"',
        f'project_id: {q(project_id)}',
        f'execution_mode: {q(execution_mode)}',
        'manifest_status: "DRAFT"',
        'generated_from: "00_control/DELIVERABLE_CHECKLIST.csv"',
        'items:',
    ]
    for row in rows:
        modes = split_modes(row.get("required_for_mode", "all")) or ["all"]
        mode_text = ", ".join(q(item) for item in modes)
        lines.extend(
            [
                f'  - id: {q(row.get("deliverable_id", ""))}',
                f'    path: {q(row.get("path", ""))}',
                f'    kind: {q(row.get("kind", "file"))}',
                f'    required_modes: [{mode_text}]',
                f'    stage: {q(row.get("stage", ""))}',
                '    status: "DRAFT"',
                '    version: ""',
                '    sha256: ""',
                f'    checksum_required: {str(row.get("checksum_required", "true")).lower()}',
                '    related_ids: []',
                '    evidence_ids: []',
                '    waiver_id: ""',
                '    owner: ""',
                f'    notes: {q(row.get("notes", ""))}',
            ]
        )
    (project_dir / "00_control" / "DELIVERABLE_MANIFEST.yaml").write_text(
        "\n".join(lines) + "\n", encoding="utf-8", newline="\n"
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="初始化桌面软件等价重建 v1.1 项目")
    parser.add_argument("--output", default=".", help="输出父目录，默认当前目录")
    parser.add_argument("--project-name", required=True, help="项目名称")
    parser.add_argument("--source-app", default="UNKNOWN", help="目标软件名称")
    parser.add_argument("--project-id", default=None, help="可选项目 ID")
    parser.add_argument(
        "--reconstruction-mode",
        choices=["black_box", "gray_box", "white_box_migration"],
        default="black_box",
        help="黑盒、灰盒或白盒迁移",
    )
    parser.add_argument(
        "--execution-mode",
        choices=["analysis", "implementation", "automation", "mixed"],
        default="analysis",
        help="资料分析、代码实施、自动观测或混合模式",
    )
    parser.add_argument("--force", action="store_true", help="仅允许写入已经存在的空目录")
    args = parser.parse_args()

    script_dir = Path(__file__).resolve().parent
    template_dir = script_dir.parent / "assets" / "project-template"
    if not (template_dir / "00_control" / "PROJECT.yaml").is_file():
        print(f"错误：找不到标准项目模板：{template_dir}", file=sys.stderr)
        return 2

    now = datetime.now().astimezone()
    project_id = args.project_id or f"RECON-{now.strftime('%Y%m%d-%H%M%S')}"
    project_dir = Path(args.output).expanduser().resolve() / safe_slug(args.project_name)

    if project_dir.exists():
        if not project_dir.is_dir() or any(project_dir.iterdir()) or not args.force:
            print(f"错误：目标目录已存在或非空：{project_dir}", file=sys.stderr)
            print("请更换目录，或仅对已存在的空目录使用 --force。", file=sys.stderr)
            return 3
    else:
        project_dir.mkdir(parents=True, exist_ok=False)

    try:
        shutil.copytree(template_dir, project_dir, dirs_exist_ok=True)
        tokens = {
            "PROJECT_ID": project_id,
            "PROJECT_NAME": args.project_name,
            "SOURCE_APP_NAME": args.source_app,
            "CREATED_AT": now.isoformat(timespec="seconds"),
            "CREATED_DATE": now.date().isoformat(),
            "CREATED_COMPACT": now.strftime("%Y%m%d%H%M%S"),
            "RECONSTRUCTION_MODE": args.reconstruction_mode,
            "EXECUTION_MODE": args.execution_mode,
        }
        replace_tokens(project_dir, tokens)
        generate_manifest(project_dir, project_id, args.execution_mode)
    except Exception:
        shutil.rmtree(project_dir, ignore_errors=True)
        raise

    print(f"项目已初始化：{project_dir}")
    print(f"项目 ID：{project_id}")
    print(f"重建模式：{args.reconstruction_mode}")
    print(f"执行模式：{args.execution_mode}")
    print("下一步：填写 00_control/AUTHORIZATION.md、PROJECT.yaml 和 SCOPE_MATRIX.csv。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
