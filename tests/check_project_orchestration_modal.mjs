import assert from 'node:assert/strict';
import { createRequire } from 'node:module';

const require = createRequire(import.meta.url);
const ProjectOrchestration = require('../app/project-orchestration.js');

class FakeElement {
  constructor(tag, document) {
    this.tagName = String(tag).toUpperCase();
    this.ownerDocument = document;
    this.children = [];
    this.attributes = {};
    this.listeners = {};
    this.parentNode = null;
    this.className = '';
    this.textContent = '';
    this.type = '';
    this.disabled = false;
    this.style = {};
    this._rectWidth = 1220;
    this._rectLeft = 0;
  }

  get firstChild() {
    return this.children[0] || null;
  }

  setAttribute(name, value) {
    this.attributes[name] = String(value);
  }

  getAttribute(name) {
    return this.attributes[name] ?? null;
  }

  appendChild(child) {
    child.parentNode = this;
    this.children.push(child);
    return child;
  }

  removeChild(child) {
    this.children = this.children.filter((candidate) => candidate !== child);
    child.parentNode = null;
    return child;
  }

  replaceChildren(...children) {
    for (const child of this.children.slice()) child.remove();
    for (const child of children) this.appendChild(child);
  }

  addEventListener(type, listener) {
    this.listeners[type] = listener;
  }

  remove() {
    if (this.parentNode) {
      this.parentNode.children = this.parentNode.children.filter((child) => child !== this);
      this.parentNode = null;
    }
    for (const child of this.children) child.remove();
  }

  focus() {
    this.ownerDocument.activeElement = this;
  }

  getBoundingClientRect() {
    return { left: this._rectLeft, width: this._rectWidth };
  }
}

function createDocument() {
  const document = {
    activeElement: null,
    listeners: {},
    body: null,
    createElement(tag) {
      return new FakeElement(tag, document);
    },
    addEventListener(type, listener) {
      document.listeners[type] = listener;
    },
    removeEventListener(type, listener) {
      if (document.listeners[type] === listener) delete document.listeners[type];
    },
  };
  document.body = new FakeElement('body', document);
  document.activeElement = new FakeElement('button', document);
  return document;
}

function walk(node, visitor) {
  visitor(node);
  for (const child of node.children || []) walk(child, visitor);
}

function findByClass(node, className) {
  let found = null;
  walk(node, (candidate) => {
    if (found) return;
    const classes = String(candidate.className || '').split(/\s+/);
    if (classes.includes(className)) found = candidate;
  });
  return found;
}

function findAllByClass(node, className) {
  const found = [];
  walk(node, (candidate) => {
    const classes = String(candidate.className || '').split(/\s+/);
    if (classes.includes(className)) found.push(candidate);
  });
  return found;
}

function findByTaskId(node, taskId) {
  let found = null;
  walk(node, (candidate) => {
    if (!found && candidate.getAttribute && candidate.getAttribute('data-task-id') === taskId) found = candidate;
  });
  return found;
}

function sampleProject(overrides = {}) {
  return {
    id: 'p1',
    title: 'Project',
    orchestration: { revision: 3, state: 'running', currentStage: 2 },
    tasks: [
      { id: 'b', title: 'B', executionStage: 2, order: 2, executionState: 'reviewing', priority: 'critical', assignee: 'Flo' },
      { id: 'a', title: 'A', executionStage: 1, executionState: 'executing', priority: 'high', assignee: 'Ana' },
      { id: 'c', title: 'C', executionStage: 2, order: 1 },
    ],
    ...overrides,
  };
}

{
  const vm = ProjectOrchestration.buildViewModel(sampleProject());
  assert.equal(vm.projectId, 'p1');
  assert.equal(vm.revision, 3);
  assert.equal(vm.currentStage, 2);
  assert.equal(vm.taskCount, 3);
  assert.equal(vm.stageCount, 2);
  assert.deepEqual(vm.stages.map((stage) => stage.stage), [1, 2]);
  assert.deepEqual(vm.stages[1].tasks.map((task) => task.id), ['c', 'b']);
  assert.equal(vm.stages[0].tasks[0].stateLabel, 'IN PROGRESS');
  assert.equal(vm.stages[1].tasks[1].stateLabel, 'REVIEW');
}

{
  const document = createDocument();
  let closed = 0;
  const session = ProjectOrchestration.open(sampleProject(), { document, onClose: () => { closed += 1; } });
  assert.equal(document.body.children.length, 1);
  assert.equal(session.overlay.getAttribute('role'), 'dialog');
  assert.equal(session.overlay.getAttribute('aria-modal'), 'true');
  assert.equal(session.overlay.getAttribute('data-project-id'), 'p1');
  assert.ok(session.modal.className.includes('is-running'));
  assert.equal(findByClass(session.overlay, 'project-orchestration-title').textContent, '任务流水线编排');
  assert.equal(findByClass(session.overlay, 'project-orchestration-count').textContent, '3 TASKS · 2 STEPS');
  assert.equal(findAllByClass(session.overlay, 'project-orchestration-stage').length, 2);
  assert.equal(findAllByClass(session.overlay, 'project-orchestration-canvas-surface').length, 1);
  assert.equal(findAllByClass(session.overlay, 'project-orchestration-new-stage').length, 0);
  assert.equal(findAllByClass(session.overlay, 'project-orchestration-task').length, 3);
  assert.equal(findByClass(session.overlay, 'project-orchestration-save'), null, 'auto-save modal must not render a manual save action');
  ProjectOrchestration.close();
  assert.equal(closed, 1);
}

{
  const document = createDocument();
  const session = ProjectOrchestration.open(sampleProject({
    orchestration: { revision: 3, state: 'draft', currentStage: null },
    tasks: [
      { id: 'a', title: 'A', executionStage: 1 },
      { id: 'b', title: 'B', executionStage: 1 },
      { id: 'c', title: 'C', executionStage: 1 },
      { id: 'd', title: 'D', executionStage: 1 },
      { id: 'e', title: 'E', executionStage: 2 },
      { id: 'f', title: 'F', executionStage: 6 },
    ],
  }), { document });
  const surface = findByClass(session.overlay, 'project-orchestration-canvas-surface');
  assert.ok(Number.parseInt(surface.style.width, 10) > 1184, 'wide stage plans should create a horizontal scroll surface');
  assert.ok(Number.parseInt(surface.style.height, 10) > 350, 'tall parallel stages should create a vertical scroll surface');
  ProjectOrchestration.close();
}

{
  const document = createDocument();
  const session = ProjectOrchestration.open(sampleProject({
    orchestration: { revision: 3, state: 'draft', currentStage: null },
  }), { document });
  assert.equal(findAllByClass(session.overlay, 'project-orchestration-new-stage').length, 1);
  assert.equal(findAllByClass(session.overlay, 'project-orchestration-insert-stage').length, 1);
  assert.equal(findByClass(session.overlay, 'project-orchestration-insert-stage').getAttribute('data-insert-after-stage'), '1');
  assert.equal(findByClass(session.overlay, 'project-orchestration-new-stage').getAttribute('data-stage'), '3');
  ProjectOrchestration.close();
}

{
  const document = createDocument();
  const previousFocus = document.activeElement;
  let closed = 0;
  ProjectOrchestration.open(sampleProject(), { document, onClose: () => { closed += 1; } });
  assert.equal(typeof document.listeners.keydown, 'function');
  document.listeners.keydown({ key: 'Escape' });
  assert.equal(document.body.children.length, 0);
  assert.equal(document.listeners.keydown, undefined);
  assert.equal(document.activeElement, previousFocus);
  assert.equal(closed, 1);
}

{
  const document = createDocument();
  const oldSession = ProjectOrchestration.open(sampleProject(), { document });
  const newSession = ProjectOrchestration.reopen(sampleProject({ id: 'p2' }), { document });
  assert.equal(document.body.children.length, 1);
  assert.equal(ProjectOrchestration.current().viewModel.projectId, 'p2');
  assert.notEqual(oldSession.overlay, newSession.overlay);
  assert.equal(oldSession.overlay.parentNode, null);
  ProjectOrchestration.close();
}

await (async () => {
  const document = createDocument();
  const session = ProjectOrchestration.open(sampleProject(), { document });
  session.modal._rectWidth = 628;
  const scale = ProjectOrchestration.fitCanvas();
  assert.equal(scale, 0.5);
  assert.equal(session.canvas.style.transformOrigin, 'top left');
  assert.equal(session.canvas.style.transform, 'scale(0.500)');
  assert.equal(session.canvas.getAttribute('data-fit-scale'), '0.500');
  ProjectOrchestration.close();
})();

await (async () => {
  const document = createDocument();
  const saves = [];
  const project = sampleProject({
    orchestration: { revision: 3, state: 'draft', currentStage: null },
    tasks: [
      { id: 'a', title: 'A', executionStage: 1, order: 1 },
      { id: 'b', title: 'B', executionStage: 2, order: 1 },
      { id: 'c', title: 'C', executionStage: 3, order: 1 },
    ],
  });
  const api = {
    async saveCompletedDrag(payload) {
      saves.push(payload);
      return {
        ok: true,
        saved: true,
        orchestration: { revision: payload.revision + 1, state: 'draft' },
        assignments: payload.assignments,
      };
    },
  };
  const session = ProjectOrchestration.open(project, { document, api });
  const result = await ProjectOrchestration.moveTaskToStage('c', 2);

  assert.equal(result.saved, true);
  assert.equal(saves.length, 1, 'one completed drag must autosave exactly once');
  assert.deepEqual(saves[0].assignments, [
    { taskId: 'a', executionStage: 1 },
    { taskId: 'b', executionStage: 2 },
    { taskId: 'c', executionStage: 2 },
  ]);
  assert.equal(findByClass(ProjectOrchestration.current().overlay, 'project-orchestration-status').getAttribute('data-status'), 'saved');
  assert.equal(ProjectOrchestration.current().viewModel.revision, 4);
  assert.deepEqual(ProjectOrchestration.current().viewModel.stages.map((stage) => stage.stage), [1, 2]);
  ProjectOrchestration.close();
})();

await (async () => {
  const document = createDocument();
  const saves = [];
  const project = sampleProject({
    orchestration: { revision: 3, state: 'draft', currentStage: null },
    tasks: [
      { id: 'a', title: 'Stage three target', executionStage: 3, order: 1 },
      { id: 'b', title: 'Stage four first card', executionStage: 4, order: 1 },
    ],
  });
  const api = {
    async saveCompletedDrag(payload) {
      saves.push(payload);
      return {
        ok: true,
        saved: true,
        assignments: payload.assignments,
        orchestration: { revision: 4, state: 'draft' },
      };
    },
  };
  ProjectOrchestration.open(project, { document, api });
  const canvas = findByClass(ProjectOrchestration.current().overlay, 'project-orchestration-canvas');
  canvas._rectLeft = 0;
  canvas._rectWidth = 1184;
  const stageFourCard = findByTaskId(ProjectOrchestration.current().overlay, 'b');

  stageFourCard.listeners.dragstart({
    clientX: 760,
    clientY: 160,
    dataTransfer: { setData() {}, effectAllowed: '' },
  });
  document.listeners.dragover({ clientX: 530, clientY: 160 });
  stageFourCard.listeners.dragend({});
  await Promise.resolve();
  await Promise.resolve();

  assert.equal(saves.length, 1, 'dragend fallback should merge a stage when native drop is not delivered');
  assert.deepEqual(saves[0].assignments, [
    { taskId: 'a', executionStage: 1 },
    { taskId: 'b', executionStage: 1 },
  ]);
  ProjectOrchestration.close();
})();

await (async () => {
  const document = createDocument();
  const saves = [];
  const project = sampleProject({
    orchestration: { revision: 3, state: 'draft', currentStage: null },
    tasks: [
      { id: 'a', title: 'First stage first card', executionStage: 1, order: 1 },
      { id: 'c', title: 'First stage second card', executionStage: 1, order: 2 },
      { id: 'b', title: 'Second stage first card', executionStage: 2, order: 1 },
    ],
  });
  const api = {
    async saveCompletedDrag(payload) {
      saves.push(payload);
      return {
        ok: true,
        saved: true,
        assignments: payload.assignments,
        orchestration: { revision: 4, state: 'draft' },
      };
    },
  };
  ProjectOrchestration.open(project, { document, api });
  const firstCard = findByTaskId(ProjectOrchestration.current().overlay, 'a');
  firstCard.listeners.pointerdown({
    button: 0,
    clientX: 40,
    clientY: 160,
    target: firstCard,
  });
  document.listeners.pointermove({
    clientX: 300,
    clientY: 160,
    preventDefault() {},
  });
  document.listeners.pointerup({
    clientX: 300,
    clientY: 160,
    preventDefault() {},
  });
  await Promise.resolve();
  await Promise.resolve();

  assert.equal(saves.length, 1, 'pointer fallback should move a first card without native dragstart');
  assert.deepEqual(saves[0].assignments, [
    { taskId: 'a', executionStage: 2 },
    { taskId: 'c', executionStage: 1 },
    { taskId: 'b', executionStage: 2 },
  ]);
  assert.equal(ProjectOrchestration.current().viewModel.stages[1].tasks.some((task) => task.id === 'a'), true);
  ProjectOrchestration.close();
})();

await (async () => {
  const document = createDocument();
  const saves = [];
  const project = sampleProject({
    orchestration: { revision: 25, state: 'draft', currentStage: null },
    tasks: [
      { id: 'a', title: 'A', executionStage: 1 },
      { id: 'b', title: 'B', executionStage: 2 },
      { id: 'c', title: 'C', executionStage: 3 },
    ],
  });
  ProjectOrchestration.open(project, {
    document,
    api: {
      async saveCompletedDrag(payload) {
        saves.push(payload);
        return { ok: true, saved: true, orchestration: { revision: 26, state: 'draft' }, assignments: payload.assignments };
      },
    },
  });
  const targetTask = findByTaskId(ProjectOrchestration.current().overlay, 'b');
  let prevented = false;
  let stopped = false;
  await targetTask.listeners.drop({
    preventDefault() { prevented = true; },
    stopPropagation() { stopped = true; },
    dataTransfer: { getData: () => 'c' },
  });
  await Promise.resolve();
  await Promise.resolve();

  assert.equal(prevented, true);
  assert.equal(stopped, true);
  assert.equal(saves.length, 1, 'dropping onto a task card should make the dragged task parallel with that card');
  assert.deepEqual(saves[0].assignments, [
    { taskId: 'a', executionStage: 1 },
    { taskId: 'b', executionStage: 2 },
    { taskId: 'c', executionStage: 2 },
  ]);
  assert.deepEqual(ProjectOrchestration.current().viewModel.stages.map((stage) => stage.stage), [1, 2]);
  ProjectOrchestration.close();
})();

await (async () => {
  const document = createDocument();
  const saves = [];
  const project = sampleProject({
    orchestration: { revision: 11, state: 'draft', currentStage: null },
    tasks: [
      { id: 'a', title: 'A', executionStage: 1 },
      { id: 'b', title: 'B', executionStage: 2 },
    ],
  });
  ProjectOrchestration.open(project, {
    document,
    api: {
      async saveCompletedDrag(payload) {
        saves.push(payload);
        return { ok: true, saved: true, orchestration: { revision: 12, state: 'draft' }, assignments: payload.assignments };
      },
    },
  });
  const stages = findAllByClass(ProjectOrchestration.current().overlay, 'project-orchestration-stage');
  const targetStage = stages.find((node) => node.getAttribute('data-stage') === '1');
  let prevented = false;
  await targetStage.listeners.drop({
    preventDefault() { prevented = true; },
    dataTransfer: { getData: () => 'b' },
  });
  await Promise.resolve();
  await Promise.resolve();

  assert.equal(prevented, true);
  assert.equal(saves.length, 1, 'drop event should produce one completed-drag auto-save');
  assert.deepEqual(saves[0].assignments, [
    { taskId: 'a', executionStage: 1 },
    { taskId: 'b', executionStage: 1 },
  ]);
  assert.equal(ProjectOrchestration.current().viewModel.stageCount, 1);
  ProjectOrchestration.close();
})();

await (async () => {
  const document = createDocument();
  const saves = [];
  const project = sampleProject({
    orchestration: { revision: 21, state: 'draft', currentStage: null },
    tasks: [
      { id: 'a', title: 'A', executionStage: 1 },
      { id: 'b', title: 'B', executionStage: 2 },
      { id: 'c', title: 'C', executionStage: 2 },
    ],
  });
  ProjectOrchestration.open(project, {
    document,
    api: {
      async saveCompletedDrag(payload) {
        saves.push(payload);
        return { ok: true, saved: true, orchestration: { revision: 22, state: 'draft' }, assignments: payload.assignments };
      },
    },
  });
  const canvas = findByClass(ProjectOrchestration.current().overlay, 'project-orchestration-canvas');
  canvas._rectLeft = 0;
  canvas._rectWidth = 1184;
  let prevented = false;
  await canvas.listeners.drop({
    clientX: 610,
    preventDefault() { prevented = true; },
    dataTransfer: { getData: () => 'c' },
  });
  await Promise.resolve();
  await Promise.resolve();

  assert.equal(prevented, true);
  assert.equal(saves.length, 0, 'dropping near the last stage should keep the task parallel in that stage');
  assert.deepEqual(ProjectOrchestration.current().viewModel.stages.map((stage) => stage.stage), [1, 2]);
  ProjectOrchestration.close();
})();

await (async () => {
  const document = createDocument();
  const saves = [];
  const project = sampleProject({
    orchestration: { revision: 21, state: 'draft', currentStage: null },
    tasks: [
      { id: 'a', title: 'A', executionStage: 1 },
      { id: 'b', title: 'B', executionStage: 2 },
      { id: 'c', title: 'C', executionStage: 2 },
    ],
  });
  ProjectOrchestration.open(project, {
    document,
    api: {
      async saveCompletedDrag(payload) {
        saves.push(payload);
        return { ok: true, saved: true, orchestration: { revision: 22, state: 'draft' }, assignments: payload.assignments };
      },
    },
  });
  const canvas = findByClass(ProjectOrchestration.current().overlay, 'project-orchestration-canvas');
  canvas._rectLeft = 0;
  canvas._rectWidth = 1184;
  let prevented = false;
  await canvas.listeners.drop({
    clientX: 760,
    preventDefault() { prevented = true; },
    dataTransfer: { getData: () => 'c' },
  });
  await Promise.resolve();
  await Promise.resolve();

  assert.equal(prevented, true);
  assert.equal(saves.length, 0, 'dropping in the broad area after the last card should still keep the task parallel');
  assert.deepEqual(ProjectOrchestration.current().viewModel.stages.map((stage) => stage.stage), [1, 2]);
  ProjectOrchestration.close();
})();

await (async () => {
  const document = createDocument();
  const saves = [];
  const project = sampleProject({
    orchestration: { revision: 21, state: 'draft', currentStage: null },
    tasks: [
      { id: 'a', title: 'A', executionStage: 1 },
      { id: 'b', title: 'B', executionStage: 2 },
      { id: 'c', title: 'C', executionStage: 2 },
    ],
  });
  ProjectOrchestration.open(project, {
    document,
    api: {
      async saveCompletedDrag(payload) {
        saves.push(payload);
        return { ok: true, saved: true, orchestration: { revision: 22, state: 'draft' }, assignments: payload.assignments };
      },
    },
  });
  const canvas = findByClass(ProjectOrchestration.current().overlay, 'project-orchestration-canvas');
  canvas._rectLeft = 0;
  canvas._rectWidth = 1184;
  let prevented = false;
  await canvas.listeners.drop({
    clientX: 920,
    preventDefault() { prevented = true; },
    dataTransfer: { getData: () => 'c' },
  });
  await Promise.resolve();
  await Promise.resolve();

  assert.equal(prevented, true);
  assert.equal(saves.length, 0, 'dropping on ordinary canvas must not create a new stage');
  assert.deepEqual(ProjectOrchestration.current().viewModel.stages.map((stage) => stage.stage), [1, 2]);
  ProjectOrchestration.close();
})();

await (async () => {
  const document = createDocument();
  const saves = [];
  const project = sampleProject({
    orchestration: { revision: 21, state: 'draft', currentStage: null },
    tasks: [
      { id: 'a', title: 'A', executionStage: 1 },
      { id: 'b', title: 'B', executionStage: 2 },
      { id: 'c', title: 'C', executionStage: 2 },
    ],
  });
  ProjectOrchestration.open(project, {
    document,
    api: {
      async saveCompletedDrag(payload) {
        saves.push(payload);
        return { ok: true, saved: true, orchestration: { revision: 22, state: 'draft' }, assignments: payload.assignments };
      },
    },
  });
  const newStage = findByClass(ProjectOrchestration.current().overlay, 'project-orchestration-new-stage');
  assert.equal(newStage.getAttribute('data-stage'), '3');
  assert.equal(newStage.style.left, '490px');
  let prevented = false;
  let stopped = false;
  await newStage.listeners.drop({
    preventDefault() { prevented = true; },
    stopPropagation() { stopped = true; },
    dataTransfer: { getData: () => 'c' },
  });
  await Promise.resolve();
  await Promise.resolve();

  assert.equal(prevented, true);
  assert.equal(stopped, true);
  assert.equal(saves.length, 1, 'dropping on the dashed new-stage target should auto-save exactly once');
  assert.deepEqual(saves[0].assignments, [
    { taskId: 'a', executionStage: 1 },
    { taskId: 'b', executionStage: 2 },
    { taskId: 'c', executionStage: 3 },
  ]);
  assert.deepEqual(ProjectOrchestration.current().viewModel.stages.map((stage) => stage.stage), [1, 2, 3]);
  ProjectOrchestration.close();
})();

await (async () => {
  const document = createDocument();
  const saves = [];
  const project = sampleProject({
    orchestration: { revision: 23, state: 'draft', currentStage: null },
    tasks: [
      { id: 'a', title: 'A', executionStage: 1 },
      { id: 'b', title: 'B', executionStage: 2 },
      { id: 'c', title: 'C', executionStage: 3 },
    ],
  });
  ProjectOrchestration.open(project, {
    document,
    api: {
      async saveCompletedDrag(payload) {
        saves.push(payload);
        return { ok: true, saved: true, orchestration: { revision: 24, state: 'draft' }, assignments: payload.assignments };
      },
    },
  });
  const canvas = findByClass(ProjectOrchestration.current().overlay, 'project-orchestration-canvas');
  canvas._rectLeft = 0;
  canvas._rectWidth = 1184;
  let prevented = false;
  await canvas.listeners.drop({
    clientX: 480,
    preventDefault() { prevented = true; },
    dataTransfer: { getData: () => 'c' },
  });
  await Promise.resolve();
  await Promise.resolve();

  assert.equal(prevented, true);
  assert.equal(saves.length, 1, 'dragging the last-stage task into the right side of the previous lane should still save as parallel');
  assert.deepEqual(saves[0].assignments, [
    { taskId: 'a', executionStage: 1 },
    { taskId: 'b', executionStage: 2 },
    { taskId: 'c', executionStage: 2 },
  ]);
  assert.deepEqual(ProjectOrchestration.current().viewModel.stages.map((stage) => stage.stage), [1, 2]);
  ProjectOrchestration.close();
})();

await (async () => {
  const document = createDocument();
  const project = sampleProject({
    orchestration: { revision: 13, state: 'draft', currentStage: null },
    tasks: [
      { id: 'a', title: 'A', executionStage: 1 },
      { id: 'b', title: 'B', executionStage: 2 },
    ],
  });
  ProjectOrchestration.open(project, {
    document,
    api: {
      async saveCompletedDrag() {
        return { ok: false, saved: false, code: 'incomplete_orchestration_assignment', error: 'full assignment required' };
      },
    },
  });
  const result = await ProjectOrchestration.moveTaskToStage('b', 1);

  assert.equal(result.saved, false);
  assert.equal(findByClass(ProjectOrchestration.current().overlay, 'project-orchestration-status').getAttribute('data-status'), 'error');
  assert.ok(ProjectOrchestration.current().modal.className.includes('has-error'));
  assert.ok(!ProjectOrchestration.current().modal.className.includes('is-saved'));
  ProjectOrchestration.close();
})();

await (async () => {
  const document = createDocument();
  const project = sampleProject({
    orchestration: { revision: 2, state: 'draft', currentStage: null },
    tasks: [
      { id: 'a', title: 'A', executionStage: 1 },
      { id: 'b', title: 'B', executionStage: 2 },
    ],
  });
  const api = {
    async saveCompletedDrag() {
      return {
        ok: false,
        saved: false,
        conflict: true,
        currentRevision: 9,
        orchestration: { revision: 9, state: 'draft' },
        assignments: [
          { taskId: 'a', executionStage: 1 },
          { taskId: 'b', executionStage: 2 },
        ],
      };
    },
  };
  ProjectOrchestration.open(project, { document, api });
  const result = await ProjectOrchestration.moveTaskToStage('b', 1);

  assert.equal(result.conflict, true);
  assert.equal(ProjectOrchestration.current().viewModel.revision, 9);
  assert.deepEqual(ProjectOrchestration.current().viewModel.stages.map((stage) => stage.stage), [1, 2]);
  assert.equal(ProjectOrchestration.current().viewModel.stages[1].tasks[0].id, 'b');
  assert.equal(findByClass(ProjectOrchestration.current().overlay, 'project-orchestration-status').getAttribute('data-status'), 'conflict');
  assert.ok(ProjectOrchestration.current().modal.className.includes('has-conflict'));
  ProjectOrchestration.close();
})();

await (async () => {
  const document = createDocument();
  const added = [];
  const project = sampleProject({
    orchestration: { revision: 6, state: 'draft' },
    tasks: [
      { id: 'a', title: 'A', executionStage: 1 },
      { id: 'b', title: 'B', executionStage: 2 },
    ],
  });
  ProjectOrchestration.open(project, {
    document,
    onAddTask: async (payload) => {
      added.push(payload);
      return {
        ok: true,
        task: { id: 'c', title: 'C', executionStage: payload.executionStage },
        orchestration: { revision: payload.revision + 1, state: 'draft' },
      };
    },
  });
  const result = await ProjectOrchestration.addTask();

  assert.equal(result.ok, true);
  assert.deepEqual(added, [{ projectId: 'p1', revision: 6, executionStage: 3 }]);
  assert.equal(ProjectOrchestration.current().viewModel.taskCount, 3);
  assert.deepEqual(ProjectOrchestration.current().viewModel.stages.map((stage) => stage.stage), [1, 2, 3]);
  assert.equal(findByClass(ProjectOrchestration.current().overlay, 'project-orchestration-status').textContent, '已添加');
  ProjectOrchestration.close();
})();

await (async () => {
  const document = createDocument();
  const added = [];
  const project = sampleProject({
    status: 'completed',
    orchestration: { revision: 10, state: 'completed', currentStage: 2 },
    tasks: [
      { id: 'a', title: 'A', executionStage: 1, executionState: 'done', completedAt: 'done-a' },
      { id: 'b', title: 'B', executionStage: 2, executionState: 'done', completedAt: 'done-b' },
    ],
  });
  ProjectOrchestration.open(project, {
    document,
    onAddTask: async (payload) => {
      added.push(payload);
      return {
        ok: true,
        project: {
          ...project,
          status: 'active',
          orchestration: { revision: 11, state: 'paused', currentStage: 3, pauseReason: 'new_task_added_after_completion' },
          tasks: [
            ...project.tasks,
            { id: 'c', title: 'C', executionStage: payload.executionStage },
          ],
        },
      };
    },
  });

  assert.equal(ProjectOrchestration.current().viewModel.canEdit, false);
  assert.equal(ProjectOrchestration.current().viewModel.canAddTask, true);
  const addButton = findByClass(ProjectOrchestration.current().overlay, 'is-add');
  assert.equal(addButton.disabled, false);
  assert.equal(findAllByClass(ProjectOrchestration.current().overlay, 'project-orchestration-task')[0].getAttribute('draggable'), null);

  const result = await ProjectOrchestration.addTask();

  assert.equal(result.ok, true);
  assert.deepEqual(added, [{ projectId: 'p1', revision: 10, executionStage: 3 }]);
  assert.equal(ProjectOrchestration.current().viewModel.state, 'paused');
  assert.equal(ProjectOrchestration.current().viewModel.canEdit, true);
  assert.deepEqual(ProjectOrchestration.current().viewModel.stages.map((stage) => stage.stage), [1, 2, 3]);
  ProjectOrchestration.close();
})();

await (async () => {
  const document = createDocument();
  const saves = [];
  const project = sampleProject({
    orchestration: { revision: 31, state: 'draft', currentStage: null },
    tasks: [
      { id: 'a', title: 'A', executionStage: 1 },
      { id: 'b', title: 'B', executionStage: 2 },
      { id: 'c', title: 'C', executionStage: 2 },
      { id: 'd', title: 'D', executionStage: 3 },
    ],
  });
  ProjectOrchestration.open(project, {
    document,
    api: {
      async saveCompletedDrag(payload) {
        saves.push(payload);
        return { ok: true, saved: true, orchestration: { revision: 32, state: 'draft' }, assignments: payload.assignments };
      },
    },
  });
  const insertTargets = findAllByClass(ProjectOrchestration.current().overlay, 'project-orchestration-insert-stage');
  const afterStageTwo = insertTargets.find((node) => node.getAttribute('data-insert-after-stage') === '2');
  assert.ok(afterStageTwo, 'editable plans should render a drop target between stage 2 and stage 3');
  let prevented = false;
  let stopped = false;
  await afterStageTwo.listeners.drop({
    preventDefault() { prevented = true; },
    stopPropagation() { stopped = true; },
    dataTransfer: { getData: () => 'b' },
  });
  await Promise.resolve();
  await Promise.resolve();

  assert.equal(prevented, true);
  assert.equal(stopped, true);
  assert.equal(saves.length, 1, 'dropping between two stages should auto-save exactly once');
  assert.deepEqual(saves[0].assignments, [
    { taskId: 'a', executionStage: 1 },
    { taskId: 'b', executionStage: 3 },
    { taskId: 'c', executionStage: 2 },
    { taskId: 'd', executionStage: 4 },
  ]);
  assert.deepEqual(ProjectOrchestration.current().viewModel.stages.map((stage) => stage.stage), [1, 2, 3, 4]);
  ProjectOrchestration.close();
})();

await (async () => {
  const document = createDocument();
  const project = sampleProject({
    orchestration: { revision: 4, state: 'running', currentStage: 1 },
    tasks: [
      { id: 'a', title: 'A', executionStage: 1, executionState: 'executing' },
      { id: 'b', title: 'B', executionStage: 2 },
    ],
  });
  const api = {
    async saveCompletedDrag() {
      throw new Error('locked projects must not save drag edits');
    },
    async pauseProject() {
      return {
        ok: true,
        project: {
          ...project,
          orchestration: { revision: 5, state: 'paused', currentStage: 1, pauseReason: 'manual_pause' },
        },
      };
    },
  };
  ProjectOrchestration.open(project, { document, api });
  assert.equal(ProjectOrchestration.current().viewModel.canEdit, false);
  assert.ok(ProjectOrchestration.current().modal.className.includes('is-locked'));
  assert.equal(findByClass(ProjectOrchestration.current().overlay, 'project-orchestration-button').disabled, true);
  assert.equal(findAllByClass(ProjectOrchestration.current().overlay, 'project-orchestration-task')[0].getAttribute('draggable'), null);
  const dragResult = await ProjectOrchestration.moveTaskToStage('b', 1);
  assert.equal(dragResult.code, 'orchestration_locked');
  const pauseResult = await ProjectOrchestration.pauseProject();
  assert.equal(pauseResult.ok, true);
  assert.equal(ProjectOrchestration.current().viewModel.state, 'paused');
  assert.equal(ProjectOrchestration.current().viewModel.canResume, true);
  assert.ok(findByClass(ProjectOrchestration.current().overlay, 'is-resume'), 'paused projects expose resume');
  ProjectOrchestration.close();
})();

await (async () => {
  const document = createDocument();
  const project = sampleProject({
    orchestration: { revision: 8, state: 'blocked', currentStage: 1, pauseReason: 'dispatch_queue_full' },
    tasks: [{ id: 'a', title: 'A', executionStage: 1 }],
  });
  const api = {
    async resumeProject() {
      return {
        ok: true,
        project: {
          ...project,
          orchestration: { revision: 9, state: 'running', currentStage: 1 },
        },
      };
    },
  };
  ProjectOrchestration.open(project, { document, api });
  assert.equal(ProjectOrchestration.current().viewModel.canResume, true);
  assert.ok(findByClass(ProjectOrchestration.current().overlay, 'is-resume'));
  const resumeResult = await ProjectOrchestration.resumeProject();
  assert.equal(resumeResult.ok, true);
  assert.equal(ProjectOrchestration.current().viewModel.state, 'running');
  assert.equal(ProjectOrchestration.current().viewModel.canEdit, false);
  ProjectOrchestration.close();
})();

await (async () => {
  const document = createDocument();
  const project = sampleProject({
    orchestration: { revision: 3, state: 'draft' },
    tasks: [
      { id: 'a', title: 'A', executionStage: 1 },
      { id: 'b', title: 'B', executionStage: 2, orchestrationSkip: { status: 'requested' } },
    ],
  });
  const api = {
    async requestTaskSkip(payload) {
      return {
        ok: true,
        task: { id: payload.taskId, orchestrationSkip: { status: 'requested' } },
        orchestration: { revision: 4, state: 'draft' },
      };
    },
    async decideTaskSkip(payload) {
      return {
        ok: true,
        task: { id: payload.taskId, orchestrationSkip: { status: payload.body.decision === 'approve' ? 'approved' : 'rejected' } },
        orchestration: { revision: 5, state: 'draft' },
      };
    },
  };
  ProjectOrchestration.open(project, { document, api });
  assert.equal(findByClass(ProjectOrchestration.current().overlay, 'project-orchestration-skip-state').textContent, 'SKIP?');
  const requestResult = await ProjectOrchestration.requestSkip('a');
  assert.equal(requestResult.ok, true);
  assert.equal(findAllByClass(ProjectOrchestration.current().overlay, 'project-orchestration-skip-state').length, 2);
  const decisionResult = await ProjectOrchestration.decideSkip('b', 'approve');
  assert.equal(decisionResult.ok, true);
  const skipped = findAllByClass(ProjectOrchestration.current().overlay, 'project-orchestration-task')
    .find((node) => node.getAttribute('data-task-id') === 'b');
  assert.equal(skipped.getAttribute('data-skip-state'), 'skip-approved');
  assert.equal(findByClass(skipped, 'project-orchestration-skip-state').textContent, 'SKIPPED');
  ProjectOrchestration.close();
})();

await (async () => {
  const document = createDocument();
  ProjectOrchestration.open(sampleProject({
    orchestration: { revision: 10, state: 'completed', currentStage: 2 },
  }), { document });
  assert.equal(ProjectOrchestration.current().viewModel.completed, true);
  assert.equal(ProjectOrchestration.current().viewModel.canEdit, false);
  assert.equal(ProjectOrchestration.current().viewModel.canAddTask, true);
  assert.ok(ProjectOrchestration.current().modal.className.includes('is-completed'));
  assert.equal(findByClass(ProjectOrchestration.current().overlay, 'is-skip-request').disabled, true);
  assert.equal(findByClass(ProjectOrchestration.current().overlay, 'is-add').disabled, false);
  assert.equal(await ProjectOrchestration.addTask().then((result) => result.code), 'missing_add_task_handler');
  ProjectOrchestration.close();
})();

console.log('project orchestration modal runtime contract ok');
