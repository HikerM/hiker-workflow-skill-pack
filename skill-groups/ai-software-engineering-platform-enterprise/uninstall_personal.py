from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import tempfile
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
NAMES = sorted(p.name for p in (ROOT / "plugins").iterdir() if p.is_dir())
BLOCK_START = "<!-- ai-engineering-global-governance start -->"
BLOCK_END = "<!-- ai-engineering-global-governance end -->"


def atomic_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True); fd, tmp = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle: handle.write(text); handle.flush(); os.fsync(handle.fileno())
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp): os.unlink(tmp)


def remove_global_agents(home: Path, stamp: str) -> dict:
    target = home / ".codex" / "AGENTS.md"
    if not target.exists(): return {"path": str(target), "status": "not-present", "backup": None}
    original = target.read_text(encoding="utf-8"); pattern = re.compile(r"\n*" + re.escape(BLOCK_START) + r".*?" + re.escape(BLOCK_END) + r"\n*", re.S); matches = pattern.findall(original)
    if not matches: return {"path": str(target), "status": "not-present", "backup": None}
    if len(matches) > 1: raise RuntimeError("multiple managed governance blocks found; refusing ambiguous removal")
    backup = home / ".codex" / "agents-backup" / stamp / "AGENTS.md"; backup.parent.mkdir(parents=True, exist_ok=True); shutil.copy2(target, backup)
    updated = pattern.sub("\n\n", original, count=1).strip()
    atomic_text(target, updated + ("\n" if updated else "")); return {"path": str(target), "status": "removed", "backup": str(backup)}


def main() -> int:
    parser = argparse.ArgumentParser(); parser.add_argument("--yes", action="store_true"); parser.add_argument("--keep-global-agents", action="store_true", help="卸载插件但保留全局自动应用规则"); args = parser.parse_args()
    if not args.yes: raise SystemExit("这是卸载操作，请使用 --yes 明确确认。")
    home = Path.home(); market = home / ".agents" / "plugins" / "marketplace.json"; stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    for name in NAMES: shutil.rmtree(home / ".codex" / "plugins" / name, ignore_errors=True)
    try:
        data = json.loads(market.read_text(encoding="utf-8")); data["plugins"] = [item for item in data.get("plugins", []) if item.get("name") not in NAMES]
        atomic_text(market, json.dumps(data, ensure_ascii=False, indent=2) + "\n")
    except Exception: pass
    global_agents = {"path": str(home / ".codex" / "AGENTS.md"), "status": "kept", "backup": None} if args.keep_global_agents else remove_global_agents(home, stamp)
    print(json.dumps({"ok": True, "removed": NAMES, "global_agents": global_agents, "note": "Codex已安装缓存和启用状态仍应通过桌面端或codex plugin命令管理。"}, ensure_ascii=False, indent=2)); return 0


if __name__ == "__main__": raise SystemExit(main())
