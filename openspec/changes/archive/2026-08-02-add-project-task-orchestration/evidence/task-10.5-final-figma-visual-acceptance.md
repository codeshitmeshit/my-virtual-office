# Task 10.5 final Figma visual acceptance

Date: 2026-07-27
Change: `add-project-task-orchestration`
Task: `10.5 Complete final Figma visual acceptance and attach reference/candidate screenshots, measured geometry, intentional-difference record, and any environment-dependent font notes.`

## Figma Source

- File: `My Virtual Office｜核心产品原型`
- URL: `https://www.figma.com/design/o6Crht2KV89peGoPpCAJsX/My-Virtual-Office%EF%BD%9C%E6%A0%B8%E5%BF%83%E4%BA%A7%E5%93%81%E5%8E%9F%E5%9E%8B?node-id=0-1&p=f&t=0UNpFb5VwaGadv5j-0`
- Full overlay node: `147:2`
- Modal node: `148:3`
- Reference viewport: `1512x742`
- Reference modal geometry: `1220x560`
- Reference pipeline canvas geometry: `1184x350`

## Attached Screenshots

Reference screenshots:

- `openspec/changes/add-project-task-orchestration/evidence/figma/figma-147-2-reference.png`
  - PNG dimensions: `1512x742`
  - SHA-256: `b574e2d99ec4e790f9cb59f24e3a3232126aedd01186222adfe173765636d4d9`
- `openspec/changes/add-project-task-orchestration/evidence/figma/figma-148-3-modal-reference.png`
  - PNG dimensions: `1292x632`
  - SHA-256: `9186496b6290ca563d4d7edb3745e03414d9fda877c8abeca3fb8e9f5c9fea34`

Candidate screenshot:

- `openspec/changes/add-project-task-orchestration/evidence/figma/candidate-8.8-orchestration-overlay.png`
  - Regenerated during final acceptance with an isolated headless Chromium instance.
  - PNG dimensions: `1512x742`
  - SHA-256: `8382ec74b5f4e8cd82414f393b59a23b8c219757358ebe44dd75164c83acd7bf`

## Measured Candidate Geometry

Collected by `tests/check_project_orchestration_visual_snapshot.mjs` at `1512x742`.

| Element | Expected From Figma | Candidate Measurement | Result |
| --- | --- | --- | --- |
| Viewport | `1512x742` | `1512x742` | pass |
| Overlay | `0,0,1512x742` | `0,0,1512x742` | pass |
| Modal | `x=146,y=91,width=1220,height=560` | `x=146,y=91,width=1220,height=560` | pass |
| Header | `height=57` | `height=57` | pass |
| Notice | `height=30` | `height=32` border-box | pass within 2px tolerance |
| Canvas | `width=1184,height=350` | `x=164,y=228,width=1184,height=350` | pass |
| Footer | `height=53` | `height=55` border-box | pass within 2px tolerance |
| Tasks | `9` | `9` | pass |
| Stages | `5` | `5` | pass |
| Connectors | `4` | `4` | pass |
| Save button | removed | `0` | pass |
| Title | `任务流水线编排` | `任务流水线编排` | pass |
| Count label | `9 TASKS · 5 STEPS` | `9 TASKS · 5 STEPS` | pass |
| Modal background | `#111124` | `rgb(17, 17, 36)` | pass |
| Modal border | `#ffd700` | `rgb(255, 215, 0)` | pass |
| Canvas background | `#09091a` | `rgb(9, 9, 26)` | pass |

## Visual Review

Manual review compared the Figma full-overlay reference and the regenerated candidate screenshot.

Accepted:

- The orchestration modal keeps the Figma placement, size, border, radius, shadow, header, notice, workspace, canvas, and footer structure.
- The pipeline canvas preserves the Figma visual hierarchy: dark canvas, horizontal stage progression, vertical parallel groups, small connector arrows, compact pixel typography, status pills, and highlighted active/review card states.
- The footer has only the cancel/close affordance and explanatory hint. There is no explicit save action.
- Text remains contained inside cards, pills, toolbar controls, and footer at the reference viewport.

Intentional differences:

- The Figma footer has a green `保存编排` button. The implementation intentionally omits it because orchestration edits auto-save.
- The candidate screenshot uses a deterministic project shell instead of the complete live VO project detail page behind the dim overlay. This isolates modal visual acceptance; task 10.4 separately verified the real modal opening inside the live app.
- Candidate task titles/assignees are fixture data, not the exact Figma copy. Geometry, count, grouping, state styling, and hierarchy are the accepted comparison target.

## Font Notes

- Figma evidence was captured against the design's pixel font treatment.
- The app loads `Press Start 2P` in `app/index.html` and defines `--project-orchestration-font: "Press Start 2P", "Fusion Pixel 12px Proportional SC", "Microsoft YaHei", monospace` in `app/project-orchestration.css`.
- In Chinese-localized app contexts, `app/fonts.css` can globally switch UI text to `Fusion Pixel 12px Proportional SC`. The visual test accepts either `Press Start 2P` or `Fusion Pixel` so CI/local runs remain stable while preserving the intended pixel-font family.

## Verification Commands

```bash
VO_CDP_URL=http://127.0.0.1:9334 node tests/check_project_orchestration_visual_snapshot.mjs
```

Result: passed and regenerated `candidate-8.8-orchestration-overlay.png`.

```bash
node --check tests/check_project_orchestration_visual_snapshot.mjs
node --check app/project-orchestration.js
.venv/bin/python -m pytest -q tests/test_project_orchestration_css.py
```

Result: `5 passed in 0.13s`.

```bash
file openspec/changes/add-project-task-orchestration/evidence/figma/figma-147-2-reference.png openspec/changes/add-project-task-orchestration/evidence/figma/figma-148-3-modal-reference.png openspec/changes/add-project-task-orchestration/evidence/figma/candidate-8.8-orchestration-overlay.png
```

Result:

- `figma-147-2-reference.png`: `PNG image data, 1512 x 742, 8-bit/color RGBA, non-interlaced`
- `figma-148-3-modal-reference.png`: `PNG image data, 1292 x 632, 8-bit/color RGBA, non-interlaced`
- `candidate-8.8-orchestration-overlay.png`: `PNG image data, 1512 x 742, 8-bit/color RGB, non-interlaced`

## Acceptance Decision

Accepted. The final candidate matches the Figma modal geometry and visual contract with only the approved save-button removal and deterministic-fixture background/copy differences.
