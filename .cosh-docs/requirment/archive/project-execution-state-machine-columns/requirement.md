# Project Execution State Machine Columns

## Background

Project Execution currently exposes board columns such as Backlog, In Progress, Review, and Done. Users naturally read these columns as a task state machine. In the current implementation, the newer Project Execution flow mainly updates `executionState` while leaving `columnId` unchanged until the task reaches Done. This creates a confusing product experience: a task can remain visually in Backlog while marked as executing or completed, then appear to jump directly to Done.

The clarified request is to unify Project Execution's internal task state with the board columns when Project Execution is enabled, while preserving normal free-form board behavior for ordinary projects.

## Target Users

- Virtual Office users running Project Execution projects.
- Users monitoring project progress from the board, without opening every task detail panel.
- Users who need to understand whether AI execution, review, human acceptance, or completion is currently happening.

## Product Goal

Make Project Execution columns behave as a clear state machine:

```text
Backlog -> In Progress -> Review -> Done
```

The board should no longer show an active or reviewed Project Execution task sitting in Backlog. The task card location, execution state, toolbar state, and history should tell one coherent story.

## Confirmed Product Understanding

- In Project Execution projects, columns represent the execution state machine.
- In ordinary projects, columns remain free-form task organization.
- Starting execution moves a task from Backlog or another eligible non-Done column into In Progress.
- Execution completion moves the task into Review.
- Reviewer pass moves the task to Done by default.
- Skipped reviewer flow also records review skipped and moves through the Review semantics before completion.
- A task-level or project-level option can require manual human acceptance.
- When manual acceptance is required, reviewer pass moves or keeps the task in Review with `awaiting_user_acceptance` product semantics.
- Human acceptance then moves the task from Review to Done.
- Project Execution mode should prevent manual drag/reorder actions that would break the state machine, such as moving an unreviewed task directly to Done.

## In Scope

1. Synchronize Project Execution state transitions with board columns.
2. Preserve free-form columns for non-Project Execution projects.
3. Move executing and reworking tasks into In Progress.
4. Move execution-complete, reviewing, and awaiting-user-acceptance tasks into Review.
5. Move reviewer-passed tasks directly to Done when manual acceptance is not required.
6. Keep awaiting-user-acceptance only when the manual acceptance option is enabled.
7. Move skipped-review tasks to Done after the skip has been confirmed and recorded, unless manual acceptance is required.
8. Keep audit/history entries that explain whether Done was reached by AI reviewer pass, skipped review, or human acceptance.
9. Enforce drag/reorder restrictions for Project Execution projects so users cannot bypass the state machine accidentally.
10. Update tests and acceptance coverage for the new column/state contract.

## Out of Scope

- Replacing Project Execution with the legacy workflow engine.
- Removing `executionState`; the field remains the canonical internal state.
- Changing ordinary project board behavior.
- Running multiple Project Execution tasks in parallel.
- Redesigning the whole project board UI.
- Removing the manual human acceptance option.
- Changing executor/reviewer role selection rules except where required by state flow.

## State And Column Contract

| Product state | Expected column | Notes |
| --- | --- | --- |
| `backlog`, `blocked` when restartable | Backlog or current non-Done eligible column | Existing task organization can remain until execution starts. |
| `executing`, `reworking` | In Progress | Shows active AI execution. |
| `execution_complete` | Review | Execution has produced evidence and is ready for independent review. |
| `reviewing` | Review | Independent reviewer is active. |
| `awaiting_user_acceptance` | Review | Only when manual acceptance is enabled. |
| `done` | Done | Completion by AI reviewer pass, skipped review confirmation, or human acceptance. |

## Manual Acceptance Semantics

Manual human acceptance is optional. When it is not enabled, reviewer pass is sufficient to complete the task and move it to Done.

When manual human acceptance is enabled:

1. Reviewer pass does not complete the task.
2. The task remains in or moves to Review.
3. The task state becomes `awaiting_user_acceptance`.
4. Human acceptance moves it to Done.

## Success Criteria

The fix succeeds when:

1. Project Execution tasks visibly follow `Backlog -> In Progress -> Review -> Done`.
2. A task is not visually stuck in Backlog while `executionState` is `executing`, `reviewing`, `execution_complete`, or `awaiting_user_acceptance`.
3. AI reviewer pass moves to Done by default.
4. Manual acceptance mode keeps a passed review in Review until human acceptance.
5. Human acceptance moves from Review to Done.
6. Skipped review is clearly recorded and reaches Done according to the manual acceptance setting.
7. Normal project boards remain manually movable and unchanged.
8. Project Execution drag/reorder restrictions prevent invalid state-machine bypasses.

