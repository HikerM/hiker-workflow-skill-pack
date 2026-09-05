from __future__ import annotations

import hashlib
import contextlib
import json
import os
import subprocess
import tempfile
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

from process_identity import owner_status, process_identity
from source_surface import bounded_process_run

SCHEMA_VERSION = "1.0.0"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def run(cmd: list[str], cwd: Path, check: bool = True) -> subprocess.CompletedProcess[str]:
    safe = list(cmd)
    if len(safe) > 1 and safe[0] == "git" and safe[1] == "status" and "--" not in safe:
        safe.extend(["--", ".", ":(exclude).ai/**"])
    return bounded_process_run(safe, cwd, check=check)


def git_root(path: Path) -> Path:
    try:
        out = run(["git", "rev-parse", "--show-toplevel"], path).stdout.strip()
        return Path(out).resolve()
    except Exception:
        return path.resolve()


def git_info(path: Path) -> dict[str, Any]:
    root = git_root(path)
    info: dict[str, Any] = {"root": str(root), "is_git": False, "head": None, "branch": None, "dirty": None}
    try:
        info["head"] = run(["git", "rev-parse", "HEAD"], root).stdout.strip()
        branch = run(["git", "branch", "--show-current"], root, check=False).stdout.strip()
        info["branch"] = branch or "DETACHED"
        info["dirty"] = bool(run(["git", "status", "--porcelain"], root).stdout.strip())
        info["is_git"] = True
    except Exception:
        pass
    return info


def atomic_write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
            f.write("\n")
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_name, path)
    finally:
        if os.path.exists(tmp_name):
            os.unlink(tmp_name)


def atomic_write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as f:
            f.write(text)
            if text and not text.endswith("\n"):
                f.write("\n")
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_name, path)
    finally:
        if os.path.exists(tmp_name):
            os.unlink(tmp_name)


def atomic_write_bytes(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_name, path)
    finally:
        if os.path.exists(tmp_name):
            os.unlink(tmp_name)


def read_json(path: Path, default: Any = None) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return default


_LOCK_LOCAL = threading.local()
_PROCESS_LOCKS_GUARD = threading.Lock()
_PROCESS_LOCKS: dict[str, threading.RLock] = {}


def _process_lock(key: str) -> threading.RLock:
    with _PROCESS_LOCKS_GUARD:
        return _PROCESS_LOCKS.setdefault(key, threading.RLock())


@contextlib.contextmanager
def state_lock(project_root: Path, timeout: float = 15.0, stale_after: float = 120.0) -> Iterator[None]:
    """Serialize small .ai state transactions; re-entrant inside one thread."""
    lock = ai_root(project_root) / "runtime" / "core-state.lock"
    lock.parent.mkdir(parents=True, exist_ok=True)
    key = str(lock.resolve()).casefold()
    process_lock = _process_lock(key)
    process_lock.acquire()
    try:
        held = getattr(_LOCK_LOCAL, "held", {})
        if held.get(key, 0):
            held[key] += 1
            _LOCK_LOCAL.held = held
            try:
                yield
            finally:
                held[key] -= 1
            return
        started = time.time()
        fd: int | None = None
        while True:
            try:
                fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                os.write(fd, json.dumps({
                    "pid": os.getpid(),
                    "created": time.time(),
                    "runtime_identity": process_identity(os.getpid()),
                }).encode("utf-8"))
                break
            except FileExistsError:
                info = read_json(lock, {}) or {}
                age = time.time() - float(info.get("created", lock.stat().st_mtime))
                owner = int(info.get("pid", 0) or 0)
                if age > stale_after and owner_status(info) in {"DEAD", "IDENTITY_CHANGED"}:
                    try:
                        lock.unlink()
                        continue
                    except FileNotFoundError:
                        continue
                if time.time() - started > timeout:
                    raise TimeoutError(f"core state lock timeout; owner pid={owner}, age={round(age, 1)}s")
                time.sleep(0.05)
        held[key] = 1
        _LOCK_LOCAL.held = held
        try:
            yield
        finally:
            held.pop(key, None)
            if fd is not None:
                os.close(fd)
            try:
                lock.unlink()
            except FileNotFoundError:
                pass
    finally:
        process_lock.release()


def append_jsonl(path: Path, record: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n"
    with path.open("a", encoding="utf-8", newline="\n") as f:
        f.write(line)
        f.flush()
        os.fsync(f.fileno())


def sha256_file(path: Path) -> str | None:
    try:
        h = hashlib.sha256()
        with path.open("rb") as f:
            for chunk in iter(lambda: f.read(1024 * 1024), b""):
                h.update(chunk)
        return h.hexdigest()
    except OSError:
        return None


def ai_root(project_root: Path) -> Path:
    return project_root / ".ai"


def ensure_schema(project_root: Path) -> tuple[bool, str]:
    data = read_json(ai_root(project_root) / "schema.json")
    if not isinstance(data, dict):
        return False, "missing schema.json"
    version = str(data.get("version", ""))
    if version.split(".")[0] != SCHEMA_VERSION.split(".")[0]:
        return False, f"incompatible schema: {version}"
    return True, version
