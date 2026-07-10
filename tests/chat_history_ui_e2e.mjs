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

function historyPage(agentId, before) {
  const requestedEnd = before?.startsWith('cursor-') ? Number(before.slice(7)) : 1000;
  const end = Number.isFinite(requestedEnd) ? Math.max(0, Math.min(1000, requestedEnd)) : 1000;
  const start = Math.max(0, end - 50);
  return {
    ok: true,
    conversationKey: `codex\u001f${agentId}\u001ffixture`,
    messages: Array.from({ length: end - start }, (_, offset) => {
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
    }),
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
  await send('Fetch.enable', { patterns: [
    { urlPattern: '*agents-list*', requestStage: 'Request' },
    { urlPattern: '*api/chat/history*', requestStage: 'Request' },
  ] });
  await send('Page.navigate', { url: `${appURL}?chatView=all` });
  await waitFor("window.__voChatWindows?.length === 4 && window.__voChatWindows[0].agentSelect?.options?.length === 3", 15000);

  await selectAgent('agent-b');
  await waitFor("document.querySelector('#chat-panel .chat-history-layer')?.textContent.includes('AGENT-B history 999')");
  const warmBRequests = requestCounts.get('agent-b') || 0;

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

  assert.ok((requestCounts.get('agent-b') || 0) >= warmBRequests + 2, 'B should have warm-switch and reopen refresh evidence');
  console.log(`chat history UI E2E passed (B requests ${requestCounts.get('agent-b')}, mounted roots ${afterOlder.roots}, oldest visible ${afterOlder.oldestVisible})`);
} finally {
  for (const delayed of pausedHistory.values()) await fulfill(delayed.requestId, delayed.payload).catch(() => {});
  ws.close();
  await closeCdpPage(page);
}
