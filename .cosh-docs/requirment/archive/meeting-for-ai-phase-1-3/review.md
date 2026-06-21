# Meeting for AI Phase 1-3 Review

## Review Status

Reviewed with no blocking product or technical questions.

The three phases should be implemented in one child requirement because Phase 2 and Phase 3 depend directly on the event identity, transition rules, and recovery model established in Phase 1. They still retain independent test and acceptance gates.

## Existing Foundation

- Meeting create, active, history, end, and delete APIs already exist.
- The office scene already moves participants and displays meeting state.
- OpenClaw, Hermes, and Codex already have provider-specific invocation paths.
- Stable conversation identifiers and Codex operation locking already exist.
- Communication history already uses persistent event IDs.
- The HTTP service uses `ThreadingHTTPServer`.
- Existing project execution code demonstrates durable state transitions and restart reconciliation.

## Required Architecture

### Canonical Store

Create a dedicated meeting store under `VO_STATUS_DIR`. The executable meeting store, event stream, and legacy projection must not compete as independent sources of truth.

Recommended logical records:

- meeting snapshot
- append-only ordered meeting events
- participant occupancy index
- optional bounded rolling summary

Writes must use locking plus atomic replace. Event sequence allocation and state mutation must occur in one critical section.

### State Machine

All state changes must pass through one transition function that:

1. validates expected current version and legal transition;
2. appends the transition event;
3. updates the meeting snapshot;
4. updates participant occupancy;
5. persists atomically;
6. returns the new version and event sequence.

HTTP handlers and worker threads must not update meeting fields directly.

### Orchestrator

Use a server-owned meeting orchestrator with one serialized runner per meeting.

- The runner derives its next action from persisted state.
- Provider calls run outside the store lock.
- Before a provider call, persist a unique pending-call record.
- After completion, commit the response only if the pending call is still current.
- Pause, cancellation, user intervention, and moderator replacement enter the same event queue.
- Restart reconciliation may resume only steps whose completion event is absent.

### Provider Adapter

Add a meeting-specific adapter over existing provider calls instead of routing through visible A2A chat as the canonical engine.

The adapter must return a normalized result:

- success or failure
- original response text
- structured meeting contribution
- provider identifiers
- duration
- error code
- human-intervention requirement

Stable provider conversation IDs should be derived from meeting ID plus participant ID. This preserves per-participant meeting context without mixing unrelated meetings.

### Prompt and Context Contract

Every AI turn receives:

- meeting type, topic, purpose, and current agenda;
- user-confirmed initial context and later user context events;
- current stage and round;
- speaker role and moderator instruction;
- rolling summary plus directly relevant prior statements;
- remaining rounds;
- required structured response shape.

The rolling summary is a convenience, not the audit record. Original transcript events remain canonical.

### User Intervention Ordering

User interventions must be persisted before they are acknowledged.

- A general user statement becomes context for subsequent turns.
- A nominated question inserts a targeted speaking step.
- Agenda changes apply from the next unstarted step.
- Pause prevents new provider calls but does not pretend to stop a provider call already in flight.
- A late provider response received after cancellation is stored as ignored evidence and must not advance state.

### Realtime UI

Phase 1-3 may use incremental polling with `after=<sequence>` because the current server already supports similar patterns. A new realtime transport is not required for this child requirement.

The UI must rebuild entirely from meeting detail plus events after refresh.

## Phase Review

### Phase 1 Gate

Must prove:

- legal and illegal transitions;
- atomic sequence allocation;
- occupancy conflicts;
- event deduplication;
- restart reconciliation;
- legacy read compatibility;
- UI rendering of persisted executable state.

No AI provider call is allowed in Phase 1 tests.

### Phase 2 Gate

Must prove:

- user form validation;
- provider-neutral invocation of available agents;
- one opening statement per participant;
- bounded moderator-directed rounds;
- early completion;
- durable transcript and structured result;
- full UI refresh recovery.

Phase 2 should reject busy providers with a clear message. It must not claim to pause their existing work.

### Phase 3 Gate

Must prove:

- event-ordered user speech, context, questions, and agenda changes;
- pause/resume without replay;
- cancellation and late-response handling;
- early ending through summarization;
- moderator failure takeover;
- no-consensus user arbitration.

## API Direction

Exact paths may follow repository conventions, but the behavioral surface must cover:

- create executable meeting
- start meeting
- get meeting detail
- get events after sequence
- submit user intervention
- pause/resume/cancel/end
- submit arbitration decision
- replace moderator

All mutating calls require an expected meeting version or idempotency key.

## Compatibility

- Existing `/api/meetings/active` and `/api/meetings/history` remain readable.
- Executable meetings project into the current active/history UI model.
- Existing record-only clients continue to create or display legacy meetings unless they explicitly request executable behavior.
- Existing office animation continues to consume active participant IDs.
- The main office canvas should consume the same executable active projection as the Meetings center, or an equivalent canonical server projection, so active executable meetings move participants into the existing meeting-table/1:1 visual behaviors without relying on the Meetings modal being open.

## Security and Permissions

- Phase 1-3 contains only user-started meetings.
- User interventions are authoritative and auditable.
- Initial and added context must be explicitly provided by the user; automatic workspace discovery is excluded.
- Provider prompts must not include unrelated chat or project data.
- Provider errors and approval requirements must be shown, not automatically bypassed.

## Observability

Each event records:

- meeting ID
- event ID and sequence
- meeting version
- actor type and actor ID
- stage and round
- related participant
- provider call ID where applicable
- timestamp
- status and bounded error metadata

Logs must correlate provider calls with meeting and event IDs without logging secrets.

## Testability

The orchestrator and provider adapter must support deterministic fake providers. Automated tests must not require live AI accounts for state-machine, ordering, pause, arbitration, or restart coverage.

Each Phase has:

- focused unit tests;
- HTTP integration tests;
- browser or DOM acceptance;
- a full manual gate.

## Risks and Mitigations

1. **Duplicate turns after restart**
   - Persist pending-call IDs and completion events before advancing.
2. **Pause race with an in-flight provider**
   - Do not start new calls; mark late responses according to current state.
3. **Cross-provider output inconsistency**
   - Normalize through a strict adapter and preserve raw text.
4. **Long context**
   - Use rolling summaries and relevant statement selection while retaining original events.
5. **Legacy meeting corruption**
   - Keep migration/projection explicit and test old fixtures.
6. **User intervention ordering**
   - Serialize through the persisted event queue rather than direct thread mutation.
7. **Meeting center and canvas drift**
   - Make `/status` or its replacement include active executable meeting projection used by the canvas, and cover both legacy and executable meetings in regression tests.

## Review Conclusion

Phase 1-3 can proceed together with independent gates. The implementation must establish the state machine first and must not hide later Phase 4-7 capabilities inside the MVP. No blocking clarification remains.
