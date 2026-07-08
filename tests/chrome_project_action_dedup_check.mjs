import { apiURL, closeCdpPage, createCdpPage, liveURL } from './cdp-test-utils.mjs';

const liveUrl = liveURL;
const apiUrl = apiURL;
const pageInfo = await createCdpPage(`${liveUrl}?project-action-dedup=${Date.now()}`);

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

let projectId = '';
const ws = await openWs(pageInfo.webSocketDebuggerUrl);
try {
  const created = await (await fetch(`${apiUrl}/api/projects`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ title: `Action Dedup E2E ${Date.now()}`, description: 'Temporary action dedup check' })
  })).json();
  projectId = created.project.id;

  await send(ws, 'Runtime.enable');
  await send(ws, 'Page.enable').catch(() => {});
  await send(ws, 'Network.enable').catch(() => {});
  await send(ws, 'Network.setCacheDisabled', { cacheDisabled: true }).catch(() => {});
  await send(ws, 'Page.navigate', { url: `${liveUrl}?project-action-dedup=${Date.now()}` }).catch(() => {});

  for (let i = 0; i < 120; i += 1) {
    const ready = await evalJson(ws, `Boolean(window.ProjMgr && window.ProjMgr.openProjectsManager && document.body && document.body.innerText.length > 100)`).catch(() => false);
    if (ready) break;
    await new Promise((resolve) => setTimeout(resolve, 250));
  }

  const result = await evalJson(ws, `new Promise(async (resolve) => {
    const wait = (ms) => new Promise(r => setTimeout(r, ms));
    const out = {};
    try {
      const projectId = ${JSON.stringify(projectId)};
      const originalFetch = window.fetch.bind(window);
      let workflowStartCalls = 0;
      window.fetch = async (input, init) => {
        const url = String(input && input.url ? input.url : input);
        if (url.includes('/api/projects/' + encodeURIComponent(projectId) + '/workflow/start')) {
          workflowStartCalls += 1;
          await wait(600);
          return new Response(JSON.stringify({ ok: true }), { status: 200, headers: { 'Content-Type': 'application/json' } });
        }
        return originalFetch(input, init);
      };

      window.ProjMgr.openProjectsManager();
      await wait(250);
      await window.ProjMgr.openProject(projectId);
      for (let i = 0; i < 80; i += 1) {
        if (document.querySelector('#wf-start-btn')) break;
        await wait(100);
      }
      const btn = document.querySelector('#wf-start-btn');
      out.buttonFound = Boolean(btn);
      if (!btn) return resolve(out);

      btn.click();
      await wait(30);
      out.busyAfterFirstClick = btn.disabled === true && btn.getAttribute('aria-busy') === 'true';
      btn.click();
      await wait(900);
      out.workflowStartCalls = workflowStartCalls;
      out.buttonTextAfterFirstClick = btn.dataset.projOriginalText || btn.textContent || '';
      out.toastText = (document.querySelector('#proj-toast') || {}).textContent || '';
      out.bodySample = (document.body.innerText || '').slice(0, 1200);
    } catch (e) {
      out.error = String(e && e.stack || e);
    }
    resolve(out);
  })`);

  console.log(JSON.stringify(result, null, 2));
  if (!result.buttonFound || !result.busyAfterFirstClick || result.workflowStartCalls !== 1) {
    throw new Error('Project action dedup E2E check failed');
  }
} finally {
  if (projectId) {
    await fetch(`${apiUrl}/api/projects/${encodeURIComponent(projectId)}`, { method: 'DELETE' }).catch(() => {});
  }
  closeCdpPage(pageInfo);
  ws.close();
}
