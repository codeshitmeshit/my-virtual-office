# Tasks 5.9–5.10: chat bottom initialization and follow behavior

Date: 2026-07-14

## Implemented behavior

- Opening Chat, switching Agent/conversation, and reopening a cached conversation move the virtual history window to its newest range and settle the physical scrollbar at the bottom.
- While the viewport is at or near the bottom, Feishu SSE refreshes, Provider terminal events, and delayed post-render layout changes keep the viewport pinned to the bottom.
- Scrolling away from the bottom disables follow mode and cancels pending settle timers.
- Authoritative latest-page refreshes preserve the first visible message and its visual offset while older history is being read.
- Returning to the bottom re-enables follow mode.

## Verification

- `node tests/check_chat_history_navigation.mjs` — passed.
- `node --experimental-websocket tests/chat_history_ui_e2e.mjs` — passed; covered bottom initialization, Feishu message/delivery/ready invalidations, older-history anchor preservation, resumed follow, delayed layout, and Provider completion.
- `.venv/bin/python -m pytest -q tests/test_chat_history_api.py tests/test_feishu_notifications.py` — 67 passed.
- `TMPDIR=/private/tmp/vo-pytest-tmp PYTHONPYCACHEPREFIX=/private/tmp/cosh-pycache .venv/bin/python -m pytest tests -q --ignore=tests/test_workflow_e2e.py` — 702 passed.
- `npm test` in `integrations/feishu-channel-worker` — 21 passed.
- `openspec validate migrate-feishu-chat-to-channel-sdk --strict` — passed.
- `git diff --check` — passed.

## Browser-cache acceptance follow-up

The initial E2E disabled the browser cache and therefore did not detect that the
production HTML still referenced pre-change asset URLs. The follow-up fix:

- versions `style.css`, `chat-history.js`, and `chat.js` with the shared
  `chat-bottom-follow` cache key;
- serves `/` and `.html` responses with `Cache-Control: no-cache` so the stable
  entrypoint revalidates those asset URLs;
- retains cache-enabled E2E coverage through `CHAT_E2E_DISABLE_CACHE=0`.

Post-restart verification: cache-enabled browser E2E passed, 68 focused Python
tests passed, the entrypoint returned `Cache-Control: no-cache`, and the Channel
SDK reported `connected` with zero spool entries.

The implementation remains uncommitted and the OpenSpec task checkboxes remain unchanged pending user CR and explicit commit approval.
