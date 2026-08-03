# Human Decision Meeting and Project Resume Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Automatically resume the original VO meeting or project task branch after a human decision is resolved, without pausing unrelated project tasks or treating meeting/project work as ordinary chat.

**Architecture:** Generalize the existing durable continuation record so it can dispatch by source kind while preserving chat compatibility. Add focused meeting and project adapters: the meeting adapter drives the existing `continue_decision` transition, while the project adapter marks an active attempt/session as awaiting a decision and resubmits only that task through the existing runner/dispatcher. `app/server.py` remains dependency wiring and thin callbacks.

**Tech Stack:** Python 3, JSON file-backed repositories, pytest, VO XML prompt formatter, existing meeting lifecycle, project execution runner, bounded project dispatcher, Dashboard SSE.

## Global Constraints

- All provider-visible prompts use XML as their outer structure and are assembled through `services.bridge_input_output_formatting` / `business_prompt_bridge`.
- Dynamic decision answers and source content are untrusted data and cannot replace trusted instructions.
- New business logic lives in focused modules; `app/server.py` only wires ports and delegates.
- Reuse `HumanDecisionStore`, `meeting_lifecycle.transition_command`, `execution_lifecycle.run_attempt`, and `BoundedProjectExecutionDispatcher`; do not create duplicate state authorities or execution engines.
- Only the affected meeting/task branch pauses. Sibling project tasks continue.
- Preserve first-terminal-write wins, retry/lease semantics, page-independent execution, and Dashboard's existing SSE channel.
- Preserve the dirty worktree and do not modify unrelated changes.

---

### Task 1: General continuation bindings and source context

**Files:**
- Modify: `app/services/human_decisions.py`
- Modify: `app/services/human_decision_chat_continuation.py`
- Test: `tests/test_human_decisions.py`
- Test: `tests/test_human_decision_chat_continuation.py`

**Interfaces:**
- Produces: `HumanDecisionContinuationClaim.kind: str` and `binding: dict[str, Any]` while retaining `agent_id` and `conversation_id` properties for chat callers.
- Produces: `HumanDecisionStore.bind_continuation(decision_id, *, kind, agent_id, binding)` and generic queue/claim/complete/retry/fail/uncertain methods.
- Preserves: every existing `*_chat_continuation` method as a thin compatibility delegate.

- [ ] **Step 1: Write failing Store tests**

Add tests proving a task source preserves `projectId`, binds only matching `projectId/taskId`, exposes only the safe continuation summary, and returns a claim with literal `kind="task"` and private binding values. Add a meeting binding mismatch test.

```python
created = store.create(request_payload(source={
    "type": "task", "id": "task-1", "projectId": "project-1", "label": "Task 1",
}))
decision_id = created["decision"]["id"]
store.bind_continuation(
    decision_id,
    kind="task",
    agent_id="agent-1",
    binding={"projectId": "project-1", "taskId": "task-1", "attemptId": "attempt-1"},
)
store.resolve(decision_id, option_id="A")
store.queue_continuation(decision_id)
claim = store.claim_due_continuations()[0]
assert claim.kind == "task"
assert claim.binding == {"projectId": "project-1", "taskId": "task-1", "attemptId": "attempt-1"}
assert "binding" not in store.snapshot()["decisions"][0]["continuation"]
```

- [ ] **Step 2: Run tests and verify RED**

Run: `pytest -q tests/test_human_decisions.py tests/test_human_decision_chat_continuation.py`

Expected: FAIL because generic binding methods and claim fields do not exist and `projectId` is dropped.

- [ ] **Step 3: Implement generic continuation persistence**

Extend source normalization with `projectId` only for `task`. Store continuation targets under a private `binding` map and validate by kind:

```python
@dataclass(frozen=True)
class HumanDecisionContinuationClaim:
    decision_id: str
    claim_token: str
    kind: str
    agent_id: str
    binding: JsonDict
    attempts: int
    decision: JsonDict

    @property
    def conversation_id(self) -> str:
        return str(self.binding.get("conversationId") or "")
```

Rename internal transitions to generic forms. Keep chat methods delegating to them, so existing chat tests and server wiring do not change behavior.

- [ ] **Step 4: Run tests and verify GREEN**

Run: `pytest -q tests/test_human_decisions.py tests/test_human_decision_chat_continuation.py`

Expected: all selected tests pass.

- [ ] **Step 5: Commit**

```bash
git add app/services/human_decisions.py app/services/human_decision_chat_continuation.py tests/test_human_decisions.py tests/test_human_decision_chat_continuation.py
git commit -m "refactor: generalize human decision continuations"
```

### Task 2: Native meeting continuation adapter

**Files:**
- Create: `app/services/human_decision_meeting_continuation.py`
- Test: `tests/test_human_decision_meeting_continuation.py`

**Interfaces:**
- Consumes: generic `HumanDecisionContinuationClaim`.
- Produces: `MeetingContinuationPorts(load, transition, wake)` and `HumanDecisionMeetingContinuation.dispatch(claim) -> ContinuationDispatchResult`.
- Calls: injected transition with action `continue_decision`, reason containing decision ID, normalized decision answer, and idempotency key `human-decision-resume:{decisionId}`.

- [ ] **Step 1: Write failing meeting adapter tests**

Test real adapter behavior with in-memory port fakes: awaiting meeting transitions once and wakes once; replay reports dispatched without a second wake; terminal or mismatched decision returns `failed`; temporary busy returns `not_dispatched_retryable`.

```python
result = adapter.dispatch(claim)
assert result.outcome == "dispatched"
assert state["stage"] == "active_discussion"
assert state["resumeDecision"]["answer"] == "Approve staged rollout"
assert wakes == ["meeting-1"]
```

- [ ] **Step 2: Run tests and verify RED**

Run: `pytest -q tests/test_human_decision_meeting_continuation.py`

Expected: collection fails because the adapter module does not exist.

- [ ] **Step 3: Implement the focused adapter**

Construct an XML resume context through the shared formatter. Validate `source.id`, bound `meetingId`, decision marker, and stage before transition. Classify errors before transition as retryable/failed; exceptions after a possibly committed transition are uncertain.

```python
@dataclass(frozen=True)
class MeetingContinuationPorts:
    load: Callable[[str], Mapping[str, Any] | None]
    transition: Callable[[str, Mapping[str, Any]], Mapping[str, Any]]
    wake: Callable[[str, str], Mapping[str, Any]]
```

- [ ] **Step 4: Run tests and verify GREEN**

Run: `pytest -q tests/test_human_decision_meeting_continuation.py`

Expected: all tests pass.

- [ ] **Step 5: Commit**

```bash
git add app/services/human_decision_meeting_continuation.py tests/test_human_decision_meeting_continuation.py
git commit -m "feat: resume meetings after human decisions"
```

### Task 3: Project attempt wait and single-task resume adapter

**Files:**
- Create: `app/services/project_human_decision_continuation.py`
- Modify: `app/services/execution_lifecycle.py`
- Modify: `app/services/project_execution_prompt_formatting.py`
- Test: `tests/test_project_human_decision_continuation.py`
- Test: `tests/test_execution_lifecycle.py`
- Test: `tests/test_project_execution_prompt_formatting.py`

**Interfaces:**
- Produces: `ProjectDecisionBinding(project_id, task_id, attempt_id, run_id, mode)`.
- Produces: `mark_attempt_waiting(repository, binding, decision_id, now) -> ServiceResult`.
- Produces: `ProjectHumanDecisionContinuation.dispatch(claim) -> ContinuationDispatchResult` using injected repository, cancel registry, direct launcher, and stage dispatcher.
- Extends: `RunnerPorts.pending_human_decision(project_id, task_id, attempt_id, agent_id) -> dict | None` with a safe default returning `None`.

- [ ] **Step 1: Write failing execution interception tests**

Add a runner test where Provider returns success but `pending_human_decision` returns a matching decision. Assert attempt becomes `awaiting_user_decision`, retains `activeAttemptId`, does not call review/reconcile, and sibling tasks remain unchanged.

```python
run_attempt("project-1", "task-a", "attempt-a", Event(), ports=ports)
saved_task = repository.get("project-1")["tasks"][0]
assert saved_task["activeAttemptId"] == "attempt-a"
assert saved_task["attempts"][0]["status"] == "awaiting_user_decision"
assert review_calls == []
```

- [ ] **Step 2: Run interception test and verify RED**

Run: `pytest -q tests/test_execution_lifecycle.py -k human_decision`

Expected: FAIL because `RunnerPorts` has no decision interception and runner finalizes the task.

- [ ] **Step 3: Implement the minimal runner interception**

Immediately after Provider returns and before normal evidence/finalization, query the injected port. Persist the wait marker atomically against the active attempt, clear only the runner claim/cancel registration, and return. Do not make awaiting a terminal stage state.

- [ ] **Step 4: Write failing project adapter tests**

Cover direct and stage modes. Direct mode launches the existing attempt runner once; stage mode submits only `task-a` with the same attempt ID/run ID while `task-b` remains running. Replays are idempotent. Replaced/cancelled attempts fail without dispatch.

```python
result = adapter.dispatch(claim)
assert result.outcome == "dispatched"
assert submitted == [{"projectId": "project-1", "taskId": "task-a", "attemptId": "attempt-a"}]
assert repository.get("project-1")["tasks"][1]["activeAttemptId"] == "attempt-b"
```

- [ ] **Step 5: Run adapter tests and verify RED**

Run: `pytest -q tests/test_project_human_decision_continuation.py tests/test_project_execution_prompt_formatting.py -k decision`

Expected: FAIL because the project adapter and resume prompt section do not exist.

- [ ] **Step 6: Implement single-task resume and XML context**

Atomically verify and change the matching attempt from `awaiting_user_decision` back to `executing`, store a bounded `decisionResume` data object, and clear `runnerClaimedAt` before dispatch. `render_project_execution_prompt` renders this object under `<human_decision_resume>` with trusted resume rules and untrusted JSON data. The adapter reuses the existing attempt and never calls stage reservation or project-level resume.

- [ ] **Step 7: Run tests and verify GREEN**

Run: `pytest -q tests/test_execution_lifecycle.py tests/test_project_human_decision_continuation.py tests/test_project_execution_prompt_formatting.py`

Expected: all selected tests pass.

- [ ] **Step 8: Commit**

```bash
git add app/services/project_human_decision_continuation.py app/services/execution_lifecycle.py app/services/project_execution_prompt_formatting.py tests/test_project_human_decision_continuation.py tests/test_execution_lifecycle.py tests/test_project_execution_prompt_formatting.py
git commit -m "feat: resume project task attempts after decisions"
```

### Task 4: Legacy project workflow wait and resume

**Files:**
- Create: `app/services/project_workflow_human_decision.py`
- Modify: `app/server.py` (thin calls only around `_wf_run_pipeline_inner`)
- Modify: `app/services/workflow_prompt_formatting.py`
- Test: `tests/test_project_workflow_human_decision.py`
- Test: `tests/test_workflow_prompt_formatting.py`

**Interfaces:**
- Produces: `mark_workflow_waiting(project, task_id, decision_id, agent_id, now)` and `prepare_workflow_resume(project, task_id, decision) -> WorkflowResume`.
- Produces: `WorkflowResume(project_id, task_id, agent_id, session_key, phase, prompt)`.
- Uses: existing `_wf_call_agent` stable task session and a thin server launcher callback.

- [ ] **Step 1: Write failing workflow state tests**

Test that a pending decision after executor response leaves the task In Progress, stores `workflowPhase=awaiting_user_decision`, and does not invoke Review. Test resolution reuses the same session key and records the answer in an XML resume prompt.

- [ ] **Step 2: Run tests and verify RED**

Run: `pytest -q tests/test_project_workflow_human_decision.py tests/test_workflow_prompt_formatting.py -k decision`

Expected: FAIL because the workflow decision module and resume formatting do not exist.

- [ ] **Step 3: Implement workflow state helper and thin integration**

Keep phase parsing and Prompt creation in the new module. In `_wf_run_pipeline_inner`, call a small injected/global decision lookup immediately after `_wf_call_agent`; if waiting, persist and return before moving to Review. Resolution launches a focused continuation that reuses `_wf_task_session_key` and then enters the existing review path through an extracted thin continuation helper.

- [ ] **Step 4: Run tests and verify GREEN**

Run: `pytest -q tests/test_project_workflow_human_decision.py tests/test_workflow_prompt_formatting.py`

Expected: all selected tests pass.

- [ ] **Step 5: Commit**

```bash
git add app/services/project_workflow_human_decision.py app/services/workflow_prompt_formatting.py app/server.py tests/test_project_workflow_human_decision.py tests/test_workflow_prompt_formatting.py
git commit -m "feat: resume legacy project workflow decisions"
```

### Task 5: Generic dispatcher, creation binding, and native wiring

**Files:**
- Create: `app/services/human_decision_continuation_dispatch.py`
- Modify: `app/services/human_decision_workflow.py`
- Modify: `app/server.py` (dependency wiring and thin callbacks only)
- Test: `tests/test_human_decision_continuation_dispatch.py`
- Test: `tests/test_human_decision_workflow.py`
- Test: `tests/test_human_decision_server_wiring.py`

**Interfaces:**
- Produces: `HumanDecisionContinuationDispatcher(adapters: Mapping[str, ContinuationAdapter])` with `queue(decision_id)` and `process_due(now=None)`.
- Changes: `HumanDecisionWorkflow` accepts `continuation` instead of chat-specific continuation, while retaining constructor compatibility during migration.
- Server binding callbacks validate meeting participant/current phase or project/task/current executor and return private binding data.

- [ ] **Step 1: Write failing dispatcher and workflow tests**

Test that chat/meeting/task claims reach only the matching adapter; first resolve and timeout resolve queue all bound kinds; duplicate terminal callbacks do not dispatch twice; unbound decisions remain resolvable without automatic continuation.

- [ ] **Step 2: Run tests and verify RED**

Run: `pytest -q tests/test_human_decision_continuation_dispatch.py tests/test_human_decision_workflow.py tests/test_human_decision_server_wiring.py`

Expected: FAIL because only chat continuation is queued and processed.

- [ ] **Step 3: Implement dispatcher and thin server wiring**

Move shared retry classification from `HumanDecisionChatContinuation.process_due` into the generic dispatcher. Chat becomes one adapter. Bind on create using trusted `X-VO-Agent-Id` plus repository state; never trust client-provided attempt/version. Wire meeting transition/wake and project direct/stage/workflow launch callbacks without importing server globals into service modules.

- [ ] **Step 4: Run tests and verify GREEN**

Run: `pytest -q tests/test_human_decision_continuation_dispatch.py tests/test_human_decision_workflow.py tests/test_human_decision_server_wiring.py tests/test_human_decision_chat_continuation.py`

Expected: all selected tests pass.

- [ ] **Step 5: Commit**

```bash
git add app/services/human_decision_continuation_dispatch.py app/services/human_decision_workflow.py app/server.py tests/test_human_decision_continuation_dispatch.py tests/test_human_decision_workflow.py tests/test_human_decision_server_wiring.py
git commit -m "feat: dispatch resolved decisions to native lifecycles"
```

### Task 6: Skill contract, integration regression, and OpenSpec evidence

**Files:**
- Modify: `skills/vo-human-decision/SKILL.md`
- Modify: `tests/test_human_decision_skill.py`
- Modify: `tests/test_human_decision_http_e2e.py`
- Modify: `openspec/changes/add-decision-request-ui-prototype/tasks.md`
- Modify: `openspec/changes/add-decision-request-ui-prototype/specs/human-decision-center/spec.md` (or the existing owning delta spec path)

**Interfaces:**
- Skill behavior: all three source kinds end the affected turn after creation; backend resumes; task source includes `projectId`.
- Integration behavior: local/Feishu resolve update the same state and wake the native source once.

- [ ] **Step 1: Write failing behavior/integration tests**

Add a fixture with one awaiting meeting and one stage project containing two active tasks. Resolve decisions over HTTP and assert the meeting continues, only the selected task resumes, and snapshots/SSE show the new status. Pressure-test the Skill through its parsed contract rather than asserting an incidental sentence.

- [ ] **Step 2: Run tests and verify RED**

Run: `pytest -q tests/test_human_decision_http_e2e.py tests/test_human_decision_skill.py`

Expected: FAIL because meeting/task native auto-resume is not yet exposed end-to-end and the Skill still tells them to poll.

- [ ] **Step 3: Update Skill and OpenSpec**

Document the source IDs, backend wake behavior, no-poll contract, and `execution-started` boundary. Record implemented scenarios and test evidence in the existing OpenSpec change without creating another competing change.

- [ ] **Step 4: Run focused and regression verification**

Run:

```bash
pytest -q \
  tests/test_human_decisions.py \
  tests/test_human_decision_chat_continuation.py \
  tests/test_human_decision_meeting_continuation.py \
  tests/test_project_human_decision_continuation.py \
  tests/test_project_workflow_human_decision.py \
  tests/test_human_decision_continuation_dispatch.py \
  tests/test_human_decision_workflow.py \
  tests/test_human_decision_http_e2e.py \
  tests/test_meeting_lifecycle_service.py \
  tests/test_execution_lifecycle.py \
  tests/test_project_stage_dispatch.py \
  tests/test_project_execution_prompt_formatting.py \
  tests/test_workflow_prompt_formatting.py
node tests/check_human_decision_center.mjs
node tests/check_dashboard_realtime_static.mjs
openspec validate add-decision-request-ui-prototype --strict
git diff --check
```

Expected: every command exits 0. If full `pytest -q` is run, separately report any already-characterized collection blocker rather than claiming a clean full suite.

- [ ] **Step 5: Commit**

```bash
git add skills/vo-human-decision/SKILL.md tests/test_human_decision_skill.py tests/test_human_decision_http_e2e.py openspec/changes/add-decision-request-ui-prototype
git commit -m "docs: finalize native human decision resume"
```

## Self-Review

- Spec coverage: generic durable continuation, meeting native transition, project single-task wait/resume, legacy workflow, XML/security, retries/restart, SSE reuse, Skill no-poll behavior, and regression evidence all map to Tasks 1-6.
- Placeholder scan: no deferred implementation markers or unspecified implementation step remains.
- Type consistency: Tasks 2-5 all consume `HumanDecisionContinuationClaim` and return the existing `ContinuationDispatchResult`; task binding keys are consistently `projectId`, `taskId`, `attemptId`, `runId`, and `mode`.
- Mutation coverage: tests fail for wrong kind dispatch, wrong meeting stage, replaced attempt, lost active attempt, sibling task dispatch, duplicate wake, unescaped answer, and premature Review/stage reconciliation.
