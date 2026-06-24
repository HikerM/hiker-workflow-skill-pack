# Safety Rules

## Write Safety

- DryRun is the default for install and uninstall.
- `-Apply` is required for writes.
- Existing skills are skipped unless `-Force` is set.
- `AGENTS.md` should be merged with `-MergeAgents`; avoid overwrite.

## Engineering Safety

- Do not default to DB writes, production data mutation, real provider calls, billing actions, service restarts, deployments, push, merge, force push, or history rewrites.
- Do not treat a single commit as completion.
- Do not claim behavior is verified without command output, logs, responses, screenshots, DB/queue/provider/billing state, or explicit limitation.

## Unity Safety

- Confirm `Assets`, `Packages/manifest.json`, and `ProjectSettings`.
- Check git status and Unity Editor state before changes.
- Preserve `.meta`, GUIDs, prefab references, serialized fields, and scene links.
- Verify console or tests after changes.

## NodeTs Safety

- Keep quote -> create -> result as the canonical flow.
- Keep provider-specific data behind adapters and normalization.
- Keep frontend dependent on canonical API responses.
- Verify billing reservation, settlement, and release separately.

## Design Safety

- Preserve original text, page order, card order, aspect ratio, and file count.
- Generate actual output files and check representative outputs.
- Do not fabricate download links or paths.
