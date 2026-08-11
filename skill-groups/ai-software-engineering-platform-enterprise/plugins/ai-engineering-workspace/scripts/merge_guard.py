from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

from workspacelib import common_dir, glob_match, read_json, repo_root, run, safe_id

COMMIT = re.compile(r"^(feat|fix|refactor|docs|test|chore|perf|build|ci)(\([^)]+\))?!?: .+")


def branch_ok(root: Path, name: str) -> bool: return run(["git", "rev-parse", "--verify", "--quiet", name], root, check=False).returncode == 0


def flow_ok(source: str, target: str) -> bool:
    return (source.startswith(("feature/", "bugfix/")) and target == "develop") or (source.startswith("hotfix/") and target == "main") or (source.startswith("release/") and target == "main") or (source == "develop" and target == "release")


def changed(root: Path, target: str, source: str) -> list[dict]:
    out = run(["git", "diff", "--name-status", "-M", f"{target}...{source}"], root).stdout; items = []
    for line in out.splitlines():
        parts = line.split("\t"); status = parts[0]
        if status.startswith("R") and len(parts) >= 3: items.append({"status": status, "old_path": parts[1], "path": parts[2]})
        elif len(parts) >= 2: items.append({"status": status, "path": parts[1]})
    return items


def owners(root: Path, items: list[dict]) -> list[dict]:
    rules = (read_json(root / ".ai/governance/ownership.json", {}) or {}).get("rules", []); output = []
    for item in items:
        matched = [{"owner": rule.get("owner"), "allowed_roles": rule.get("allowed_roles", []), "glob": rule.get("glob")} for rule in rules if glob_match(item["path"], str(rule.get("glob", "")))]
        output.append({"path": item["path"], "owners": matched, "status": "OWNED" if matched else "UNOWNED"})
    return output


def conflict_probe(root: Path, target: str, source: str) -> dict:
    base = (run(["git", "merge-base", target, source], root).stdout or "").strip(); result = run(["git", "merge-tree", base, target, source], root, check=False); text = (result.stdout or "") + "\n" + (result.stderr or ""); markers = [line for line in text.splitlines() if "<<<<<<<" in line or "changed in both" in line or "CONFLICT" in line]
    return {"merge_base": base, "potential_conflict": bool(markers), "markers": markers[:50], "command_returncode": result.returncode}


def commit_messages(root: Path, target: str, source: str) -> list[str]: return [x for x in run(["git", "log", "--format=%s", f"{target}..{source}"], root).stdout.splitlines() if x]


def task_gate(root: Path, task_id: str | None) -> list[str]:
    if not task_id: return []
    task = read_json(root / ".ai" / "tasks" / f"{safe_id(task_id).upper()}.json", {}) or {}; failures = []
    if not task: return ["unknown task"]
    if task.get("state") != "Testing": failures.append("task state must be Testing")
    if task.get("review", {}).get("status") != "PASS": failures.append("review evidence is not PASS")
    if task.get("tests", {}).get("status") != "PASS": failures.append("test evidence is not PASS")
    if task.get("closure", {}).get("merge") != "PASS": failures.append("feature closure gate is not PASS")
    locks = (read_json(common_dir(root) / "ai-engineering" / "file-locks.json", {}) or {}).get("locks", [])
    if any(x.get("task_id") == task.get("task_id") for x in locks): failures.append("task still holds file locks")
    return failures


def evaluate(root: Path, source: str, target: str, task_id: str | None = None) -> dict:
    missing = [x for x in (source, target) if not branch_ok(root, x)]
    if missing: return {"ok": False, "result": "BLOCKED", "missing_branches": missing, "merge_executed": False}
    failures = []
    if not flow_ok(source, target): failures.append(f"branch flow forbidden: {source} -> {target}")
    messages = commit_messages(root, target, source); bad = [x for x in messages if not COMMIT.fullmatch(x)]
    if not messages: failures.append("source has no commits to merge")
    if bad: failures.append("non-conventional commit messages: " + ", ".join(bad))
    failures += task_gate(root, task_id)
    items = changed(root, target, source); probe = conflict_probe(root, target, source); ownership = owners(root, items)
    if probe["potential_conflict"]: failures.append("potential merge conflict")
    critical = [x for x in items if re.search(r"(?:migration|schema|auth|permission|package-lock|pnpm-lock|ProjectSettings|Packages/manifest|\.asmdef$|api[-_/]?contract)", x["path"], re.I)]
    unowned = [x for x in ownership if x["status"] == "UNOWNED"]
    result = "FAIL" if failures else ("PASS_WITH_WARNINGS" if critical or unowned else "PASS")
    return {"ok": not failures, "result": result, "source": source, "target": target, "task_id": task_id, "failures": failures, "commits": messages, "changes": items, "ownership": ownership, "critical_changes": critical, "conflict_probe": probe, "merge_executed": False, "requirements": ["Review Agent PASS", "Test Agent PASS", "feature closure PASS", "CHANGELOG evidence", "clean locks"]}


def main() -> int:
    ap = argparse.ArgumentParser(); ap.add_argument("--root", default="."); ap.add_argument("--source", required=True); ap.add_argument("--target", default="develop"); ap.add_argument("--task-id"); ap.add_argument("--output"); args = ap.parse_args(); root = repo_root(Path(args.root).resolve()); data = evaluate(root, args.source, args.target, args.task_id); text = json.dumps(data, ensure_ascii=False, indent=2); print(text)
    if args.output: Path(args.output).write_text(text + "\n", encoding="utf-8")
    return 0 if data.get("result") in {"PASS", "PASS_WITH_WARNINGS"} else 2


if __name__ == "__main__": raise SystemExit(main())
