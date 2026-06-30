# Review

## Review status

Result: approved for checklist drafting. No blocking product or technical questions remain.

## Product review

The clarified product intent is coherent:

- The task detail is the correct surface because the meeting is part of the task execution history.
- Restricting the scope to task-triggered meetings avoids noisy project-wide meeting history.
- Showing conclusions, risks, and action items gives users enough context without duplicating full meeting transcripts.
- Recording no-consensus meetings is important because they explain why a task is blocked or waiting for user action.

The main product risk is UI overload when a task has multiple meetings. The accepted product direction is to list all task-triggered meeting records in time order, but the implementation should keep each record compact.

## Current implementation context

Observed existing surfaces:

- `app/server.py` persists task fields including `meetingActionItems`, `meetingDecisionHistory`, and `meetingDiscussionPoints`.
- `_project_execution_apply_meeting_output_to_task` already writes approved meeting decisions into `meetingDecisionHistory` and `meetingDiscussionPoints`, and writes risks into `meetingDiscussionPoints`.
- `_project_execution_apply_meeting_result` handles approved, no-consensus, rejected, and needs-user-decision outcomes for task-linked meetings.
- `app/projects.js` renders `meetingDiscussionPoints` in the task detail, currently under a hard-coded Chinese label `会议议论要点`, and renders `meetingActionItems` separately.
- Tests already cover some discussion-point recording, but the product requirement now needs a clearer task meeting records contract.

## Technical review

The implementation should formalize task meeting records rather than relying only on loosely named discussion points. Two low-risk paths are available:

1. Continue using `meetingDiscussionPoints`, but rename/present it as a task meeting records module and ensure all outcomes are represented.
2. Add a dedicated `meetingRecords` collection and optionally keep compatibility with existing `meetingDiscussionPoints`.

The conservative direction is to reuse existing task-level meeting fields unless the implementation discovers that a dedicated collection is cleaner. The existing persistence layer already supports these fields, and the UI already renders them. The required work is mostly completion, naming, outcome coverage, ordering, idempotency, and tests.

## Edge cases to cover

- Approved meeting with decision, risks, and action items.
- Meeting with no consensus or rejected outcome.
- Meeting that requires user decision.
- Repeated application of the same meeting result.
- Multiple task-triggered meetings on the same task.
- Non-task project meetings or ad hoc meetings must not appear in unrelated task meeting records.
- Existing meeting action item panel must remain separate from meeting records.

## Recommendation

Proceed to checklist. The requirement is small enough to implement within the existing Project Execution and task detail surfaces, but the checklist should require explicit verification of outcome coverage and non-duplication.
