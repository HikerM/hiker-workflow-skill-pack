from __future__ import annotations

import json


def main() -> int:
    """5.16兼容入口；不再记录助手消息、会话内容或Agent生命周期事件。"""
    print(json.dumps({"continue": True, "compatibility": "disabled-lifecycle-event-capture"}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
