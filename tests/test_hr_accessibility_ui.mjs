import assert from 'node:assert/strict';
import { createRequire } from 'node:module';


const require = createRequire(import.meta.url);

function focusable(name) {
  return {
    name,
    closest: () => null,
    focus() { globalThis.document.activeElement = this; },
  };
}

const first = focusable('first');
const last = focusable('last');
const opener = focusable('opener');
const classes = new Set();
const modal = {
  classList: {
    add: (name) => classes.add(name),
    remove: (name) => classes.delete(name),
  },
  querySelectorAll: () => [first, last],
  setAttribute() {},
};
const listeners = {};
globalThis.document = {
  activeElement: opener,
  addEventListener: (name, callback) => { listeners[name] = callback; },
  getElementById: (id) => (id === 'humanResourcesModal' ? modal : null),
  querySelector: () => null,
};

const hr = require('../app/human-resources.js');
assert.equal(listeners.keydown, hr.helpers.handleKeydown);

hr.state.open = true;
globalThis.document.activeElement = last;
let prevented = false;
hr.helpers.handleKeydown({ key: 'Tab', shiftKey: false, preventDefault: () => { prevented = true; } });
assert.equal(prevented, true);
assert.equal(globalThis.document.activeElement, first, 'forward Tab wraps to first focusable control');

globalThis.document.activeElement = first;
prevented = false;
hr.helpers.handleKeydown({ key: 'Tab', shiftKey: true, preventDefault: () => { prevented = true; } });
assert.equal(prevented, true);
assert.equal(globalThis.document.activeElement, last, 'reverse Tab wraps to last focusable control');

hr.state.returnFocus = opener;
prevented = false;
hr.helpers.handleKeydown({ key: 'Escape', preventDefault: () => { prevented = true; } });
assert.equal(prevented, true);
assert.equal(hr.state.open, false);
assert.equal(classes.has('hidden'), true);
assert.equal(globalThis.document.activeElement, opener, 'Escape returns focus to the opener');

console.log('Human Resources focus trap, Escape, and focus return checks passed');
