# Review

## Product Review

The product direction is clear enough to proceed.

The important distinction is that this requirement is not about general meeting notes. It only targets AI meetings created because a running project task needed a decision. In that context, the meeting is part of the task state machine. Meeting output must therefore feed back into the source task before execution resumes.

Resolved product semantics:

- Meeting action items are not merely drafts in this scenario.
- Current-agent action items become pending work inside the source task.
- The source task can continue only after those pending action items are completed and checked.
- Meeting decisions become task context.
- Meeting risks become verification-visible task checklist/review material.
- Other-owner action items become linked tasks so responsibility is not hidden inside the current task.
- No-consensus meetings keep the source task blocked.

No further product clarification is blocking.

## Current System Review

Relevant existing behavior:

- `app/server.py` has executable meeting action item drafts and manual confirmation into tasks.
- `app/server.py` has `_project_execution_apply_meeting_result(meeting)`, which currently resumes the source task when the meeting outcome is approved.
- Running tasks can enter `awaiting_meeting_resolution` through the meeting blocker path.
- Meeting results currently include `summary`, `decision`, `unresolvedQuestions`, `disagreements`, and `actionItems`.
- Project tasks already support checklist, comments, source metadata, execution state, attempts, linked activity, and task creation with `assignee`/`executorAgentId`.

Gap:

- Approved meeting result currently resumes the original task directly.
- It does not first add meeting action items into the original task backlog/todo, track their completion, and only then resume the original task.
- Existing action item draft UI still frames action items as user-confirmed project tasks, which is useful for general meetings but insufficient for task-blocking meetings.

## Technical Review

No blocking technical issue was found.

Recommended implementation direction:

- Extend task data with a meeting-applied action item collection or reuse checklist with source metadata so each meeting-created action item can be tracked and checked off.
- Ensure every applied action item has stable source identity: meeting id, meeting request id, action item id, source task id, owner, status, and created timestamp.
- Apply meeting result idempotently by checking meeting id/action item id before adding task entries.
- For current executor-owned action items, add them to the original task as pending work before resuming execution.
- For other-owner action items, create linked project tasks with `source.kind = meeting_action_item` and a backlink to the original task.
- Convert decision and risk data into task comments, task context, or review-visible checklist items.
- Change the approved-meeting resume path so it starts an action-item completion phase first; only after required action items are checked should it resume the original task.
- Keep `no_consensus`, `rejected`, unresolved questions, or ambiguous meeting outcome in the blocked/awaiting state.
- Surface meeting-applied action items in the project task UI so the user can inspect what was added and what is already checked.

## State Flow Review

Expected task state flow:

1. Task is executing.
2. Agent requests AI meeting and task enters `awaiting_meeting_resolution`.
3. Meeting completes.
4. If meeting has no consensus or unresolved blocking questions, task stays blocked/awaiting.
5. If meeting is approved, meeting output is applied to the source task.
6. Current-agent action items are added as pending task backlog/todo entries.
7. The agent executes those meeting-created action items and checks them off.
8. Only after all required action items are checked, the original task continues.
9. The original task then proceeds through its normal execution/review/user acceptance flow.

## Risk Review

- Idempotency risk: meeting result hooks may run more than once. Action item application must avoid duplicates.
- Ownership risk: meeting output may use display names instead of agent ids. Owner matching must be conservative and visible.
- Resume risk: automatically resuming too early would violate the main product requirement.
- UI risk: if meeting-added action items are hidden inside task data, users cannot understand why execution is delayed.
- Regression risk: general meetings should keep their manual action item draft behavior.

## Review Conclusion

Proceed to checklist.

The implementation is feasible with the existing meeting blocker and project execution state machine. The main acceptance risk is behavioral: the system must prove that approved meetings no longer resume the original task until meeting-created action items are applied, completed, and checked off.
