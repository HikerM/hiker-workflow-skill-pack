from __future__ import annotations

import argparse
import json
from pathlib import Path

from corelib import SCHEMA_VERSION, ai_root, atomic_write_json, atomic_write_text, git_info, read_json, utc_now
from context_memory import ensure_memory_policy
from detect_project import detect
from state_consistency import (
    assess as assess_state_consistency,
    recover_for_new_session,
    repair as repair_state_consistency,
)

DEFAULT_POLICY = {
    "schema_version": "1.0.0",
    "require_build": True,
    "require_tests": True,
    "require_review": True,
    "max_graph_depth": 2,
    "max_graph_nodes": 300,
    "auto_destructive_rollback": False,
    "auto_merge": False,
    "include_staged": True,
    "include_unstaged": True,
    "include_untracked": True,
}


def initialize(root: Path, force: bool = False, recovery: dict | None = None) -> dict:
    root = root.resolve()
    initial_consistency = assess_state_consistency(root)
    recovery = recovery or recover_for_new_session(root)
    ai = ai_root(root)
    ai.mkdir(parents=True, exist_ok=True)
    detected = detect(root)
    schema_path = ai / "schema.json"
    existing_schema = read_json(schema_path)
    if existing_schema and not force:
        major = str(existing_schema.get("version", "")).split(".")[0]
        if major and major != SCHEMA_VERSION.split(".")[0]:
            raise RuntimeError(f"incompatible existing .ai schema: {existing_schema.get('version')}")
    atomic_write_json(schema_path, {"version": SCHEMA_VERSION, "created_at": existing_schema.get("created_at", utc_now()) if isinstance(existing_schema, dict) else utc_now(), "updated_at": utc_now()})
    atomic_write_json(ai / "context" / "project.json", {"schema_version": SCHEMA_VERSION, "repository": git_info(root), "project_count": len(detected["projects"]), "monorepo": detected["monorepo"], "initialized_at": utc_now()})
    atomic_write_json(ai / "context" / "tech-stack.json", detected)
    if force or not (ai / "context" / "architecture.json").exists():
        atomic_write_json(ai / "context" / "architecture.json", {"schema_version": SCHEMA_VERSION, "status": "DISCOVERED_NOT_FROZEN", "modules": [], "constraints": [], "updated_at": utc_now()})
    if force or not (ai / "context" / "standards.json").exists():
        atomic_write_json(ai / "context" / "standards.json", {"schema_version": SCHEMA_VERSION, "status": "PENDING_OFFICIAL_VERIFICATION", "sources": [], "rules": [], "updated_at": utc_now()})
    if force or not (ai / "runtime" / "task.json").exists():
        atomic_write_json(ai / "runtime" / "task.json", {"schema_version": SCHEMA_VERSION, "id": None, "goal": None, "status": "IDLE", "plan_version": 0, "completed": [], "working": [], "pending": [], "risks": [], "updated_at": utc_now()})
    if force or not (ai / "runtime" / "control.json").exists():
        atomic_write_json(ai / "runtime" / "control.json", {"schema_version": SCHEMA_VERSION, "requested_action": None, "request_text": None, "updated_at": utc_now()})
    if force or not (ai / "runtime" / "active-context.md").exists():
        atomic_write_text(ai / "runtime" / "active-context.md", "# 当前有效上下文\n\n当前没有活动任务。\n")
    if force or not (ai / "governance" / "locked-decisions.json").exists():
        atomic_write_json(ai / "governance" / "locked-decisions.json", {"schema_version": "2.0.0", "decisions": []})
    if force or not (ai / "governance" / "ownership.json").exists():
        atomic_write_json(ai / "governance" / "ownership.json", {"schema_version": SCHEMA_VERSION, "rules": []})
    if force or not (ai / "quality" / "policy.json").exists():
        atomic_write_json(ai / "quality" / "policy.json", DEFAULT_POLICY)
    if force or not (ai / "evidence" / "index.json").exists():
        atomic_write_json(ai / "evidence" / "index.json", {"schema_version": SCHEMA_VERSION, "records": []})
    if force or not (ai / "knowledge" / "metadata.json").exists():
        atomic_write_json(ai / "knowledge" / "metadata.json", {"schema_version": SCHEMA_VERSION, "graph_format": "sqlite-file-relations-v1", "last_indexed_commit": None, "updated_at": None})
    (ai / "runtime" / "checkpoints").mkdir(parents=True, exist_ok=True)
    ensure_memory_policy(root)
    (ai / "logs").mkdir(parents=True, exist_ok=True)
    if not assess_state_consistency(root)["ok"]:
        repair_state_consistency(
            root,
            allow_untrusted_initialization=initial_consistency["status"] == "STATELESS_UNMANAGED",
        )
    detected["new_session_recovery"] = recovery
    return detected


def prepare_for_new_session(root: Path) -> dict:
    """Run one bounded recovery pass and bootstrap only when current derived state needs it."""
    root = root.resolve()
    recovery = recover_for_new_session(root)
    if recovery.get("bootstrap_required"):
        detected = initialize(root, recovery=recovery)
        recovery = {**recovery, "project_detection": {
            "project_count": len(detected.get("projects") or []),
            "monorepo": bool(detected.get("monorepo")),
        }}
    return recovery


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=".")
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args()
    data = initialize(Path(args.root), args.force)
    print(json.dumps({"ok": True, "projects": data["projects"], "ai_root": str(Path(args.root).resolve() / ".ai")}, ensure_ascii=False, indent=2))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
