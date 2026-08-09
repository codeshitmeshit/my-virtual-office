import assert from 'assert';
import fs from 'fs';
import vm from 'vm';


const source = fs.readFileSync('app/personal-assets.js', 'utf8');
const content = { innerHTML: '', textContent: '' };
const modal = { classList: { add() {}, remove() {} } };
const toggle = { classList: { add() {}, remove() {} }, setAttribute() {}, removeAttribute() {} };
const requests = [];

const document = {
  activeElement: null,
  addEventListener() {},
  getElementById(id) {
    if (id === 'personal-assets-content') return content;
    if (id === 'personalAssetsModal') return modal;
    if (id === 'personal-assets-toggle') return toggle;
    return null;
  },
};
const window = {
  document,
  addEventListener() {},
  clearTimeout() {},
  setTimeout() { return 1; },
  i18n: {
    t(key) { return key; },
    async managementFetch(path) {
      requests.push(path);
      if (path === '/api/personal-assets/sync/availability') {
        return { ok: true, async json() { return { ok: true, availability: { status: 'available', checkedAt: '2026-08-09T10:30:00Z' } }; } };
      }
      return { ok: true, async json() { return { ok: true, profile: { revision: 0, entries: [], suggestions: [] }, sync: { enabled: true, status: 'idle' } }; } };
    },
  },
};

vm.runInNewContext(source, { window, document, FormData: class {} });
window.openPersonalAssets();
await new Promise(resolve => setTimeout(resolve, 0));

assert.deepEqual(requests.slice(0, 2).sort(), [
  '/api/personal-assets',
  '/api/personal-assets/sync/availability',
]);
assert.equal(window.PersonalAssets.state.availability.status, 'available');
assert.match(content.innerHTML, /Available/);

await window.PersonalAssets.loadSnapshot({ quiet: true });
assert.equal(
  requests.filter(path => path === '/api/personal-assets/sync/availability').length,
  1,
  'sync polling must not repeat the availability check',
);

window.PersonalAssets.state.availability.status = 'unavailable';
window.PersonalAssets.render();
assert.match(content.innerHTML, /Unavailable/);
assert.match(content.innerHTML, /data-sync-now disabled/);

window.PersonalAssets.state.sync.status = 'syncing';
window.PersonalAssets.render();
assert.match(content.innerHTML, /Syncing/);
assert.doesNotMatch(content.innerHTML, /personal-assets-sync-status is-unavailable/);

console.log('personal assets availability behavior checks passed');
