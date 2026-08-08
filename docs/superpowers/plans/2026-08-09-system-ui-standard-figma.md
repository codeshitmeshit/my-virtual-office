# Virtual Office System UI Standard Figma Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Upgrade the existing Figma reference page into an authoritative, reviewable system UI standard without modifying frontend code.

**Architecture:** Extend the existing first-page reference as a single vertically ordered documentation surface. Reuse the current semantic variables and component sets, add narrowly scoped icon/action patterns and destructive-flow examples, and validate every new section structurally and visually before final delivery.

**Tech Stack:** Figma Plugin API through `use_figma`, existing Virtual Office variables and component sets, Figma screenshots for visual verification.

## Global Constraints

- Do not modify HTML, CSS, JavaScript, templates, server code, or tests.
- Keep the standard page at page index `0` and preserve existing product pages.
- Reuse the existing Noto Sans SC typography and semantic color, spacing, and radius variables.
- Use gold for global primary/active semantics and red only for destructive/error semantics.
- Keep green domain examples labeled as existing examples, not global defaults.
- Make every top-level section independently named, searchable, editable, and directly linkable.
- Treat delete, close, clear, and remove as distinct semantics.

---

### Task 1: Authoritative entry and page baseline

**Figma objects:**
- Modify page: `356:240`
- Modify root: `356:241`
- Modify cover: `357:2`
- Modify composition: `363:44`

**Interfaces:**
- Consumes: existing page order, semantic variables, component instances, and composition example.
- Produces: authoritative page title, scope banner, Agent reading order, and one clearly labeled standard page composition.

- [ ] **Step 1: Read the target nodes and confirm current IDs, order, names, and typography.**
- [ ] **Step 2: Rename the page to `00 · SYSTEM UI STANDARD · AI START HERE`.**
- [ ] **Step 3: Update the cover with `AUTHORITATIVE STANDARD`, the Figma-only scope boundary, and the required Agent reading order.**
- [ ] **Step 4: Rename the composition section to `05 · Standard Page Composition` and add a note that it is the target visual baseline, not a live implementation.**
- [ ] **Step 5: Capture cover and composition screenshots; verify no clipping and that the standard is visibly distinguishable from product pages.**

### Task 2: Icon and action language

**Figma objects:**
- Create frame: `03 · Icons & Actions`
- Create component set: `VO Standard/Icon Button`
- Create component examples for Plus, Edit, Trash, Remove, Clear, Close, Arrow Left, Chevron, More, Refresh, Check, Warning, and Error.

**Interfaces:**
- Consumes: semantic text, border, gold, danger, success, warning, spacing, and radius variables.
- Produces: reusable icon-button variants and a semantic action inventory used by destructive-flow examples.

- [ ] **Step 1: Search the local file and available libraries for compatible icon assets; reuse only if the visual language and ownership are compatible.**
- [ ] **Step 2: Build a consistent 16 px linear icon family with a 32 px default control and a minimum documented 40 × 40 px pointer target.**
- [ ] **Step 3: Build `VO Standard/Icon Button` variants for `Tone=Neutral|Primary|Danger` and `State=Default|Hover|Focus|Disabled|Loading`.**
- [ ] **Step 4: Add usage rows that distinguish Delete, Close, Clear, and Remove by icon, label, color, tooltip, and accessible name.**
- [ ] **Step 5: Add correct/incorrect examples, including the rule that color never carries meaning alone.**
- [ ] **Step 6: Validate component structure and screenshot the full section.**

### Task 3: Destructive action levels and flows

**Figma objects:**
- Create frame: `04 · Destructive Actions`
- Create examples: `Level 1 · Remove`, `Level 2 · Recoverable Delete`, `Level 3 · Permanent Delete`
- Create confirmation examples using `VO Reference/Modal Shell` and global button variants.

**Interfaces:**
- Consumes: icon/action language from Task 2, modal shell `360:378`, button set `361:327`, and semantic danger variables.
- Produces: visual and behavioral contract for destructive operations.

- [ ] **Step 1: Document Level 1 as neutral removal with immediate feedback and optional undo.**
- [ ] **Step 2: Document Level 2 as danger-triggered deletion with named-object confirmation, loading lock, error preservation, and recovery entry.**
- [ ] **Step 3: Document Level 3 as irreversible deletion with explicit consequence copy and an action-specific primary label.**
- [ ] **Step 4: Add a numbered flow from trigger through confirmation, request, success/error, and recovery.**
- [ ] **Step 5: Document that Close, Cancel, backdrop click, and Escape have no destructive side effect.**
- [ ] **Step 6: Validate the section structure and screenshot all three levels.**

### Task 4: Adoption boundary and Agent checklist

**Figma objects:**
- Create frame: `06 · Adoption Checklist`
- Modify cover guidance in `357:2`

**Interfaces:**
- Consumes: approved scope and all standard sections.
- Produces: a machine-readable checklist separating this Figma standard phase from later frontend implementation.

- [ ] **Step 1: Add a `Before designing` checklist: read foundations, reuse components, classify actions, and inspect states.**
- [ ] **Step 2: Add a `Before handoff` checklist: verify tokens, names, focus, loading, error, destructive behavior, and accessibility labels.**
- [ ] **Step 3: Add a scope boundary: this phase defines Figma standards; frontend alignment is a separate future requirement.**
- [ ] **Step 4: Add deviation handling: record reason, affected surface, and regression expectation instead of silently creating a second pattern.**
- [ ] **Step 5: Screenshot and verify the checklist is readable and searchable.**

### Task 5: Final integration and quality gate

**Figma objects:**
- Validate page: `356:240`
- Validate root: `356:241`

**Interfaces:**
- Consumes: all completed standard sections.
- Produces: final direct node links and full-page review screenshot.

- [ ] **Step 1: Audit page index, top-level order, unique names, empty text, default layer names, and fonts.**
- [ ] **Step 2: Audit component bindings and confirm new components use existing semantic variables wherever applicable.**
- [ ] **Step 3: Confirm no product page was intentionally edited and no frontend repository file changed during Figma execution.**
- [ ] **Step 4: Capture screenshots for the cover, icons/actions, destructive actions, composition, adoption checklist, and full page.**
- [ ] **Step 5: Visually inspect screenshots for clipping, overflow, inconsistent alignment, incorrect icon meaning, and missing states.**
- [ ] **Step 6: Return direct Figma links and summarize the authoritative visual and interaction decisions.**
