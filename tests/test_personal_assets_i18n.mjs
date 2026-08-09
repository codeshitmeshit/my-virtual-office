import assert from 'assert';
import fs from 'fs';
import vm from 'vm';


const source = fs.readFileSync('app/personal-assets.js', 'utf8');
const listeners = {};
const documentListeners = {};
const content = { innerHTML: '', textContent: '' };
const modal = { classList: { add() {}, remove() {} } };
const toggle = { classList: { add() {}, remove() {} }, setAttribute() {}, removeAttribute() {} };
let language = 'en';

const document = {
  activeElement: null,
  addEventListener(type, listener) { documentListeners[type] = listener; },
  getElementById(id) {
    if (id === 'personal-assets-content') return content;
    if (id === 'personalAssetsModal') return modal;
    if (id === 'personal-assets-toggle') return toggle;
    return null;
  },
};
const window = {
  document,
  addEventListener(type, listener) { listeners[type] = listener; },
  clearTimeout() {},
  setTimeout() { return 1; },
  i18n: {
    t(key) {
      const values = {
        en: { personal_assets_overview: 'Profile overview' },
        zh: { personal_assets_overview: '资料总览' },
      };
      return values[language][key] || key;
    },
  },
};

vm.runInNewContext(source, { window, document, FormData: class {} });
window.PersonalAssets.render();
assert.match(content.innerHTML, /Profile overview/);

window.PersonalAssets.state.entries = [
  { id: 'name', category: 'basic-info', label: 'Display name', value: 'cosh', sensitivity: 'standard' },
  { id: 'goal', category: 'office-goals', label: 'Office goal', value: 'Ship autonomously', sensitivity: 'standard' },
];
window.PersonalAssets.render();
assert.match(content.innerHTML, /personal-assets-category-nav/, 'overview should render grouped navigation');
documentListeners.click({
  target: { closest() { return { dataset: { categoryId: 'office-goals' } }; } },
});
assert.equal(window.PersonalAssets.state.selectedCategory, 'office-goals');
assert.match(content.innerHTML, /Ship autonomously/);
assert.doesNotMatch(content.innerHTML, />cosh</);

language = 'zh';
assert.equal(typeof listeners['i18n:changed'], 'function', 'dynamic panel should subscribe to language changes');
listeners['i18n:changed']();
assert.match(content.innerHTML, /资料总览/, 'open dynamic content should rerender in the selected language');

console.log('personal assets i18n behavior checks passed');
