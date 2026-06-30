# Meeting Action Items To Task

## Background

Project Execution already supports AI meeting requests that can block a running task and later resume it after the meeting reaches consensus. Current meeting action items are mostly handled as action item drafts that a user can manually confirm into project tasks.

This requirement changes the product behavior for meetings created from a running project task: after the AI meeting finishes, the meeting result must be applied back to the original task so the meeting is part of the execution loop, not a separate record.

## Target Users

- Human project owner who expects task execution to continue after AI agents resolve a disagreement.
- AI agent currently executing a project task and requesting a meeting to resolve ambiguity or conflict.
- Other meeting participant agents who may receive follow-up action items from the meeting.

## Product Goal

When a task-running AI meeting completes, the meeting decision, risks, and action items must be reflected in the original task workflow. The original task should not continue until meeting-created action items that were added to its backlog/todo area are completed and checked off.

## Scope

- Apply meeting results back to the source project task when the meeting was created from a project task blocker.
- Add meeting action items to the original task backlog/todo list after the meeting completes.
- Mark action items as pending work until the responsible AI completes them.
- Check off completed meeting action items before resuming the original task.
- Write meeting decisions into the task context/history.
- Convert meeting risks into checklist or review-visible items so they affect verification.
- If an action item belongs to the current executing agent, merge it into the current task backlog/todo.
- If an action item belongs to another owner, create an associated project task linked to the original task.
- If the meeting has unresolved questions or no consensus, keep the original task blocked instead of continuing.
- After all required meeting action items are completed, automatically continue the original task when the meeting reached consensus.

## Non-Goals

- Do not make all meeting action items globally auto-execute without project/task context.
- Do not remove the existing manual meeting action item draft UI for non-blocking or ad hoc meetings.
- Do not allow archive-manager/system-only agents to receive ordinary project action items.
- Do not treat unresolved meeting discussions as successful task input.

## Product Decisions

- Default behavior for this scenario: meeting output is automatically applied to the source task after the meeting completes.
- Meeting output to apply: action items, decision, and risks.
- Target placement: the original task that triggered the meeting.
- Current owner behavior: current agent's action items are merged into the original task backlog/todo.
- Multi-owner behavior: current agent's action items stay in the original task; other owners get linked follow-up tasks.
- Resume behavior: the original task resumes only after meeting action items added to its backlog/todo are completed and checked off.
- Failure behavior: unresolved questions or lack of consensus keeps the task in `awaiting_meeting_resolution` or blocked status.

## Key Constraints

- The source meeting must be traceable to `projectId`, `taskId`, and meeting request id.
- The user should be able to inspect what the meeting added to the task.
- The original task should not silently skip meeting-created action items.
- Re-applying the same meeting result must be idempotent.
- Existing completed and archived requirement behavior must not regress.
