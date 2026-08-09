# Task 8.1 Evidence: Figma Reference Capture

## Status

Captured.

Reference Figma file:

`https://www.figma.com/design/o6Crht2KV89peGoPpCAJsX/My-Virtual-Office%EF%BD%9C%E6%A0%B8%E5%BF%83%E4%BA%A7%E5%93%81%E5%8E%9F%E5%9E%8B?node-id=0-1&p=f&t=0UNpFb5VwaGadv5j-0`

Figma file key: `o6Crht2KV89peGoPpCAJsX`

## Confirmed Inputs

- Full overlay frame node: `147:2`
- Modal node: `148:3`
- Reference viewport: `1512x742`
- Reference modal geometry: `1220x560`
- Reference pipeline canvas geometry: `1184x350`
- Approved intentional visual delta: remove the bottom `保存编排` action because orchestration edits auto-save.
- Font constraint from design: reuse existing `Press Start 2P` loading; do not copy generated Figma/Tailwind code directly into the app.

## Captured Screenshots

- Full overlay reference: `openspec/changes/add-project-task-orchestration/evidence/figma/figma-147-2-reference.png`
  - Exported PNG dimensions: `1512x742`
  - Figma node: `147:2` / `02B · 项目执行看板｜编排弹窗`
- Modal reference: `openspec/changes/add-project-task-orchestration/evidence/figma/figma-148-3-modal-reference.png`
  - Exported PNG dimensions: `1292x632`
  - Figma node: `148:3` / `Task Pipeline · Modal`
  - The PNG includes modal shadow/padding; the modal frame itself is `1220x560`.

## Computed Specifications

### Full Overlay Frame `147:2`

- Frame: `1512x742`, canvas position `x=8776,y=0`.
- Background: dark `#0a0a0f` Virtual Office page remains visible behind the orchestration modal.
- Project detail shell: `x=32,y=24,width=1448,height=694`.
- Project dim overlay: `Overlay · Project Dim`, `x=0,y=0,width=1512,height=742`.
- Orchestration dim overlay: `Overlay · Orchestration Dim`, `x=0,y=0,width=1512,height=742`.
- Orchestration modal placement: `x=146,y=91,width=1220,height=560`.

### Modal Frame `148:3`

- Modal root: `width=1220,height=560`, border `2px #ffd700`, radius `9px`, background `#111124`, shadow `0 16px 36px rgba(0,0,0,0.65)`.
- Header: `x=0,y=0,width=1220,height=57`, background `#0d0d1e`, horizontal padding `18px`, vertical padding `14px`, gap `12px`.
- Title: `任务流水线编排`, `Press Start 2P`, `10px`, color `#e8e8f0`, line-height `1.45`.
- Subtitle: `拖动任务调整执行编号；相同编号的任务并行执行`, `Press Start 2P`, `6px`, color `#73738f`.
- Close control: `x=1190,y=20,width=12,height=17`, `12px`, color `#73738f`.
- Notice: `x=0,y=57,width=1220,height=30`, background `#0d1a29`, border `1px #3c82f6`, text color `#8cb2eb`, icon color `#3c82f6`.
- Workspace: `x=0,y=87,width=1220,height=403`, background `#111124`, padding `18px` horizontal, `10px 8px` vertical, gap `8px`.
- Controls row: `x=18,y=10,width=1184,height=27`, gap `8px`.
- Add-task button: `59x25`, background `#2e2600`, border `1px #ffd700`, radius `5px`, label `6.5px #ffd700`.
- Summary label: `9 TASKS · 5 STEPS`, `6px #73738f`.
- Parallel hint: `相同编号并行`, `6px #3c82f6`.
- Fit-canvas button: `46x25`, background `#1a1a38`, border `1px #3b3b5e`, radius `5px`, label `6.5px #e8e8f0`.
- Pipeline canvas: `x=18,y=45,width=1184,height=350`, background `#09091a`, border `1px #2b2b4f`, radius `7px`, overflow clipped.
- Task card base: `190x68`, background `#15152e`, radius `7px`, padding `9px`, vertical gap `8px`.
- Task title row: horizontal gap `6px`; number badge has border `#ffd700`, radius `10px`, padding `6px 4px`, label `4.5px #ffd700`.
- Task title: `Press Start 2P`, `5.4px`, color `#e8e8f0`, line-height `1.45`.
- Task metadata: `Press Start 2P`, `4.8px`, color `#73738f`.
- State pill: radius `10px`, padding `6px 4px`, label `4.5px`.
- In-progress state: border/text `#3c82f6`.
- Backlog state: border/text `#73738f`.
- Review state: border/text `#ff7d0d`.
- Connector arrows: `12px`, color `#73738f`, y `166`, x positions `227`, `460`, `693`, `926`.
- Stage columns:
  - Stage 1: `x=24,y=141,width=190,height=68`.
  - Stage 2 parallel group: `x=257,y=101,width=190,height=148`, two cards at `y=0` and `y=80`.
  - Stage 3 parallel group: `x=490,y=61,width=190,height=228`, three cards at `y=0`, `y=80`, `y=160`.
  - Stage 4: `x=723,y=141,width=190,height=68`.
  - Stage 5 parallel group: `x=956,y=101,width=190,height=148`, two cards at `y=0` and `y=80`.
- Footer: `x=0,y=490,width=1220,height=53`, background `#0d0d1e`, horizontal padding `18px`, vertical padding `13px`, gap `10px`.
- Footer hint: `横向拖动调整任务编号 · 同编号任务纵向排列并行执行`, `5.5px #73738f`.
- Cancel button: `x=1105,y=13,width=37,height=27`, background `#1a1a38`, border `1px #3a3a5e`, radius `5px`, label `6.5px #e8e8f0`.
- Figma save button: `x=1152,y=13,width=50,height=27`, background `#11351b`, border `1px #4caf50`, radius `5px`, label `保存编排`, `6.5px #6bc773`.

### Intentional Visual Delta

The implementation MUST omit the footer `保存编排` button. This is the only approved intentional visual delta from Figma because orchestration edits auto-save. The footer layout should keep the cancel/close affordance and remaining hint text aligned after removing the save action.

## Repository Search

Commands run:

```bash
rg -n "147:2|148:3|Figma|figma|reference screenshot|1512|742|1220|560|1184|350" openspec app tests . -g '!node_modules' -g '!__pycache__'
rg -n "figma\\.com|fileKey|file key|node-id|147-2|148-3|147:2|148:3" . -g '!node_modules' -g '!__pycache__' -g '!*.pyc'
find openspec/changes/add-project-task-orchestration -maxdepth 4 -type f | sort
find . -path './node_modules' -prune -o -path './.git' -prune -o \( -iname '*figma*' -o -iname '*147*' -o -iname '*148*' -o -iname '*orchestration*png' -o -iname '*orchestration*jpg' \) -print
rg -a -n "figma\\.com/(design|file|proto)|node-id=147|node-id=148|147-2|148-3" data .codex . -g '!node_modules' -g '!__pycache__'
find /root/home/cosh/my-virtual-office /root/.config /root/.cache /root/.local/share -type f \( -name 'History' -o -name 'Archived History' -o -name 'Bookmarks' -o -name 'Preferences' -o -name 'Login Data' \) 2>/dev/null
```

Findings:

- OpenSpec references the Figma node IDs in `proposal.md`, `design.md`, `tasks.md`, and `specs/project-task-orchestration/spec.md`.
- No Figma URL, Figma file key, prior reference screenshot, or local exported image for nodes `147:2` / `148:3` was found in the repository or local `data/` search.
- Local browser profile search found only `/root/home/cosh/my-virtual-office/data/agent-browser-profile/Default/Preferences`; no `History` or `Bookmarks` database with a Figma URL was present.
- Connected Chrome DevTools pages were checked and only local Virtual Office / blank pages were open; no Figma document tab was available to inspect for a file key.

## Verification

```bash
npx --yes @fission-ai/openspec@latest validate add-project-task-orchestration --strict
```

Result before task status update: `Change 'add-project-task-orchestration' is valid`

```bash
file openspec/changes/add-project-task-orchestration/evidence/figma/figma-147-2-reference.png
```

Result: `PNG image data, 1512 x 742, 8-bit/color RGBA, non-interlaced`

```bash
file openspec/changes/add-project-task-orchestration/evidence/figma/figma-148-3-modal-reference.png
```

Result: `PNG image data, 1292 x 632, 8-bit/color RGBA, non-interlaced`

```bash
npx --yes @fission-ai/openspec@latest validate add-project-task-orchestration --strict
```

Result after task status update: `Change 'add-project-task-orchestration' is valid`
