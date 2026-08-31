# NEXT-01 Perspective Applicability

## Boundary

Perspective Applicability is an optional semantic section of the existing Task Contract. ChatGPT selects project-relevant perspectives from current Artifact, Actor, Usage Condition, Risk and Project Fact evidence. The runtime only validates external observed-fact references, bounded size, known safety-critical coverage and contract shape.

It does not create a Perspective Manager, workflow engine, Agent pool, Skill route, state writer or model call. When omitted, the optional section is absent (semantically `NOT_APPLICABLE`) and the Task Map retains the same bytes, lanes and execution topology as the existing path.

## Existing capability audit

| Surface | Classification | Finding |
|---|---|---|
| UI Skill | `PROMPT_ONLY` | Roles and interaction states existed, but there was no task-local applicability contract. |
| Architecture Skill | `PROMPT_ONLY` | Operations and future-change concerns existed without a dynamic perspective selection record. |
| API/Backend Skill | `PROMPT_ONLY` | Consumers and recovery semantics existed without model-selected caller/operator applicability. |
| Quality Skill | `RUNTIME_ONLY` + `REUSABLE` | Failure recovery and downstream visibility are technical checks, not perspective-selection authority. |
| Workspace Router / Task Contract | `REUSABLE` | Already accepts a model proposal and is the single location for the optional section. |
| Gate Applicability | `REUSABLE` | Already proves the required model-native validation pattern. |
| Capability Registry | `REUSABLE`, unchanged | Remains the one 42-Skill authority; Perspective does not select additional Skills. |
| Duplicate or hardcoded perspective implementation | `MISSING`, not retained | No parallel active implementation or fixed perspective taxonomy was found. |

## Single authority path

```text
ChatGPT semantic proposal
  -> task_router.py (existing Task Contract authority)
     -> externally supplied OBSERVED_FACT_CATALOG / Evidence Receipt
     -> perspective_applicability.py (thin validator)
  -> existing Task Map / Evidence Snapshot
```

The Enhancement Ledger is a release-evidence index only. Project, Goal, Task, Evidence and Decision Memory remain the runtime authorities.

## Invariants

- No keyword-to-perspective mapping.
- No fixed perspective checklist.
- One to eight model-selected perspectives only when the section is applicable.
- Artifact, actor, usage, risk and project fact references must resolve in an external observed-fact catalog bound to the current request fingerprint and, when present, the current Project Fact Plane fingerprint; the Perspective Proposal cannot declare that catalog.
- Each perspective cites a declared artifact and at least one externally observed actor, usage condition, risk or project fact.
- Every known task-bounded safety-critical risk is covered by at least one model-selected perspective, even when the Proposal omits or downgrades it.
- Formal acceptance references must be externally bound; otherwise they remain explicit `SEMANTIC_ACCEPTANCE_LABEL` values and do not masquerade as metric authority.
- The validator never creates an artifact, actor, workflow, lane, Skill, Agent or runtime state.
- Artifact types describe supported inputs; they do not require every project to contain every artifact.

## Governance tax target

- Default prompt bytes: unchanged.
- Default model calls: unchanged.
- Default Skill loads: unchanged.
- New state authorities: zero.
- New managers: zero.

Measured evidence is recorded in `docs/evidence/NEXT-01-governance-tax.json`; the real UI comparison is recorded in `docs/evidence/NEXT-01-ui-field.json` without private paths, screenshots or product data.
