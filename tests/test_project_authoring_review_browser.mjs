import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import vm from 'node:vm';

const source = readFileSync('app/project-authoring-review.js', 'utf8');

const decodeHtml = value => String(value || '')
  .replace(/&quot;/g, '"')
  .replace(/&#39;/g, "'")
  .replace(/&lt;/g, '<')
  .replace(/&gt;/g, '>')
  .replace(/&amp;/g, '&');

function draft(title = 'Agent proposal') {
  return {
    title,
    projectType: 'one_time',
    agentMaintenanceMode: 'strict_confirmation',
    columns: [{ id: 'todo', title: 'Todo' }],
    tasks: [{
      title: 'Implement',
      columnId: 'todo',
      responsibleActor: { type: 'agent', id: 'owner' },
      executorActor: { type: 'agent', id: 'builder' },
      reviewerRecommendation: {
        recommended: true,
        triggers: ['critical_delivery'],
        rationale: 'Critical release gate',
        candidate: { type: 'agent', id: 'reviewer' },
      },
    }],
    template: { mode: 'none' },
    recurrence: { enabled: false },
  };
}

function createHarness(overrides = {}) {
  let request = {
    id: 'request-1',
    requestId: 'request-1',
    requestingAgentId: 'author',
    state: 'pending',
    revision: 1,
    originalDraft: draft('Original proposal'),
    workingDraft: draft('Working proposal'),
    ...overrides,
  };
  const textarea = { value: '' };
  const root = {
    _html: '',
    set innerHTML(value) {
      this._html = String(value);
      const match = this._html.match(/id="project-authoring-approved-draft"[^>]*>([\s\S]*?)<\/textarea>/);
      if (match) textarea.value = decodeHtml(match[1]);
    },
    get innerHTML() { return this._html; },
  };
  const calls = [];
  const opened = [];
  const confirmationKeys = [];
  let project = null;
  let confirmGate = null;
  let promptValue = 'Not approved';

  const response = (payload, status = 200) => ({
    ok: status >= 200 && status < 300,
    status,
    async json() { return structuredClone(payload); },
  });

  async function managementFetch(url, init = {}) {
    const method = init.method || 'GET';
    const body = init.body ? JSON.parse(init.body) : null;
    calls.push({ url, method, body });
    if (url.includes('?state=')) {
      const visible = ['pending', 'failed', 'materializing'].includes(request.state);
      return response({
        ok: true,
        requests: visible ? [{
          id: request.id,
          title: request.workingDraft.title,
          requestingAgentId: request.requestingAgentId,
          state: request.state,
          revision: request.revision,
          taskCount: request.workingDraft.tasks.length,
        }] : [],
      });
    }
    if (method === 'GET') return response({ ok: true, request });
    if (method === 'PUT') {
      assert.equal(body.expectedRevision, request.revision);
      request = { ...request, state: 'pending', revision: request.revision + 1, workingDraft: body.draft };
      return response({ ok: true, request });
    }
    if (url.endsWith('/confirm')) {
      confirmationKeys.push(body.confirmationKey);
      if (confirmGate) await confirmGate;
      if (request.state !== 'confirmed') {
        assert.equal(body.expectedRevision, request.revision);
        request = { ...request, state: 'confirmed', revision: request.revision + 1, projectId: 'project-1' };
        project = { id: 'project-1', title: request.workingDraft.title };
        return response({ ok: true, created: true, request, project });
      }
      return response({ ok: true, created: false, request, project });
    }
    if (url.endsWith('/reject')) {
      assert.equal(body.expectedRevision, request.revision);
      request = { ...request, state: 'rejected', revision: request.revision + 1, rejectionReason: body.reason };
      return response({ ok: true, request });
    }
    throw new Error(`Unexpected request: ${method} ${url}`);
  }

  const document = {
    documentElement: { lang: 'en' },
    getElementById(id) {
      if (id === 'proj-main-content') return root;
      if (id === 'project-authoring-approved-draft') return textarea;
      return null;
    },
  };
  const window = {
    i18n: { managementFetch },
    confirm: () => true,
    prompt: () => promptValue,
    ProjMgr: { openProject: id => opened.push(id) },
  };
  const context = {
    window,
    document,
    console,
    crypto: { randomUUID: () => 'stable-confirmation-id' },
    structuredClone,
    setTimeout,
    clearTimeout,
  };
  vm.runInNewContext(source, context, { filename: 'project-authoring-review.js' });
  return {
    review: window.ProjectAuthoringReview,
    root,
    textarea,
    calls,
    opened,
    confirmationKeys,
    request: () => request,
    setPrompt: value => { promptValue = value; },
    setConfirmGate: promise => { confirmGate = promise; },
  };
}

{
  const harness = createHarness();
  await harness.review.show();
  assert.match(harness.root.innerHTML, /Original Agent proposal/);
  assert.match(harness.root.innerHTML, /Critical release gate/);
  assert.match(harness.root.innerHTML, /Template and recurrence/);

  const edited = draft('User-edited proposal');
  harness.textarea.value = JSON.stringify(edited);
  await harness.review.saveEdit();
  assert.equal(harness.request().revision, 2);
  assert.equal(harness.request().workingDraft.title, 'User-edited proposal');

  await harness.review.confirm();
  assert.equal(harness.request().state, 'confirmed');
  assert.match(harness.root.innerHTML, /Project created successfully/);
  assert.match(harness.root.innerHTML, /Open project/);

  await harness.review.confirm();
  assert.deepEqual(harness.confirmationKeys, ['review:stable-confirmation-id', 'review:stable-confirmation-id']);
  harness.review.openCreatedProject();
  assert.deepEqual(harness.opened, ['project-1']);
}

{
  const harness = createHarness();
  await harness.review.show();
  let release;
  const gate = new Promise(resolve => { release = resolve; });
  harness.setConfirmGate(gate);
  const first = harness.review.confirm();
  await Promise.resolve();
  const duplicate = harness.review.confirm();
  await duplicate;
  assert.match(harness.root.innerHTML, /already has an action in progress/);
  assert.equal(harness.calls.filter(call => call.url.endsWith('/confirm')).length, 1);
  release();
  await first;
}

{
  const harness = createHarness();
  await harness.review.show();
  harness.setPrompt('Outside approved scope');
  await harness.review.reject();
  assert.equal(harness.request().state, 'rejected');
  assert.equal(harness.request().rejectionReason, 'Outside approved scope');
  assert.match(harness.root.innerHTML, /Draft rejected/);
}

{
  const harness = createHarness({
    state: 'failed',
    code: 'workspace_preparation_failed',
    error: 'Workspace unavailable',
    issues: [{ path: 'tasks[0].executorActor', message: 'Agent is unavailable' }],
  });
  await harness.review.show();
  assert.match(harness.root.innerHTML, /workspace_preparation_failed/);
  assert.match(harness.root.innerHTML, /Workspace unavailable/);
  assert.match(harness.root.innerHTML, /tasks\[0\]\.executorActor/);
}

console.log('project authoring review browser checks passed');
