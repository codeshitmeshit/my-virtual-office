import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';

const source = fs.readFileSync(new URL('../app/projects.js', import.meta.url), 'utf8');
const publicMarker = '    // ── PUBLIC API ────────────────────────────────────────────────';
const instrumented = source.slice(0, source.indexOf(publicMarker)) + `
    window.__completionReportStatusTest = { renderReportView, resendCompletionReportAction };
})();`;

const main = { innerHTML: '', querySelector() { return null; }, querySelectorAll() { return []; } };
const toast = { id: 'proj-toast', textContent: '', className: '', classList: { add() {}, remove() {} } };
const document = {
  documentElement: { lang: 'zh' },
  activeElement: null,
  body: { appendChild() {} },
  createElement() { return { nodeType: 1, dataset: {}, classList: { add() {}, remove() {} } }; },
  getElementById(id) { return id === 'proj-main-content' ? main : (id === 'proj-toast' ? toast : null); },
};
let resolveMutation;
const requests = [];
const i18n = {
  getLanguage: () => 'zh',
  t: key => key,
  managementFetch(url, init) {
    requests.push({ url, init });
    return new Promise(resolve => { resolveMutation = () => resolve({ ok: true, status: 200, json: async () => ({ ok: true }) }); });
  },
};
const report = {
  projectId: 'p1', title: 'Demo', generatedAt: '2026-08-03T00:00:00Z', finalReport: null,
  stats: { total: 0, done: 0, inProgress: 0, overdue: 0 }, columns: [], agentWorkload: {}, timeline: [],
  completionReports: [],
};
const context = {
  window: { i18n }, document, i18n, console,
  crypto: { randomUUID: () => 'id' },
  setTimeout, clearTimeout, setInterval, clearInterval,
  fetch: async () => ({ ok: true, status: 200, json: async () => ({ ok: true, report }) }),
  URL, EventSource: function EventSource() {},
};
context.window.window = context.window;
context.window.document = document;
vm.runInNewContext(instrumented, context);

const ui = context.window.__completionReportStatusTest;
const html = ui.renderReportView({
  ...report,
  completionReports: [
    { occurrenceId: 'o1', version: 1, status: 'delivered', completedAt: '2026-08-01T00:00:00Z', deliveredAt: '2026-08-01T01:00:00Z', canResend: false },
    { occurrenceId: 'o3', version: 3, status: 'failed', completedAt: '2026-08-03T00:00:00Z', canResend: true, lastError: { code: 'send_failed', message: '<img src=x onerror=alert(1)>' } },
    { occurrenceId: 'o2', version: 2, status: 'pending', completedAt: '2026-08-02T00:00:00Z', canResend: false },
  ],
});
assert.ok(html.indexOf('v3') < html.indexOf('v2') && html.indexOf('v2') < html.indexOf('v1'), 'versions render newest first');
assert.match(html, /处理中/);
assert.match(html, /已送达/);
assert.match(html, /发送失败/);
assert.doesNotMatch(html, /<img src=x/);
assert.match(html, /&lt;img src=x onerror=alert\(1\)&gt;/);
assert.equal((html.match(/重新发送/g) || []).length, 1, 'only the failed occurrence has a resend button');

const first = ui.resendCompletionReportAction('p1', 'o3', { showBusyText: false, silentDuplicate: true });
const duplicate = ui.resendCompletionReportAction('p1', 'o3', { showBusyText: false, silentDuplicate: true });
assert.equal(requests.length, 1, 'duplicate clicks share one in-flight mutation');
assert.equal(requests[0].url, '/api/projects/p1/completion-reports/o3/resend');
assert.deepEqual(JSON.parse(requests[0].init.body), {});
resolveMutation();
await Promise.all([first, duplicate]);
assert.match(main.innerHTML, /proj-report-body/, 'successful resend refreshes the report view');
