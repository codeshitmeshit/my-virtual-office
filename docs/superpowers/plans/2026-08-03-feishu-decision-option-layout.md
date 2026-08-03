# Feishu Decision Option Layout Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Render A–D decision options as four distinct Feishu card detail blocks while preserving existing actions and delivery routing.

**Architecture:** Change only the decision-specific intent builder in `human_decision_delivery.py`. Continue passing a plain ordered `details` mapping into the shared Feishu card renderer so the common renderer, sender, updater, and schema remain unchanged.

**Tech Stack:** Python 3, existing Feishu notification renderer, pytest.

## Global Constraints

- Reuse the existing common Feishu card renderer and delivery adapter.
- Keep A–D action values and custom input behavior unchanged.
- Keep terminal-card schema and update behavior unchanged.
- Preserve option order A, B, C, D.

---

### Task 1: Separate option detail blocks

**Files:**
- Modify: `tests/test_human_decision_delivery.py`
- Modify: `app/services/human_decision_delivery.py`

**Interfaces:**
- Consumes: `build_decision_intent(decision, terminal=False, application="") -> dict`
- Produces: an ordered `details` mapping with one `A｜...` through `D｜...` entry per option

- [ ] **Step 1: Write the failing card-output test**

Build the real card with `build_feishu_card(build_decision_intent(decision))`. Assert that the card contains four distinct Markdown elements whose text starts with `**A｜`, `**B｜`, `**C｜`, and `**D｜`, and that no Markdown element contains more than one option heading.

- [ ] **Step 2: Run the focused test and verify RED**

Run: `.venv/bin/python -m pytest -q tests/test_human_decision_delivery.py::test_pending_card_renders_each_option_as_a_distinct_detail_block`

Expected: FAIL because all four options currently occupy the single `ABCD 选项` detail value.

- [ ] **Step 3: Implement the minimal intent change**

Replace `_option_lines` with an option-detail mapping builder. Insert the returned entries into `details` between risk/urgency and VO recommendation. Use `A｜label（VO 推荐）` for the recommended option and `影响：impact` as its value.

- [ ] **Step 4: Run focused and delivery tests**

Run: `.venv/bin/python -m pytest -q tests/test_human_decision_delivery.py`

Expected: all tests pass.

### Task 2: Real-card acceptance

**Files:**
- Modify: `openspec/changes/add-decision-request-ui-prototype/verification-evidence.md`

**Interfaces:**
- Consumes: local `POST /api/agent/human-decisions` with a new idempotency key
- Produces: one new real Feishu Mock decision card

- [ ] **Step 1: Restart VO with the updated Python code**

Stop only the verified current repository `start.sh` process and launch `./start.sh`; confirm `/health` returns HTTP 200.

- [ ] **Step 2: Create a new Mock decision**

POST a non-business chat-source decision with a unique idempotency key, four distinct A–D labels, and the required trusted Agent headers.

- [ ] **Step 3: Verify delivery evidence**

Confirm the response reports `created=true`, `delivery.ok=true`, `delivery.status=sent`, and persisted delivery metadata contains a message ID.

- [ ] **Step 4: Record evidence and check the diff**

Run: `git diff --check -- app/services/human_decision_delivery.py tests/test_human_decision_delivery.py openspec/changes/add-decision-request-ui-prototype/verification-evidence.md`

Expected: exit code 0 with no output.
