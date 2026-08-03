from __future__ import annotations

import json
import sys
from pathlib import Path

from corelib import ai_root, append_jsonl, git_info, utc_now


def main() -> int:
    try: payload = json.load(sys.stdin)
    except Exception: payload = {}
    root = Path(payload.get("cwd") or ".").resolve()
    if (ai_root(root) / "schema.json").exists():
        append_jsonl(ai_root(root) / "logs" / "execution.jsonl", {"event": "turn_stop", "at": utc_now(), "session_id": payload.get("session_id"), "turn_id": payload.get("turn_id"), "git": git_info(root), "assistant_tail": str(payload.get("last_assistant_message") or "")[-4000:]})
    print(json.dumps({"continue": True})); return 0

if __name__ == "__main__": raise SystemExit(main())
