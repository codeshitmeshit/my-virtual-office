# Review: Dashboard Realtime Status

## Review Status

Status: reviewed.

The product boundary is now clear enough to generate an initial checklist. The first phase is limited to dashboard status overview and meeting summary, with action-required activity log entries and visible sync/fallback state.

## Product Review

### Clear Points

- The main product value is dashboard trustworthiness, not novelty of streaming.
- The first phase should focus on the control panel summary instead of the entire app.
- The experience target is near-realtime, roughly 1-3 seconds for important state changes.
- The activity log should behave more like an action-required or exception center than a complete message feed.
- Snapshot correction and visible sync state are part of the product promise.

### Product Decisions From Final Clarification

1. Dashboard scope: status overview plus meeting summary.
   - Include status counters, agent current status, active meetings, and pending meeting requests.
   - Exclude project summary from this first phase.

2. Activity log policy: only events needing user action.
   - Include approvals, meeting confirmations, conflicts, timeouts, failures, arbitration needs, and other user-action-required states.
   - Exclude normal agent chatter, every provider progress tick, and complete audit-style process history.

3. Sync-state presentation: status indicator plus explicit error/reconnect hints.
   - Use low-noise presentation in normal state.
   - Clearly communicate degraded, reconnecting, or fallback refresh state.

4. Realtime fallback: explicit fallback notice.
   - Continue to serve the dashboard through fallback refresh.
   - Do not let users assume realtime is active when it has disconnected.

5. Success metric: latency plus accuracy.
   - Important state should normally appear within 1-3 seconds.
   - Reconnect and correction should converge to backend snapshot state.

## Technical Review

Technical review found no product-blocking technical issue.

Existing implementation has several relevant surfaces:

- `/status` currently feeds the sidebar state and counts through polling.
- `/agent-chat` currently feeds agent bubbles through polling.
- `/api/meetings/active` and meeting request endpoints feed meeting summary through polling.
- Meeting detail already has a live-events concept with polling.
- Provider-specific SSE surfaces already exist, so a streaming response pattern is already present in the server.

Technical topics to handle during implementation:

- Event source and event taxonomy.
- Snapshot initialization and reconciliation behavior.
- Reconnect and stale-state behavior.
- Frontend state ownership between dashboard data, meeting data, agent data, and project data.
- Noise control for high-frequency progress events.
- Compatibility with existing polling fallback.
- Observability for missed events, reconnects, and snapshot correction.

Recommended technical direction for the checklist:

- Keep existing snapshot endpoints as initialization and fallback sources.
- Add a dashboard event stream for incremental status and meeting-summary updates.
- Use a small event taxonomy for this phase rather than a complete app event bus.
- Coalesce or throttle noisy status changes so the panel stays calm.
- Represent connection state in the dashboard UI.
- The connection state UI should distinguish SSE connected, SSE reconnecting, and polling fallback modes.
- Put new frontend realtime dashboard logic in a focused JS module.
- Put new backend dashboard event-stream logic in a focused Python module.
- Limit changes in existing large files to wiring, route registration, and calling into the new modules.

## Decision

Generate `checklist.md` and wait for user confirmation before creating `todolist.md`.
