from __future__ import annotations

import argparse
import ctypes
import hashlib
import json
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from session_pool import load_pool, resolved_slot_key, role_family
from workspacelib import atomic_json, locked_state, repo_root, safe_id


SCHEMA = "1.0.0"


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    if os.name == "nt":
        process_query_limited_information = 0x1000
        still_active = 259
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        handle = kernel32.OpenProcess(process_query_limited_information, False, pid)
        if not handle:
            return False
        try:
            exit_code = ctypes.c_ulong()
            if not kernel32.GetExitCodeProcess(handle, ctypes.byref(exit_code)):
                return False
            return exit_code.value == still_active
        finally:
            kernel32.CloseHandle(handle)
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def worktree_probe(repository: Path, worktree: str | None) -> dict[str, Any]:
    if not worktree:
        return {"status": "NOT_REGISTERED", "path": None, "clean": None}
    target = Path(worktree).resolve()
    result = subprocess.run(
        ["git", "worktree", "list", "--porcelain"], cwd=str(repository), text=True,
        encoding="utf-8", errors="replace", stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False,
    )
    registered = {
        Path(line.split(" ", 1)[1]).resolve()
        for line in result.stdout.splitlines() if line.startswith("worktree ")
    }
    if target not in registered and not target.exists():
        return {"status": "CLOSED", "path": str(target), "clean": True}
    if target not in registered:
        return {"status": "UNREGISTERED_PATH_EXISTS", "path": str(target), "clean": False}
    status = subprocess.run(
        ["git", "status", "--porcelain"], cwd=str(target), text=True,
        encoding="utf-8", errors="replace", stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False,
    )
    clean = status.returncode == 0 and not status.stdout.strip()
    return {"status": "KEPT_CLEAN" if clean else "DIRTY", "path": str(target), "clean": clean}


@locked_state
def create_probe(
    root: Path,
    project_id: str,
    role: str,
    repository: str,
    thread_state: str,
    desktop_observation_id: str,
    runtime_pids: list[int],
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
    pids = sorted(set(int(value) for value in runtime_pids if int(value) > 0))
    alive = [value for value in pids if pid_alive(value)]
    runtime_status = "RELEASED" if pids and not alive else "RUNNING" if alive else "NOT_OBSERVABLE"
    worktree = worktree_probe(Path(repository).resolve(), slot.get("worktree"))
    thread_ok = thread_state in {"ARCHIVED", "NOT_FOUND"}
    worktree_ok = worktree["status"] in {"CLOSED", "KEPT_CLEAN", "NOT_REGISTERED"}
    blockers = []
    if not thread_ok:
        blockers.append("desktop thread is not archived")
    if runtime_status != "RELEASED":
        blockers.append("runtime process release is not verified")
    if not worktree_ok:
        blockers.append("worktree is dirty or has an unregistered remaining path")
    payload = {
        "schema_version": SCHEMA, "project_id": safe_id(project_id).upper(), "slot_key": key,
        "thread_id": slot.get("thread_id"), "desktop_observation_id": desktop_observation_id,
        "thread_state": thread_state, "runtime_pids": pids, "alive_pids": alive,
        "runtime_status": runtime_status, "worktree": worktree, "observed_at": now(),
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
    parser.add_argument("--runtime-pid", action="append", type=int, default=[])
    args = parser.parse_args()
    root = repo_root(Path(args.root).resolve())
    try:
        result = create_probe(root, args.project_id, args.role, args.repository or str(root), args.thread_state, args.desktop_observation_id, args.runtime_pid, args.ownership_lane)
        print(json.dumps({"ok": result["result"] == "PASS", "result": result}, ensure_ascii=False, indent=2))
        return 0 if result["result"] == "PASS" else 2
    except (OSError, RuntimeError, ValueError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False, indent=2))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
