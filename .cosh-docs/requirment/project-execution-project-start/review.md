# Project Execution Project Start Review

## Review Conclusion

Reviewed with no blocking product questions after the follow-up product clarification. The user expectation is valid: once executable projects are the default, hiding the project-level start button makes the project feel inert. The recommended solution is to add a Project Execution-specific project-level start coordinator with a toolbar start-mode radio control.

The toolbar should let users choose between starting only the next task and continuously starting tasks. Continuous task flow should be the default, but it must still respect task-level review and manual acceptance boundaries.

## Product Review

The requirement is coherent because it resolves a mismatch between default project creation and visible controls:

- Default projects are now executable.
- Users expect a project-level action after creating a project.
- The current "start this task" control is hidden inside task details and is discoverability-poor.
- A toolbar-level start control restores the previous mental model while still using Project Execution semantics.
- A start-mode radio control resolves the ambiguity between "启动第一个任务" and "启动项目": the user can see that project start is either next-task start or continuous task flow.
- Task-level manual acceptance configuration is necessary because continuous flow needs a clear product-level stop condition.

No further product clarification is required before checklist confirmation.

## Technical Review

### Project-Level Start Semantics

Project Execution currently starts by task ID. The project-level start should not introduce a second execution engine. It should:

1. Inspect the project.
2. Find the next eligible task.
3. Call or share logic with the existing task-level Project Execution start handler.
4. Return the selected task ID and attempt ID.

This keeps state transitions, dirty-worktree confirmation, role validation, active-task locking, cancellation, evidence capture, reviewer handoff, and acceptance behavior in one execution path.

### Project Start Mode

The project toolbar should expose a radio group near the project start button:

- Start next task: select and start one eligible task.
- Continuous task flow: default; continue selecting the next eligible task after a task passes review, unless the task requires manual user acceptance or a blocking state occurs.

This mode is Project Execution-specific and must not be wired to the legacy workflow `autoMode` semantics for normal projects.

### Task Selection

Selection must be deterministic. The safest first version is:

- Sort columns by `order`.
- Sort tasks in each column by `order`.
- Ignore Done-like columns.
- Pick the first task whose execution state is startable.

Done-like columns should reuse existing Done detection semantics where possible.

For continuous task flow, each next task selection should re-run the same deterministic eligibility rule after the previous task reaches an auto-continuable state.

### Manual Acceptance Stop Point

Task creation and the task/control panel should expose whether the task requires manual user acceptance. When review passes:

- If the task requires manual acceptance, the project should enter a clear waiting-for-user-acceptance state.
- If the task does not require manual acceptance and the selected project start mode is continuous task flow, the coordinator can continue to the next eligible task.

This keeps continuous flow useful without automatically accepting tasks that the user explicitly marked as requiring manual acceptance.

### API Shape

The backend should expose a project-scoped endpoint or handler for Project Execution project start. Exact route can follow current conventions, for example:

- `POST /api/projects/{projectId}/project-execution/start`

The response should include:

- selected `taskId`
- `attemptId` when execution starts
- selected start mode
- whether the selected task requires manual acceptance
- selected task title if useful
- existing dirty-worktree confirmation payload when applicable
- clear error messages for no task, missing roles, invalid workspace, or active task conflict

### Frontend Behavior

For Project Execution projects, toolbar should show:

- A project start mode radio group: "启动下一个任务" and "连续启动任务".
- Start project button when no active task is running.
- Stop/current state control when a task is active if existing cancellation support can map to the active task.
- Existing artifact/report/edit/template controls unchanged.
- A control-panel marker showing whether the active or selected task requires manual user acceptance.

The button label can be "启动项目" but should map internally to next eligible task start. If no task exists, the UI should tell the user to add a task first.

### Role Validation

A project-level start will likely surface missing executor/reviewer more often because the user may not open task detail first. The API should reuse existing role resolution:

- task executor override
- task assignee
- project default executor
- project default reviewer

If missing, return the same clear errors as task start.

### Dirty Worktree Confirmation

The existing task start action handles dirty git worktree confirmation by returning `confirmationRequired` and a fingerprint. Project-level start must preserve that behavior. If confirmation is required, the frontend should ask the same confirmation and retry project-level start with the selected task and fingerprint or call the selected task start with the fingerprint.

For continuous task flow, dirty-worktree confirmation must be scoped to the selected task/start attempt. The coordinator should not silently continue to another task when a confirmation fingerprint was produced for a different selected task.

### Compatibility

Normal project workflow must remain unchanged. Project Execution task-detail start must remain available. Existing tests for task start, active task conflict, dirty confirmation, review, acceptance, and artifacts should continue to pass. Existing default executable project creation and auto workspace behavior must continue to work.

### Risks

1. Ambiguous "start project" expectations: users may expect the whole project to run to completion automatically. Mitigate with explicit "启动下一个任务" versus "连续启动任务" radio copy and visible acceptance stop states.
2. Incorrect task selection: deterministic column/order selection must be tested.
3. Duplicate start paths: project-level start must share existing task start logic rather than duplicating state transitions.
4. Dirty confirmation mismatch: retry must target the same selected task or re-evaluate safely.
5. Continuous-flow runaway: must stop at missing roles, active conflict, dirty confirmation, failed review, blocked state, error, no eligible task, and tasks requiring manual acceptance.

## Test Strategy

Testing should cover:

- Project Execution project toolbar shows project-level start.
- Project Execution project toolbar shows start mode radio control and defaults to continuous task flow.
- Normal project toolbar still shows old workflow controls.
- Project-level start selects the first eligible task by column/order.
- Start-next-task mode only starts one selected task.
- Continuous task flow advances to the next eligible task after review pass for tasks not requiring manual acceptance.
- Continuous task flow stops when a task requires manual acceptance and shows the waiting state.
- Task creation and task/control panel expose manual acceptance configuration.
- Done-column tasks are skipped.
- Active task conflict returns a clear error.
- No eligible task returns a clear error.
- Missing executor/reviewer returns existing role errors.
- Dirty worktree confirmation still works.
- Existing task-level Project Execution start still works.
- Existing Project Execution review and acceptance flows still work.

## Non-Blocking Follow-Ups

- Add a "continue project" mode after user acceptance to advance to the next task.
- Add explicit queue preview in the project toolbar.
- Add policy settings for eligible columns or priorities.
- Add better onboarding copy explaining that Project Execution runs one task at a time.
