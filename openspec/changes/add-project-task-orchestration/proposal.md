## Why

New projects currently expose free-form and single-task Project Execution controls, so task order is advisory rather than an enforceable project plan. Project owners need one orchestration model that groups tasks into sequential stages, runs tasks within a stage in parallel, and advances the project without manual per-task progression.

## What Changes

- Add a task-pipeline orchestration workspace to project management, visually matched to the approved Figma prototype for typography, sizing, spacing, colors, borders, task states, canvas layout, and controls, except that the prototype's "保存编排" action is removed because orchestration edits auto-save.
- Require every task in a newly marked project to belong to exactly one positive, contiguous execution stage; tasks with the same stage run in parallel and stages run in ascending order.
- Keep orchestration and project start as separate actions. Starting a project locks the pipeline and dispatches every eligible task in stage 1; completion of a stage automatically dispatches the next stage.
- Add controlled exception handling: a task owner may request a skip, a project owner or manager must approve it, and failed or blocked work pauses automatic advancement until resolved.
- Allow an executing project to be paused and re-orchestrated: completed stages remain immutable, active tasks are terminated and returned to pending, and only unfinished tasks can be reassigned to stages after the last completed stage.
- Automatically complete the project after the final stage is completed or has approved skips; human acceptance must be represented as an explicit pipeline task when required.
- Persist an internal new-project orchestration marker in the JSONL project record without exposing a user-visible badge.
- **BREAKING** Remove the free-execution and single-task/manual-progression mode for marked new projects, including legacy project properties, API inputs/outputs, client state, and state transitions that exist only to select or maintain those modes.
- **BREAKING** Do not migrate legacy projects. Pre-release legacy project data may be removed, and only newly marked projects are required to satisfy the orchestration contract.

## Capabilities

### New Capabilities

- `project-task-orchestration`: Defines pipeline authoring, strict Figma-aligned presentation, stage invariants, separate project start, parallel stage dispatch, automatic advancement, exception approval, re-orchestration, and automatic project completion.

### Modified Capabilities

- `project-execution-service-boundaries`: Replaces compatibility requirements for free/single-task progression with the marked-new-project pipeline lifecycle and explicitly permits removal of obsolete execution-mode storage and API fields.

## Impact

- Project-management UI, localization, and project-page interaction behavior.
- Project and task commands, execution lifecycle, review/acceptance continuation, meeting-driven resumption, scheduler/recovery behavior, and realtime projections.
- Project JSONL serialization/materialization and every project-creation path that must set the internal orchestration marker.
- Existing Project Execution request/response fields, client workflow state, persisted properties, and tests that assume selectable continuous versus single-task execution.
- Automated and visual verification, including comparison against Figma nodes `147:2` and `148:3` with the confirmed removal of the save action.
