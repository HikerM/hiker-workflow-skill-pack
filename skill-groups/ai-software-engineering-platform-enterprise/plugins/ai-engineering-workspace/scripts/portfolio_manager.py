from __future__ import annotations

import argparse
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from workspacelib import atomic_json, read_json, repo_root, run, safe_id

SCHEMA = "1.0.0"


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def load(path: Path) -> dict:
    return read_json(path, {"schema_version": SCHEMA, "active_project": None, "projects": {}}) or {"schema_version": SCHEMA, "active_project": None, "projects": {}}


def snapshot(path: Path) -> dict:
    branch = run(["git", "branch", "--show-current"], path, check=False).stdout.strip() or "DETACHED"
    head = run(["git", "rev-parse", "HEAD"], path, check=False).stdout.strip() or None
    return {"branch": branch, "head": head, "dirty": bool(run(["git", "status", "--porcelain"], path, check=False).stdout.strip())}


def main() -> int:
    ap = argparse.ArgumentParser(); ap.add_argument("--registry", default=".ai/portfolio/projects.json"); sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("register"); p.add_argument("--project-id", required=True); p.add_argument("--path", required=True)
    p = sub.add_parser("activate"); p.add_argument("--project-id", required=True)
    p = sub.add_parser("check"); p.add_argument("--project-id", required=True); p.add_argument("--cwd", default=".")
    sub.add_parser("list")
    args = ap.parse_args(); registry = Path(args.registry).expanduser().resolve(); data = load(registry)
    try:
        if args.cmd == "register":
            pid = safe_id(args.project_id); root = repo_root(Path(args.path).expanduser().resolve()); state = read_json(root / ".ai/governance/project-state.json", {}) or {}
            if state.get("project_id") != pid: raise RuntimeError("registered project id does not match its PROJECT_STATE")
            for existing, item in data["projects"].items():
                if Path(item["path"]).resolve() == root and existing != pid: raise RuntimeError("repository is already registered under another project id")
            data["projects"][pid] = {"path": str(root), "registered_at": now()}; atomic_json(registry, data)
        elif args.cmd == "activate":
            pid = safe_id(args.project_id)
            if pid not in data["projects"]: raise RuntimeError("unknown project id")
            data["active_project"] = pid; data["activated_at"] = now(); atomic_json(registry, data)
        elif args.cmd == "check":
            pid = safe_id(args.project_id); item = data["projects"].get(pid)
            if not item: raise RuntimeError("unknown project id")
            current = repo_root(Path(args.cwd).resolve()); expected = Path(item["path"]).resolve()
            result = {"ok": data.get("active_project") == pid and current == expected, "active_project": data.get("active_project"), "expected_root": str(expected), "current_root": str(current)}
            print(json.dumps(result, ensure_ascii=False, indent=2)); return 0 if result["ok"] else 2
        output = {"schema_version": SCHEMA, "active_project": data.get("active_project"), "projects": {pid: {**item, **snapshot(Path(item["path"]))} for pid, item in data["projects"].items()}}
        print(json.dumps({"ok": True, "result": output}, ensure_ascii=False, indent=2)); return 0
    except (RuntimeError, ValueError, subprocess.CalledProcessError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False, indent=2)); return 2


if __name__ == "__main__":
    raise SystemExit(main())
