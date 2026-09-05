from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from session_pool import load_pool, resolved_slot_key, role_family, runtime_identity, runtime_registration_id
from process_identity import pid_presence
from workspacelib import atomic_json, locked_state, repo_root, run, safe_id


SCHEMA = "1.0.0"


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def worktree_probe(repository: Path, worktree: str | None) -> dict[str, Any]:
    if not worktree:
        return {"status": "NOT_REGISTERED", "path": None, "clean": None}
    target = Path(worktree).resolve()
    result = run(["git", "worktree", "list", "--porcelain"], repository, check=False)
    if result.returncode != 0:
        return {"status": "PROBE_ERROR", "path": str(target), "clean": None}
    registered = {
        Path(line.split(" ", 1)[1]).resolve()
        for line in result.stdout.splitlines() if line.startswith("worktree ")
    }
    if target not in registered and not target.exists():
        return {"status": "CLOSED", "path": str(target), "clean": True}
    if target not in registered:
        return {"status": "UNREGISTERED_PATH_EXISTS", "path": str(target), "clean": False}
    status = run(["git", "status", "--porcelain"], target, check=False)
    if status.returncode != 0:
        return {"status": "PROBE_ERROR", "path": str(target), "clean": None}
    clean = not status.stdout.strip()
    return {"status": "KEPT_CLEAN" if clean else "DIRTY", "path": str(target), "clean": clean}


def valid_runtime_identity(value: Any) -> bool:
    return bool(
        isinstance(value, dict)
        and value.get("identity_version") == "pid-start-v1"
        and isinstance(value.get("pid"), int)
        and value["pid"] > 0
        and isinstance(value.get("process_fingerprint"), str)
        and len(value["process_fingerprint"]) == 64
        and all(ch in "0123456789abcdef" for ch in value["process_fingerprint"])
    )


@locked_state
def create_probe(
    root: Path,
    project_id: str,
    role: str,
    repository: str,
    thread_state: str,
    desktop_observation_id: str,
    runtime_pids: list[int] | None = None,
    ownership_lane: str = "default",
) -> dict[str, Any]:
    state = load_pool(root)
    family = role_family(role)
    key = resolved_slot_key(state, project_id, repository, family, ownership_lane)
    slot = state.get("slots", {}).get(key)
    if not slot:
        raise RuntimeError("role slot not found")
    if not desktop_observation_id.strip():
        raise RuntimeError("desktop observation id is required")
    registered = slot.get("runtime_processes")
    registered = registered if isinstance(registered, list) else []
    valid_registration = bool(registered) and all(valid_runtime_identity(value) for value in registered)
    registered_pids = [int(value["pid"]) for value in registered if valid_runtime_identity(value)]
    valid_registration = valid_registration and len(registered_pids) == len(set(registered_pids))
    stored_registration_id = slot.get("runtime_registration_id")
    valid_registration = valid_registration and bool(stored_registration_id) and stored_registration_id == runtime_registration_id(slot)
    asserted_pids = sorted(set(int(value) for value in (runtime_pids or []) if int(value) > 0))
    assertion_matches = not asserted_pids or asserted_pids == sorted(registered_pids)

    process_observations = []
    for registered_identity in registered if valid_registration else []:
        pid = int(registered_identity["pid"])
        current_identity = runtime_identity(pid)
        presence = pid_presence(pid)
        if current_identity is None:
            status = "EXITED" if presence is False else "UNVERIFIABLE"
        elif current_identity != registered_identity:
            status = "IDENTITY_MISMATCH"
        elif presence is False:
            status = "EXITED"
        elif presence is True:
            status = "RUNNING"
        else:
            status = "UNVERIFIABLE"
        process_observations.append({"pid": pid, "status": status})

    statuses = {value["status"] for value in process_observations}
    if not valid_registration:
        runtime_status = "NOT_REGISTERED"
    elif "IDENTITY_MISMATCH" in statuses:
        runtime_status = "IDENTITY_MISMATCH"
    elif "UNVERIFIABLE" in statuses:
        runtime_status = "UNVERIFIABLE"
    elif "RUNNING" in statuses:
        runtime_status = "RUNNING"
    elif statuses == {"EXITED"}:
        runtime_status = "RELEASED"
    else:
        runtime_status = "NOT_OBSERVABLE"
    worktree = worktree_probe(Path(repository).resolve(), slot.get("worktree"))
    thread_ok = thread_state in {"ARCHIVED", "NOT_FOUND"}
    worktree_ok = worktree["status"] in {"CLOSED", "KEPT_CLEAN", "NOT_REGISTERED"}
    blockers = []
    if not thread_ok:
        blockers.append("desktop thread is not archived")
    if runtime_status != "RELEASED":
        blockers.append("runtime process release is not verified")
    if not assertion_matches:
        blockers.append("caller runtime PID assertion does not match registered slot identities")
    if not worktree_ok:
        blockers.append("worktree is dirty or has an unregistered remaining path")
    payload = {
        "schema_version": SCHEMA, "project_id": safe_id(project_id).upper(), "slot_key": key,
        "thread_id": slot.get("thread_id"), "desktop_observation_id": desktop_observation_id,
        "thread_state": thread_state,
        "runtime_registration_id": stored_registration_id,
        "registered_runtime_pids": registered_pids,
        "asserted_runtime_pids": asserted_pids,
        "runtime_process_observations": process_observations,
        "runtime_status": runtime_status, "worktree": worktree, "observed_at": now(),
        "evidence_authority": {
            "desktop_thread": "HOST_ASSERTED",
            "runtime_processes": "LOCAL_VERIFIED",
            "worktree": "LOCAL_VERIFIED",
        },
        "result": "PASS" if not blockers else "BLOCKED", "blockers": blockers,
    }
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    probe_id = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]
    payload["probe_id"] = probe_id
    atomic_json(root / ".ai" / "evidence" / "runtime-release" / f"{probe_id}.json", payload)
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(description="核验桌面任务、Worktree与已登记运行时的终态释放")
    parser.add_argument("--root", default=".")
    parser.add_argument("--project-id", required=True)
    parser.add_argument("--role", required=True)
    parser.add_argument("--repository")
    parser.add_argument("--ownership-lane", default="default")
    parser.add_argument("--thread-state", choices=["ARCHIVED", "NOT_FOUND", "ACTIVE", "UNKNOWN"], required=True)
    parser.add_argument("--desktop-observation-id", required=True)
    parser.add_argument("--assert-runtime-pid", "--runtime-pid", dest="assert_runtime_pid", action="append", type=int, default=[])
    args = parser.parse_args()
    root = repo_root(Path(args.root).resolve())
    try:
        result = create_probe(root, args.project_id, args.role, args.repository or str(root), args.thread_state, args.desktop_observation_id, args.assert_runtime_pid, args.ownership_lane)
        print(json.dumps({"ok": result["result"] == "PASS", "result": result}, ensure_ascii=False, indent=2))
        return 0 if result["result"] == "PASS" else 2
    except (OSError, RuntimeError, ValueError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False, indent=2))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
