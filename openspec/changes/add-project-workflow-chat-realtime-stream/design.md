## Context

Project Execution chat currently calls `GET /api/projects/{projectId}/workflow/chat` when the board opens and every 2.5 seconds while execution is active. Each read resolves the current task/attempt scope and projects Provider history through the canonical conversation timeline. This is correct and recoverable, but visible updates can lag by one polling interval and unchanged histories are repeatedly read.

Standard chat already consumes `GET /api/provider/events` using Server-Sent Events. The Provider event journal supports bounded replay with `Last-Event-ID`, heartbeat/snapshot events, and an additive canonical `timelineItem` produced by the shared timeline projector. Project Execution can reuse those authorities, but it must resolve scope from the project on the server rather than trusting a client-supplied Provider, Agent, or conversation tuple.

This change follows completion of `unify-conversation-timeline-projections`; it depends on that change's canonical identity, lifecycle, ordering, deduplication, sanitization, and Provider coverage rather than recreating them.

## Goals / Non-Goals

**Goals:**

- Make eligible Project Execution chat activity visible with event-stream latency for Codex, Claude Code, Hermes, and OpenClaw.
- Bind every stream and event to the current project/task/attempt/Agent/Provider/conversation scope.
- Reuse canonical `timelineItem` projection and reconciliation for both snapshot and live updates.
- Preserve durable snapshot recovery, bounded replay, terminal settlement, and a polling fallback.
- Reduce repeated unchanged workflow-history reads without weakening recovery.
- Keep lifecycle ownership, cleanup, reconnect, and visibility behavior independently testable.

**Non-Goals:**

- Redesign Project Execution chat components, labels, expansion, truncation, or scrolling.
- Guarantee persistence of Provider events that are transient under existing contracts.
- Change Provider launch, approval, cancellation, continuation, or native history formats.
- Remove the workflow-chat snapshot endpoint.
- Introduce WebSocket infrastructure, a new durable event store, or cross-process journal coherence.

## Decisions

### 1. Add a project-scoped SSE endpoint

Add `GET /api/projects/{projectId}/workflow/chat/events`. The handler delegates to a focused service that reuses `ProjectWorkflowChatService` to resolve the authorized current scope, then subscribes only to matching Provider journal events.

The browser does not provide authoritative Provider, Agent, task, attempt, or conversation identifiers. An optional opaque scope/version token may be used only to detect that the server's resolved scope changed.

Alternative considered: connecting Project Execution directly to `/api/provider/events` was rejected because it makes the client reconstruct authoritative project scope and complicates attempt-switch isolation.

### 2. Keep snapshot-first hybrid delivery

On opening Project Execution chat, the client first reads the existing workflow-chat snapshot and then opens the scoped stream. Canonical identities reconcile any event that overlaps the snapshot. A terminal event triggers a debounced authoritative snapshot refresh to settle durable messages and Provider data that was not streamed.

EventSource reconnect and bounded journal replay cover short interruptions. If the stream is unavailable or recovery indicates a cursor gap, the client refreshes the snapshot and enables fallback polling. During a healthy stream, polling becomes low-frequency health/reconciliation polling rather than the primary update path.

Alternative considered: pure SSE was rejected because Provider durability and event completeness differ, and application restart can discard allowed transient state.

### 3. Reuse the canonical timeline item as the only live model input

The stream retains compatible Provider event names where useful, but Project Execution message state changes only from sanitized canonical `timelineItem` values or a full canonical snapshot. The project client does not parse native Provider payloads or derive identity, status, reasoning accumulation, tool transitions, or order.

Presentation-only mapping remains local: existing labels, details elements, truncation, and scroll behavior do not move into the timeline service.

### 4. Treat scope changes as stream boundaries

The server attaches an opaque scope digest/version to the initial stream snapshot and every event. If the current task/attempt scope changes, the server emits `workflow.scope.changed` and closes the old stream. The client discards queued events from the old version, loads a fresh snapshot, and opens a new stream.

No event lacking a matching project and resolved scope may update the visible project chat.

### 5. Preserve bounded transport and recovery behavior

Reuse Provider journal retention, payload sanitization, canonical item bounds, heartbeat cadence, and `Last-Event-ID` handling. The project stream must not hold project/workflow locks while waiting or writing. Slow/disconnected clients are closed without affecting Provider execution.

Diagnostics record only project/scope digests, event IDs, counts, state, and latency; they exclude message/reasoning content, tool payloads, credentials, headers, tokens, and unrestricted paths.

### 6. Roll out behind a reversible transport switch

Keep existing polling behavior available behind a runtime/configuration switch during rollout. Enable the stream per Provider after parity, replay, scope-isolation, and browser recovery tests pass. Rollback disables project SSE and restores the existing 2.5-second polling path without data repair because the change introduces no persistence migration.

## Risks / Trade-offs

- **[Snapshot/stream race duplicates or drops an item]** → Reconcile by canonical identity/version, buffer events during the initial snapshot, and test both ordering directions.
- **[Attempt changes while the old stream is connected]** → Use a server-issued scope version, close on scope change, and reject stale events client-side.
- **[Provider does not publish every visible record]** → Refresh on terminal events and retain low-frequency/failure polling.
- **[Journal cursor is unavailable after restart or retention overflow]** → Signal recovery-required and replace from an authoritative snapshot instead of fabricating replay.
- **[More long-lived HTTP connections consume resources]** → Open only while the project view is active, use heartbeat/idle cleanup, and measure concurrent stream limits.
- **[Two transports become two semantic authorities]** → Both carry canonical items; polling/SSE select transport and recovery timing only.

## Migration Plan

1. Freeze polling latency/load and four-Provider snapshot behavior.
2. Add the project-scoped backend stream and scope-version contract without changing the client.
3. Add snapshot/stream reconciliation, reconnect, scope-switch, visibility, and terminal-refresh handling behind a disabled switch.
4. Verify each Provider against polling output and enable incrementally.
5. Reduce healthy-stream polling to the accepted recovery cadence while retaining automatic fast fallback.
6. Remove temporary comparison instrumentation after final parity and performance evidence.

Rollback disables the stream switch and restores the characterized polling path. Existing histories, event journals, projects, task attempts, and Provider sessions require no repair.

## Open Questions

- Select the healthy-stream reconciliation cadence from measured Provider completeness and load evidence; start with 10–15 seconds as a test range rather than a fixed product contract.
- Confirm whether `workflow.scope.changed` should close immediately or allow a final terminal event; isolation takes precedence if the two conflict.
