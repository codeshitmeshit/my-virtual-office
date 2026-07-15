# Tasks 5.5–5.8: Feishu live history synchronization

Date: 2026-07-14

## Root cause

The Feishu SSE endpoint continued to emit `message` and `delivery`, but Chat History V2 refreshed `/api/chat/history` using the active provider conversation ID. Feishu ledger rows use a separate `feishu-dm:*` conversation ID, so the authoritative refresh excluded them. Two UI details compounded the symptom: `ready` did not invalidate history, and repeated activation/latest-page refresh could restore an older virtual range instead of mounting a newly appended authoritative row.

## Implementation

- Normalized history admits cross-conversation rows only when they are positively identified as Feishu-originated, visible, and involve the selected Agent.
- Feishu delivery-operation rows remain excluded from visible history.
- SSE `ready`, `message`, and `delivery` coalesce into an authoritative history refresh; invalidations arriving during a request cause one trailing refresh.
- Refreshing the already-active history entry preserves its virtual window.
- A latest authoritative page advances the virtual window only when it was already at the newest records.
- The browser regression covers request, reply/delivery invalidation, reconnect/ready recovery, and exactly-once DOM rendering.

## Automated verification

```text
.venv/bin/python -m pytest -q tests/test_chat_history_api.py tests/test_feishu_notifications.py
67 passed

PYTHONPYCACHEPREFIX=/private/tmp/cosh-pycache .venv/bin/python -m pytest tests -q --ignore=tests/test_workflow_e2e.py
702 passed in 65.17s

cd integrations/feishu-channel-worker && npm test
21 passed

node tests/check_chat_history_store.mjs
chat history store checks passed

node tests/check_chat_history_navigation.mjs
chat history navigation checks passed

node --experimental-websocket tests/chat_history_ui_e2e.mjs
chat history UI E2E passed (Feishu live request/reply/reconnect once)

openspec validate migrate-feishu-chat-to-channel-sdk --strict
Change 'migrate-feishu-chat-to-channel-sdk' is valid
```

Bits Remote UT was not applicable because this repository has no Go module or Bits pipeline.

## Local 8090 acceptance

The existing 8090/8091 service was stopped, both ports were verified free, and the service was restarted with `./start.sh`.

- HTTP 8090 and WebSocket 8091 health checks passed.
- Effective Feishu transport: `channel-sdk-node`.
- Worker status: connected/running, SDK connected, spool entries `0`.
- A Feishu self-test produced SSE `message` ×2 and `delivery` ×1.
- Querying normalized history with provider conversation ID `acceptance-provider-conversation` returned the self-test Feishu request and reply from `agent-platform-communications`, despite their persisted `feishu-dm:*` conversation identity.
- The non-visible delivery operation did not appear as a chat message.

The local 8090 service remains running for reviewer acceptance.
