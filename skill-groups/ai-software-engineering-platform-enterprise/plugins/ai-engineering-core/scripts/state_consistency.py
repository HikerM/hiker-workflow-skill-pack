from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from corelib import SCHEMA_VERSION, ai_root, atomic_write_json, read_json, utc_now
from source_identity import identify
from technology_markers import STATE_FINGERPRINT_NAMES

MANIFEST_NAMES = STATE_FINGERPRINT_NAMES
MATERIAL_HINTS = (
    "migration", "schema", "openapi", "asyncapi", "proto", "contract",
    "routes", "router", "projectsettings", "packages/manifest",
)
LEGACY_STATE_MARKERS = (
    "schema.json", "runtime/task.json", "runtime/task-index.json", "runtime/skill-routing.json",
    "governance/project-state.json", "governance/task-index.json", "governance/goal-contract.json",
    "workspace/task-map.json",
)
RECOVERY_INDEX_VERSION = "hiker-new-session-recovery/v1"
RECOVERY_INDEX_RELATIVE = "governance/new-session-recovery.json"
MAX_RECOVERY_FILES = 24
MAX_RECOVERY_FILE_BYTES = 1024 * 1024
KNOWN_LEGACY_SCHEMA_MAJORS = {"0", "2"}
QUARANTINED_AUTHORITY_PATHS = (
    "governance/source-provenance.json",
    "governance/goal-contract.json",
    "governance/task-index.json",
    "governance/locked-decisions.json",
    "governance/ownership.json",
    "runtime/task.json",
    "runtime/task-index.json",
    "runtime/skill-routing.json",
    "workspace/task-map.json",
)
DERIVED_JSON_PATHS = (
    "context/project.json",
    "context/tech-stack.json",
    "runtime/skill-routing.json",
    "runtime/task-index.json",
    "governance/task-index.json",
    "evidence/index.json",
)


def _run(root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        list(args), cwd=root, text=True, encoding="utf-8", errors="replace",
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False,
    )


def _sha(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8", errors="replace")).hexdigest()


def _git(root: Path, *args: str) -> str:
    result = _run(root, "git", *args)
    return result.stdout.strip() if result.returncode == 0 else ""


def _repo_id(root: Path) -> str:
    remote = _git(root, "config", "--get", "remote.origin.url")
    common = _git(root, "rev-parse", "--git-common-dir")
    if remote:
        seed = remote
    elif common:
        common_path = Path(common)
        if not common_path.is_absolute():
            common_path = root / common_path
        seed = str(common_path.resolve())
    else:
        seed = str(root.resolve())
    return _sha(seed)


def _tracked_manifests(root: Path) -> list[Path]:
    output = _git(root, "ls-files", "-z")
    found: list[Path] = []
    for raw in output.split("\0"):
        if not raw:
            continue
        path = Path(raw)
        normalized = raw.replace("\\", "/").lower()
        if path.name.lower() in {name.lower() for name in MANIFEST_NAMES} or "/migrations/" in f"/{normalized}/":
            target = root / path
            if target.is_file():
                found.append(target)
        if len(found) >= 500:
            break
    return found


def _manifest_hash(root: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(_tracked_manifests(root)):
        digest.update(path.relative_to(root).as_posix().encode("utf-8"))
        try:
            digest.update(path.read_bytes())
        except OSError:
            digest.update(b"unreadable")
    return digest.hexdigest()


def current_snapshot(root: Path, identity: dict[str, Any] | None = None) -> dict[str, Any]:
    root = root.resolve()
    identity = identity or identify(root)
    if not identity.get("is_git"):
        digest = hashlib.sha256()
        candidates = [root / name for name in MANIFEST_NAMES]
        try:
            children = sorted((item for item in root.iterdir() if item.is_dir()), key=lambda item: item.name)[:32]
        except OSError:
            children = []
        for child in children:
            candidates.extend(child / name for name in MANIFEST_NAMES)
        for path in sorted(item for item in candidates if item.is_file())[:96]:
            digest.update(path.relative_to(root).as_posix().encode("utf-8"))
            try:
                digest.update(path.read_bytes())
            except OSError:
                digest.update(b"unreadable")
        return {
            "schema_version": "1.0.0",
            "repo_id": _sha(str(root)),
            "head": None,
            "branch": "NON_GIT",
            "dirty": None,
            "manifest_hash": digest.hexdigest(),
        }
    return {
        "schema_version": "1.0.0",
        "repo_id": identity.get("repo_id") or _repo_id(root),
        "head": identity.get("head"),
        "branch": identity.get("branch") or "DETACHED",
        "dirty": identity.get("dirty"),
        "manifest_hash": identity.get("manifest_hash") or _manifest_hash(root),
    }


def provenance_path(root: Path) -> Path:
    return ai_root(root) / "governance" / "source-provenance.json"


def recovery_index_path(root: Path) -> Path:
    return ai_root(root) / RECOVERY_INDEX_RELATIVE


def _bounded_file_fact(path: Path, relative: str) -> dict[str, Any]:
    try:
        if path.is_symlink():
            return {"path": relative, "status": "UNSAFE_LINK", "sha256": None, "size": None}
        size = path.stat().st_size
        if size > MAX_RECOVERY_FILE_BYTES:
            return {"path": relative, "status": "OVERSIZED_PRESERVED", "sha256": None, "size": size}
        return {
            "path": relative,
            "status": "PRESERVED_IN_PLACE",
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "size": size,
        }
    except OSError:
        return {"path": relative, "status": "UNREADABLE_PRESERVED", "sha256": None, "size": None}


def _bounded_recovery_facts(root: Path) -> list[dict[str, Any]]:
    base = ai_root(root)
    facts: list[dict[str, Any]] = []
    for relative in QUARANTINED_AUTHORITY_PATHS[:MAX_RECOVERY_FILES]:
        path = base / relative
        if path.exists() or path.is_symlink():
            facts.append(_bounded_file_fact(path, relative))
    return facts


def _json_state(path: Path) -> str:
    if not path.exists() and not path.is_symlink():
        return "MISSING"
    if path.is_symlink():
        return "UNSAFE_LINK"
    try:
        if path.stat().st_size > MAX_RECOVERY_FILE_BYTES:
            return "OVERSIZED"
        value = json.loads(path.read_text(encoding="utf-8"))
        return "VALID" if isinstance(value, dict) else "INVALID"
    except (OSError, UnicodeError, json.JSONDecodeError):
        return "INVALID"


def _bounded_json_value(path: Path) -> dict[str, Any] | None:
    if _json_state(path) != "VALID":
        return None
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else None
    except (OSError, UnicodeError, json.JSONDecodeError):
        return None


def _legacy_authority_candidate(root: Path) -> tuple[dict[str, Any] | None, str | None]:
    ai = ai_root(root)
    goal = _bounded_json_value(ai / "governance" / "goal-contract.json")
    index = _bounded_json_value(ai / "governance" / "task-index.json")
    runtime_task = _bounded_json_value(ai / "runtime" / "task.json")
    if not isinstance(goal, dict) or goal.get("status") != "ACTIVE":
        return None, "CURRENT_GOAL_AUTHORITY_MISSING"
    goal_id = str(goal.get("goal_id") or "")
    statement = str(goal.get("outcome") or "").strip()
    revision = goal.get("revision")
    fingerprint = str(goal.get("fingerprint") or "")
    if not goal_id or not statement or not isinstance(revision, int) or revision < 1 or not re.fullmatch(r"[0-9a-f]{64}", fingerprint):
        return None, "CURRENT_GOAL_CONTRACT_INVALID"
    summaries = [
        item for item in ((index or {}).get("tasks") or [])
        if isinstance(item, dict) and item.get("task_id") and item.get("state") not in {"Merged", "Released"}
    ][:8]
    runtime_id = str((runtime_task or {}).get("id") or (runtime_task or {}).get("task_id") or "")
    candidates = [str(item["task_id"]) for item in summaries]
    task_id = runtime_id if runtime_id in candidates else candidates[0] if len(candidates) == 1 else ""
    if len(candidates) > 1 and not task_id:
        return None, "MULTIPLE_CURRENT_TASK_AUTHORITIES"
    task = None
    if task_id:
        safe = re.sub(r"[^A-Za-z0-9._-]+", "-", task_id).strip("._-")
        task = _bounded_json_value(ai / "tasks" / f"{safe}.json")
    elif isinstance(runtime_task, dict):
        task = runtime_task
    if not isinstance(task, dict):
        return None, "CURRENT_TASK_AUTHORITY_MISSING"
    task_statement = str(task.get("goal") or task.get("scope") or "").strip()
    binding = task.get("goal_binding") if isinstance(task.get("goal_binding"), dict) else {}
    if not task_statement or binding.get("scope") != "project" or any((
        binding.get("goal_id") != goal_id,
        binding.get("revision") != revision,
        binding.get("fingerprint") != fingerprint,
    )):
        return None, "CURRENT_GOAL_TASK_BINDING_MISMATCH"
    history = task.get("history") if isinstance(task.get("history"), list) else []
    return {
        "contract_version": "hiker-recovered-current-authority/v1",
        "goal": {
            "statement": statement,
            "state": "ACTIVE",
            "authority_source": "RUNTIME_CURRENT_GOAL_CONTRACT",
            "authority_generation": revision,
        },
        "task": {
            "statement": task_statement,
            "state": "IN_PROGRESS",
            "authority_source": "RUNTIME_CURRENT_TASK_CONTRACT",
            "authority_generation": len(history),
        },
    }, None


def _snapshot_recovery(
    root: Path,
    classification: str,
    current: dict[str, Any],
    facts: list[dict[str, Any]],
) -> tuple[str, str, int]:
    basis = {
        "classification": classification,
        "repo_id": current.get("repo_id"),
        "head": current.get("head"),
        "facts": facts,
    }
    snapshot_id = hashlib.sha256(
        json.dumps(basis, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()[:20]
    relative = f"recovery/snapshots/{snapshot_id}.json"
    path = ai_root(root) / relative
    if path.exists():
        return snapshot_id, relative, 0
    atomic_write_json(path, {
        "contract_version": RECOVERY_INDEX_VERSION,
        "snapshot_id": snapshot_id,
        "classification": classification,
        "source_identity": current,
        "authority_files": facts,
        "created_at": utc_now(),
        "payload_policy": "REFERENCES_ONLY_NO_FULL_AI_COPY",
    })
    return snapshot_id, relative, 1


def _quarantine_file(root: Path, relative: str, snapshot_id: str) -> tuple[str | None, int]:
    source = ai_root(root) / relative
    if not source.exists() and not source.is_symlink():
        return None, 0
    if source.is_symlink():
        return None, 0
    target = ai_root(root) / "recovery" / "quarantine" / snapshot_id / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        return target.relative_to(ai_root(root)).as_posix(), 0
    source.replace(target)
    return target.relative_to(ai_root(root)).as_posix(), 1


def _write_recovery_index(root: Path, payload: dict[str, Any]) -> int:
    path = recovery_index_path(root)
    existing = _bounded_json_value(path)
    comparable = {key: value for key, value in payload.items() if key != "updated_at"}
    prior = {key: value for key, value in existing.items() if key != "updated_at"} if isinstance(existing, dict) else None
    if prior == comparable:
        return 0
    atomic_write_json(path, {**payload, "updated_at": utc_now()})
    return 1


def _has_untrusted_state(root: Path) -> bool:
    base = ai_root(root)
    return any((base / relative).is_file() for relative in LEGACY_STATE_MARKERS)


def _execution_policy(mode: str, trusted: bool, requires_recovery: bool) -> dict[str, Any]:
    return {
        "mode": mode,
        "trusted_ai_state": trusted,
        "current_request_is_authoritative": True,
        "current_git_is_authoritative": True,
        "may_resume_old_tasks": trusted,
        "may_reuse_prior_pass": trusted,
        "may_create_sessions_or_worktrees": trusted,
        "requires_state_recovery": requires_recovery,
    }


def _changed_paths(root: Path, old_head: str, new_head: str) -> tuple[list[str], bool]:
    if not old_head or not new_head or old_head == new_head:
        return [], True
    check = _run(root, "git", "cat-file", "-e", f"{old_head}^{{commit}}")
    if check.returncode != 0:
        return [], False
    raw = _git(root, "diff", "--name-only", "-z", old_head, new_head)
    paths = [item.replace("\\", "/") for item in raw.split("\0") if item]
    return paths[:1000], True


def assess(root: Path, current: dict[str, Any] | None = None) -> dict[str, Any]:
    current = current or current_snapshot(root)
    stored = read_json(provenance_path(root), None)
    if not isinstance(stored, dict):
        if not _has_untrusted_state(root):
            return {
                "ok": True,
                "status": "STATELESS_UNMANAGED",
                "recovery_level": "L0",
                "current": current,
                "stored": None,
                "invalidated": [],
                "execution_policy": _execution_policy("CURRENT_REQUEST_AND_GIT_ONLY", False, False),
            }
        return {
            "ok": False,
            "status": "UNTRUSTED_AI_STATE",
            "recovery_level": "L3",
            "current": current,
            "stored": None,
            "invalidated": ["legacy-task-state", "legacy-skill-routing", "review-evidence", "test-evidence"],
            "execution_policy": _execution_policy("QUARANTINE_AI_STATE", False, True),
        }
    if stored.get("repo_id") != current["repo_id"]:
        return {
            "ok": False,
            "status": "PROJECT_IDENTITY_DRIFT",
            "recovery_level": "L4",
            "current": current,
            "stored": stored,
            "invalidated": ["all-derived-ai-state", "review-evidence", "test-evidence"],
            "execution_policy": _execution_policy("QUARANTINE_AI_STATE", False, True),
        }
    paths, reachable = _changed_paths(root, str(stored.get("head") or ""), str(current.get("head") or ""))
    material = stored.get("manifest_hash") != current["manifest_hash"] or any(
        Path(path).name.lower() in {name.lower() for name in MANIFEST_NAMES}
        or any(hint in path.lower() for hint in MATERIAL_HINTS)
        for path in paths
    )
    if not reachable:
        return {
            "ok": False,
            "status": "HISTORY_DIVERGED",
            "recovery_level": "L3",
            "current": current,
            "stored": stored,
            "changed_paths": [],
            "invalidated": ["candidate-binding", "derived-graph", "review-evidence", "test-evidence"],
            "execution_policy": _execution_policy("QUARANTINE_AI_STATE", False, True),
        }
    if material:
        return {
            "ok": False,
            "status": "MATERIAL_DRIFT",
            "recovery_level": "L2",
            "current": current,
            "stored": stored,
            "changed_paths": paths,
            "invalidated": ["affected-module-baseline", "affected-contract-evidence"],
            "execution_policy": _execution_policy("CURRENT_REQUEST_AND_GIT_ONLY", False, True),
        }
    if paths or stored.get("dirty") != current["dirty"] or stored.get("branch") != current["branch"]:
        return {
            "ok": False,
            "status": "INCREMENTAL_DRIFT",
            "recovery_level": "L1",
            "current": current,
            "stored": stored,
            "changed_paths": paths,
            "invalidated": ["affected-hot-index"],
            "execution_policy": _execution_policy("CURRENT_REQUEST_AND_GIT_ONLY", False, True),
        }
    return {
        "ok": True,
        "status": "CONSISTENT",
        "recovery_level": "L0",
        "current": current,
        "stored": stored,
        "changed_paths": [],
        "invalidated": [],
        "execution_policy": _execution_policy("TRUSTED_AI_STATE", True, False),
    }


def recover_for_new_session(root: Path) -> dict[str, Any]:
    """Prepare current project facts without treating untrusted old state as project failure."""
    root = root.resolve()
    ai = ai_root(root)
    ai_existed = ai.is_dir()
    report = assess(root)
    status = str(report.get("status") or "UNKNOWN")
    current = report.get("current") if isinstance(report.get("current"), dict) else current_snapshot(root)
    actions: list[str] = []
    state_writes = 0
    bootstrap_required = not ai_existed
    old_state_resumability = "NOT_PRESENT" if not ai_existed else "PRESERVED"
    classification = "NO_AI_DIRECTORY" if not ai_existed else status
    diagnostic_ref: str | None = None
    existing_recovery = _bounded_json_value(recovery_index_path(root))
    if status == "CONSISTENT" and isinstance(existing_recovery, dict):
        recorded = str(existing_recovery.get("old_state_resumability") or "")
        if recorded in {"QUARANTINED", "AMBIGUOUS", "REBINDABLE"}:
            old_state_resumability = recorded
            classification = "CONSISTENT_RECOVERED_PROJECT"
            diagnostic_ref = RECOVERY_INDEX_RELATIVE

    authority_paths = (
        "governance/goal-contract.json",
        "governance/locked-decisions.json",
        "governance/ownership.json",
        "runtime/task.json",
    )
    invalid_authority = [relative for relative in authority_paths if _json_state(ai / relative) in {"INVALID", "UNSAFE_LINK", "OVERSIZED"}]
    invalid_derived = [relative for relative in DERIVED_JSON_PATHS if _json_state(ai / relative) in {"INVALID", "UNSAFE_LINK", "OVERSIZED"}]
    required_derived = ("context/project.json", "context/tech-stack.json", "runtime/task.json")
    missing_derived = [relative for relative in required_derived if _json_state(ai / relative) == "MISSING"] if ai_existed else list(required_derived)
    schema_state = _json_state(ai / "schema.json")

    quarantine_statuses = {"UNTRUSTED_AI_STATE", "PROJECT_IDENTITY_DRIFT", "HISTORY_DIVERGED"}
    if status in quarantine_statuses or invalid_authority:
        classification = (
            "CORRUPTED_AUTHORITY_FILE" if invalid_authority
            else "FOREIGN_AI" if status == "PROJECT_IDENTITY_DRIFT"
            else "LEGACY_AI_WITHOUT_PROVENANCE" if status == "UNTRUSTED_AI_STATE"
            else "HISTORY_DIVERGED"
        )
        authority_candidate, candidate_error = _legacy_authority_candidate(root)
        facts = _bounded_recovery_facts(root)
        if schema_state != "MISSING":
            facts.append(_bounded_file_fact(ai / "schema.json", "schema.json"))
        snapshot_id, diagnostic_ref, writes = _snapshot_recovery(root, classification, current, facts)
        state_writes += writes
        targets = invalid_authority if invalid_authority else list(QUARANTINED_AUTHORITY_PATHS)
        quarantined: list[str] = []
        for relative in targets[:MAX_RECOVERY_FILES]:
            target, writes = _quarantine_file(root, relative, snapshot_id)
            state_writes += writes
            if target:
                quarantined.append(target)
        legacy_schema = _bounded_json_value(ai / "schema.json")
        legacy_version = str((legacy_schema or {}).get("version") or "")
        legacy_major = legacy_version.split(".")[0] if legacy_version else ""
        if legacy_major in KNOWN_LEGACY_SCHEMA_MAJORS:
            schema_target = ai / "recovery" / "quarantine" / snapshot_id / "schema.json"
            if not schema_target.exists() and (ai / "schema.json").is_file() and not (ai / "schema.json").is_symlink():
                schema_target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(ai / "schema.json", schema_target)
                state_writes += 1
            atomic_write_json(ai / "schema.json", {
                "version": SCHEMA_VERSION,
                "created_at": legacy_schema.get("created_at", utc_now()),
                "updated_at": utc_now(),
                "migrated_from": legacy_version,
                "migration_snapshot": diagnostic_ref,
            })
            state_writes += 1
            actions.append("COPY_ON_WRITE_SCHEMA_MIGRATION")
        elif schema_state in {"INVALID", "OVERSIZED"}:
            _, writes = _quarantine_file(root, "schema.json", snapshot_id)
            state_writes += writes
            atomic_write_json(ai / "schema.json", {"version": SCHEMA_VERSION, "created_at": utc_now(), "updated_at": utc_now()})
            state_writes += 1
            actions.append("QUARANTINE_AND_REGENERATE_SCHEMA")
        elif legacy_major and legacy_major != SCHEMA_VERSION.split(".")[0]:
            classification = "UNKNOWN_SCHEMA"
            old_state_resumability = "AMBIGUOUS"
            bootstrap_required = False
            actions.append("PRESERVE_UNKNOWN_SCHEMA_READ_ONLY")
        candidate_ref = None
        if authority_candidate is not None and status != "PROJECT_IDENTITY_DRIFT" and not invalid_authority:
            candidate_ref = "recovery/current-authority-candidate.json"
            atomic_write_json(ai / candidate_ref, authority_candidate)
            state_writes += 1
            old_state_resumability = "REBINDABLE"
            actions.append("PRESERVE_UNIQUE_AUTHORITY_CANDIDATE")
        elif candidate_error == "MULTIPLE_CURRENT_TASK_AUTHORITIES":
            old_state_resumability = "AMBIGUOUS"
        else:
            old_state_resumability = "QUARANTINED"
        atomic_write_json(provenance_path(root), {
            **current,
            "recovery_contract": RECOVERY_INDEX_VERSION,
            "recovery_snapshot_id": snapshot_id,
            "old_state_resumability": old_state_resumability,
        })
        state_writes += 1
        bootstrap_required = classification != "UNKNOWN_SCHEMA" and schema_state != "UNSAFE_LINK"
        actions.extend(["BOUNDED_AUTHORITY_SNAPSHOT", "QUARANTINE_OLD_AUTHORITY", "ESTABLISH_CURRENT_SOURCE_PROVENANCE"])
        index = {
            "contract_version": RECOVERY_INDEX_VERSION,
            "classification": classification,
            "project_usability": "CURRENT_PROJECT_READY",
            "old_state_resumability": old_state_resumability,
            "snapshot_ref": diagnostic_ref,
            "authority_candidate_ref": candidate_ref,
            "authority_candidate_error": candidate_error,
            "quarantined_paths": quarantined,
            "source_repo_id": current.get("repo_id"),
            "full_ai_scan": False,
            "cold_history_scanned": False,
        }
        state_writes += _write_recovery_index(root, index)
        diagnostic_ref = RECOVERY_INDEX_RELATIVE
    else:
        schema_path = ai / "schema.json"
        schema = _bounded_json_value(schema_path)
        version = str(schema.get("version") or "") if isinstance(schema, dict) else ""
        major = version.split(".")[0] if version else ""
        if major and major != SCHEMA_VERSION.split(".")[0] and major in KNOWN_LEGACY_SCHEMA_MAJORS:
            classification = "OLD_SCHEMA"
            fact = _bounded_file_fact(schema_path, "schema.json")
            snapshot_id, diagnostic_ref, writes = _snapshot_recovery(root, classification, current, [fact])
            state_writes += writes
            target = ai / "recovery" / "quarantine" / snapshot_id / "schema.json"
            if not target.exists() and schema_path.is_file() and not schema_path.is_symlink():
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(schema_path, target)
                state_writes += 1
            atomic_write_json(schema_path, {
                "version": SCHEMA_VERSION,
                "created_at": schema.get("created_at", utc_now()),
                "updated_at": utc_now(),
                "migrated_from": version,
                "migration_snapshot": diagnostic_ref,
            })
            state_writes += 1
            actions.append("COPY_ON_WRITE_SCHEMA_MIGRATION")
            bootstrap_required = True
        elif major and major != SCHEMA_VERSION.split(".")[0]:
            classification = "UNKNOWN_SCHEMA"
            old_state_resumability = "AMBIGUOUS"
            actions.append("PRESERVE_UNKNOWN_SCHEMA_READ_ONLY")

        if status in {"INCREMENTAL_DRIFT", "MATERIAL_DRIFT"}:
            repair(root)
            state_writes += 2 if provenance_path(root).exists() else 1
            actions.append("REFRESH_AFFECTED_SOURCE_PROVENANCE")
            classification = status
        if invalid_derived:
            classification = "CORRUPTED_DERIVED_FILE"
            facts = [_bounded_file_fact(ai / relative, relative) for relative in invalid_derived[:MAX_RECOVERY_FILES]]
            snapshot_id, diagnostic_ref, writes = _snapshot_recovery(root, classification, current, facts)
            state_writes += writes
            for relative in invalid_derived[:MAX_RECOVERY_FILES]:
                _, writes = _quarantine_file(root, relative, snapshot_id)
                state_writes += writes
            actions.append("QUARANTINE_AND_REGENERATE_DERIVED_STATE")
            bootstrap_required = True
        if missing_derived:
            if classification in {"CONSISTENT", "STATELESS_UNMANAGED"}:
                classification = "PARTIAL_AI" if ai_existed else "NO_AI_DIRECTORY"
            actions.append("REBUILD_MISSING_DERIVED_STATE")
            bootstrap_required = True

    if not actions:
        actions.append("REUSE_CURRENT_STATE" if status == "CONSISTENT" else "USE_CURRENT_REQUEST_AND_GIT")
    project_ready = True
    user_action_required = "NONE"
    affected_capability = "OLD_STATE_RESUME" if old_state_resumability in {"QUARANTINED", "AMBIGUOUS"} else "DERIVED_STATE_ONLY"
    return {
        "ok": True,
        "classification": classification,
        "affected_capability": affected_capability,
        "automatic_action_taken": actions,
        "recovery_status": "CURRENT_PROJECT_READY",
        "diagnostic_ref": diagnostic_ref,
        "user_action_required": user_action_required,
        "project_usability": "READY" if project_ready else "BLOCKED",
        "old_state_resumability": old_state_resumability,
        "bootstrap_required": bootstrap_required,
        "state_reads": len(QUARANTINED_AUTHORITY_PATHS) + len(DERIVED_JSON_PATHS) + 2,
        "state_writes": state_writes,
        "full_ai_scan": False,
        "cold_history_scanned": False,
        "current": current,
    }


def repair(root: Path, allow_untrusted_initialization: bool = False) -> dict[str, Any]:
    report = assess(root)
    if report["status"] == "UNTRUSTED_AI_STATE" and not allow_untrusted_initialization:
        return {
            **report,
            "repaired": False,
            "repair_blocked": True,
            "message": "旧 .ai 缺少可信源码指纹；保持隔离，禁止自动恢复旧任务或旧 PASS",
        }
    path = provenance_path(root)
    if path.exists():
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        archive = ai_root(root) / "archive" / "consistency" / f"source-provenance-{stamp}.json"
        archive.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, archive)
    atomic_write_json(path, report["current"])
    return {**report, "repaired": True, "new_status": "CONSISTENT", "provenance": path.relative_to(root).as_posix()}


def main() -> int:
    parser = argparse.ArgumentParser(description="检查 .ai 与当前源码身份和候选的一致性")
    parser.add_argument("--root", default=".")
    parser.add_argument("--repair", action="store_true")
    args = parser.parse_args()
    root = Path(args.root).resolve()
    result = repair(root) if args.repair else assess(root)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result.get("ok") or result.get("repaired") else 2


if __name__ == "__main__":
    raise SystemExit(main())
