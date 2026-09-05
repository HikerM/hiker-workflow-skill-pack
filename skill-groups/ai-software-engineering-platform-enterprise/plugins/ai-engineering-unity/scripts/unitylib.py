from __future__ import annotations
import json, re, sys
from pathlib import Path

CORE_SCRIPTS=Path(__file__).resolve().parents[2]/"ai-engineering-core"/"scripts"
if str(CORE_SCRIPTS) not in sys.path:sys.path.insert(0,str(CORE_SCRIPTS))
from source_surface import TraversalBudget,read_bounded_text,walk_source_files

SKIP={"Library","Temp","Logs","obj","bin","Build","Builds",".git",".ai","UserSettings"}

def walk_files(root:Path):
    paths,_=walk_source_files(root,TraversalBudget(max_depth=12,max_directories=4096,max_entries=50000,max_files=20000,max_observed_bytes=4*1024*1024*1024,max_elapsed_ms=10000),ignored_directories=frozenset(name.casefold() for name in SKIP),include=lambda path:path.stat().st_size<=16*1024*1024)
    yield from paths

def files(root:Path,suffixes:set[str]):
    for p in walk_files(root):
        if p.suffix.lower() in suffixes:
            yield p

def asset_files(root:Path):
    assets=root/"Assets"
    if assets.exists():
        yield from walk_files(assets)

def read_json(path:Path,default=None):
    try:
        value,truncated=read_bounded_text(path,8*1024*1024);return default if truncated else json.loads(value)
    except Exception:return default

def project_version(root:Path):
    p=root/"ProjectSettings/ProjectVersion.txt"
    if not p.exists():return None
    m=re.search(r"m_EditorVersion:\s*([^\r\n]+)",read_bounded_text(p,64*1024)[0])
    return m.group(1).strip() if m else None
