# NEXT-02 Structural Change Decision Intelligence

## Status

FIELD_PROVEN

This enhancement adds an optional, model-selected structural decision to the existing Task Contract. It does not add a workflow, manager, state plane, agent, model call, default Skill load, or background runtime.

## Capability audit

| Existing capability | Classification | Reuse and boundary |
| --- | --- | --- |
| Architecture Decision Challenge | REUSABLE + PROMPT_ONLY | Supplies model reasoning for goals, alternatives, trade-offs and invariants. It never writes or validates runtime state. |
| Full Change Risk Review | REUSABLE + HYBRID | Supplies post-change risk reasoning and reuses risk_review.py, Architecture Guard and bounded verification identity. It does not select a structural action. |
| Long-chain Change Convergence | REUSABLE + HYBRID | Supplies uniqueness, migration exit, retirement evidence and anti-loop rules. It remains a downstream consumer, not a decision authority. |
| Impact / blast radius | REUSABLE + RUNTIME_ONLY | graph_store.py, risk_review.py and Architecture Guard provide bounded, freshness-aware dependency evidence. Stale or truncated graphs cannot prove a decision. |
| Root-cause evidence | REUSABLE + MISSING | Convergence hypotheses can carry falsifiable root-cause evidence, but there is no public standalone structural-action selector. NEXT-02 consumes grounded problem refs and does not create another diagnosis engine. |
| Patch-debt evidence | MISSING | No public authoritative Patch Debt contract exists. NEXT-02 may consume a future evidence ref but must not infer debt from repetition, file size or keywords. |
| Implementation Registry | REUSABLE + RUNTIME_ONLY | implementation_guard.py already validates active routes, shared contracts, canonical writers and migration exits. It remains the authority for implementation-route facts. |
| Decision Memory | REUSABLE + RUNTIME_ONLY | Stores only explicitly locked, scoped decisions. Normal structural evaluation stays task-local and creates no default memory write. |
| Consumer analysis | REUSABLE + HYBRID | Architecture public surfaces, graph impact and Implementation Registry supply consumer evidence. Unknown consumers remain unknown; absence is never inferred from a filename. |
| Project Fact Plane | REUSABLE + RUNTIME_ONLY | Supplies current project identity, source binding, authority conflicts and bounded current scope. |
| Perspective Applicability | REUSABLE + HYBRID | Provides the model-native optional-section pattern and external observed-fact grounding. Its evidence parser must become shared rather than duplicated. |
| Task Contract | REUSABLE | Remains the only task-local authority. The new decision is one optional section, not a parallel task model. |
| Evidence and freshness | REUSABLE | Existing fingerprints, current Project Fact Plane binding and bounded evidence refs are reused. Fabricated, stale or contradictory refs fail closed. |
| Pro Change Intelligence | MISSING public integration contract | Community may consume only the public Pro machine envelope and project facts. Private Pro implementation, commercial logic and internal state are not copied into this repository. |
| Legacy Architecture Guard structural_decisions strings | OVERLAPPING_AUTHORITY + HARDCODED | Existing KEEP/EXTRACT/MIGRATE/RETIRE strings are a compatibility input for file-growth governance. They must normalize into, or yield to, the single NEXT-02 decision authority and may not coexist contradictorily. |

## Decision authority

- Semantic authority: ChatGPT selects exactly one of MODIFY_EXISTING, INTRODUCE_ABSTRACTION, CONSOLIDATE_SIMPLIFY, DELETE_SAFELY, or KEEP_CURRENT_STRUCTURE.
- Runtime role: validate schema, bounded scope, evidence grounding, freshness, consumer and authority facts, action prerequisites, contradictions, risk coverage and rollback/exit evidence.
- Existing authorities remain unchanged: Project Fact Plane owns current project facts; Implementation Registry owns active implementation and writer facts; Decision Memory owns explicitly locked decisions; Task Contract owns the current task decision.
- The runtime never chooses an action from keywords, similarity, file size, declaration count or path names.

## Contract

The optional section contains:

- action
- decision_scope
- problem_refs
- evidence_refs
- reason
- alternatives_rejected
- expected_gain with OBSERVED, INFERRED, or EXPECTED classification
- migration_cost
- regression_risk
- rollback_or_exit_condition
- confidence

All scope and problem refs are externally grounded. Observed gain requires direct evidence. Inferred and expected gain remain explicitly non-observed.

## Deterministic action prerequisites

- MODIFY_EXISTING: current evidence must show a cohesive/local responsibility and must not prove a conflicting shared authority.
- INTRODUCE_ABSTRACTION: requires a proven shared invariant and multiple real consumers; similar text or code is insufficient.
- CONSOLIDATE_SIMPLIFY: requires multiple active implementations under the same responsibility/authority and rejects divergent lifecycles.
- DELETE_SAFELY: requires proven absence of runtime consumers plus completed or non-applicable migration, bounded rollback/exit evidence and no omitted safety-critical fact.
- KEEP_CURRENT_STRUCTURE: accepts a grounded positive decision; large size alone never forces splitting.

## Implemented integration

1. `observed_fact_catalog.py` is the single bounded evidence parser shared by Perspective Applicability and Structural Decision validation.
2. `structural_change_decision.py` validates the model-selected action, while stable contract parsing and tamper-evident receipt validation remain separate small responsibilities.
3. `task_router.py` exposes one optional `structural_change_decision` section. When omitted, the serialized route output is byte-identical to the pre-NEXT-02 baseline.
4. The existing Task Contract writer persists only a validated receipt. Architecture Guard consumes that receipt and rejects a simultaneous legacy `structural_decisions` authority.
5. Implementation Registry, Decision Memory, convergence state, Community/Pro boundary and all existing state planes remain unchanged.

## Authority and execution topology

- Structural semantic authority count: one (`CHATGPT_SEMANTIC_SELECTION`).
- Runtime action-selection count: zero; `runtime_selected_action` is always false.
- Task state writer count: one existing Task Contract writer.
- New state authorities, managers, workflows, agents and model calls: zero.
- Private Pro internals are not inspected, copied or persisted. Community integration remains limited to existing public project facts and CLI envelopes.
- Legacy Architecture Guard strings remain a deprecated compatibility input only. New and legacy decision inputs cannot coexist.

## Verification

- Required A–K action, abstraction, large-cohesive-file, consolidation, deletion, fabrication and staleness scenarios pass.
- Patch-on-patch evidence can drive `CONSOLIDATE_SIMPLIFY` without creating another state machine.
- Perspective and Structural Decision share one external observed-fact catalog and preserve separate model-native semantics.
- Focused structural/Perspective tests: 46 passed after the final patch-on-patch case.
- Final full affected regressions: Core 196, Workspace 173, Quality 116 (`485/485`).
- Schema parsing, Python compilation, diff checks, Architecture Guard, Privacy Guard and five-plugin/42-Skill coherence are release-independent closing gates for this enhancement.

## Real project decision field

- `FIELD-UI-A`: a real Vue/TypeScript project. A growing execution-error projection has one cohesive authority and multiple known consumers. The model selected `MODIFY_EXISTING` and explicitly rejected premature abstraction.
- `FIELD-SERVER-B`: a real multi-service Python backend. Two active readiness modules were byte-identical, changed together, shared the same policy authority and had two proven service consumers. The model selected `CONSOLIDATE_SIMPLIFY` with an explicit compatibility migration and rollback boundary.
- Both projects were dirty before observation. HEAD, status fingerprint and bound source SHA-256 remained unchanged across the field; no business source or `.ai` content was modified.
- Implementation field: `NOT_RUN_JUSTIFIED`. Read-only evidence was sufficient, both working trees had active unrelated work, and no business-source mutation was authorized.

## Governance tax

- Default route serialized output: 7538 bytes before and after, with the same SHA-256.
- Default route median P95: 0.0628 ms before, 0.0629 ms after (`+0.0001 ms`).
- Explicit structural validation median P95: 0.2041 ms.
- Default prompt, model call, Skill load, state write, repository scan, agent, workflow and manager deltas: zero.
- Compact on-demand guidance adds 827 bytes across three existing Skills; at most 654 bytes across any two selected Skills in this change set.

Evidence:

- `docs/evidence/NEXT-02-structural-field.json`
- `docs/evidence/NEXT-02-governance-tax.json`
