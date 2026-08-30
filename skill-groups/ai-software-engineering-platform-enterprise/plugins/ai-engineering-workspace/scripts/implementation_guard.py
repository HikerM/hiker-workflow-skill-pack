from __future__ import annotations

import argparse
import json
from itertools import combinations
from pathlib import Path
from typing import Any

from workspacelib import RESOURCE_HARD_MAX, read_json


ACTIVE_STATUSES = {"active", "transitional"}
PROPOSAL_ACTIONS = {"MODIFY_EXISTING", "ADD_PARALLEL_IMPLEMENTATION", "MIGRATE"}
LIMITS = RESOURCE_HARD_MAX["implementation_registry"]


def registry_path(root: Path) -> Path:
    return root / ".ai" / "governance" / "implementation-registry.json"


def _text_set(item: dict[str, Any], *keys: str) -> set[str]:
    values: list[Any] = []
    for key in keys:
        raw = item.get(key)
        if isinstance(raw, list):
            values.extend(raw)
        elif raw:
            values.append(raw)
    return {str(value).strip() for value in values[:LIMITS["max_boundary_values"]] if str(value).strip()}


def _route(capability: dict[str, Any], item: dict[str, Any], index: int) -> dict[str, Any]:
    usage = item.get("active_usage")
    if isinstance(usage, dict):
        usage_active = str(usage.get("status") or "").lower() in {"active", "observed", "confirmed"}
        usage_evidence = _text_set(usage, "evidence", "references")
    elif isinstance(usage, bool):
        usage_active = usage
        usage_evidence = set()
    else:
        usage_active = str(item.get("status") or "").lower() in ACTIVE_STATUSES
        usage_evidence = set()
    return {
        "route_id": str(item.get("id") or item.get("route_id") or item.get("path") or f"route-{index}"),
        "path": str(item.get("path") or ""),
        "capability_id": str(capability.get("id") or "UNKNOWN"),
        "responsibility": str(item.get("responsibility") or capability.get("responsibility") or capability.get("id") or "").strip(),
        "call_paths": _text_set(item, "call_paths", "entrypoints"),
        "write_authorities": _text_set(item, "write_authorities", "write_authority"),
        "contracts": _text_set(item, "contracts", "contract_ids"),
        "active_usage": usage_active,
        "usage_evidence": usage_evidence,
        "writes_canonical_state": item.get("writes_canonical_state") is True,
        "status": str(item.get("status") or "").lower(),
    }


def _shared_boundaries(left: dict[str, Any], right: dict[str, Any]) -> dict[str, list[str]]:
    return {
        "call_paths": sorted(left["call_paths"] & right["call_paths"]),
        "write_authorities": sorted(left["write_authorities"] & right["write_authorities"]),
        "contracts": sorted(left["contracts"] & right["contracts"]),
    }


def _fingerprint(value: Any) -> bool:
    text = str(value or "").lower()
    return len(text) == 64 and all(ch in "0123456789abcdef" for ch in text)


def _evidence_complete(proposal: dict[str, Any], route: dict[str, Any]) -> bool:
    evidence = proposal.get("evidence")
    if not isinstance(evidence, dict):
        return False
    impact = evidence.get("impact")
    architecture = evidence.get("architecture")
    if not _fingerprint(evidence.get("change_contract_fingerprint")):
        return False
    if not isinstance(impact, dict) or not _fingerprint(impact.get("fingerprint")):
        return False
    if not isinstance(architecture, dict) or not _fingerprint(architecture.get("fingerprint")):
        return False
    responsibilities = _text_set(impact, "responsibilities") | _text_set(architecture, "responsibilities")
    if route["responsibility"] not in responsibilities:
        return False
    available = {
        "call_paths": _text_set(impact, "call_paths") | _text_set(architecture, "call_paths"),
        "write_authorities": _text_set(impact, "write_authorities") | _text_set(architecture, "write_authorities"),
        "contracts": _text_set(impact, "contracts") | _text_set(architecture, "contracts"),
    }
    if not any(route[key] for key in available):
        return False
    return all(route[key] <= available[key] for key in available)


def assess_proposal(active_routes: list[dict[str, Any]], proposal: dict[str, Any]) -> dict[str, Any]:
    """Validate a model proposal without inferring responsibility from a filename."""
    action = str(proposal.get("action") or "").upper()
    if action not in PROPOSAL_ACTIONS:
        return {"ok": False, "status": "REQUIRES_REVIEW", "code": "INVALID_PROPOSAL_ACTION", "conflicts": []}
    raw_route = proposal.get("route")
    if not isinstance(raw_route, dict):
        return {"ok": False, "status": "REQUIRES_REVIEW", "code": "ROUTE_EVIDENCE_REQUIRED", "conflicts": []}
    route = _route({"id": "PROPOSAL", "responsibility": raw_route.get("responsibility")}, raw_route, 0)
    existing_ids = {str(item.get("route_id") or "") for item in active_routes}

    if action == "MODIFY_EXISTING":
        target = str(proposal.get("existing_route_id") or route.get("route_id") or "")
        if target not in existing_ids:
            return {"ok": False, "status": "REQUIRES_REVIEW", "code": "EXISTING_ROUTE_NOT_PROVEN", "conflicts": []}
        return {
            "ok": True, "status": "PASS", "decision": "MODIFY_EXISTING", "conflicts": [],
            "filename_semantics_used": False,
        }

    if not route["responsibility"] or not _evidence_complete(proposal, route):
        return {
            "ok": False, "status": "REQUIRES_REVIEW", "code": "BOUNDARY_EVIDENCE_REQUIRED",
            "conflicts": [], "filename_semantics_used": False,
        }

    conflicts = []
    unresolved = []
    for existing in active_routes:
        if not existing.get("active_usage") or existing.get("responsibility") != route["responsibility"]:
            continue
        shared = _shared_boundaries(existing, route)
        if any(shared.values()):
            conflicts.append({"existing_route_id": existing.get("route_id"), "shared": shared})
        elif not (existing.get("call_paths") or existing.get("write_authorities") or existing.get("contracts")):
            unresolved.append(str(existing.get("route_id") or "UNKNOWN"))

    if action == "ADD_PARALLEL_IMPLEMENTATION":
        if conflicts:
            return {
                "ok": False, "status": "BLOCK", "code": "COMPETING_IMPLEMENTATION_PATH",
                "decision": "MODIFY_EXISTING", "conflicts": conflicts, "filename_semantics_used": False,
            }
        if unresolved:
            return {
                "ok": False, "status": "REQUIRES_REVIEW", "code": "ACTIVE_PATH_BOUNDARY_UNKNOWN",
                "conflicts": [], "unresolved_routes": unresolved, "filename_semantics_used": False,
            }
        return {
            "ok": True, "status": "PASS", "decision": "ADD_INDEPENDENT_IMPLEMENTATION",
            "conflicts": [], "filename_semantics_used": False,
        }

    migration = proposal.get("migration")
    if not isinstance(migration, dict):
        return {"ok": False, "status": "REQUIRES_REVIEW", "code": "MIGRATION_WINDOW_REQUIRED", "conflicts": conflicts}
    source = str(migration.get("source_route_id") or "")
    exits = migration.get("exit_conditions")
    canonical_writer = str(migration.get("canonical_writer_route_id") or "")
    if source not in existing_ids or not isinstance(exits, list) or not exits or canonical_writer not in {source, route["route_id"]}:
        return {"ok": False, "status": "REQUIRES_REVIEW", "code": "MIGRATION_EXIT_OR_AUTHORITY_REQUIRED", "conflicts": conflicts}
    writer_ids = {str(item.get("route_id")) for item in active_routes if item.get("writes_canonical_state")}
    if route["writes_canonical_state"]:
        writer_ids.add(route["route_id"])
    if writer_ids - {canonical_writer}:
        return {
            "ok": False, "status": "BLOCK", "code": "MULTIPLE_CANONICAL_WRITERS",
            "conflicts": conflicts, "writer_routes": sorted(writer_ids), "filename_semantics_used": False,
        }
    return {
        "ok": True, "status": "PASS", "decision": "BOUNDED_MIGRATION",
        "conflicts": conflicts, "exit_conditions": list(dict.fromkeys(str(value) for value in exits)),
        "filename_semantics_used": False,
    }


def validate_registry(root: Path, data: dict[str, Any] | None = None) -> dict[str, Any]:
    path = registry_path(root)
    if data is None and path.is_file() and path.stat().st_size > LIMITS["max_file_bytes"]:
        return {
            "ok": False, "status": "BLOCK", "registry": str(path),
            "errors": [{"code": "REGISTRY_FILE_BUDGET_EXCEEDED", "message": "实现登记超过有界输入预算"}],
            "warnings": [], "bounded_evaluation": {"limits": LIMITS, "comparisons": 0},
        }
    registry = data if data is not None else read_json(path, None)
    if not isinstance(registry, dict):
        return {
            "ok": True,
            "status": "NOT_APPLICABLE",
            "reason": "implementation-registry-missing",
            "errors": [],
            "warnings": [],
        }

    errors: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    capabilities = registry.get("capabilities")
    if not isinstance(capabilities, list):
        capabilities = []
        errors.append({"code": "INVALID_REGISTRY", "message": "capabilities必须是数组"})
    elif len(capabilities) > LIMITS["max_capabilities"]:
        errors.append({"code": "CAPABILITY_BUDGET_EXCEEDED", "message": "实现登记能力数量超过确定性上限"})
        capabilities = capabilities[:LIMITS["max_capabilities"]]

    all_entrypoints: dict[str, str] = {}
    active_routes: list[dict[str, Any]] = []
    implementation_count = 0
    for capability in capabilities:
        if not isinstance(capability, dict):
            errors.append({"code": "INVALID_CAPABILITY", "message": "能力登记必须是对象"})
            continue
        cap_id = str(capability.get("id") or "UNKNOWN")
        implementations = capability.get("implementations")
        if not isinstance(implementations, list):
            implementations = []
        remaining = LIMITS["max_implementations"] - implementation_count
        if len(implementations) > max(0, remaining):
            errors.append({"code": "IMPLEMENTATION_BUDGET_EXCEEDED", "capability": cap_id, "message": "活动实现登记超过确定性上限"})
            implementations = implementations[:max(0, remaining)]
        implementation_count += len(implementations)
        live = [item for item in implementations if isinstance(item, dict) and str(item.get("status") or "").lower() in ACTIVE_STATUSES]
        active_routes.extend(_route(capability, item, index) for index, item in enumerate(live, 1))
        authoritative = [item for item in live if item.get("authoritative") is True]
        writers = [item for item in live if item.get("writes_canonical_state") is True]

        if len(authoritative) != 1:
            errors.append({
                "code": "AUTHORITATIVE_IMPLEMENTATION_COUNT",
                "capability": cap_id,
                "message": "每个能力必须且只能有一个权威活动实现",
            })
        if len(writers) > 1:
            errors.append({
                "code": "MULTIPLE_CANONICAL_WRITERS",
                "capability": cap_id,
                "message": "同一能力存在多个活动写入者",
            })
        if len(live) > 1:
            migration = capability.get("migration") if isinstance(capability.get("migration"), dict) else {}
            exit_conditions = migration.get("exit_conditions") if isinstance(migration, dict) else None
            target = migration.get("target") if isinstance(migration, dict) else None
            if not target or not isinstance(exit_conditions, list) or not exit_conditions:
                errors.append({
                    "code": "COEXISTENCE_WITHOUT_EXIT",
                    "capability": cap_id,
                    "message": "新旧实现并存必须声明目标实现和退出条件",
                })

        for item in implementations:
            if not isinstance(item, dict):
                continue
            status = str(item.get("status") or "").lower()
            if status == "deprecated" and item.get("writes_canonical_state") is True:
                errors.append({
                    "code": "DEPRECATED_WRITER",
                    "capability": cap_id,
                    "path": item.get("path"),
                    "message": "废弃实现不得继续写入权威状态",
                })
            if status == "deprecated" and item.get("accepts_new_work") is True:
                errors.append({
                    "code": "DEPRECATED_ACCEPTS_NEW_WORK",
                    "capability": cap_id,
                    "path": item.get("path"),
                    "message": "废弃实现不得承载新增需求",
                })
            if status not in ACTIVE_STATUSES:
                continue
            for entrypoint in item.get("entrypoints", []) if isinstance(item.get("entrypoints"), list) else []:
                key = str(entrypoint).strip()
                if not key:
                    continue
                owner = all_entrypoints.get(key)
                if owner and owner != cap_id:
                    errors.append({
                        "code": "DUPLICATE_ACTIVE_ENTRYPOINT",
                        "capability": cap_id,
                        "entrypoint": key,
                        "other_capability": owner,
                        "message": "活动入口被多个能力声明",
                    })
                else:
                    all_entrypoints[key] = cap_id

        if not implementations:
            warnings.append({"code": "NO_IMPLEMENTATION", "capability": cap_id, "message": "能力尚未登记实现证据"})

    comparison_count = 0
    for left, right in combinations(active_routes, 2):
        if comparison_count >= LIMITS["max_comparisons"]:
            errors.append({"code": "COMPARISON_BUDGET_EXCEEDED", "message": "实现路径比较超过确定性上限"})
            break
        comparison_count += 1
        if left["capability_id"] == right["capability_id"] or left["responsibility"] != right["responsibility"]:
            continue
        shared = _shared_boundaries(left, right)
        if left["active_usage"] and right["active_usage"] and any(shared.values()):
            errors.append({
                "code": "COMPETING_IMPLEMENTATION_PATH",
                "responsibility": left["responsibility"],
                "routes": [left["route_id"], right["route_id"]],
                "shared": shared,
                "message": "不同登记分组仍共享职责与活动边界，必须收敛为唯一活动路径",
            })

    proposal_assessment = None
    if isinstance(registry.get("proposal"), dict):
        proposal_assessment = assess_proposal(active_routes, registry["proposal"])
        if proposal_assessment["status"] == "BLOCK":
            errors.append({
                "code": proposal_assessment.get("code"),
                "message": "新增并行实现与现有活动路径竞争；优先修改现有实现",
                "conflicts": proposal_assessment.get("conflicts", []),
            })
        elif proposal_assessment["status"] == "REQUIRES_REVIEW":
            warnings.append({
                "code": proposal_assessment.get("code"),
                "message": "实现路径边界证据不足，运行时不会根据文件名猜测",
            })

    requires_review = bool(proposal_assessment and proposal_assessment.get("status") == "REQUIRES_REVIEW")
    return {
        "ok": not errors and not requires_review,
        "status": "BLOCK" if errors else "REQUIRES_REVIEW" if requires_review else "PASS",
        "registry": path.relative_to(root).as_posix() if path.is_absolute() and root in path.parents else str(path),
        "capability_count": len(capabilities),
        "errors": errors,
        "warnings": warnings,
        "proposal_assessment": proposal_assessment,
        "decision_basis": ["responsibility", "call_paths", "write_authorities", "contracts", "active_usage"],
        "filename_semantics_used": False,
        "bounded_evaluation": {
            "limits": LIMITS,
            "capabilities": len(capabilities),
            "implementations": implementation_count,
            "active_routes": len(active_routes),
            "comparisons": comparison_count,
        },
    }


def enforce_registry(root: Path) -> dict[str, Any]:
    report = validate_registry(root)
    if report.get("status") != "NOT_APPLICABLE" and not report.get("ok"):
        codes = [str(item.get("code")) for item in report.get("errors", []) + report.get("warnings", [])]
        raise RuntimeError("implementation registry blocks task progression: " + "; ".join(codes))
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="检查一个业务能力是否只有一个权威活动实现")
    parser.add_argument("--root", default=".")
    parser.add_argument("--registry")
    args = parser.parse_args()
    root = Path(args.root).resolve()
    data = read_json(Path(args.registry).resolve(), None) if args.registry else None
    result = validate_registry(root, data)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["ok"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
