from __future__ import annotations

from typing import Any


MAX_QUERIES = 128
MAX_INDEXES = 128
MAX_COLUMNS = 16


def _strings(value: Any, limit: int) -> list[str]:
    if not isinstance(value, list):
        return []
    return list(dict.fromkeys(str(item).strip() for item in value if str(item).strip()))[:limit]


def _query_fields(query: dict[str, Any]) -> tuple[set[str], set[str]]:
    filters = query.get("filters", []) if isinstance(query.get("filters"), list) else []
    equality = {
        str(item.get("field")) for item in filters
        if isinstance(item, dict) and item.get("field") and str(item.get("operator") or "").upper() in {"EQ", "IN"}
    }
    range_fields = {
        str(item.get("field")) for item in filters
        if isinstance(item, dict) and item.get("field") and str(item.get("operator") or "").upper() in {"GT", "GTE", "LT", "LTE", "BETWEEN"}
    }
    tenant = str(query.get("tenant_scope") or "").strip()
    joins = {
        str(item.get("field")) for item in query.get("joins", [])
        if isinstance(item, dict) and item.get("field")
    } if isinstance(query.get("joins"), list) else set()
    sorts = {
        str(item.get("field")) for item in query.get("sort", [])
        if isinstance(item, dict) and item.get("field")
    } if isinstance(query.get("sort"), list) else set()
    prefix = equality | joins | ({tenant} if tenant else set())
    return prefix, prefix | range_fields | sorts


def evaluate(payload: Any) -> dict[str, Any]:
    if payload in (None, {}):
        return {
            "status": "NOT_APPLICABLE", "findings": [], "evaluated_indexes": 0,
            "recommendations": [], "rule": "NO_QUERY_EVIDENCE_NO_INDEX_RECOMMENDATION",
        }
    if not isinstance(payload, dict):
        return {"status": "BLOCKED", "findings": [{"code": "QUERY_EVIDENCE_MUST_BE_OBJECT"}], "recommendations": []}
    queries = payload.get("queries", [])
    indexes = payload.get("proposed_indexes", [])
    findings: list[dict[str, str]] = []
    if not isinstance(queries, list) or len(queries) > MAX_QUERIES:
        findings.append({"code": "QUERY_EVIDENCE_BUDGET_OR_TYPE_INVALID"}); queries = []
    if not isinstance(indexes, list) or len(indexes) > MAX_INDEXES:
        findings.append({"code": "INDEX_EVIDENCE_BUDGET_OR_TYPE_INVALID"}); indexes = []
    by_id: dict[str, dict[str, Any]] = {}
    for position, query in enumerate(queries[:MAX_QUERIES]):
        if not isinstance(query, dict) or not str(query.get("query_id") or "").strip():
            findings.append({"code": "INVALID_QUERY_EVIDENCE", "location": f"queries[{position}]"}); continue
        query_id = str(query["query_id"]).strip()
        if query_id in by_id:
            findings.append({"code": "DUPLICATE_QUERY_ID", "location": query_id}); continue
        if not str(query.get("entity") or "").strip() or not _strings(query.get("evidence_refs"), 16):
            findings.append({"code": "QUERY_FACTS_OR_EVIDENCE_MISSING", "location": query_id})
        by_id[query_id] = query
    decisions: list[dict[str, Any]] = []
    for position, index in enumerate(indexes[:MAX_INDEXES]):
        if not isinstance(index, dict):
            findings.append({"code": "INVALID_INDEX_PROPOSAL", "location": f"proposed_indexes[{position}]"}); continue
        index_id = str(index.get("index_id") or f"index-{position}").strip()
        columns = _strings(index.get("columns"), MAX_COLUMNS)
        query_ids = _strings(index.get("query_ids"), MAX_QUERIES)
        entity = str(index.get("entity") or "").strip()
        reasons: list[str] = []
        if not columns:
            reasons.append("INDEX_COLUMNS_MISSING")
        referenced = [by_id[item] for item in query_ids if item in by_id]
        if not query_ids or len(referenced) != len(query_ids):
            reasons.append("BLIND_INDEX_WITHOUT_QUERY_EVIDENCE")
        if referenced and any(str(query.get("entity")) != entity for query in referenced):
            reasons.append("INDEX_QUERY_ENTITY_MISMATCH")
        supported = False
        low_selectivity = False
        for query in referenced:
            prefix, all_fields = _query_fields(query)
            if columns and columns[0] in (prefix or all_fields) and set(columns).issubset(all_fields):
                supported = True
            stats = query.get("field_stats", {}) if isinstance(query.get("field_stats"), dict) else {}
            if len(columns) == 1 and isinstance(stats.get(columns[0]), dict):
                rows = stats[columns[0]].get("rows")
                distinct = stats[columns[0]].get("distinct")
                if isinstance(rows, (int, float)) and rows > 0 and isinstance(distinct, (int, float)):
                    low_selectivity = distinct / rows < 0.01
        if referenced and not supported:
            reasons.append("INDEX_PREFIX_NOT_SUPPORTED_BY_QUERY")
        if low_selectivity and not str(index.get("justification") or "").strip():
            reasons.append("LOW_SELECTIVITY_INDEX_REQUIRES_JUSTIFICATION")
        reads_per_write = [
            query.get("read_write_ratio", {}).get("reads_per_write")
            for query in referenced if isinstance(query.get("read_write_ratio"), dict)
        ]
        if reads_per_write and all(isinstance(value, (int, float)) and value < 1 for value in reads_per_write) and not str(index.get("write_cost_justification") or "").strip():
            reasons.append("WRITE_HEAVY_INDEX_REQUIRES_JUSTIFICATION")
        decision = "BLOCKED" if reasons else "SUPPORTED"
        decisions.append({"index_id": index_id, "decision": decision, "reasons": reasons, "query_ids": query_ids, "columns": columns})
        findings.extend({"code": reason, "location": index_id} for reason in reasons)
    return {
        "status": "BLOCKED" if findings else "PASS",
        "findings": findings,
        "decisions": decisions,
        "evaluated_indexes": len(decisions),
        "recommendations": [],
        "rule": "QUERY_EVIDENCE_REQUIRED; NO_FIELD_NAME_OR_STATUS_SPECIAL_CASE",
    }
