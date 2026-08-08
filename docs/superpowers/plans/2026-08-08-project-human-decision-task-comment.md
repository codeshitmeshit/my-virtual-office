# Project Human Decision Task Comment Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add one idempotent “human decision” system comment to the bound project task when its decision resolves, then verify the original task resumes with that context.

**Architecture:** A focused comment factory owns structured metadata, fallback text, and duplicate detection. `ProjectHumanDecisionContinuation` adds the comment inside the same repository update that prepares the attempt for resume, before dispatching external work. A focused browser helper renders the structured comment through the existing task comment list and Human Decision Center.

**Tech Stack:** Python 3, pytest, existing Markdown-backed `ProjectRepository`, vanilla JavaScript UMD module, Node.js contract tests, existing project UI/i18n.

## Global Constraints

- Reuse `task.comments`; do not create another comment API, store, or timeline.
- Persist `kind=human_decision`, stable `author=human_decision`, `decisionId`, title, final answer, optional non-duplicated custom input, and compatible text.
- A resolved decision comment remains if downstream dispatch is temporarily rejected; retries must not duplicate it.
- Comment persistence and attempt resume preparation occur in one repository update; persistence failure must prevent dispatch.
- Dynamic comment data remains untrusted in XML Agent prompts.
- New business logic belongs in focused modules; server wiring remains dependency injection only.

---

### Task 1: Structured task decision comment and atomic resume preparation

**Files:**
- Create: `app/services/project_human_decision_comment.py`
- Modify: `app/services/project_human_decision_continuation.py`
- Modify: `app/server.py`
- Create: `tests/test_project_human_decision_comment.py`
- Modify: `tests/test_project_human_decision_continuation.py`

**Interfaces:**
- Consumes: `HumanDecisionContinuationClaim`, current task mapping, `new_id: Callable[[], str]`, `now: Callable[[], str]`.
- Produces: `ensure_decision_comment(task, decision, *, decision_id, new_id, now) -> tuple[dict[str, Any], bool]` where the boolean says whether a new comment was appended.
- Extends: `ProjectContinuationPorts.new_id: Callable[[], str]`.

- [ ] **Step 1: Write failing comment-factory tests**

```python
def test_ensure_decision_comment_adds_structured_compatible_comment_once():
    task = {"id": "t1", "comments": []}
    first, created = ensure_decision_comment(
        task,
        {"title": "确认发布策略", "resolution": {"answer": "分阶段发布", "optionId": "B"}},
        decision_id="d1", new_id=lambda: "c1", now=lambda: "now",
    )
    second, replay_created = ensure_decision_comment(
        task,
        {"title": "确认发布策略", "resolution": {"answer": "分阶段发布", "optionId": "B"}},
        decision_id="d1", new_id=lambda: "c2", now=lambda: "later",
    )
    assert created is True and replay_created is False
    assert first is second
    assert first["kind"] == "human_decision"
    assert first["decisionId"] == "d1"
    assert len(task["comments"]) == 1
```

- [ ] **Step 2: Run tests and verify RED**

Run: `pytest -q tests/test_project_human_decision_comment.py tests/test_project_human_decision_continuation.py`

Expected: FAIL because the comment factory and `new_id` port do not exist.

- [ ] **Step 3: Implement the factory and call it inside `prepare`**

```python
def ensure_decision_comment(task, decision, *, decision_id, new_id, now):
    comments = task.setdefault("comments", [])
    existing = next((item for item in comments if item.get("kind") == "human_decision" and item.get("decisionId") == decision_id), None)
    if existing:
        return existing, False
    resolution = decision.get("resolution") if isinstance(decision.get("resolution"), dict) else {}
    answer = str(resolution.get("answer") or "").strip()
    custom = answer if not resolution.get("optionId") else ""
    comment = {
        "id": new_id(), "kind": "human_decision", "author": "human_decision",
        "text": answer, "createdAt": now(), "decisionId": decision_id,
        "decisionTitle": str(decision.get("title") or "").strip(),
        "decisionAnswer": answer, "customAnswer": "" if custom == answer else custom,
    }
    comments.append(comment)
    return comment, True
```

Call this after binding validation and before the repository update returns. Inject `new_id=lambda: str(uuid.uuid4())` from server wiring. On dispatcher rejection, restore attempt fields only; leave the comment intact.

- [ ] **Step 4: Run tests and verify GREEN**

Run: `pytest -q tests/test_project_human_decision_comment.py tests/test_project_human_decision_continuation.py tests/test_human_decision_server_wiring.py`

Expected: all selected tests PASS.

- [ ] **Step 5: Commit atomic comment persistence**

```bash
git add app/services/project_human_decision_comment.py app/services/project_human_decision_continuation.py app/server.py tests/test_project_human_decision_comment.py tests/test_project_human_decision_continuation.py tests/test_human_decision_server_wiring.py
git commit -m "feat: record project decisions as task comments"
```

### Task 2: Markdown round-trip and later-Agent context

**Files:**
- Test: `tests/test_project_repository.py`
- Test: `tests/test_project_execution_prompt_formatting.py`
- Modify only if failing: `app/project_store.py`
- Modify only if failing: `app/services/project_execution_prompt_formatting.py`

**Interfaces:**
- Consumes: structured decision comment produced by Task 1.
- Produces: unchanged structured fields after Markdown repository save/load and compatible `text` visible to later task Agents.

- [ ] **Step 1: Write failing or characterization tests for round-trip and prompt visibility**

```python
def test_human_decision_comment_round_trips_structured_metadata(project_repository):
    project_repository.update("p1", lambda project: project["tasks"][0].setdefault("comments", []).append({
        "id": "c1", "kind": "human_decision", "author": "human_decision",
        "text": "分阶段发布", "createdAt": "now", "decisionId": "d1",
        "decisionTitle": "确认发布策略", "decisionAnswer": "分阶段发布", "customAnswer": "",
    }))
    comment = project_repository.get("p1")["tasks"][0]["comments"][0]
    assert comment["kind"] == "human_decision"
    assert comment["decisionId"] == "d1"
```

Add a prompt-formatting assertion that the task context contains `分阶段发布` inside the formatter's untrusted data section.

- [ ] **Step 2: Run tests and verify behavior**

Run: `pytest -q tests/test_project_repository.py tests/test_project_execution_prompt_formatting.py -k 'human_decision_comment'`

Expected: the round-trip test may already pass through `comments_json`; the prompt assertion must demonstrate actual visibility. If a test passes immediately, keep it only as characterization and create a failing test for the missing consumer behavior before production changes.

- [ ] **Step 3: Make the smallest required persistence/prompt change**

Preserve the whole comment mapping in `comments_json`. If the execution prompt currently omits comments, add the existing comments list as a named untrusted field through the shared business prompt formatter; do not concatenate comment text into trusted XML rules.

- [ ] **Step 4: Run persistence and prompt security regressions**

Run: `pytest -q tests/test_project_repository.py tests/test_project_execution_prompt_formatting.py tests/test_human_decision_agent_prompt_contract.py`

Expected: all selected tests PASS.

- [ ] **Step 5: Commit only if production files changed**

```bash
git add app/project_store.py app/services/project_execution_prompt_formatting.py tests/test_project_repository.py tests/test_project_execution_prompt_formatting.py
git commit -m "feat: retain project decision comments in agent context"
```

### Task 3: Special project comment UI and i18n

**Files:**
- Create: `app/project-human-decision-comment-ui.js`
- Modify: `app/index.html`
- Modify: `app/projects.js`
- Modify: `app/style.css`
- Modify: `app/locales/en.json`
- Modify: `app/locales/zh.json`
- Create: `tests/check_project_human_decision_comment.mjs`

**Interfaces:**
- Consumes: structured task comment from Task 1 and global `humanDecisionCenter.open({decisionId})`.
- Produces: `ProjectHumanDecisionCommentUI.isDecisionComment(comment)` and `ProjectHumanDecisionCommentUI.render(comment, helpers)`.

- [ ] **Step 1: Write the failing Node contract test**

```javascript
const html = UI.render({
  kind: 'human_decision', decisionId: 'd1', decisionTitle: '确认发布策略',
  decisionAnswer: '分阶段发布', customAnswer: '', createdAt: 'now'
}, { t: (_key, fallback) => fallback, escape: String, timeAgo: String });
assert.match(html, /👤/);
assert.match(html, /确认发布策略/);
assert.match(html, /分阶段发布/);
assert.match(html, /d1/);
```

Also assert `projects.js` delegates decision comments to this helper and leaves the ordinary-comment branch intact.

- [ ] **Step 2: Run test and verify RED**

Run: `node tests/check_project_human_decision_comment.mjs`

Expected: FAIL because the helper and projects.js branch do not exist.

- [ ] **Step 3: Implement helper, thin list integration, styles, and locales**

Load the helper before `projects.js`. In `renderDetailPanel`, map comments through `ProjectHumanDecisionCommentUI.render` only when `kind === 'human_decision'`; otherwise preserve current author/time/Markdown HTML exactly. The helper's detail button calls `root.humanDecisionCenter.open({decisionId})`.

Add locale keys `proj_human_decision_comment`, `proj_human_decision_result`, `proj_human_decision_custom`, and `proj_human_decision_view_detail` in both locales.

- [ ] **Step 4: Run UI and project-panel regressions**

Run: `node tests/check_project_human_decision_comment.mjs && node tests/check_project_polling_preserves_detail.mjs && node tests/check_project_workflow_chat_stability.mjs && python -m json.tool app/locales/en.json >/dev/null && python -m json.tool app/locales/zh.json >/dev/null`

Expected: all commands exit 0.

- [ ] **Step 5: Commit project comment UI**

```bash
git add app/project-human-decision-comment-ui.js app/index.html app/projects.js app/style.css app/locales/en.json app/locales/zh.json tests/check_project_human_decision_comment.mjs
git commit -m "feat: render project decision system comments"
```

### Task 4: Project regression and real acceptance

**Files:**
- Modify only if a defect is found: files owned by Tasks 1-3 and their tests.
- Evidence: `log/project-human-decision-acceptance-2026-08-08.md`

**Interfaces:**
- Consumes: local VO service, real configured project executor, task Human Decision skill flow.
- Produces: evidence with project ID, task ID, attempt ID, decision ID, comment ID, retry count, and resumed execution result.

- [ ] **Step 1: Run focused and broad project regressions**

Run: `pytest -q tests/test_project_human_decision_comment.py tests/test_project_human_decision_continuation.py tests/test_project_repository.py tests/test_project_execution_prompt_formatting.py tests/test_project_execution.py && node tests/check_project_human_decision_comment.mjs`

Expected: all tests PASS.

- [ ] **Step 2: Create and start a substantive real project task**

Using the real VO project UI/API, create a project with a task whose executor must choose between materially different rollout strategies without pre-authorization. Start the task through the normal project execution path and record project, task, and attempt IDs.

- [ ] **Step 3: Trigger and resolve the real task decision**

Wait for the attempt to enter `awaiting_user_decision`, then resolve the generated decision through the Human Decision Center. Do not call the comment endpoint manually.

- [ ] **Step 4: Verify one task comment and original-attempt resume**

Reload the project through its normal API and confirm the bound task has exactly one `kind=human_decision` comment for the decision ID. Open task detail and verify the localized system comment and detail action. Confirm the same attempt resumes with `decisionResume.answer` and sibling tasks remain unchanged.

- [ ] **Step 5: Record evidence and commit any stable acceptance fixture**

```bash
git add log/project-human-decision-acceptance-2026-08-08.md
git commit -m "test: verify real project decision task resume"
```
