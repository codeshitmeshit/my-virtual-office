# Project Execution Project Start

## Background

After executable projects became the default, users naturally expect a project-level "start project" control to remain available. The current UI hides the old workflow start controls for Project Execution projects and only exposes "start this task" inside each task detail panel. This makes a newly created executable project feel impossible to start, especially when users are used to the old project-level workflow button.

The clarified request is not to fall back to the old workflow engine. The request is to preserve the project-level start experience for Project Execution projects while keeping Project Execution's stricter task-level execution, review, evidence, and user acceptance model.

## Target User

- A Virtual Office user creating or opening a Project Execution project.
- The user expects to start work from the project board toolbar.
- The user may not know that Project Execution currently requires opening a task detail panel.

## Product Goal

Let a user start a Project Execution project from the project toolbar, using a familiar project-level "start" action. The toolbar should expose a project start mode radio control:

- Start next task: start only the next eligible task.
- Continuous task flow: default mode; start and continue through eligible tasks until there are no tasks or an execution, review, error, or acceptance stop point is reached.

Internally, the system should still run work through Project Execution tasks, so the task-level execution, review, evidence, and user acceptance model remains intact.

## Confirmed Product Understanding

- Users expect the project-level start affordance to remain visible for default executable projects.
- Project Execution must keep task-level evidence, independent review, and user acceptance.
- Project-level start should not use the old legacy workflow engine for Project Execution projects.
- A project-level start action can be implemented as a coordinator that selects the next eligible Project Execution task and calls the existing task execution start flow.
- The toolbar should include a radio control for project task flow mode.
- The default mode should be continuous task flow.
- Task creation should make explicit whether the task requires manual user acceptance.
- The project execution control panel should show whether the active or selected task requires user acceptance.
- If a task does not require manual user acceptance, a passed review can automatically continue to the next task in continuous task flow.
- If a task requires manual user acceptance, continuous task flow must stop and wait for user acceptance.

## In Scope

1. Add a visible project-level start control for Project Execution projects.
2. Keep the old workflow controls for normal projects unchanged.
3. Define "start project" for Project Execution as "start the next eligible task".
4. Select the next task from project tasks in a predictable order.
5. Reuse the existing Project Execution task start API and state machine once a task is selected.
6. Show useful messages when no eligible task exists.
7. Show useful messages when an executor or reviewer is missing.
8. Prevent starting a second task when another Project Execution task is already active.
9. Preserve task-level review, rework, blocked, and user acceptance behavior.
10. Keep the task-detail "启动此任务" action available.
11. Make the project toolbar state understandable: idle, executing, reviewing, awaiting user action, done, blocked.
12. Add a toolbar radio control for "启动下一个任务" and "连续启动任务".
13. Default Project Execution project startup to "连续启动任务".
14. Add task-level manual acceptance configuration at task creation and in the task/control panel.
15. Continue automatically after review pass only when the task is configured as not requiring manual acceptance.

## Out of Scope

- Replacing Project Execution with the old workflow system.
- Automatically completing the entire project without user acceptance.
- Changing the reviewer pass and user acceptance requirements.
- Running multiple Project Execution tasks in parallel.
- New scheduling rules beyond selecting the next eligible task.
- Full Auto Mode parity with the old workflow pipeline.
- Agent role auto-assignment beyond existing project defaults and task overrides.
- Bypassing review for tasks in continuous task flow.
- Automatically accepting tasks that are explicitly marked as requiring manual user acceptance.

## Product Constraints

- Project-level start must not bypass the selected task's executor and reviewer requirements.
- Project-level start must not move tasks to Done directly.
- If no task is eligible, the user should understand what to do next.
- If a task cannot start because roles are missing, the user should know which role is required.
- Existing normal projects must continue to show and use the old workflow start behavior.
- Continuous task flow must not run more than one task at the same time.
- Continuous task flow must stop at tasks requiring manual user acceptance.
- The UI copy should emphasize that project start is a task flow: "启动下一个任务" versus "连续启动任务".

## Proposed Eligible Task Rule

The first version should choose the first task that:

1. Belongs to a non-Done column.
2. Has `executionState` empty or in a startable state such as `backlog` or `blocked` after user correction.
3. Is not currently active.
4. Appears earliest by column order and task order.

If no eligible task exists, show a clear "没有可启动的任务" style message.

## Project Start Modes

The project toolbar should expose a radio group near the "启动项目" button:

1. "启动下一个任务": project start selects and starts one eligible task, then stops after that task reaches a terminal or waiting state.
2. "连续启动任务": default; project start selects and starts the next eligible task, and after each task passes review it continues to the next eligible task if the completed task does not require manual user acceptance.

When a task requires manual user acceptance, the control panel should clearly show that the project is waiting for user acceptance. After the user accepts, the project can continue according to the selected task flow mode.

## Task Manual Acceptance

Task creation should require or clearly expose a task-level choice for manual acceptance. The task/control panel should allow users to see and adjust whether a task requires manual user acceptance.

The default should preserve Project Execution safety. If a default must be chosen for new tasks, it should favor requiring manual acceptance unless the product explicitly chooses a lower-friction default later.

## Success Criteria

The feature succeeds when:

1. A Project Execution project shows a project-level start button in the toolbar.
2. Clicking the button starts the next eligible task.
3. The started task transitions through the existing Project Execution state machine.
4. The toolbar reflects active execution state.
5. Starting is blocked with a clear message if another task is already active.
6. Starting is blocked with a clear message if executor or reviewer configuration is missing.
7. Normal project workflow start behavior is unchanged.
8. The toolbar offers a project start mode radio control and defaults to continuous task flow.
9. Continuous task flow automatically advances only when review passes and the completed task does not require manual user acceptance.
10. Tasks requiring manual user acceptance stop the continuous flow and show a clear waiting state.
