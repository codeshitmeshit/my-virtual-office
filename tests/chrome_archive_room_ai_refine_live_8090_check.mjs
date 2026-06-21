const liveUrl = 'http://10.110.139.216:8090/';
const pageInfo = await (await fetch(`http://127.0.0.1:9224/json/new?${encodeURIComponent(`${liveUrl}?ai-refine-live=${Date.now()}`)}`, { method: 'PUT' })).json();

function openWs(url) {
  return new Promise((resolve, reject) => {
    const ws = new WebSocket(url);
    const timer = setTimeout(() => reject(new Error('Timed out opening websocket')), 10000);
    ws.addEventListener('open', () => {
      clearTimeout(timer);
      resolve(ws);
    }, { once: true });
    ws.addEventListener('error', reject, { once: true });
  });
}

let seq = 0;
function send(ws, method, params = {}) {
  const id = ++seq;
  ws.send(JSON.stringify({ id, method, params }));
  return new Promise((resolve, reject) => {
    const timer = setTimeout(() => reject(new Error(`Timed out ${method}`)), 45000);
    const onMessage = (event) => {
      const msg = JSON.parse(event.data.toString());
      if (msg.id !== id) return;
      clearTimeout(timer);
      ws.removeEventListener('message', onMessage);
      if (msg.error) reject(new Error(`${method}: ${JSON.stringify(msg.error)}`));
      else resolve(msg.result || {});
    };
    ws.addEventListener('message', onMessage);
  });
}

async function evalJson(ws, expression) {
  const res = await send(ws, 'Runtime.evaluate', { expression, awaitPromise: true, returnByValue: true });
  if (res.exceptionDetails) throw new Error(res.exceptionDetails.text || JSON.stringify(res.exceptionDetails));
  return res.result.value;
}

const ws = await openWs(pageInfo.webSocketDebuggerUrl);
await send(ws, 'Runtime.enable');
await send(ws, 'Page.enable').catch(() => {});
await send(ws, 'Network.enable').catch(() => {});
await send(ws, 'Network.setCacheDisabled', { cacheDisabled: true }).catch(() => {});
await send(ws, 'Page.navigate', { url: `${liveUrl}?ai-refine-live=${Date.now()}` }).catch(() => {});

const result = { url: liveUrl, pageId: pageInfo.id };
for (let i = 0; i < 120; i++) {
  const ready = await evalJson(ws, `Boolean(window.openArchiveRoom && document.body && document.body.innerText.length > 100)`).catch(() => false);
  if (ready) break;
  await new Promise((resolve) => setTimeout(resolve, 250));
}

await evalJson(ws, `(() => {
  const realFetch = window.fetch.bind(window);
  window.__aiRefineLiveCheck = { called: false, payloads: [], errors: [] };
  window.fetch = (input, init = {}) => {
    const url = String(input || '');
    if (url.includes('/api/archive-room/projects/') && url.endsWith('/ai-refine')) {
      window.__aiRefineLiveCheck.called = true;
      const body = Object.assign({}, init && init.body ? JSON.parse(init.body) : {}, { timeoutSec: 3 });
      window.__aiRefineLiveCheck.payloads.push(body);
      return realFetch(input, Object.assign({}, init, { body: JSON.stringify(body) }));
    }
    return realFetch(input, init);
  };
  window.openArchiveRoom();
  return true;
})()`);

for (let i = 0; i < 80; i++) {
  const ready = await evalJson(ws, `Boolean(document.querySelector('.archive-room-modal-content') && document.body.innerText.includes('AI 精整档案'))`).catch(() => false);
  if (ready) break;
  await new Promise((resolve) => setTimeout(resolve, 150));
}

Object.assign(result, await evalJson(ws, `(() => {
  const button = Array.from(document.querySelectorAll('button')).find(b => (b.innerText || '').includes('AI 精整档案'));
  window.__archiveAiRefineListBefore = document.querySelector('.archive-room-list');
  return {
    buttonFound: Boolean(button),
    initialButtonText: button ? button.innerText : '',
    initialTextSample: (document.body.innerText || '').slice(0, 800),
  };
})()`));

if (result.buttonFound) {
  await evalJson(ws, `(() => {
    const button = Array.from(document.querySelectorAll('button')).find(b => (b.innerText || '').includes('AI 精整档案'));
    if (button) button.click();
    return true;
  })()`);
  await new Promise((resolve) => setTimeout(resolve, 200));
  Object.assign(result, await evalJson(ws, `(() => {
    const text = document.body.innerText || '';
    return {
      runningVisible: text.includes('已委派档案管理员 AI 精整档案') && text.includes('处理中...'),
      runningButtonText: (Array.from(document.querySelectorAll('button')).find(b => (b.innerText || '').includes('处理中')) || {}).innerText || '',
    };
  })()`));
  for (let i = 0; i < 160; i++) {
    const done = await evalJson(ws, `(() => {
      const text = document.body.innerText || '';
      return text.includes('AI 精整失败') || text.includes('AI 精整完成') || text.includes('Unexpected end of JSON input');
    })()`).catch(() => false);
    if (done) break;
    await new Promise((resolve) => setTimeout(resolve, 250));
  }
  Object.assign(result, await evalJson(ws, `(() => {
    const text = document.body.innerText || '';
    const listAfter = document.querySelector('.archive-room-list');
    return {
      aiRefineCalled: Boolean(window.__aiRefineLiveCheck && window.__aiRefineLiveCheck.called),
      payloads: (window.__aiRefineLiveCheck && window.__aiRefineLiveCheck.payloads) || [],
      failedVisible: text.includes('AI 精整失败'),
      timeoutMessageVisible: text.includes('档案管理员调用超时或被中断') || text.includes('档案管理员调用失败'),
      parseErrorVisible: text.includes('Unexpected end of JSON input') || text.includes("Failed to execute 'json'"),
      detailNoticeVisible: Boolean(document.querySelector('.archive-manager-notice')),
      detailStillVisible: Boolean(document.querySelector('.archive-room-detail')),
      listReplaced: window.__archiveAiRefineListBefore && listAfter ? window.__archiveAiRefineListBefore !== listAfter : null,
      finalButtonText: (Array.from(document.querySelectorAll('button')).find(b => (b.innerText || '').includes('AI 精整档案')) || {}).innerText || '',
      noticeSample: text.split('\\n').filter(line => line.includes('AI 精整') || line.includes('档案管理员调用') || line.includes('Unexpected')).slice(0, 10),
    };
  })()`));
}

console.log(JSON.stringify(result, null, 2));
fetch(`http://127.0.0.1:9224/json/close/${encodeURIComponent(pageInfo.id)}`).catch(() => {});
ws.close();
