const liveUrl = process.env.VO_LIVE_URL || 'http://10.43.55.108:8090/';
const apiUrl = process.env.VO_API_URL || 'http://10.43.55.108:8090';
const pageInfo = await (await fetch(`http://127.0.0.1:9224/json/new?${encodeURIComponent(`${liveUrl}?meeting-records=${Date.now()}`)}`, { method: 'PUT' })).json();

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
let projectId = '';
let externalProject = false;
try {
  let task;
  if (process.env.VO_TEST_PROJECT_ID && process.env.VO_TEST_TASK_ID) {
    projectId = process.env.VO_TEST_PROJECT_ID;
    task = { id: process.env.VO_TEST_TASK_ID };
    externalProject = true;
  } else {
    const title = 'Meeting Records UI ' + Date.now();
    const created = await (await fetch(`${apiUrl}/api/projects`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ title, description: 'Temporary meeting records UI check' })
    })).json();
    const project = created.project;
    projectId = project.id;
    const backlog = (project.columns || []).find(c => c.title === 'Backlog') || project.columns[0];
    const taskCreated = await (await fetch(`${apiUrl}/api/projects/${encodeURIComponent(project.id)}/tasks`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        title: 'Task with meeting records',
        columnId: backlog.id,
        meetingRecords: [
          {
            id: 'meeting:m1:record',
            meetingId: 'm1',
            requestId: 'r1',
            outcome: 'approved',
            status: 'approved',
            decision: 'Ship the daily report after applying copy edits.',
            summary: 'Meeting approved publication.',
            risks: ['Source availability may fluctuate.'],
            actionItems: [{ title: 'Apply copy edits', owner: 'main' }],
            appliedAt: '2026-06-25T10:00:00+00:00',
            createdAt: '2026-06-25T10:00:00+00:00'
          },
          {
            id: 'meeting:m2:record',
            meetingId: 'm2',
            requestId: 'r2',
            outcome: 'no_consensus',
            status: 'no_consensus',
            decision: 'No consensus on auto-publishing.',
            risks: [],
            actionItems: [],
            appliedAt: '2026-06-25T11:00:00+00:00',
            createdAt: '2026-06-25T11:00:00+00:00'
          }
        ],
        meetingActionItems: [{ id: 'a1', meetingId: 'm1', title: 'Apply copy edits', owner: 'main', status: 'pending' }],
        checklist: [{ id: 'c1', text: 'Deliverable remains verifiable', done: false }]
      })
    })).json();
    task = taskCreated.task;
  }

  await send(ws, 'Runtime.enable');
  await send(ws, 'Page.enable').catch(() => {});
  await send(ws, 'Network.enable').catch(() => {});
  await send(ws, 'Network.setCacheDisabled', { cacheDisabled: true }).catch(() => {});
  await send(ws, 'Page.navigate', { url: `${liveUrl}?meeting-records=${Date.now()}` }).catch(() => {});

  for (let i = 0; i < 120; i++) {
    const ready = await evalJson(ws, `Boolean(window.ProjMgr && window.ProjMgr.openProjectsManager && document.body && document.body.innerText.length > 100)`).catch(() => false);
    if (ready) break;
    await new Promise((resolve) => setTimeout(resolve, 250));
  }

  const result = await evalJson(ws, `new Promise(async (resolve) => {
    const wait = (ms) => new Promise(r => setTimeout(r, ms));
    const out = {};
    try {
      const projectId = ${JSON.stringify(projectId)};
      const taskId = ${JSON.stringify(task.id)};
      out.projectId = projectId;
      window.ProjMgr.openProjectsManager();
      await wait(300);
      window.ProjMgr.openProject(projectId);
      for (let i = 0; i < 80; i++) {
        if ((document.body.innerText || '').includes('Task with meeting records')) break;
        await wait(150);
      }
      window.ProjMgr.openTaskDetail(taskId);
      for (let i = 0; i < 80; i++) {
        if ((document.body.innerText || '').includes('Meeting records')) break;
        await wait(150);
      }
      const recordsPanel = document.querySelector('.proj-meeting-discussion-panel');
      const actionsPanel = document.querySelector('.proj-meeting-action-panel');
      out.recordsFound = Boolean(recordsPanel);
      out.recordsText = recordsPanel ? recordsPanel.innerText : '';
      out.actionsFound = Boolean(actionsPanel);
      out.actionsText = actionsPanel ? actionsPanel.innerText : '';
      out.bodySample = (document.body.innerText || '').slice(0, 2000);
    } catch (e) {
      out.error = String(e && e.stack || e);
    }
    resolve(out);
  })`);

  projectId = result.projectId || '';
  console.log(JSON.stringify(result, null, 2));
  const recordsText = String(result.recordsText || '');
  const recordsTextLower = recordsText.toLowerCase();
  if (!result.recordsFound || !recordsTextLower.includes('meeting records') || !recordsText.includes('Ship the daily report') || !recordsText.includes('No consensus') || !recordsText.includes('Source availability') || !recordsText.includes('Apply copy edits') || !result.actionsFound) {
    throw new Error('Project meeting records UI check failed');
  }
} finally {
  if (projectId && !externalProject) {
    await fetch(`${apiUrl}/api/projects/${encodeURIComponent(projectId)}`, { method: 'DELETE' }).catch(() => {});
  }
  fetch(`http://127.0.0.1:9224/json/close/${encodeURIComponent(pageInfo.id)}`).catch(() => {});
  ws.close();
}
