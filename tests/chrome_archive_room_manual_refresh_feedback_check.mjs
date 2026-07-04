import fs from 'node:fs';
import { spawnSync } from 'node:child_process';

const archiveRoomJs = fs.readFileSync('app/archive-room.js', 'utf8');
const archiveRoomCss = fs.readFileSync('app/archive-room.css', 'utf8');

async function loadOverviewWithFixture() {
  let data = await (await fetch('http://127.0.0.1:8090/api/archive-room')).json();
  if ((data.projects || []).length) return data;
  const python = fs.existsSync('.venv/bin/python') ? '.venv/bin/python' : 'python3';
  const seeded = spawnSync(python, ['tests/seed_archive_room_phase7_fixture.py'], { encoding: 'utf8', env: { ...process.env, VO_STATUS_DIR: `${process.cwd()}/data` } });
  if (seeded.status !== 0) throw new Error(`Failed to seed archive room fixture: ${seeded.stderr || seeded.stdout}`);
  data = await (await fetch('http://127.0.0.1:8090/api/archive-room')).json();
  if (!(data.projects || []).length) throw new Error('Archive room fixture did not create a visible project');
  return data;
}

const overview = await loadOverviewWithFixture();
const projectId = (overview.projects || [])[0]?.id;
const project = await (await fetch(`http://127.0.0.1:8090/api/archive-room/projects/${projectId}`)).json();
let maintainCalled = false;
const maintained = {
  ok: true,
  project: {
    ...project.project,
    managerMaintenance: [
      ...((project.project || {}).managerMaintenance || []),
      {
        at: new Date().toISOString(),
        status: 'ok',
        summary: '当前项目档案已根据现有项目、任务和产物记录刷新。',
      },
    ],
  },
  archiveManager: (project.project || {}).archiveManager || overview.archiveManager || {},
};

const pageInfo = await (await fetch('http://127.0.0.1:9224/json/new?about:blank', { method: 'PUT' })).json();

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
  document.documentElement.innerHTML = '<head><meta charset="utf-8"><title>刷新反馈检查</title></head><body><div id="archiveRoomModal" class="archive-room-modal"><div class="archive-room-modal-content"><div class="archive-room-header"><h2>🗄️ 档案室</h2><div id="archive-room-manager"></div></div><div id="archive-room-content" class="archive-room-content"></div></div></div></body>';
  const style = document.createElement('style');
  style.textContent = ${JSON.stringify(archiveRoomCss)};
  document.head.appendChild(style);
  const script = document.createElement('script');
  script.textContent = ${JSON.stringify(archiveRoomJs)};
  document.body.appendChild(script);
  const overview = ${JSON.stringify(overview)};
  const project = ${JSON.stringify(project)};
  const maintained = ${JSON.stringify(maintained)};
  window.__maintainCalled = false;
  window.fetch = async (input, init) => {
    const url = String(input || '');
    if (url === '/api/archive-room') return new Response(JSON.stringify(overview), { status: 200, headers: { 'Content-Type': 'application/json' } });
    if (url.includes('/api/archive-room/projects/') && url.endsWith('/maintain')) {
      window.__maintainCalled = true;
      await new Promise(r => setTimeout(r, 250));
      return new Response(JSON.stringify(maintained), { status: 200, headers: { 'Content-Type': 'application/json' } });
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
    if (document.querySelector('.archive-detail-actions .archive-primary-btn')) break;
    await wait(100);
  }
  const btn = document.querySelector('.archive-detail-actions .archive-primary-btn');
  const initialButton = btn?.innerText || '';
  btn?.click();
  await wait(60);
  const runningText = document.body.innerText;
  for (let i = 0; i < 80; i++) {
    if ((document.body.innerText || '').includes('档案刷新完成')) break;
    await wait(100);
  }
  const doneText = document.body.innerText;
  resolve({
    initialButton,
    maintainCalled: window.__maintainCalled,
    runningVisible: runningText.includes('档案管理员正在刷新当前档案') && runningText.includes('刷新中...'),
    doneVisible: doneText.includes('档案刷新完成') && doneText.includes('当前项目档案已根据现有项目、任务和产物记录刷新。'),
    finalButton: document.querySelector('.archive-detail-actions .archive-primary-btn')?.innerText || '',
  });
})`);

console.log(JSON.stringify(result, null, 2));
fetch(`http://127.0.0.1:9224/json/close/${encodeURIComponent(pageInfo.id)}`).catch(() => {});
ws.close();
