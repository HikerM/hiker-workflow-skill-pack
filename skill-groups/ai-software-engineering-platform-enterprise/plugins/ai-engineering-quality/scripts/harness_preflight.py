from __future__ import annotations

import argparse
import json
import os
import shlex
import shutil
import tempfile
from pathlib import Path
from typing import Any

from qualitylib import git_root, load_json, repo_ai, write_json

WINDOWS_COMMAND_BUDGET = 7000


def executable(command: str) -> str:
    try:
        return shlex.split(command, posix=os.name != "nt")[0]
    except ValueError:
        return ""


def inspect_plan(root: Path, plan: dict[str, Any]) -> list[dict[str, str]]:
    findings: list[dict[str, str]] = []
    commands = list(plan.get("mandatory", [])) + list(plan.get("recommended", []))
    for item in commands:
        command = str(item.get("command") or "")
        cwd = (root / str(item.get("cwd") or ".")).resolve()
        if not cwd.is_dir():
            findings.append({"severity": "BLOCK", "type": "MISSING_CWD", "detail": str(cwd)})
        if os.name == "nt" and len(command) > WINDOWS_COMMAND_BUDGET:
            findings.append({"severity": "BLOCK", "type": "WINDOWS_COMMAND_TOO_LONG", "detail": str(len(command))})
        exe = executable(command)
        if exe.startswith("${"):
            findings.append({"severity": "WARN", "type": "RUNTIME_REQUIRED", "detail": exe})
        elif exe and shutil.which(exe) is None:
            findings.append({"severity": "BLOCK", "type": "MISSING_RUNTIME", "detail": exe})
    return findings


def inspect_manifest(manifest: dict[str, Any]) -> list[dict[str, str]]:
    findings: list[dict[str, str]] = []
    groups = manifest.get("groups", []) if isinstance(manifest, dict) else []
    seen: set[str] = set()
    for group in groups:
        group_id = str(group.get("id") or "")
        if not group_id or group_id in seen:
            findings.append({"severity": "BLOCK", "type": "INVALID_GROUP_ID", "detail": group_id or "missing"})
            continue
        seen.add(group_id)
        cases = group.get("cases", []) if isinstance(group.get("cases"), list) else []
        declared = int(group.get("declared_count", len(cases)))
        if declared != len(cases):
            findings.append({"severity": "BLOCK", "type": "COUNT_MISMATCH", "detail": f"{group_id}:{declared}!={len(cases)}"})
        if group.get("mutation_required") and not group.get("mutation_evidence"):
            findings.append({"severity": "BLOCK", "type": "MUTATION_NOT_PROVEN", "detail": group_id})
        if not group.get("sample_pass") or not group.get("sample_fail"):
            findings.append({"severity": "BLOCK", "type": "SAMPLES_INCOMPLETE", "detail": group_id})
    return findings


def temp_probe(root: Path) -> list[dict[str, str]]:
    findings = []
    try:
        repo_ai(root).mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="ai-harness-preflight-", dir=str(repo_ai(root))) as td:
            probe = Path(td) / "probe.txt"; probe.write_text("ok", encoding="utf-8")
            if probe.read_text(encoding="utf-8") != "ok":
                raise OSError("probe read mismatch")
    except OSError as exc:
        findings.append({"severity": "BLOCK", "type": "TEMP_IO_FAILED", "detail": str(exc)})
    return findings


def preflight(root: Path, plan: dict[str, Any], manifest: dict[str, Any] | None = None) -> dict[str, Any]:
    findings = inspect_plan(root, plan) + temp_probe(root)
    if manifest is not None:
        findings += inspect_manifest(manifest)
    blockers = [item for item in findings if item["severity"] == "BLOCK"]
    return {
        "schema_version": 1, "result": "PASS" if not blockers else "INVALID", "findings": findings,
        "full_matrix_allowed": not blockers,
        "rule": "large matrices require valid runtimes, paths, counts, mutations, pass/fail samples and temporary I/O",
    }


def main() -> int:
    parser = argparse.ArgumentParser(); parser.add_argument("--root", default="."); parser.add_argument("--plan"); parser.add_argument("--manifest")
    args = parser.parse_args(); root = git_root(Path(args.root))
    plan_path = Path(args.plan) if args.plan else repo_ai(root) / "evidence" / "test-plan" / "latest.json"
    plan = load_json(plan_path, {}) or {}
    if not plan:
        raise SystemExit("missing test plan")
    manifest = load_json(Path(args.manifest), {}) if args.manifest else None
    result = preflight(root, plan, manifest)
    write_json(repo_ai(root) / "evidence" / "test-plan" / "harness-preflight.json", result)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["full_matrix_allowed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
