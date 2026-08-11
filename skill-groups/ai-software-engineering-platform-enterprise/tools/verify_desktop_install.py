from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from install_personal import load, verify_installation


def main() -> int:
    parser = argparse.ArgumentParser(description="核验桌面端插件源目录、安装目录、发现缓存、启用配置和全局规则是否一致。")
    parser.add_argument("--home", default=str(Path.home()))
    args = parser.parse_args()
    home = Path(args.home).resolve()
    marketplace = load(home / ".agents" / "plugins" / "marketplace.json").get("name", "personal-ai-engineering-marketplace")
    result = verify_installation(home, str(marketplace))
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["ok"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
