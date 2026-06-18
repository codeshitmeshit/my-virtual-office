# Meeting for AI Phase 4: AI Meeting Requests and Pre-Meeting Context

## Background

`meeting-for-ai-phase-1-3` has completed the executable meeting foundation, user-started meetings, live user control, arbitration, and moderator takeover. The parent `meeting-for-ai` requirement still includes Phase 4-7.

Phase 4 focuses on letting an AI propose a meeting while preserving user control. The first supported trigger is an AI working on a project task that reaches a clear collaboration blocker.

## Parent Requirement

- Parent: `meeting-for-ai`
- Prior completed child: `meeting-for-ai-phase-1-3`
- Parent Phase: Phase 4, AI initiated request and pre-meeting context

## Product Goal

Allow an AI that is executing a project task to request a multi-AI meeting when it is blocked by a decision, needs another AI's specialized judgment, or cannot responsibly continue alone.

The user must understand the request, edit the proposed meeting, confirm selected context, or reject the request. Nothing should call meeting participants or occupy Agents before user confirmation.

## Target Users

- Users managing projects in Virtual Office.
- Users who rely on multiple AI Agents to complete project tasks.
- AI Agents working on project tasks that need collaboration before proceeding.

## Primary Scenario

1. An AI is executing or progressing a project task.
2. It detects a clear collaboration blocker:
   - A decision is required.
   - Another AI has relevant expertise.
   - Continuing alone would likely produce poor or incomplete work.
3. The AI submits a meeting request with required explanation fields.
4. The system recommends same-project context candidates.
5. The user reviews the request, edits meeting configuration, selects context, then confirms or rejects.
6. Confirmed requests become executable meetings using the user-approved configuration and context snapshot.
7. Rejected requests are closed and the rejection reason is visible to the requesting AI/task context.

## In Scope

### AI Request Eligibility

- The first supported request source is a project task.
- The AI may request a meeting only when it can describe a clear blocker.
- The request must include:
  - Meeting goal.
  - Expected outcome.
  - Why the AI cannot complete the task alone.
  - Suggested participants or required roles.
  - Suggested meeting type.
  - Link to the source project/task.
- The product should leave an explicit extension point for later request sources, such as other workflows or chat, but those sources are not active in this Phase.

### Request Review

The user can:

- View pending AI meeting requests.
- Understand the source project/task and reason for the request.
- Reject the request with an optional or required reason.
- Edit before confirmation:
  - Topic.
  - Purpose.
  - Meeting type.
  - Participants.
  - Moderator.
  - Maximum rounds or equivalent meeting controls.
  - Context candidates.
  - Supplemental context.

### Frontend Display Placement

AI meeting requests should appear in three places with different purposes:

- Source task detail panel: the primary context view for requests created from that task. It should show pending, rejected, and confirmed requests related to the open task, including requesting AI, request reason, expected outcome, status, and the review action.
- Meetings dashboard: add a dedicated AI Requests tab or equivalent independent section beside Active and History. It is the aggregated processing queue for all AI meeting requests and must not mix pending requests into Active meetings.
- Control panel Meetings widget: when there are AI meeting requests requiring user confirmation, show a clear pending request count or confirmation-needed prompt under the existing Meetings section in the right control panel. Clicking it should open the Meetings dashboard AI Requests queue. It should not render full request review controls inline.

Task cards may show a compact status badge or count when the task has pending AI meeting requests, but the card is not the primary review surface.

### Context Candidates

The system recommends context candidates from:

- Current project.
- Current task.
- Related tasks in the same project.
- Prior meetings in the same project.

Recommended context is not enabled by default. The user must explicitly select candidate context before it becomes part of the meeting.

### Confirmed Context Snapshot

- The final meeting receives only the user-selected context and user-entered supplemental context.
- The selected context becomes an immutable snapshot for that meeting.
- Unselected candidates must not be sent to meeting participants, meeting prompts, visible transcript, summary, or result.

### Rejection Handling

- Rejected requests are closed.
- The rejection reason is returned to the source task context so the requesting AI can continue, adjust its plan, or avoid repeating the same request.

## Out of Scope

- Ordinary chat-originated meeting requests.
- Automatic periodic scanning that creates meeting requests.
- Cross-project context recommendation.
- Auto-selecting recommended context.
- Starting a meeting without user confirmation.
- Occupying Agents before confirmation.
- Pausing or restoring active tasks for meeting participation; that remains Phase 5.
- Converting meeting action items into project tasks; that remains Phase 6.
- Full audit/metrics hardening beyond what is necessary to validate request lifecycle and context isolation; that remains Phase 7.

## Product Decisions Confirmed

- Primary trigger: AI working on a project task encounters a clear collaboration blocker.
- Later trigger sources should be possible, but not implemented in this Phase.
- Context recommendation scope: current project, current task, related same-project tasks, same-project prior meetings.
- Recommended context defaults to unselected.
- Confirmation flow: editable review before starting the meeting.
- Request quality gate: meeting goal, expected outcome, and why the AI cannot complete alone are required.
- Rejection handling: close the request and return the reason to the source AI/task context.
- Difference tracking: keep a lightweight record of original request reason and user edit summary.
- Ordinary chat requests are out of scope for this Phase.
- Success standard: user can understand, edit, confirm context, and start; unconfirmed requests never occupy Agents or call participants.
- Delivery sequence: build and validate the request APIs, context candidate behavior, and frontend UI first with deterministic or equivalent request fixtures.
- Real AI acceptance gate: before testing the true AI-originated request flow, the implementation must stop and notify the user so the required skill can be installed for the requesting AI.
- Frontend placement: task detail is the source-context view, Meetings dashboard has the aggregated AI Requests queue, and the right control panel Meetings widget shows a lightweight confirmation-needed prompt.

## Success Criteria

- A project-task AI can create a valid pending meeting request.
- Invalid requests without required explanation do not become actionable pending requests.
- The user can review, edit, reject, or confirm the request.
- Recommended context appears as selectable candidates and is not selected by default.
- A request is visible from both its source task detail panel and the Meetings dashboard AI Requests queue.
- Confirmed meetings use only user-selected and supplemental context.
- Rejected requests preserve a rejection reason for the source task context.
- Unconfirmed requests do not reserve participants, create active meetings, or call any meeting participant provider.
- Phase 1-3 user-started meeting behavior remains intact.
- Pre-real-AI implementation can be accepted for APIs and UI using deterministic fixtures, but final true AI-originated acceptance must wait for the user to prepare and install the required skill.
