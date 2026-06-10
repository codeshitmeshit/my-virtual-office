# 通用项目执行 Universal Project Execution Review

## Review conclusion

Reviewed with no blocking product or technical questions. The clarified scope is implementable on the existing markdown-backed project store and provider chat bridges, but the current workflow pipeline must be refactored rather than incrementally relabeled.

The delivery is split into 执行底座 and 独立审查与最终验收 with separate test and user-confirmation gates. 独立审查与最终验收 depends on the persisted attempt and evidence contract delivered by 执行底座.

## Delivery sequence

### 执行底座: Universal project execution foundation

执行底座 owns project/task schema migration, workspace validation, role configuration, explicit task start, provider-neutral executor dispatch, evidence collection, cancellation/failure behavior, state persistence, and recovery. Reviewer identity is resolved and validated, but no Reviewer provider call is made.

After successful execution, the task enters `execution_complete`. This is an intentional intermediate state, not completion: generic updates, drag/drop, legacy auto-mode, and old self-review logic must not move it to Done.

### 独立审查与最终验收: Independent review and final acceptance

独立审查与最终验收 consumes the immutable 执行底座 attempt/evidence record. It adds the read-only Reviewer packet, structured review schema, rework loop, three-cycle cap, blocked escalation, final acceptance UI, and guarded user actions.

独立审查与最终验收 must not redefine the 执行底座 execution contract. If implementation requires changing persisted attempt or evidence semantics after 执行底座 acceptance, the affected 执行底座 checks must be rerun and reconfirmed.

## Current-state findings

1. `app/project_store.py` is the canonical persisted project/task store and already supports legacy JSON migration, but it does not persist workspace bindings, default executor/reviewer settings, attempt history, evidence bundles, or user acceptance records.
2. `app/server.py` dispatches work to OpenClaw, Hermes, and Codex, but `_wf_run_pipeline_inner` uses the task executor as its reviewer.
3. The current workflow may auto-pass a task with no checklist and may move a reviewer-approved task directly to Done. Both conflict with 通用项目执行.
4. Workflow start selects the next backlog task and supports auto-mode. 通用项目执行 requires an explicitly selected task and one active task per project.
5. Current stop/failure paths do not consistently preserve a normalized task attempt and evidence record.
6. Existing workflow state is partly in memory and partly in `workflow-state.json`; project/task state must become the durable source of truth for acceptance and recovery.

## Proposed technical shape

### Canonical project fields

Add backward-compatible project fields:

- `workspacePath`: canonical real path selected by the user.
- `workspaceKind`: `git` or `directory`.
- `workspaceStatus`: normalized validation result and last validation time.
- `defaultExecutorAgentId` and `defaultReviewerAgentId`.
- `executionPolicy`: single-task execution and dirty-worktree confirmation policy.

Paths must be normalized with realpath semantics. Execution must reject missing paths, non-directories, inaccessible directories, and paths outside configured project roots when an allowlist is configured. API responses should avoid exposing unrelated directory contents.

### Canonical task fields

Add task fields with migration defaults:

- `executorAgentId` and `reviewerAgentId` overrides;
- `executionState` independent from display column names;
- `activeAttemptId`, `attempts`, and `reworkCount`;
- `reviewResult`, `acceptanceStatus`, and `acceptanceHistory`;
- `blockedReason` and `lastError`.

Column titles remain presentation metadata. State transitions must use `executionState`, not English column-name matching.

### Execution attempts and evidence

Each start creates an immutable attempt identity recording resolved executor, reviewer, workspace, dirty-worktree confirmation, timestamps, terminal status, provider references, summaries, and evidence.

The Office runtime collects a bounded evidence bundle:

- baseline and final Git state when the workspace is a repository;
- changed-file names and diff/stat summaries;
- executor-reported and runtime-observed test commands/results;
- task checklist and execution summary;
- normalized activity references rather than copied unrestricted raw logs;
- truncation markers when evidence is bounded.

Sensitive values must use the existing activity redaction strategy before persistence or display.

### Reviewer isolation

The reviewer must not receive a normal writable project execution session. The Office runtime generates a read-only evidence packet and sends that packet to the reviewer through the provider adapter. The reviewer returns structured JSON that is schema-validated before state transition.

This design enforces the 通用项目执行 read-only rule without depending on OpenClaw, Hermes, or Codex having equivalent native filesystem sandbox controls. A reviewer response cannot directly mutate task state except through the validated review result handler.

### State machine

Use explicit guarded transitions:

- `backlog -> validating -> executing`
- 执行底座: `executing -> execution_complete | blocked`
- 独立审查与最终验收: `execution_complete -> reviewing | blocked`
- `reviewing -> reworking | awaiting_user_acceptance | blocked`
- `reworking -> reviewing | blocked`
- `awaiting_user_acceptance -> done | reworking | blocked`
- `blocked -> backlog | executing` only through an explicit user recovery action

The fourth failed reviewer result is not dispatched for automatic rework: after three completed rework cycles, the task becomes blocked.

### User acceptance

Reviewer pass creates an acceptance packet and transitions to `awaiting_user_acceptance`. Only the dedicated acceptance endpoint may transition to Done. Generic task updates and drag/drop must reject or neutralize attempts to bypass this guard.

`reject_and_rework` requires non-empty user feedback, increments acceptance history, sends the task back to the same executor by default, and invalidates the prior reviewer pass. `mark_blocked` records a reason and stops the run.

### Dirty worktree handling

For Git workspaces, start performs a fresh status check. A dirty tree returns a confirmation-required response containing a bounded summary. Confirmation is scoped to the project, task, current dirty-state fingerprint, and one start attempt; it cannot be reused after the worktree changes.

Non-Git directories do not have a dirty-state gate but still require path validation.

### Recovery and concurrency

A per-project lock and persisted active attempt enforce one running task. On service restart, nonterminal attempts are reconciled conservatively: a run that cannot be proven active becomes blocked rather than silently resumed or marked done.

Provider-native sessions are references attached to attempts, not the canonical state. Cancellation targets only the active provider operation and preserves the evidence captured before and after cancellation.

## API impact

The existing project/task CRUD APIs remain backward compatible. 通用项目执行 requires explicit operations for:

- workspace validation and project binding;
- starting one specified task with optional dirty-state confirmation;
- status/evidence retrieval;
- cancellation;
- user acceptance, rejection for rework, blocking, and recovery.

Exact route names may follow existing `/api/projects/{projectId}/...` conventions. All state-changing operations require project/task/attempt identity and reject stale attempts.

## UI impact

- Project settings expose workspace, default executor, and default reviewer.
- Task settings expose optional role overrides and reject identical resolved agents.
- Workflow start is task-specific; auto-mode is hidden or disabled for 通用项目执行 projects.
- The board displays explicit executing, reviewing, reworking, blocked, and awaiting-user states without relying only on columns.
- The acceptance view displays the required evidence and only the three confirmed user actions.

## Compatibility and migration

- Existing projects load with null workspace/default roles and are marked configuration-required before execution.
- Existing `assignee` maps to the task executor until explicitly migrated.
- Existing review fields remain readable but do not count as 通用项目执行 acceptance.
- Existing completed tasks remain completed; migration must not reopen historical Done tasks.
- Existing project CRUD, templates, reports, scores, OpenClaw/Hermes chat, and Codex live bridge/6 Codex flows require regression coverage.

## Security and privacy

- Canonicalize and validate paths; prevent traversal and symlink escapes from configured roots.
- Do not expose arbitrary filesystem browsing through project APIs.
- Bound and redact diffs, command output, activity, and reviewer packets.
- Do not treat reviewer text as trusted state-transition instructions.
- Ensure only explicit human-facing acceptance operations can mark a 通用项目执行 task Done.

## Observability

Every transition records project, task, attempt, actor, previous state, next state, timestamp, and reason. Provider calls record normalized provider/agent references, duration, terminal category, and correlation identifiers without credentials or unrestricted raw payloads.

## Test strategy

- Unit tests for migration, path validation, state guards, role resolution, evidence bounds/redaction, review schema, and dirty-state fingerprints.
- Server/API tests for start, conflict, cancel, restart reconciliation, reviewer/rework loops, and user acceptance.
- Provider matrix tests for OpenClaw, Hermes, and Codex as executor and reviewer using controlled fakes, plus selected real-provider smoke tests.
- Browser acceptance for project setup, task start, evidence display, reviewer outcomes, rework, blocking, refresh, and final acceptance.
- 执行底座 and 独立审查与最终验收 each require their own automated regression result and browser confirmation record; 独立审查与最终验收 completion does not retroactively replace the 执行底座 acceptance record.

## Risks and mitigations

- Large repositories can produce excessive evidence: use bounded summaries and truncation markers.
- Provider responses may not follow review schema: validate strictly and block after controlled retry rather than infer approval.
- Existing column-driven workflow behavior may bypass state guards: centralize transitions and test every mutation route.
- Dirty worktrees can contain user changes unrelated to the task: require a fresh fingerprinted confirmation and never claim rollback.

## Deferred work

- Per-project parallel execution, isolated worktrees, branch ownership, conflict handling, and merge policy belong to a later phase.
- Office-owned scheduling and universal automations belong to a later phase built on the 通用项目执行 task execution contract.
