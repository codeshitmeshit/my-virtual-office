# Human Decision VO Shell Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Move the human-decision entry into the VO right control panel and present its detailed UI as a centered VO modal with consistent typography.

**Architecture:** Keep the existing `HumanDecisionCenter` controller and HTTP/SSE wiring unchanged. Move only the entry markup, restyle the existing host as a centered modal, and update the controller-rendered icon and label so the component continues to own pending-count state.

**Tech Stack:** Static HTML, vanilla JavaScript, CSS, Node.js contract tests, in-app browser acceptance.

## Global Constraints

- Reuse existing VO sidebar, modal, color-variable, and typography patterns.
- Use `⚖️` instead of `◇`.
- Do not change decision API, SSE, Feishu, reminder, timeout, or persistence behavior.
- Preserve the existing management-token submission flow.

---

### Task 1: Sidebar and modal contract

**Files:**
- Modify: `tests/check_human_decision_center.mjs`
- Modify: `app/index.html`
- Modify: `app/human-decision-center.js`

**Interfaces:**
- Consumes: `HumanDecisionCenter.mount({ toggle, panel }, snapshot, callbacks)`
- Produces: sidebar-owned `#human-decision-center-toggle` and page-level `#human-decision-center-panel`

- [ ] **Step 1: Write the failing static contract assertions**

Assert that the toggle appears between the opening and closing `.sidebar` markup, that the toolbar no longer contains the toggle, that the sidebar copy contains `⚖️ 人工决策`, and that controller output uses `⚖️` plus `打开人工决策`.

- [ ] **Step 2: Run the contract test and verify RED**

Run: `node tests/check_human_decision_center.mjs`

Expected: FAIL because the toggle remains in the toolbar and the controller still renders `◇ 决策`.

- [ ] **Step 3: Implement the minimal markup and renderer change**

Move the toggle into a new `.human-decision-sidebar.collapsible` block next to meetings/projects and replace the rendered icon/label with `⚖️` and `打开人工决策`.

- [ ] **Step 4: Run the contract test and verify GREEN**

Run: `node tests/check_human_decision_center.mjs`

Expected: PASS.

### Task 2: Centered VO modal and typography

**Files:**
- Modify: `tests/check_human_decision_center.mjs`
- Modify: `app/human-decision-center.css`

**Interfaces:**
- Consumes: `.human-decision-center-host`, `.human-decision-center`, existing VO CSS variables
- Produces: centered modal geometry and four explicit font tiers

- [ ] **Step 1: Write failing CSS contract assertions**

Assert centered host alignment, a modal width no larger than the meetings pattern, a 14px shell title, 12px decision title, 10px body/control text, and 8–9px metadata.

- [ ] **Step 2: Run the contract test and verify RED**

Run: `node tests/check_human_decision_center.mjs`

Expected: FAIL because the host is end-aligned and large titles use `clamp(...)` up to 34px.

- [ ] **Step 3: Implement the minimal CSS change**

Center the host, match the VO modal surface and border, add sidebar-specific styles, and replace oversized responsive font rules with the four approved tiers.

- [ ] **Step 4: Run component and related UI tests**

Run: `node tests/check_human_decision_center.mjs && node tests/check_dashboard_realtime_static.mjs && node tests/test_management_token_dialog.js`

Expected: PASS.

### Task 3: Browser acceptance

**Files:**
- Modify: `openspec/changes/add-decision-request-ui-prototype/verification-evidence.md`

**Interfaces:**
- Consumes: local VO at `http://127.0.0.1:8090/`
- Produces: recorded acceptance evidence

- [ ] **Step 1: Reload the local VO and inspect the right sidebar**

Verify the toolbar has no decision button and the right sidebar contains the `⚖️ 人工决策` section.

- [ ] **Step 2: Open the center and inspect the modal**

Verify it is centered, uses a consistent font scale, supports pending/history navigation, and closes from both the close button and backdrop.

- [ ] **Step 3: Verify live-state compatibility**

Confirm the existing SSE snapshot still updates pending count and decision history without creating another `EventSource`.

- [ ] **Step 4: Record evidence and run scoped verification**

Run: `git diff --check -- app/index.html app/human-decision-center.js app/human-decision-center.css tests/check_human_decision_center.mjs openspec/changes/add-decision-request-ui-prototype/verification-evidence.md`

Expected: no output and exit code 0.
