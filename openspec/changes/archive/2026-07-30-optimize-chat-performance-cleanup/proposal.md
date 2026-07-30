## Why

The previous Codex chat fast path made warm chat visibly faster, but the Provider bridge area still carries old run-bridge implementations that are bypassed by the current routed server path. Those remnants make the code harder to reason about, keep stale static anchors alive, and increase the risk that future changes accidentally revive obsolete run/idempotency authorities.

There is also a smaller second layer of performance work left in the active chat hot path. Current Codex event handling still performs repeated sanitization, defensive copying, telemetry locking, and generic journal processing for events that have already passed through a Codex-specific fast path. These costs are much smaller than the pre-fast-path file rewrite bottlenecks, but they are now the next credible optimization target.

## What Changes

- Prove and remove unused legacy Provider bridge code from the chat bridge split, including `ProviderRunBridge`, `PROVIDER_RUN_BRIDGE`, old Codex/provider idempotency maps, and copied run-start/event implementations that are not reached after route hydration.
- Replace stale module-split test markers that require obsolete bridge symbols with markers for the current service boundary: `ProviderRunCoordinator`, `ProviderEventJournal`, and `PROVIDER_SSE_TRANSPORT`.
- Preserve the public `/api/codex/*`, `/api/hermes/*`, and `/api/claude-code/*` chat/run contracts and the current route hydration behavior.
- Add an explicit verification fixture proving that `server_routes.agent_bridges` resolves to the authoritative `server.py` implementations before serving run/chat routes.
- Optimize the active Codex hot path by avoiding duplicate sanitize/deepcopy work where an internal payload is already bounded and trusted.
- Review and, where safe, reduce high-frequency transient event telemetry overhead without changing durable terminal, approval, history, or replay semantics.
- Re-run focused bridge, fast-path, SSE, and route-split regressions plus deterministic performance comparison evidence.

## Capabilities

### New Capabilities

- `chat-bridge-cleanup-and-performance`: Defines the code cleanup, proof-of-unused, hot-path optimization, compatibility, and measurement requirements for the current chat bridge.

### Modified Capabilities

None. The previous Codex fast-path work is implementation and evidence context for this change; the new behavior contract is captured by `chat-bridge-cleanup-and-performance`.

## Impact

- Affects chat bridge routing, `server_services/agent_bridges.py`, module-split static checks, Provider run/SSE tests, Codex fast-path event processing, Provider event journal internals, and performance fixtures.
- Does not redesign public routes, change Provider response schemas, remove flag-off rollback semantics, or alter durable chat, approval, cancellation, history, terminal, thread mapping, or SSE replay guarantees.
- Does not claim model latency improvements or real-Provider capacity-8 proof; performance claims remain bounded to deterministic local fixtures unless separately measured.
