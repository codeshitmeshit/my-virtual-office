## Why

Codex approval requests created by Feishu-originated turns are currently visible only in the Virtual Office web chat and polling APIs. A Feishu user can therefore leave a turn waiting on an approval that they never receive, while the office may misleadingly appear idle.

## What Changes

- Deliver every Codex command, file-change, and permission approval to the human who initiated the Feishu turn.
- Prefer the configured Feishu notification application; if it is unavailable or delivery fails, fall back to the originating Feishu Chat App conversation.
- Let either approval card approve once or cancel the original Codex turn, with one effective decision across duplicate, retried, or late card actions.
- If neither Feishu application can deliver the card, stop the approval wait and send a visible failure reply to the originating chat instead of leaving the Agent stalled.
- Keep approval cards and card-action messages out of Virtual Office chat history while retaining separate delivery, callback, decision, and failure audit records; normal final Agent replies remain in history.

## Capabilities

### New Capabilities
- `codex-feishu-approval-routing`: Routes Codex approval requests and decisions through the preferred Feishu application with fallback, idempotency, failure closure, and chat-history isolation.

### Modified Capabilities

None.

## Impact

- Codex pending-approval lifecycle and normalized provider approval coordination.
- Feishu notification-card delivery and Feishu Chat App outbound delivery.
- Feishu card-action dispatch, authorization/linkage checks, idempotency, and card status updates.
- Provider event, notification, and callback audit surfaces.
- VO normalized chat-history filtering and Feishu live-history projection.
- Focused provider approval, Feishu notification, Chat App, callback, and history-isolation tests and documentation.
