from __future__ import annotations

import contextlib
import hashlib
import json
import os
import subprocess
import time
import uuid
from functools import lru_cache
from pathlib import Path
from typing import Any

from process_identity import owner_status, process_identity


class TraceWriteError(RuntimeError):
    """Trace persistence is temporarily unavailable and the operation may be retried."""


class TraceStateError(RuntimeError):
    """Local trace files cannot be reconciled without a same-operation retry."""


def _run(root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        list(args),
        cwd=str(root),
        text=True,
        encoding="utf-8",
        errors="replace",
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )


def project_ref(root: Path) -> str:
    common = _run(root, "git", "rev-parse", "--git-common-dir")
    seed = common.stdout.strip() if common.returncode == 0 else str(root.resolve())
    if common.returncode == 0:
        path = Path(seed)
        if not path.is_absolute():
            path = root / path
        seed = str(path.resolve())
    return hashlib.sha256(seed.encode("utf-8", errors="replace")).hexdigest()


def _repository_marker(root: Path) -> str:
    for candidate in (root, *root.parents):
        marker = candidate / ".git"
        if marker.exists():
            return str(marker)
    return ""


@lru_cache(maxsize=256)
def _cached_control_root(root_text: str, state_base: str, repository_marker: str) -> Path:
    root = Path(root_text)
    result = _run(root, "git", "rev-parse", "--git-common-dir")
    if result.returncode == 0 and result.stdout.strip():
        common = Path(result.stdout.strip())
        if not common.is_absolute():
            common = root / common
        return common.resolve() / "ai-engineering" / "control"
    local = Path(state_base) if state_base else Path.home() / ".local" / "state"
    return local / "Hiker" / "engineering-control" / project_ref(root)[:24]


def control_root(root: Path) -> Path:
    resolved = root.resolve()
    state_base = (
        os.environ.get("HIKER_CONTROL_STATE_DIR")
        or os.environ.get("LOCALAPPDATA")
        or os.environ.get("XDG_STATE_HOME")
        or ""
    )
    return _cached_control_root(str(resolved), state_base, _repository_marker(resolved))


def event_file(root: Path) -> Path:
    return control_root(root) / "events-v1.jsonl"


def index_file(root: Path) -> Path:
    return control_root(root) / "event-index.json"


def _lock_owner(path: Path) -> tuple[dict[str, Any], bool]:
    try:
        raw = path.read_text(encoding="ascii").strip()
        if raw.startswith("{"):
            owner = json.loads(raw)
            return (owner, True) if isinstance(owner, dict) else ({}, False)
        return {"pid": int(raw), "created": path.stat().st_mtime, "token": None}, True
    except (OSError, ValueError, json.JSONDecodeError):
        return {}, False


@contextlib.contextmanager
def trace_lock(root: Path, timeout: float = 5.0, stale_after: float = 120.0):
    lock = control_root(root) / "trace.lock"
    lock.parent.mkdir(parents=True, exist_ok=True)
    started = time.time()
    descriptor: int | None = None
    owner_token = uuid.uuid4().hex
    while True:
        try:
            descriptor = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            owner = {
                "pid": os.getpid(),
                "created": time.time(),
                "token": owner_token,
                "runtime_identity": process_identity(os.getpid()),
            }
            os.write(descriptor, json.dumps(owner, separators=(",", ":")).encode("ascii"))
            break
        except FileExistsError:
            owner, valid_owner = _lock_owner(lock)
            try:
                fallback_created = lock.stat().st_mtime
            except FileNotFoundError:
                continue
            created = float(owner.get("created") or fallback_created)
            age = max(0.0, time.time() - created)
            pid = int(owner.get("pid") or 0)
            status = owner_status(owner) if valid_owner else "DAMAGED"
            if status in {"DEAD", "IDENTITY_CHANGED"}:
                try:
                    lock.unlink()
                    continue
                except FileNotFoundError:
                    continue
            if time.time() - started > timeout:
                if status == "DAMAGED":
                    raise TraceStateError(
                        f"local trace lock is damaged; controlled recovery required; age={round(age, 1)}s"
                    )
                raise TimeoutError(
                    f"local trace lock timeout; owner={pid}, owner_status={status}, age={round(age, 1)}s"
                )
            time.sleep(0.02)
    try:
        yield
    finally:
        if descriptor is not None:
            os.close(descriptor)
        current_owner, valid_owner = _lock_owner(lock)
        if valid_owner and current_owner.get("token") == owner_token:
            try:
                lock.unlink()
            except FileNotFoundError:
                pass


@contextlib.contextmanager
def trace_transaction(root: Path):
    try:
        with trace_lock(root):
            yield
    except (OSError, TimeoutError, TraceStateError) as exc:
        raise TraceWriteError("control trace persistence is pending; retry the same operation id") from exc
