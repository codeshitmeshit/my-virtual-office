const assert = require('assert');
const fs = require('fs');
const path = require('path');
const vm = require('vm');

const root = path.resolve(__dirname, '..');
const source = fs.readFileSync(path.join(root, 'app', 'oss-settings.js'), 'utf8');
const index = fs.readFileSync(path.join(root, 'app', 'index.html'), 'utf8');
const en = JSON.parse(fs.readFileSync(path.join(root, 'app', 'locales', 'en.json'), 'utf8'));
const zh = JSON.parse(fs.readFileSync(path.join(root, 'app', 'locales', 'zh.json'), 'utf8'));

assert(index.includes('oss-settings.js'), 'existing settings page should load focused OSS module');
assert(source.includes("i18n.managementFetch"), 'OSS settings must reuse management authorization');
assert(source.includes("MutationObserver"), 'OSS settings should load only when the panel opens');
assert(source.includes("textContent"), 'dynamic status must use safe text rendering');
assert(!source.includes('localStorage'), 'OSS settings and secrets must not use localStorage');
assert(!source.includes('sessionStorage'), 'OSS settings and secrets must not use sessionStorage');
for (const key of [
  'oss_settings_title', 'oss_endpoint', 'oss_bucket', 'oss_access_key_id',
  'oss_access_key_secret', 'oss_secret_configured', 'oss_test_and_activate',
  'oss_loading', 'oss_activated', 'oss_secret_required', 'oss_settings_failed',
  'oss_endpoint_invalid', 'oss_region_unresolved', 'oss_bucket_invalid',
  'oss_access_key_id_invalid', 'oss_access_key_secret_invalid',
]) {
  assert(en[key], `en.json missing ${key}`);
  assert(zh[key], `zh.json missing ${key}`);
}

class FakeElement {
  constructor(tag, document) {
    this.tagName = String(tag).toUpperCase();
    this.ownerDocument = document;
    this.children = [];
    this.listeners = {};
    this.attributes = {};
    this.value = '';
    this.textContent = '';
    this.className = '';
    this.disabled = false;
    this.hidden = false;
    this.type = '';
    this.parentNode = null;
    this._innerHTML = '';
    this.classList = {
      values: new Set(),
      contains: (value) => this.classList.values.has(value),
      add: (value) => this.classList.values.add(value),
      remove: (value) => this.classList.values.delete(value),
    };
  }
  set id(value) {
    this._id = value;
    if (value) this.ownerDocument.byId.set(value, this);
  }
  get id() { return this._id || ''; }
  set innerHTML(value) {
    this._innerHTML = String(value);
    const pattern = /<(input|button|div|span)[^>]*\sid="([^"]+)"[^>]*>/g;
    let match;
    while ((match = pattern.exec(this._innerHTML))) {
      const child = new FakeElement(match[1], this.ownerDocument);
      child.id = match[2];
      if (/type="password"/.test(match[0])) child.type = 'password';
      if (/\shidden(?:\s|>)/.test(match[0])) child.hidden = true;
      this.appendChild(child);
    }
  }
  get innerHTML() { return this._innerHTML; }
  setAttribute(name, value) { this.attributes[name] = String(value); }
  getAttribute(name) { return this.attributes[name] || null; }
  appendChild(child) { child.parentNode = this; this.children.push(child); return child; }
  insertBefore(child, reference) {
    child.parentNode = this;
    const index = this.children.indexOf(reference);
    if (index < 0) this.children.push(child);
    else this.children.splice(index, 0, child);
    return child;
  }
  querySelector(selector) {
    if (selector.startsWith('.')) {
      const className = selector.slice(1);
      return this.children.find((child) => String(child.className || '').split(/\s+/).includes(className)) || null;
    }
    return null;
  }
  addEventListener(type, listener) { this.listeners[type] = listener; }
}

function createEnvironment() {
  const document = {
    byId: new Map(),
    readyState: 'complete',
    createElement(tag) { return new FakeElement(tag, document); },
    getElementById(id) { return document.byId.get(id) || null; },
    querySelector(selector) { return selector === '#main-menu-panel .main-menu-body' ? body : null; },
  };
  const panel = new FakeElement('div', document);
  panel.id = 'main-menu-panel';
  const body = new FakeElement('div', document);
  const saveButton = new FakeElement('button', document);
  saveButton.className = 'mm-btn mm-btn-primary mm-save-all';
  body.appendChild(saveButton);
  const observers = [];
  class MutationObserver {
    constructor(callback) { this.callback = callback; observers.push(this); }
    observe(target, options) { this.target = target; this.options = options; }
    trigger() { this.callback([{ type: 'attributes', attributeName: 'class' }]); }
  }
  const responses = [];
  const calls = [];
  const i18n = {
    t: (key) => key,
    applyTranslations() {},
    async managementFetch(url, init) {
      calls.push({ url, init });
      if (!responses.length) throw new Error('missing fake response');
      return responses.shift();
    },
  };
  const window = { i18n };
  const context = { window, document, MutationObserver, console, Promise, setTimeout, clearTimeout };
  vm.runInNewContext(source, context, { filename: 'oss-settings.js' });
  return { window, document, panel, body, saveButton, observers, responses, calls };
}

function response(payload, ok = true) {
  return { ok, status: ok ? 200 : 400, async json() { return payload; } };
}

async function flush() {
  await new Promise((resolve) => setImmediate(resolve));
  await new Promise((resolve) => setImmediate(resolve));
}

async function main() {
  const env = createEnvironment();
  const section = env.document.getElementById('oss-settings-section');
  assert(section, 'section should be appended once');
  assert(env.body.children.indexOf(section) < env.body.children.indexOf(env.saveButton), 'OSS section should precede page save action');
  assert.strictEqual(env.document.getElementById('oss-region'), null, 'Region must not be exposed as a setting');
  assert.strictEqual(env.document.getElementById('oss-settings-status').hidden, true, 'status panel should not reserve space before first load');
  assert.strictEqual(env.calls.length, 0, 'closed panel must not read protected settings');

  env.responses.push(response({
    ok: true,
    settings: {
      endpoint: '',
      bucket: '',
      accessKeyId: '',
      configured: false,
      secretConfigured: false,
    },
  }));
  env.panel.classList.add('open');
  env.observers[0].trigger();
  await flush();
  assert.strictEqual(env.calls.length, 1, 'first open should load settings once');
  assert.strictEqual(env.calls[0].url, '/api/settings/oss');
  assert.strictEqual(env.document.getElementById('oss-access-key-secret').value, '', 'stored secret must never be filled');
  assert.strictEqual(env.document.getElementById('oss-bucket').value, '');
  assert.strictEqual(env.document.getElementById('oss-settings-status').hidden, true, 'empty configuration should not show a status panel');

  env.observers[0].trigger();
  await flush();
  assert.strictEqual(env.calls.length, 1, 'same page should not reload protected settings');

  env.document.getElementById('oss-endpoint').value = 'oss-cn-hangzhou.aliyuncs.com';
  env.document.getElementById('oss-bucket').value = 'replacement-bucket';
  env.document.getElementById('oss-access-key-id').value = 'LTAI-safe';
  env.document.getElementById('oss-access-key-secret').value = 'replacement-secret';
  env.responses.push(response({
    ok: true,
    settings: {
      endpoint: 'https://oss-cn-hangzhou.aliyuncs.com',
      bucket: 'replacement-bucket',
      accessKeyId: 'LTAI-safe',
      configured: true,
      secretConfigured: true,
    },
  }));
  await env.window.VOOssSettings.testAndActivate();
  const submitted = JSON.parse(env.calls[1].init.body);
  assert.strictEqual(submitted.endpoint, 'oss-cn-hangzhou.aliyuncs.com', 'scheme-less Endpoint should be accepted by the settings API');
  assert.strictEqual(submitted.accessKeySecret, 'replacement-secret');
  assert.strictEqual(Object.prototype.hasOwnProperty.call(submitted, 'region'), false, 'POST must not contain Region');
  assert.strictEqual(env.document.getElementById('oss-access-key-secret').value, '', 'submitted secret must be cleared');
  assert.strictEqual(env.document.getElementById('oss-settings-status').textContent, 'oss_activated');
  assert.strictEqual(env.document.getElementById('oss-settings-status').hidden, false, 'activation result should be visible');

  env.document.getElementById('oss-access-key-secret').value = 'replacement-secret';
  env.responses.push(response({
    ok: false,
    code: 'oss_endpoint_invalid',
    error: 'unlocalized server message',
  }, false));
  await env.window.VOOssSettings.testAndActivate();
  assert.strictEqual(
    env.document.getElementById('oss-settings-status').textContent,
    'oss_endpoint_invalid',
    'known safe error codes should use the active locale',
  );
}

main().then(() => {
  console.log('OSS settings UI contract ok');
}).catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
