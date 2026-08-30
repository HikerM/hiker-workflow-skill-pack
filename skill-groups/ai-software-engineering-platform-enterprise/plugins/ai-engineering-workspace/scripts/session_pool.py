from __future__ import annotations

import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from workspacelib import atomic_json, common_dir, effective_budget, locked_state, read_json, safe_id
from dispatch_state import OUTSTANDING_TURN_LEASES, load_dispatch
from file_lock import load_locks
from turn_lease import read_turn_lease


CORE_SCRIPTS = Path(__file__).resolve().parents[2] / "ai-engineering-core" / "scripts"
if str(CORE_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(CORE_SCRIPTS))
from process_identity import process_identity as runtime_identity  # noqa: E402


SCHEMA = "1.0.0"
ACTIVE_STATES = {"SETUP_PENDING", "BOUND", "READY", "RUNNING", "WAITING_APPROVAL", "UNKNOWN_RUNNING"}
REUSABLE_STATES = {"IDLE_REUSABLE"}
RELEASE_BLOCKING_STATES = {"PAUSED_DIRTY", "RELEASE_PENDING", "ARCHIVE_REQUESTED", "ARCHIVED_RUNTIME_UNVERIFIED"}
TERMINAL_OUTCOMES = {"PASS", "FAIL", "CANCELLED", "SUPERSEDED"}
RESERVATION_TTL_SECONDS = 120
ROLE_FAMILIES = {
    "master agent": "control",
    "planning agent": "control",
    "developer agent": "writer",
    "fix agent": "writer",
    "repair agent": "writer",
    "review agent": "assurance",
    "test agent": "assurance",
    "reverify agent": "assurance",
    "verification agent": "assurance",
    "merge agent": "control",
    "document agent": "control",
    "browser agent": "assurance",
    "e2e agent": "assurance",
}


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def pool_file(root: Path) -> Path:
    return common_dir(root) / "ai-engineering" / "session-pool.json"


def role_family(role: str) -> str:
    token = " ".join(role.strip().lower().split())
    if token in ROLE_FAMILIES:
        return ROLE_FAMILIES[token]
    if any(value in token for value in ("review", "test", "verify", "审核", "测试", "复验")):
        return "assurance"
    if any(value in token for value in ("developer", "writer", "fix", "repair", "开发", "实现", "修复")):
        return "writer"
    if any(value in token for value in ("browser", "e2e", "浏览器")):
        return "assurance"
    if any(value in token for value in ("master", "总控")):
        return "control"
    return "control"


def normalized_lane(family: str, ownership_lane: str | None = None) -> str:
    if family != "writer":
        return family
    return safe_id(ownership_lane or "default").lower()


def slot_key(project_id: str, repository: str, family: str, ownership_lane: str | None = None) -> str:
    lane = normalized_lane(family, ownership_lane)
    raw = "|".join((safe_id(project_id).upper(), str(Path(repository).resolve()).casefold(), safe_id(family).lower(), lane))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]


def legacy_slot_key(project_id: str, repository: str, family: str) -> str:
    raw = "|".join((safe_id(project_id).upper(), str(Path(repository).resolve()).casefold(), safe_id(family).lower()))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]


def resolved_slot_key(state: dict[str, Any], project_id: str, repository: str, family: str, ownership_lane: str | None = None) -> str:
    key = slot_key(project_id, repository, family, ownership_lane)
    if key in state.get("slots", {}):
        return key
    if normalized_lane(family, ownership_lane) in {"default", family}:
        legacy = legacy_slot_key(project_id, repository, family)
        if legacy in state.get("slots", {}):
            return legacy
    compatible_legacy = {"control": {"master"}, "assurance": {"browser"}}.get(family, set())
    normalized_project = safe_id(project_id).upper()
    normalized_repository = str(Path(repository).resolve()).casefold()
    for existing_key, slot in state.get("slots", {}).items():
        if (
            slot.get("project_id") == normalized_project
            and str(Path(slot.get("repository") or repository).resolve()).casefold() == normalized_repository
            and slot.get("role_family") in compatible_legacy
        ):
            return existing_key
    return key


def load_pool(root: Path) -> dict[str, Any]:
    path = pool_file(root)
    if path.is_file():
        try:
            state = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise RuntimeError(f"session pool is damaged; creation is blocked until recovery: {exc}")
        if not isinstance(state, dict):
            raise RuntimeError("session pool is damaged; root value must be an object")
    else:
        state = {}
    state.setdefault("schema_version", SCHEMA)
    state.setdefault("slots", {})
    if not isinstance(state.get("schema_version"), str):
        raise RuntimeError("session pool is damaged; schema_version must be a string")
    if not isinstance(state.get("slots"), dict):
        raise RuntimeError("session pool is damaged; slots must be an object")
    if any(not isinstance(key, str) or not isinstance(slot, dict) for key, slot in state["slots"].items()):
        raise RuntimeError("session pool is damaged; every slot must be an object keyed by a string")
    return state


def runtime_registration_id(slot: dict[str, Any]) -> str | None:
    processes = slot.get("runtime_processes")
    if not isinstance(processes, list) or not processes:
        return None
    payload = {
        "slot_key": slot.get("slot_key"),
        "task_id": slot.get("runtime_registration_task_id", slot.get("current_task_id")),
        "thread_id": slot.get("thread_id"),
        "bound_at": slot.get("bound_at"),
        "runtime_processes": processes,
    }
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def project_policy(root: Path) -> dict[str, int]:
    project = read_json(root / ".ai" / "governance" / "project-state.json", {}) or {}
    configured = project.get("session_budget", {})
    return effective_budget("execution", configured)


def _resident(slot: dict[str, Any]) -> bool:
    return slot.get("state") != "RELEASED"


def _expire_unbound_reservations(state: dict[str, Any]) -> bool:
    changed = False
    current = datetime.now(timezone.utc)
    for slot in state.get("slots", {}).values():
        if slot.get("state") != "SETUP_PENDING":
            continue
        try:
            created = datetime.fromisoformat(str(slot.get("reserved_at") or slot.get("bound_at")))
            if created.tzinfo is None:
                created = created.replace(tzinfo=timezone.utc)
        except (TypeError, ValueError):
            created = current
        if (current - created).total_seconds() >= RESERVATION_TTL_SECONDS:
            slot["state"] = "REQUERY_REQUIRED"
            slot["requery_required_at"] = now()
            changed = True
    return changed


@locked_state
def plan(
    root: Path,
    project_id: str,
    task_id: str,
    role: str,
    repository: str,
    base_sha: str,
    observation: str,
    thread_id: str | None = None,
    client_thread_id: str | None = None,
    ownership_lane: str | None = None,
) -> dict[str, Any]:
    state = load_pool(root)
    expired = _expire_unbound_reservations(state)
    family = role_family(role)
    lane = normalized_lane(family, ownership_lane)
    key = resolved_slot_key(state, project_id, repository, family, lane)
    existing = state["slots"].get(key)
    if existing and existing.get("state") == "REQUERY_REQUIRED" and observation == "EMPTY_CONFIRMED":
        state["slots"].pop(key, None)
        existing = None
        expired = True
    policy = project_policy(root)
    project_slots = [slot for slot in state["slots"].values() if slot.get("project_id") == safe_id(project_id).upper() and _resident(slot)]
    pending = sum(1 for slot in project_slots if slot.get("state") == "SETUP_PENDING")
    writer_slots = [slot for slot in project_slots if slot.get("role_family") == "writer"]

    if observation in {"API_ERROR", "QUERY_TIMEOUT"}:
        action, reason = "BLOCK_QUERY", "桌面任务查询失败或超时，禁止猜测式创建替代会话"
    elif existing and existing.get("state") == "REQUERY_REQUIRED":
        action, reason = "BLOCK_QUERY", "会话创建预留已过期；必须重新查询宿主状态后才能继续"
    elif existing and existing.get("state") in RELEASE_BLOCKING_STATES:
        action, reason = "BLOCK_RELEASE_PENDING", "角色槽位尚未完成终态回收"
    elif existing and existing.get("state") == "SETUP_PENDING":
        action, reason = "WAIT_PENDING", "角色槽位仍在创建，禁止创建第二个会话"
    elif existing and existing.get("state") in ACTIVE_STATES:
        if existing.get("current_task_id") == safe_id(task_id).upper():
            action, reason = "CONTINUE_EXISTING", "同一任务已绑定当前角色槽位"
        else:
            action, reason = "QUEUE", "角色槽位仍在处理另一任务"
    elif existing and existing.get("state") in REUSABLE_STATES and existing.get("thread_id"):
        action, reason = "REUSE_THREAD", "复用同项目、同仓库、同角色的空闲会话"
    elif observation in {"BOUND", "READY", "RUNNING", "WAITING_APPROVAL", "UNKNOWN_RUNNING"} and thread_id:
        action, reason = "BIND_DISCOVERED", "绑定桌面端已存在的角色会话"
    elif observation == "SETUP_PENDING" and client_thread_id:
        if pending >= policy["max_pending_creates"]:
            action, reason = "QUEUE", "项目已有待创建会话，禁止并发创建更多运行时"
        else:
            action, reason = "TRACK_PENDING", "登记唯一待创建角色槽位"
    elif observation == "EMPTY_CONFIRMED":
        if len(project_slots) >= policy["max_resident_slots"]:
            action, reason = "QUEUE", "项目常驻角色槽位已达预算"
        elif family == "writer" and len(writer_slots) >= policy["max_writer_slots"]:
            action, reason = "QUEUE", "项目稳定写通道已达预算"
        elif pending >= policy["max_pending_creates"]:
            action, reason = "QUEUE", "项目已有待创建会话"
        else:
            action, reason = "CREATE_THREAD", "没有可复用槽位且桌面端明确返回空结果"
    else:
        action, reason = "BLOCK_UNKNOWN", "无法证明已有会话不存在或可以安全复用"

    if action in {"CREATE_THREAD", "TRACK_PENDING"} and not existing:
        state["slots"][key] = {
            "slot_key": key,
            "project_id": safe_id(project_id).upper(),
            "repository": str(Path(repository).resolve()),
            "role_family": family,
            "ownership_lane": lane,
            "role": role,
            "state": "SETUP_PENDING",
            "thread_id": thread_id,
            "client_thread_id": client_thread_id,
            "current_task_id": safe_id(task_id).upper(),
            "base_sha": base_sha,
            "reserved_at": now(),
            "terminal_task_count": 0,
        }
        state["updated_at"] = now()
        atomic_json(pool_file(root), state)
    elif expired:
        state["updated_at"] = now()
        atomic_json(pool_file(root), state)

    return {
        "slot_key": key,
        "project_id": safe_id(project_id).upper(),
        "task_id": safe_id(task_id).upper(),
        "role": role,
        "role_family": family,
        "ownership_lane": lane,
        "repository": str(Path(repository).resolve()),
        "base_sha": base_sha,
        "action": action,
        "reason": reason,
        "existing_slot": existing,
        "policy": policy,
        "resident_slots": len(project_slots),
        "pending_creates": pending,
    }


@locked_state
def bind(
    root: Path,
    project_id: str,
    task_id: str,
    role: str,
    repository: str,
    base_sha: str,
    thread_id: str | None,
    client_thread_id: str | None,
    runtime_state: str,
    worktree: str | None = None,
    ownership_lane: str | None = None,
    runtime_pids: list[int] | None = None,
) -> dict[str, Any]:
    state = load_pool(root)
    family = role_family(role)
    lane = normalized_lane(family, ownership_lane)
    key = resolved_slot_key(state, project_id, repository, family, lane)
    current = state["slots"].get(key, {})
    if current.get("state") in ACTIVE_STATES and current.get("current_task_id") not in {None, safe_id(task_id).upper()}:
        raise RuntimeError("role slot is active for another task")
    if current.get("state") in RELEASE_BLOCKING_STATES:
        raise RuntimeError("role slot cannot be rebound before terminal release completes")
    resolved_thread_id = thread_id or current.get("thread_id")
    supplied_pids = None if runtime_pids is None else sorted(set(int(pid) for pid in runtime_pids if int(pid) > 0))
    if supplied_pids is None:
        registered_processes = list(current.get("runtime_processes") or []) if current.get("thread_id") == resolved_thread_id else []
    else:
        registered_processes = []
        invalid_pids = []
        for pid in supplied_pids:
            identity = runtime_identity(pid)
            if identity is None:
                invalid_pids.append(pid)
            else:
                registered_processes.append(identity)
        if invalid_pids:
            raise RuntimeError(f"runtime process identity cannot be verified for PID(s): {invalid_pids}")
    entry = {
        "slot_key": key,
        "project_id": safe_id(project_id).upper(),
        "repository": str(Path(repository).resolve()),
        "role_family": family,
        "ownership_lane": lane,
        "role": role,
        "state": runtime_state,
        "thread_id": resolved_thread_id,
        "client_thread_id": client_thread_id or current.get("client_thread_id"),
        "current_task_id": safe_id(task_id).upper(),
        "base_sha": base_sha,
        "worktree": worktree or current.get("worktree"),
        "bound_at": datetime.now(timezone.utc).isoformat(timespec="microseconds"),
        "terminal_task_count": int(current.get("terminal_task_count", 0)),
        "runtime_processes": registered_processes,
        "runtime_identity_status": "VERIFIED" if registered_processes else "MISSING",
        "runtime_registration_task_id": safe_id(task_id).upper(),
    }
    entry["runtime_registration_id"] = runtime_registration_id(entry)
    state["slots"][key] = entry
    state["updated_at"] = now()
    atomic_json(pool_file(root), state)
    return entry


@locked_state
def complete(
    root: Path,
    project_id: str,
    task_id: str,
    role: str,
    repository: str,
    outcome: str,
    checkpoint_id: str,
    locks_released: bool,
    resources_released: bool,
    worktree_state: str,
    candidate_id: str | None = None,
    project_terminal: bool = False,
    ownership_lane: str | None = None,
) -> dict[str, Any]:
    outcome = outcome.upper()
    if outcome not in TERMINAL_OUTCOMES:
        raise ValueError(f"unsupported terminal outcome: {outcome}")
    state = load_pool(root)
    family = role_family(role)
    key = resolved_slot_key(state, project_id, repository, family, ownership_lane)
    slot = state["slots"].get(key)
    if not slot or slot.get("current_task_id") != safe_id(task_id).upper():
        raise RuntimeError("task is not bound to the requested role slot")
    blockers = []
    task_key = safe_id(task_id).upper()
    turns = [
        turn for turn in load_dispatch(root).get("turn_leases", {}).values()
        if isinstance(turn, dict) and turn.get("task_id") == task_key
    ]
    active_turns = [turn for turn in turns if turn.get("status") in OUTSTANDING_TURN_LEASES]
    active_runtime_leases = [
        turn for turn in turns
        if (read_turn_lease(root, str(turn.get("thread_key") or "")) or {}).get("lease_state") == "ACTIVE"
    ]
    task_locks = [item for item in load_locks(root).get("locks", []) if item.get("task_id") == task_key]
    if not checkpoint_id.strip():
        blockers.append("missing checkpoint")
    if active_turns:
        blockers.append("Turn is not confirmed or recovered")
    if active_runtime_leases:
        blockers.append("Turn lease is still active")
    if not locks_released:
        blockers.append("file locks not released")
    elif task_locks:
        blockers.append("file locks remain registered")
    if not resources_released:
        blockers.append("runtime release pending" if project_terminal else "external resources not released")
    if worktree_state not in {"CLEAN", "CLOSED", "PAUSED_DIRTY"}:
        blockers.append("unsupported worktree state")
    if worktree_state == "PAUSED_DIRTY":
        blockers.append("dirty worktree must remain paused and cannot be reused")
    slot["last_outcome"] = outcome
    slot["last_checkpoint_id"] = checkpoint_id
    slot["last_candidate_id"] = candidate_id
    completion_key = hashlib.sha256(f"{task_key}|{outcome}|{checkpoint_id}".encode("utf-8")).hexdigest()[:24]
    if slot.get("last_completion_key") != completion_key:
        slot["terminal_task_count"] = int(slot.get("terminal_task_count", 0)) + 1
    slot["last_completion_key"] = completion_key
    slot["completed_at"] = now()
    slot["release_blockers"] = blockers
    only_terminal_probe_pending = project_terminal and blockers == ["runtime release pending"]
    if blockers and not only_terminal_probe_pending:
        slot["state"] = "PAUSED_DIRTY" if worktree_state == "PAUSED_DIRTY" else "RELEASE_PENDING"
    else:
        slot["state"] = "RELEASE_PENDING" if project_terminal else "IDLE_REUSABLE"
        slot["current_task_id"] = None
    state["updated_at"] = now()
    atomic_json(pool_file(root), state)
    return {
        "ok": not blockers or only_terminal_probe_pending,
        "slot": slot,
        "next_action": "ARCHIVE_AND_VERIFY_RUNTIME" if project_terminal and (not blockers or only_terminal_probe_pending) else ("REUSE_THREAD" if not blockers else "RESOLVE_RELEASE_BLOCKERS"),
        "blockers": blockers,
    }


@locked_state
def release_ack(
    root: Path,
    project_id: str,
    role: str,
    repository: str,
    thread_archived: bool,
    runtime_release_verified: bool,
    worktree_state: str,
    ownership_lane: str | None = None,
    probe_id: str | None = None,
) -> dict[str, Any]:
    state = load_pool(root)
    family = role_family(role)
    key = resolved_slot_key(state, project_id, repository, family, ownership_lane)
    slot = state["slots"].get(key)
    if not slot:
        raise RuntimeError("role slot not found")
    if slot.get("state") not in {"RELEASE_PENDING", "ARCHIVE_REQUESTED", "ARCHIVED_RUNTIME_UNVERIFIED"}:
        raise RuntimeError("role slot is not waiting for terminal release")
    probe = read_json(root / ".ai" / "evidence" / "runtime-release" / f"{safe_id(probe_id)}.json", {}) if probe_id else {}
    probe_hash_valid = False
    if isinstance(probe, dict) and probe:
        hash_payload = dict(probe)
        embedded_probe_id = hash_payload.pop("probe_id", None)
        raw = json.dumps(hash_payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        calculated_probe_id = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]
        probe_hash_valid = embedded_probe_id == probe_id == calculated_probe_id
    authorities = probe.get("evidence_authority") or {}
    probe_valid = bool(
        probe_hash_valid and probe.get("result") == "PASS" and probe.get("slot_key") == key
        and probe.get("project_id") == safe_id(project_id).upper()
        and probe.get("thread_id") == slot.get("thread_id")
        and probe.get("runtime_registration_id") == slot.get("runtime_registration_id")
        and authorities.get("desktop_thread") == "HOST_ASSERTED"
        and authorities.get("runtime_processes") == "LOCAL_VERIFIED"
        and authorities.get("worktree") == "LOCAL_VERIFIED"
    )
    if probe_valid:
        thread_archived = probe.get("thread_state") in {"ARCHIVED", "NOT_FOUND"}
        runtime_release_verified = probe.get("runtime_status") == "RELEASED"
        observed_worktree = (probe.get("worktree") or {}).get("status")
        worktree_state = "CLOSED" if observed_worktree == "CLOSED" else "KEPT"
    blockers = [
        value for value in slot.get("release_blockers", [])
        if value not in {"thread archive not confirmed", "worktree disposition not confirmed", "runtime release pending", "current runtime release probe not found or does not match the role slot"}
    ]
    if not probe_valid:
        blockers.append("current runtime release probe not found or does not match the role slot")
    if not thread_archived:
        blockers.append("thread archive not confirmed")
    if worktree_state not in {"KEPT", "CLOSED"}:
        blockers.append("worktree disposition not confirmed")
    if thread_archived and not runtime_release_verified:
        slot["state"] = "ARCHIVED_RUNTIME_UNVERIFIED"
    elif not blockers and runtime_release_verified:
        slot["state"] = "RELEASED"
        slot["released_at"] = now()
    else:
        slot["state"] = "RELEASE_PENDING"
    slot["thread_archived"] = thread_archived
    slot["runtime_release_verified"] = runtime_release_verified
    slot["runtime_release_probe_id"] = probe_id if probe_valid else None
    slot["worktree_disposition"] = worktree_state
    slot["release_blockers"] = list(dict.fromkeys(blockers))
    state["updated_at"] = now()
    atomic_json(pool_file(root), state)
    return {"ok": slot["state"] == "RELEASED", "slot": slot, "blockers": slot["release_blockers"]}


@locked_state
def status(root: Path, project_id: str | None = None) -> dict[str, Any]:
    state = load_pool(root)
    slots = list(state["slots"].values())
    if project_id:
        slots = [slot for slot in slots if slot.get("project_id") == safe_id(project_id).upper()]
    counts: dict[str, int] = {}
    for slot in slots:
        counts[str(slot.get("state", "UNKNOWN"))] = counts.get(str(slot.get("state", "UNKNOWN")), 0) + 1
    blockers = [slot for slot in slots if slot.get("state") in RELEASE_BLOCKING_STATES]
    return {"schema_version": SCHEMA, "slots": slots, "counts": counts, "release_blockers": blockers, "ok": not blockers}
