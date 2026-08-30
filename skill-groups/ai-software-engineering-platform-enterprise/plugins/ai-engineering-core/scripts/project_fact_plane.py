from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any, Iterable

from engineering_manifests import DiscoveryBudget, discover_engineering_manifests
from source_identity import context_fresh, identify
from technology_markers import manifest_signals

FACT_CLASSIFICATIONS = {"FACT", "INFERENCE", "PROPOSAL", "DECISION"}
CURRENT_AUTHORITIES = {"AUTHORITATIVE_CURRENT", "PRO_STATE_PLANE", "CURRENT_PROJECT_STATE"}
HISTORICAL_AUTHORITIES = {"IMPORTED_LEGACY", "HISTORICAL", "ARCHIVED"}


def _fact(
    value: Any,
    authority: str,
    fingerprint: str,
    generation: int = 0,
    freshness: str = "CURRENT",
    *,
    classification: str = "FACT",
    source: str = "CURRENT_PROJECT",
    scope: str = "PROJECT",
    confidence: str = "HIGH",
    lifecycle: str = "CURRENT",
) -> dict[str, Any]:
    return {
        "value": value,
        "classification": classification if classification in FACT_CLASSIFICATIONS else "INFERENCE",
        "authority": authority,
        "source": source,
        "source_fingerprint": fingerprint,
        "generation": generation,
        "freshness": freshness,
        "scope": scope,
        "confidence": confidence,
        "lifecycle": lifecycle,
    }


def _root_for_manifest(path: str) -> str:
    parent = Path(path).parent.as_posix()
    if path.endswith("Packages/manifest.json"):
        parent = Path(path).parent.parent.as_posix()
    return "." if parent in {"", "."} else parent


def _append_unique(values: list[str], items: Iterable[str], limit: int = 32) -> None:
    for item in items:
        normalized = str(item).strip().replace("\\", "/").strip("/") or "."
        if normalized not in values:
            values.append(normalized)
        if len(values) >= limit:
            return


def _structured_context(root: Path, identity: dict[str, Any], trusted: bool) -> dict[str, Any]:
    path = root / ".ai" / "context" / "tech-stack.json"
    ready = trusted and (
        context_fresh(path, identity.get("branch") or "", identity.get("head") or "")
        if identity.get("is_git") else path.is_file()
    )
    if not ready:
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8")[:64 * 1024])
    except (OSError, json.JSONDecodeError):
        return {}
    if not isinstance(payload, dict):
        return {}
    allowed: dict[str, Any] = {}
    for key in (
        "architecture", "project_architecture", "framework", "frameworks", "frontend",
        "backend", "client", "database", "runtime", "application_roots", "service_roots",
        "frontend_roots", "backend_roots",
    ):
        if key in payload:
            allowed[key] = payload[key]
    allowed["source"] = str(path)
    allowed["fingerprint"] = hashlib.sha256(json.dumps(allowed, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()
    return allowed


def _tokens(value: Any) -> set[str]:
    if isinstance(value, str):
        return {value.strip().lower()} if value.strip() else set()
    if isinstance(value, list):
        return {str(item).strip().lower() for item in value if str(item).strip()}
    if isinstance(value, dict):
        return {str(key).strip().lower() for key, item in value.items() if item not in (None, False, "")}
    return set()


def _pro_fact(payload: dict[str, Any] | None, name: str) -> dict[str, Any] | None:
    if not isinstance(payload, dict):
        return None
    facts = payload.get("facts") if isinstance(payload.get("facts"), dict) else payload
    value = facts.get(name) if isinstance(facts, dict) else None
    if not isinstance(value, dict) or value.get("value") in (None, ""):
        return None
    authority = str(value.get("authority") or "UNKNOWN").strip().upper()
    historical = authority in HISTORICAL_AUTHORITIES
    classification = str(value.get("classification") or ("DECISION" if name == "project_architecture" else "FACT")).strip().upper()
    if classification not in FACT_CLASSIFICATIONS:
        classification = "INFERENCE"
    generation = value.get("generation", 0)
    generation = generation if isinstance(generation, int) and not isinstance(generation, bool) and generation >= 0 else 0
    freshness = str(value.get("freshness") or ("HISTORICAL" if historical else "CURRENT")).strip().upper()
    lifecycle = str(value.get("lifecycle") or ("ARCHIVED" if historical else "CURRENT")).strip().upper()
    fingerprint = str(value.get("source_fingerprint") or "").strip().lower()
    if not re.fullmatch(r"[a-f0-9]{64}", fingerprint):
        fingerprint = hashlib.sha256(json.dumps({"name": name, "value": value.get("value"), "authority": authority, "generation": generation}, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()
    return _fact(
        value.get("value"), authority, fingerprint, generation, freshness,
        classification=classification,
        source=str(value.get("source") or "PRO_STATE_PLANE")[:80],
        scope=str(value.get("scope") or "PROJECT")[:80],
        confidence=str(value.get("confidence") or ("LOW" if historical else "HIGH")).strip().upper(),
        lifecycle=lifecycle,
    )


def _is_current(fact: dict[str, Any]) -> bool:
    return fact.get("freshness") == "CURRENT" and fact.get("lifecycle") in {"CURRENT", "ACTIVE"}


def _public_fact(fact: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in fact.items() if key not in {"classification", "source", "scope", "confidence"}}


def _architectures_compatible(first: str | None, second: str | None) -> bool:
    if not first or not second or first == second:
        return True
    return {first, second} == {"bs", "backend"}


def _pro_scalar(payload: dict[str, Any] | None, name: str) -> Any:
    if not isinstance(payload, dict):
        return None
    facts = payload.get("facts") if isinstance(payload.get("facts"), dict) else payload
    return facts.get(name) if isinstance(facts, dict) else None


def _architecture(frontend: list[str], backend: list[str], client: list[str], context: dict[str, Any]) -> str | None:
    if client and (frontend or backend):
        return "hybrid"
    if client:
        return "cs"
    if frontend:
        return "bs"
    if backend:
        return "backend"
    context_architecture = str(context.get("project_architecture") or context.get("architecture") or "").strip().lower()
    return context_architecture if context_architecture in {"bs", "cs", "backend", "hybrid"} else None


def build_project_fact_plane(
    root: Path,
    identity: dict[str, Any] | None = None,
    state_consistency: dict[str, Any] | None = None,
    pro_payload: dict[str, Any] | None = None,
    budget: DiscoveryBudget | None = None,
) -> dict[str, Any]:
    root = root.resolve()
    identity = identity or identify(root)
    trusted_state = bool((state_consistency or {}).get("execution_policy", {}).get("trusted_ai_state"))
    context = _structured_context(root, identity, trusted_state)
    pro_roots = _pro_scalar(pro_payload, "verified_topology_roots") or []
    discovery = discover_engineering_manifests(
        root,
        identity.get("trusted_markers") or [],
        pro_roots if isinstance(pro_roots, list) else [],
        identity.get("nested_worktrees") or [],
        budget,
    )
    application_roots: list[str] = []
    service_roots: list[str] = []
    frontend_roots: list[str] = []
    backend_roots: list[str] = []
    client_roots: list[str] = []
    frameworks: list[str] = []
    databases: list[str] = []
    runtimes: list[str] = []
    authorities: set[str] = set()

    for manifest in discovery["manifests"]:
        path = str(manifest["path"])
        content = str(manifest["content"])
        root_name = _root_for_manifest(path)
        authorities.add(str(manifest["authority"]))
        signals = manifest_signals(path, content)
        roles = set(signals["roles"])
        frontend = "frontend" in roles
        backend = "backend" in roles
        client = "client" in roles
        _append_unique(frameworks, signals["frameworks"])
        _append_unique(databases, signals["databases"])
        _append_unique(runtimes, signals["runtimes"])

        if frontend or backend or client:
            _append_unique(application_roots, [root_name])
        if frontend:
            _append_unique(frontend_roots, [root_name])
        if backend:
            _append_unique(backend_roots, [root_name])
            _append_unique(service_roots, [root_name])
        if client:
            _append_unique(client_roots, [root_name])

    context_frontend = _tokens(context.get("frontend"))
    context_backend = _tokens(context.get("backend"))
    context_client = _tokens(context.get("client"))
    _append_unique(frameworks, _tokens(context.get("framework")) | _tokens(context.get("frameworks")))
    _append_unique(databases, _tokens(context.get("database")))
    _append_unique(runtimes, _tokens(context.get("runtime")))
    _append_unique(application_roots, _tokens(context.get("application_roots")))
    _append_unique(service_roots, _tokens(context.get("service_roots")))
    _append_unique(frontend_roots, _tokens(context.get("frontend_roots")))
    _append_unique(backend_roots, _tokens(context.get("backend_roots")))
    if context_frontend and not frontend_roots:
        _append_unique(frontend_roots, ["."])
    if context_backend and not backend_roots:
        _append_unique(backend_roots, ["."])
        _append_unique(service_roots, ["."])
    if context_client and not client_roots:
        _append_unique(client_roots, ["."])

    observed_architecture = _architecture(frontend_roots, backend_roots, client_roots, {})
    context_architecture = str(context.get("project_architecture") or context.get("architecture") or "").strip().lower()
    context_architecture = context_architecture if context_architecture in {"bs", "cs", "backend", "hybrid"} else None
    authority_conflicts: list[dict[str, Any]] = []
    authority_resolutions: list[dict[str, Any]] = []
    local_architecture = observed_architecture or context_architecture
    if observed_architecture and context_architecture:
        if not _architectures_compatible(observed_architecture, context_architecture):
            authority_conflicts.append({
                "fact": "project_architecture", "code": "CURRENT_AUTHORITY_CONFLICT", "severity": "BLOCK",
                "current_value": observed_architecture, "competing_value": context_architecture,
                "current_authority": "CURRENT_WORKSPACE_MANIFEST", "competing_authority": "CURRENT_PROJECT_DECISION",
                "scope": "PROJECT", "resolution": "RECONCILE_BEFORE_EXECUTION",
            })
        elif observed_architecture == "backend" and context_architecture == "bs":
            local_architecture = "bs"
    local_authority = (
        "CURRENT_WORKSPACE_MANIFEST"
        if "CURRENT_WORKSPACE_MANIFEST" in authorities
        else "VERIFIED_DERIVED"
        if discovery["manifests"] or context
        else "CURRENT_RUNTIME_OBSERVATION"
    )
    local_fingerprint = discovery["fingerprint"]
    pro_architecture = _pro_fact(pro_payload, "project_architecture")
    selected_architecture = local_architecture
    architecture_fact = _fact(
        local_architecture, local_authority, local_fingerprint,
        classification="INFERENCE", source="CURRENT_MANIFEST_AND_TRUSTED_CONTEXT",
        confidence="HIGH" if discovery["manifests"] else "MEDIUM",
    ) if local_architecture else _fact(
        None, "UNKNOWN", local_fingerprint, freshness="UNKNOWN",
        classification="INFERENCE", source="BOUNDED_DISCOVERY", confidence="NONE", lifecycle="UNKNOWN",
    )
    if pro_architecture:
        pro_value = str(pro_architecture.get("value") or "").lower()
        pro_current = _is_current(pro_architecture)
        pro_authoritative = pro_architecture.get("authority") in CURRENT_AUTHORITIES and pro_architecture.get("classification") in {"FACT", "DECISION"}
        compatible = _architectures_compatible(pro_value, local_architecture)
        if not pro_current:
            authority_resolutions.append({"fact": "project_architecture", "resolution": "HISTORICAL_IGNORED"})
        elif pro_architecture.get("classification") in {"PROPOSAL", "INFERENCE"} and local_architecture:
            authority_resolutions.append({"fact": "project_architecture", "resolution": "LOWER_AUTHORITY_INFERENCE_IGNORED"})
        elif not pro_authoritative:
            authority_resolutions.append({"fact": "project_architecture", "resolution": "UNKNOWN_AUTHORITY_IGNORED"})
        elif local_architecture and not compatible:
            authority_conflicts.append({
                "fact": "project_architecture", "code": "CURRENT_AUTHORITY_CONFLICT", "severity": "BLOCK",
                "current_value": local_architecture, "competing_value": pro_value,
                "current_authority": local_authority, "competing_authority": pro_architecture.get("authority"),
                "scope": "PROJECT", "resolution": "RECONCILE_BEFORE_EXECUTION",
            })
        elif not local_architecture or compatible:
            selected_architecture = pro_value
            architecture_fact = pro_architecture

    pro_facts = pro_payload.get("facts") if isinstance(pro_payload, dict) and isinstance(pro_payload.get("facts"), dict) else {}
    pro_project_id = pro_facts.get("project_id")
    project_id = pro_project_id or identity.get("repo_id")
    generation = int(pro_facts.get("project_generation") or 0)
    plane_basis = {
        "project_id": project_id,
        "repo_id": identity.get("repo_id"),
        "architecture": selected_architecture,
        "applications": application_roots,
        "services": service_roots,
        "frontend": frontend_roots,
        "backend": backend_roots,
        "client": client_roots,
        "manifest_fingerprint": local_fingerprint,
        "pro_generation": generation,
    }
    plane_fingerprint = hashlib.sha256(json.dumps(plane_basis, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()
    identity_fact = _fact(project_id, "PRO_STATE_PLANE" if pro_project_id else "CURRENT_RUNTIME_OBSERVATION", plane_fingerprint, generation if pro_project_id else 0, source="PRO_STATE_PLANE" if pro_project_id else "SOURCE_IDENTITY")
    topology_fact = _fact(
        {
            "application_roots": application_roots,
            "service_roots": service_roots,
            "frontend_roots": frontend_roots,
            "backend_roots": backend_roots,
            "client_roots": client_roots,
        },
        local_authority,
        local_fingerprint,
        generation,
        classification="INFERENCE",
        source="BOUNDED_MANIFEST_DISCOVERY",
    )

    def activity_scalar(name: str) -> str | None:
        value = pro_facts.get(name)
        return str(value).strip()[:160] if isinstance(value, (str, int)) and str(value).strip() else None

    def activity_list(name: str, limit: int) -> list[str]:
        value = pro_facts.get(name)
        if not isinstance(value, list):
            return []
        return [str(item).strip().replace("\\", "/")[:240] for item in value if str(item).strip()][:limit]

    result = {
        "schema_version": "1.1.0",
        "fact_contract": {
            "defaults": {"classification": "FACT", "scope": "PROJECT", "confidence": "HIGH", "source": ["authority", "source_fingerprint"]},
            "overrides": {
                "project_topology": {"classification": "INFERENCE"},
                "project_architecture": {
                    "classification": architecture_fact.get("classification"),
                    "confidence": architecture_fact.get("confidence"),
                },
            },
        },
        "project_identity": _public_fact(identity_fact),
        "project_topology": _public_fact(topology_fact),
        "project_architecture": _public_fact(architecture_fact),
        "framework_facts": _public_fact(_fact(frameworks, local_authority, local_fingerprint, generation, source="BOUNDED_MANIFEST_DISCOVERY")),
        "database_facts": _public_fact(_fact(databases, local_authority, local_fingerprint, generation, source="BOUNDED_MANIFEST_DISCOVERY")),
        "runtime_facts": _public_fact(_fact(runtimes, local_authority, local_fingerprint, generation, source="BOUNDED_MANIFEST_DISCOVERY")),
        "current_goal": activity_scalar("current_goal"),
        "current_task": activity_scalar("current_task"),
        "current_goal_revision": pro_facts.get("current_goal_revision", 0),
        "current_stage": pro_facts.get("current_stage"),
        "current_changed_scope": activity_list("current_changed_scope", 80),
        "environment_profile": pro_facts.get("environment_profile"),
        "source_fingerprint": plane_fingerprint,
        "context_source_trusted": bool(context),
        "manifest_discovery": {
            "sources": [item["path"] for item in discovery["manifests"]],
            "budget": discovery["budget"],
            "metrics": discovery["metrics"],
        },
        "source_identity": {
            "branch": identity.get("branch"),
            "head": identity.get("head"),
            "repo_id": identity.get("repo_id"),
            "source_conflicts": bool(identity.get("nested_worktrees")),
            "nested_worktree_count": len(identity.get("nested_worktrees") or []),
            "tracked_file_count": identity.get("tracked_file_count"),
        },
    }
    for name in ("current_direct_dependencies", "current_contracts", "current_evidence_refs"):
        normalized = activity_list(name, 16)
        if normalized:
            result[name] = normalized
    authority_status = "CONFLICT" if authority_conflicts else "CURRENT" if selected_architecture else "UNKNOWN"
    if authority_status != "CURRENT":
        result["authority_status"] = authority_status
    if authority_conflicts:
        result["authority_conflicts"] = authority_conflicts
    if authority_resolutions:
        result["authority_resolutions"] = authority_resolutions
    return result
