from __future__ import annotations

import hashlib
import json
import os
import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCHEMA_VERSION = "1.0.0"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def run(cmd: list[str], cwd: Path, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, cwd=str(cwd), text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=check)


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


def read_json(path: Path, default: Any = None) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return default


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
