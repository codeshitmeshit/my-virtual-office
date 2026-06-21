import fs from 'node:fs';

const browserVersion = await (await fetch('http://127.0.0.1:9224/json/version')).json();
const archiveRoomJs = fs.readFileSync('app/archive-room.js', 'utf8');
const archiveRoomCss = fs.readFileSync('app/archive-room.css', 'utf8');
const realOverview = await (await fetch('http://127.0.0.1:8090/api/archive-room')).json();
const realProjects = {};
for (const p of (realOverview.projects || []).slice(0, 8)) {
  realProjects[p.id] = await (await fetch(`http://127.0.0.1:8090/api/archive-room/projects/${p.id}`)).json();
}
const pageInfo = await (await fetch('http://127.0.0.1:9224/json/new?http://127.0.0.1:8090/', { method: 'PUT' })).json();

function openWs(url) {
  return new Promise((resolve, reject) => {
    const timer = setTimeout(() => reject(new Error('Timed out opening websocket')), 10000);
    const ws = new WebSocket(url);
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
    const timer = setTimeout(() => {
      ws.removeEventListener('message', onMessage);
      reject(new Error(`Timed out waiting for ${method}`));
    }, method === 'Runtime.evaluate' ? 30000 : 10000);
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

async function waitFor(ws, expression, timeoutMs = 20000) {
  const start = Date.now();
  while (Date.now() - start < timeoutMs) {
    try {
      const value = await evalJson(ws, expression);
      if (value) return value;
    } catch {}
    await new Promise((resolve) => setTimeout(resolve, 250));
  }
  throw new Error(`Timed out: ${expression}`);
}

const ws = await openWs(pageInfo.webSocketDebuggerUrl);
await send(ws, 'Page.enable');
await send(ws, 'Runtime.enable');
await send(ws, 'Emulation.setDeviceMetricsOverride', { width: 1440, height: 1000, deviceScaleFactor: 1, mobile: false });
try {
  await waitFor(ws, 'Boolean(window.openArchiveRoom && window.ArchiveRoom)', 4000);
} catch {
  await send(ws, 'Page.stopLoading').catch(() => {});
  await evalJson(ws, `(() => {
    document.documentElement.innerHTML = '<head><meta charset="utf-8"><title>档案室切换检查</title></head><body><div id="archiveRoomModal" class="archive-room-modal"><div class="archive-room-modal-content"><div class="archive-room-header"><h2>🗄️ 档案室</h2><div id="archive-room-manager"></div></div><div id="archive-room-content" class="archive-room-content"></div></div></div></body>';
    const style = document.createElement('style');
    style.textContent = ${JSON.stringify(archiveRoomCss)};
    document.head.appendChild(style);
    const script = document.createElement('script');
    script.textContent = ${JSON.stringify(archiveRoomJs)};
    document.body.appendChild(script);
    const overviewPayload = ${JSON.stringify(realOverview)};
    const projectPayloads = ${JSON.stringify(realProjects)};
    window.fetch = async (input) => {
      const url = String(input || '');
      if (url === '/api/archive-room' || url.endsWith('/api/archive-room')) {
        return new Response(JSON.stringify(overviewPayload), { status: 200, headers: { 'Content-Type': 'application/json' } });
      }
      const m = url.match(/\\/api\\/archive-room\\/projects\\/([^/?]+)/);
      if (m && projectPayloads[decodeURIComponent(m[1])]) {
        return new Response(JSON.stringify(projectPayloads[decodeURIComponent(m[1])]), { status: 200, headers: { 'Content-Type': 'application/json' } });
      }
      return new Response(JSON.stringify({ error: 'Unexpected fetch: ' + url }), { status: 404, headers: { 'Content-Type': 'application/json' } });
    };
    return Boolean(window.openArchiveRoom && window.ArchiveRoom);
  })()`);
  await waitFor(ws, 'Boolean(window.openArchiveRoom && window.ArchiveRoom)', 10000);
}

const result = await evalJson(ws, `new Promise(async (resolve) => {
  const wait = (ms) => new Promise(r => setTimeout(r, ms));
  window.openArchiveRoom();
  for (let i = 0; i < 80; i++) {
    if (document.querySelectorAll('.archive-project-card').length >= 3) break;
    await wait(150);
  }
  const list0 = document.querySelector('.archive-room-list');
  const first0 = document.querySelector('.archive-project-card');
  const cards0 = Array.from(document.querySelectorAll('.archive-project-card'));
  const target = cards0.find(card => !(card.className || '').includes('active')) || cards0[1];
  if (!list0 || !first0 || !target) {
    resolve({ ok: false, reason: 'missing-list-or-target', text: document.body.innerText.slice(0, 1000) });
    return;
  }
  list0.scrollTop = Math.min(420, list0.scrollHeight);
  const beforeScroll = list0.scrollTop;
  const beforeTitle = target.innerText.split('\\n')[0];
  target.click();
  await wait(120);
  const duringList = document.querySelector('.archive-room-list');
  const duringFirst = document.querySelector('.archive-project-card');
  const duringText = document.body.innerText.slice(0, 1000);
  for (let i = 0; i < 80; i++) {
    const loading = (document.body.innerText || '').includes('正在加载项目档案');
    if (!loading) break;
    await wait(100);
  }
  await wait(200);
  const afterList = document.querySelector('.archive-room-list');
  const afterFirst = document.querySelector('.archive-project-card');
  resolve({
    ok: true,
    clicked: beforeTitle,
    listReplacedDuring: duringList !== list0,
    firstCardReplacedDuring: duringFirst !== first0,
    listReplacedAfter: afterList !== list0,
    firstCardReplacedAfter: afterFirst !== first0,
    beforeScroll,
    duringScroll: duringList ? duringList.scrollTop : -1,
    afterScroll: afterList ? afterList.scrollTop : -1,
    activeCount: document.querySelectorAll('.archive-project-card.active').length,
    duringText,
  });
})`);

console.log(JSON.stringify(result, null, 2));
fetch(`http://127.0.0.1:9224/json/close/${encodeURIComponent(pageInfo.id)}`).catch(() => {});
ws.close();
