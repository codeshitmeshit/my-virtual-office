const liveUrl = process.env.VO_LIVE_URL || 'http://10.43.55.108:8090/';
const pageInfo = await (await fetch(`http://127.0.0.1:9224/json/new?${encodeURIComponent(`${liveUrl}?meeting-action-items=${Date.now()}`)}`, { method: 'PUT' })).json();

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
await send(ws, 'Page.navigate', { url: `${liveUrl}?meeting-action-items=${Date.now()}` }).catch(() => {});

for (let i = 0; i < 120; i++) {
  const ready = await evalJson(ws, `Boolean(window.ProjMgr && window.ProjMgr.openProjectsManager && document.body && document.body.innerText.length > 100)`).catch(() => false);
  if (ready) break;
  await new Promise((resolve) => setTimeout(resolve, 250));
}

const result = await evalJson(ws, `new Promise(async (resolve) => {
  const wait = (ms) => new Promise(r => setTimeout(r, ms));
  const out = {};
  try {
    window.ProjMgr.openProjectsManager();
    for (let i = 0; i < 80; i++) {
      if ((document.body.innerText || '').includes('Meeting Action Items Acceptance')) break;
      await wait(150);
    }
    const projects = await (await fetch('/api/projects')).json();
    const project = (projects.projects || []).find(p => p.title === 'Meeting Action Items Acceptance');
    out.projectFound = Boolean(project);
    if (project) window.ProjMgr.openProject(project.id);
    for (let i = 0; i < 80; i++) {
      if ((document.body.innerText || '').includes('Implement source task after meeting')) break;
      await wait(150);
    }
    const refreshed = await (await fetch('/api/projects/' + encodeURIComponent(project.id))).json();
    const task = ((refreshed.project || {}).tasks || []).find(t => t.title === 'Implement source task after meeting');
    out.taskFound = Boolean(task);
    if (task) window.ProjMgr.openTaskDetail(task.id);
    for (let i = 0; i < 80; i++) {
      if (document.querySelector('.proj-meeting-action-panel')) break;
      await wait(150);
    }
    const panel = document.querySelector('.proj-meeting-action-panel');
    const checklistText = Array.from(document.querySelectorAll('#detail-checklist .proj-checklist-item')).map(el => el.innerText);
    const commentsText = Array.from(document.querySelectorAll('#detail-comments .proj-comment')).map(el => el.innerText);
    out.panelFound = Boolean(panel);
    out.panelText = panel ? panel.innerText : '';
    out.pendingCount = panel ? panel.querySelectorAll('.status-pending').length : 0;
    out.linkedCount = panel ? panel.querySelectorAll('.status-external_task_created').length : 0;
    out.panelHasMeetingAction = out.panelText.includes('Apply meeting decision');
    out.checklistHasMeetingAction = checklistText.some(t => t.includes('行动项：Apply meeting decision') || t.includes('Meeting action: Apply meeting decision'));
    out.checklistHasMeetingRisk = checklistText.some(t => t.includes('Meeting risk: Original task must not resume') || t.includes('会议风险'));
    out.commentsHasMeetingRisk = commentsText.some(t => t.includes('会议风险') && t.includes('Original task must not resume'));
    out.bodySample = (document.body.innerText || '').slice(0, 1600);
  } catch (e) {
    out.error = String(e && e.stack || e);
  }
  resolve(out);
})`);

console.log(JSON.stringify(result, null, 2));
if (!result.projectFound || !result.taskFound || !result.panelFound || result.pendingCount < 1 || result.linkedCount < 1 || !result.panelHasMeetingAction || result.checklistHasMeetingAction || result.checklistHasMeetingRisk || !result.commentsHasMeetingRisk) {
  throw new Error('Meeting action item UI check failed');
}

fetch(`http://127.0.0.1:9224/json/close/${encodeURIComponent(pageInfo.id)}`).catch(() => {});
ws.close();
