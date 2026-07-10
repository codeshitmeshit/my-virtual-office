#!/usr/bin/env node
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';

const source = fs.readFileSync('app/chat-history.js', 'utf8');
const context = {
  console,
  TextEncoder,
  URLSearchParams,
  AbortController,
  performance: { now: () => 0, mark() {}, measure() {} },
  fetch: async () => { throw new Error('unexpected fetch'); },
};
context.globalThis = context;
vm.runInNewContext(source, context, { filename: 'app/chat-history.js' });

const runtime = context.ChatHistoryRuntime;
assert.ok(runtime, 'ChatHistoryRuntime must be exported');
assert.equal(runtime.stableHistoryHash(''), '811c9dc5');
assert.equal(runtime.stableHistoryHash('hello'), '4f9f2cab');
assert.equal(runtime.stableHistoryHash('聊天历史'), '2b992da3');
assert.equal(runtime.stableHistoryHash('codex\u001fagent\u001fconv'), '4fe64f31');
assert.equal(
  runtime.createConversationKey({ providerKind: 'codex', agentId: 'agent', conversationId: 'conv' }),
  'codex\u001fagent\u001fconv'
);
assert.deepEqual(
  JSON.parse(JSON.stringify(runtime.constants)),
  { PAGE_SIZE: 50, DOM_WINDOW_MAX: 160, MESSAGE_LIMIT: 1000, INACTIVE_ENTRY_LIMIT: 8 }
);

{
  assert.deepEqual(
    JSON.parse(JSON.stringify(runtime.computeWindowRange(1000))),
    { start: 950, end: 1000 },
    'the first paint should mount only the newest 50 messages'
  );
  const olderOnce = runtime.computeWindowRange(1000, { current: { start: 950, end: 1000 }, direction: 'older' });
  assert.deepEqual(JSON.parse(JSON.stringify(olderOnce)), { start: 910, end: 1000 });
  const olderTwice = runtime.computeWindowRange(1000, { current: olderOnce, direction: 'older' });
  assert.deepEqual(JSON.parse(JSON.stringify(olderTwice)), { start: 870, end: 1000 });
  const full = runtime.computeWindowRange(1000, { current: olderTwice, direction: 'older' });
  assert.deepEqual(JSON.parse(JSON.stringify(full)), { start: 840, end: 1000 });
  const shiftedOlder = runtime.computeWindowRange(1000, { current: full, direction: 'older' });
  assert.deepEqual(JSON.parse(JSON.stringify(shiftedOlder)), { start: 800, end: 960 });
  const shiftedNewer = runtime.computeWindowRange(1000, { current: shiftedOlder, direction: 'newer' });
  assert.deepEqual(JSON.parse(JSON.stringify(shiftedNewer)), { start: 840, end: 1000 });
  assert.ok(shiftedOlder.end - shiftedOlder.start <= runtime.constants.DOM_WINDOW_MAX);

  const jumped = runtime.computeWindowRange(1000, { targetIndex: 500 });
  assert.ok(jumped.start <= 480 && jumped.end >= 521, 'jump ranges should include 20 messages of overscan');
  assert.ok(jumped.end - jumped.start <= runtime.constants.DOM_WINDOW_MAX);

  const ids = Array.from({ length: 10 }, (_, index) => `m-${index}`);
  const heights = new Map(ids.map((id, index) => [id, index + 1]));
  assert.deepEqual(
    JSON.parse(JSON.stringify(runtime.computeSpacerHeights(ids, { start: 3, end: 7 }, heights, 20))),
    { top: 6, bottom: 27 }
  );
  assert.deepEqual(
    JSON.parse(JSON.stringify(runtime.computeSpacerHeights(ids, { start: 2, end: 4 }, new Map(), 20))),
    { top: 40, bottom: 120 },
    'unknown roots should use the measured fallback height'
  );
  assert.equal(runtime.computeAnchorDelta(125.5, 173.25), 47.75);
  assert.equal(runtime.presentationStateKey('message', 'details:tool'), 'message\u001fdetails:tool');
}

const makeContext = (name) => ({ providerKind: 'codex', agentId: `agent-${name}`, conversationId: `conv-${name}` });
const makeMessage = (id, epochMs, overrides = {}) => ({
  id,
  version: overrides.version || `v-${id}`,
  providerKind: 'codex',
  conversationId: 'conv',
  role: 'assistant',
  text: overrides.text || id,
  epochMs,
  status: overrides.status || 'done',
  tools: overrides.tools || [],
  media: overrides.media || [],
  ...overrides,
});

{
  const store = new runtime.ChatHistoryStore({ fetchImpl: context.fetch });
  const entry = store.getOrCreate(makeContext('merge'));
  store.mergePage(entry, {
    messages: [makeMessage('m2', 2), makeMessage('m1', 1)],
    nextCursor: 'older',
    hasMore: true,
    session: { contextUsed: 10 },
  }, 'latest');
  assert.deepEqual(Array.from(entry.order), ['m1', 'm2']);
  assert.equal(entry.nextCursor, 'older');
  assert.equal(entry.hasMore, true);
  assert.equal(entry.session.contextUsed, 10);

  store.mergePage(entry, { messages: [makeMessage('m2', 2, { version: 'v2', text: 'updated' })] }, 'latest');
  assert.equal(entry.messages.get('m2').text, 'updated');
  assert.equal(entry.order.filter(id => id === 'm2').length, 1);
}

{
  const store = new runtime.ChatHistoryStore({ fetchImpl: context.fetch });
  const entry = store.getOrCreate(makeContext('terminal'));
  store.mergePage(entry, { messages: [makeMessage('run', 1, { status: 'done', version: 'done' })] }, 'latest');
  store.mergePage(entry, { messages: [makeMessage('run', 1, { status: 'running', version: 'older' })] }, 'latest');
  assert.equal(entry.messages.get('run').status, 'done', 'running snapshots must not replace terminal live state');
}

{
  const store = new runtime.ChatHistoryStore({ fetchImpl: context.fetch });
  for (let index = 0; index < 9; index += 1) store.getOrCreate(makeContext(`lru-${index}`));
  assert.equal(store.entries.size, 8, 'inactive conversation cache must be bounded');
  assert.equal(store.entries.has(runtime.createConversationKey(makeContext('lru-0'))), false, 'oldest inactive entry should be evicted');

  const activeView = { activation: 0, onHistoryEntryChanged() {} };
  const active = store.activate(makeContext('active'), activeView);
  for (let index = 0; index < 10; index += 1) store.getOrCreate(makeContext(`extra-${index}`));
  assert.equal(store.entries.has(active.key), true, 'active conversations must not be evicted');
}

{
  const store = new runtime.ChatHistoryStore({ fetchImpl: context.fetch });
  const entry = store.getOrCreate(makeContext('limit'));
  store.mergePage(entry, {
    messages: Array.from({ length: 1005 }, (_, index) => makeMessage(`m-${index}`, index)),
  }, 'latest');
  assert.equal(entry.order.length, 1000);
  assert.equal(entry.order[0], 'm-5');
}

{
  const store = new runtime.ChatHistoryStore({ fetchImpl: context.fetch });
  store.setRenderedHtml('message', 'v1', '<p>cached</p>');
  assert.equal(store.getRenderedHtml('message', 'v1'), '<p>cached</p>');
  assert.equal(store.getRenderedHtml('message', 'v2'), null, 'version changes must invalidate rendered HTML');
}

{
  const store = new runtime.ChatHistoryStore({ fetchImpl: context.fetch, inactiveByteLimit: 300 });
  const first = store.getOrCreate(makeContext('bytes-1'));
  store.mergePage(first, { messages: [makeMessage('large-1', 1, { text: 'x'.repeat(300) })] }, 'latest');
  const second = store.getOrCreate(makeContext('bytes-2'));
  store.mergePage(second, { messages: [makeMessage('large-2', 2, { text: 'y'.repeat(300) })] }, 'latest');
  assert.ok(store.entries.size <= 1, 'inactive byte budget should evict oldest entries');

  const htmlStore = new runtime.ChatHistoryStore({ fetchImpl: context.fetch, renderedHtmlByteLimit: 20, renderedHtmlEntryLimit: 2 });
  htmlStore.setRenderedHtml('one', 'v1', '1234567890');
  htmlStore.setRenderedHtml('two', 'v1', 'abcdefghij');
  assert.equal(htmlStore.getRenderedHtml('one', 'v1'), null, 'rendered HTML byte budget should evict oldest entry');
}

{
  let resolveFetch;
  let fetchCount = 0;
  const fetchImpl = () => {
    fetchCount += 1;
    return new Promise(resolve => { resolveFetch = resolve; });
  };
  const store = new runtime.ChatHistoryStore({ fetchImpl });
  const ctx = makeContext('request');
  const first = store.fetchLatest(ctx);
  const second = store.fetchLatest(ctx);
  assert.equal(first, second, 'latest requests for one key must share a promise');
  assert.equal(fetchCount, 1);
  resolveFetch({ ok: true, json: async () => ({ ok: true, messages: [makeMessage('network', 1)], hasMore: false }) });
  await first;
  assert.equal(store.getOrCreate(ctx).messages.has('network'), true);
}

{
  let fetchCount = 0;
  const fetchImpl = async (_url, options) => {
    fetchCount += 1;
    if (fetchCount === 1) {
      return { ok: false, json: async () => ({ ok: false, code: 'invalid_chat_history_cursor', error: 'bad cursor' }) };
    }
    assert.equal(options.signal.aborted, false);
    return { ok: true, json: async () => ({ ok: true, messages: [makeMessage('recovered', 3)], hasMore: false }) };
  };
  const store = new runtime.ChatHistoryStore({ fetchImpl });
  const ctx = makeContext('cursor-retry');
  const entry = store.getOrCreate(ctx);
  entry.hasMore = true;
  entry.nextCursor = 'stale-cursor';
  await store.fetchOlder(ctx);
  assert.equal(fetchCount, 2, 'invalid older cursor should retry the newest page exactly once');
  assert.equal(entry.messages.has('recovered'), true);
}

{
  let capturedSignal;
  const fetchImpl = (_url, options) => {
    capturedSignal = options.signal;
    return new Promise(() => {});
  };
  const store = new runtime.ChatHistoryStore({ fetchImpl });
  const ctx = makeContext('abort');
  store.fetchLatest(ctx);
  store.invalidate(ctx);
  assert.equal(capturedSignal.aborted, true, 'invalidating a conversation should abort its request');
}

{
  const notifications = [];
  const view = { activation: 0, onHistoryEntryChanged: entry => notifications.push(entry.key) };
  const store = new runtime.ChatHistoryStore({ fetchImpl: context.fetch });
  const first = store.activate(makeContext('first'), view);
  const second = store.activate(makeContext('second'), view);
  store.mergePage(first.entry, { messages: [makeMessage('late', 1)] }, 'latest');
  assert.equal(notifications.includes(first.key), false, 'stale conversation response must not notify the reactivated view');
  store.mergePage(second.entry, { messages: [makeMessage('current', 2)] }, 'latest');
  assert.equal(notifications.at(-1), second.key);
}

{
  const store = new runtime.ChatHistoryStore({ fetchImpl: context.fetch });
  const ctx = makeContext('live');
  const optimistic = store.insertOptimistic(ctx, makeMessage('optimistic', 1, { status: 'running' }));
  assert.equal(store.getOrCreate(ctx).messages.has(optimistic.id), true);
  store.applyLiveEvent(ctx, 'run.completed', makeMessage('optimistic', 1, { status: 'done', version: 'final', text: 'final' }));
  assert.equal(store.getOrCreate(ctx).messages.get('optimistic').text, 'final');
  store.removeMessage(ctx, 'optimistic');
  assert.equal(store.getOrCreate(ctx).messages.has('optimistic'), false);
  store.invalidate(ctx);
  assert.equal(store.entries.has(runtime.createConversationKey(ctx)), false);
}

console.log('chat history store checks passed');
