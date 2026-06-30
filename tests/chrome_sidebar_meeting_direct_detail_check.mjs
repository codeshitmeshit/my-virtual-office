const liveUrl = process.env.VO_LIVE_URL || 'http://192.168.100.3:8090/';
const apiUrl = process.env.VO_API_URL || 'http://127.0.0.1:8090';

const active = await (await fetch(`${apiUrl}/api/meetings/active`)).json();
let meeting = (active.meetings || [])[0];
let createdMeetingId = '';
if (!meeting) {
  const topic = 'Sidebar direct detail check ' + Date.now();
  const created = await (await fetch(`${apiUrl}/api/meetings/executable/create`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      topic,
      purpose: 'Temporary UI click verification',
      participants: ['vo-test-agent-1', 'vo-test-agent-2'],
      moderator: 'vo-test-agent-1',
      meetingType: 'discussion',
      maxRounds: 1,
      allowConflicts: true,
      idempotencyKey: 'sidebar-direct-detail-' + Date.now()
    })
  })).json();
  if (!created.meeting) throw new Error(created.error || 'Failed to create temporary meeting');
  meeting = created.meeting;
  createdMeetingId = meeting.id;
}

const pageInfo = await (await fetch(`http://127.0.0.1:9224/json/new?${encodeURIComponent(`${liveUrl}?sidebar-meeting=${Date.now()}`)}`, { method: 'PUT' })).json();

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
try {
  await send(ws, 'Runtime.enable');
  await send(ws, 'Page.enable').catch(() => {});
  await send(ws, 'Network.enable').catch(() => {});
  await send(ws, 'Network.setCacheDisabled', { cacheDisabled: true }).catch(() => {});
  await send(ws, 'Page.navigate', { url: `${liveUrl}?sidebar-meeting=${Date.now()}` }).catch(() => {});

  const result = await evalJson(ws, `new Promise(async (resolve) => {
    const wait = (ms) => new Promise(r => setTimeout(r, ms));
    const meetingId = ${JSON.stringify(meeting.id)};
    const out = { meetingId };
    try {
      for (let i = 0; i < 120; i++) {
        if (document.querySelector('.sidebar-mtg-item') && typeof window.openMeetingReference === 'function') break;
        await wait(250);
      }
      const cards = Array.from(document.querySelectorAll('.sidebar-mtg-item'));
      out.cardCount = cards.length;
      const card = cards.find(el => (el.textContent || '').includes(${JSON.stringify(meeting.topic || '')})) || cards[0];
      out.cardText = card ? card.textContent : '';
      if (card) card.click();
      for (let i = 0; i < 120; i++) {
        const detail = document.getElementById('meetingDetailModal');
        if (detail && !detail.classList.contains('hidden') && (detail.innerText || '').includes(${JSON.stringify(meeting.topic || '')})) break;
        await wait(250);
      }
      const detail = document.getElementById('meetingDetailModal');
      const dashboard = document.getElementById('meetingsModal');
      out.detailVisible = Boolean(detail && !detail.classList.contains('hidden'));
      out.detailText = detail ? (detail.innerText || '').slice(0, 1200) : '';
      out.dashboardVisible = Boolean(dashboard && !dashboard.classList.contains('hidden'));
    } catch (e) {
      out.error = String(e && e.stack || e);
    }
    resolve(out);
  })`);

  console.log(JSON.stringify(result, null, 2));
  if (!result.cardCount || !result.detailVisible || !result.detailText.includes(meeting.topic || '')) {
    throw new Error('Sidebar meeting direct detail check failed');
  }
} finally {
  if (createdMeetingId) {
    await fetch(`${apiUrl}/api/meetings/executable/${encodeURIComponent(createdMeetingId)}/transition`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ action: 'cancel', reason: 'sidebar direct detail check complete', idempotencyKey: 'sidebar-direct-detail-cleanup-' + Date.now() })
    }).catch(() => {});
  }
  fetch(`http://127.0.0.1:9224/json/close/${encodeURIComponent(pageInfo.id)}`).catch(() => {});
  ws.close();
}
