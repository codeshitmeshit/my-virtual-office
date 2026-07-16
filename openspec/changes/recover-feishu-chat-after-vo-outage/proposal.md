## Why

Feishu Agent Chat can keep its WebSocket worker alive while VO is unavailable or unresponsive, but callback failures that outlive the immediate retry window leave durable inbound messages stranded until a narrow recovery path or manual restart happens. Operators can also see a connected channel while the VO processing path is degraded, so the failure is neither self-healing nor clearly visible.

## What Changes

- Add automatic recovery for durable Feishu Agent Chat inbound messages after VO becomes responsive again, without requiring a new Feishu message, configuration toggle, or process restart.
- Start recovery within one minute of VO callback availability returning, continue retrying retained messages until durably acknowledged, and preserve user-visible exactly-once outcomes and deterministic per-conversation order.
- Keep accepting and isolating work across conversations within bounded safety limits so one degraded conversation does not silently disable the entire Feishu Chat channel.
- Add a Feishu message-processing status bar to the VO control panel that distinguishes WebSocket connectivity from VO callback-processing health and exposes redacted backlog and recovery state.
- Add observable degraded/recovering states, backlog count, oldest pending age, recent successful processing time, retry progress, and threshold-based operator warning while background recovery continues.
- Limit this change to Feishu Agent Chat inbound processing and its worker-to-VO callback path; notification/card-action applications and standalone outbound-operation recovery remain unchanged.

## Capabilities

### New Capabilities

- `feishu-agent-chat-resilience`: Defines outage retention, automatic callback recovery, ordering/idempotency guarantees, bounded degradation behavior, and control-panel visibility for Feishu Agent Chat inbound processing.

### Modified Capabilities

None.

## Impact

- Affected runtime areas include the Feishu Channel worker callback/replay lifecycle, durable inbox status, VO worker supervision/status projection, and Feishu control-panel rendering.
- Existing Feishu Agent routing, persistent source-message idempotency, conversation ordering, history, notification/card-action integration, and outbound command behavior must remain compatible.
- Focused worker, server-status, and control-panel tests will need outage, recovery, ordering, duplicate, backlog, and observability scenarios.
