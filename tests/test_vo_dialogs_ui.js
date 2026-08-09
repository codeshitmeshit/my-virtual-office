const assert = require('assert');
const fs = require('fs');
const path = require('path');
const vm = require('vm');

const root = path.resolve(__dirname, '..');
const source = fs.readFileSync(path.join(root, 'app', 'vo-dialogs.js'), 'utf8');

function node(tag) {
  return {
    tagName: String(tag || '').toUpperCase(),
    children: [],
    attributes: {},
    listeners: {},
    parentNode: null,
    className: '',
    id: '',
    value: '',
    textContent: '',
    appendChild(child) { child.parentNode = this; this.children.push(child); return child; },
    removeChild(child) { this.children = this.children.filter(item => item !== child); child.parentNode = null; },
    setAttribute(name, value) { this.attributes[name] = String(value); },
    addEventListener(name, listener) { this.listeners[name] = listener; },
    focus() { this.focused = true; },
    select() { this.selected = true; }
  };
}

function documentFixture() {
  const body = node('body');
  const head = node('head');
  const listeners = {};
  function walk(current, predicate) {
    if (predicate(current)) return current;
    for (const child of current.children) {
      const found = walk(child, predicate);
      if (found) return found;
    }
    return null;
  }
  return {
    body,
    head,
    listeners,
    createElement: node,
    getElementById(id) { return walk(body, item => item.id === id) || walk(head, item => item.id === id); },
    addEventListener(name, listener) { listeners[name] = listener; },
    removeEventListener(name, listener) { if (listeners[name] === listener) delete listeners[name]; }
  };
}

(async function run() {
  const document = documentFixture();
  const window = { document };
  vm.runInNewContext(source, { window, Promise }, { filename: 'vo-dialogs.js' });

  assert.ok(window.VODialogs);
  assert.ok(!source.includes("style.textContent"), 'dialog presentation must live in ui-dialogs.css');

  const confirmPromise = window.VODialogs.showConfirm('Delete item?', { tone: 'danger' });
  const overlay = document.body.children[0];
  const box = overlay.children[0];
  const title = box.children[0];
  const actions = box.children[box.children.length - 1];
  const ok = actions.children[1];
  assert.strictEqual(box.attributes.role, 'dialog');
  assert.strictEqual(box.attributes['aria-modal'], 'true');
  assert.strictEqual(box.attributes['aria-labelledby'], title.id);
  assert.strictEqual(ok.className, 'vo-dialog-danger');
  assert.strictEqual(ok.focused, true);
  assert.strictEqual(overlay.listeners.click, undefined, 'generic dialog must not add backdrop close');
  ok.listeners.click();
  assert.strictEqual(await confirmPromise, true);
  assert.strictEqual(document.body.children.length, 0);

  const promptPromise = window.VODialogs.showPrompt('Name', 'draft');
  document.listeners.keydown({ key: 'Escape', preventDefault() {} });
  assert.strictEqual(await promptPromise, null);

  const alertPromise = window.VODialogs.showAlert('Saved');
  document.listeners.keydown({ key: 'Enter', preventDefault() {} });
  assert.strictEqual(await alertPromise, undefined);
  assert.strictEqual(document.body.children.length, 0);
  assert.strictEqual(document.listeners.keydown, undefined);

  for (const filename of ['app/index.html', 'app/models.html', 'app/cron.html']) {
    const html = fs.readFileSync(path.join(root, filename), 'utf8');
    assert.match(html, /href="ui-dialogs\.css\?v=[^"]+"/, `${filename} must load ui-dialogs.css`);
  }

  console.log('vo dialogs behavior and presentation boundary ok');
})().catch(error => {
  console.error(error);
  process.exitCode = 1;
});
