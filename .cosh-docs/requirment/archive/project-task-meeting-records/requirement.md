# Project Task Meeting Records

## Background

Project Execution tasks can request AI meetings while a task is running. Those meetings may unblock, block, or redirect the task. Users need to see the meeting conclusion directly inside the task detail instead of opening the meeting detail page to reconstruct what happened.

The product already has meeting action items and some meeting discussion data in task records, but the task detail should clearly present a meeting records module for meetings launched from that task.

## Product Clarification

The user clarified the following product choices:

- Primary goal: let users quickly see final meeting conclusions inside the task detail.
- Meeting scope: only meetings triggered by the project task, such as task execution meetings.
- Content scope: show meeting conclusion, risks, and follow-up action items.
- Multiple meetings: list all meeting conclusions in chronological order.
- No-consensus meetings: record them too, with a clear no-consensus or user-decision-needed state.

## Target Users

- Project owners and operators checking why a task changed state.
- Users accepting or rejecting Project Execution results.
- Agents or workflows that need task-local meeting context for subsequent execution.

## Goals

- Add or formalize a task-level meeting records module.
- For meetings launched from a project task, record the meeting result back onto that task.
- Show the meeting conclusion, risks, and follow-up action items in the task detail.
- Preserve all task-triggered meeting records, ordered by time, so users can trace task history.
- Record no-consensus or needs-user-decision meetings instead of silently hiding them.

## Scope

- Applies to meetings with a project task source, specifically meetings tied to a `projectId`, `taskId`, and meeting request.
- Covers completed meeting outcomes including approved, no consensus, rejected, and needs user decision.
- Covers task detail display and persisted task data.
- Covers existing and future task meeting result application paths.

## Non-goals

- Do not show every unrelated project meeting in every task.
- Do not embed full meeting transcripts in the task detail.
- Do not replace the existing meeting detail page.
- Do not merge meeting action items into the task acceptance checklist.
- Do not change meeting approval or execution rules.

## Key Constraints

- Task meeting records must be idempotent: repeated meeting result application must not duplicate records.
- Existing meeting action item behavior must remain separate and visible.
- Existing task checklist behavior must remain focused on deliverable acceptance criteria.
- The UI should remain scan-friendly; detailed meeting discussion stays in the meeting page.
- Localization must cover new visible labels in Chinese and English.
