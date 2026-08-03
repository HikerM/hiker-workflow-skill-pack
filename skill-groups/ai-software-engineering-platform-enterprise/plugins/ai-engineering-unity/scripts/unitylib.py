from __future__ import annotations
import json, os, re
from pathlib import Path

SKIP={"Library","Temp","Logs","obj","bin","Build","Builds",".git",".ai","UserSettings"}

def walk_files(root:Path):
    for dirpath,dirnames,filenames in os.walk(root):
        dirnames[:] = [name for name in dirnames if name not in SKIP]
        current=Path(dirpath)
        for filename in filenames:
            yield current/filename

def files(root:Path,suffixes:set[str]):
    for p in walk_files(root):
        if p.suffix.lower() in suffixes:
            yield p

def asset_files(root:Path):
    assets=root/"Assets"
    if assets.exists():
        yield from walk_files(assets)

def read_json(path:Path,default=None):
    try:return json.loads(path.read_text(encoding="utf-8"))
    except Exception:return default

def project_version(root:Path):
    p=root/"ProjectSettings/ProjectVersion.txt"
    if not p.exists():return None
    m=re.search(r"m_EditorVersion:\s*([^\r\n]+)",p.read_text(encoding="utf-8",errors="ignore"))
    return m.group(1).strip() if m else None
