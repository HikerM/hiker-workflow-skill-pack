from __future__ import annotations

from pathlib import Path
from typing import Any

from goal_contract import verify_binding


def quality_lineage(root: Path, task: dict[str, Any]) -> dict[str, Any]:
    """Bind quality evidence to the live candidate and goal revision."""
    candidate = task.get("review_candidate") or {}
    candidate_id = candidate.get("candidate_id")
    if not candidate_id:
        raise RuntimeError("quality evidence requires a frozen review candidate")
    from candidate_guard import verify as verify_candidate

    report = verify_candidate(root, str(candidate_id))
    if report.get("result") != "PASS":
        raise RuntimeError("quality evidence candidate is stale")
    goal = verify_binding(root, task.get("goal_binding"))
    if not goal.get("ok"):
        raise RuntimeError("quality evidence goal binding is stale")
    return {
        "candidate_id": candidate_id,
        "candidate_fingerprint": candidate.get("candidate_fingerprint"),
        "candidate_commit": candidate.get("candidate_commit"),
        "worktree_fingerprint": candidate.get("worktree_fingerprint"),
        "goal_revision": (task.get("goal_binding") or {}).get("revision"),
        "goal_fingerprint": (task.get("goal_binding") or {}).get("fingerprint"),
    }


def verify_quality_lineage(
    root: Path,
    task: dict[str, Any],
    kind: str,
    *,
    require_live_candidate: bool = True,
) -> dict[str, Any]:
    key = "tests" if kind == "test" else kind
    evidence = task.get(key) or {}
    binding = evidence.get("binding") or {}
    candidate = task.get("review_candidate") or {}
    expected = {
        "candidate_id": candidate.get("candidate_id"),
        "candidate_fingerprint": candidate.get("candidate_fingerprint"),
        "candidate_commit": candidate.get("candidate_commit"),
        "worktree_fingerprint": candidate.get("worktree_fingerprint"),
        "goal_revision": (task.get("goal_binding") or {}).get("revision"),
        "goal_fingerprint": (task.get("goal_binding") or {}).get("fingerprint"),
    }
    mismatches = {
        field: {"expected": value, "actual": binding.get(field)}
        for field, value in expected.items()
        if not value or binding.get(field) != value
    }
    if not binding.get("evidence_digest"):
        mismatches["evidence_digest"] = {"expected": "sha256", "actual": None}
    if evidence.get("status") != "PASS":
        mismatches["status"] = {"expected": "PASS", "actual": evidence.get("status")}
    if require_live_candidate and not mismatches:
        from candidate_guard import verify as verify_candidate

        candidate_report = verify_candidate(root, str(candidate.get("candidate_id") or ""))
        if candidate_report.get("result") != "PASS":
            mismatches["live_candidate"] = {
                "expected": "PASS",
                "actual": candidate_report.get("result"),
                "details": candidate_report.get("mismatches") or {},
            }
        else:
            goal = verify_binding(root, task.get("goal_binding"))
            if not goal.get("ok"):
                mismatches["live_goal"] = {
                    "expected": "CURRENT",
                    "actual": goal.get("status"),
                }
    return {"ok": not mismatches, "kind": kind, "binding": binding, "mismatches": mismatches}
