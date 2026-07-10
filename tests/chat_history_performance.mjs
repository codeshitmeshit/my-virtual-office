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

function send(ws, method, params = {}) {
  const id = ++send.sequence;
  ws.send(JSON.stringify({ id, method, params }));
  return new Promise((resolve, reject) => {
    const timer = setTimeout(() => reject(new Error(`Timed out waiting for ${method}`)), 30000);
    const onMessage = event => {
      const message = JSON.parse(event.data.toString());
      if (message.id !== id) return;
      clearTimeout(timer);
      ws.removeEventListener('message', onMessage);
      if (message.error) reject(new Error(JSON.stringify(message.error)));
      else resolve(message.result || {});
    };
    ws.addEventListener('message', onMessage);
  });
}
send.sequence = 0;

function openWebSocket(url) {
  return new Promise((resolve, reject) => {
    const ws = new WebSocket(url);
    ws.addEventListener('open', () => resolve(ws), { once: true });
    ws.addEventListener('error', () => reject(new Error('Unable to connect to page CDP socket')), { once: true });
  });
}

async function evaluate(ws, expression) {
  const response = await send(ws, 'Runtime.evaluate', { expression, awaitPromise: true, returnByValue: true });
  if (response.exceptionDetails) throw new Error(response.exceptionDetails.text || JSON.stringify(response.exceptionDetails));
  return response.result?.value;
}

const page = await createCdpPage('about:blank');
const pageWs = await openWebSocket(page.webSocketDebuggerUrl);

try {
  await send(pageWs, 'Page.enable');
  await send(pageWs, 'Runtime.enable');
  await send(pageWs, 'Emulation.setDeviceMetricsOverride', {
    width: 1440,
    height: 1000,
    deviceScaleFactor: 1,
    mobile: false,
  });
  await send(pageWs, 'Page.navigate', { url: appURL });
  await new Promise(resolve => setTimeout(resolve, 500));

  const result = await evaluate(pageWs, `(async () => {
    const source = await fetch(${JSON.stringify(new URL('chat-history.js', appURL).href)}).then(response => response.text());
    document.open();
    document.write('<!doctype html><html><head></head><body></body></html>');
    document.close();
    (0, eval)(source);
    document.body.innerHTML = '<div id="primary" class="scroll"><div class="history"></div><div class="live"></div></div><div id="secondary" class="scroll"><div class="history"></div><div class="live"></div></div>';
    const style = document.createElement('style');
    style.textContent = '.scroll{height:500px;width:600px;overflow:auto;display:flex;flex-direction:column;gap:8px}.history,.live{display:flex;flex-direction:column;gap:8px}.chat-msg{height:36px;flex:none}.chat-history-spacer{flex:none}';
    document.head.appendChild(style);

    const runtime = window.ChatHistoryRuntime;
    const canvas = document.createElement('canvas');
    document.body.appendChild(canvas);
    let canvasFrames = 0;
    let canvasFrame = requestAnimationFrame(() => { canvasFrames += 1; });
    cancelAnimationFrame(canvasFrame);
    const messages = Array.from({ length: 1000 }, (_, index) => ({
      id: 'message-' + index,
      version: 'v1',
      role: index % 2 ? 'assistant' : 'user',
      text: 'history ' + index,
      epochMs: index + 1,
      status: 'done',
    }));
    const deferred = new Map();
    const requestCounts = new Map();
    const fetchImpl = url => {
      const query = new URL(url, location.href).searchParams;
      const conversation = query.get('conversationId') || query.get('sessionKey');
      requestCounts.set(conversation, (requestCounts.get(conversation) || 0) + 1);
      return new Promise(resolve => deferred.set(conversation, resolve));
    };
    const store = new runtime.ChatHistoryStore({ fetchImpl });
    const context = { providerKind: 'codex', agentId: 'agent', conversationId: 'cached' };
    const entry = store.getOrCreate(context);
    store.mergePage(entry, { messages, hasMore: false }, 'latest');

    function buildView(id) {
      const scrollElement = document.getElementById(id);
      const historyLayer = scrollElement.querySelector('.history');
      const liveLayer = scrollElement.querySelector('.live');
      const view = new runtime.ChatHistoryView({
        scrollElement,
        historyLayer,
        liveLayer,
        fallbackHeight: 36,
        renderMessage(message, options) {
          const root = document.createElement('div');
          root.className = 'chat-msg';
          root.textContent = message.text;
          const details = document.createElement('details');
          details.innerHTML = '<summary>tool</summary><span>result</span>';
          root.appendChild(details);
          if (message.id === 'message-999') {
            const media = document.createElement('img');
            media.alt = 'fixture media';
            media.style.display = 'block';
            media.style.height = '8px';
            media.src = 'data:image/gif;base64,R0lGODlhAQABAAD/ACwAAAAAAQABAAACADs=';
            root.appendChild(media);
          }
          options.parent.appendChild(root);
          return root;
        },
      });
      return { scrollElement, historyLayer, liveLayer, view };
    }

    const primary = buildView('primary');
    store.activate(context, primary.view);
    primary.view.activate(entry);
    const latestPromise = store.fetchLatest(context);
    const cachedBeforeNetwork = primary.historyLayer.querySelector('[data-history-message-id]')?.textContent.includes('history 950');
    const latestCount = primary.historyLayer.querySelectorAll('[data-history-message-id]').length;

    const anchor = primary.historyLayer.querySelector('[data-history-message-id="message-950"]');
    const anchorBefore = anchor.getBoundingClientRect().top;
    primary.view.navigate('older');
    await new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)));
    const anchorAfter = primary.historyLayer.querySelector('[data-history-message-id="message-950"]').getBoundingClientRect().top;
    const anchorDrift = Math.abs(anchorAfter - anchorBefore);

    for (let index = 0; index < 30; index += 1) primary.view.navigate('older');
    const oldEndReached = primary.view.range.start === 0;
    let maxRoots = primary.historyLayer.querySelectorAll('[data-history-message-id]').length;
    for (let index = 0; index < 30; index += 1) {
      primary.view.navigate('newer');
      maxRoots = Math.max(maxRoots, primary.historyLayer.querySelectorAll('[data-history-message-id]').length);
    }
    const newEndReached = primary.view.range.end === 1000;

    const details = primary.historyLayer.querySelector('details');
    details.open = true;
    details.dispatchEvent(new Event('toggle'));
    primary.view.renderAll();
    const detailsRestored = primary.historyLayer.querySelector('details')?.open === true;
    const liveMarker = document.createElement('div');
    liveMarker.id = 'live-marker';
    primary.liveLayer.appendChild(liveMarker);
    primary.view.renderAll();
    const livePreserved = Boolean(document.getElementById('live-marker'));
    const mediaRoot = primary.historyLayer.querySelector('[data-history-message-id="message-999"]');
    const media = mediaRoot?.querySelector('img');
    if (media) {
      media.style.height = '48px';
      media.dispatchEvent(new Event('load'));
      await new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)));
    }
    const mediaRemeasured = Number(primary.view.heights.get('message-999') || 0) >= 36;

    const secondary = buildView('secondary');
    store.activate(context, secondary.view);
    secondary.view.activate(entry);
    const secondaryCacheReuse = secondary.historyLayer.querySelectorAll('[data-history-message-id]').length === 50;

    const contextA = { providerKind: 'codex', agentId: 'agent', conversationId: 'out-of-order-a' };
    const contextB = { providerKind: 'codex', agentId: 'agent', conversationId: 'out-of-order-b' };
    const contextC = { providerKind: 'codex', agentId: 'agent', conversationId: 'out-of-order-c' };
    store.activate(contextA, primary.view);
    primary.view.activate(store.getOrCreate(contextA));
    const requestA = store.fetchLatest(contextA);
    store.activate(contextB, primary.view);
    primary.view.activate(store.getOrCreate(contextB));
    const requestB = store.fetchLatest(contextB);
    store.activate(contextC, primary.view);
    primary.view.activate(store.getOrCreate(contextC));
    const requestC = store.fetchLatest(contextC);
    deferred.get('out-of-order-b')({ ok: true, json: async () => ({ ok: true, messages: [{ id: 'b', version: '1', role: 'assistant', text: 'B', epochMs: 2 }], hasMore: false }) });
    await requestB;
    deferred.get('out-of-order-a')({ ok: true, json: async () => ({ ok: true, messages: [{ id: 'a', version: '1', role: 'assistant', text: 'A', epochMs: 1 }], hasMore: false }) });
    await requestA;
    deferred.get('out-of-order-c')({ ok: true, json: async () => ({ ok: true, messages: [{ id: 'c', version: '1', role: 'assistant', text: 'C', epochMs: 3 }], hasMore: false }) });
    await requestC;
    const staleIsolation = primary.historyLayer.textContent.includes('C') && !primary.historyLayer.textContent.includes('A') && !primary.historyLayer.textContent.includes('B');

    deferred.get('cached')({ ok: true, json: async () => ({ ok: true, messages: messages.slice(-50), hasMore: true, nextCursor: 'older' }) });
    await latestPromise;
    const measures = performance.getEntriesByName('vo-chat-history:render-batch');
    const maxRenderBatchMs = Math.max(0, ...measures.map(item => item.duration));
    canvasFrame = requestAnimationFrame(() => { canvasFrames += 1; });
    await new Promise(resolve => requestAnimationFrame(resolve));
    cancelAnimationFrame(canvasFrame);

    return {
      cachedBeforeNetwork,
      latestCount,
      maxRoots,
      anchorDrift,
      oldEndReached,
      newEndReached,
      detailsRestored,
      livePreserved,
      mediaRemeasured,
      staleIsolation,
      secondaryCacheReuse,
      cachedRequests: requestCounts.get('cached') || 0,
      maxRenderBatchMs,
      canvasAnimationRestored: canvasFrames > 0,
    };
  })()`);

  assert.equal(result.cachedBeforeNetwork, true, 'cached content must paint before the delayed latest response');
  assert.ok(result.latestCount <= 50, `cold/latest mount should be <=50, got ${result.latestCount}`);
  assert.ok(result.maxRoots <= 160, `mounted history roots should be <=160, got ${result.maxRoots}`);
  assert.ok(result.anchorDrift <= 2, `anchor drift should be <=2px, got ${result.anchorDrift}`);
  assert.equal(result.oldEndReached, true, 'the virtual window must navigate to the oldest loaded message');
  assert.equal(result.newEndReached, true, 'the virtual window must navigate back to the newest loaded message');
  assert.equal(result.detailsRestored, true, 'interactive details state must survive bounded redraws');
  assert.equal(result.livePreserved, true, 'history redraws must preserve the live layer');
  assert.equal(result.mediaRemeasured, true, 'media load/resize must refresh measured history heights');
  assert.equal(result.staleIsolation, true, 'out-of-order responses must not mutate the selected conversation DOM');
  assert.equal(result.secondaryCacheReuse, true, 'a secondary view must synchronously reuse the shared cache');
  assert.equal(result.canvasAnimationRestored, true, 'canvas animation must resume after the controlled performance section');
  assert.equal(result.cachedRequests, 1, 'same-key refreshes must deduplicate while in flight');
  assert.ok(result.maxRenderBatchMs < 50, `history render batches should stay below 50ms, got ${result.maxRenderBatchMs.toFixed(2)}ms`);
  console.log(`chat history performance checks passed (max roots ${result.maxRoots}, anchor drift ${result.anchorDrift.toFixed(2)}px, max batch ${result.maxRenderBatchMs.toFixed(2)}ms)`);
} finally {
  pageWs.close();
  await closeCdpPage(page);
}
