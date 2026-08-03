from __future__ import annotations

import fnmatch
import hashlib
import json
import os
from pathlib import Path
from typing import Iterator

SKIP = {"node_modules", "dist", "build", ".git", ".next", ".nuxt", "coverage", ".cache", ".ai"}
SOURCE_EXT = {".ts", ".tsx", ".js", ".jsx", ".vue", ".svelte", ".css", ".scss", ".less"}


def read_json(path: Path, default=None):
    try: return json.loads(path.read_text(encoding="utf-8"))
    except Exception: return default


def source_files(root: Path) -> Iterator[Path]:
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [name for name in dirnames if name not in SKIP]
        current = Path(dirpath)
        for filename in filenames:
            p = current / filename
            if p.suffix.lower() in SOURCE_EXT:
                yield p


def digest(path: Path) -> str:
    h = hashlib.sha256(); h.update(path.read_bytes()); return h.hexdigest()


def glob_match(path: str, pattern: str) -> bool:
    path = path.replace("\\", "/"); pattern = pattern.replace("\\", "/")
    if fnmatch.fnmatchcase(path, pattern): return True
    if "/**/" in pattern and fnmatch.fnmatchcase(path, pattern.replace("/**/", "/")): return True
    return False
