const assert = require('assert');
const fs = require('fs');
const path = require('path');
const vm = require('vm');

const root = path.resolve(__dirname, '..');
const source = fs.readFileSync(path.join(root, 'app', 'i18n.js'), 'utf8');
const styles = fs.readFileSync(path.join(root, 'app', 'style.css'), 'utf8');

assert(source.includes("function requestManagementToken()"));
assert(source.includes("input.type = 'password'"));
assert(source.includes("input.autocomplete = 'current-password'"));
assert(source.includes("event.key === 'Escape'"));
assert(source.includes("event.key === 'Enter'"));
assert(source.includes("event.target === modal"));
assert(source.includes("previouslyFocused.focus()"));
assert(source.includes("token = await requestManagementToken()"));
assert(!source.includes("window.prompt(t('management_token_prompt')"));
assert(styles.includes('.management-token-dialog'));
assert(styles.includes('.management-token-input:focus'));

for (const locale of ['en.json', 'zh.json']) {
  const messages = JSON.parse(fs.readFileSync(path.join(root, 'app', 'locales', locale), 'utf8'));
  for (const key of [
    'management_token_title',
    'management_token_placeholder',
    'management_token_cancel',
    'management_token_confirm',
  ]) {
    assert(messages[key], `${locale} missing ${key}`);
  }
}

console.log('management token dialog contract ok');

class FakeElement {
  constructor(tag, document) {
    this.tagName = String(tag).toUpperCase();
    this.ownerDocument = document;
    this.children = [];
    this.attributes = {};
    this.listeners = {};
    this.parentNode = null;
    this.value = '';
    this.textContent = '';
    this.className = '';
  }
  set id(value) {
    this._id = value;
    if (value) this.ownerDocument.byId.set(value, this);
  }
  get id() { return this._id || ''; }
  setAttribute(name, value) { this.attributes[name] = String(value); }
  getAttribute(name) { return this.attributes[name] ?? null; }
  appendChild(child) { child.parentNode = this; this.children.push(child); return child; }
  addEventListener(type, listener) { this.listeners[type] = listener; }
  focus() { this.ownerDocument.activeElement = this; }
  remove() {
    if (this.id) this.ownerDocument.byId.delete(this.id);
    for (const child of this.children) child.remove();
    if (this.parentNode) this.parentNode.children = this.parentNode.children.filter((child) => child !== this);
  }
  closest(selector) {
    const match = /^\[([^\]]+)\]$/.exec(selector);
    return match && Object.prototype.hasOwnProperty.call(this.attributes, match[1]) ? this : null;
  }
}

function createDocument() {
  const listeners = {};
  const document = {
    byId: new Map(),
    readyState: 'loading',
    activeElement: { focus() {} },
    createElement(tag) { return new FakeElement(tag, document); },
    getElementById(id) { return document.byId.get(id) || null; },
    querySelector() { return null; },
    querySelectorAll() { return []; },
    addEventListener(type, listener) { listeners[type] = listener; },
    removeEventListener(type, listener) { if (listeners[type] === listener) delete listeners[type]; },
    documentElement: { lang: 'en' },
  };
  document.body = new FakeElement('body', document);
  return document;
}

async function testConcurrentPromptSharing() {
  const document = createDocument();
  const storage = new Map();
  const window = {
    location: { href: 'http://localhost:8090/' },
    dispatchEvent() {},
  };
  const context = {
    window,
    document,
    navigator: { language: 'en' },
    localStorage: { getItem: () => null, setItem() {} },
    sessionStorage: {
      getItem(key) { return storage.get(key) || null; },
      setItem(key, value) { storage.set(key, String(value)); },
      removeItem(key) { storage.delete(key); },
    },
    Headers,
    URL,
    CustomEvent: class CustomEvent {},
    fetch: async () => ({ status: 200 }),
    console,
    setTimeout,
    clearTimeout,
  };
  vm.runInNewContext(source, context, { filename: 'i18n.js' });

  const first = window.i18n.requestManagementToken();
  const second = window.i18n.requestManagementToken();
  assert.strictEqual(first, second, 'concurrent callers must share one prompt promise');
  assert.strictEqual(document.body.children.length, 1, 'only one modal should be rendered');

  const input = document.getElementById('management-token-input');
  input.value = ' 4285 ';
  input.listeners.input();
  const modal = document.getElementById('management-token-dialog');
  const confirm = modal.children[0].children[2].children[1];
  modal.listeners.click({ target: confirm });
  assert.strictEqual(await first, '4285');
  assert.strictEqual(await second, '4285');
  assert.strictEqual(document.getElementById('management-token-dialog'), null);

  await Promise.resolve();
  const third = window.i18n.requestManagementToken();
  assert.notStrictEqual(third, first, 'a settled prompt must allow a new dialog');
  const thirdModal = document.getElementById('management-token-dialog');
  thirdModal.listeners.click({ target: thirdModal });
  assert.strictEqual(await third, '');
}

testConcurrentPromptSharing().then(() => {
  console.log('management token concurrent prompt behavior ok');
}).catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
