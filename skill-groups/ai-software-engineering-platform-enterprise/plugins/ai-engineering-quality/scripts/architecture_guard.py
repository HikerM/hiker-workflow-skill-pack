from __future__ import annotations

import argparse
import hashlib
import json
import re
import sqlite3
import subprocess
from pathlib import Path
from typing import Any

from change_set import collect
from graph_store import impact, import_tokens, resolve_token
from qualitylib import git, git_root, head, load_json, matches_any, now, posix, repo_ai, worktree_fingerprint, write_json


DEFAULT_BUDGET = {
    "preempt_lines": 320, "warn_lines": 400, "block_lines": 700,
    "responsibility_growth": 1, "warn_growth": 80, "block_growth": 200,
}
MAX_HISTORICAL_TEXT_BYTES = 2_000_000
DECLARATION = re.compile(
    r"^\s*(?:export\s+)?(?:default\s+)?(?:abstract\s+)?(?:class|interface|type|enum|function|def|record|struct)\s+[A-Za-z_$][\w$]*"
    r"|^\s*(?:export\s+)?(?:const|let|var)\s+[A-Za-z_$][\w$]*\s*=",
    re.MULTILINE,
)


def safe_id(value: str) -> str:
    return "".join(ch for ch in str(value).upper() if ch.isalnum() or ch in "-._")


def sha256(path: Path) -> str | None:
    if not path.is_file(): return None
    h = hashlib.sha256()
    try:
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""): h.update(chunk)
        return h.hexdigest()
    except OSError: return None


def text_lines(path: Path) -> int | None:
    try:
        if not path.is_file() or path.stat().st_size > 2_000_000: return None
        return len(path.read_text(encoding="utf-8", errors="ignore").splitlines())
    except OSError: return None


def git_lines(root: Path, rel: str, ref: str = "HEAD") -> int:
    return len(git_text(root, rel, ref).splitlines())


def git_text(root: Path, rel: str, ref: str = "HEAD") -> str:
    normalized = posix(rel)
    if normalized == ".ai" or normalized.startswith(".ai/"):
        return ""
    spec = f"{ref}:{normalized}"
    size = git(root, "cat-file", "-s", spec, check=False)
    try:
        if size.returncode != 0 or int(size.stdout.strip()) > MAX_HISTORICAL_TEXT_BYTES:
            return ""
    except ValueError:
        return ""
    result = git(root, "show", spec, check=False)
    return result.stdout if result.returncode == 0 else ""


def declaration_count(text: str) -> int:
    return len(DECLARATION.findall(text))


def structural_decisions(contract: dict[str, Any]) -> tuple[dict[str, dict[str, str]], list[str]]:
    decisions: dict[str, dict[str, str]] = {}; errors: list[str] = []
    for raw in contract.get("structural_decisions", []) or []:
        parts = [part.strip() for part in str(raw).split("|")]
        path = posix(parts[0]) if parts else ""; action = parts[1].upper() if len(parts) > 1 else ""
        if not path or action not in {"KEEP", "EXTRACT", "MIGRATE", "RETIRE"}:
            errors.append(f"结构决策格式无效: {raw}")
            continue
        if action == "KEEP" and (len(parts) < 3 or not parts[2]):
            errors.append(f"KEEP 结构决策缺少职责稳定理由: {path}")
            continue
        if action in {"EXTRACT", "MIGRATE", "RETIRE"} and (len(parts) < 4 or not parts[2] or not parts[3]):
            errors.append(f"{action} 结构决策必须包含目标路径和退出条件/证据: {path}")
            continue
        decisions[path] = {
            "path": path, "action": action, "reason": parts[2] if action == "KEEP" else "",
            "target": parts[2] if action != "KEEP" else "", "exit": parts[3] if len(parts) > 3 else "",
        }
    return decisions, errors


def recent_line_trajectory(root: Path, rel: str, current: int, limit: int = 4) -> list[int]:
    result = git(root, "log", "--format=%H", f"-n{limit}", "--", rel, check=False)
    commits = [line.strip() for line in result.stdout.splitlines() if line.strip()]
    historical = [git_lines(root, rel, commit) for commit in reversed(commits)]
    return historical + [current]


def oscillates(values: list[int]) -> bool:
    signs = []
    for left, right in zip(values, values[1:]):
        delta = right - left
        if delta: signs.append(1 if delta > 0 else -1)
    turns = sum(left != right for left, right in zip(signs, signs[1:]))
    return len(signs) >= 3 and signs[-1] > 0 and turns >= 2


def module_for(path: str, registry: dict[str, Any]) -> str:
    for item in registry.get("modules", []):
        if isinstance(item, dict) and matches_any(path, item.get("paths", [])): return str(item.get("name") or "unknown")
    parts = posix(path).split("/"); return "/".join(parts[:2]) if len(parts) > 1 else parts[0]


def allowed(path: str, module: str, contract: dict[str, Any]) -> bool:
    files = contract.get("allowed_files", []); modules = contract.get("allowed_modules", [])
    return bool((files and matches_any(path, files)) or module in modules)


def graph_nodes(db: Path) -> set[str]:
    if not db.is_file(): return set()
    try:
        with sqlite3.connect(db) as connection: return {str(row[0]) for row in connection.execute("SELECT path FROM nodes")}
    except sqlite3.Error: return set()


def dependency_violations(root: Path, changed: list[dict], registry: dict, dependency: dict, db: Path) -> list[dict]:
    rules = dependency.get("rules", []); paths = graph_nodes(db); violations = []
    if not rules or not paths: return violations
    for change in changed:
        rel = change["path"]; source = root / rel
        if not source.is_file(): continue
        source_module = module_for(rel, registry); language = source.suffix.lower().lstrip(".")
        language = {"ts":"typescript","tsx":"typescript","js":"javascript","jsx":"javascript","py":"python","cs":"csharp","kt":"kotlin"}.get(language, language)
        for token in import_tokens(source, language):
            target = resolve_token(rel, token, paths)
            if not target: continue
            target_module = module_for(target, registry)
            for rule in rules:
                if rule.get("from") != source_module: continue
                deny = rule.get("deny", []); allow_only = rule.get("allow_only", [])
                if target_module in deny or allow_only and target_module not in allow_only and target_module != source_module:
                    violations.append({"path": rel, "module": source_module, "depends_on": target, "target_module": target_module})
    return violations


def evaluate(root: Path, task_id: str | None = None, mode: str = "all-local", base: str | None = None, target: str | None = None, files: list[str] | None = None) -> dict:
    root = git_root(root); ai = repo_ai(root); governed = (ai / "governance" / "project-state.json").is_file(); task_key = safe_id(task_id or "")
    task = load_json(ai / "tasks" / f"{task_key}.json", {}) if task_key else {}; contract = task.get("change_contract", {}) if isinstance(task, dict) else {}
    registry = load_json(ai / "architecture" / "module-registry.json", {}) or {}; dependency = load_json(ai / "architecture" / "dependency-rules.json", {}) or {}; public = load_json(ai / "architecture" / "public-surface.json", {}) or {}
    collected = collect(root, mode, base, target, files); changes = [item for item in collected.get("files", []) if not item["path"].startswith(".ai/") and item["path"] not in {"PROJECT_STATE.md", "CURRENT_CONTEXT.md"}]; effective_mode = mode; baseline_ref = "HEAD"
    if not changes and task and mode == "all-local" and task.get("base_branch") and task.get("branch"):
        ranged = collect(root, "range", str(task["base_branch"]), str(task["branch"]), None)
        if ranged.get("files"):
            collected = ranged; changes = [item for item in ranged["files"] if not item["path"].startswith(".ai/") and item["path"] not in {"PROJECT_STATE.md", "CURRENT_CONTEXT.md"}]; effective_mode = "task-range"; baseline_ref = str(task["base_branch"])
    elif mode == "range" and base:
        baseline_ref = base
    findings = []; blockers = []; warnings = []
    if governed and changes and not task_key: blockers.append("受治理项目的变更检查必须指定 Task ID")
    if task_key and not task: blockers.append(f"找不到任务状态: {task_key}")
    if task and not contract: blockers.append("任务缺少 change_contract")
    if contract and not contract.get("allowed_files") and not contract.get("allowed_modules"): blockers.append("change_contract 未声明允许修改的文件或模块")

    changed_modules = []; drift = []
    for item in changes:
        module = module_for(item["path"], registry); changed_modules.append(module)
        if contract and not allowed(item["path"], module, contract): drift.append({"path": item["path"], "module": module})
        if module in contract.get("protected_modules", []): blockers.append(f"修改了受保护模块: {module} ({item['path']})")
    if drift: blockers.append(f"实际改动超出 change_contract: {len(drift)} 个文件")

    budget = dict(DEFAULT_BUDGET); budget.update((contract.get("file_growth_budget") or {}) if isinstance(contract, dict) else {})
    decisions, decision_errors = structural_decisions(contract)
    blockers.extend(decision_errors)
    growth = []
    responsibility_risks = []
    history_budget = 12
    for item in changes:
        if item.get("binary"):
            growth.append({"path": item["path"], "before": None, "after": None, "growth": None, "skipped": "binary"})
            continue
        rel = item["path"]; old_rel = item.get("old_path") or rel
        current = text_lines(root / rel); previous = git_lines(root, old_rel, baseline_ref); delta = None if current is None else current - previous
        current_text = (root / rel).read_text(encoding="utf-8", errors="ignore") if current is not None and (root / rel).is_file() else ""
        previous_text = git_text(root, old_rel, baseline_ref)
        responsibility_delta = declaration_count(current_text) - declaration_count(previous_text)
        row = {"path": rel, "before": previous, "after": current, "growth": delta, "responsibility_delta": responsibility_delta}; growth.append(row)
        if current is not None and current >= int(budget["block_lines"]): blockers.append(f"文件超过阻断预算 {budget['block_lines']} 行: {item['path']} ({current})")
        elif current is not None and current >= int(budget["warn_lines"]): warnings.append(f"文件超过警告预算 {budget['warn_lines']} 行: {item['path']} ({current})")
        if delta is not None and delta >= int(budget["block_growth"]): blockers.append(f"单次增长超过阻断预算 {budget['block_growth']} 行: {item['path']} (+{delta})")
        elif delta is not None and delta >= int(budget["warn_growth"]): warnings.append(f"单次增长超过警告预算 {budget['warn_growth']} 行: {item['path']} (+{delta})")
        near_budget = current is not None and max(previous, current) >= int(budget["preempt_lines"])
        adds_responsibility = responsibility_delta >= int(budget["responsibility_growth"])
        decision = decisions.get(rel)
        trajectory: list[int] = []
        repeated_cycle = False
        if near_budget and history_budget > 0:
            trajectory = recent_line_trajectory(root, rel, current)
            repeated_cycle = oscillates(trajectory)
            history_budget -= 1
        if near_budget and adds_responsibility and not decision:
            blockers.append(f"接近文件预算时新增职责但缺少编码前结构决策: {rel}（新增声明 {responsibility_delta}）")
        if repeated_cycle and (not decision or decision.get("action") not in {"EXTRACT", "MIGRATE", "RETIRE"}):
            blockers.append(f"检测到文件反复增长—拆分—再写回: {rel}；必须给出带退出条件的提取、迁移或退役决策")
        if near_budget or repeated_cycle:
            responsibility_risks.append({
                "path": rel, "near_budget": near_budget, "responsibility_delta": responsibility_delta,
                "trajectory": trajectory, "oscillation": repeated_cycle, "decision": decision,
            })

    public_changes = []
    declared = set(contract.get("public_contract_changes", [])); characterization = contract.get("characterization_tests", []); consumer_tests = contract.get("consumer_tests", [])
    for surface in public.get("surfaces", []):
        if not isinstance(surface, dict) or not surface.get("path"): continue
        rel = str(surface["path"]); current = sha256(root / rel); baseline = surface.get("sha256")
        if current != baseline and any(x.get("path") == rel for x in changes):
            entry = {"path": rel, "baseline": baseline, "current": current, "consumers": surface.get("consumers", []), "tests": surface.get("tests", [])}; public_changes.append(entry)
            if rel not in declared: blockers.append(f"公共契约变化未在 change_contract 声明: {rel}")
            if not entry["consumers"]: blockers.append(f"公共契约缺少消费者登记: {rel}")
            if not characterization or not consumer_tests: blockers.append(f"公共契约变化缺少特征测试或消费者回归: {rel}")

    registered_paths = {str(item.get("path")) for item in public.get("surfaces", []) if isinstance(item, dict)}
    potential_public = [item["path"] for item in changes if item["path"] not in registered_paths and any(token in f"/{item['path'].lower()}" for token in ("/shared/", "/common/", "/core/", "/base/", "/contracts/", "/api/", "coreservice", "publicservice"))]
    if potential_public:
        warnings.append(f"自动识别到 {len(potential_public)} 个可能的公共或高复用表面")
        if not contract.get("consumers"): blockers.append("可能的公共表面变化缺少消费者声明")
        if not characterization or not consumer_tests: blockers.append("可能的公共表面变化缺少特征测试或消费者回归")

    db = ai / "knowledge" / "engineering.db"; graph = None
    if db.is_file() and changes:
        graph = impact(db, [x["path"] for x in changes], 3, max(1, int(contract.get("max_blast_radius", 80) or 80) + 1), "both", head(root), worktree_fingerprint(root))
        maximum = int(contract.get("max_blast_radius", 80) or 80)
        if graph.get("stale"): blockers.append("工程图谱已过期，不能证明影响范围")
        if graph.get("truncated") or len(graph.get("nodes", [])) > maximum: blockers.append(f"影响半径超过任务上限 {maximum}")
    elif changes and (public_changes or potential_public or any("shared" in str(x).lower() or "common" in str(x).lower() or "core" in str(x).lower() for x in changed_modules)):
        blockers.append("共享或公共变更缺少可用工程图谱")

    dep_violations = dependency_violations(root, changes, registry, dependency, db)
    if dep_violations: blockers.append(f"模块依赖规则违规: {len(dep_violations)} 处")
    if changes and contract and not contract.get("behavior_invariants"): blockers.append("change_contract 缺少原有行为不变量")
    if changes and contract and not contract.get("required_tests"): blockers.append("change_contract 缺少最低回归测试")
    result = "BLOCKED" if blockers else "PASS_WITH_WARNINGS" if warnings else "PASS"
    return {
        "schema_version": "1.0.0", "generated_at": now(), "result": result, "project_id": task.get("project_id") if task else None, "task_id": task_key or None,
        "head": head(root), "worktree_fingerprint": worktree_fingerprint(root), "change_mode": effective_mode, "baseline_ref": baseline_ref, "changes": changes,
        "changed_modules": sorted(set(changed_modules)), "scope_drift": drift, "file_growth": growth, "file_growth_budget": budget,
        "public_contract_changes": public_changes, "potential_public_changes": potential_public, "dependency_violations": dep_violations, "graph": graph,
        "structural_decisions": list(decisions.values()), "responsibility_risks": responsibility_risks,
        "blockers": list(dict.fromkeys(blockers)), "warnings": list(dict.fromkeys(warnings)), "findings": findings,
    }


def initialize(root: Path) -> dict:
    root = git_root(root); folder = repo_ai(root) / "architecture"; folder.mkdir(parents=True, exist_ok=True)
    files = {
        "module-registry.json": {"schema_version":"1.0.0","mode":"auto-discovery","modules":[],"note":"只补充受保护或边界敏感模块。"},
        "dependency-rules.json": {"schema_version":"1.0.0","mode":"advisory-until-configured","rules":[],"note":"无显式规则时保持自动分析，不阻塞普通改动。"},
        "public-surface.json": {"schema_version":"1.0.0","surfaces":[],"note":"只登记跨模块公共契约。"},
        "runtime-topology.json": {"schema_version":"1.0.0","nodes":[],"edges":[],"note":"只补充源码无法推断的运行时关系。"},
    }
    created = []
    for name, data in files.items():
        path = folder / name
        if not path.exists(): write_json(path, data); created.append(str(path))
    return {"ok": True, "created": created, "folder": str(folder)}


def register_module(root: Path, name: str, paths: list[str], owner: str | None) -> dict:
    root = git_root(root); initialize(root); path = repo_ai(root) / "architecture" / "module-registry.json"
    data = load_json(path, {}) or {}; modules = [item for item in data.get("modules", []) if item.get("name") != name]
    modules.append({"name": name, "paths": list(dict.fromkeys(paths)), "owner": owner, "protected": False})
    data["modules"] = sorted(modules, key=lambda item: str(item.get("name"))); write_json(path, data)
    return {"ok": True, "module": name, "paths": paths, "output": str(path)}


def set_dependency_rule(root: Path, source: str, allow_only: list[str], deny: list[str]) -> dict:
    root = git_root(root); initialize(root); path = repo_ai(root) / "architecture" / "dependency-rules.json"
    data = load_json(path, {}) or {}; rules = [item for item in data.get("rules", []) if item.get("from") != source]
    rules.append({"from": source, "allow_only": list(dict.fromkeys(allow_only)), "deny": list(dict.fromkeys(deny))})
    data["rules"] = sorted(rules, key=lambda item: str(item.get("from"))); write_json(path, data)
    return {"ok": True, "from": source, "output": str(path)}


def register_surface(root: Path, rel: str, consumers: list[str], tests: list[str]) -> dict:
    root = git_root(root); initialize(root); source = root / rel
    if not source.is_file(): raise RuntimeError(f"public surface does not exist: {rel}")
    path = repo_ai(root) / "architecture" / "public-surface.json"; data = load_json(path, {}) or {}
    surfaces = [item for item in data.get("surfaces", []) if item.get("path") != posix(rel)]
    surfaces.append({"path": posix(rel), "sha256": sha256(source), "consumers": list(dict.fromkeys(consumers)), "tests": list(dict.fromkeys(tests))})
    data["surfaces"] = sorted(surfaces, key=lambda item: str(item.get("path"))); write_json(path, data)
    return {"ok": True, "path": posix(rel), "output": str(path)}


def main() -> int:
    ap = argparse.ArgumentParser(); ap.add_argument("--root", default="."); sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("init")
    check = sub.add_parser("check"); check.add_argument("--task-id"); check.add_argument("--mode", choices=["all-local","staged","working-tree","range"], default="all-local"); check.add_argument("--base"); check.add_argument("--target")
    module = sub.add_parser("module-register"); module.add_argument("--name", required=True); module.add_argument("--path", action="append", required=True); module.add_argument("--owner")
    dependency = sub.add_parser("dependency-set"); dependency.add_argument("--from-module", required=True); dependency.add_argument("--allow-only", nargs="*", default=[]); dependency.add_argument("--deny", nargs="*", default=[])
    surface = sub.add_parser("surface-register"); surface.add_argument("--path", required=True); surface.add_argument("--consumer", action="append", default=[]); surface.add_argument("--test", action="append", default=[])
    args = ap.parse_args(); root = Path(args.root).resolve()
    if args.cmd == "init": data = initialize(root)
    elif args.cmd == "module-register": data = register_module(root, args.name, args.path, args.owner)
    elif args.cmd == "dependency-set": data = set_dependency_rule(root, args.from_module, args.allow_only, args.deny)
    elif args.cmd == "surface-register": data = register_surface(root, args.path, args.consumer, args.test)
    else:
        data = evaluate(root, args.task_id, args.mode, args.base, args.target)
        out = repo_ai(git_root(root)) / "evidence" / "architecture-guard" / f"{safe_id(args.task_id or 'unscoped')}.json"; write_json(out, data); data["output"] = str(out)
    print(json.dumps(data, ensure_ascii=False, indent=2)); return 0 if data.get("result", "PASS") in {"PASS","PASS_WITH_WARNINGS"} else 2


if __name__ == "__main__": raise SystemExit(main())
