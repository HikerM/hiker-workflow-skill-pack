from __future__ import annotations

import argparse
import json
import re
import time
from collections import defaultdict, deque
from pathlib import Path

DEFAULT_CONTRACT = Path(".ai/ui/interaction-contracts.json")
MAX_BYTES = 1024 * 1024
MAX_INTERACTIONS = 500
MAX_STATES = 64
MAX_TRANSITIONS = 256
MAX_FINDINGS = 50
ID_RE = re.compile(r"^INT-[A-Z0-9]+(?:-[A-Z0-9]+)*$")
ASYNC_POLICIES = {"latest-wins", "single-flight", "queue", "idempotent"}
OVERLAY_KINDS = {"modal", "drawer", "popover", "menu", "combobox", "tooltip", "toast"}
HIDDEN_SURFACES = {"select", "combobox", "dropdown", "menu", "context-menu", "modal", "drawer", "popover", "tooltip", "date-picker", "tree", "cascader", "upload", "editor"}


def finding(target: list[dict], code: str, message: str, interaction_id: str | None = None) -> None:
    if len(target) < MAX_FINDINGS:
        item = {"code": code, "message": message}
        if interaction_id:
            item["interaction_id"] = interaction_id
        target.append(item)


def load_contract(path: Path) -> dict:
    size = path.stat().st_size
    if size > MAX_BYTES:
        raise ValueError(f"契约超过 {MAX_BYTES} 字节上限，请按模块拆分")
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("契约根节点必须是 JSON 对象")
    return data


def reachable(initial: str, transitions: list[dict]) -> set[str]:
    graph: dict[str, set[str]] = defaultdict(set)
    for row in transitions:
        source, target = row.get("from"), row.get("to")
        if isinstance(source, str) and isinstance(target, str):
            graph[source].add(target)
    seen = {initial}
    queue = deque([initial])
    while queue:
        for target in graph.get(queue.popleft(), set()):
            if target not in seen:
                seen.add(target)
                queue.append(target)
    return seen


def evaluate(contract: dict, mode: str = "review") -> dict:
    started = time.perf_counter()
    errors: list[dict] = []
    warnings: list[dict] = []
    interactions = contract.get("interactions", [])
    if not isinstance(interactions, list):
        interactions = []
        finding(errors, "INVALID_INTERACTIONS", "interactions 必须是数组")
    if len(interactions) > MAX_INTERACTIONS:
        finding(errors, "TOO_MANY_INTERACTIONS", f"交互数量超过 {MAX_INTERACTIONS}，请按模块拆分")
        interactions = interactions[:MAX_INTERACTIONS]

    seen_ids: set[str] = set()
    shortcuts: dict[tuple[str, str, str], str] = {}
    transition_count = 0
    state_count = 0
    for row in interactions:
        if not isinstance(row, dict):
            finding(errors, "INVALID_INTERACTION", "交互条目必须是对象")
            continue
        interaction_id = str(row.get("id") or "")
        if not ID_RE.fullmatch(interaction_id):
            finding(errors, "INVALID_ID", "交互 ID 必须符合 INT-大写稳定标识", interaction_id or None)
        elif interaction_id in seen_ids:
            finding(errors, "DUPLICATE_ID", "交互 ID 重复", interaction_id)
        seen_ids.add(interaction_id)
        for field in ("owner", "scope", "surface", "initial_state"):
            if not str(row.get(field) or "").strip():
                finding(errors, "MISSING_FIELD", f"缺少 {field}", interaction_id or None)

        states = row.get("states", [])
        transitions = row.get("transitions", [])
        if not isinstance(states, list) or not all(isinstance(x, str) and x for x in states):
            finding(errors, "INVALID_STATES", "states 必须是非空字符串数组", interaction_id or None)
            states = []
        if len(states) > MAX_STATES:
            finding(errors, "TOO_MANY_STATES", f"单个交互状态超过 {MAX_STATES}", interaction_id or None)
            states = states[:MAX_STATES]
        state_count += len(states)
        state_set = set(states)
        initial = str(row.get("initial_state") or "")
        if initial and initial not in state_set:
            finding(errors, "INVALID_INITIAL_STATE", "initial_state 不在 states 中", interaction_id or None)
        if not isinstance(transitions, list):
            finding(errors, "INVALID_TRANSITIONS", "transitions 必须是数组", interaction_id or None)
            transitions = []
        if len(transitions) > MAX_TRANSITIONS:
            finding(errors, "TOO_MANY_TRANSITIONS", f"单个交互转换超过 {MAX_TRANSITIONS}", interaction_id or None)
            transitions = transitions[:MAX_TRANSITIONS]
        transition_count += len(transitions)
        for transition in transitions:
            if not isinstance(transition, dict):
                finding(errors, "INVALID_TRANSITION", "状态转换必须是对象", interaction_id or None)
                continue
            source, target, event = transition.get("from"), transition.get("to"), transition.get("event")
            if source not in state_set or target not in state_set or not str(event or "").strip():
                finding(errors, "BROKEN_TRANSITION", "转换必须引用已声明状态并包含 event", interaction_id or None)
            if transition.get("async") is True:
                policy = transition.get("policy")
                if policy not in ASYNC_POLICIES:
                    finding(errors, "MISSING_ASYNC_POLICY", "异步转换必须声明有效并发策略", interaction_id or None)
                cancel_on = transition.get("cancel_on", [])
                if policy == "latest-wins" and (not isinstance(cancel_on, list) or not cancel_on):
                    finding(errors, "INVALID_CANCEL_POLICY", "latest-wins 必须声明非空 cancel_on", interaction_id or None)
            if transition.get("destructive") is True and transition.get("policy") not in {"single-flight", "idempotent"}:
                finding(errors, "UNSAFE_DESTRUCTIVE_ACTION", "危险写操作必须使用 single-flight 或 idempotent", interaction_id or None)
        if initial in state_set:
            unreachable = state_set - reachable(initial, transitions)
            if unreachable:
                finding(errors, "UNREACHABLE_STATE", f"存在不可达状态：{', '.join(sorted(unreachable)[:8])}", interaction_id or None)

        overlay = row.get("overlay")
        if overlay is not None:
            if not isinstance(overlay, dict) or overlay.get("kind") not in OVERLAY_KINDS:
                finding(errors, "INVALID_OVERLAY", "overlay.kind 不受支持", interaction_id or None)
            else:
                token = overlay.get("priority_token")
                if isinstance(token, (int, float)) or not str(token or "").startswith("layer."):
                    finding(errors, "RAW_OVERLAY_PRIORITY", "浮层必须使用 layer.* 语义层级令牌", interaction_id or None)
                if not str(overlay.get("group") or ""):
                    finding(errors, "MISSING_OVERLAY_GROUP", "浮层必须声明互斥组", interaction_id or None)

        for shortcut in row.get("shortcuts", []) if isinstance(row.get("shortcuts", []), list) else []:
            if not isinstance(shortcut, dict):
                continue
            key = (str(shortcut.get("keys") or "").lower(), str(shortcut.get("scope") or row.get("scope") or ""), str(shortcut.get("when") or "always"))
            if not key[0]:
                continue
            if key in shortcuts:
                finding(errors, "SHORTCUT_CONFLICT", f"快捷键与 {shortcuts[key]} 在同一作用域和条件下冲突", interaction_id or None)
            else:
                shortcuts[key] = interaction_id

        if str(row.get("surface") or "").lower() in HIDDEN_SURFACES:
            required = row.get("required_evidence", [])
            if not isinstance(required, list) or "open" not in required or "closed" not in required:
                finding(warnings if mode == "design" else errors, "HIDDEN_SURFACE_EVIDENCE", "隐藏表面至少需要 open 与 closed 证据", interaction_id or None)
        if mode in {"implementation", "review"} and not row.get("evidence"):
            finding(warnings, "UNVERIFIED_INTERACTION", "尚无已执行的交互证据，不得声称验证通过", interaction_id or None)

    status = "BLOCKED" if errors else "PASS_WITH_WARNINGS" if warnings else "PASS"
    return {
        "schema_version": "1.0.0",
        "status": status,
        "mode": mode,
        "summary": {"interactions": len(interactions), "states": state_count, "transitions": transition_count, "errors": len(errors), "warnings": len(warnings)},
        "errors": errors,
        "warnings": warnings,
        "truncated": len(errors) >= MAX_FINDINGS or len(warnings) >= MAX_FINDINGS,
        "elapsed_ms": round((time.perf_counter() - started) * 1000, 3),
    }


def run(root: Path, contract_path: Path | None, mode: str) -> dict:
    path = contract_path or root / DEFAULT_CONTRACT
    if not path.is_absolute():
        path = root / path
    if not path.is_file():
        return {"schema_version": "1.0.0", "status": "NOT_APPLICABLE", "mode": mode, "contract": str(path), "reason": "当前模块没有交互契约；普通任务不生成全项目配置", "elapsed_ms": 0.0}
    try:
        data = load_contract(path)
        result = evaluate(data, mode)
        result["contract"] = str(path.resolve())
        return result
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        return {"schema_version": "1.0.0", "status": "BLOCKED", "mode": mode, "contract": str(path), "errors": [{"code": "CONTRACT_LOAD_FAILED", "message": str(exc)}], "elapsed_ms": 0.0}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=".")
    parser.add_argument("--contract")
    parser.add_argument("--mode", choices=("design", "implementation", "review"), default="review")
    args = parser.parse_args()
    root = Path(args.root).resolve()
    result = run(root, Path(args.contract) if args.contract else None, args.mode)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 2 if result["status"] == "BLOCKED" else 0


if __name__ == "__main__":
    raise SystemExit(main())
