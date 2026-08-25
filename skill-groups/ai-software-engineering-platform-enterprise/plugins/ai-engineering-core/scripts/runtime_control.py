from __future__ import annotations

import json
import sys


def main() -> int:
    """5.16兼容入口；不再读取Prompt或用关键词决定控制动作。"""
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    print(json.dumps({
        "continue": True,
        "compatibility": "disabled-prompt-classifier",
        "replacement": "由ChatGPT/Codex在当前语义轮次选择动作，再显式调用hikerctl transition --control-action",
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
