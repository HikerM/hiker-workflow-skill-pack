---
name: unity-codex-guardrails
description: Apply Hiker guardrails for Unity projects worked through Codex App or Unity MCP. Use when the task mentions Unity, Unity Editor, CoplayDev unity-mcp, MCP tools, scene, prefab, GameObject, script, asset, meta/guid, play mode, console, hierarchy, tests, or avoiding unverified Unity modifications.
---

# Unity Codex Guardrails

version: 0.2.0
owner: Hiker

## Use When

Use before modifying Unity scenes, prefabs, scripts, assets, project settings, or running Unity MCP operations.

## Do Not Use When

Do not use for non-Unity code or generic C# questions unless the answer will modify a Unity project.

## Goal

Prevent silent Unity breakage by inspecting project root, git state, Editor state, console, hierarchy, and target assets before changes, then verify after changes.

## Required Inputs

- Unity project root and target scene/prefab/script/asset.
- Git branch, HEAD, and status.
- Unity Editor/MCP availability if Editor automation is needed.
- Expected behavior or visual result.

## Required Process

1. Confirm project root: `Assets`, `Packages/manifest.json`, and `ProjectSettings`.
2. Check `git status`, branch, and target file ownership.
3. Inspect Unity Editor state if available: open scene, play mode, console errors, hierarchy, selected object.
4. Read target scene/prefab/script/asset and `.meta` relationships before editing.
5. Make the smallest scoped change.
6. Preserve GUIDs, `.meta` files, prefab references, serialized fields, and scene object links.
7. Verify via console, scene hierarchy, tests/play mode/screenshot when relevant.
8. Report exact evidence and remaining manual checks.

## Evidence Rules

- Strong evidence includes Unity console state, compile result, play mode/test result, hierarchy inspection, scene/prefab diff, and relevant screenshots.
- File edits alone are weak evidence for Unity behavior.
- Absence of console access must be stated as a limitation.

## Output Format

```text
Unity 结论：
已检查：
改动：
验证证据：
风险/限制：
下一步：
```

## Hard Rules

- Do not modify scene, prefab, script, asset, or `.meta` before checking project root and git status.
- Do not delete/regenerate `.meta` or GUIDs casually.
- Do not edit scenes/prefabs blindly with text replacement when Unity serialization could break references.
- Do not claim Unity behavior is verified without Editor console/test/play evidence or a stated limitation.

## Failure Modes

- Editing the wrong Unity project root.
- Breaking prefab references through GUID/meta changes.
- Saving a scene while in the wrong play/edit mode.
- Ignoring console compile errors after script changes.

## Example User Inputs

- "用 Codex App 修改 Unity prefab，先做安全检查。"
- "通过 unity-mcp 调整 scene hierarchy。"
- "这个 Unity 线程结果靠谱吗？"

## Example Final Output

```text
Unity 结论：暂不应改 scene，先补检查。
已检查：需要确认项目根目录、git status、Editor 是否打开、当前 scene、console errors、hierarchy。
风险/限制：没有 console 和 hierarchy 证据，不能证明 prefab/script 改动安全。
下一步：先读取 Assets/Packages/ProjectSettings，确认目标 prefab 的 .meta/GUID，再做最小修改。
```
