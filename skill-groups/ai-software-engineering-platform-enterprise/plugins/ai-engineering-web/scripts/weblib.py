from __future__ import annotations

import fnmatch
import hashlib
import json
import sys
from pathlib import Path
from typing import Iterator

CORE_SCRIPTS=Path(__file__).resolve().parents[2]/"ai-engineering-core"/"scripts"
if str(CORE_SCRIPTS) not in sys.path:sys.path.insert(0,str(CORE_SCRIPTS))
from source_surface import TraversalBudget, read_bounded_bytes, read_bounded_text, walk_source_files

SKIP = {"node_modules", "dist", "build", ".git", ".next", ".nuxt", "coverage", ".cache", ".ai"}
SOURCE_EXT = {".ts", ".tsx", ".js", ".jsx", ".vue", ".svelte", ".css", ".scss", ".less"}


def read_json(path: Path, default=None):
    try:
        text,truncated=read_bounded_text(path,8*1024*1024);return default if truncated else json.loads(text)
    except Exception: return default


def source_files(root: Path, max_files: int = 5000) -> Iterator[Path]:
    paths,_=walk_source_files(root,TraversalBudget(max_depth=12,max_directories=4096,max_entries=50000,max_files=max(20000,max_files*10),max_observed_bytes=2*1024*1024*1024,max_elapsed_ms=10000,max_entries_per_directory=max(8192,(max_files+1)*2)),ignored_directories=frozenset(name.casefold() for name in SKIP),include=lambda p:p.suffix.lower() in SOURCE_EXT and p.stat().st_size<=8*1024*1024)
    yield from paths[:max_files]


def source_inventory(root: Path, max_files: int = 5000) -> tuple[list[Path], bool]:
    files = list(source_files(root, max_files=max_files + 1))
    return files[:max_files], len(files) > max_files


def digest(path: Path) -> str:
    h = hashlib.sha256(); h.update(read_bounded_bytes(path,8*1024*1024)[0]); return h.hexdigest()


def glob_match(path: str, pattern: str) -> bool:
    path = path.replace("\\", "/"); pattern = pattern.replace("\\", "/")
    if fnmatch.fnmatchcase(path, pattern): return True
    if "/**/" in pattern and fnmatch.fnmatchcase(path, pattern.replace("/**/", "/")): return True
    return False
