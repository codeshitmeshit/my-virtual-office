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
  const root = {};
  assert.equal(runtime.claimChatSubmission(root, 'same-message', 1000), true);
  assert.equal(runtime.claimChatSubmission(root, 'same-message', 1001), false, 'one UI action must only claim one submission');
  assert.equal(runtime.claimChatSubmission(root, 'different-message', 1001), true, 'different input must remain sendable');
  assert.equal(runtime.claimChatSubmission(root, 'same-message', 2501), true, 'an intentional later retry must remain sendable');
}

{
  let renderCalls = 0;
  const fakeView = { renderMessage: () => { renderCalls += 1; } };
  const rendered = runtime.ChatHistoryView.prototype._renderRoot.call(fakeView, {
    id: 'optimistic-primary-1', version: 'optimistic', role: 'user', text: 'hello',
  });
  assert.equal(rendered, null, 'store optimistic messages must stay out of the history DOM');
  assert.equal(renderCalls, 0, 'the live layer is the only optimistic renderer');
}

{
  const nodes = [
    { dataset: { providerRunId: 'run-1' }, removed: false, remove() { this.removed = true; } },
    { dataset: { providerRunId: 'run-2' }, removed: false, remove() { this.removed = true; } },
  ];
  const removed = runtime.removeProviderRunNodes({ querySelectorAll: () => nodes }, 'run-1');
  assert.equal(removed, 1);
  assert.equal(nodes[0].removed, true, 'the authoritative provider reply must replace its live reply');
  assert.equal(nodes[1].removed, false, 'another run reply must remain');
}

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

  const nodes = [
    { dataset: { idempotencyKey: 'request-1' }, removed: false, remove() { this.removed = true; } },
    { dataset: { idempotencyKey: 'request-2' }, removed: false, remove() { this.removed = true; } },
  ];
  const removed = runtime.removeReconciledOptimisticNodes(
    { querySelectorAll: () => nodes },
    [{ idempotencyKey: 'request-1' }]
  );
  assert.equal(removed, 1);
  assert.equal(nodes[0].removed, true, 'the exact live optimistic node must be removed');
  assert.equal(nodes[1].removed, false, 'a distinct same-text request key must remain');
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
  const entry = store.getOrCreate(makeContext('authoritative-idempotency'));
  store.mergePage(entry, { messages: [
    makeMessage('authoritative-first', 10, { role: 'user', text: '你好', idempotencyKey: 'office-same-request' }),
    makeMessage('authoritative-fallback', 11, { role: 'user', text: '你好', idempotencyKey: 'office-same-request' }),
  ] }, 'latest');
  assert.deepEqual(Array.from(entry.order), ['authoritative-first'], 'two authoritative records for one request must render once');
  assert.equal(entry.messages.has('authoritative-fallback'), false);
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

{
  const store = new runtime.ChatHistoryStore({ fetchImpl: context.fetch });
  const ctx = makeContext('canonical-live');
  const payload = {
    runId: 'legacy-run',
    text: 'legacy text must not win',
    status: 'failed',
    timelineItem: makeMessage('canonical-item', 20, {
      providerRunId: 'canonical-run', text: 'canonical text', status: 'done', version: 'canonical-v1', sequence: 2,
      thinking: 'canonical reasoning', tools: [{ id: 'tool', status: 'done' }],
    }),
  };
  store.applyLiveEvent(ctx, 'run.completed', payload);
  const item = store.getOrCreate(ctx).messages.get('canonical-item');
  assert.equal(item.text, 'canonical text', 'timelineItem must own live text');
  assert.equal(item.status, 'done', 'timelineItem must own live lifecycle');
  assert.equal(item.thinking, 'canonical reasoning', 'timelineItem must own live reasoning');
  assert.equal(item.tools[0].status, 'done', 'timelineItem must own tool lifecycle');
  assert.equal(store.getOrCreate(ctx).messages.has('legacy-run'), false, 'legacy payload identity must not be re-derived');

  store.applyLiveEvent(ctx, 'tool.completed', {
    timelineItem: makeMessage('same-time-later', 20, { sequence: 3, status: 'done' }),
  });
  assert.deepEqual(JSON.parse(JSON.stringify(store.getOrCreate(ctx).order)), ['canonical-item', 'same-time-later'], 'canonical sequence must break equal-time ties');
  const beforeDelta = store.getOrCreate(ctx).order.slice();
  store.applyLiveEvent(ctx, 'message.delta', { timelineItem: makeMessage('delta', 21, { status: 'running' }) });
  assert.deepEqual(JSON.parse(JSON.stringify(store.getOrCreate(ctx).order)), JSON.parse(JSON.stringify(beforeDelta)), 'streaming deltas must remain in the existing transient presentation layer');
}

{
  const reconciliations = [];
  const store = new runtime.ChatHistoryStore({ fetchImpl: context.fetch });
  const ctx = makeContext('optimistic-reconcile');
  const view = { activation: 0, onHistoryEntryChanged: (_entry, mutation) => reconciliations.push(...(mutation.reconciled || [])) };
  const { entry } = store.activate(ctx, view);
  store.insertOptimistic(ctx, makeMessage('optimistic-slot-1', 10, {
    role: 'user', text: 'same text', status: 'running', idempotencyKey: 'request-1',
    media: [{ url: 'data:image/png;base64,one' }],
  }), { notify: false });
  store.insertOptimistic(ctx, makeMessage('optimistic-slot-2', 11, {
    role: 'user', text: 'same text', status: 'running', idempotencyKey: 'request-2',
  }), { notify: false });
  store.mergePage(entry, { messages: [makeMessage('persisted-1', 12, {
    role: 'user', text: 'same text', status: 'done', idempotencyKey: 'request-1',
    attachments: [{ name: 'one.png', path: '/safe/one.png' }],
  })] }, 'latest');
  assert.equal(entry.messages.has('optimistic-slot-1'), false, 'the exact optimistic request must be replaced');
  assert.equal(entry.messages.has('persisted-1'), true, 'the authoritative message must remain');
  assert.equal(entry.messages.get('persisted-1').attachments[0].name, 'one.png', 'authoritative attachment metadata must win');
  assert.equal(entry.messages.has('optimistic-slot-2'), true, 'same text under a different request key must remain distinct');
  assert.deepEqual(JSON.parse(JSON.stringify(reconciliations)), [{
    optimisticId: 'optimistic-slot-1', authoritativeId: 'persisted-1', idempotencyKey: 'request-1',
  }]);
}

{
  const reconciliations = [];
  const store = new runtime.ChatHistoryStore({ fetchImpl: context.fetch });
  const ctx = makeContext('provider-final-reconcile');
  const view = { activation: 0, onHistoryEntryChanged: (_entry, mutation) => reconciliations.push(...(mutation.reconciled || [])) };
  const { entry } = store.activate(ctx, view);
  store.applyLiveEvent(ctx, 'run.completed', makeMessage('run-codex-run-1-final', 1000, {
    role: 'assistant', text: '验收通过', status: 'done',
  }), { notify: false });
  store.mergePage(entry, { messages: [makeMessage('communication-reply-1', 1005, {
    role: 'assistant', text: '验收通过', status: 'done', source: 'agent-platform-communications',
  })] }, 'latest');
  assert.equal(entry.messages.has('run-codex-run-1-final'), false, 'authoritative communication history must replace the transient run final');
  assert.equal(entry.messages.has('communication-reply-1'), true);
  assert.deepEqual(JSON.parse(JSON.stringify(reconciliations)), [{
    providerRunId: 'codex-run-1', authoritativeId: 'communication-reply-1',
  }]);
}

{
  const reconciliations = [];
  const store = new runtime.ChatHistoryStore({ fetchImpl: context.fetch });
  const ctx = makeContext('canonical-provider-final-reconcile');
  const view = { activation: 0, onHistoryEntryChanged: (_entry, mutation) => reconciliations.push(...(mutation.reconciled || [])) };
  const { entry } = store.activate(ctx, view);
  store.applyLiveEvent(ctx, 'run.completed', {
    timelineItem: makeMessage('tl-canonical-run', 1000, {
      itemKind: 'run', providerRunId: 'canonical-run-1', role: 'assistant', text: 'canonical final', status: 'done',
    }),
  }, { notify: false });
  store.mergePage(entry, { messages: [makeMessage('communication-canonical-1', 1005, {
    role: 'assistant', text: 'canonical final', status: 'done', source: 'agent-platform-communications',
  })] }, 'latest');
  assert.equal(entry.messages.has('tl-canonical-run'), false, 'durable history must settle the canonical transient run item');
  assert.equal(entry.messages.has('communication-canonical-1'), true);
  assert.deepEqual(JSON.parse(JSON.stringify(reconciliations)), [{
    providerRunId: 'canonical-run-1', authoritativeId: 'communication-canonical-1',
  }]);
}

{
  let nextRange = null;
  const fakeEntry = { order: Array.from({ length: 51 }, (_, index) => `m-${index}`) };
  const fakeView = {
    entry: fakeEntry,
    range: { start: 0, end: 50 },
    onReconciled() {},
    _patchMessage: () => false,
    renderAll() { nextRange = { ...this.range }; },
  };
  runtime.ChatHistoryView.prototype.onHistoryEntryChanged.call(fakeView, fakeEntry, {
    mode: 'latest', messageIds: ['m-50'], reconciled: [{ idempotencyKey: 'request-1' }],
  });
  assert.deepEqual(nextRange, { start: 0, end: 51 }, 'a reconciled latest-page message must enter the visible newest window');
}

console.log('chat history store checks passed');
