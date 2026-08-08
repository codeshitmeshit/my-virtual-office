# Figma AI UI Reference Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a first-position, clearly labeled AI UI reference page to the existing My Virtual Office Figma file without changing existing prototype screens.

**Architecture:** The work lives entirely in the existing Figma design file. A dedicated page contains a cover, foundations, reusable local component examples, state examples, and one composition example; existing local variables and styles are reused where possible, and any new reference-only variables are scoped and named deterministically.

**Tech Stack:** Figma Design, Figma Plugin API through `use_figma`, existing Virtual Office design tokens and Noto Sans SC typography.

## Global Constraints

- Create `00 · AI UI Reference · START HERE` and place it first when supported.
- Do not modify or delete existing prototype screens.
- Use Auto Layout and stable, searchable names.
- Reuse existing tokens/components where compatible; new variables must have explicit scopes and code syntax.
- Do not include secrets, live credentials, or environment-specific paths.
- Verify every major section visually and check for clipping, overflow, font mismatch, and ambiguous labels.

---

### Task 1: Discover and lock source truth

**Files:**
- Read: `app/*.css`
- Read: `app/*.js`
- Read: Figma file `o6Crht2KV89peGoPpCAJsX`
- Create: `/tmp/design-system-state-mvo-ai-ui-reference-20260809.json`

**Interfaces:**
- Consumes: approved design specification and Figma node `334:245`.
- Produces: exact page inventory, local variable/style/component inventory, source token map, font map, and v1 component list.

- [ ] **Step 1: Inspect the Figma file without mutation**

Use the design-system inspection helper through `use_figma`; return page order, existing components, local variable collections, local styles, and available fonts relevant to `Noto Sans SC`.

- [ ] **Step 2: Inspect code tokens and UI patterns**

Use CodeGraph and focused searches to extract actual colors, typography, spacing, radius values, and the existing implementations of buttons, inputs, navigation, badges, cards, and modals.

- [ ] **Step 3: Search linked Figma libraries**

Call `get_libraries`, then search for button, input, toggle, navigation, badge, card, and modal assets. Prefer compatible local assets, then linked library assets, then new local reference components.

- [ ] **Step 4: Record the locked scope and gap analysis**

Write the discovery result and every code/Figma conflict resolution to the state ledger. The v1 component list is: Button, Input, Select, Toggle, Navigation Item, Status Badge, Card, and Modal Shell.

### Task 2: Create the discoverable reference page and foundations

**Files:**
- Modify: Figma file `o6Crht2KV89peGoPpCAJsX`
- Modify: `/tmp/design-system-state-mvo-ai-ui-reference-20260809.json`

**Interfaces:**
- Consumes: Task 1 token/style/font inventory.
- Produces: reference page ID plus cover and foundations frame IDs.

- [ ] **Step 1: Create and prioritize the page**

Create `00 · AI UI Reference · START HERE`, move it to index `0` if the Plugin API supports document-child reordering, and return the created page ID.

- [ ] **Step 2: Create the cover frame**

Build `00 · Cover · AI UI Reference` with a high-contrast label, purpose statement, four Agent guidance rules, and a compact scope note.

- [ ] **Step 3: Create foundations documentation**

Build `01 · Foundations` with verified color, typography, spacing, and radius examples. Bind to compatible existing variables; create narrowly scoped reference variables only when no compatible variable exists.

- [ ] **Step 4: Validate foundations**

Capture the cover and foundations screenshots, inspect text and layout, and read back font families and variable bindings.

### Task 3: Create reusable component and state references

**Files:**
- Modify: Figma file `o6Crht2KV89peGoPpCAJsX`
- Modify: `/tmp/design-system-state-mvo-ai-ui-reference-20260809.json`

**Interfaces:**
- Consumes: Task 2 foundations and page ID.
- Produces: component/component-set IDs and state-reference frame ID.

- [ ] **Step 1: Create atomic controls**

Create or reuse Button, Input, Select, Toggle, Navigation Item, and Status Badge patterns with Auto Layout, explicit variable bindings, stable variant properties, descriptions, and component instances for documentation.

- [ ] **Step 2: Create container patterns**

Create or reuse Card and Modal Shell patterns using the same foundations and document their intended use.

- [ ] **Step 3: Create the state matrix**

Build `03 · States` showing applicable Default, Hover, Focus, Selected, Disabled, Loading, Success, Warning, and Error states. Do not fabricate impossible states for components that do not support them.

- [ ] **Step 4: Validate components and states**

Inspect structure and screenshots for every component family, verify component properties and bindings, and correct clipping or naming issues before composition work.

### Task 4: Add a composition example and complete QA

**Files:**
- Modify: Figma file `o6Crht2KV89peGoPpCAJsX`
- Modify: `/tmp/design-system-state-mvo-ai-ui-reference-20260809.json`

**Interfaces:**
- Consumes: Task 3 component instances.
- Produces: final composition frame, QA evidence, and direct Figma node links.

- [ ] **Step 1: Build the composition example**

Build `04 · Composition Example` as a compact settings-style panel assembled from reference components. Use generic safe sample data and preserve the established Virtual Office dark visual language.

- [ ] **Step 2: Run structural QA**

Audit duplicate or unnamed nodes, page order, component names, unresolved bindings, and accidental changes outside the new page.

- [ ] **Step 3: Run visual QA**

Capture the full reference page and each major section. Check for clipped text, overflow, placeholder copy, inconsistent spacing, incorrect hotspot/state labels, font substitution, and low contrast.

- [ ] **Step 4: Hand off review links**

Return the Figma page link and direct links to Cover, Foundations, Components, States, and Composition Example, accompanied by a concise summary of the reference rules.
