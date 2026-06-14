# Meeting for AI Phase 1-3

## Parent Requirement

- Parent: `meeting-for-ai`
- Parent path: `../meeting-for-ai/`
- Delivery scope: Phase 1, Phase 2, and Phase 3 implemented together.

## Goal

Deliver the first complete executable multi-AI meeting experience:

1. A durable meeting domain model and recoverable state machine.
2. A user-started meeting that actually invokes multiple AI agents in sequence.
3. User intervention, pause/resume, early ending, moderator takeover, and disagreement arbitration.

At completion, a user can start a meeting with at least three available agents, observe structured turns, intervene while it runs, and receive a durable structured result.

## Phase 1: Durable Meeting Foundation

### Scope

- Introduce a canonical executable meeting entity separate from legacy display-only records.
- Persist meeting configuration, lifecycle state, stage, round, speaker queue, participant state, context, events, result draft, timestamps, and version.
- Use immutable event sequence numbers for state changes and transcript entries.
- Define valid lifecycle transitions for:
  - `draft`
  - `preparing`
  - `active_opening`
  - `active_discussion`
  - `paused`
  - `awaiting_user_decision`
  - `summarizing`
  - `completed`
  - `cancelled`
  - `failed`
- Enforce one active meeting per agent.
- Preserve compatibility with `_meetings` and `_meetingHistory`.
- Add APIs for meeting creation, detail, event retrieval, transition, cancellation, and recovery status.
- Update the meeting center to distinguish legacy meetings from executable meetings.
- Reconcile non-terminal meetings after a service restart without duplicating completed events.

### Phase 1 Exit Result

Meeting state survives restart, invalid transitions are rejected, participant occupancy is consistent, and legacy meetings still render.

## Phase 2: User-Started Sequential AI Meeting MVP

### Scope

- Add a user-facing start-meeting form.
- Support meeting types:
  - information gathering
  - decision discussion
  - task collaboration
- Let the user select at least two participants, an AI moderator, meeting purpose, initial context, and maximum discussion rounds.
- Only available agents can start Phase 2 meetings.
- Use the existing provider adapters for OpenClaw, Hermes, and Codex.
- Give every meeting and participant a stable conversation identifier.
- Execute an opening round where every valid participant speaks once.
- Execute moderator-directed discussion rounds up to the configured limit.
- Provide each speaker with confirmed context, current agenda, rolling discussion summary, relevant prior statements, current stage, and remaining rounds.
- Normalize speaker output into structured transcript events while retaining the original text.
- Allow the moderator to recommend early completion.
- Generate a structured meeting result:
  - summary
  - decision or conclusion
  - unresolved questions
  - disagreements
  - participant contributions
  - action-item drafts
- Show stage, round, current speaker, participant status, transcript, and result in the meeting UI.

### Phase 2 Constraints

- AI-initiated meeting requests are excluded.
- Automatic project/history context collection is excluded.
- Busy agents are rejected rather than paused or interrupted.
- Action items remain result drafts and do not create project tasks.

### Phase 2 Exit Result

A user can complete a real three-agent meeting through the UI and obtain a durable structured result.

## Phase 3: User Control and Arbitration

### Scope

- Persist all user interventions in the same ordered meeting event stream.
- Let the user:
  - speak to the room
  - ask a question
  - nominate a specific AI to answer
  - add context
  - change the agenda
  - pause
  - resume
  - cancel
  - end early
- Apply user changes to subsequent AI turns without rewriting previous events.
- Prevent new AI calls while paused.
- Resume from the next incomplete step without replaying completed turns.
- Detect an unresolved disagreement at round exhaustion and enter `awaiting_user_decision`.
- Present competing positions and moderator recommendation without majority-vote auto-selection.
- Let the user provide a decision, request another targeted response, or end without consensus.
- Let the user take over moderation or replace a failed AI moderator.
- Preserve completed statements if the moderator changes.

### Phase 3 Exit Result

The user can safely control an active meeting at any stage, and unresolved disagreement is explicitly handed to the user.

## Shared Product Rules

- The user is the highest authority.
- Meeting execution continues on the server if the browser is closed.
- A meeting must not rely on browser memory as canonical state.
- Every transition and side effect must be idempotent.
- A participant may belong to only one non-terminal executable meeting.
- Provider failures are represented as participant or moderator state, not hidden.
- Original transcript text and structured summaries remain traceable to event IDs.

## Out of Scope

- AI-initiated meeting requests and confirmation.
- Automatic context discovery from projects, tasks, and prior meetings.
- Interrupting, pausing, or resuming an agent's existing work.
- Waiting for or force-joining busy agents.
- Parallel membership of one agent in multiple meetings.
- Creating project tasks from action items.
- Production-complete timeout/retry matrices for every provider.
- Advanced metrics, search, retention controls, and full Phase 7 hardening.

## Success Criteria

- Phase 1, Phase 2, and Phase 3 each pass their independent automated and manual gate.
- A full user-started three-agent meeting passes end to end.
- Browser refresh and service restart do not lose canonical meeting state.
- Paused meetings produce no new speaker calls.
- User interventions affect later turns and remain auditable.
- No-consensus meetings wait for explicit user action.
- Existing legacy meetings, ordinary chat, and project workflows do not regress.
