#!/usr/bin/env node
import assert from 'node:assert/strict';
import { spawnSync } from 'node:child_process';
import fs from 'node:fs';
import { closeCdpPage, createCdpPage, cdpVersion } from './cdp-test-utils.mjs';


if (typeof WebSocket === 'undefined') {
  const child = spawnSync(process.execPath, ['--experimental-websocket', ...process.argv.slice(1)], {
    env: process.env,
    stdio: 'inherit',
  });
  process.exit(child.status ?? 1);
}

await cdpVersion();
const fixture = JSON.parse(fs.readFileSync('tests/fixtures/hr-browser-acceptance.json', 'utf8'));
const locale = JSON.parse(fs.readFileSync('app/locales/en.json', 'utf8'));
const javascript = fs.readFileSync('app/human-resources.js', 'utf8');
const css = fs.readFileSync('app/human-resources.css', 'utf8');
const page = await createCdpPage('about:blank');
const ws = new WebSocket(page.webSocketDebuggerUrl);
await new Promise((resolve, reject) => {
  ws.addEventListener('open', resolve, { once: true });
  ws.addEventListener('error', reject, { once: true });
});

let sequence = 0;
const pending = new Map();
ws.addEventListener('message', (event) => {
  const message = JSON.parse(event.data.toString());
  if (!message.id || !pending.has(message.id)) return;
  const waiter = pending.get(message.id);
  pending.delete(message.id);
  clearTimeout(waiter.timer);
  if (message.error) waiter.reject(new Error(JSON.stringify(message.error)));
  else waiter.resolve(message.result || {});
});

function send(method, params = {}) {
  const id = ++sequence;
  ws.send(JSON.stringify({ id, method, params }));
  return new Promise((resolve, reject) => {
    const timer = setTimeout(() => {
      pending.delete(id);
      reject(new Error(`Timed out waiting for ${method}`));
    }, 20000);
    pending.set(id, { resolve, reject, timer });
  });
}

async function evaluate(expression) {
  const response = await send('Runtime.evaluate', {
    expression,
    awaitPromise: true,
    returnByValue: true,
  });
  if (response.exceptionDetails) {
    throw new Error(response.exceptionDetails.text || JSON.stringify(response.exceptionDetails));
  }
  return response.result?.value;
}

async function waitFor(expression, timeoutMs = 10000) {
  const started = Date.now();
  while (Date.now() - started < timeoutMs) {
    if (await evaluate(expression)) return;
    await new Promise((resolve) => setTimeout(resolve, 80));
  }
  throw new Error(`Timed out waiting for ${expression}`);
}

try {
  await send('Page.enable');
  await send('Runtime.enable');
  await send('Emulation.setDeviceMetricsOverride', {
    width: 1440,
    height: 1000,
    deviceScaleFactor: 1,
    mobile: false,
  });
  await evaluate(`(() => {
    document.documentElement.innerHTML = ${JSON.stringify(`
      <head><meta charset="utf-8"><title>HR Browser Acceptance</title></head>
      <body>
        <div class="toolbar"><button id="btn-human-resources" onclick="openHumanResources()">Human Resources</button></div>
        <div id="humanResourcesModal" class="modal hidden" role="dialog" aria-modal="true" aria-labelledby="human-resources-title">
          <div class="modal-content hr-modal-content">
            <div class="modal-header hr-header">
              <h2 id="human-resources-title">Human Resources</h2>
              <span id="human-resources-status" class="hr-header-status"></span>
              <button id="human-resources-close" class="close-btn hr-close" onclick="closeHumanResources()">×</button>
            </div>
            <div id="human-resources-content" class="hr-content"></div>
          </div>
        </div>
      </body>
    `)};
    const style = document.createElement('style');
    style.textContent = '.hidden{display:none!important}.modal{position:fixed;inset:0;display:grid;place-items:center;background:#080b12}' + ${JSON.stringify(css)};
    document.head.appendChild(style);
    const fixture = ${JSON.stringify(fixture)};
    const locale = ${JSON.stringify(locale)};
    window.__hrFixture = { data: fixture, failExport: false, failDetail: false, requests: [] };
    window.confirm = () => true;
    window.i18n = {
      t(key, params) {
        let value = locale[key] || key;
        for (const [name, replacement] of Object.entries(params || {})) {
          value = String(value).replaceAll('{{' + name + '}}', replacement);
        }
        return value;
      },
      async managementFetch(input, options = {}) {
        const url = String(input || '');
        window.__hrFixture.requests.push({ url, method: options.method || 'GET', body: options.body || '' });
        if (options.method === 'POST') {
          if (url.endsWith('/pause')) fixture.overview.hr.status = 'paused';
          if (url.endsWith('/resume')) fixture.overview.hr.status = 'ready';
          return new Response(JSON.stringify({ ok: true, command: { accepted: true } }), { status: 202 });
        }
        if (url.includes('/overview')) return new Response(JSON.stringify(fixture.overview), { status: 200 });
        if (url.includes('/export?table=agents')) {
          if (window.__hrFixture.failExport) return new Response(JSON.stringify({ ok: false, code: 'hr_repository_unavailable' }), { status: 503 });
          return new Response(JSON.stringify({ ok: true, export: { rows: fixture.agents } }), { status: 200 });
        }
        if (url.includes('/agents/agent-1')) {
          if (window.__hrFixture.failDetail) return new Response(JSON.stringify({ ok: false, code: 'hr_repository_unavailable' }), { status: 503 });
          const parsed = new URL(url, location.href);
          if (parsed.searchParams.has('reportCursor')) {
            return new Response(JSON.stringify({ ok: true, agent: fixture.reportPage }), { status: 200 });
          }
          if (parsed.searchParams.has('accessCursor')) {
            return new Response(JSON.stringify({ ok: true, agent: fixture.accessPage }), { status: 200 });
          }
          return new Response(JSON.stringify({ ok: true, agent: fixture.agent }), { status: 200 });
        }
        return new Response(JSON.stringify({ ok: false, code: 'hr_agent_not_found' }), { status: 404 });
      },
    };
    const script = document.createElement('script');
    script.textContent = ${JSON.stringify(javascript)};
    document.body.appendChild(script);
    return Boolean(window.HumanResources && window.openHumanResources);
  })()`);

  await evaluate("document.getElementById('btn-human-resources').click()");
  await waitFor("document.querySelectorAll('.hr-agent-row').length === 2 && document.querySelector('.hr-overview')");
  const overview = await evaluate(`(() => ({
    modalOpen: !document.getElementById('humanResourcesModal').classList.contains('hidden'),
    roster: document.querySelectorAll('.hr-agent-row').length,
    dailyStatus: document.querySelector('.hr-overview').innerText.includes('Daily reporting status'),
    activity: document.querySelector('.hr-overview').innerText.includes('Daily report'),
  }))()`);
  assert.deepEqual(overview, { modalOpen: true, roster: 2, dailyStatus: true, activity: true });

  await evaluate("document.querySelector('[data-agent-id=\"agent-1\"]').click()");
  await waitFor("document.querySelector('.hr-detail-view')?.innerText.includes('RAW FIXTURE REPORT ONE')");
  const detail = await evaluate(`(() => ({
    reportCards: document.querySelectorAll('.hr-record-card:not(.hr-assessment-card)').length,
    assessmentCards: document.querySelectorAll('.hr-assessment-card').length,
    normalizedVisible: document.body.innerText.includes('Completed fixture research'),
    evidenceVisible: document.body.innerText.includes('Daily report evidence'),
    accessRows: document.querySelectorAll('.hr-detail-section .hr-history-list li').length,
  }))()`);
  assert.equal(detail.reportCards, 1);
  assert.equal(detail.assessmentCards, 1);
  assert.equal(detail.normalizedVisible, true);
  assert.equal(detail.evidenceVisible, true);
  assert.ok(detail.accessRows >= 1);

  await evaluate("HumanResources.loadMore('reports')");
  await waitFor("document.body.innerText.includes('RAW FIXTURE REPORT TWO')");
  await evaluate("HumanResources.loadMore('access')");
  await waitFor("document.body.innerText.includes('Review Agent')");
  assert.equal(await evaluate("document.querySelectorAll('.hr-record-card:not(.hr-assessment-card)').length"), 2);

  await evaluate("HumanResources.selectAgent('')");
  await waitFor("document.querySelector('.hr-command-panel')");
  await evaluate("HumanResources.runCommand('pause')");
  await waitFor("HumanResources.state.overview.hr.status === 'paused'");
  assert.equal(await evaluate("document.getElementById('human-resources-status').textContent"), 'Paused');
  await evaluate("HumanResources.runCommand('resume')");
  await waitFor("HumanResources.state.overview.hr.status === 'ready'");

  await evaluate("window.__hrFixture.failExport = true; HumanResources.reload()");
  await waitFor("document.querySelector('.hr-degraded-banner')");
  const degraded = await evaluate(`(() => ({
    rosterRetained: document.querySelectorAll('.hr-agent-row').length,
    overviewRetained: Boolean(document.querySelector('.hr-overview')),
    errorText: document.querySelector('.hr-degraded-banner').innerText,
  }))()`);
  assert.equal(degraded.rosterRetained, 2);
  assert.equal(degraded.overviewRetained, true);
  assert.match(degraded.errorText, /repository is unavailable/i);

  await evaluate("window.__hrFixture.failExport = false; HumanResources.selectAgent('agent-1')");
  await waitFor("document.body.innerText.includes('RAW FIXTURE REPORT ONE')");
  await evaluate("window.__hrFixture.failDetail = true; HumanResources.state.detail.accessNextCursor = 'retry-access'; HumanResources.loadMore('access')");
  await waitFor("document.querySelector('.hr-degraded-banner')");
  assert.equal(await evaluate("document.body.innerText.includes('Builder Agent')"), true, 'valid detail remains browsable after paging failure');

  const summary = await evaluate(`(() => ({
    requests: window.__hrFixture.requests.length,
    pauseCalls: window.__hrFixture.requests.filter(item => item.url.endsWith('/pause')).length,
    resumeCalls: window.__hrFixture.requests.filter(item => item.url.endsWith('/resume')).length,
    reportPageCalls: window.__hrFixture.requests.filter(item => item.url.includes('reportCursor=')).length,
    accessPageCalls: window.__hrFixture.requests.filter(item => item.url.includes('accessCursor=')).length,
  }))()`);
  assert.deepEqual(summary, { requests: 15, pauseCalls: 1, resumeCalls: 1, reportPageCalls: 1, accessPageCalls: 2 });
  console.log(JSON.stringify({ ok: true, overview, detail, degraded, summary }, null, 2));
} finally {
  closeCdpPage(page);
  ws.close();
}
