#!/usr/bin/env node
import assert from 'node:assert/strict';
import { spawnSync } from 'node:child_process';
import { appURL, closeCdpPage, createCdpPage, cdpVersion } from './cdp-test-utils.mjs';

if (typeof WebSocket === 'undefined') {
  const child = spawnSync(process.execPath, ['--experimental-websocket', ...process.argv.slice(1)], {
    env: process.env,
    stdio: 'inherit',
  });
  process.exit(child.status ?? 1);
}

await cdpVersion();

const agents = ['agent-a', 'agent-b', 'agent-c'].map((id, index) => ({
  key: id,
  agentId: id,
  sessionKey: `codex:${id}`,
  providerKind: 'codex',
  providerType: 'runtime',
  providerAgentId: id,
  branch: 'E2E fixtures',
  emoji: ['A', 'B', 'C'][index],
  name: `History ${id.slice(-1).toUpperCase()}`,
}));
const delayedAgents = new Set();
const pausedHistory = new Map();
const requestCounts = new Map();
const feishuHistory = new Map();

function historyPage(agentId, before) {
  const requestedEnd = before?.startsWith('cursor-') ? Number(before.slice(7)) : 1000;
  const end = Number.isFinite(requestedEnd) ? Math.max(0, Math.min(1000, requestedEnd)) : 1000;
  const start = Math.max(0, end - 50);
  const baseMessages = Array.from({ length: end - start }, (_, offset) => {
    const index = start + offset;
    return {
      id: `${agentId}-message-${index}`,
      version: 'v1',
      providerKind: 'codex',
      conversationId: 'fixture',
      role: index % 2 ? 'assistant' : 'user',
      text: `${agentId.toUpperCase()} history ${index}`,
      epochMs: index + 1,
      status: 'done',
    };
  });
  const liveMessages = before ? [] : (feishuHistory.get(agentId) || []);
  const messages = [...baseMessages, ...liveMessages]
    .sort((left, right) => Number(left.epochMs || 0) - Number(right.epochMs || 0) || left.id.localeCompare(right.id))
    .slice(-50);
  return {
    ok: true,
    conversationKey: `codex\u001f${agentId}\u001ffixture`,
    messages,
    nextCursor: start > 0 ? `cursor-${start}` : '',
    hasMore: start > 0,
    session: { model: 'e2e-model', contextWindow: 200000, contextUsed: end },
  };
}

function encodeBody(value) {
  return Buffer.from(JSON.stringify(value)).toString('base64');
}

const page = await createCdpPage('about:blank');
const ws = new WebSocket(page.webSocketDebuggerUrl);
await new Promise((resolve, reject) => {
  ws.addEventListener('open', resolve, { once: true });
  ws.addEventListener('error', () => reject(new Error('Unable to open page CDP socket')), { once: true });
});

let sequence = 0;
const pending = new Map();
function send(method, params = {}) {
  const id = ++sequence;
  ws.send(JSON.stringify({ id, method, params }));
  return new Promise((resolve, reject) => {
    const timer = setTimeout(() => {
      pending.delete(id);
      reject(new Error(`Timed out waiting for ${method}`));
    }, 30000);
    pending.set(id, { resolve, reject, timer });
  });
}

async function fulfill(requestId, payload) {
  await send('Fetch.fulfillRequest', {
    requestId,
    responseCode: 200,
    responseHeaders: [
      { name: 'Content-Type', value: 'application/json' },
      { name: 'Cache-Control', value: 'no-store' },
    ],
    body: encodeBody(payload),
  });
}

ws.addEventListener('message', event => {
  const message = JSON.parse(event.data.toString());
  if (message.id && pending.has(message.id)) {
    const waiter = pending.get(message.id);
    pending.delete(message.id);
    clearTimeout(waiter.timer);
    if (message.error) waiter.reject(new Error(JSON.stringify(message.error)));
    else waiter.resolve(message.result || {});
    return;
  }
  if (message.method !== 'Fetch.requestPaused') return;
  const { requestId, request } = message.params;
  const url = new URL(request.url);
  if (url.pathname === '/agents-list') {
    fulfill(requestId, { agents }).catch(() => {});
    return;
  }
  if (url.pathname === '/api/feishu-chat/config') {
    fulfill(requestId, { ok: true, enabled: true, representativeAgentId: 'agent-b' }).catch(() => {});
    return;
  }
  if (url.pathname === '/api/chat/history') {
    const agentId = url.searchParams.get('agentId') || 'agent-a';
    const before = url.searchParams.get('before') || '';
    requestCounts.set(agentId, (requestCounts.get(agentId) || 0) + 1);
    if (delayedAgents.has(agentId) && !before) {
      pausedHistory.set(agentId, { requestId, payload: historyPage(agentId, before) });
    } else {
      fulfill(requestId, historyPage(agentId, before)).catch(() => {});
    }
  }
});

async function evaluate(expression) {
  const response = await send('Runtime.evaluate', { expression, awaitPromise: true, returnByValue: true });
  if (response.exceptionDetails) throw new Error(response.exceptionDetails.text || JSON.stringify(response.exceptionDetails));
  return response.result?.value;
}

async function waitFor(expression, timeoutMs = 10000) {
  const startedAt = Date.now();
  while (Date.now() - startedAt < timeoutMs) {
    if (await evaluate(expression)) return;
    await new Promise(resolve => setTimeout(resolve, 100));
  }
  throw new Error(`Timed out waiting for: ${expression}`);
}

async function selectAgent(agentId) {
  await evaluate(`(() => {
    const select = window.__voChatWindows?.[0]?.agentSelect;
    if (!select) return false;
    select.value = ${JSON.stringify(agentId)};
    select.dispatchEvent(new Event('change', { bubbles: true }));
    return true;
  })()`);
}

try {
  await send('Page.enable');
  await send('Runtime.enable');
  await send('Network.enable');
  if (process.env.CHAT_E2E_DISABLE_CACHE !== '0') {
    await send('Network.setCacheDisabled', { cacheDisabled: true });
  }
  await send('Page.addScriptToEvaluateOnNewDocument', { source: `(() => {
    window.__voFakeEventSources = [];
    window.EventSource = class FakeEventSource {
      constructor(url) {
        this.url = String(url || '');
        this.listeners = new Map();
        this.closed = false;
        window.__voFakeEventSources.push(this);
        queueMicrotask(() => this.emit('open'));
      }
      addEventListener(type, listener) {
        const listeners = this.listeners.get(type) || [];
        listeners.push(listener);
        this.listeners.set(type, listeners);
      }
      emit(type, data = {}) {
        if (this.closed) return;
        const event = { type, data: JSON.stringify(data) };
        for (const listener of this.listeners.get(type) || []) listener.call(this, event);
      }
      close() { this.closed = true; }
    };
  })();` });
  await send('Fetch.enable', { patterns: [
    { urlPattern: '*agents-list*', requestStage: 'Request' },
    { urlPattern: '*api/chat/history*', requestStage: 'Request' },
    { urlPattern: '*api/feishu-chat/config*', requestStage: 'Request' },
  ] });
  await send('Page.navigate', { url: `${appURL}?chatView=all` });
  await waitFor("window.__voChatWindows?.length === 4 && window.__voChatWindows[0].agentSelect?.options?.length === 3", 15000);

  await selectAgent('agent-b');
  await waitFor("document.querySelector('#chat-panel .chat-history-layer')?.textContent.includes('AGENT-B history 999')");
  await waitFor("window.__voChatWindows?.[0]?.historyStickToBottom && window.__voChatWindows[0].isNearBottom() && window.__voChatWindows[0].historyView.range.end === window.__voChatWindows[0].historyView.entry.order.length");
  const warmBRequests = requestCounts.get('agent-b') || 0;

  const optimisticFixture = await evaluate(`(() => {
    const win = window.__voChatWindows?.[0];
    const idempotencyKey = 'e2e-optimistic-reconcile';
    const text = 'E2E optimistic message must appear once';
    const epochMs = Date.now();
    const entry = win.historyView.entry;
    win.appendMessage('user', text, epochMs, [], { label: 'You', kind: 'human', idempotencyKey });
    win.historyStore.insertOptimistic(entry.context, {
      id: 'optimistic-e2e-reconcile', version: 'optimistic', role: 'user', text, epochMs,
      status: 'running', idempotencyKey,
    }, { notify: false });
    win.historyStore.mergePage(entry, { messages: [
      {
        id: 'authoritative-e2e-reconcile', version: 'authoritative', role: 'user', text,
        epochMs: epochMs + 1, status: 'done', idempotencyKey,
        attachments: [{ name: 'authoritative.txt', path: '/safe/authoritative.txt' }],
      },
      {
        id: 'authoritative-e2e-fallback-duplicate', version: 'authoritative', role: 'user', text,
        epochMs: epochMs + 2, status: 'done', idempotencyKey,
      },
    ] }, 'latest');
    return {
      idempotencyKey,
      text,
      range: { ...win.historyView.range },
      orderTail: entry.order.slice(-3),
      hasAuthoritative: entry.messages.has('authoritative-e2e-reconcile'),
      hasFallbackDuplicate: entry.messages.has('authoritative-e2e-fallback-duplicate'),
      hasOptimistic: entry.messages.has('optimistic-e2e-reconcile'),
      liveMatches: win.liveLayer.querySelectorAll('[data-idempotency-key="e2e-optimistic-reconcile"]').length,
      historyMatches: win.historyLayer.querySelectorAll('[data-history-message-id="authoritative-e2e-reconcile"]').length,
    };
  })()`);
  assert.equal(optimisticFixture.hasOptimistic, false, `optimistic Store record should reconcile: ${JSON.stringify(optimisticFixture)}`);
  assert.equal(optimisticFixture.hasAuthoritative, true, `authoritative Store record should exist: ${JSON.stringify(optimisticFixture)}`);
  assert.equal(optimisticFixture.hasFallbackDuplicate, false, `fallback authoritative duplicate should reconcile: ${JSON.stringify(optimisticFixture)}`);
  assert.equal(optimisticFixture.liveMatches, 0, `live bubble should be removed synchronously: ${JSON.stringify(optimisticFixture)}`);
  if (!optimisticFixture.historyMatches) console.log(`optimistic reconciliation render state: ${JSON.stringify(optimisticFixture)}`);
  await waitFor("document.querySelector('[data-history-message-id=\"authoritative-e2e-reconcile\"]')?.textContent.includes('E2E optimistic message must appear once')");
  const reconciliationState = await evaluate(`(() => ({
    liveMatches: document.querySelectorAll('#chat-panel .chat-live-layer [data-idempotency-key="e2e-optimistic-reconcile"]').length,
    historyMatches: document.querySelectorAll('#chat-panel .chat-history-layer [data-history-message-id="authoritative-e2e-reconcile"]').length,
    visibleTextMatches: [...document.querySelectorAll('#chat-panel .chat-msg')].filter(node => node.textContent.includes(${JSON.stringify('E2E optimistic message must appear once')})).length,
  }))()`);
  assert.equal(optimisticFixture.idempotencyKey, 'e2e-optimistic-reconcile');
  assert.equal(reconciliationState.liveMatches, 0, 'the reconciled live optimistic bubble must be removed');
  assert.equal(reconciliationState.historyMatches, 1, 'the authoritative history bubble must be rendered once');
  assert.equal(reconciliationState.visibleTextMatches, 1, 'the user must see exactly one bubble after reconciliation');
  await evaluate(`(() => {
    const win = window.__voChatWindows?.[0];
    win.historyStore.removeMessage(win.historyView.entry.context, 'authoritative-e2e-reconcile');
  })()`);
  await waitFor("!document.querySelector('[data-history-message-id=\"authoritative-e2e-reconcile\"]')");

  await selectAgent('agent-a');
  await waitFor("document.querySelector('#chat-panel .chat-history-layer')?.textContent.includes('AGENT-A history 999')");

  delayedAgents.add('agent-b');
  await selectAgent('agent-b');
  await waitFor("Boolean(document.querySelector('#chat-panel .chat-history-layer')?.textContent.includes('AGENT-B history 999'))");
  await waitFor("Boolean(document.querySelector('#chat-panel')?.classList.contains('open'))");
  const cacheBeforeRefresh = await evaluate(`(() => ({
    text: document.querySelector('#chat-panel .chat-history-layer')?.textContent || '',
    roots: document.querySelectorAll('#chat-panel .chat-history-layer [data-history-message-id]').length,
    loadingBubble: [...document.querySelectorAll('#chat-panel .chat-live-layer .chat-msg')].some(node => node.textContent.includes('Loading chat history')),
  }))()`);
  assert.ok(pausedHistory.has('agent-b'), 'the background refresh should be delayed by the E2E fixture');
  assert.ok(cacheBeforeRefresh.text.includes('AGENT-B history 999'), 'cached B history should remain visible before refresh completion');
  assert.equal(cacheBeforeRefresh.loadingBubble, false, 'a warm switch should not show a blocking loading bubble');
  assert.ok(cacheBeforeRefresh.roots <= 50, `warm latest view should start with <=50 roots, got ${cacheBeforeRefresh.roots}`);
  await fulfill(pausedHistory.get('agent-b').requestId, pausedHistory.get('agent-b').payload);
  pausedHistory.delete('agent-b');
  delayedAgents.delete('agent-b');
  await new Promise(resolve => setTimeout(resolve, 150));

  await evaluate(`(() => {
    const messages = document.querySelector('#chat-panel .chat-messages');
    messages.scrollTop = 0;
    messages.dispatchEvent(new Event('scroll'));
  })()`);
  await waitFor("document.querySelector('#chat-panel .chat-history-layer')?.textContent.includes('AGENT-B history 949')");
  for (let index = 0; index < 5; index += 1) {
    await evaluate(`(() => {
      const messages = document.querySelector('#chat-panel .chat-messages');
      messages.scrollTop = 0;
      messages.dispatchEvent(new Event('scroll'));
    })()`);
    await new Promise(resolve => setTimeout(resolve, 120));
  }
  const afterOlder = await evaluate(`(() => ({
    roots: document.querySelectorAll('#chat-panel .chat-history-layer [data-history-message-id]').length,
    oldestVisible: document.querySelector('#chat-panel .chat-history-layer [data-history-message-id]')?.dataset.historyMessageId || '',
  }))()`);
  assert.ok(afterOlder.roots <= 160, `scrolling older must keep <=160 roots, got ${afterOlder.roots}`);

  await evaluate("document.querySelector('#chat-panel .chat-close')?.click()");
  await waitFor("!document.querySelector('#chat-panel')?.classList.contains('open')");
  const requestsBeforeReopen = requestCounts.get('agent-b') || 0;
  delayedAgents.add('agent-b');
  await evaluate("document.querySelector('#chat-toggle')?.click()");
  await waitFor("document.querySelector('#chat-panel')?.classList.contains('open')");
  await waitFor("document.querySelector('#chat-panel .chat-history-layer')?.textContent.includes('AGENT-B history')");
  const reopenState = await evaluate(`(() => ({
    roots: document.querySelectorAll('#chat-panel .chat-history-layer [data-history-message-id]').length,
    text: document.querySelector('#chat-panel .chat-history-layer')?.textContent || '',
  }))()`);
  assert.ok(reopenState.roots > 0 && reopenState.roots <= 160, 'reopening should synchronously restore a bounded cached view');
  assert.ok(reopenState.text.includes('AGENT-B history'), 'reopening should restore B without waiting for the delayed refresh');
  assert.equal(requestCounts.get('agent-b'), requestsBeforeReopen + 1, 'reopen should issue one background refresh');

  const delayedReopen = pausedHistory.get('agent-b');
  if (delayedReopen) await fulfill(delayedReopen.requestId, delayedReopen.payload);
  pausedHistory.delete('agent-b');
  delayedAgents.delete('agent-b');

  await evaluate(`(() => {
    const win = window.__voChatWindows?.[0];
    const count = win?.historyView?.entry?.order?.length || 0;
    win.historyView.range = { start: Math.max(0, count - 50), end: count };
    win.historyView.renderAll();
    win.prepareHistoryBottomFollow({ newest: true });
    win.scheduleHistoryBottomFollow();
  })()`);
  await waitFor("window.__voChatWindows?.[0]?.historyStickToBottom && window.__voChatWindows[0].isNearBottom()");
  await waitFor("window.__voFakeEventSources?.some(source => !source.closed && source.url.includes('agentId=agent-b'))");
  feishuHistory.set('agent-b', [{
    id: 'feishu-live-request', version: 'v1', providerKind: 'codex', conversationId: 'fixture',
    role: 'user', text: 'Feishu live request appeared automatically', epochMs: 2001, status: 'done',
    source: 'agent-platform-communications', fromAgentId: 'user', toAgentId: 'agent-b',
  }]);
  await evaluate(`(() => {
    for (const source of window.__voFakeEventSources.filter(item => !item.closed && item.url.includes('agentId=agent-b'))) {
      source.emit('message', { event: 'message' });
    }
  })()`);
  await new Promise(resolve => setTimeout(resolve, 500));
  const feishuDebugState = await evaluate(`(() => {
    const win = window.__voChatWindows?.[0];
    return {
      selectedAgent: win?.getSelectedAgentId?.() || win?.selectedAgentKey,
      open: Boolean(win?.root?.classList.contains('open')),
      sources: window.__voFakeEventSources.filter(item => !item.closed && item.url.includes('agentId=agent-b')).length,
      pending: win?.feishuHistoryRefreshPending,
      running: win?.feishuHistoryRefreshRunning,
      timer: Boolean(win?.feishuHistoryRefreshTimer),
      range: win?.historyView?.range,
      orderTail: win?.historyView?.entry?.order?.slice(-5),
      mountedTail: [...(win?.historyLayer?.querySelectorAll('[data-history-message-id]') || [])].slice(-5).map(node => node.dataset.historyMessageId),
    };
  })()`);
  if (!feishuDebugState.mountedTail?.includes('feishu-live-request')) {
    console.log(`Feishu live E2E diagnostics: ${JSON.stringify({ ...feishuDebugState, requests: requestCounts.get('agent-b') || 0 })}`);
  }
  await waitFor("document.querySelector('[data-history-message-id=\"feishu-live-request\"]')?.textContent.includes('Feishu live request appeared automatically')");

  feishuHistory.get('agent-b').push({
    id: 'feishu-live-reply', version: 'v1', providerKind: 'codex', conversationId: 'fixture',
    role: 'assistant', text: 'Feishu live reply appeared automatically', epochMs: 2002, status: 'done',
    source: 'agent-platform-communications', fromAgentId: 'agent-b', toAgentId: 'user',
  });
  await evaluate(`(() => {
    for (const source of window.__voFakeEventSources.filter(item => !item.closed && item.url.includes('agentId=agent-b'))) {
      source.emit('delivery', { event: 'delivery' });
    }
  })()`);
  await waitFor("document.querySelector('[data-history-message-id=\"feishu-live-reply\"]')?.textContent.includes('Feishu live reply appeared automatically')");

  feishuHistory.get('agent-b').push({
    id: 'feishu-reconnect-recovery', version: 'v1', providerKind: 'codex', conversationId: 'fixture',
    role: 'user', text: 'Feishu reconnect recovered missed history', epochMs: 2003, status: 'done',
    source: 'agent-platform-communications', fromAgentId: 'user', toAgentId: 'agent-b',
  });
  await evaluate(`(() => {
    for (const source of window.__voFakeEventSources.filter(item => !item.closed && item.url.includes('agentId=agent-b'))) {
      source.emit('ready', { event: 'ready' });
    }
  })()`);
  await waitFor("document.querySelector('[data-history-message-id=\"feishu-reconnect-recovery\"]')?.textContent.includes('Feishu reconnect recovered missed history')");
  const feishuLiveState = await evaluate(`(() => ({
    request: document.querySelectorAll('[data-history-message-id="feishu-live-request"]').length,
    reply: document.querySelectorAll('[data-history-message-id="feishu-live-reply"]').length,
    recovered: document.querySelectorAll('[data-history-message-id="feishu-reconnect-recovery"]').length,
    nearBottom: window.__voChatWindows?.[0]?.isNearBottom(),
  }))()`);
  assert.deepEqual(feishuLiveState, { request: 1, reply: 1, recovered: 1, nearBottom: true }, 'Feishu SSE refresh and reconnect recovery must render once and follow an already-bottomed viewport');

  await evaluate(`(() => {
    const win = window.__voChatWindows?.[0];
    win.messages.scrollTop = Math.max(300, Math.floor((win.messages.scrollHeight - win.messages.clientHeight) / 2));
    win.messages.dispatchEvent(new Event('scroll'));
  })()`);
  await waitFor("window.__voChatWindows?.[0]?.historyStickToBottom === false");
  const olderAnchorBefore = await evaluate(`(() => {
    const win = window.__voChatWindows?.[0];
    const top = win.messages.getBoundingClientRect().top;
    const root = [...win.historyLayer.querySelectorAll('[data-history-message-id]')]
      .find(node => node.getBoundingClientRect().bottom >= top);
    return { id: root?.dataset.historyMessageId || '', offset: root ? root.getBoundingClientRect().top - top : 0 };
  })()`);
  feishuHistory.get('agent-b').push({
    id: 'feishu-no-forced-follow', version: 'v1', providerKind: 'codex', conversationId: 'fixture',
    role: 'assistant', text: 'Feishu event must not interrupt older history', epochMs: 2004, status: 'done',
    source: 'agent-platform-communications', fromAgentId: 'agent-b', toAgentId: 'user',
  });
  await evaluate(`(() => {
    for (const source of window.__voFakeEventSources.filter(item => !item.closed && item.url.includes('agentId=agent-b'))) {
      source.emit('message', { event: 'message' });
    }
  })()`);
  await waitFor("window.__voChatWindows?.[0]?.historyView?.entry?.messages?.has('feishu-no-forced-follow')");
  await new Promise(resolve => setTimeout(resolve, 400));
  const noForcedFollowState = await evaluate(`(() => {
    const win = window.__voChatWindows?.[0];
    const top = win.messages.getBoundingClientRect().top;
    const root = [...win.historyLayer.querySelectorAll('[data-history-message-id]')]
      .find(node => node.getBoundingClientRect().bottom >= top);
    return {
      stick: win.historyStickToBottom,
      nearBottom: win.isNearBottom(),
      remaining: win.messages.scrollHeight - win.messages.scrollTop - win.messages.clientHeight,
      anchor: { id: root?.dataset.historyMessageId || '', offset: root ? root.getBoundingClientRect().top - top : 0 },
    };
  })()`);
  assert.equal(noForcedFollowState.stick, false, `reading older history must keep bottom-follow disabled: ${JSON.stringify(noForcedFollowState)}`);
  assert.equal(noForcedFollowState.nearBottom, false, `a new event must not force the older viewport to the bottom: ${JSON.stringify(noForcedFollowState)}`);
  assert.equal(noForcedFollowState.anchor.id, olderAnchorBefore.id, 'a new event must preserve the first visible history message');
  assert.ok(Math.abs(noForcedFollowState.anchor.offset - olderAnchorBefore.offset) <= 1, `older viewport offset should remain anchored: ${JSON.stringify({ before: olderAnchorBefore, after: noForcedFollowState.anchor })}`);

  await evaluate(`(() => {
    const win = window.__voChatWindows?.[0];
    win.historyView.navigateToNewest();
    win.messages.scrollTop = win.messages.scrollHeight;
    win.messages.dispatchEvent(new Event('scroll'));
  })()`);
  await waitFor("window.__voChatWindows?.[0]?.historyStickToBottom && window.__voChatWindows[0].isNearBottom()");
  feishuHistory.get('agent-b').push({
    id: 'feishu-follow-resumed', version: 'v1', providerKind: 'codex', conversationId: 'fixture',
    role: 'assistant', text: 'Feishu bottom follow resumed', epochMs: 2005, status: 'done',
    source: 'agent-platform-communications', fromAgentId: 'agent-b', toAgentId: 'user',
  });
  await evaluate(`(() => {
    for (const source of window.__voFakeEventSources.filter(item => !item.closed && item.url.includes('agentId=agent-b'))) {
      source.emit('delivery', { event: 'delivery' });
    }
  })()`);
  await waitFor("document.querySelector('[data-history-message-id=\"feishu-follow-resumed\"]') && window.__voChatWindows?.[0]?.isNearBottom()");

  await evaluate(`(() => {
    const win = window.__voChatWindows?.[0];
    win.scheduleHistoryBottomFollow();
    setTimeout(() => {
      const delayed = document.createElement('div');
      delayed.id = 'delayed-layout-fixture';
      delayed.style.height = '480px';
      win.liveLayer.appendChild(delayed);
    }, 40);
  })()`);
  await new Promise(resolve => setTimeout(resolve, 420));
  assert.equal(await evaluate("window.__voChatWindows?.[0]?.isNearBottom()"), true, 'delayed post-render layout must settle back to the bottom');
  await evaluate("document.querySelector('#delayed-layout-fixture')?.remove()");

  await evaluate(`(() => {
    const source = [...window.__voFakeEventSources].reverse().find(item => !item.closed && item.url.includes('/api/provider/events') && item.url.includes('agentId=agent-b'));
    source?.emit('run.completed', { runId: 'provider-bottom-follow', reply: 'Provider live event followed the bottom', epochMs: 2006 });
  })()`);
  await waitFor("[...document.querySelectorAll('#chat-panel .chat-msg')].some(node => node.textContent.includes('Provider live event followed the bottom')) && window.__voChatWindows?.[0]?.isNearBottom()");

  assert.ok((requestCounts.get('agent-b') || 0) >= warmBRequests + 2, 'B should have warm-switch and reopen refresh evidence');
  console.log(`chat history UI E2E passed (B requests ${requestCounts.get('agent-b')}, mounted roots ${afterOlder.roots}, oldest visible ${afterOlder.oldestVisible}, bottom init/follow/preserve/resume/provider passed)`);
} finally {
  for (const delayed of pausedHistory.values()) await fulfill(delayed.requestId, delayed.payload).catch(() => {});
  ws.close();
  await closeCdpPage(page);
}
