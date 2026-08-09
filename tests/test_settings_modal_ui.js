const assert = require('assert');
const fs = require('fs');
const path = require('path');
const vm = require('vm');

const root = path.resolve(__dirname, '..');
const modulePath = path.join(root, 'app', 'settings-modal-ui.js');
assert(fs.existsSync(modulePath), 'settings modal presentation module must exist');
const source = fs.readFileSync(modulePath, 'utf8');

class FakeClassList {
  constructor(element) {
    this.element = element;
    this.values = new Set();
  }
  _syncFromClassName() {
    this.values = new Set(String(this.element._className || '').split(/\s+/).filter(Boolean));
  }
  _syncToClassName() { this.element._className = [...this.values].join(' '); }
  add(...values) { values.forEach((value) => this.values.add(value)); this._syncToClassName(); }
  remove(...values) { values.forEach((value) => this.values.delete(value)); this._syncToClassName(); }
  contains(value) { return this.values.has(value); }
  toggle(value, force) {
    const enabled = force === undefined ? !this.contains(value) : Boolean(force);
    if (enabled) this.add(value); else this.remove(value);
    return enabled;
  }
}

class FakeElement {
  constructor(tagName, document) {
    this.tagName = String(tagName).toUpperCase();
    this.ownerDocument = document;
    this.children = [];
    this.parentNode = null;
    this.attributes = {};
    this.listeners = {};
    this.hidden = false;
    this.textContent = '';
    this.value = '';
    this.type = '';
    this._className = '';
    this.classList = new FakeClassList(this);
  }
  set id(value) {
    this._id = String(value || '');
    if (this._id) this.ownerDocument.byId.set(this._id, this);
  }
  get id() { return this._id || ''; }
  set className(value) { this._className = String(value || ''); this.classList._syncFromClassName(); }
  get className() { return this._className; }
  setAttribute(name, value) {
    this.attributes[name] = String(value);
    if (name === 'class') this.className = value;
  }
  getAttribute(name) { return Object.hasOwn(this.attributes, name) ? this.attributes[name] : null; }
  removeAttribute(name) { delete this.attributes[name]; }
  appendChild(child) {
    if (child.parentNode) child.parentNode.removeChild(child);
    child.parentNode = this;
    this.children.push(child);
    return child;
  }
  insertBefore(child, reference) {
    if (child.parentNode) child.parentNode.removeChild(child);
    const index = this.children.indexOf(reference);
    child.parentNode = this;
    if (index < 0) this.children.push(child); else this.children.splice(index, 0, child);
    return child;
  }
  removeChild(child) {
    const index = this.children.indexOf(child);
    if (index >= 0) this.children.splice(index, 1);
    child.parentNode = null;
    return child;
  }
  addEventListener(type, listener) {
    if (!this.listeners[type]) this.listeners[type] = [];
    this.listeners[type].push(listener);
  }
  click() { for (const listener of this.listeners.click || []) listener({ currentTarget: this, target: this }); }
  keydown(key) {
    let prevented = false;
    for (const listener of this.listeners.keydown || []) {
      listener({ key, currentTarget: this, target: this, preventDefault() { prevented = true; } });
    }
    return prevented;
  }
  focus() { this.ownerDocument.activeElement = this; }
  matches(selector) {
    if (selector.startsWith('#')) return this.id === selector.slice(1);
    if (selector.startsWith('.')) return this.classList.contains(selector.slice(1));
    const attribute = /^\[([^=\]]+)="([^"]+)"\]$/.exec(selector);
    if (attribute) return this.getAttribute(attribute[1]) === attribute[2];
    if (selector === 'a[href="/setup"]') return this.tagName === 'A' && this.getAttribute('href') === '/setup';
    return this.tagName === selector.toUpperCase();
  }
  querySelector(selector) {
    if (this.matches(selector)) return this;
    for (const child of this.children) {
      const found = child.querySelector(selector);
      if (found) return found;
    }
    return null;
  }
  querySelectorAll(selector) {
    const found = [];
    for (const child of this.children) {
      if (child.matches(selector)) found.push(child);
      found.push(...child.querySelectorAll(selector));
    }
    return found;
  }
}

function createSection(document, anchor, title) {
  const section = new FakeElement('section', document);
  section.className = 'mm-section';
  section.setAttribute('data-fixture-title', title);
  const control = new FakeElement(anchor === 'setup-link' ? 'a' : 'input', document);
  if (anchor === 'setup-link') control.setAttribute('href', '/setup');
  else control.id = anchor;
  control.value = title;
  section.appendChild(control);
  return { section, control };
}

function createEnvironment() {
  const documentListeners = {};
  const windowListeners = {};
  const document = {
    byId: new Map(),
    readyState: 'complete',
    createElement(tagName) { return new FakeElement(tagName, document); },
    getElementById(id) { return document.byId.get(id) || null; },
    addEventListener(type, listener) { documentListeners[type] = listener; },
  };

  const panel = new FakeElement('div', document);
  panel.id = 'main-menu-panel';
  panel.className = 'main-menu-panel';
  const header = new FakeElement('header', document);
  header.className = 'main-menu-header';
  const title = new FakeElement('span', document);
  title.textContent = 'SETTINGS';
  const close = new FakeElement('button', document);
  close.textContent = 'x';
  header.appendChild(title);
  header.appendChild(close);
  const body = new FakeElement('div', document);
  body.className = 'main-menu-body';
  panel.appendChild(header);
  panel.appendChild(body);

  const fixtures = [
    createSection(document, 'mm-oc-path', 'openclaw'),
    createSection(document, 'mm-hermes-enable', 'hermes'),
    createSection(document, 'mm-codex-enable', 'providers'),
    createSection(document, 'mm-office-name', 'office'),
    createSection(document, 'mm-show-bubbles', 'display'),
    createSection(document, 'mm-show-weather', 'weather location'),
    createSection(document, 'mm-weather-provider', 'weather provider'),
    createSection(document, 'mm-apiusage-enable', 'api usage'),
    createSection(document, 'mm-pcmetrics-enable', 'pc metrics'),
    createSection(document, 'mm-browser-enable', 'browser'),
    createSection(document, 'mm-feishu-enable', 'notifications'),
    createSection(document, 'mm-feishu-chat-enable', 'chat notifications'),
    createSection(document, 'oss-settings-section', 'storage'),
    createSection(document, 'mm-import-file', 'actions'),
    createSection(document, 'setup-link', 'help'),
  ];
  fixtures.forEach(({ section }) => body.appendChild(section));
  const unknown = createSection(document, 'future-setting', 'future');
  body.appendChild(unknown.section);

  const saveButton = new FakeElement('button', document);
  saveButton.className = 'mm-btn mm-save-all';
  saveButton.textContent = 'Save';
  body.appendChild(saveButton);

  let language = 'en';
  const translations = {
    en: {
      settings_modal_connections_agents: 'Connections & Agents',
      settings_modal_office: 'Office',
      settings_modal_weather: 'Weather',
      settings_modal_display: 'Display',
      settings_modal_tools_browser: 'Tools & Browser',
      settings_modal_notifications: 'Notifications',
      settings_modal_storage: 'Storage',
      settings_modal_advanced: 'Advanced',
      settings_modal_subtitle: 'Manage the current settings in one place.',
    },
    zh: {
      settings_modal_connections_agents: '连接与 Agent',
      settings_modal_office: '办公室',
      settings_modal_weather: '天气',
      settings_modal_display: '显示',
      settings_modal_tools_browser: '工具与浏览器',
      settings_modal_notifications: '通知',
      settings_modal_storage: '存储',
      settings_modal_advanced: '高级',
      settings_modal_subtitle: '集中管理当前设置。',
    },
  };
  const window = {
    document,
    i18n: { t(key) { return translations[language][key] || key; } },
    addEventListener(type, listener) {
      if (!windowListeners[type]) windowListeners[type] = [];
      windowListeners[type].push(listener);
    },
    dispatchEvent(event) {
      for (const listener of windowListeners[event.type] || []) listener(event);
    },
  };
  const context = { window, document, console, module: { exports: {} }, exports: {}, setTimeout, clearTimeout };
  vm.runInNewContext(source, context, { filename: 'settings-modal-ui.js' });
  return {
    document,
    window,
    panel,
    header,
    body,
    fixtures,
    unknown,
    saveButton,
    api: window.VOSettingsModal,
    setLanguage(next, eventType = 'i18n:changed') {
      language = next;
      window.dispatchEvent({ type: eventType });
    },
  };
}

function main() {
  const env = createEnvironment();
  assert(env.api, 'module should expose a focused VOSettingsModal API');
  assert.deepStrictEqual(
    Array.from(env.api.CATEGORY_DEFINITIONS, (category) => category.id),
    ['connections-agents', 'office', 'weather', 'display', 'tools-browser', 'notifications', 'storage', 'advanced'],
    'the modal should expose Weather as an independent task category',
  );

  const dialog = env.panel.querySelector('.settings-modal-dialog');
  assert(dialog, 'complete DOM should mount one large modal dialog');
  assert(env.panel.classList.contains('settings-modal-mounted'), 'enhancement class should be added after mount');
  assert.strictEqual(env.panel.querySelector('.main-menu-body'), env.body, 'existing body node must remain authoritative');
  assert.strictEqual(env.panel.querySelector('.main-menu-header'), env.header, 'existing header node must be moved, not cloned');
  assert.strictEqual(env.panel.querySelector('.mm-save-all'), env.saveButton, 'existing save action must be moved, not cloned');

  for (const { section, control } of env.fixtures) {
    if (control.id) {
      assert.strictEqual(env.document.getElementById(control.id), control);
    } else {
      assert.strictEqual(env.panel.querySelector('a[href="/setup"]'), control);
    }
    assert.strictEqual(section.parentNode.getAttribute('data-settings-category'), env.api.classifySection(section));
  }
  assert.strictEqual(env.api.classifySection(env.unknown.section), 'advanced', 'future settings must remain accessible');
  assert.strictEqual(env.unknown.section.getAttribute('data-settings-unclassified'), 'true');
  const notificationPanel = env.panel.querySelector('[data-settings-category-panel="notifications"]');
  assert.strictEqual(
    notificationPanel.querySelectorAll('.mm-section').length,
    2,
    'Feishu notifications and Feishu chat must remain separate cards in the notification category',
  );
  const officePanel = env.panel.querySelector('[data-settings-category-panel="office"]');
  const weatherPanel = env.panel.querySelector('[data-settings-category-panel="weather"]');
  assert(officePanel.querySelector('#mm-office-name'), 'Office should retain office identity settings');
  assert(officePanel.querySelector('#mm-weather-provider'), 'Office should own the weather provider integration');
  assert.strictEqual(officePanel.querySelector('#mm-show-weather'), null, 'Office must not own weather controls');
  assert(weatherPanel.querySelector('#mm-show-weather'), 'Weather should own its display toggle');
  assert.strictEqual(weatherPanel.querySelector('#mm-weather-provider'), null, 'Weather should not duplicate the provider integration');
  assert.strictEqual(weatherPanel.querySelectorAll('.mm-section').length, 1, 'Weather should render location as its own card');
  assert.strictEqual(officePanel.querySelectorAll('.mm-section').length, 2, 'Office should render identity and provider as independent cards');

  const originalInput = env.document.getElementById('mm-oc-path');
  originalInput.value = '/edited/path';
  let businessCalls = 0;
  env.window.mmSaveSettings = () => { businessCalls += 1; };
  env.api.activateCategory('display');
  env.api.activateCategory('connections-agents');
  assert.strictEqual(originalInput.value, '/edited/path', 'category switches must preserve the original input value');
  assert.strictEqual(businessCalls, 0, 'category navigation must not invoke settings business handlers');

  const activeButton = env.panel.querySelector('[data-settings-category-button="connections-agents"]');
  const officeButton = env.panel.querySelector('[data-settings-category-button="office"]');
  const displayPanel = env.panel.querySelector('[data-settings-category-panel="display"]');
  assert.strictEqual(activeButton.getAttribute('aria-selected'), 'true');
  assert.strictEqual(displayPanel.hidden, true);
  assert.strictEqual(activeButton.keydown('ArrowDown'), true, 'tab arrow navigation should prevent page scrolling');
  assert.strictEqual(officeButton.getAttribute('aria-selected'), 'true', 'ArrowDown should activate the next category');
  assert.strictEqual(env.document.activeElement, officeButton, 'keyboard navigation should move focus with selection');
  env.api.activateCategory('connections-agents');

  const originalDialog = dialog;
  assert.strictEqual(env.api.mountSettingsModal(), originalDialog, 'mount must be idempotent');
  assert.strictEqual(env.panel.querySelectorAll('.settings-modal-dialog').length, 1, 'repeat mount must not duplicate the dialog');

  const inputIdentityBeforeLanguageChange = env.document.getElementById('mm-oc-path');
  env.setLanguage('zh', 'i18n:ready');
  assert.strictEqual(env.document.getElementById('mm-oc-path'), inputIdentityBeforeLanguageChange, 'language changes must not rebuild controls');
  assert.strictEqual(activeButton.textContent, '连接与 Agent');

  console.log('settings modal UI behavior ok');
}

main();
