# Chat History Switching Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` when subagents are available, otherwise use `superpowers:executing-plans`. Execute every numbered checkbox in order and preserve unrelated worktree changes.

**Goal:** Make cached chat switching immediate, cold history recent-first and paged, and long conversations bounded to 160 mounted historical messages without losing rich content or live-event consistency.

**Architecture:** Add a same-origin provider-neutral history page endpoint in `app/server.py`, a shared runtime `ChatHistoryStore` and measured `ChatHistoryView` in `app/chat-history.js`, and narrow integration points in the existing `ChatWindow`. Keep provider-specific endpoints and `loadLegacyHistory()` as a temporary rollback path.

**Tech Stack:** Python standard-library HTTP server and file I/O, vanilla JavaScript, DOM/ResizeObserver/Performance APIs, Node static/unit-style tests, Python fixture tests, and CDP browser acceptance.

**Implementation visualization:** [PNG flow](./assets/implementation-flow.png) | [Mermaid source](./assets/implementation-flow.mmd)

## File Map

- Create `app/chat-history.js`: pure conversation identity, store, page merge, render cache, range calculation, anchor state, bounded view, and debug counters.
- Modify `app/server.py`: request validation, identity/cursor helpers, provider source adapters, lazy source snapshots, page merge, and `GET /api/chat/history`.
- Modify `app/chat.js`: ChatWindow history/live layer lifecycle, store activation, legacy fallback, rich-message rendering hook, optimistic/new-session mutations, provider/Gateway event merge, and Feishu keyed revalidation.
- Modify `app/index.html`: load `chat-history.js` after `marked.min.js`/`codex-reasoning.js` and before `chat.js`.
- Modify `app/style.css`: history/live layers, non-collapsing spacers, and loading/error states without changing panel layout.
- Create `tests/test_chat_history_api.py`: server helper and route-contract fixtures.
- Create `tests/check_chat_history_store.mjs`: pure store, identity, paging-state, range, and race tests.
- Create `tests/check_chat_history_navigation.mjs`: static integration and rollback-path checks.
- Create `tests/chat_history_performance.mjs`: controlled CDP fixture and long-history acceptance.
- Modify `tests/check_frontend_performance_static.mjs`: require bounded history runtime markers while preserving prior performance checks.

## Fixed Contracts

Server page helper and response:

```python
def _handle_chat_history_page(query):
    # Returns {ok, conversationKey, messages, nextCursor, hasMore, session}
    # or {ok: False, code, error, _status: 400}.
    request = _parse_chat_history_request(query)
    source_pages, session = _load_chat_history_source_pages(request)
    messages, next_cursor, has_more = _merge_chat_history_source_pages(
        source_pages, request.before, request.limit
    )
    return {
        "ok": True,
        "conversationKey": request.key,
        "messages": messages,
        "nextCursor": next_cursor,
        "hasMore": has_more,
        "session": session,
    }
```

Frontend runtime surface:

```javascript
globalThis.ChatHistoryRuntime = {
  createConversationKey,
  stableHistoryHash,
  computeWindowRange,
  ChatHistoryStore,
  ChatHistoryView,
  constants: {
    PAGE_SIZE: 50,
    DOM_WINDOW_MAX: 160,
    MESSAGE_LIMIT: 1000,
    INACTIVE_ENTRY_LIMIT: 8
  }
};
```

## 1. Identity, Cursor, and Request Contract

- [x] 1.1 Create `tests/test_chat_history_api.py` with failing cases for the shared UTF-8 FNV-1a fixture vectors, deterministic fallback IDs/versions, cursor round-trip, cursor ordering, malformed cursors, provider enum validation, identifier length limits, and `limit` clamping to 1-50.
- [x] 1.2 Run `PYTHONPYCACHEPREFIX=/tmp/vo-pycache python3 tests/test_chat_history_api.py`; verify RED because `_chat_history_hash`, `_encode_chat_history_cursor`, `_decode_chat_history_cursor`, and `_parse_chat_history_request` do not exist.
- [x] 1.3 Add the pure identity, canonical-field, cursor, and request-validation helpers near `_load_comm_history()` in `app/server.py`; return stable codes including `invalid_chat_history_request` and `invalid_chat_history_cursor` without logging identifiers or payloads.
- [x] 1.4 Add the same FNV-1a fixture vectors to `tests/check_chat_history_store.mjs`, initially loading a minimal `app/chat-history.js` runtime and asserting exact Python-compatible unsigned hexadecimal values.
- [x] 1.5 Create the initial `app/chat-history.js` IIFE with `stableHistoryHash()`, `createConversationKey()`, constants, and a `globalThis.ChatHistoryRuntime` export; do not touch DOM at module evaluation time.
- [x] 1.6 Run `PYTHONPYCACHEPREFIX=/tmp/vo-pycache .venv/bin/python tests/test_chat_history_api.py && node tests/check_chat_history_store.mjs`; verify GREEN for identity, cursor, and validation cases.

## 2. Unified History Page API

- [x] 2.1 Extend `tests/test_chat_history_api.py` with RED fixtures for Codex, Hermes, Claude Code, Gateway raw JSONL, communication/Feishu overlap, source-ID preference, fallback collision ordinal, chronological output, newest 50, older cursor pages, `hasMore`, session metrics, and rich text/media/tool/approval preservation.
- [x] 2.2 Add RED cache cases proving provider JSON snapshots are stat-invalidated, Gateway/communication snapshots extend lazily, concurrent reads are lock-safe, and cache limits are 32 entries/64 MiB.
- [x] 2.3 Run `PYTHONPYCACHEPREFIX=/tmp/vo-pycache .venv/bin/python tests/test_chat_history_api.py`; verify provider and paging cases fail before source adapters exist.
- [x] 2.4 Implement `_normalize_chat_history_message()`, `_chat_history_message_id()`, provider `page_before()` adapters, raw Gateway content-block parsing, communication-history paging, session metrics, and `_merge_chat_history_source_pages()` in `app/server.py`.
- [x] 2.5 Implement the `OrderedDict` plus `threading.RLock` source snapshot cache, inode/size/mtime-ns validation, lazy reverse JSONL extension, 1,000-record source cap, and estimated 64 MiB eviction.
- [x] 2.6 Add the same-origin `/api/chat/history` branch to `OfficeHandler.do_GET()` before legacy provider history branches; send JSON without `Access-Control-Allow-Origin: *` and preserve all old routes unchanged.
- [x] 2.7 Run `PYTHONPYCACHEPREFIX=/tmp/vo-pycache .venv/bin/python tests/test_chat_history_api.py`; verify GREEN for all four providers, paging, rich-content, cache, validation, and header cases.
- [x] 2.8 Run `PYTHONPYCACHEPREFIX=/tmp/vo-pycache .venv/bin/python -m py_compile app/server.py`; verify exit code 0.

## 3. Shared Conversation Store

- [x] 3.1 Expand `tests/check_chat_history_store.mjs` with RED cases for keyed entries, newest/older merge, stable-ID dedupe, version replacement, terminal-state precedence, latest-request dedupe, older-request dedupe by cursor, stale activation isolation, and live-event/history races.
- [x] 3.2 Add RED capacity cases for eight inactive entries, active-entry protection, 1,000 messages per entry, 12 MiB inactive model budget, 1,000/8 MiB sanitized HTML cache, and explicit abort on eviction or session invalidation.
- [x] 3.3 Run `node tests/check_chat_history_store.mjs`; verify RED because `ChatHistoryStore` behavior is not implemented.
- [x] 3.4 Implement `ChatHistoryStore` entry creation, active-view references, activation tokens, keyed request promises, latest/older page merge, message ordering, terminal-state precedence, session metrics, anchor/presentation state, and listener notification in `app/chat-history.js`.
- [x] 3.5 Implement count/byte LRU eviction and sanitized HTML LRU using two bytes per JavaScript string code unit for deterministic budget accounting; never evict active entries.
- [x] 3.6 Implement `fetchLatest()`, `fetchOlder()`, `applyLiveEvent()`, `insertOptimistic()`, `removeMessage()`, `invalidate()`, and retry-once behavior for `invalid_chat_history_cursor`.
- [x] 3.7 Run `node tests/check_chat_history_store.mjs`; verify GREEN for merge, race, request, eviction, and render-cache cases.

## 4. Bounded Dynamic History View

- [x] 4.1 Add RED pure cases to `tests/check_chat_history_store.mjs` for newest 50, 40-message shifts, 20-message overscan, maximum 160 range, navigation toward both ends, top/bottom spacer totals, and anchor delta calculation.
- [x] 4.2 Run `node tests/check_chat_history_store.mjs`; verify the new range/anchor cases fail.
- [x] 4.3 Implement `computeWindowRange()`, height accounting, presentation-state keys, and anchor-delta helpers as pure functions in `app/chat-history.js` until the RED cases pass.
- [x] 4.4 Implement `ChatHistoryView` with separate history/live layers, non-collapsing top/bottom spacers, one `ResizeObserver` observing mounted message roots, media remeasure hooks, capture-phase `details` toggle state, and `data-history-message-id` roots.
- [x] 4.5 Implement full bounded redraw only for activation/range/page changes and keyed single-message patch/append for live mutations; trim the opposite edge when a newest append would exceed 160 roots.
- [x] 4.6 Add `.chat-history-layer`, `.chat-live-layer`, and `.chat-history-spacer` rules to `app/style.css`, preserving the existing column gap, width constraints, overflow owner, and panel dimensions.
- [x] 4.7 Run `node tests/check_chat_history_store.mjs && node --check app/chat-history.js`; verify GREEN and valid syntax.

## 5. ChatWindow Selection and Panel Integration

- [x] 5.1 Create `tests/check_chat_history_navigation.mjs` with RED checks for script order, `CHAT_HISTORY_V2_ENABLED`, history/live layer initialization, `loadLegacyHistory()`, cache-first activation, no loading bubble on a cache hit, same-key refresh dedupe, and primary/secondary reopen reuse.
- [x] 5.2 Add RED checks that provider/Gateway new-session success invalidates the old key, activates an empty new key, and that attachment-only upload failure removes the optimistic model record as well as its DOM node.
- [x] 5.3 Run `node tests/check_chat_history_navigation.mjs`; verify RED before `ChatWindow` integration.
- [x] 5.4 Load `chat-history.js` in `app/index.html` immediately before `chat.js`, with a cache-busting version suffix matching repository conventions.
- [x] 5.5 In `ChatWindow` construction, create history/live layers inside `.chat-messages`, construct `ChatHistoryView`, and route historical rendering through the explicit parent while keeping streaming, typing, and activity in the live layer.
- [x] 5.6 Split current `loadHistory()` into `loadLegacyHistory()` plus the V2 activation/revalidation wrapper; preserve the entire legacy provider-specific implementation without semantic edits.
- [x] 5.7 Update `applySelection()`, `setPrimaryPanelOpen()`, and `setSecondaryPanelOpen()` to save the old anchor, render a cache hit synchronously, show loading only on a cold miss, reconnect streams, and schedule one keyed background refresh.
- [x] 5.8 Update `newSession()` and `sendMessage()` to keep store and DOM optimistic state atomic across successful reset, upload failure, archive-manager local reply, and provider send failure.
- [x] 5.9 Run `node tests/check_chat_history_navigation.mjs && node tests/check_chat_bug_regressions.mjs`; verify GREEN and preserve existing attachment/new-session regressions.

## 6. Rich Rendering and Live Event Reconciliation

- [x] 6.1 Add RED store/navigation fixtures for cached Markdown reuse, text/tool/thinking/approval/media/status version invalidation, interactive `details` restoration, and no reuse of approval/tool DOM bound to another `ChatWindow`.
- [x] 6.2 Add RED fixtures for provider `message.delta` versus terminal messages, tool start/complete/fail, approval request/resolved, Gateway final events, `session.message` recovery, and Feishu message/delivery keyed revalidation.
- [x] 6.3 Run `node tests/check_chat_history_store.mjs && node tests/check_chat_history_navigation.mjs`; verify RED for live-event and rich-rendering integration.
- [x] 6.4 Extend `appendMessage()`/finalization in `app/chat.js` to accept normalized history records and optional cached sanitized HTML; cache only `formatContent()` output for non-running records and reconstruct sender/media/thinking/tool/approval nodes for the active window.
- [x] 6.5 Feed provider SSE and Gateway final/history events into `ChatHistoryStore` before existing transient handlers; retain streaming deltas in the live layer and commit only finalized content to history.
- [x] 6.6 Replace `scheduleFeishuHistoryRefresh()` full reload with one deduplicated latest-page revalidation for the active conversation key because Feishu SSE carries only refresh signals.
- [x] 6.7 Ensure a matching inactive entry may update without visible DOM mutation and a latest-page response cannot overwrite a newer terminal live mutation.
- [x] 6.8 Run `node tests/check_chat_history_store.mjs && node tests/check_chat_history_navigation.mjs && node tests/check_provider_chat_sse.mjs && node tests/check_codex_approval_ui.mjs`; verify GREEN.

## 7. Performance Observability and Rollback

- [x] 7.1 Extend `tests/check_frontend_performance_static.mjs` with RED checks for page size 50, DOM maximum 160, render-batch marks, hashed debug labels, absence of payload fields in debug output, and the V2 legacy kill switch.
- [x] 7.2 Run `node tests/check_frontend_performance_static.mjs`; verify RED for the new observability contract.
- [x] 7.3 Add history switch/cache paint/page paint/render batch marks and measures; expose frozen aggregate counters through `window.__voChatHistoryDebug` without raw keys, IDs, text, attachments, commands, or tool payloads.
- [x] 7.4 Add content-free slow-request timing and source-cache hit/miss logging to the new server handler; do not log cursor, agent, conversation, or message data.
- [x] 7.5 Keep `CHAT_HISTORY_V2_ENABLED` as the single frontend rollback switch, default it on only after functional integration is green, and verify setting it false invokes the unchanged `loadLegacyHistory()` path.
- [x] 7.6 Run `node tests/check_frontend_performance_static.mjs && node tests/check_chat_history_navigation.mjs`; verify GREEN.

## 8. Controlled Browser Acceptance

- [x] 8.1 Create `tests/chat_history_performance.mjs` using `tests/cdp-test-utils.mjs`; add a deterministic 1,000-message fixture, delayed latest response, three out-of-order conversation responses, rich-card/media resize cases, and canvas-animation pause/restore cleanup.
- [x] 8.2 Run the fixture before final integration and verify RED on at least one required invariant: cache-before-network paint, maximum 160 historical roots, anchor stability, stale-response isolation, live-layer preservation, or render batch below 50 ms.
- [x] 8.3 Confirm ports 18092 and 19224 are free, start the isolated VO server on 18092 and a CDP-enabled browser on 19224, then run `VO_APP_URL=http://127.0.0.1:18092/ VO_CDP_URL=http://127.0.0.1:19224 node tests/chat_history_performance.mjs`.
- [x] 8.4 Verify GREEN for cached content before delayed response release, latest page at most 50, old/new navigation through 1,000 records, mounted history roots at most 160, anchor drift at most 2 CSS pixels, only selected conversation visible after out-of-order responses, restored rich-card state, and every instrumented history batch below 50 ms.
- [x] 8.5 Repeat browser acceptance for the primary panel and one secondary panel; verify reopening the secondary panel reuses its cache and does not issue a blocking full-history request.

## 9. Regression, OpenSpec Verification, and Evidence

- [x] 9.1 Run `PYTHONPYCACHEPREFIX=/tmp/vo-pycache .venv/bin/python tests/test_chat_history_api.py` and record the passed case count for API, identity, cache, and provider fixtures.
- [x] 9.2 Run `node tests/check_chat_history_store.mjs`, `node tests/check_chat_history_navigation.mjs`, and `node tests/chat_history_performance.mjs` with the isolated runtime; record counts and measured maximum batch duration.
- [x] 9.3 Run existing targeted regressions: `node tests/check_provider_chat_sse.mjs`, `node tests/check_codex_runs_bridge.mjs`, `node tests/check_codex_approval_ui.mjs`, `node tests/check_claude_code_runs_sse.mjs`, `node tests/check_chat_bug_regressions.mjs`, and `node tests/check_frontend_performance_static.mjs`.
- [x] 9.4 Run `PYTHONPYCACHEPREFIX=/tmp/vo-pycache .venv/bin/python -m py_compile app/server.py`, `node --check app/chat-history.js`, `node --check app/chat.js`, and `git diff --check`; require all exit codes 0.
- [x] 9.5 Run `openspec validate optimize-chat-history-switching --type change --strict --json --no-interactive --no-color`; require one passed change, zero failed, and zero issues.
- [x] 9.6 Audit every scenario in `specs/chat-history-navigation/spec.md` against test output and browser evidence; leave any unsupported scenario unchecked and continue implementation rather than declaring completion.
- [x] 9.7 Update these OpenSpec task checkboxes only after their commands and acceptance evidence actually pass; do not archive or remove the legacy path before the separate test-result and final-archive confirmations.

## Spec Traceability

| Confirmed requirement | Primary tasks | Acceptance evidence |
| --- | --- | --- |
| Cached conversations switch without network wait | 3, 5, 8 | Delayed-response cache-paint browser case |
| Cold newest page first | 1, 2, 8 | API page fixtures and 50-node initial browser assertion |
| Incremental older history with stable viewport | 2, 4, 8 | Cursor fixtures and <=2 px anchor drift |
| Mounted DOM remains bounded | 4, 8 | 1,000-message fixture with <=160 roots |
| Stable rendering is reusable | 3, 6 | Render-cache hit/invalidation fixtures |
| Refresh and live events share state | 3, 6, 8 | SSE/history race and out-of-order response cases |
| All providers retain rich history behavior | 2, 6, 9 | Four-provider API fixtures and existing provider regressions |
| Performance is measurable | 7, 8, 9 | Performance marks, counters, and <50 ms batch result |
