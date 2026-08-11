from __future__ import annotations

import argparse
import json
import re
from datetime import datetime, timezone
from pathlib import Path

from corelib import atomic_write_json, atomic_write_text, git_info, sha256_file
from requirements_fusion import init as init_requirements, merge as merge_requirements

SCHEMA = "1.0.0"
CHANGE_TYPES = {"add", "modify", "replace", "remove"}


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}


def locations(root: Path) -> dict[str, Path]:
    return {
        "baseline": root / ".ai/requirements/source-baseline.json",
        "result": root / ".ai/requirements/reconciliation.json",
        "context": root / ".ai/context/requirement-reconciliation.json",
        "markdown": root / "REQUIREMENT_DELTA.md",
    }


def safe_evidence(root: Path, raw: str) -> tuple[str, Path]:
    candidate = (root / raw).resolve()
    try:
        relative = candidate.relative_to(root.resolve()).as_posix()
    except ValueError as exc:
        raise ValueError(f"证据路径越出仓库：{raw}") from exc
    if not candidate.is_file():
        raise ValueError(f"证据文件不存在：{raw}")
    return relative, candidate


def initialize(root: Path, project_id: str, goal: str) -> dict:
    paths = locations(root)
    tech = read_json(root / ".ai/context/tech-stack.json")
    init_requirements(root, project_id, goal, mode="brownfield")
    if not paths["baseline"].exists():
        atomic_write_json(paths["baseline"], {
            "schema_version": SCHEMA,
            "project_id": project_id,
            "git": git_info(root),
            "tech_stack_snapshot": tech,
            "capabilities": [],
            "unknowns": ["尚未登记现有能力及其代码/测试证据"],
            "updated_at": now(),
        })
    atomic_write_json(paths["context"], {
        "schema_version": SCHEMA,
        "project_id": project_id,
        "goal": goal,
        "mode": "brownfield",
        "stage": "BASELINE_DISCOVERY",
        "baseline_status": "PENDING",
        "checkpoint_status": "PENDING",
        "updated_at": now(),
    })
    render(root)
    return {"ok": True, "mode": "brownfield", "baseline": str(paths["baseline"])}


def set_baseline(root: Path, payload: dict) -> dict:
    paths = locations(root)
    current = read_json(paths["baseline"])
    if not current:
        raise RuntimeError("请先执行 init")
    capabilities = payload.get("capabilities", [])
    errors: list[str] = []
    normalized = []
    seen = set()
    for cap in capabilities:
        cap_id = str(cap.get("id", ""))
        if not re.fullmatch(r"CAP-[0-9]{3,}", cap_id): errors.append(f"无效能力ID：{cap_id}"); continue
        if cap_id in seen: errors.append(f"重复能力ID：{cap_id}"); continue
        seen.add(cap_id)
        if not str(cap.get("statement", "")).strip(): errors.append(f"{cap_id} 缺少statement"); continue
        evidence = []
        for raw in cap.get("evidence", []):
            try:
                rel, path = safe_evidence(root, str(raw)); evidence.append({"path": rel, "sha256": sha256_file(path)})
            except ValueError as exc: errors.append(f"{cap_id}: {exc}")
        if not evidence: errors.append(f"{cap_id} 缺少有效仓库内证据")
        normalized.append({
            "id": cap_id,
            "statement": str(cap["statement"]).strip(),
            "confidence": cap.get("confidence", "observed"),
            "evidence": evidence,
            "modules": list(cap.get("modules", [])),
            "apis": list(cap.get("apis", [])),
            "data": list(cap.get("data", [])),
            "tests": list(cap.get("tests", [])),
        })
    if errors: return {"ok": False, "errors": errors}
    current.update({"capabilities": sorted(normalized, key=lambda x: x["id"]), "unknowns": list(payload.get("unknowns", [])), "updated_at": now()})
    atomic_write_json(paths["baseline"], current)
    context = read_json(paths["context"]); context.update({"baseline_status": "RECORDED", "stage": "REQUIREMENT_RECONCILIATION", "updated_at": now()}); atomic_write_json(paths["context"], context)
    render(root)
    return {"ok": True, "capability_count": len(normalized), "unknown_count": len(current["unknowns"])}


def reconcile(root: Path, payload: dict) -> dict:
    paths = locations(root); baseline = read_json(paths["baseline"])
    if not baseline.get("capabilities"):
        return {"ok": False, "errors": ["现有能力基线为空；先执行 baseline"]}
    capability_ids = {x["id"] for x in baseline["capabilities"]}
    requirements = payload.get("requirements", [])
    errors, blockers, matrix = [], [], []
    for item in requirements:
        change_type = item.get("change_type")
        targets = list(item.get("targets", []))
        req_id = str(item.get("id", "UNKNOWN"))
        if change_type not in CHANGE_TYPES: errors.append(f"{req_id}: change_type无效")
        if change_type != "add" and not targets: blockers.append(f"{req_id}: 非新增需求必须指向CAP")
        missing = sorted(set(targets) - capability_ids)
        if missing: blockers.append(f"{req_id}: 目标能力不存在 {', '.join(missing)}")
        impact = {key: list(item.get("impact", {}).get(key, [])) for key in ("modules", "apis", "data", "permissions", "tests", "migrations")}
        if not any(impact.values()): blockers.append(f"{req_id}: 尚未记录影响范围")
        matrix.append({"requirement_id": req_id, "change_type": change_type, "targets": targets, "impact": impact})
    if errors: return {"ok": False, "errors": errors}
    merged = merge_requirements(root, requirements, mode="brownfield")
    if not merged.get("ok"): return merged
    result = {
        "schema_version": SCHEMA,
        "project_id": baseline.get("project_id"),
        "baseline_updated_at": baseline.get("updated_at"),
        "matrix": matrix,
        "blockers": blockers,
        "checkpoint_required": any(row["impact"][key] for row in matrix for key in ("apis", "data", "permissions", "migrations")),
        "status": "BLOCKED" if blockers else "READY_FOR_PLANNING",
        "updated_at": now(),
    }
    atomic_write_json(paths["result"], result)
    context = read_json(paths["context"]); context.update({"stage": result["status"], "checkpoint_status": "REQUIRED" if result["checkpoint_required"] else "NOT_REQUIRED", "updated_at": now()}); atomic_write_json(paths["context"], context)
    render(root)
    return {"ok": not blockers, **result}


def render(root: Path) -> None:
    paths = locations(root); baseline, result = read_json(paths["baseline"]), read_json(paths["result"])
    lines = ["# REQUIREMENT DELTA", "", f"- 模式：brownfield", f"- 存量能力：{len(baseline.get('capabilities', []))}", f"- 对账状态：{result.get('status', 'BASELINE_DISCOVERY')}", f"- Checkpoint：{'需要' if result.get('checkpoint_required') else '暂不需要'}", "", "## 存量能力基线", ""]
    lines += [f"- **{x['id']}** {x['statement']}（证据：{', '.join(e['path'] for e in x.get('evidence', []))}）" for x in baseline.get("capabilities", [])] or ["- 尚未登记。"]
    lines += ["", "## 需求变更矩阵", ""]
    for row in result.get("matrix", []):
        affected = [f"{k}={','.join(v)}" for k, v in row["impact"].items() if v]
        lines.append(f"- **{row['requirement_id']} [{row['change_type']}]** targets={','.join(row['targets']) or '-'}；{'；'.join(affected) or '影响待补充'}")
    lines += ["", "## 阻塞与未知", ""]
    lines += [f"- BLOCKER：{x}" for x in result.get("blockers", [])] or [f"- 未知：{x}" for x in baseline.get("unknowns", [])] or ["- 无。"]
    lines += ["", "> 完整事实见 `.ai/requirements/source-baseline.json`、`ledger.json` 与 `reconciliation.json`。", ""]
    atomic_write_text(paths["markdown"], "\n".join(lines))


def validate(root: Path) -> dict:
    paths = locations(root); baseline, result = read_json(paths["baseline"]), read_json(paths["result"]); errors = []
    if baseline.get("schema_version") != SCHEMA: errors.append("缺少或不兼容的source-baseline.json")
    for cap in baseline.get("capabilities", []):
        for evidence in cap.get("evidence", []):
            try:
                _, path = safe_evidence(root, evidence["path"])
                if sha256_file(path) != evidence.get("sha256"): errors.append(f"{cap['id']}: 证据哈希已变化")
            except ValueError as exc: errors.append(f"{cap['id']}: {exc}")
    if result and result.get("blockers"): errors.extend(result["blockers"])
    return {"ok": not errors, "capability_count": len(baseline.get("capabilities", [])), "errors": errors}


def main() -> int:
    parser = argparse.ArgumentParser(); sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("init"); p.add_argument("--root", default="."); p.add_argument("--project-id", required=True); p.add_argument("--goal", required=True)
    for name in ("baseline", "reconcile"):
        p = sub.add_parser(name); p.add_argument("--root", default="."); p.add_argument("--input", required=True)
    p = sub.add_parser("validate"); p.add_argument("--root", default=".")
    args = parser.parse_args(); root = Path(args.root).resolve()
    if args.command == "init": result = initialize(root, args.project_id, args.goal)
    elif args.command == "baseline": result = set_baseline(root, json.loads(Path(args.input).read_text(encoding="utf-8")))
    elif args.command == "reconcile": result = reconcile(root, json.loads(Path(args.input).read_text(encoding="utf-8")))
    else: result = validate(root)
    print(json.dumps(result, ensure_ascii=False, indent=2)); return 0 if result.get("ok") else 2


if __name__ == "__main__": raise SystemExit(main())
