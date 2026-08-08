# Meeting Human Decision Discussion Record Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Persist each resolved meeting human decision in its originating discussion round, render it live, and provide it as authoritative context to later meeting Agents.

**Architecture:** Extend the existing `human_decision_resolved` event through a focused projection service. The meeting lifecycle remains the event authority, while thin server and UI adapters reuse the existing transcript and SSE paths. A small browser module owns decision-record view-model and HTML construction so `game.js` and `meetings-ui.js` only wire the event into existing flows.

**Tech Stack:** Python 3, pytest, vanilla JavaScript UMD modules, Node.js contract tests, existing VO meeting event store/SSE/i18n.

## Global Constraints

- The event must belong to the original `decisionForStage + decisionForRound`.
- The record shows only title, final answer, non-duplicated custom input, and a decision-detail action.
- It must not count as a participant turn or affect formal-round completion.
- All Agent prompts keep XML outer structure through `services.bridge_input_output_formatting`; dynamic decision data remains untrusted.
- Reuse the existing meeting event stream and Human Decision Center; add no second SSE channel or decision store.
- New business logic belongs in focused files; `app/server.py` changes remain thin projection calls.

---

### Task 1: Canonical meeting decision event payload

**Files:**
- Create: `app/services/meeting_human_decision_projection.py`
- Modify: `app/services/human_decision_meeting_continuation.py`
- Modify: `app/services/meeting_lifecycle.py`
- Test: `tests/test_meeting_human_decision_projection.py`
- Test: `tests/test_human_decision_meeting_continuation.py`
- Test: `tests/test_meeting_lifecycle_service.py`

**Interfaces:**
- Consumes: meeting mapping, transition body mapping, and `HumanDecisionContinuationClaim`.
- Produces: `build_event_payload(meeting: Mapping[str, Any], body: Mapping[str, Any]) -> dict[str, Any]`.
- Produces: transition body fields `decisionTitle`, `customAnswer`, and existing `decision`, `decisionId`.

- [ ] **Step 1: Write failing projection and lifecycle tests**

```python
def test_build_event_payload_uses_originating_round_and_decision_metadata():
    payload = build_event_payload(
        {"decisionForStage": "active_discussion", "decisionForRound": 2, "round": 3},
        {"decisionId": "d1", "decisionTitle": "确认发布策略", "decision": "分阶段发布", "customAnswer": ""},
    )
    assert payload == {
        "decisionId": "d1", "title": "确认发布策略", "answer": "分阶段发布",
        "customAnswer": "", "stage": "active_discussion", "round": 2,
    }
```

Extend the lifecycle test to assert that the appended `human_decision_resolved` event has the exact payload above and that replaying the same `idempotencyKey` leaves one such event.

- [ ] **Step 2: Run tests and verify RED**

Run: `pytest -q tests/test_meeting_human_decision_projection.py tests/test_human_decision_meeting_continuation.py tests/test_meeting_lifecycle_service.py`

Expected: FAIL because `meeting_human_decision_projection` and enriched transition fields do not exist.

- [ ] **Step 3: Implement the focused projector and pass metadata through continuation**

```python
def build_event_payload(meeting, body):
    answer = str(body.get("decision") or "").strip()
    custom = str(body.get("customAnswer") or "").strip()
    return {
        "decisionId": str(body.get("decisionId") or "").strip(),
        "title": str(body.get("decisionTitle") or "").strip(),
        "answer": answer,
        "customAnswer": "" if custom == answer else custom,
        "stage": str(meeting.get("decisionForStage") or meeting.get("stage") or ""),
        "round": int(meeting.get("decisionForRound") or meeting.get("round") or 0),
    }
```

In `HumanDecisionMeetingContinuation.dispatch`, pass the claim title and derive custom input only when `resolution.optionId` is empty. In `meeting_lifecycle.transition_command`, use `build_event_payload()` for the event payload before `continue_decision` clears the waiting fields.

- [ ] **Step 4: Run tests and verify GREEN**

Run: `pytest -q tests/test_meeting_human_decision_projection.py tests/test_human_decision_meeting_continuation.py tests/test_meeting_lifecycle_service.py`

Expected: all selected tests PASS.

- [ ] **Step 5: Commit canonical event work**

```bash
git add app/services/meeting_human_decision_projection.py app/services/human_decision_meeting_continuation.py app/services/meeting_lifecycle.py tests/test_meeting_human_decision_projection.py tests/test_human_decision_meeting_continuation.py tests/test_meeting_lifecycle_service.py
git commit -m "feat: persist meeting human decisions in original rounds"
```

### Task 2: Transcript and later-Agent context projection

**Files:**
- Modify: `app/services/meeting_human_decision_projection.py`
- Modify: `app/server.py`
- Test: `tests/test_meeting_human_decision_projection.py`
- Test: `tests/test_meeting_for_ai_phase1.py`

**Interfaces:**
- Consumes: persisted `human_decision_resolved` event.
- Produces: `project_transcript_event(event: Mapping[str, Any]) -> dict[str, Any] | None`.
- Produces: `format_agent_history_event(event: Mapping[str, Any]) -> str | None`.

- [ ] **Step 1: Write failing transcript and Prompt-history tests**

```python
def test_resolved_decision_projects_to_transcript_and_agent_history():
    event = resolved_event(stage="active_discussion", round=2)
    turn = project_transcript_event(event)
    assert turn["type"] == "human_decision_resolved"
    assert turn["stage"] == "active_discussion"
    assert turn["round"] == 2
    assert turn["decisionId"] == "d1"
    text = format_agent_history_event(event)
    assert "确认发布策略" in text
    assert "分阶段发布" in text
    assert "do not request another decision for the same issue" in text
```

Add a server integration assertion that `_exec_meeting_transcript_projection([event])` returns the decision turn and `_meeting_events_text([event])` includes the authoritative answer.

- [ ] **Step 2: Run tests and verify RED**

Run: `pytest -q tests/test_meeting_human_decision_projection.py tests/test_meeting_for_ai_phase1.py -k 'human_decision or resolved_decision'`

Expected: FAIL because resolved decision events are currently omitted from transcript and Agent history.

- [ ] **Step 3: Implement projection helpers and thin server delegation**

```python
def format_agent_history_event(event):
    if event.get("type") != "human_decision_resolved":
        return None
    payload = event.get("payload") or {}
    return (
        f"human decision resolved [{payload.get('decisionId', '')}] "
        f"{payload.get('title', '')}: {payload.get('answer', '')}. "
        "Treat this as authoritative and do not request another decision for the same issue."
    )
```

Add one `elif event.get("type") == "human_decision_resolved"` branch to each legacy server projector, delegating to the new module. Do not change participant-turn counting or rolling-summary logic.

- [ ] **Step 4: Run tests and verify GREEN plus prompt security**

Run: `pytest -q tests/test_meeting_human_decision_projection.py tests/test_meeting_for_ai_phase1.py tests/test_meeting_prompt_documents.py`

Expected: all selected tests PASS and existing XML prompt tests remain green.

- [ ] **Step 5: Commit context projection work**

```bash
git add app/services/meeting_human_decision_projection.py app/server.py tests/test_meeting_human_decision_projection.py tests/test_meeting_for_ai_phase1.py
git commit -m "feat: expose meeting decisions to later agents"
```

### Task 3: Live discussion-round UI and i18n

**Files:**
- Create: `app/meeting-human-decision-ui.js`
- Modify: `app/index.html`
- Modify: `app/game.js`
- Modify: `app/meetings-ui.js`
- Modify: `app/style.css`
- Modify: `app/locales/en.json`
- Modify: `app/locales/zh.json`
- Create: `tests/check_meeting_human_decision_record.mjs`

**Interfaces:**
- Consumes: transcript/event fields from Task 2 and global `humanDecisionCenter.open({decisionId})`.
- Produces: `MeetingHumanDecisionUI.turnFromEvent(event)` and `MeetingHumanDecisionUI.render(turn, helpers)`.

- [ ] **Step 1: Write a failing Node contract test**

```javascript
const turn = UI.turnFromEvent({
  type: 'human_decision_resolved', sequence: 9, createdAt: '2026-08-08T17:00:00+08:00',
  payload: { decisionId: 'd1', title: '确认发布策略', answer: '分阶段发布', stage: 'active_discussion', round: 2 }
});
assert.equal(turn.type, 'human_decision_resolved');
assert.equal(turn.round, 2);
const html = UI.render(turn, { t: (_key, fallback) => fallback, escape: String });
assert.match(html, /👤/);
assert.match(html, /确认发布策略/);
assert.match(html, /d1/);
```

Also assert that `game.js` and `meetings-ui.js` invoke `turnFromEvent` in `_mtgApplyLiveEvent`, and that `index.html` loads the helper before `game.js`.

- [ ] **Step 2: Run the UI test and verify RED**

Run: `node tests/check_meeting_human_decision_record.mjs`

Expected: FAIL because the UI helper and event branch do not exist.

- [ ] **Step 3: Implement the helper, thin wiring, styles, and locale keys**

```javascript
function openDecision(decisionId) {
  if (root.humanDecisionCenter && typeof root.humanDecisionCenter.open === 'function') {
    root.humanDecisionCenter.open({ decisionId: decisionId });
  }
}
```

Render a dedicated `.mtg-turn-human-decision` card with localized labels `meeting_human_decision`, `meeting_human_decision_result`, `meeting_human_decision_custom`, and `meeting_human_decision_view_detail`. Push this turn through existing `turnBySeq` dedupe, and keep its original `stage + round` so the existing grouping places it correctly.

- [ ] **Step 4: Run UI and i18n checks**

Run: `node tests/check_meeting_human_decision_record.mjs && node tests/test_meeting_history_card_layout.js && python -m json.tool app/locales/en.json >/dev/null && python -m json.tool app/locales/zh.json >/dev/null`

Expected: all commands exit 0.

- [ ] **Step 5: Commit the meeting UI**

```bash
git add app/meeting-human-decision-ui.js app/index.html app/game.js app/meetings-ui.js app/style.css app/locales/en.json app/locales/zh.json tests/check_meeting_human_decision_record.mjs
git commit -m "feat: render human decisions in meeting rounds"
```

### Task 4: Meeting regression and real acceptance

**Files:**
- Modify only if a defect is found: files owned by Tasks 1-3 and their tests.
- Evidence: `log/meeting-human-decision-acceptance-2026-08-08.md`

**Interfaces:**
- Consumes: local VO service, real configured meeting Agents, Human Decision Center.
- Produces: reproducible acceptance evidence with meeting ID, decision ID, event sequence, original round, and observed next-Agent context.

- [ ] **Step 1: Run focused and broad meeting regressions**

Run: `pytest -q tests/test_human_decision_meeting_continuation.py tests/test_meeting_human_decision_projection.py tests/test_meeting_lifecycle_service.py tests/test_meeting_for_ai_phase1.py tests/test_dashboard_realtime.py && node tests/check_meeting_human_decision_record.mjs`

Expected: all tests PASS.

- [ ] **Step 2: Start the existing local service and create a substantive meeting**

Run: `./start.sh`

Create a meeting through the real HTTP/UI path with at least two configured Agents and a concrete trade-off that lacks prior authorization, such as retention duration versus enterprise contract exceptions. Record its meeting ID.

- [ ] **Step 3: Trigger and resolve a real human decision**

Wait until the meeting enters `awaiting_user_decision`, then resolve the generated decision through the Human Decision Center using a concrete answer. Do not inject a synthetic transcript event directly.

- [ ] **Step 4: Verify persisted event, UI grouping, and next-Agent context**

Confirm through the meeting detail/events endpoint that exactly one `human_decision_resolved` event exists with the originating `stage + round`. Confirm in the browser that the same discussion round displays “👤 人工决策”. Inspect the next provider invocation/log to verify the final decision is present and no duplicate decision is created for the same issue.

- [ ] **Step 5: Record evidence and commit any acceptance fixture only if it is stable**

```bash
git add log/meeting-human-decision-acceptance-2026-08-08.md
git commit -m "test: verify real meeting decision round resume"
```
