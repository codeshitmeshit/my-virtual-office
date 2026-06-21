const liveUrl = 'http://10.110.139.216:8090/';
const pageInfo = await (await fetch(`http://127.0.0.1:9224/json/new?${encodeURIComponent(`${liveUrl}?live-feedback=${Date.now()}`)}`, { method: 'PUT' })).json();
const created = true;

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
await send(ws, 'Page.navigate', { url: `${liveUrl}?live-feedback=${Date.now()}` }).catch(() => {});

const result = { created };
for (let i = 0; i < 120; i++) {
  const ready = await evalJson(ws, `Boolean(window.openArchiveRoom && document.body && document.body.innerText.length > 100)`).catch(() => false);
  if (ready) break;
  await new Promise((resolve) => setTimeout(resolve, 250));
}
await evalJson(ws, `(() => {
  if (window.openArchiveRoom) window.openArchiveRoom();
  else {
    const btn = Array.from(document.querySelectorAll('button')).find(b => (b.innerText || '').includes('档案室'));
    if (btn) btn.click();
  }
  return true;
})()`).catch(() => {});

for (let i = 0; i < 80; i++) {
  const ready = await evalJson(ws, `Boolean(document.querySelector('.archive-room-modal-content') && document.body.innerText.includes('刷新当前档案'))`).catch(() => false);
  if (ready) break;
  await new Promise((resolve) => setTimeout(resolve, 150));
}

Object.assign(result, await evalJson(ws, `(() => {
  try {
    window.__archiveLiveCheckListBefore = document.querySelector('.archive-room-list');
    const button = Array.from(document.querySelectorAll('button')).find(b => (b.innerText || '').includes('刷新当前档案'));
    return {
      url: location.href,
      buttonFound: Boolean(button),
      initialButtonText: button ? button.innerText : '',
      listNodeBefore: Boolean(window.__archiveLiveCheckListBefore),
      scrollBefore: window.__archiveLiveCheckListBefore ? window.__archiveLiveCheckListBefore.scrollTop : -1,
      textSample: ((document.body && document.body.innerText) || '').slice(0, 1200),
    };
  } catch (e) {
    return { url: location.href, buttonFound: false, error: String(e), textSample: '' };
  }
})()`));

if (result.buttonFound) {
  await evalJson(ws, `(() => {
    const button = Array.from(document.querySelectorAll('button')).find(b => (b.innerText || '').includes('刷新当前档案'));
    if (button) button.click();
    return true;
  })()`);
  await new Promise((resolve) => setTimeout(resolve, 120));
  Object.assign(result, await evalJson(ws, `(() => {
    const text = document.body.innerText || '';
    return {
      runningVisible: text.includes('档案管理员正在刷新当前档案') && text.includes('刷新中...'),
      runningButtonText: (Array.from(document.querySelectorAll('button')).find(b => (b.innerText || '').includes('刷新中')) || {}).innerText || '',
    };
  })()`));
  for (let i = 0; i < 120; i++) {
    const done = await evalJson(ws, `(() => {
      const text = document.body.innerText || '';
      return text.includes('档案刷新完成') || text.includes('档案刷新失败');
    })()`).catch(() => false);
    if (done) break;
    await new Promise((resolve) => setTimeout(resolve, 250));
  }
  Object.assign(result, await evalJson(ws, `(() => {
    const text = document.body.innerText || '';
    const listAfter = document.querySelector('.archive-room-list');
    return {
      doneVisible: text.includes('档案刷新完成'),
      errorVisible: text.includes('档案刷新失败'),
      finalButtonText: (Array.from(document.querySelectorAll('button')).find(b => (b.innerText || '').includes('刷新当前档案')) || {}).innerText || '',
      summaryVisible: text.includes('当前项目档案已根据现有项目、任务和产物记录刷新'),
      listReplaced: window.__archiveLiveCheckListBefore && listAfter ? window.__archiveLiveCheckListBefore !== listAfter : null,
      scrollAfter: listAfter ? listAfter.scrollTop : -1,
      noticeSample: text.split('\\n').filter(line => line.includes('档案刷新') || line.includes('刷新当前档案') || line.includes('档案管理员正在')).slice(0, 8),
    };
  })()`));
}

console.log(JSON.stringify(result, null, 2));
ws.close();
