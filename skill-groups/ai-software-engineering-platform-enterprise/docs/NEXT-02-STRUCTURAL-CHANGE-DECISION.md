# NEXT-02 Structural Change Decision Intelligence

## Status

DISCOVERED

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

## Planned integration

1. Extract the existing observed-fact catalog parser into one shared, bounded validator.
2. Add one pure structural-decision validator beside the current Project Fact Plane contracts.
3. Add the optional section to task_router.py without changing the default route output.
4. Make Architecture Guard consume the normalized decision when present and reject conflicting legacy/new authorities.
5. Keep Implementation Registry, Decision Memory, convergence state and Pro state unchanged.

## Field and governance plan

- Run the eleven required action, fabrication and staleness scenarios.
- Run affected Core, Workspace and Quality regressions.
- Perform read-only decision comparison on at least two real business repositories.
- Do not change business source during decision field verification.
- Implementation field remains NOT_RUN_JUSTIFIED unless the read-only decision field first passes and a safe business slice is separately authorized.
- Default prompt bytes, model calls, Skill loads, state writes, repository scans, agents and workflows must all remain delta zero.

