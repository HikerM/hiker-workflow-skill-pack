from __future__ import annotations

import csv
import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "plugins" / "ai-engineering-core" / "scripts"))

from suite_router import route, skill_display


def evaluate() -> dict:
    positive = negative = positive_total = negative_total = 0
    failures = []
    with tempfile.TemporaryDirectory() as td:
        project = Path(td)
        for csv_path in sorted((ROOT / "plugins").glob("*/evals/prompts.csv")):
            for row in csv.DictReader(csv_path.open(encoding="utf-8")):
                selected = [item["skill"] for item in route(project, row["prompt"])["selected"]]
                should_trigger = str(row.get("should_trigger", "")).lower() == "true"
                if row["skill"] == "ai-engineering-router":
                    ok = bool(selected) if should_trigger else not selected
                else:
                    expected = skill_display(row["skill"])
                    ok = expected in selected if should_trigger else expected not in selected
                if should_trigger:
                    positive_total += 1; positive += int(ok)
                else:
                    negative_total += 1; negative += int(ok)
                if not ok:
                    failures.append({"id": row["id"], "expected_skill": row["skill"], "should_trigger": should_trigger, "selected": selected})
    return {
        "ok": not failures,
        "positive": {"passed": positive, "total": positive_total, "recall": round(positive / positive_total, 4) if positive_total else 1.0},
        "negative": {"passed": negative, "total": negative_total, "specificity": round(negative / negative_total, 4) if negative_total else 1.0},
        "failures": failures,
    }


if __name__ == "__main__":
    result = evaluate(); print(json.dumps(result, ensure_ascii=False, indent=2)); raise SystemExit(0 if result["ok"] else 2)
