from __future__ import annotations
import json, sys
from pathlib import Path
from corelib import ai_root, append_jsonl, git_info, utc_now

def main() -> int:
    try: p = json.load(sys.stdin)
    except Exception: p = {}
    root = Path(p.get("cwd") or ".").resolve()
    if (ai_root(root) / "schema.json").exists(): append_jsonl(ai_root(root) / "logs" / "execution.jsonl", {"event": "session_end", "at": utc_now(), "session_id": p.get("session_id"), "reason": p.get("reason"), "git": git_info(root)})
    return 0
if __name__ == "__main__": raise SystemExit(main())
