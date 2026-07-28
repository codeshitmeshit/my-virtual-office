import assert from 'node:assert/strict';
import { createRequire } from 'node:module';

const require = createRequire(import.meta.url);
const TaskDialog = require('../app/project-orchestration-task-dialog.js');

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
    this.value = '';
    this.placeholder = '';
    this.style = {};
  }

  appendChild(child) {
    child.parentNode = this;
    this.children.push(child);
    return child;
  }

  setAttribute(name, value) {
    this.attributes[name] = String(value);
  }

  getAttribute(name) {
    return this.attributes[name] ?? null;
  }

  addEventListener(type, listener) {
    this.listeners[type] = listener;
  }

  remove() {
    if (!this.parentNode) return;
    this.parentNode.children = this.parentNode.children.filter((child) => child !== this);
    this.parentNode = null;
  }

  focus() {
    this.ownerDocument.activeElement = this;
  }
}

function createDocument() {
  const document = {
    activeElement: null,
    body: null,
    createElement(tag) {
      return new FakeElement(tag, document);
    },
  };
  document.body = new FakeElement('body', document);
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
    if (String(candidate.className || '').split(/\s+/).includes(className)) found = candidate;
  });
  return found;
}

const document = createDocument();
const promise = TaskDialog.open({
  document,
  executionStage: 4,
  agents: [{ id: 'codex-local', name: 'Codex' }],
});

assert.equal(document.body.children.length, 1);
assert.equal(document.body.children[0].getAttribute('role'), 'dialog');
assert.equal(findByClass(document.body, 'project-orchestration-task-dialog-subtitle').textContent, '阶段 4 · 新任务');

const submitButton = findByClass(document.body, 'is-submit');
submitButton.listeners.click();
assert.equal(findByClass(document.body, 'project-orchestration-task-dialog-error').textContent, '请输入任务标题');

const titleInput = findByClass(document.body, 'project-orchestration-task-dialog-input');
titleInput.value = '验证并行阶段输出';
const descriptionInput = findByClass(document.body, 'project-orchestration-task-dialog-textarea');
descriptionInput.value = '读取阶段一的两个结果并汇总。';
submitButton.listeners.click();

const result = await promise;
assert.equal(result.ok, true);
assert.equal(result.task.title, '验证并行阶段输出');
assert.equal(result.task.description, '读取阶段一的两个结果并汇总。');
assert.equal(result.task.executionStage, 4);
assert.equal(result.task.priority, 'medium');
assert.equal(document.body.children.length, 0);

console.log('project orchestration task dialog runtime contract ok');
