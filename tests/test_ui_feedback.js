const assert = require('assert');
const fs = require('fs');
const path = require('path');

class FakeElement {
    constructor(tagName, documentRef) {
        this.tagName = String(tagName).toUpperCase();
        this.ownerDocument = documentRef;
        this.children = [];
        this.parentNode = null;
        this.attributes = {};
        this.listeners = {};
        this.className = '';
        this.id = '';
        this.textContent = '';
        this.type = '';
    }
    appendChild(child) {
        child.parentNode = this;
        this.children.push(child);
        return child;
    }
    removeChild(child) {
        const index = this.children.indexOf(child);
        if (index >= 0) this.children.splice(index, 1);
        child.parentNode = null;
        return child;
    }
    setAttribute(name, value) { this.attributes[name] = String(value); }
    getAttribute(name) { return this.attributes[name]; }
    addEventListener(type, listener) { this.listeners[type] = listener; }
    click() { if (this.listeners.click) this.listeners.click({ currentTarget: this }); }
    get lastChild() { return this.children[this.children.length - 1] || null; }
}

class FakeDocument {
    constructor() { this.body = new FakeElement('body', this); }
    createElement(tagName) { return new FakeElement(tagName, this); }
    getElementById(id) {
        function find(node) {
            if (node.id === id) return node;
            for (const child of node.children) {
                const match = find(child);
                if (match) return match;
            }
            return null;
        }
        return find(this.body);
    }
}

const pendingTimers = new Map();
let timerId = 0;
global.document = new FakeDocument();
global.setTimeout = (callback, duration) => {
    const id = ++timerId;
    pendingTimers.set(id, { callback, duration });
    return id;
};
global.clearTimeout = (id) => pendingTimers.delete(id);

const feedback = require('../app/ui-feedback.js');

const successId = feedback.show({ title: 'Saved', message: 'Draft updated', tone: 'success', duration: 2500 });
const errorId = feedback.show({ message: 'Save failed', tone: 'error' });
const region = document.getElementById('vo-feedback-region');
assert(region, 'feedback region should be mounted once');
assert.strictEqual(region.children.length, 2, 'messages must stack instead of replacing each other');
assert.strictEqual(region.children[0].getAttribute('role'), 'status');
assert.strictEqual(region.children[0].getAttribute('aria-live'), 'polite');
assert.strictEqual(region.children[0].children[1].children[0].textContent, 'Saved');
assert.strictEqual(feedback.snapshot()[0].title, 'Saved');
assert.strictEqual(region.children[1].getAttribute('role'), 'alert');
assert.strictEqual(region.children[1].getAttribute('aria-live'), 'assertive');
assert.strictEqual(feedback.snapshot()[1].persistent, true, 'errors stay visible by default');
assert.strictEqual(pendingTimers.size, 1, 'only transient feedback should schedule dismissal');

pendingTimers.values().next().value.callback();
assert.deepStrictEqual(feedback.snapshot().map((item) => item.id), [errorId]);
assert.strictEqual(feedback.remove(errorId), true);
assert.strictEqual(region.children.length, 0);

let retried = false;
feedback.show({
    message: 'Try again',
    tone: 'error',
    action: { label: 'Retry', onClick: () => { retried = true; } },
});
region.children[0].children[2].children[0].click();
assert.strictEqual(retried, true, 'feedback actions must invoke their callback');
assert.strictEqual(feedback.snapshot().length, 0, 'a completed action dismisses its feedback');

feedback.legacy('❌ Could not save');
feedback.legacy('✅ Saved');
assert.deepStrictEqual(feedback.snapshot().map((item) => item.tone), ['error', 'success']);
feedback.clear();

const html = fs.readFileSync(path.join(__dirname, '../app/index.html'), 'utf8');
const css = fs.readFileSync(path.join(__dirname, '../app/ui-feedback.css'), 'utf8');
assert(html.indexOf('ui-feedback.css') < html.indexOf('style.css'), 'feedback primitives load before feature styles');
assert(html.indexOf('ui-feedback.js') < html.indexOf('game.js'), 'feedback owner loads before legacy adapters');
assert(css.includes('data-tone="error"'));
assert(css.includes(':focus-visible'));
assert(css.includes('top: var(--ui-space-xl)'));

console.log('UI feedback queue tests passed');
