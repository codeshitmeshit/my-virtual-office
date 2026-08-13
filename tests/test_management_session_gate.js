const assert = require('assert');
const fs = require('fs');
const path = require('path');
const vm = require('vm');

const root = path.resolve(__dirname, '..');
const gate = fs.readFileSync(path.join(root, 'app', 'management-session-gate.js'), 'utf8');
const readiness = fs.readFileSync(path.join(root, 'app', 'management-session-readiness.js'), 'utf8');
const css = fs.readFileSync(path.join(root, 'app', 'management-session-gate.css'), 'utf8');
const index = fs.readFileSync(path.join(root, 'app', 'index.html'), 'utf8');
const i18n = fs.readFileSync(path.join(root, 'app', 'i18n.js'), 'utf8');
const server = fs.readFileSync(path.join(root, 'app', 'server.py'), 'utf8');

assert(index.includes('class="management-session-pending"'));
assert(index.includes('management-session-gate.css'));
assert(index.includes('<script src="management-session-gate.js'));
assert(index.includes('<script src="management-session-readiness.js'));
assert(gate.includes("PROBE_PATH = '/api/management/session'"));
assert(gate.includes("sessionStorage.setItem(STORAGE_KEY, token)"));
assert(!gate.includes('localStorage.setItem'));
assert(gate.includes("event.key === 'Escape'"));
assert(gate.includes("event.key !== 'Tab'"));
assert(gate.includes("input.type = 'password'"));
assert(gate.includes('card.tabIndex = -1'));
assert(gate.includes('if (elements.input.value.trim()) validateInput()'));
assert(gate.includes("credentials: 'same-origin'"));
assert(gate.includes('PROBE_TIMEOUT_MS = 8000'));
assert(gate.includes('Promise.race'));
assert(gate.includes('controller.abort()'));
assert(readiness.includes("AUTHENTICATED_EVENT = 'management-session:authenticated'"));
assert(readiness.includes("classList.contains('management-session-pending')"));
assert(css.includes('z-index: 20000'));
assert(css.includes('backdrop-filter: blur(8px)'));
assert(css.includes('body > :not(#management-session-gate)'));
assert(i18n.includes('setManagementAccessHandler'));
assert(i18n.includes("sessionStorage.removeItem('voManagementToken')"));
assert(server.includes('server_routes.management_session.GET_PATH'));

for (const locale of ['en.json', 'zh.json']) {
    const messages = JSON.parse(fs.readFileSync(path.join(root, 'app', 'locales', locale), 'utf8'));
    for (const key of [
        'management_gate_checking_title',
        'management_gate_login_title',
        'management_gate_submit',
        'management_gate_invalid',
        'management_gate_timeout',
        'management_gate_network_error'
    ]) assert(messages[key], `${locale} missing ${key}`);
}

console.log('management session entry gate contract ok');

class FakeElement {
    constructor(tag, document) {
        this.tagName = String(tag).toUpperCase();
        this.ownerDocument = document;
        this.children = [];
        this.listeners = {};
        this.attributes = {};
        this.className = '';
        this.textContent = '';
        this.value = '';
        this.hidden = false;
        this.disabled = false;
        this.parentNode = null;
        this.classList = {
            contains: (name) => this.className.split(/\s+/).includes(name),
            add: (name) => { if (!this.classList.contains(name)) this.className = `${this.className} ${name}`.trim(); },
            remove: (name) => { this.className = this.className.split(/\s+/).filter((item) => item && item !== name).join(' '); }
        };
    }
    set id(value) { this._id = value; if (value) this.ownerDocument.byId.set(value, this); }
    get id() { return this._id || ''; }
    setAttribute(name, value) { this.attributes[name] = String(value); }
    addEventListener(type, listener) { this.listeners[type] = listener; }
    appendChild(child) { child.parentNode = this; this.children.push(child); return child; }
    focus() { this.ownerDocument.activeElement = this; }
    remove() {
        if (this.id) this.ownerDocument.byId.delete(this.id);
        for (const child of this.children) child.remove();
        if (this.parentNode) this.parentNode.children = this.parentNode.children.filter((child) => child !== this);
    }
}

async function testEntryGateAuthenticatesAndStoresTabSession() {
    const byId = new Map();
    const htmlClasses = new Set(['management-session-pending']);
    const document = {
        byId,
        activeElement: null,
        listeners: {},
        createElement(tag) { return new FakeElement(tag, document); },
        getElementById(id) { return byId.get(id) || null; },
        addEventListener(type, listener) { this.listeners[type] = listener; },
        removeEventListener(type, listener) { if (this.listeners[type] === listener) delete this.listeners[type]; },
        documentElement: { classList: { add(name) { htmlClasses.add(name); }, remove(name) { htmlClasses.delete(name); } } }
    };
    document.body = new FakeElement('body', document);
    const storage = new Map();
    const events = {};
    const calls = [];
    const window = {
        navigator: { language: 'en' },
        addEventListener(type, listener) { events[type] = listener; },
        dispatchEvent() {},
        fetch: async (_url, init) => {
            const token = init.headers.get('X-VO-Management-Token') || '';
            calls.push(token);
            return token === '4285'
                ? new Response(JSON.stringify({ ok: true, authenticated: true }), { status: 200 })
                : new Response(JSON.stringify({ ok: false, code: 'management_token_required' }), { status: 403 });
        },
        i18n: { getLanguage: () => 'en', t: (key) => key, setManagementAccessHandler(handler) { this.handler = handler; } }
    };
    const context = {
        window,
        document,
        sessionStorage: {
            getItem(key) { return storage.get(key) || null; },
            setItem(key, value) { storage.set(key, String(value)); },
            removeItem(key) { storage.delete(key); }
        },
        Headers,
        Response,
        CustomEvent: class CustomEvent {},
        Promise,
        setTimeout: (fn, delay) => { if (!delay) fn(); return 1; },
        clearTimeout() {},
        AbortController
    };
    vm.runInNewContext(gate, context, { filename: 'management-session-gate.js' });
    await new Promise((resolve) => setImmediate(resolve));

    const overlay = document.getElementById('management-session-gate');
    assert(overlay, 'unauthenticated startup must keep the entry gate mounted');
    const input = document.getElementById('management-session-input');
    input.value = '4285';
    input.listeners.input();
    const form = overlay.children[0].children[3];
    form.listeners.submit({ preventDefault() {} });
    await new Promise((resolve) => setImmediate(resolve));

    assert.strictEqual(storage.get('voManagementToken'), '4285');
    assert.strictEqual(document.getElementById('management-session-gate'), null);
    assert.strictEqual(htmlClasses.has('management-session-pending'), false);
    assert.deepStrictEqual(calls, ['', '4285']);
}

testEntryGateAuthenticatesAndStoresTabSession().then(() => {
    console.log('management session entry gate behavior ok');
}).catch((error) => {
    console.error(error);
    process.exitCode = 1;
});
