import fs from 'node:fs';
import { apiURL, closeCdpPage, createCdpPage } from './cdp-test-utils.mjs';

const archiveRoomJs = fs.readFileSync('app/archive-room.js', 'utf8');
const archiveRoomCss = fs.readFileSync('app/archive-room.css', 'utf8');
const realOverview = await (await fetch(`${apiURL}/api/archive-room`)).json();
const firstProjectId = (realOverview.projects || [])[0]?.id;
const realProject = await (await fetch(`${apiURL}/api/archive-room/projects/${firstProjectId}`)).json();
const pageInfo = await createCdpPage('about:blank');

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
    const timer = setTimeout(() => reject(new Error(`Timed out ${method}`)), 30000);
    const onMessage = (event) => {
      const msg = JSON.parse(event.data.toString());
      if (msg.id !== id) return;
      clearTimeout(timer);
      ws.removeEventListener('message', onMessage);
      if (msg.error) reject(new Error(JSON.stringify(msg.error)));
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
await evalJson(ws, `(() => {
  document.documentElement.innerHTML = '<head><meta charset="utf-8"><title>档案室样式检查</title></head><body><div id="archiveRoomModal" class="archive-room-modal"><div class="archive-room-modal-content"><div class="archive-room-header"><h2>🗄️ 档案室</h2><div id="archive-room-manager"></div></div><div id="archive-room-content" class="archive-room-content"></div></div></div></body>';
  const style = document.createElement('style');
  style.textContent = ${JSON.stringify(archiveRoomCss)};
  document.head.appendChild(style);
  const script = document.createElement('script');
  script.textContent = ${JSON.stringify(archiveRoomJs)};
  document.body.appendChild(script);
  window.fetch = async (input) => {
    const url = String(input || '');
    if (url === '/api/archive-room') return new Response(JSON.stringify(${JSON.stringify(realOverview)}), { status: 200, headers: { 'Content-Type': 'application/json' } });
    if (url.includes('/api/archive-room/projects/')) return new Response(JSON.stringify(${JSON.stringify(realProject)}), { status: 200, headers: { 'Content-Type': 'application/json' } });
    return new Response(JSON.stringify({ error: 'unexpected' }), { status: 404, headers: { 'Content-Type': 'application/json' } });
  };
  return true;
})()`);

const result = await evalJson(ws, `new Promise(async (resolve) => {
  window.openArchiveRoom();
  const wait = (ms) => new Promise(r => setTimeout(r, ms));
  for (let i = 0; i < 60; i++) {
    if (document.querySelector('.archive-detail-actions .archive-primary-btn')) break;
    await wait(100);
  }
  const pill = document.querySelector('.archive-status-pill');
  const btn = document.querySelector('.archive-detail-actions .archive-primary-btn');
  const ps = pill ? getComputedStyle(pill) : null;
  const bs = btn ? getComputedStyle(btn) : null;
  resolve({
    pillText: pill?.innerText || '',
    buttonText: btn?.innerText || '',
    pillFontSize: ps?.fontSize || '',
    buttonFontSize: bs?.fontSize || '',
    pillHeight: pill ? Math.round(pill.getBoundingClientRect().height) : 0,
    buttonHeight: btn ? Math.round(btn.getBoundingClientRect().height) : 0,
    pillLineHeight: ps?.lineHeight || '',
    buttonLineHeight: bs?.lineHeight || '',
  });
})`);

console.log(JSON.stringify(result, null, 2));
closeCdpPage(pageInfo);
ws.close();
