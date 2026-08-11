from __future__ import annotations

import argparse
import json
import statistics
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ROUTER = ROOT / "plugins" / "ai-engineering-core" / "scripts" / "suite_router.py"
PROMPTS = (
    "修改现有登录功能",
    "修改登录功能，包含前端页面和后端接口",
    "检查桌面端插件为什么选择很慢",
    "大型项目跨多会话开发，上下文压缩不能丢失决定",
)


def percentile(values: list[float], ratio: float) -> float:
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, max(0, int(len(ordered) * ratio + 0.999) - 1))]


def benchmark(runs: int, max_p95_ms: float) -> dict:
    samples = []
    with tempfile.TemporaryDirectory() as td:
        root = Path(td); (root / "package.json").write_text('{"dependencies":{"react":"19","fastify":"5"}}', encoding="utf-8")
        for index in range(runs):
            start = time.perf_counter()
            result = subprocess.run([sys.executable, "-X", "utf8", str(ROUTER), "--root", str(root), "--request", PROMPTS[index % len(PROMPTS)]], stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, timeout=10)
            if result.returncode: raise RuntimeError(result.stderr.decode("utf-8", errors="replace"))
            samples.append((time.perf_counter() - start) * 1000)
    p95 = percentile(samples, .95)
    return {"ok": p95 <= max_p95_ms, "scope": "本地冷进程路由开销，不包含桌面端网络与模型首字延迟", "runs": runs, "median_ms": round(statistics.median(samples), 2), "p95_ms": round(p95, 2), "max_p95_ms": max_p95_ms}


def main() -> int:
    parser = argparse.ArgumentParser(); parser.add_argument("--runs", type=int, default=20); parser.add_argument("--max-p95-ms", type=float, default=500)
    args = parser.parse_args(); data = benchmark(max(3, args.runs), args.max_p95_ms); print(json.dumps(data, ensure_ascii=False, indent=2)); return 0 if data["ok"] else 2


if __name__ == "__main__": raise SystemExit(main())
