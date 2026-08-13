const assert = require('assert');
const fs = require('fs');
const path = require('path');
const vm = require('vm');

const source = fs.readFileSync(path.join(__dirname, '../app/management-session-readiness.js'), 'utf8');

function environment(pending) {
    const listeners = new Map();
    const classes = new Set(pending ? ['management-session-pending'] : []);
    const window = {
        addEventListener(type, listener) { listeners.set(type, listener); },
        removeEventListener(type, listener) {
            if (listeners.get(type) === listener) listeners.delete(type);
        }
    };
    const document = {
        documentElement: { classList: { contains(name) { return classes.has(name); } } }
    };
    vm.runInNewContext(source, { window, document, Object }, { filename: 'management-session-readiness.js' });
    return { window, listeners, classes };
}

const ready = environment(false);
let immediateCalls = 0;
ready.window.VOManagementSessionReadiness.whenAuthenticated(() => { immediateCalls += 1; });
assert.strictEqual(immediateCalls, 1, 'already authenticated pages should start immediately');

const pending = environment(true);
let deferredCalls = 0;
pending.window.VOManagementSessionReadiness.whenAuthenticated(() => { deferredCalls += 1; });
assert.strictEqual(deferredCalls, 0, 'pending pages must not start protected background work');
pending.classes.delete('management-session-pending');
pending.listeners.get('management-session:authenticated')();
assert.strictEqual(deferredCalls, 1, 'authentication should release deferred background work once');

console.log('management session readiness behavior ok');
