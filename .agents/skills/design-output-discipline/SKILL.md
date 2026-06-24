---
name: design-output-discipline
description: Enforce Hiker output discipline for PPT, images, posters, playing cards, SVG, PDF, Excel, file conversion, and batch image export tasks. Use when the user asks for visual artifacts, deck edits, poster/card generation, SVG conversion, batch export, preserving original content, avoiding text/proportion changes, or delivering separate files/zip outputs.
---

# Design Output Discipline

version: 0.2.0
owner: Hiker

## Use When

Use for PPT, image, poster, playing card, SVG, PDF, Excel, batch export, file conversion, and visual delivery tasks.

## Do Not Use When

Do not use for pure UI code implementation unless the output is a design artifact or exported file.

## Goal

Deliver actual generated files with preserved content, controlled style, correct proportions, and clear file paths.

## Required Inputs

- Source files or text/content to preserve.
- Desired output format, size, aspect ratio, style, batch naming, and delivery folder.
- Any reference image, brand/style constraint, or forbidden changes.

## Required Process

1. Inspect source files and identify content that must not change.
2. Choose the correct toolchain for the format: presentation, document, spreadsheet, PDF, SVG/vector, raster image, or batch conversion.
3. Preserve original text, order, proportions, and page/card count unless the user asks to edit them.
4. Generate separate output files or a zip when requested.
5. Render or open-check representative outputs before claiming completion.
6. Report exact generated file paths and any visual QA limitations.

## Evidence Rules

- Completion requires generated files, not just a description.
- A download link is valid only if the file exists at that path.
- For PPT/PDF/image outputs, visual render checks are stronger than file creation alone.
- For batch jobs, report file count and sample names.

## Output Format

```text
结论：
已生成：
保留/修改：
检查证据：
文件路径：
限制：
```

## Hard Rules

- Do not silently rewrite user text.
- Do not change aspect ratio, crop, or reorder pages/cards unless requested.
- Do not fabricate file paths, download links, or screenshots.
- Do not overwrite source files unless explicitly requested.

## Failure Modes

- Delivering only instructions instead of files.
- Losing Chinese text, fonts, ordering, page count, or card fronts/backs.
- Converting SVG/PPT with broken layout and no visual QA.

## Example User Inputs

- "把这个 PPT 批量导出成图片。"
- "做扑克牌海报，文字不要改。"
- "把 SVG 转成 PNG 和 PDF，保持比例。"

## Example Final Output

```text
结论：已生成批量图片和压缩包。
已生成：36 张 PNG，1 个 ZIP。
保留/修改：保留原文字和页面顺序，只统一导出尺寸。
检查证据：抽查第 1/18/36 张可打开，尺寸一致。
文件路径：C:\...\outputs\cards-export.zip
```
