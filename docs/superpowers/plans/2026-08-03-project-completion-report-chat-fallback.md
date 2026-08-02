# Project Completion Report Chat Fallback Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fall back from deterministic Feishu notification-app failures to one fixed owner chat, with redacted audit logs and visible delivery-channel state.

**Architecture:** Keep the existing notification-app delivery function unchanged as the primary attempt. Add one focused project-report fallback orchestrator that performs the approved `if` decision, calls an injected chat sender, and emits bounded audit events; wire it through the existing runtime factory. Extend occurrence completion metadata and the report page only with the final channel.

**Tech Stack:** Python 3.12 services and pytest, existing Feishu channel worker, markdown-backed project repository, vanilla JavaScript UI and Node VM tests.

## Global Constraints

- Apply fallback only to project completion reports.
- Do not fall back for network or timeout outcomes whose delivery result is unknown.
- Use one explicitly configured owner chat ID.
- Never log App secrets, tokens, webhook values, report bodies, artifact contents, or Agent prompts.
- Keep new business logic in focused files; `app/server.py` remains dependency wiring only.

---

### Task 1: Deterministic Chat Fallback and Audit Boundary

**Files:**
- Create: `app/services/project_completion_report_fallback.py`
- Create: `app/services/project_completion_report_audit.py`
- Modify: `app/services/project_completion_report_runtime.py`
- Test: `tests/test_project_completion_report_fallback.py`

**Interfaces:**
- Consumes: existing `deliver_completion_report(project, occurrence, report, ...) -> dict` result.
- Produces: `deliver_with_chat_fallback(..., primary_delivery, chat_delivery, owner_chat_id, audit) -> dict` with `deliveryChannel` equal to `notification_app` or `chat_app_fallback`.
- Produces: `append_completion_report_delivery_audit(status_dir, event) -> None` with bounded redacted JSONL output.

- [x] **Step 1: Write failing routing and audit tests**

```python
def test_missing_notification_app_falls_back_once_to_fixed_owner_chat():
    result = deliver_with_chat_fallback(
        project, occurrence, report,
        primary_delivery=lambda: {"ok": False, "status": "notification_app_required"},
        chat_delivery=lambda chat_id, markdown: {"ok": True, "messageId": "m-chat"},
        owner_chat_id="oc_owner",
        audit=events.append,
    )
    assert result["deliveryChannel"] == "chat_app_fallback"
    assert events[-1]["fallbackStatus"] == "sent"

def test_unknown_primary_result_does_not_fall_back():
    # Repeat for network_error and timeout; assert chat_delivery is never called.
```

- [x] **Step 2: Run the focused test and verify RED**

Run: `.venv/bin/pytest -q tests/test_project_completion_report_fallback.py`

Expected: collection fails because `services.project_completion_report_fallback` does not exist.

- [x] **Step 3: Implement the minimal `if` and redacted audit writer**

```python
UNKNOWN_PRIMARY_STATUSES = {"network_error", "timeout", "delivery_timeout"}

primary = primary_delivery()
if primary.get("ok"):
    return {**primary, "deliveryChannel": "notification_app"}
if primary.get("status") in UNKNOWN_PRIMARY_STATUSES:
    return primary
fallback = chat_delivery(owner_chat_id, render_chat_markdown(project, occurrence, report))
return ({**fallback, "deliveryChannel": "chat_app_fallback"}
        if fallback.get("ok") else combined_failure(primary, fallback))
```

Audit only IDs, channel statuses, bounded error codes, final message ID, and fallback decision.

- [x] **Step 4: Run focused and existing delivery/runtime tests**

Run: `.venv/bin/pytest -q tests/test_project_completion_report_fallback.py tests/test_project_completion_report_delivery.py tests/test_project_completion_report_runtime.py`

Expected: all pass.

- [x] **Step 5: Commit**

```bash
git add app/services/project_completion_report_fallback.py app/services/project_completion_report_audit.py app/services/project_completion_report_runtime.py tests/test_project_completion_report_fallback.py
git commit -m "feat(reporting): fall back to Feishu chat app"
```

### Task 2: Runtime Configuration, Persisted Channel, and UI

**Files:**
- Modify: `app/server.py`
- Modify: `app/services/project_completion_reporting.py`
- Modify: `app/services/project_completion_report_worker.py`
- Modify: `app/services/project_completion_report_api.py`
- Modify: `app/projects.js`
- Test: `tests/test_project_completion_report_server_wiring.py`
- Test: `tests/test_project_completion_reporting.py`
- Test: `tests/check_project_completion_report_status_ui.mjs`

**Interfaces:**
- Consumes: `VO_CONFIG.feishu.chatApp.completionReportFallbackChatId` and `VO_FEISHU_COMPLETION_REPORT_FALLBACK_CHAT_ID`.
- Produces: occurrence `deliveryChannel` and public summary `deliveryChannel`.
- Injects chat delivery through `_feishu_chat_app_text_send(chat_id, markdown)` and audit through the focused audit writer.

- [x] **Step 1: Write failing persistence, wiring, and UI tests**

```python
finish_completion_report_delivery(
    project, occurrence_id="o1", token="claim", now=NOW,
    message_id="m1", delivery_channel="chat_app_fallback",
)
assert occurrence["deliveryChannel"] == "chat_app_fallback"
```

The server test must prove the fixed chat ID and channel sender are injected without invoking the inbound chat dispatcher. The Node test must assert the report card contains `聊天机器人降级送达`.

- [x] **Step 2: Run tests and verify RED**

Run: `.venv/bin/pytest -q tests/test_project_completion_reporting.py tests/test_project_completion_report_server_wiring.py && node tests/check_project_completion_report_status_ui.mjs`

Expected: failures for the missing delivery-channel parameter/configuration/UI label.

- [x] **Step 3: Add thin configuration and state plumbing**

```python
occurrence.update({
    "state": "delivered",
    "visibleStatus": "delivered",
    "deliveryChannel": delivery_channel,
    "messageId": message_id,
})
```

Expose only the bounded channel enum in the report API and render the corresponding Chinese label on delivered cards.

- [x] **Step 4: Run focused tests**

Run: `.venv/bin/pytest -q tests/test_project_completion_reporting.py tests/test_project_completion_report_worker.py tests/test_project_completion_report_server_wiring.py tests/test_project_completion_report_api.py && node tests/check_project_completion_report_status_ui.mjs`

Expected: all pass.

- [x] **Step 5: Commit**

```bash
git add app/server.py app/services/project_completion_reporting.py app/services/project_completion_report_worker.py app/services/project_completion_report_api.py app/projects.js tests/test_project_completion_report_server_wiring.py tests/test_project_completion_reporting.py tests/check_project_completion_report_status_ui.mjs
git commit -m "feat(reporting): expose completion report delivery channel"
```

### Task 3: Live Simulation and Regression Verification

**Files:**
- Modify: `tests/test_project_completion_report_e2e.py`
- Modify: `openspec/changes/add-feishu-project-completion-reports/tasks.md`

**Interfaces:**
- Uses the configured single owner P2P chat as `completionReportFallbackChatId`.
- Uses the running worker and real local project repository for the acceptance occurrence.

- [ ] **Step 1: Add failing end-to-end fallback tests**

```python
def test_unconfigured_notification_app_delivers_once_through_chat_fallback():
    # Build the real runtime with fake primary/chat ports.
    # Assert delivered, chat_app_fallback, one Agent generation, and redacted audit metadata.
```

- [ ] **Step 2: Run the end-to-end test and verify RED, then complete minimal wiring**

Run: `.venv/bin/pytest -q tests/test_project_completion_report_e2e.py`

Expected RED before final runtime plumbing, then PASS after it is connected.

- [ ] **Step 3: Configure the sole local P2P owner chat and restart the service**

Persist the discovered sole P2P chat ID as `feishu.chatApp.completionReportFallbackChatId` without printing it, restart with `scripts/restart-local-8090.sh`, and verify `/health` returns HTTP 200.

- [ ] **Step 4: Create and complete the demo project**

Create `飞书汇报降级验收项目` with one final Markdown artifact and a staged completion occurrence. Wake the live worker, poll the report API until terminal, and assert `status=delivered` plus `deliveryChannel=chat_app_fallback`.

- [ ] **Step 5: Verify logs and regressions**

Run the completion-report, stage-dispatch, Feishu notification, periodic timer, API, and UI tests. Inspect the newest audit record for primary failure, fallback success, IDs, channel, and absence of secret/report content. Run `openspec validate add-feishu-project-completion-reports`.

- [ ] **Step 6: Commit**

```bash
git add tests/test_project_completion_report_e2e.py openspec/changes/add-feishu-project-completion-reports/tasks.md
git commit -m "test(reporting): verify live chat fallback flow"
```
