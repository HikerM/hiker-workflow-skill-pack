from __future__ import annotations

from pathlib import Path
from typing import Any

from corelib import ai_root, atomic_write_json, read_json, state_lock, utc_now


AUTHORITIES = {
    "ARCHITECTURE_CONSTRAINT",
    "PROJECT_DECISION",
    "SYSTEM_INVARIANT",
    "USER_LOCKED_DECISION",
}
MAX_REFS = 32
MAX_RETRIEVED = 20
MAX_MEMORY_BYTES = 1024 * 1024
MAX_DECISIONS = 4096


def load(root: Path) -> dict[str, Any]:
    path = ai_root(root) / "governance" / "locked-decisions.json"
    try:
        if path.stat().st_size > MAX_MEMORY_BYTES:
            return {"schema_version": "2.0.0", "status": "OVERFLOW_REQUIRES_COMPACTION", "decisions": []}
    except OSError:
        return {"schema_version": "2.0.0", "decisions": []}
    payload = read_json(path, {}) or {}
    return payload if isinstance(payload, dict) else {"schema_version": "2.0.0", "status": "INVALID", "decisions": []}


def _refs(value: Any, limit: int = MAX_REFS) -> list[str]:
    if not isinstance(value, list):
        return []
    return list(dict.fromkeys(str(item).strip()[:240] for item in value if str(item).strip()))[:limit]


def _overlaps(left: str, right: str) -> bool:
    left = left.strip().replace("\\", "/").strip("/")
    right = right.strip().replace("\\", "/").strip("/")
    return bool(left and right and (left == right or left.startswith(right + "/") or right.startswith(left + "/")))


def _goal_matches(binding: dict[str, Any], current: dict[str, Any]) -> bool:
    if not binding:
        return True
    if not current or current.get("status") != "ACTIVE":
        return False
    if binding.get("goal_id") and binding.get("goal_id") != current.get("goal_id"):
        return False
    if binding.get("revision") is not None and int(binding.get("revision") or 0) != int(current.get("revision") or 0):
        return False
    return not binding.get("fingerprint") or binding.get("fingerprint") == current.get("fingerprint")


def retrieve(
    payload: dict[str, Any],
    *,
    current_goal: dict[str, Any] | None = None,
    current_task: str | None = None,
    current_generation: int | None = None,
    current_scope: list[str] | None = None,
    limit: int = MAX_RETRIEVED,
) -> dict[str, Any]:
    decisions = payload.get("decisions", []) if isinstance(payload, dict) else []
    decisions = decisions if isinstance(decisions, list) else []
    overflow = payload.get("status") == "OVERFLOW_REQUIRES_COMPACTION" or len(decisions) > MAX_DECISIONS
    if overflow:
        return {
            "schema_version": "2.0.0", "selected": [], "selected_count": 0,
            "considered_count": min(len(decisions), MAX_DECISIONS),
            "excluded": {"MEMORY_OVERFLOW": max(1, len(decisions) - MAX_DECISIONS)},
            "bounded": True, "limit": max(1, min(int(limit), MAX_RETRIEVED)),
            "requires_compaction": True,
        }
    selected: list[dict[str, Any]] = []
    excluded: dict[str, int] = {}
    scope = _refs(current_scope)
    limit = max(1, min(int(limit), MAX_RETRIEVED))
    for raw in decisions:
        if not isinstance(raw, dict):
            excluded["INVALID"] = excluded.get("INVALID", 0) + 1
            continue
        reason = None
        if raw.get("status", "LOCKED") != "LOCKED" or raw.get("superseded_by"):
            reason = "SUPERSEDED_OR_INACTIVE"
        authority = str(raw.get("authority") or "USER_LOCKED_DECISION").strip().upper()
        if not reason and authority not in AUTHORITIES:
            reason = "UNTRUSTED_AUTHORITY"
        binding = raw.get("goal_binding") if isinstance(raw.get("goal_binding"), dict) else {}
        if not reason and not _goal_matches(binding, current_goal or {}):
            reason = "GOAL_MISMATCH"
        tasks = _refs(raw.get("task_relevance"))
        if not reason and tasks and (not current_task or current_task not in tasks):
            reason = "TASK_MISMATCH"
        generation = raw.get("generation", 0)
        generation = generation if isinstance(generation, int) and not isinstance(generation, bool) and generation >= 0 else -1
        if not reason and generation < 0:
            reason = "INVALID_GENERATION"
        elif not reason and generation > 0 and (current_generation is None or generation != current_generation):
            reason = "GENERATION_MISMATCH"
        decision_scope = _refs(raw.get("scope"))
        if not reason and decision_scope and (not scope or not any(_overlaps(left, right) for left in decision_scope for right in scope)):
            reason = "SCOPE_MISMATCH"
        if reason:
            excluded[reason] = excluded.get(reason, 0) + 1
            continue
        selected.append({
            "id": str(raw.get("id") or "")[:160],
            "content": str(raw.get("content") or "")[:1000],
            "authority": authority,
            "generation": generation,
            "scope": decision_scope,
        })
    selected = selected[-limit:]
    return {
        "schema_version": "2.0.0",
        "selected": selected,
        "selected_count": len(selected),
        "considered_count": len(decisions),
        "excluded": excluded,
        "bounded": len(selected) <= limit,
        "limit": limit,
        "requires_compaction": False,
    }


def record(
    root: Path,
    *,
    decision_id: str,
    content: str,
    reason: str,
    authority: str = "USER_LOCKED_DECISION",
    generation: int = 0,
    task_relevance: list[str] | None = None,
    scope: list[str] | None = None,
    bind_current_goal: bool = True,
    supersedes: str | None = None,
) -> dict[str, Any]:
    authority = authority.strip().upper()
    if authority not in AUTHORITIES:
        raise ValueError("decision authority is invalid")
    if generation < 0:
        raise ValueError("decision generation must be non-negative")
    path = ai_root(root) / "governance" / "locked-decisions.json"
    with state_lock(root):
        try:
            if path.stat().st_size > MAX_MEMORY_BYTES:
                raise ValueError("decision memory exceeds the hot-state budget; compact it before writing")
        except FileNotFoundError:
            pass
        data = read_json(path, {"schema_version": "2.0.0", "decisions": []}) or {}
        decisions = data.setdefault("decisions", [])
        if not isinstance(decisions, list):
            raise ValueError("decision memory is invalid")
        if len(decisions) >= MAX_DECISIONS:
            raise ValueError("decision memory exceeds the record budget; compact it before writing")
        if any(isinstance(item, dict) and item.get("id") == decision_id for item in decisions):
            raise ValueError("decision id already exists")
        goal = read_json(ai_root(root) / "governance" / "goal-contract.json", {}) or {}
        goal_binding = {}
        if bind_current_goal and goal.get("status") == "ACTIVE":
            goal_binding = {key: goal.get(key) for key in ("goal_id", "revision", "fingerprint")}
        if supersedes:
            previous = next((item for item in decisions if isinstance(item, dict) and item.get("id") == supersedes), None)
            if not previous or previous.get("status", "LOCKED") != "LOCKED" or previous.get("superseded_by"):
                raise ValueError("decision to supersede is not active")
            previous["status"] = "SUPERSEDED"
            previous["superseded_by"] = decision_id
            previous["updated_at"] = utc_now()
        decision = {
            "id": decision_id,
            "status": "LOCKED",
            "content": content,
            "reason": reason,
            "authority": authority,
            "goal_binding": goal_binding,
            "task_relevance": _refs(task_relevance),
            "generation": generation,
            "scope": _refs(scope),
            "created_at": utc_now(),
            "superseded_by": None,
        }
        decisions.append(decision)
        data["schema_version"] = "2.0.0"
        atomic_write_json(path, data)
    return {"status": "RECORDED", "decision": decision, "superseded": supersedes}
