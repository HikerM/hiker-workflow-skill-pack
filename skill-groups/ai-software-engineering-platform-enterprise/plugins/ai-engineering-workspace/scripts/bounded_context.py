from __future__ import annotations

import hashlib
import shutil
from pathlib import Path
from typing import Any

from workspacelib import atomic_json, read_json

DEFAULT_POLICY = {
    "schema_version": "1.0.0",
    "active_context_max_chars": 12000,
    "session_context_max_chars": 6500,
    "max_items_per_section": 12,
    "max_recent_checkpoints": 12,
    "max_milestone_checkpoints": 8,
    "max_ledger_entries": 32,
    "max_task_index_closed": 200,
}
MILESTONE_WORDS = ("start", "pause", "adjust", "plan", "review", "test", "merge", "release", "complete", "handoff")


def ensure_policy(root: Path) -> dict[str, Any]:
    path = root / ".ai" / "governance" / "context-retention.json"
    current = read_json(path, {}) or {}
    policy = dict(DEFAULT_POLICY)
    if isinstance(current, dict):
        for key, default in DEFAULT_POLICY.items():
            value = current.get(key)
            if key == "schema_version":
                if isinstance(value, str) and value:
                    policy[key] = value
            elif isinstance(value, int) and value > 0:
                policy[key] = value
    if current != policy:
        atomic_json(path, policy)
    return policy


def crop(value: Any, limit: int = 600) -> str:
    text = str(value or "").strip()
    return text if len(text) <= limit else text[: max(0, limit - 14)].rstrip() + "…（详见事实源）"


def bounded_bullets(values: Any, limit: int, source: str, newest: bool = True) -> list[str]:
    raw = values if isinstance(values, (list, tuple)) else list(values or [])
    selected_raw = raw[-limit:] if newest else raw[:limit]
    selected = [crop(item) for item in selected_raw if str(item).strip()]
    lines = [f"- {item}" for item in selected] or ["- 无"]
    if len(raw) > len(selected_raw):
        lines.append(f"- 另有 {len(raw) - len(selected_raw)} 项未进入当前工作集；完整事实见 `{source}`。")
    return lines


def limit_text(text: str, max_chars: int, source: str) -> str:
    if len(text) <= max_chars:
        return text
    suffix = f"\n\n> 当前工作集已达到 {max_chars} 字符上限；其余事实按需读取 `{source}`。\n"
    return text[: max(0, max_chars - len(suffix))].rstrip() + suffix


def _sha(path: Path) -> str | None:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError:
        return None


def _milestone(data: dict[str, Any]) -> bool:
    label = str(data.get("label") or "").lower()
    event = str(data.get("event") or "").lower()
    if event in {"precompact", "stop", "auto", "workspacecheckpoint"} and not any(word in label for word in MILESTONE_WORDS):
        return False
    return any(word in label for word in MILESTONE_WORDS) or event in {"manual", "milestone"}


def retain_checkpoints(root: Path, updated_at: str) -> dict[str, Any]:
    policy = ensure_policy(root)
    folder = root / ".ai" / "runtime" / "checkpoints"; folder.mkdir(parents=True, exist_ok=True)
    ledger_path = root / ".ai" / "runtime" / "checkpoint-ledger.json"
    records = []
    for path in folder.glob("*.json"):
        data = read_json(path, {}) or {}
        if isinstance(data, dict):
            records.append((path, data))
    records.sort(key=lambda item: (str(item[1].get("created_at") or ""), item[0].name), reverse=True)
    milestones = [item for item in records if _milestone(item[1])]
    rolling = [item for item in records if not _milestone(item[1])]
    keep = {path for path, _ in milestones[: policy["max_milestone_checkpoints"]]}
    keep.update(path for path, _ in rolling[: policy["max_recent_checkpoints"]])
    prune = [(path, data) for path, data in records if path not in keep]
    ledger = read_json(ledger_path, {}) or {}
    entries = list(ledger.get("recent_pruned", [])) if isinstance(ledger, dict) and isinstance(ledger.get("recent_pruned"), list) else []
    chain = str(ledger.get("pruned_hash_chain") or "") if isinstance(ledger, dict) else ""
    count = int(ledger.get("pruned_count") or 0) if isinstance(ledger, dict) else 0
    first = ledger.get("first_pruned_at") if isinstance(ledger, dict) else None
    for path, data in sorted(prune, key=lambda item: (str(item[1].get("created_at") or ""), item[0].name)):
        digest = _sha(path)
        chain = hashlib.sha256(f"{chain}|{path.name}|{digest or 'unreadable'}".encode("utf-8")).hexdigest()
        created = data.get("created_at")
        entries.append({"name": path.name, "created_at": created, "label": data.get("label"), "event": data.get("event"), "sha256": digest})
        first = first or created or updated_at; count += 1
        path.unlink(missing_ok=True); shutil.rmtree(folder / f"{path.stem}-state", ignore_errors=True)
    entries = entries[-policy["max_ledger_entries"] :]
    retained = [{"name": path.name, "created_at": data.get("created_at"), "label": data.get("label"), "event": data.get("event")} for path, data in records if path in keep and path.exists()]
    out = {
        "schema_version": "1.0.0", "policy": policy, "retained_count": len(retained), "retained": retained,
        "pruned_count": count, "first_pruned_at": first,
        "last_pruned_at": entries[-1].get("created_at") if entries else (ledger.get("last_pruned_at") if isinstance(ledger, dict) else None),
        "pruned_hash_chain": chain or None, "recent_pruned": entries, "updated_at": updated_at,
    }
    atomic_json(ledger_path, out)
    return out
