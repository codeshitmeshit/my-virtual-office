import fs from 'node:fs';
import { apiURL, closeCdpPage, createCdpPage } from './cdp-test-utils.mjs';

const archiveRoomJs = fs.readFileSync('app/archive-room.js', 'utf8');
const archiveRoomCss = fs.readFileSync('app/archive-room.css', 'utf8');
const overview = await (await fetch(`${apiURL}/api/archive-room`)).json();
const projectId = (overview.projects || [])[0]?.id;
const project = await (await fetch(`${apiURL}/api/archive-room/projects/${projectId}`)).json();
const refined = {
  ok: true,
  project: {
    ...project.project,
    managerMaintenance: [
      ...((project.project || {}).managerMaintenance || []),
      {
        at: new Date().toISOString(),
        status: 'ok',
        eventType: 'ai_refine',
        summary: '档案管理员 AI 已完成精整并入档。',
        output: { summary: '档案管理员 AI 已完成精整并入档。' },
      },
    ],
  },
  archiveManager: (project.project || {}).archiveManager || overview.archiveManager || {},
  maintenance: {
    status: 'ok',
    summary: '档案管理员 AI 已完成精整并入档。',
    output: { summary: '档案管理员 AI 已完成精整并入档。' },
  },
};

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
  document.documentElement.innerHTML = '<head><meta charset="utf-8"><title>AI 精整反馈检查</title></head><body><div id="archiveRoomModal" class="archive-room-modal"><div class="archive-room-modal-content"><div class="archive-room-header"><h2>🗄️ 档案室</h2><div id="archive-room-manager"></div></div><div id="archive-room-content" class="archive-room-content"></div></div></div></body>';
  const style = document.createElement('style');
  style.textContent = ${JSON.stringify(archiveRoomCss)};
  document.head.appendChild(style);
  const script = document.createElement('script');
  script.textContent = ${JSON.stringify(archiveRoomJs)};
  document.body.appendChild(script);
  const overview = ${JSON.stringify(overview)};
  const project = ${JSON.stringify(project)};
  const refined = ${JSON.stringify(refined)};
  window.__aiRefineCalled = false;
  window.fetch = async (input) => {
    const url = String(input || '');
    if (url === '/api/archive-room') return new Response(JSON.stringify(overview), { status: 200, headers: { 'Content-Type': 'application/json' } });
    if (url.includes('/api/archive-room/projects/') && url.endsWith('/ai-refine')) {
      window.__aiRefineCalled = true;
      await new Promise(r => setTimeout(r, 250));
      return new Response(JSON.stringify(refined), { status: 200, headers: { 'Content-Type': 'application/json' } });
    }
    if (url.includes('/api/archive-room/projects/')) return new Response(JSON.stringify(project), { status: 200, headers: { 'Content-Type': 'application/json' } });
    return new Response(JSON.stringify({ error: 'unexpected ' + url }), { status: 404, headers: { 'Content-Type': 'application/json' } });
  };
  return true;
})()`);

const result = await evalJson(ws, `new Promise(async (resolve) => {
  const wait = (ms) => new Promise(r => setTimeout(r, ms));
  window.openArchiveRoom();
  for (let i = 0; i < 80; i++) {
    if (document.body.innerText.includes('AI 精整档案')) break;
    await wait(100);
  }
  const btn = Array.from(document.querySelectorAll('button')).find(b => (b.innerText || '').includes('AI 精整档案'));
  const initialButton = btn?.innerText || '';
  btn?.click();
  await wait(80);
  const runningText = document.body.innerText || '';
  for (let i = 0; i < 80; i++) {
    const buttonText = (Array.from(document.querySelectorAll('button')).find(b => (b.innerText || '').includes('AI 精整档案')) || {}).innerText || '';
    if (window.__aiRefineCalled && buttonText.includes('AI 精整档案')) break;
    await wait(100);
  }
  const doneText = document.body.innerText || '';
  resolve({
    initialButton,
    aiRefineCalled: window.__aiRefineCalled,
    runningVisible: runningText.includes('处理中...'),
    detailNoticeVisible: Boolean(document.querySelector('.archive-manager-notice')),
    finalButtonText: (Array.from(document.querySelectorAll('button')).find(b => (b.innerText || '').includes('AI 精整档案')) || {}).innerText || '',
    activityVisible: doneText.includes('完成 AI 精整项目档案') || doneText.includes('AI 精整项目档案'),
  });
})`);

console.log(JSON.stringify(result, null, 2));
closeCdpPage(pageInfo);
ws.close();
