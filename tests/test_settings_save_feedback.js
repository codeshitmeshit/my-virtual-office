const assert = require('assert');
const fs = require('fs');
const path = require('path');
const vm = require('vm');

const root = path.resolve(__dirname, '..');
const modulePath = path.join(root, 'app', 'settings-save-feedback.js');
assert(fs.existsSync(modulePath), 'settings save feedback module must exist');
const source = fs.readFileSync(modulePath, 'utf8');

class FakeClassList {
  constructor() { this.values = new Set(); }
  add(...values) { values.forEach((value) => this.values.add(value)); }
  remove(...values) { values.forEach((value) => this.values.delete(value)); }
  contains(value) { return this.values.has(value); }
}

class FakeElement {
  constructor(tagName, document) {
    this.tagName = tagName.toUpperCase();
    this.ownerDocument = document;
    this.children = [];
    this.parentNode = null;
    this.attributes = {};
    this.classList = new FakeClassList();
    this.className = '';
    this.textContent = '';
    this.hidden = false;
    this.disabled = false;
  }
  set id(value) { this._id = value; if (value) this.ownerDocument.byId.set(value, this); }
  get id() { return this._id || ''; }
  setAttribute(name, value) { this.attributes[name] = String(value); }
  getAttribute(name) { return this.attributes[name] || null; }
  appendChild(child) { child.parentNode = this; this.children.push(child); return child; }
  insertBefore(child, reference) {
    child.parentNode = this;
    const index = this.children.indexOf(reference);
    if (index < 0) this.children.push(child); else this.children.splice(index, 0, child);
    return child;
  }
}

function createEnvironment() {
  const listeners = {};
  const document = {
    byId: new Map(),
    readyState: 'complete',
    createElement(tag) { return new FakeElement(tag, document); },
    getElementById(id) { return document.byId.get(id) || null; },
    querySelector(selector) {
      if (selector === '.settings-modal-footer') return footer;
      if (selector === '.settings-modal-footer .mm-save-all') return saveButton;
      return null;
    },
  };
  const footer = new FakeElement('div', document);
  footer.className = 'settings-modal-footer';
  const saveButton = new FakeElement('button', document);
  saveButton.className = 'mm-save-all';
  footer.appendChild(saveButton);
  let language = 'en';
  const copy = {
    en: { settings_save_saving: 'Saving settings…', settings_save_success: 'Settings saved', settings_save_failed: 'Save failed' },
    zh: { settings_save_saving: '正在保存设置…', settings_save_success: '设置已保存', settings_save_failed: '保存失败' },
  };
  const window = {
    document,
    i18n: { t(key) { return copy[language][key] || key; } },
    addEventListener(type, listener) { (listeners[type] ||= []).push(listener); },
    dispatchEvent(event) { for (const listener of listeners[event.type] || []) listener(event); },
  };
  const context = { window, document, console, module: { exports: {} }, exports: {} };
  vm.runInNewContext(source, context, { filename: 'settings-save-feedback.js' });
  return { window, document, footer, saveButton, api: window.VOSettingsSaveFeedback, setLanguage(next) { language = next; } };
}

function main() {
  const env = createEnvironment();
  assert(env.api, 'module should expose VOSettingsSaveFeedback');
  const status = env.document.getElementById('settings-save-status');
  assert(status, 'one footer status region should mount');
  assert.strictEqual(status.getAttribute('role'), 'status');
  assert.strictEqual(status.getAttribute('aria-live'), 'polite');
  assert.strictEqual(status.hidden, true);

  env.api.start();
  assert.strictEqual(env.saveButton.disabled, true);
  assert.strictEqual(status.hidden, false);
  assert.strictEqual(status.getAttribute('data-state'), 'saving');
  assert.strictEqual(status.textContent, 'Saving settings…');

  env.api.success();
  assert.strictEqual(env.saveButton.disabled, false);
  assert.strictEqual(status.getAttribute('data-state'), 'success');
  assert.strictEqual(status.textContent, 'Settings saved');

  env.api.failure('<gateway unavailable>');
  assert.strictEqual(env.saveButton.disabled, false);
  assert.strictEqual(status.getAttribute('data-state'), 'error');
  assert.strictEqual(status.textContent, 'Save failed: <gateway unavailable>');

  env.setLanguage('zh');
  env.window.dispatchEvent({ type: 'i18n:changed' });
  assert.strictEqual(status.textContent, '保存失败: <gateway unavailable>');
  assert.strictEqual(env.api.mount(), status, 'mount should be idempotent');
  assert.strictEqual(env.footer.children.filter((child) => child.id === 'settings-save-status').length, 1);

  console.log('settings save feedback UI ok');
}

main();
