# Project Execution State Machine Columns Review

## Product Review

The product direction is coherent and addresses the observed confusion. The current Project Execution behavior presents board columns as if they are a state machine, but only the internal `executionState` changes for most transitions. Users therefore see a mismatch between what the card says and where it is placed.

The clarified product model is strong:

- Project Execution projects use columns as state-machine lanes.
- Ordinary projects keep flexible board semantics.
- AI reviewer pass is sufficient for Done by default.
- Human acceptance is optional and only creates `awaiting_user_acceptance` when enabled.

No additional product clarification is blocking this requirement.

## Technical Review

### Relevant Areas

- Project Execution state transitions in `app/server.py`.
- Board column helpers such as `_wf_get_backlog_col`, `_wf_get_inprogress_col`, `_wf_get_review_col`, and `_wf_get_done_col`.
- Task move/update/reorder handlers that enforce manual movement rules.
- Project board rendering and toolbar state in `app/projects.js`.
- Project persistence through the markdown project store.
- Focused tests in `tests/test_project_execution.py`.

### State Flow Assessment

The main technical gap is that `_project_execution_transition()` currently updates `executionState` and history but does not synchronize `columnId`. `_project_execution_mark_done()` is the main path that explicitly moves a task to the Done column. That explains why tasks can remain in Backlog while active or awaiting review.

The fix should avoid duplicating state logic in many handlers. A conservative approach is to define a Project Execution state-to-column synchronization helper and call it from transition paths. Done handling can continue to use existing Done logic, but it should be consistent with the helper contract.

### Compatibility

The change must be scoped to projects where Project Execution is enabled. Ordinary projects and legacy workflow behavior must remain unchanged.

Existing data may already contain Project Execution tasks with mismatched `executionState` and `columnId`. The implementation should normalize these tasks when touched by status calls or transitions, or at least avoid creating new mismatches. A broad migration is not required for the first fix unless tests reveal stale real data creates visible regressions.

### Manual Movement Rules

Manual task move and reorder restrictions already exist around some Project Execution states. They need review against the clarified contract:

- Invalid direct move to Done should remain blocked.
- Moving active/reviewing Project Execution tasks should be blocked unless it is a system transition.
- Ordinary project movement should remain unchanged.

### Observability And Audit

History entries should continue recording state transitions. Completion should remain auditable with actor and reason, including:

- AI reviewer pass.
- Skipped review confirmation.
- Human acceptance after manual acceptance mode.

### Risks

- A helper that moves columns on every transition may accidentally move tasks in ordinary projects if not gated by Project Execution.
- Continuous project flow may depend on task eligibility based on `executionState`; column movement should not cause completed tasks or review tasks to be selected again.
- Skipped-review behavior needs careful testing because it has both safety and completion semantics.
- UI labels may still mention awaiting user acceptance even when manual acceptance is disabled; copy and state display should be checked during implementation.

## Review Conclusion

No blocking product or technical questions remain. Proceed to checklist confirmation before implementation planning.

