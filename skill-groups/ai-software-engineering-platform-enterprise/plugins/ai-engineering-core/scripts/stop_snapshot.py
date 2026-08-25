from __future__ import annotations

import json


def main() -> int:
    """5.16兼容入口；Stop事件不再持久化助手输出或Git绝对路径。"""
    print(json.dumps({"continue": True, "compatibility": "disabled-stop-capture"}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
