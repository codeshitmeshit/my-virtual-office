# Project Execution State Machine Columns Todolist

## TODO-001 Define Project Execution column sync contract

- 目标：Create a single, auditable mapping between Project Execution states and board columns.
- 涉及区域：`app/server.py` Project Execution helpers and transition functions.
- 输入：Confirmed requirement state table; existing `_wf_get_inprogress_col`, `_wf_get_review_col`, `_wf_get_done_col`; existing `_project_execution_transition`.
- 输出：A reusable helper or equivalent centralized logic that maps execution states to expected columns only for Project Execution projects.
- 依赖：None.
- 完成标准：State-to-column behavior is centralized, gated to Project Execution, and avoids changing ordinary project behavior.
- 关联 checklist：CHK-001, CHK-002, CHK-003, CHK-004, CHK-005, CHK-006, CHK-009, CHK-010, CHK-012, CHK-017.

## TODO-002 Apply column sync to execution start and active states

- 目标：Ensure execution and rework states visibly enter In Progress.
- 涉及区域：Task start, rework creation, `_project_execution_transition`, persisted project save paths.
- 输入：Existing start/rework flows and TODO-001 contract.
- 输出：Tasks in `executing` and `reworking` states are persisted in the In Progress column.
- 依赖：TODO-001.
- 完成标准：Starting a Project Execution task moves it to In Progress; rework also moves to In Progress; `completedAt` remains empty.
- 关联 checklist：CHK-001, CHK-009, CHK-014, CHK-015, CHK-016.

## TODO-003 Apply column sync to execution-complete and review states

- 目标：Ensure execution-complete, reviewing, and awaiting-human-acceptance states visibly use the Review column.
- 涉及区域：Execution completion, review start, review pass with manual acceptance, skipped-review with manual acceptance.
- 输入：Existing `_project_execution_run_attempt`, `_handle_project_execution_review_start`, `_project_execution_run_review`, skipped-review flow.
- 输出：Tasks ready for review, under review, or waiting for manual acceptance are persisted in Review.
- 依赖：TODO-001.
- 完成标准：No Project Execution task remains in Backlog while `executionState` is `execution_complete`, `reviewing`, or `awaiting_user_acceptance`.
- 关联 checklist：CHK-002, CHK-003, CHK-005, CHK-008, CHK-014, CHK-015, CHK-016.

## TODO-004 Update reviewer pass and skipped-review completion semantics

- 目标：Make reviewer pass complete directly by default, while preserving manual acceptance as an explicit option.
- 涉及区域：`_project_execution_requires_user_acceptance`, `_project_execution_run_review`, skipped-review branch in `_project_execution_run_attempt`, `_project_execution_mark_done`, acceptance handler.
- 输入：Confirmed product rule: AI reviewer pass equals acceptance unless manual acceptance is enabled.
- 输出：Default reviewer pass and confirmed reviewer skip move to Done; manual acceptance mode still waits in Review.
- 依赖：TODO-001, TODO-003.
- 完成标准：Default pass and default skipped-review flows end in Done with audit history; manual acceptance flows wait in Review and complete after user acceptance.
- 关联 checklist：CHK-004, CHK-005, CHK-006, CHK-007, CHK-008, CHK-014.

## TODO-005 Review and tighten manual move/reorder restrictions

- 目标：Prevent users from manually bypassing Project Execution state-machine rules without affecting ordinary projects.
- 涉及区域：Task update handler, reorder handler, drag/drop API validation, UI error display if already wired.
- 输入：Existing 409 behavior around Done moves; confirmed Project Execution restriction policy.
- 输出：Invalid Project Execution moves are blocked; ordinary project moves remain allowed.
- 依赖：TODO-001.
- 完成标准：Unreviewed or non-terminal Project Execution tasks cannot be dragged or updated directly to Done; normal projects can still move tasks freely.
- 关联 checklist：CHK-011, CHK-012, CHK-017.

## TODO-006 Preserve continuous flow eligibility

- 目标：Ensure column synchronization does not cause continuous flow to restart Review, Done, or awaiting-acceptance tasks.
- 涉及区域：`_project_execution_next_task`, `_project_execution_is_startable_task`, project-start continuation logic.
- 输入：Existing continuous project flow tests and state contract.
- 输出：Continuous flow starts only startable tasks and respects Review/Done/awaiting acceptance states.
- 依赖：TODO-002, TODO-003, TODO-004.
- 完成标准：Continuous flow skips non-startable Review/Done/awaiting acceptance tasks and handles no eligible task clearly.
- 关联 checklist：CHK-013, CHK-014, CHK-016.

## TODO-007 Add focused backend regression tests

- 目标：Lock the new state/column contract with automated tests.
- 涉及区域：`tests/test_project_execution.py`.
- 输入：Checklist scenarios and existing fake executor/reviewer patterns.
- 输出：Tests for start to In Progress, execution complete to Review, reviewing to Review, pass to Done by default, manual acceptance to Review then Done, skipped review paths, rework to In Progress, invalid move blocking, ordinary project movement unchanged, and continuous eligibility.
- 依赖：TODO-002, TODO-003, TODO-004, TODO-005, TODO-006.
- 完成标准：Focused tests fail on the old mismatch and pass after implementation.
- 关联 checklist：CHK-001 through CHK-014, CHK-017, CHK-018.

## TODO-008 Verify frontend board and toolbar behavior

- 目标：Confirm the user-visible board reflects the same state machine as the backend.
- 涉及区域：`app/projects.js`, `app/projects.css` if needed, local service/browser validation.
- 输入：Backend API results and existing board rendering.
- 输出：Project board shows active tasks in the expected columns; toolbar/task detail status does not contradict card location.
- 依赖：TODO-002, TODO-003, TODO-004.
- 完成标准：Browser validation shows Backlog no longer contains active/reviewed Project Execution tasks; toolbar and task detail match the column state.
- 关联 checklist：CHK-015, CHK-016.

## TODO-009 Run regression suite and record results

- 目标：Execute the agreed validation set and capture outcomes for acceptance.
- 涉及区域：Python compile checks, Project Execution tests, front-end JS syntax checks, project CRUD regression, optional browser smoke checks.
- 输入：Implemented changes and confirmed checklist.
- 输出：Test results recorded in checklist or final delivery notes.
- 依赖：TODO-007, TODO-008.
- 完成标准：Relevant automated tests pass; any skipped browser/manual checks are explicitly reported.
- 关联 checklist：CHK-018.

## TODO-010 Update requirement status after implementation

- 目标：Keep the requirement archive accurate through implementation, testing, and final closure.
- 涉及区域：`.cosh-docs/requirment/project-execution-state-machine-columns/`.
- 输入：Implementation status, test results, user confirmations.
- 输出：Updated `checklist.md` with test execution records and updated `status.json` stages.
- 依赖：TODO-009.
- 完成标准：After development, stage can advance to `implementation_done`; after tests and user confirmation, it can advance to `tested` and then `done` per workflow.
- 关联 checklist：CHK-018.

