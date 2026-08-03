from __future__ import annotations

import json
import sys
from pathlib import Path

from statectl import checkpoint


def main() -> int:
    try: payload = json.load(sys.stdin)
    except Exception: payload = {}
    root = Path(payload.get("cwd") or ".").resolve()
    if not (root / ".ai" / "schema.json").exists(): return 0
    label = f"precompact-{payload.get('trigger', 'unknown')}-{str(payload.get('session_id', 'session'))[-8:]}"
    try:
        checkpoint(root, label, event="PreCompact")
        print(json.dumps({"continue": True}))
    except Exception as exc:
        print(json.dumps({"continue": False, "stopReason": f"压缩前状态保存失败：{exc}", "systemMessage": "为避免丢失工程状态，本次压缩已停止。"}, ensure_ascii=False))
    return 0

if __name__ == "__main__": raise SystemExit(main())
