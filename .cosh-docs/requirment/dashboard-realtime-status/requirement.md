# Dashboard Realtime Status

## Background

The Virtual Office control panel currently appears delayed: several sidebar messages, agent states, meeting states, and dashboard counters do not update in a way that feels immediate or trustworthy. Existing frontend behavior is based on multiple polling loops with different intervals, which can make the control panel feel inconsistent.

The proposed product direction is to make the control panel a near-realtime, trustworthy status surface. A unified event stream has been discussed as a possible product concept: the control panel would receive state-change events and update its summary UI incrementally, while still relying on full snapshots for initialization and correction.

## Target Users

- Primary user: the local Virtual Office operator who watches the control panel to understand what agents and meetings are doing.
- Secondary user: anyone using the office UI to decide whether to intervene in meetings, agent work, or project execution.

## Product Goal

Make the control panel a trustworthy near-realtime overview of the Virtual Office state, so users can quickly understand whether agents are working, idle, in meetings, blocked, or waiting for user action.

## Current Product Decisions

The following choices have been clarified by the user:

- Core problem: state trustworthiness.
  - The control panel should reduce stale or misleading status information.
- Initial scope: dashboard summary first.
  - Prioritize status counts, agent current status, meeting list, and activity log over every detail panel.
- Realtime expectation: near realtime.
  - Most important changes should appear within roughly 1-3 seconds.
- Activity log role: exception and action-required center.
  - The log should emphasize timeouts, failures, approvals, meeting conflicts, arbitration needs, and other items that need attention.
- Consistency priority: trustworthiness over raw freshness.
  - If event updates and full snapshots disagree, the UI should expose syncing or correction state instead of silently showing stale data.
- Phase scope: status overview plus meeting summary.
  - Status counts, agent current status, active meeting list, and pending meeting requests must be near-realtime in this phase.
  - Project summary is not required for the first phase.
- Activity log event policy: only events needing user action.
  - The activity log should prioritize meeting requests, conflicts, approvals, timeouts, failures, arbitration needs, and other user-action-needed items.
- Sync-state expression: status indicator plus explicit error or reconnect hints.
  - Normal state can stay low-noise; degraded or reconnecting state should be visible.
  - The control panel should explicitly show whether it is currently using the SSE realtime connection, reconnecting SSE, or polling fallback.
- Realtime fallback: explicit fallback notice.
  - If realtime updates disconnect, the control panel should keep working through fallback refresh and tell the user that it is degraded.
- Success standard: perceived latency plus accuracy.
  - Important dashboard state should update within 1-3 seconds in normal conditions.
  - Dashboard state should remain consistent with backend snapshots after reconnect or correction.
- Implementation packaging: new code should live in small dedicated modules.
  - Frontend realtime dashboard behavior should be added through a new JS file instead of expanding `app/game.js`.
  - Backend dashboard event-stream behavior should be added through a new Python file instead of expanding `app/server.py` more than necessary.
  - Existing large files may keep thin integration hooks, but the main new behavior should be isolated so the codebase can gradually move away from large coupled files.

## Proposed Scope

### In Scope

- Improve the control panel's perceived freshness for high-level office state.
- Make agent and meeting status changes easier to trust.
- Ensure action-required events are visible in the activity log or equivalent dashboard area.
- Preserve a snapshot-based fallback so the panel can recover from missed events or reconnects.
- Show enough sync state for users to understand when the panel may be stale or reconnecting.
- Show the current dashboard update mode: SSE connected, SSE reconnecting, or polling fallback.
- Keep status overview and meeting summary near-realtime:
  - working / idle / meeting / break counts.
  - agent current state and task summary used by the sidebar.
  - active meeting list.
  - pending meeting requests.
- Show only action-required events in the activity log for this phase.

### Out of Scope For Now

- Turning every chat, meeting detail, project detail, skill library view, and metric panel into a full realtime surface.
- Showing every provider token, every tool progress event, or every internal trace in the activity log.
- Replacing existing detail pages or workflows.
- Treating the activity log as a complete audit trail.
- Project summary realtime updates.

## Final Product Clarification Answers

- Dashboard summary areas: B. Status overview plus meeting summary.
- Activity log priority: A. Only events needing user action.
- Sync-state expression: B. Status indicator plus explicit error/reconnect hints.
- Realtime fallback behavior: B. Visible fallback / degraded refresh hint.
- Success standard: A+B. Perceived latency and accuracy / consistency.

## Constraints

- The dashboard should remain calm and scannable; realtime updates must not turn it into a noisy feed.
- The activity log should prioritize attention-worthy items, not every background message.
- Existing user workflows should continue to work if realtime updates are unavailable.
- The UI should make stale or reconnecting state visible enough to preserve trust.
- The UI should make the active update mode visible enough that the user can tell whether the control panel is using SSE or fallback polling.
- New implementation should prefer new focused JS/Python modules, with only minimal integration hooks in existing large files.

## Non-Goals

- A complete event-audit system.
- A developer trace viewer.
- A replacement for meeting detail transcript views.
- A high-frequency token-level streaming display in the control panel.
- A broad refactor of all existing `game.js` or `server.py` responsibilities.
