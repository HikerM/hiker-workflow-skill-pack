from __future__ import annotations

import argparse
import json
import re
from datetime import datetime, timezone
from pathlib import Path

from corelib import atomic_write_json, atomic_write_text

SCHEMA = "1.0.0"
VALID_PRIORITIES = {"must", "should", "could", "wont"}


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def paths(root: Path, mode: str = "greenfield") -> tuple[Path, Path, Path]:
    context_name = "greenfield.json" if mode == "greenfield" else "requirement-reconciliation.json"
    return root / ".ai/requirements/ledger.json", root / ".ai/context" / context_name, root / "REQUIREMENTS.md"


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}


def render(root: Path, limit: int = 30, mode: str = "greenfield") -> None:
    ledger_path, context_path, markdown_path = paths(root, mode)
    ledger, context = load_json(ledger_path), load_json(context_path)
    items = ledger.get("requirements", [])
    active = [x for x in items if x.get("status", "active") != "superseded"][: max(1, limit)]
    lines = ["# REQUIREMENTS", "", f"- 项目：{context.get('project_id', 'UNKNOWN')}", f"- 目标：{context.get('goal', '')}", f"- 阶段：{context.get('stage', 'DISCOVERY')}", f"- 活动需求：{len(items)}（当前切片 {len(active)}）", "", "## 当前需求", ""]
    for item in active:
        acceptance = "；".join(item.get("acceptance", [])) or "待补充"
        lines.append(f"- **{item['id']} [{item['priority']}]** {item['statement']}（验收：{acceptance}）")
    conflicts = [(item["id"], target) for item in items for target in item.get("conflicts_with", [])]
    lines += ["", "## 冲突与未知", ""]
    lines += [f"- {a} 与 {b} 冲突，必须解决后锁定相关决策。" for a, b in conflicts] or ["- 当前未记录显式冲突。"]
    unknowns = context.get("unknowns", [])
    lines += [f"- 未知：{x}" for x in unknowns] or ["- 当前未记录未知项。"]
    lines += ["", "## 关键决策", "", f"- Checkpoint：{context.get('checkpoint_status', 'AUTO_RECORD_REQUIRED')}", f"- 决策模式：{context.get('decision_mode', 'automatic_non_blocking')}", f"- 已锁定：{', '.join(context.get('locked_decisions', [])) or '无'}", "", "> 决策 Checkpoint 自动记录后非阻塞继续，不设置人工审批暂停点。完整历史和被裁剪需求见 `.ai/requirements/ledger.json`，会话只加载本文件活动切片。", ""]
    atomic_write_text(markdown_path, "\n".join(lines))


def init(root: Path, project_id: str, goal: str, mode: str = "greenfield") -> dict:
    ledger_path, context_path, _ = paths(root, mode)
    if not ledger_path.exists():
        atomic_write_json(ledger_path, {"schema_version": SCHEMA, "revision": 0, "requirements": [], "updated_at": now()})
    if not context_path.exists():
        unknowns = ["目标平台与部署边界", "数据与安全边界", "可验收的核心工作流"] if mode == "greenfield" else ["现有能力及代码证据", "新增需求与存量行为的冲突", "兼容与迁移边界"]
        atomic_write_json(context_path, {"schema_version": SCHEMA, "project_id": project_id, "goal": goal, "mode": mode, "stage": "REQUIREMENTS", "decision_mode": "automatic_non_blocking", "checkpoint_status": "AUTO_RECORD_REQUIRED", "locked_decisions": [], "unknowns": unknowns, "updated_at": now()})
    else:
        context = load_json(context_path)
        if context.get("decision_mode") != "automatic_non_blocking" or context.get("checkpoint_status") in {"PENDING", "REQUIRED"}:
            context.update({"decision_mode": "automatic_non_blocking", "checkpoint_status": "AUTO_RECORD_REQUIRED", "updated_at": now()})
            atomic_write_json(context_path, context)
    render(root, mode=mode)
    return {"ok": True, "ledger": str(ledger_path), "context": str(context_path)}


def validate_item(item: dict) -> list[str]:
    errors = []
    if not re.fullmatch(r"REQ-[0-9]{3,}", str(item.get("id", ""))): errors.append("id 必须为 REQ-001 格式")
    if not str(item.get("statement", "")).strip(): errors.append("statement 不能为空")
    if item.get("priority", "") not in VALID_PRIORITIES: errors.append("priority 必须为 must/should/could/wont")
    if not isinstance(item.get("acceptance", []), list): errors.append("acceptance 必须为数组")
    return errors


def merge(root: Path, incoming: list[dict], mode: str = "greenfield") -> dict:
    ledger_path, _, _ = paths(root, mode)
    ledger = load_json(ledger_path)
    if not ledger: raise RuntimeError("请先执行 init")
    errors = {str(x.get("id", "UNKNOWN")): validate_item(x) for x in incoming}
    errors = {k: v for k, v in errors.items() if v}
    if errors: return {"ok": False, "errors": errors}
    by_id = {x["id"]: x for x in ledger.get("requirements", [])}
    added, updated = [], []
    for raw in incoming:
        item = {"type": "functional", "source": "user", "status": "active", "dependencies": [], "conflicts_with": [], "acceptance": [], **raw}
        old = by_id.get(item["id"])
        if old and {k: v for k, v in old.items() if k not in {"history", "updated_at"}} != item:
            history = list(old.get("history", []))
            history.append({"revision": ledger.get("revision", 0), "snapshot": {k: v for k, v in old.items() if k != "history"}, "replaced_at": now()})
            item["history"] = history[-20:]
            updated.append(item["id"])
        elif old:
            item = old
        else:
            added.append(item["id"])
        item["updated_at"] = now()
        by_id[item["id"]] = item
    ledger.update({"revision": int(ledger.get("revision", 0)) + 1, "requirements": sorted(by_id.values(), key=lambda x: x["id"]), "updated_at": now()})
    atomic_write_json(ledger_path, ledger)
    render(root, mode=mode)
    return {"ok": True, "revision": ledger["revision"], "added": added, "updated": updated, "conflicts": sum(len(x.get("conflicts_with", [])) for x in by_id.values())}


def validate(root: Path) -> dict:
    ledger = load_json(paths(root)[0]); seen = set(); errors = []
    for item in ledger.get("requirements", []):
        errors += [f"{item.get('id')}: {e}" for e in validate_item(item)]
        if item.get("id") in seen: errors.append(f"重复ID: {item.get('id')}")
        seen.add(item.get("id"))
    return {"ok": not errors, "count": len(seen), "errors": errors}


def main() -> int:
    parser = argparse.ArgumentParser(); sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("init"); p.add_argument("--root", default="."); p.add_argument("--project-id", required=True); p.add_argument("--goal", required=True); p.add_argument("--mode", choices=["greenfield", "brownfield"], default="greenfield")
    p = sub.add_parser("merge"); p.add_argument("--root", default="."); p.add_argument("--input", required=True)
    p = sub.add_parser("validate"); p.add_argument("--root", default=".")
    p = sub.add_parser("slice"); p.add_argument("--root", default="."); p.add_argument("--limit", type=int, default=30)
    args = parser.parse_args(); root = Path(args.root).resolve()
    if args.command == "init": result = init(root, args.project_id, args.goal, args.mode)
    elif args.command == "merge":
        payload = json.loads(Path(args.input).read_text(encoding="utf-8")); result = merge(root, payload if isinstance(payload, list) else payload.get("requirements", []))
    elif args.command == "validate": result = validate(root)
    else: render(root, args.limit); result = {"ok": True, "output": str(paths(root)[2])}
    print(json.dumps(result, ensure_ascii=False, indent=2)); return 0 if result.get("ok") else 2


if __name__ == "__main__": raise SystemExit(main())
