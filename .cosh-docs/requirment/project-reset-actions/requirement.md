# Project Reset Actions Requirement

## Background

The Project board currently has controls for starting project execution, editing metadata, viewing artifacts, reports, and templates. Users also need a recovery/reset entry near these project-level controls so a project can be returned to a usable backlog state after execution, review, blocking, or done states accumulate.

The product clarification is complete. The feature is a project-level "重置" button that opens a choice dialog with two reset actions.

## Target Users

- Project owner or operator managing a Virtual Office project board.
- Users running Project Execution repeatedly for validation, demos, scheduled work, or recovery from stuck execution states.

## Product Goal

Provide a clear, safe reset workflow that lets users recover task flow without manually dragging tasks or editing internal execution states.

## In Scope

- Add a project-level button named "重置" in the project toolbar area shown in the screenshot.
- Clicking "重置" opens a dialog with two choices:
  - "重置任务状态"
  - "彻底重置项目"
- "重置任务状态":
  - Forces tasks back to backlog.
  - Clears current execution context, including active attempt, blocked reason, review result, meeting blocker/current meeting action fields, completion state, and current execution state.
  - Preserves historical records such as comments, attempts, state history, meeting history/archive fields, artifacts, and audit trails.
- "彻底重置项目":
  - Resets task flow and execution flow state more broadly.
  - Keeps tasks added after project creation.
  - Puts all tasks back into backlog while preserving task ordering.
  - Preserves project-level configuration and scheduled cron configuration.
- Confirmation behavior:
  - If tasks are in non-initial states such as executing, blocked, review, done/completed, or have active execution context, show a high-risk confirmation.
  - If the project is already in an initial/empty backlog state, allow reset without high-risk confirmation.
- Preserve task order carefully. Reset must not scramble the user-visible sequence.
- Testing must include automated tests and E2E/manual acceptance of the UI flow.

## Out of Scope

- Deleting projects or project workspaces.
- Resetting project title, description, priority, default agents, workspace path, templates, or scheduled cron definitions.
- Clearing persistent history or audit records.
- Resetting external provider state outside the project model.
- Reworking the Project Execution state machine beyond the reset recovery action.

## Key Product Decisions

- Button label: "重置".
- Reset entry uses a choice dialog with two actions rather than one irreversible action.
- Confirmation is conditional: only risky/non-initial states require high-risk confirmation.
- Added tasks are preserved.
- Project configuration and scheduled tasks are preserved.
- Execution order is a core acceptance requirement.

## Success Criteria

- Users can find and click the "重置" button in the project toolbar.
- Users can clearly choose between task-state reset and project reset.
- Risky states require explicit confirmation before reset proceeds.
- Reset tasks appear in backlog in the expected order.
- Running/blocked/review/done tasks are no longer shown as active, blocked, review, or done after reset.
- Persistent history remains available for traceability.
- Automated and E2E validation cover the main flow, risky confirmation flow, order preservation, and regression surfaces.
