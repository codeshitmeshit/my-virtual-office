## Why

Project Execution chat currently refreshes on a 2.5-second polling cycle, so active Provider output is only near-real-time and repeatedly rereads unchanged history. The canonical conversation timeline and Provider SSE projection now make it possible to deliver attempt-scoped updates immediately without reintroducing Provider-specific client logic.

## What Changes

- Add a project-scoped workflow-chat event stream that resolves the current project, task, attempt, Agent, Provider, and conversation on the server.
- Deliver canonical `timelineItem` updates for Codex, Claude Code, Hermes, and OpenClaw while preserving the existing workflow-chat snapshot endpoint and response contract.
- Reconcile streamed items through the same canonical timeline identity, ordering, lifecycle, reasoning, and tool semantics used by snapshot reads.
- Retain bounded polling and snapshot refresh as recovery mechanisms for disconnects, application restarts, missed or non-durable Provider events, and final terminal settlement.
- Rebind or close the stream when the selected project execution scope changes so stale attempts cannot update the current project chat.
- Preserve the existing Project Execution chat UI; this change improves transport latency and read efficiency rather than redesigning presentation.

## Capabilities

### New Capabilities

- `project-workflow-chat-realtime`: Defines project-scoped canonical timeline streaming, reconnect/replay, scope changes, snapshot reconciliation, fallback polling, failure isolation, and latency/load acceptance across all four Providers.

### Modified Capabilities

None.

## Impact

- Affected backend areas include project workflow-chat transport, project execution scope resolution, Provider event-journal subscription, canonical timeline projection, and HTTP SSE routing.
- Affected frontend areas include Project Execution chat lifecycle, canonical item reconciliation, stream reconnect handling, visibility changes, and fallback polling cadence.
- The existing `GET /api/projects/{projectId}/workflow/chat` snapshot endpoint remains available and authoritative for durable recovery.
- No Provider launch, history persistence, approval/cancellation protocol, project persistence schema, or visual component redesign is introduced.
