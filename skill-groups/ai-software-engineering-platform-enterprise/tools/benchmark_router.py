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
PROPOSALS = (
    ("backend", "development", "backend-component-implementation"),
    ("hybrid", "governance", "workspace-task-router"),
    ("tooling", "review", "full-change-risk-review"),
    ("unknown", "governance", "bounded-context-memory"),
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
            architecture, stage, skill = PROPOSALS[index % len(PROPOSALS)]
            result = subprocess.run([
                sys.executable, "-X", "utf8", str(ROUTER), "--root", str(root),
                "--project-mode", "existing", "--architecture", architecture,
                "--stage", stage, "--current-action", "基准测试当前阶段",
                "--candidate", skill,
            ], stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, timeout=10)
            if result.returncode: raise RuntimeError(result.stderr.decode("utf-8", errors="replace"))
            samples.append((time.perf_counter() - start) * 1000)
    p95 = percentile(samples, .95)
    return {"ok": p95 <= max_p95_ms, "scope": "本地冷进程路由开销，不包含桌面端网络与模型首字延迟", "runs": runs, "median_ms": round(statistics.median(samples), 2), "p95_ms": round(p95, 2), "max_p95_ms": max_p95_ms}


def main() -> int:
    parser = argparse.ArgumentParser(); parser.add_argument("--runs", type=int, default=20); parser.add_argument("--max-p95-ms", type=float, default=200)
    args = parser.parse_args(); data = benchmark(max(3, args.runs), args.max_p95_ms); print(json.dumps(data, ensure_ascii=False, indent=2)); return 0 if data["ok"] else 2


if __name__ == "__main__": raise SystemExit(main())
