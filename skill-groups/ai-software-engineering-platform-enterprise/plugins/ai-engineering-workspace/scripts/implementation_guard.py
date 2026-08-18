from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from workspacelib import read_json


ACTIVE_STATUSES = {"active", "transitional"}


def registry_path(root: Path) -> Path:
    return root / ".ai" / "governance" / "implementation-registry.json"


def validate_registry(root: Path, data: dict[str, Any] | None = None) -> dict[str, Any]:
    path = registry_path(root)
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

    all_entrypoints: dict[str, str] = {}
    for capability in capabilities:
        if not isinstance(capability, dict):
            errors.append({"code": "INVALID_CAPABILITY", "message": "能力登记必须是对象"})
            continue
        cap_id = str(capability.get("id") or "UNKNOWN")
        implementations = capability.get("implementations")
        if not isinstance(implementations, list):
            implementations = []
        live = [item for item in implementations if isinstance(item, dict) and str(item.get("status") or "").lower() in ACTIVE_STATUSES]
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

    return {
        "ok": not errors,
        "status": "PASS" if not errors else "BLOCK",
        "registry": path.relative_to(root).as_posix() if path.is_absolute() and root in path.parents else str(path),
        "capability_count": len(capabilities),
        "errors": errors,
        "warnings": warnings,
    }


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
