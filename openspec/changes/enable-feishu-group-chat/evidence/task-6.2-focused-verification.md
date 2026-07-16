## Task 6.2 Focused Verification

Date: 2026-07-16

### Python Feishu, history, and Provider paths

```bash
.venv/bin/python -m pytest -q \
  tests/test_feishu_notifications.py \
  tests/test_chat_history_api.py \
  tests/test_provider_conversations.py \
  tests/test_openclaw_conversation_boundary.py \
  tests/test_codex_server.py \
  tests/test_claude_code_server.py \
  tests/test_hermes_server_native_api.py
```

Result: **151 passed in 4.81s**.

This covers private compatibility, group admission/text/rich-post image, Hermes/Codex/Claude Code/OpenClaw dispatch metadata, source-message idempotency, same-group ordering, cross-group progress, pressure metrics, group reply/thread placement, delivery failures, audit visibility, history/SSE isolation, public API redaction, notification/card-action isolation, and legacy transport rollback behavior.

### Node worker protocol, policy, spool, status, and capacity

```bash
cd integrations/feishu-channel-worker
npm test
```

Result: **23 passed, 0 failed**.

The run includes authenticated commands, strict v1 validation, identity/thread/resource preservation, direct bot mention policy, `@all`/bot-loop rejection counters, atomic status, rate-limited redacted logs, durable spool/replay, callback recovery/timeout, global callback limit 16, per-chat depth 20, queue pressure, and spool-full behavior.

One transient startup-network warning (`ENOTFOUND open.feishu.cn`) was intentionally injected by the recovery test; the associated reconnect scenario passed.

### Static UI and history contracts

```bash
node tests/check_feishu_group_chat_config_static.mjs
node tests/check_chat_history_store.mjs
node --check app/chat.js
node --check tests/chat_history_ui_e2e.mjs
```

Result: all commands passed.

The deterministic browser acceptance now injects group request/delivery/reconnect SSE payloads and asserts zero history refreshes and zero bubbles, then injects one private event and asserts exactly one refresh. The in-app browser could open the local app once, but subsequent navigation/reload attempts timed out in the browser-control environment; the complete browser script remains scheduled for the final verification task rather than being reported as executed here.

### Intentional compatibility changes

- Group chat remains default-off and requires the Node Channel SDK transport; legacy Python remains private-only.
- Private send, history visibility, SSE refresh, binding, notification, and card-action behavior remain unchanged.
- Group request/reply/delivery rows remain durable internally but are invisible to office history and redacted or excluded from public APIs.
- Group completion uses reply-to-source semantics; private completion continues to use the existing send operation.
- Source-message idempotency now uses atomic per-source status files and backfills from legacy JSONL records on first lookup.

### Focused conclusion

No focused regression remains. Real-tenant acceptance and the broader repository regression matrix are intentionally deferred to Tasks 7.2 and 7.3.
