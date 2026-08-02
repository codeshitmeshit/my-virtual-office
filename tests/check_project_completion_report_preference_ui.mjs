import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';

const source = fs.readFileSync(new URL('../app/projects.js', import.meta.url), 'utf8');
const publicMarker = '    // ── PUBLIC API ────────────────────────────────────────────────';
const instrumented = source.slice(0, source.indexOf(publicMarker)) + `
    window.__projectPreferenceTest = { showFormModal, submitNewProject, submitEditProject };
})();`;

const elements = new Map();
const overlay = {
  classList: { remove() {}, add() {} },
  innerHTML: '',
};
const document = {
  documentElement: { lang: 'zh' },
  body: { appendChild(element) { elements.set(element.id, element); } },
  createElement() {
    return { classList: { add() {}, remove() {} }, textContent: '', className: '', id: '' };
  },
  getElementById(id) {
    if (id === 'proj-form-overlay') return overlay;
    return elements.get(id) || null;
  },
};
const requests = [];
const i18n = {
  getLanguage: () => 'zh',
  t: key => key,
  async managementFetch(url, init) {
    requests.push({ url, init });
    return { json: async () => ({ ok: true }) };
  },
};
const context = {
  window: { i18n },
  document,
  i18n,
  console,
  crypto: { randomUUID: () => 'id' },
  setTimeout,
  clearTimeout,
  setInterval,
  clearInterval,
  fetch: async () => ({ json: async () => ({}) }),
  URL,
  EventSource: function EventSource() {},
};
context.window.window = context.window;
context.window.document = document;
vm.runInNewContext(instrumented, context);

const ui = context.window.__projectPreferenceTest;
elements.set('pf-title', { focus() {} });
ui.showFormModal('new-project', {});
assert.match(
  overlay.innerHTML,
  /id="pf-feishu-completion-report" checked/,
  'new projects should render the Feishu completion report preference enabled',
);

ui.showFormModal('edit-project', {
  id: 'project-1',
  title: 'Completed project',
  feishuCompletionReportEnabled: false,
  orchestration: { completedAt: '2026-08-03T00:00:00+00:00' },
});
assert.match(
  overlay.innerHTML,
  /id="pf-feishu-completion-report"[^>]*disabled/,
  'completed projects should render a locked preference control',
);
assert.doesNotMatch(
  overlay.innerHTML,
  /id="pf-feishu-completion-report"[^>]*checked/,
  'an explicitly disabled preference should remain disabled in the edit form',
);

const value = (input = '') => ({ value: input, checked: false });
for (const [id, element] of Object.entries({
  'pf-title': value('New project'),
  'pf-desc': value(''),
  'pf-status': value('active'),
  'pf-priority': value('medium'),
  'pf-due': value(''),
  'pf-tags': value(''),
  'pf-long-term-project': value(''),
  'pf-high-priority-ai-meeting-auto-approve': value(''),
  'pf-project-execution': { checked: false },
  'pf-feishu-completion-report': { checked: false },
  'pf-workspace': value(''),
  'pf-executor': value(''),
  'pf-reviewer': value(''),
})) elements.set(id, element);

await ui.submitNewProject();
assert.equal(
  JSON.parse(requests.at(-1).init.body).feishuCompletionReportEnabled,
  false,
  'create payload should preserve the project-scoped reporting choice',
);

elements.set('pf-edit-id', value('project-1'));
elements.set('pf-feishu-completion-report', { checked: true });
await ui.submitEditProject();
assert.equal(
  JSON.parse(requests.at(-1).init.body).feishuCompletionReportEnabled,
  true,
  'edit payload should preserve the project-scoped reporting choice',
);
