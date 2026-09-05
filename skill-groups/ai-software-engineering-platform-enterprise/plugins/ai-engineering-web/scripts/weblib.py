from __future__ import annotations

import fnmatch
import hashlib
import json
import os
import sys
from pathlib import Path
from typing import Iterator

CORE_SCRIPTS = Path(__file__).resolve().parents[2] / "ai-engineering-core" / "scripts"
if str(CORE_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(CORE_SCRIPTS))
from resource_budget import effective_value  # noqa: E402
from source_surface import read_bounded_bytes, read_bounded_text  # noqa: E402

SKIP = {"node_modules", "dist", "build", ".git", ".next", ".nuxt", "coverage", ".cache", ".ai"}
SOURCE_EXT = {".ts", ".tsx", ".js", ".jsx", ".vue", ".svelte", ".css", ".scss", ".less"}


def read_json(path: Path, default=None):
    try:
        text,truncated=read_bounded_text(path,8*1024*1024);return default if truncated else json.loads(text)
    except Exception: return default


def source_files(root: Path, max_files: int = 5000) -> Iterator[Path]:
    max_files = effective_value("source_scan", "max_files", max_files)
    emitted = 0
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [name for name in dirnames if name not in SKIP]
        current = Path(dirpath)
        for filename in filenames:
            p = current / filename
            if p.suffix.lower() in SOURCE_EXT:
                if emitted >= max_files:
                    return
                emitted += 1
                yield p


def source_inventory(root: Path, max_files: int = 5000) -> tuple[list[Path], bool]:
    max_files = effective_value("source_scan", "max_files", max_files)
    files = list(source_files(root, max_files=max_files + 1))
    return files[:max_files], len(files) > max_files


def digest(path: Path) -> str:
    h = hashlib.sha256(); h.update(read_bounded_bytes(path,8*1024*1024)[0]); return h.hexdigest()


def glob_match(path: str, pattern: str) -> bool:
    path = path.replace("\\", "/"); pattern = pattern.replace("\\", "/")
    if fnmatch.fnmatchcase(path, pattern): return True
    if "/**/" in pattern and fnmatch.fnmatchcase(path, pattern.replace("/**/", "/")): return True
    return False
