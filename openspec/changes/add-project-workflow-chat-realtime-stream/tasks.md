## 1. Baseline and Contracts

- [ ] 1.1 Characterize current 2.5-second workflow-chat polling latency, request volume, four-Provider snapshot output, active/terminal transitions, refresh recovery, scrolling, and project/task/attempt switching without recording conversation content.
- [ ] 1.2 Define the project stream route, server-resolved scope/version, event names, heartbeat, cursor/replay, recovery-required, terminal settlement, empty/not-found, status/error, sanitization, and rollback contracts with HTTP/SSE fixtures.

## 2. Project-Scoped Stream Service

- [ ] 2.1 Add a focused project workflow-chat stream service that reuses `ProjectWorkflowChatService` scope resolution and injected Provider journal readers without importing `server.py`, launching Provider work, or mutating project/history state.
- [ ] 2.2 Implement strict project/task/attempt/review/Agent/Provider/conversation filtering, opaque scope versioning, scope-change invalidation, bounded replay, heartbeat, disconnect cleanup, and content-free diagnostics.
- [ ] 2.3 Register a thin `GET /api/projects/{projectId}/workflow/chat/events` transport delegate and verify compatible inactive/not-found behavior, `Last-Event-ID`, malformed cursor handling, slow/disconnected clients, and no locks held while waiting or writing.

## 3. Canonical Event Projection

- [ ] 3.1 Route Codex, Claude Code, Hermes, and OpenClaw eligible project events through the existing canonical `timelineItem` projector and public-payload sanitization without adding Provider parsing to the project service or client.
- [ ] 3.2 Verify message, reasoning, tool, approval, run, recovered-history, terminal, duplicate, out-of-order, malformed, oversized, sensitive, and cross-scope event behavior for all four Providers.
- [ ] 3.3 Add snapshot/stream race fixtures proving canonical identity/version reconciliation is deterministic whether the snapshot or matching event arrives first.

## 4. Project Client Hybrid Transport

- [ ] 4.1 Add a focused Project Execution chat stream controller that opens only for the visible eligible project scope, tracks event cursors and scope versions, and closes on view/project/task/attempt changes.
- [ ] 4.2 Reconcile only canonical `timelineItem` values into project chat model state while preserving existing rendering, labels, expansion, truncation, tool summaries, timestamps, scroll position, and bottom-follow behavior.
- [ ] 4.3 Buffer events during initial snapshot load, refresh the authoritative snapshot after terminal/recovery-required events, ignore stale-scope events, and prove no duplicate or lost items across switching and concurrent refresh.
- [ ] 4.4 Retain bounded fallback polling for stream failure/unsupported environments, use a measured lower-frequency reconciliation cadence while healthy, and restore fast fallback automatically after disconnect.

## 5. Recovery, Performance, and Security

- [ ] 5.1 Exercise EventSource reconnect, replay within retention, cursor gaps, application restart, journal eviction, offline/online transitions, hidden/visible views, concurrent polling, and one-Provider-unavailable scenarios.
- [ ] 5.2 Verify payload bounds, allowlisting, secret/header/token/path redaction, scope isolation, rate-limited content-free diagnostics, resource cleanup, and bounded per-client/server stream state.
- [ ] 5.3 Compare before/after active-update median/p95 latency, unchanged workflow-history reads, response/event bytes, concurrent stream cost, Provider calls/writes, cache behavior, and lock-held work; reject material regressions outside the intended latency/load improvement.

## 6. Rollout and Acceptance

- [ ] 6.1 Add a reversible project-stream configuration switch and verify per-Provider enablement plus immediate rollback to characterized 2.5-second polling with no data repair.
- [ ] 6.2 Run project execution, workflow chat, canonical timeline, Provider journal/SSE, HTTP, browser UI, refresh/restart, scope-isolation, approval/cancellation, startup, and static boundary regression suites.
- [ ] 6.3 Produce a four-Provider acceptance matrix mapping every specification scenario to automated evidence, documenting measured latency/load improvement, fallback behavior, residual transient limits, and unchanged product presentation.
