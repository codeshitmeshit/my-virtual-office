const assert = require('assert');
const fs = require('fs');
const path = require('path');
const vm = require('vm');

const source = fs.readFileSync(path.resolve(__dirname, '..', 'app', 'office-branding.js'), 'utf8');

function element(id) {
  return {
    id,
    attributes: new Map(),
    className: '',
    textContent: '',
    src: '',
    disabled: false,
    classList: { toggle() {} },
    addEventListener() {},
    getAttribute(name) { return this.attributes.get(name) || null; },
    setAttribute(name, value) { this.attributes.set(name, String(value)); },
  };
}

async function run() {
  const brand = element('brand-title');
  const preview = element('mm-office-icon-preview');
  preview.setAttribute('data-default-src', 'favicon.png');
  const status = element('mm-office-icon-status');
  const fileInput = element('mm-office-icon-file');
  const clearButton = element('mm-office-icon-clear');
  const saveButton = element('save');
  const favicon = element('favicon');
  favicon.setAttribute('href', 'favicon.png');
  const elements = new Map([
    ['brand-title', brand],
    ['mm-office-icon-preview', preview],
    ['mm-office-icon-status', status],
    ['mm-office-icon-file', fileInput],
    ['mm-office-icon-clear', clearButton],
  ]);
  const document = {
    readyState: 'complete',
    title: '',
    getElementById(id) { return elements.get(id) || null; },
    querySelector(selector) { return selector.includes('mm-save-all') ? saveButton : null; },
    querySelectorAll(selector) { return selector === 'link[rel~="icon"]' ? [favicon] : []; },
    createElement() { throw new Error('canvas should not be needed in this test'); },
  };
  const icon = `data:image/png;base64,${Buffer.from('icon').toString('base64')}`;
  const window = {
    document,
    fetch() { return Promise.resolve({ json: async () => ({ office: { name: 'Studio', iconDataUrl: icon } }) }); },
    addEventListener() {},
    Promise,
  };
  const context = { window, globalThis: window, module: { exports: {} }, Promise, setTimeout, clearTimeout };
  vm.createContext(context);
  vm.runInContext(source, context);
  await Promise.resolve();
  await Promise.resolve();

  const api = window.VOOfficeBranding;
  assert(api, 'office branding API should be exposed');
  api.loadFromConfig({ name: 'Studio', iconDataUrl: icon });
  assert.strictEqual(document.title, 'Studio');
  assert.strictEqual(brand.textContent, 'STUDIO');
  assert.strictEqual(favicon.getAttribute('href'), icon);
  assert.deepStrictEqual(JSON.parse(JSON.stringify(api.buildOfficePayload('  New HQ  '))), { name: 'New HQ', iconDataUrl: icon });

  api.clearDraftIcon();
  assert.strictEqual(api.buildOfficePayload('New HQ').iconDataUrl, null);
  assert.strictEqual(favicon.getAttribute('href'), icon, 'draft removal must not change the live favicon');

  api.applySavedOffice({ name: 'New HQ', iconDataUrl: null });
  assert.strictEqual(document.title, 'New HQ');
  assert.strictEqual(favicon.getAttribute('href'), 'favicon.png');
  console.log('office branding browser state ok');
}

run().catch((error) => { console.error(error); process.exitCode = 1; });
