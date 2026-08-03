#!/usr/bin/env python3
"""Install this Skill into a user, repository, or custom .agents/skills root."""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

from common import write_json

SKILL_NAME = "desktop-app-reconstruction-zh"
IGNORE_NAMES = {"__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache", ".DS_Store"}


def ignore_copy(_directory: str, names: list[str]) -> set[str]:
    return {name for name in names if name in IGNORE_NAMES or name.endswith((".pyc", ".pyo", ".tmp", ".swp"))}


def run_validation(skill_root: Path, validator: Path) -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="skill-install-validation-") as temp_dir:
        output = Path(temp_dir) / "validation.json"
        env = dict(os.environ)
        env["PYTHONDONTWRITEBYTECODE"] = "1"
        completed = subprocess.run(
            [sys.executable, str(validator), str(skill_root), "--json", str(output)],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            shell=False,
            check=False,
            timeout=180,
            env=env,
        )
        try:
            data = json.loads(output.read_text(encoding="utf-8-sig"))
        except (OSError, json.JSONDecodeError) as exc:
            return {
                "gate": "FAIL", "error": f"无法读取校验结果：{exc}",
                "exit_code": completed.returncode,
                "stderr": completed.stderr[-4000:],
            }
        data["exit_code"] = completed.returncode
        if completed.stderr.strip():
            data["stderr"] = completed.stderr.strip()[-4000:]
        return data


def target_root(args: argparse.Namespace) -> Path:
    if args.destination:
        return Path(args.destination).expanduser().resolve()
    if args.scope == "user":
        return (Path.home() / ".agents" / "skills").resolve()
    repo_root = Path(args.repo_root or os.getcwd()).expanduser().resolve()
    return (repo_root / ".agents" / "skills").resolve()


def main() -> int:
    parser = argparse.ArgumentParser(description="安装中文桌面软件等价重建 Skill")
    parser.add_argument("--source", default=None, help="Skill 源目录；默认脚本父目录的父目录")
    parser.add_argument("--scope", choices=["user", "repo"], default="user", help="用户级或项目级安装")
    parser.add_argument("--repo-root", default=None, help="项目级安装的仓库根目录；默认当前目录")
    parser.add_argument("--destination", default=None, help="自定义 skills 根目录，覆盖 --scope")
    parser.add_argument("--no-backup", action="store_true", help="更新时不保留旧版本备份")
    parser.add_argument("--dry-run", action="store_true", help="只校验和显示目标，不写入")
    parser.add_argument("--json", dest="json_path", default=None, help="写入安装结果 JSON")
    args = parser.parse_args()

    source = Path(args.source).expanduser().resolve() if args.source else Path(__file__).resolve().parent.parent
    validator = source / "scripts" / "validate_skill_package.py"
    destination_root = target_root(args)
    destination = destination_root / SKILL_NAME
    result: dict[str, Any] = {
        "schema_version": "1.1",
        "skill_name": SKILL_NAME,
        "source": str(source),
        "destination_root": str(destination_root),
        "destination": str(destination),
        "scope": "custom" if args.destination else args.scope,
        "dry_run": args.dry_run,
        "installed_at": datetime.now().astimezone().isoformat(timespec="seconds"),
    }

    if not source.is_dir() or not validator.is_file():
        result.update({"gate": "FAIL", "issues": ["源目录不是有效 Skill，或缺少校验脚本"]})
    else:
        precheck = run_validation(source, validator)
        result["source_validation"] = precheck
        if precheck.get("gate") != "PASS":
            result.update({"gate": "FAIL", "issues": ["源 Skill 校验失败，未安装"]})
        elif args.dry_run:
            result.update({"gate": "PASS", "message": "校验通过；dry-run 未写入文件", "backup": ""})
        else:
            destination_root.mkdir(parents=True, exist_ok=True)
            staging_parent = destination_root / f".skill-install-{uuid.uuid4().hex[:10]}"
            staging = staging_parent / SKILL_NAME
            backup: Path | None = None
            try:
                staging_parent.mkdir(parents=True, exist_ok=False)
                shutil.copytree(source, staging, symlinks=False, ignore=ignore_copy)
                staging_check = run_validation(staging, staging / "scripts" / "validate_skill_package.py")
                result["staging_validation"] = staging_check
                if staging_check.get("gate") != "PASS":
                    raise RuntimeError("暂存副本校验失败")
                if destination.exists():
                    if args.no_backup:
                        shutil.rmtree(destination)
                    else:
                        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
                        backup = destination_root / f"{SKILL_NAME}.backup-{stamp}"
                        counter = 1
                        while backup.exists():
                            backup = destination_root / f"{SKILL_NAME}.backup-{stamp}-{counter}"
                            counter += 1
                        destination.rename(backup)
                staging.rename(destination)
                shutil.rmtree(staging_parent, ignore_errors=True)
                installed_check = run_validation(destination, destination / "scripts" / "validate_skill_package.py")
                result["installed_validation"] = installed_check
                if installed_check.get("gate") != "PASS":
                    raise RuntimeError("安装后校验失败")
                result.update({
                    "gate": "PASS",
                    "message": "安装完成",
                    "backup": str(backup) if backup else "",
                })
            except Exception as exc:
                if staging_parent.exists():
                    shutil.rmtree(staging_parent, ignore_errors=True)
                if destination.exists() and result.get("installed_validation", {}).get("gate") != "PASS":
                    shutil.rmtree(destination, ignore_errors=True)
                if backup is not None and backup.exists() and not destination.exists():
                    backup.rename(destination)
                result.update({"gate": "FAIL", "issues": [f"安装失败：{exc}"]})

    print(json.dumps(result, ensure_ascii=False, indent=2))
    if args.json_path:
        write_json(Path(args.json_path).expanduser().resolve(), result)
    return 0 if result.get("gate") == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
