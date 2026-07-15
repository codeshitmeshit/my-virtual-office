# Task 5.4 Optimistic History Reconciliation

Recorded: 2026-07-14 (Asia/Shanghai)

## Defect evidence

The reported Codex request `你 cli 的会话 ID 是多少？` appeared twice in the chat UI, while both the communication ledger and `/api/chat/history` contained exactly one persisted user request. The duplicate was a client presentation defect: the live-layer optimistic bubble remained after authoritative history rendered the same request.

## Implemented contract

- The UI creates the `idempotencyKey` before optimistic rendering and attaches it to the optimistic Store record, live DOM node, and provider request.
- Normalized authoritative history exposes the communication record's metadata `idempotencyKey`.
- `ChatHistoryStore.mergePage` replaces only a user-side `optimistic-*` record with an authoritative user record carrying the exact same key in the same provider/conversation entry.
- Reconciliation notifies the active history view, which removes only the matching live-layer node.
- Same-text requests with different keys remain distinct; no text/time heuristic is used.
- Authoritative timestamps, IDs, status, and attachment metadata win after reconciliation.
- Existing explicit optimistic cleanup on rejected or failed sends remains in place.

## Verification

```text
node tests/check_chat_history_store.mjs
# chat history store checks passed

node tests/check_chat_history_navigation.mjs
# chat history navigation checks passed

node tests/check_chat_bug_regressions.mjs
# chat bug regression checks passed

VO_CDP_URL=http://127.0.0.1:9224 VO_TEST_URL=http://127.0.0.1:8090 \
  node tests/chat_history_ui_e2e.mjs
# chat history UI E2E passed

PYTHONPYCACHEPREFIX=/private/tmp/cosh-pycache .venv/bin/python -m pytest \
  tests/test_chat_history_api.py tests/test_feishu_notifications.py -q
# 65 passed

PYTHONPYCACHEPREFIX=/private/tmp/cosh-pycache .venv/bin/python -m pytest \
  tests -q --ignore=tests/test_workflow_e2e.py
# 700 passed
```

After restarting the supported local service on port 8090, the real history API returned one matching persisted request with its exact original key:

```json
{
  "matches": 1,
  "id": "50d15dbc-35a2-4202-8638-ef2dd750d528",
  "idempotencyKey": "office-1784008904451-a8j2001fz3f"
}
```

The UI E2E was run against an isolated headless Chrome profile on port 9224. It creates an optimistic live-layer user bubble, merges an authoritative history record with the same key, and asserts that the live bubble count becomes zero, the authoritative history count becomes one, and the visible matching text count is exactly one.

The first browser run exposed an additional virtual-window edge: reconciliation succeeded in the Store and removed the live bubble, but a 50-item `latest` window did not expand to mount the new authoritative 51st item. The view now treats reconciliation at the newest boundary like a live append and expands the range. The complete browser suite then passed with the existing 160-root virtualization bound intact.

## Authoritative fallback duplicate follow-up (2026-07-15)

A real 8090 browser replay found that `/api/codex/runs` could persist the user
request and a subsequent `/api/codex/chat` fallback could persist it again with
a different event ID but the same `idempotencyKey`. The fix now enforces the
request identity at three boundaries:

- the communication writer atomically reuses an existing request scoped by
  conversation, agent, and idempotency key;
- visible communication history collapses legacy authoritative duplicates;
- `ChatHistoryStore.mergePage` retains the earliest authoritative user record
  for an idempotency key and still removes its optimistic counterpart.

Verification evidence:

- real browser before fix: two history-layer nodes for
  `office-1784032714970-arctnwksbhk`;
- real browser after restart: one node for that key and `duplicateKeys: []`;
- cache-enabled browser E2E passed with optimistic + two authoritative IDs;
- focused regression suite: 76 passed;
- full Python suite: 705 passed.
