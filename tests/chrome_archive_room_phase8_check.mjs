import fs from 'node:fs';

const browserVersion = await (await fetch('http://127.0.0.1:9224/json/version')).json();
const archiveRoomJs = fs.readFileSync('app/archive-room.js', 'utf8');
const archiveRoomCss = fs.readFileSync('app/archive-room.css', 'utf8');
const phase8ProjectId = '7e8fb87a-bff6-4442-9854-c761e8c97532';
const realOverview = await (await fetch('http://127.0.0.1:8090/api/archive-room')).json();
const realProject = await (await fetch(`http://127.0.0.1:8090/api/archive-room/projects/${phase8ProjectId}`)).json();
const realMarkdown = await (await fetch(`http://127.0.0.1:8090/api/projects/${phase8ProjectId}/artifacts/read?archive=1&path=docs%2Fphase8%2Fgovernance%2Fsource-comparison.md`)).json();
if (Array.isArray(realOverview.projects)) {
  const targetSummary = realOverview.projects.find((p) => p.id === phase8ProjectId);
  if (targetSummary) {
    realOverview.projects = [
      targetSummary,
      ...realOverview.projects.filter((p) => p.id !== phase8ProjectId),
    ];
  }
}

function send(ws, method, params = {}) {
  const id = ++send.seq;
  ws.send(JSON.stringify({ id, method, params }));
  return new Promise((resolve, reject) => {
    const timeoutMs = method === 'Runtime.evaluate' ? 30000 : 10000;
    const timer = setTimeout(() => {
      ws.removeEventListener('message', onMessage);
      reject(new Error(`Timed out waiting for CDP response: ${method}`));
    }, timeoutMs);
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
send.seq = 0;

function eventOnce(ws, method, predicate = () => true, timeoutMs = 15000) {
  return new Promise((resolve, reject) => {
    const timer = setTimeout(() => {
      ws.removeEventListener('message', onMessage);
      reject(new Error(`Timed out waiting for ${method}`));
    }, timeoutMs);
    const onMessage = (event) => {
      const msg = JSON.parse(event.data.toString());
      if (msg.method === method && predicate(msg.params || {})) {
        clearTimeout(timer);
        ws.removeEventListener('message', onMessage);
        resolve(msg.params || {});
      }
    };
    ws.addEventListener('message', onMessage);
  });
}

async function waitForRuntime(pageWs, expression, timeoutMs = 15000) {
  const start = Date.now();
  let last = '';
  while (Date.now() - start < timeoutMs) {
    const res = await send(pageWs, 'Runtime.evaluate', {
      expression,
      awaitPromise: true,
      returnByValue: true,
    });
    if (res.exceptionDetails) last = res.exceptionDetails.text || JSON.stringify(res.exceptionDetails);
    else if (res.result && res.result.value) return res.result.value;
    await new Promise((resolve) => setTimeout(resolve, 250));
  }
  throw new Error(`Timed out waiting for expression: ${expression}\n${last}`);
}

async function evalJson(pageWs, expression) {
  const res = await send(pageWs, 'Runtime.evaluate', {
    expression,
    awaitPromise: true,
    returnByValue: true,
  });
  if (res.exceptionDetails) throw new Error(res.exceptionDetails.text || JSON.stringify(res.exceptionDetails));
  return res.result.value;
}

function openWs(url, label) {
  return new Promise((resolve, reject) => {
    const timer = setTimeout(() => reject(new Error(`Timed out opening ${label}`)), 10000);
    const ws = new WebSocket(url);
    ws.addEventListener('open', () => {
      clearTimeout(timer);
      resolve(ws);
    }, { once: true });
    ws.addEventListener('error', (event) => {
      clearTimeout(timer);
      reject(new Error(`Failed to open ${label}: ${event.message || 'websocket error'}`));
    }, { once: true });
  });
}

const pageInfo = await (await fetch('http://127.0.0.1:9224/json/new?about:blank', { method: 'PUT' })).json();
if (!pageInfo) throw new Error('Created page not found');
console.log('phase8-cdp: page created');

const pageWs = await openWs(pageInfo.webSocketDebuggerUrl, 'page websocket');

console.log('phase8-cdp: connected');
await send(pageWs, 'Page.enable');
await send(pageWs, 'Runtime.enable');
await send(pageWs, 'DOM.enable');
await send(pageWs, 'Emulation.setDeviceMetricsOverride', {
  width: 1440,
  height: 1000,
  deviceScaleFactor: 1,
  mobile: false,
});

await send(pageWs, 'Page.navigate', { url: 'http://127.0.0.1:8090/' });
await new Promise((resolve) => setTimeout(resolve, 1500));
let hasArchiveRoom = false;
try {
  hasArchiveRoom = Boolean(await waitForRuntime(pageWs, 'Boolean(window.openArchiveRoom && window.ArchiveRoom)', 2500));
} catch {
  hasArchiveRoom = false;
}
if (!hasArchiveRoom) {
  console.log('phase8-cdp: injecting archive room harness');
  await send(pageWs, 'Page.stopLoading').catch(() => {});
  await evalJson(pageWs, `(() => {
    document.documentElement.innerHTML = '<head><meta charset="utf-8"><title>档案室验收</title></head><body><div id="archiveRoomModal" class="archive-room-modal"><div class="archive-room-modal-content"><div class="archive-room-header"><h2>🗄️ 档案室</h2><div id="archive-room-manager"></div></div><div id="archive-room-content" class="archive-room-content"></div></div></div><div id="archiveArtifactOverlay" class="archive-artifact-overlay hidden"><div class="archive-artifact-modal"><div class="archive-artifact-modal-head"><div><div id="archive-artifact-modal-title" class="archive-artifact-modal-title"></div><div id="archive-artifact-modal-meta" class="archive-artifact-modal-meta"></div></div><div class="archive-artifact-modal-actions"><a id="archive-artifact-open-link" class="archive-open-link" target="_blank" rel="noopener">打开</a><button class="archive-secondary-btn" onclick="ArchiveRoom.closeProjectArtifacts()">关闭</button></div></div><div id="archive-artifact-modal-body" class="archive-artifact-modal-body"></div></div></div></body>';
    const style = document.createElement('style');
    style.textContent = ${JSON.stringify(archiveRoomCss)};
    document.head.appendChild(style);
    const script = document.createElement('script');
    script.textContent = ${JSON.stringify(archiveRoomJs)};
    document.body.appendChild(script);
    return Boolean(window.openArchiveRoom && window.ArchiveRoom);
  })()`);
  await waitForRuntime(pageWs, 'Boolean(window.openArchiveRoom && window.ArchiveRoom)', 10000);
}
console.log('phase8-cdp: archive room available');

const result = await evalJson(pageWs, `new Promise(async (resolve) => {
  const pid = ${JSON.stringify(phase8ProjectId)};
  const started = Date.now();
  const timeout = setTimeout(() => resolve({
    error: 'phase8 ui script timeout',
    elapsedMs: Date.now() - started,
    text: (document.body.innerText || '').slice(0, 3000),
    hasArchiveRoom: Boolean(window.ArchiveRoom),
    selectedProject: Boolean(window.ArchiveRoom && window.ArchiveRoom.state && window.ArchiveRoom.state.selectedProject),
  }), 12000);
  const overviewPayload = ${JSON.stringify(realOverview)};
  const projectPayload = ${JSON.stringify(realProject)};
  const markdownPayload = ${JSON.stringify(realMarkdown)};
  window.fetch = async (input, init) => {
    const url = String(input || '');
    let payload = null;
    if (url === '/api/archive-room' || url.endsWith('/api/archive-room')) payload = overviewPayload;
    else if (url.includes('/api/archive-room/projects/' + pid)) payload = projectPayload;
    else if (url.includes('/api/projects/' + pid + '/artifacts/read')) payload = markdownPayload;
    if (payload) {
      return new Response(JSON.stringify(payload), { status: 200, headers: { 'Content-Type': 'application/json' } });
    }
    return new Response(JSON.stringify({ error: 'Unexpected harness fetch: ' + url }), { status: 404, headers: { 'Content-Type': 'application/json' } });
  };
  window.openArchiveRoom();
  const wait = (ms) => new Promise(r => setTimeout(r, ms));
  for (let i = 0; i < 40; i++) {
    if (document.querySelector('.archive-room-modal-content')) break;
    await wait(100);
  }
  for (let i = 0; i < 80; i++) {
    const text = document.body.innerText || '';
    if (text.includes('Archive Room Phase 8 Frequency Governance Acceptance')) break;
    await wait(150);
  }
  try {
    await window.ArchiveRoom.openProject(pid);
  } catch (e) {
    resolve({ error: String(e), phase: 'openProject', text: (document.body.innerText || '').slice(0, 1000) });
    return;
  }
  for (let i = 0; i < 60; i++) {
    const text = document.body.innerText || '';
    if (text.includes('Archive Room Phase 8 Frequency Governance Acceptance') && text.includes('事件触发 + 每周巡检')) break;
    await wait(100);
  }
  const detailBeforeSchedule = document.querySelector('.archive-room-detail');
  const maintenanceControl = document.querySelector('.archive-maintenance-control');
  if (detailBeforeSchedule && maintenanceControl) {
    detailBeforeSchedule.scrollTop = Math.max(0, maintenanceControl.offsetTop - 48);
    await wait(100);
  }
  const scheduleScrollBefore = detailBeforeSchedule ? detailBeforeSchedule.scrollTop : -1;
  const adjust = Array.from(document.querySelectorAll('button')).find(b => (b.innerText || '').includes('调整频率'));
  if (adjust) adjust.click();
  await wait(300);
  const detailAfterSchedule = document.querySelector('.archive-room-detail');
  const scheduleScrollAfter = detailAfterSchedule ? detailAfterSchedule.scrollTop : -1;
  const scheduleScrollPreserved = scheduleScrollBefore >= 0 && scheduleScrollAfter >= 0
    ? Math.abs(scheduleScrollAfter - scheduleScrollBefore) <= 4
    : false;
  const artifactButton = Array.from(document.querySelectorAll('button')).find(b => (b.innerText || '').includes('查看项目产物'));
  if (artifactButton) artifactButton.click();
  await wait(700);
  const pathTab = Array.from(document.querySelectorAll('button')).find(b => (b.innerText || '').includes('按路径'));
  if (pathTab) pathTab.click();
  await wait(400);
  const bodyText = document.body.innerText || '';
  const firstArtifact = document.querySelector('.archive-artifact-row');
  if (firstArtifact) firstArtifact.click();
  await wait(400);
  const bodyAfterArtifact = document.body.innerText || '';
  const englishFragments = Array.from(new Set((bodyAfterArtifact.match(/\\b(?:Artifacts|Updated|No explicitly|Open or download|Unable to read|Current|Project|Done|Backlog|Review|In Progress|Loading archive room|Failed to load|Copy onboarding package|artifact|archive room)\\b/g) || []))).slice(0, 20);
  clearTimeout(timeout);
  resolve({
    elapsedMs: Date.now() - started,
    modal: Boolean(document.querySelector('.archive-room-modal-content')),
    projectVisible: bodyText.includes('Archive Room Phase 8 Frequency Governance Acceptance'),
    weeklyVisible: bodyText.includes('事件触发 + 每周巡检'),
    schedulePanelVisible: bodyText.includes('事件触发 + 每日巡检') && bodyText.includes('事件触发 + 每周巡检'),
    scheduleScrollBefore,
    scheduleScrollAfter,
    scheduleScrollPreserved,
    autoNoticeVisible: bodyText.includes('自动治理') || bodyText.includes('档案管理员已自动处理非人工确认内容'),
    staleVisible: bodyText.includes('已过期') || bodyText.includes('旧内容已标记过期'),
    sourceComparisonVisible: bodyText.includes('来源对比') || bodyText.includes('新来源'),
    pendingVisible: bodyText.includes('待确认') && bodyText.includes('发布规则'),
    artifactBrowserVisible: Boolean(document.querySelector('.archive-artifact-browser')),
    pathViewVisible: bodyAfterArtifact.includes('media') && bodyAfterArtifact.includes('phase8') && bodyAfterArtifact.includes('preview'),
    artifactsVisible: ['video.mp4','image.png','audio.mp3','source-comparison.md'].filter(x => bodyAfterArtifact.includes(x)),
    previewVisible: Boolean(document.querySelector('.archive-artifact-browser-preview')),
    chineseLabelsVisible: ['调整频率','自动治理','已过期','待确认','查看项目产物','按路径','按来源'].filter(x => bodyAfterArtifact.includes(x)),
    englishFragments,
    textSample: bodyAfterArtifact.slice(0, 500),
    textLength: bodyAfterArtifact.length
  });
})`);

const screenshot = await send(pageWs, 'Page.captureScreenshot', { format: 'png', captureBeyondViewport: true });
fs.writeFileSync('/tmp/archive-room-phase8-cdp.png', Buffer.from(screenshot.data, 'base64'));

console.log(JSON.stringify(result, null, 2));

const requiredChecks = [
  'modal',
  'projectVisible',
  'weeklyVisible',
  'schedulePanelVisible',
  'scheduleScrollPreserved',
  'autoNoticeVisible',
  'staleVisible',
  'sourceComparisonVisible',
  'pendingVisible',
  'artifactBrowserVisible',
  'pathViewVisible',
  'previewVisible',
];
const failedChecks = requiredChecks.filter((key) => !result[key]);
if (failedChecks.length) {
  console.error(`Archive Room Phase8 CDP check failed: ${failedChecks.join(', ')}`);
  process.exitCode = 1;
}

fetch(`http://127.0.0.1:9224/json/close/${encodeURIComponent(pageInfo.id)}`).catch(() => {});
pageWs.close();
