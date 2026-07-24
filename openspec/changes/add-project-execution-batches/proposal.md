## Why

Project tasks currently expose an execution order number, but the product goal has shifted from a globally unique linear sequence to batch-based flow execution. Future Project Execution should support a single project flow that runs all tasks in the current batch concurrently, waits for that batch to finish, and then advances to the next batch.

The existing uniqueness-oriented behavior is not a safe foundation for this. It prevents users from expressing parallel work, makes the UI misleading when tasks move out of Backlog, and risks state-machine ambiguity once concurrent execution is introduced.

## What Changes

- Rename the product concept from "execution order" to "execution batch" in user-facing project task planning and editing.
- Require every project task to have a positive execution-batch number.
- Allow multiple tasks in the same project to share the same execution-batch number; shared numbers mean those tasks belong to the same concurrent batch.
- Project Execution starts the lowest unfinished batch, starts all eligible tasks in that batch together, and does not advance to the next batch until the current batch is fully complete.
- If any task in the active batch fails or blocks, the batch blocks as a whole until the user resolves the issue.
- The batch editor covers all project tasks and shows each task's current column/state, not only Backlog tasks.
- AI may suggest batch assignments, but user confirmation is required before the assignments take effect.
- Started, reviewing, blocked, awaiting-acceptance, completed, or otherwise historical tasks cannot be moved into a different batch. Unstarted tasks can only be moved to future batches that have not started or completed.
- Existing projects remain readable. Tasks without a persisted batch receive a compatible effective batch based on prior ordering until the project is saved or backfilled.

## Capabilities

### New Capabilities

- `project-execution-batches`: Batch-number semantics, editing rules, and batch-gated Project Execution.

### Modified Capabilities

- `project-execution-service-boundaries`: Project Execution selection and state-machine advancement must respect execution batches instead of choosing a single next task by unique order.
- `agent-project-authoring`: Agent-created projects and templates must include confirmed execution-batch assignments for every task.

## Impact

- Project UI: task cards and the order editor should present "Execution Batch" and include every task in the project.
- Project/task persistence: every task needs a positive batch value, with compatibility for legacy records that do not yet have one.
- Project commands: task create/update, template materialization, direct authoring, recurrence instance materialization, and manual UI creation must preserve or assign valid batch values.
- Project Execution lifecycle: project-level start/continue must select a batch of tasks and manage batch completion/blocking semantics.
- Tests: persistence, project command validation, materialization, authoring, template, recurrence, UI/static, direct task start, project flow, batch blocking, and legacy compatibility coverage.

## Non-Goals

- Arbitrary dependency graphs between tasks.
- Per-Agent capacity scheduling or resource balancing beyond existing executor availability checks.
- Partial advancement from a batch before all tasks in that batch are complete.
- Renaming persisted fields before compatibility and migration behavior are explicitly designed.

## Open Questions

- Whether the persisted field should remain `executionOrder` for compatibility while the product label becomes "Execution Batch", or whether a new persisted `executionBatch` field should be introduced with a migration path.
- How batch-level progress and blocked state should be displayed in the project UI.
