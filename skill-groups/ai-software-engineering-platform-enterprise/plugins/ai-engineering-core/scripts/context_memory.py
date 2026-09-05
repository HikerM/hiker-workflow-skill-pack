from __future__ import annotations

import hashlib
import json
import shutil
import zipfile
from pathlib import Path
from typing import Any

from corelib import ai_root, atomic_write_json, read_json, sha256_file, utc_now
from source_surface import TraversalBudget, walk_source_files

DEFAULT_MEMORY_POLICY = {
    "schema_version": "1.1.0",
    "active_context_max_chars": 8000,
    "session_context_max_chars": 4000,
    "max_items_per_section": 8,
    "max_recent_checkpoints": 8,
    "max_milestone_checkpoints": 6,
    "max_ledger_entries": 24,
    "max_task_index_closed": 120,
    "max_task_history_events": 40,
    "max_task_history_ledger_entries": 20,
    "max_session_epoch_turns": 20,
    "max_session_epoch_tool_calls": 40,
    "max_session_epoch_tool_output_chars": 60000,
    "max_session_epoch_compactions": 1,
}

LEGACY_EPOCH_DEFAULTS = {
    "max_session_epoch_turns": 40,
    "max_session_epoch_tool_calls": 80,
    "max_session_epoch_tool_output_chars": 120000,
    "max_session_epoch_compactions": 2,
}

LEGACY_CONTEXT_DEFAULTS = {
    "active_context_max_chars": 12000,
    "session_context_max_chars": 6500,
    "max_items_per_section": 12,
    "max_recent_checkpoints": 12,
    "max_milestone_checkpoints": 8,
    "max_ledger_entries": 32,
    "max_task_index_closed": 200,
}

MILESTONE_WORDS = ("start", "pause", "adjust", "plan", "review", "test", "merge", "release", "complete", "handoff")


def policy_path(root: Path) -> Path:
    return ai_root(root) / "governance" / "context-retention.json"


def read_memory_policy(root: Path) -> dict[str, Any]:
    current = read_json(policy_path(root), {}) or {}
    policy = dict(current) if isinstance(current, dict) else {}
    policy["schema_version"] = DEFAULT_MEMORY_POLICY["schema_version"]
    if isinstance(current, dict):
        for key, default in DEFAULT_MEMORY_POLICY.items():
            value = current.get(key)
            if key == "schema_version":
                continue
            elif isinstance(value, int) and value > 0:
                # 5.14/5.15 早期默认值对桌面长任务过于宽松。只迁移旧默认，
                # 用户明确调整过的其他正整数阈值仍保留。
                legacy_defaults = {**LEGACY_EPOCH_DEFAULTS, **LEGACY_CONTEXT_DEFAULTS}
                if current.get("schema_version") in {"1.0.0", "1.1.0"} and legacy_defaults.get(key) == value:
                    policy[key] = default
                else:
                    policy[key] = value
            else:
                policy[key] = default
    return policy


def ensure_memory_policy(root: Path) -> dict[str, Any]:
    path = policy_path(root)
    current = read_json(path, {}) or {}
    policy = read_memory_policy(root)
    if current != policy:
        atomic_write_json(path, policy)
    return policy


def crop(value: Any, limit: int = 600) -> str:
    text = str(value or "").strip()
    return text if len(text) <= limit else text[: max(0, limit - 14)].rstrip() + "…（详见事实源）"


def bounded_items(values: Any, limit: int, source: str, newest: bool = True) -> list[str]:
    raw = values if isinstance(values, (list, tuple)) else list(values or [])
    selected_raw = raw[-limit:] if newest else raw[:limit]
    selected = [crop(item) for item in selected_raw if str(item).strip()]
    lines = [f"- {item}" for item in selected] or ["- 无"]
    if len(raw) > len(selected_raw):
        lines.append(f"- 另有 {len(raw) - len(selected_raw)} 项未注入会话；完整事实见 `{source}`。")
    return lines


def limit_text(text: str, max_chars: int, source: str) -> str:
    if len(text) <= max_chars:
        return text
    suffix = f"\n\n> 工作集已达到 {max_chars} 字符上限；其余事实未丢弃，按需读取 `{source}`。\n"
    return text[: max(0, max_chars - len(suffix))].rstrip() + suffix


def is_milestone(data: dict[str, Any]) -> bool:
    label = str(data.get("label") or "").lower()
    event = str(data.get("event") or "").lower()
    if event in {"precompact", "stop", "auto", "workspacecheckpoint"} and not any(word in label for word in MILESTONE_WORDS):
        return False
    return any(word in label for word in MILESTONE_WORDS) or event in {"milestone", "manual"}


def _chain(previous: str, name: str, digest: str | None) -> str:
    payload = f"{previous}|{name}|{digest or 'unreadable'}".encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def archive_checkpoint(root: Path, path: Path, data: dict[str, Any]) -> tuple[str, str | None]:
    created = str(data.get("created_at") or utc_now())
    month = created[:7] if len(created) >= 7 and created[4:5] == "-" else "unknown"
    archive_dir = ai_root(root) / "archive" / "checkpoints" / month
    archive_dir.mkdir(parents=True, exist_ok=True)
    archive = archive_dir / f"{path.stem}.zip"
    state_dir = path.parent / f"{path.stem}-state"
    if not archive.exists():
        with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as bundle:
            bundle.write(path, arcname=path.name)
            if state_dir.is_dir():
                items, _ = walk_source_files(
                    state_dir,
                    TraversalBudget(max_depth=12,max_directories=2048,max_entries=10000,max_files=10000,max_observed_bytes=512*1024*1024,max_elapsed_ms=10000),
                    ignored_directories=frozenset(),
                )
                for item in items:
                    bundle.write(item, arcname=(Path("state") / item.relative_to(state_dir)).as_posix())
    index = ai_root(root) / "archive" / "checkpoints" / "index.jsonl"
    with index.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps({"name": path.name, "created_at": data.get("created_at"), "archive": archive.relative_to(ai_root(root)).as_posix(), "sha256": sha256_file(archive)}, ensure_ascii=False) + "\n")
    return archive.relative_to(ai_root(root)).as_posix(), sha256_file(archive)


def enforce_checkpoint_retention(root: Path) -> dict[str, Any]:
    policy = ensure_memory_policy(root)
    folder = ai_root(root) / "runtime" / "checkpoints"
    folder.mkdir(parents=True, exist_ok=True)
    ledger_path = ai_root(root) / "runtime" / "checkpoint-ledger.json"
    records: list[tuple[Path, dict[str, Any]]] = []
    paths, _ = walk_source_files(
        folder,
        TraversalBudget(max_depth=0,max_directories=1,max_entries=4096,max_files=4096,max_observed_bytes=128*1024*1024,max_elapsed_ms=2000),
        ignored_directories=frozenset(),include=lambda item:item.suffix.lower()==".json",
    )
    for path in paths:
        data = read_json(path, {}) or {}
        if isinstance(data, dict):
            records.append((path, data))
    records.sort(key=lambda item: (str(item[1].get("created_at") or ""), item[0].name), reverse=True)
    milestones = [item for item in records if is_milestone(item[1])]
    rolling = [item for item in records if not is_milestone(item[1])]
    keep = {path for path, _ in milestones[: policy["max_milestone_checkpoints"]]}
    keep.update(path for path, _ in rolling[: policy["max_recent_checkpoints"]])
    prune = [(path, data) for path, data in records if path not in keep]

    ledger = read_json(ledger_path, {}) or {}
    if not isinstance(ledger, dict):
        ledger = {}
    entries = list(ledger.get("recent_pruned", [])) if isinstance(ledger.get("recent_pruned"), list) else []
    chain = str(ledger.get("pruned_hash_chain") or "")
    first = ledger.get("first_pruned_at")
    count = int(ledger.get("pruned_count") or 0)
    for path, data in sorted(prune, key=lambda item: (str(item[1].get("created_at") or ""), item[0].name)):
        digest = sha256_file(path)
        archive, archive_digest = archive_checkpoint(root, path, data)
        created = data.get("created_at")
        chain = _chain(chain, path.name, digest)
        entries.append({
            "name": path.name,
            "created_at": created,
            "label": data.get("label"),
            "event": data.get("event"),
            "sha256": digest,
            "archive": archive,
            "archive_sha256": archive_digest,
        })
        first = first or created or utc_now()
        count += 1
        path.unlink(missing_ok=True)
        shutil.rmtree(folder / f"{path.stem}-state", ignore_errors=True)
    entries = entries[-policy["max_ledger_entries"] :]
    retained = []
    for path, data in records:
        if path in keep and path.exists():
            retained.append({"name": path.name, "created_at": data.get("created_at"), "label": data.get("label"), "event": data.get("event")})
    out = {
        "schema_version": "1.0.0",
        "policy": policy,
        "retained_count": len(retained),
        "retained": retained,
        "pruned_count": count,
        "first_pruned_at": first,
        "last_pruned_at": (entries[-1].get("created_at") if entries else ledger.get("last_pruned_at")),
        "pruned_hash_chain": chain or None,
        "recent_pruned": entries,
        "updated_at": utc_now(),
    }
    atomic_write_json(ledger_path, out)
    return out


def memory_status(root: Path) -> dict[str, Any]:
    policy = read_memory_policy(root)
    active = ai_root(root) / "runtime" / "active-context.md"
    ledger = read_json(ai_root(root) / "runtime" / "checkpoint-ledger.json", {}) or {}
    return {
        "policy": policy,
        "active_context_chars": len(active.read_text(encoding="utf-8")) if active.exists() else 0,
        "retained_checkpoints": int(ledger.get("retained_count") or 0),
        "pruned_checkpoints": int(ledger.get("pruned_count") or 0),
        "cold_archived_checkpoints": int(ledger.get("pruned_count") or 0),
        "cold_archive": ".ai/archive/checkpoints/",
        "pruned_hash_chain": ledger.get("pruned_hash_chain"),
        "canonical_sources": [
            "PROJECT_STATE.md", "CURRENT_CONTEXT.md", "CHANGELOG.md", "ARCHITECTURE.md",
            ".ai/tasks/*.json", ".ai/governance/locked-decisions.json", "Git history/status",
        ],
    }
