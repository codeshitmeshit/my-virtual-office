import assert from 'assert';
import fs from 'fs';

const requiredFiles = ['app/settings-modal-ui.js', 'app/settings-save-feedback.js', 'app/settings-save-transport.js', 'app/settings-modal.css', 'app/office-branding.js'];
for (const file of requiredFiles) {
  assert.ok(fs.existsSync(file), `${file} must exist`);
}

const index = fs.readFileSync('app/index.html', 'utf8');
const source = fs.readFileSync('app/settings-modal-ui.js', 'utf8');
const feedbackSource = fs.readFileSync('app/settings-save-feedback.js', 'utf8');
const transportSource = fs.readFileSync('app/settings-save-transport.js', 'utf8');
const brandingSource = fs.readFileSync('app/office-branding.js', 'utf8');
const css = fs.readFileSync('app/settings-modal.css', 'utf8');
const en = JSON.parse(fs.readFileSync('app/locales/en.json', 'utf8'));
const zh = JSON.parse(fs.readFileSync('app/locales/zh.json', 'utf8'));

assert.ok(index.indexOf('style.css') < index.indexOf('settings-modal.css'), 'modal CSS must load after base settings CSS');
assert.ok(index.includes('game.js?v=20260810-settings-save-i18n'), 'save lifecycle wiring must use the current game.js asset version');
assert.ok(index.indexOf('oss-settings.js') < index.indexOf('settings-modal-ui.js'), 'modal UI must mount after the dynamic OSS section');
assert.ok(index.indexOf('settings-modal-ui.js') < index.indexOf('settings-save-feedback.js'), 'save feedback must mount after the modal footer');
assert.ok(index.indexOf('settings-save-feedback.js') < index.indexOf('settings-save-transport.js'), 'save transport must load with the settings feedback modules');
assert.ok(index.indexOf('game.js') < index.indexOf('office-branding.js'), 'office branding must augment the loaded settings runtime');

const localeKeys = [
  'settings_modal_connections_agents',
  'settings_modal_office',
  'settings_modal_weather',
  'settings_modal_display',
  'settings_modal_tools_browser',
  'settings_modal_notifications',
  'settings_modal_storage',
  'settings_modal_advanced',
  'settings_modal_subtitle',
  'settings_save_saving',
  'settings_save_success',
  'settings_save_success_refresh',
  'settings_save_failed',
  'office_icon',
  'office_icon_remove',
  'office_icon_hint',
];
for (const key of localeKeys) {
  assert.ok(Object.hasOwn(en, key), `en.json missing ${key}`);
  assert.ok(Object.hasOwn(zh, key), `zh.json missing ${key}`);
}

const stableSettingIds = [
  'main-menu-panel', 'mm-oc-path', 'mm-hermes-enable', 'mm-codex-enable',
  'mm-office-name', 'mm-office-icon-file', 'mm-office-icon-preview', 'mm-office-icon-clear',
  'mm-show-bubbles', 'mm-show-weather', 'mm-apiusage-enable',
  'mm-pcmetrics-enable', 'mm-browser-enable', 'mm-feishu-enable', 'mm-feishu-chat-enable', 'mm-import-file',
];
for (const id of stableSettingIds) {
  assert.ok(index.includes(`id="${id}"`), `existing setting ID ${id} must remain in index.html`);
}

for (const forbidden of ['/setup/save', 'localStorage', 'mmSaveSettings =', 'mmTestConnection =']) {
  assert.ok(!source.includes(forbidden), `presentation module must not own ${forbidden}`);
}
for (const forbidden of ['/setup/save', 'localStorage', 'managementFetch(', 'fetch(']) {
  assert.ok(!feedbackSource.includes(forbidden), `save feedback module must not own ${forbidden}`);
}
assert.ok(!transportSource.includes('localStorage'), 'save transport must not persist settings locally');
assert.ok(!fs.readFileSync('app/game.js', 'utf8').includes('Settings saved! Hard refresh'), 'save notification must not hardcode English copy');
assert.ok(!fs.readFileSync('app/main-menu-settings.js', 'utf8').includes('Settings saved! Hard refresh'), 'legacy settings entry must use the same localized save copy');
assert.ok(brandingSource.includes("fetch('/vo-config')"), 'office branding should load the saved server configuration');
assert.ok(brandingSource.includes("querySelectorAll('link[rel~=\"icon\"]')"), 'office branding should update favicon links');
assert.ok(brandingSource.includes('buildOfficePayload'), 'office branding should expose the settings payload boundary');

assert.ok(source.includes("getElementById('main-menu-panel')"), 'module should preserve the current visibility root');
assert.ok(source.includes("querySelector('.main-menu-body')"), 'module should preserve the OSS body contract');
assert.ok(css.includes('.main-menu-panel.settings-modal-mounted'), 'all enhancement styles need the mounted gate');
assert.ok(css.includes('.settings-modal-dialog'));
assert.ok(css.includes('.settings-modal-layout'));
assert.ok(css.includes('.settings-modal-nav'));
assert.ok(css.includes('.settings-modal-content'));
assert.ok(css.includes('.settings-modal-footer'));
assert.ok(
  css.includes('grid-template-columns: 204px minmax(0, 1fr)'),
  'the overall desktop layout should keep one navigation column plus one content region',
);
assert.ok(
  css.includes('column-count: 2'),
  'the content region should form two continuous internal columns',
);
assert.ok(css.includes('break-inside: avoid'), 'a settings card must not split across internal columns');
assert.ok(
  css.includes('.settings-modal-category-panel[data-settings-category="weather"]'),
  'the Weather category should define its own single-column layout without affecting other categories',
);
assert.ok(!css.includes('repeat(3, minmax(0, 1fr))'), 'the content region must not create a fourth overall column');
assert.ok(index.includes('data-settings-card="feishu-notifications"'), 'Feishu notifications must own a dedicated settings card');
assert.ok(index.includes('data-settings-card="feishu-chat-app"'), 'Feishu chat must own a dedicated settings card');
assert.ok(index.includes('data-settings-card="weather-location"'), 'Weather location must own a dedicated settings card');
assert.ok(index.includes('data-settings-card="weather-provider"'), 'Weather provider must own a dedicated settings card');
assert.ok(
  source.includes("{ id: 'office', labelKey: 'settings_modal_office', selectors: ['#mm-office-name', '#mm-weather-provider'] }"),
  'weather provider must be classified under Office with the office identity card',
);
assert.ok(
  source.includes("{ id: 'weather', labelKey: 'settings_modal_weather', selectors: ['#mm-show-weather'] }"),
  'weather location and display controls must remain in the Weather category',
);
assert.ok(
  source.includes("selectors: ['#mm-feishu-enable', '#mm-feishu-chat-enable']"),
  'both independent Feishu cards must remain in the notifications category',
);
assert.ok(!index.includes('height:1px;background:#2b2b3f;margin:12px 0;'), 'the old in-card divider must be removed');
const sectionTitleRule = css.match(/\.main-menu-panel\.settings-modal-mounted \.mm-section-title\s*\{([^}]*)\}/);
assert.ok(sectionTitleRule, 'scoped settings title rule must exist');
assert.ok(/font-size:\s*calc\(12px\s*\*\s*var\(--vo-font-scale,\s*1\)\)\s*!important/.test(sectionTitleRule[1]), 'settings card titles should enforce the scalable 12px component-title level');
assert.ok(/line-height:\s*calc\(16px\s*\*\s*var\(--vo-font-scale,\s*1\)\)/.test(sectionTitleRule[1]), 'settings card titles should use the scalable 12/16 type scale');
const helpRule = css.match(/\.main-menu-panel\.settings-modal-mounted \.mm-help\s*\{([^}]*)\}/);
assert.ok(helpRule, 'scoped settings help rule must exist');
assert.ok(/font-size:\s*calc\(9px\s*\*\s*var\(--vo-font-scale,\s*1\)\)\s*!important/.test(helpRule[1]), 'settings help copy should enforce the scalable 9px metadata level');
assert.ok(/line-height:\s*calc\(14px\s*\*\s*var\(--vo-font-scale,\s*1\)\)/.test(helpRule[1]), 'settings help copy should use the scalable 9/14 type scale');
assert.ok(css.includes('@media (max-width:'), 'narrow desktop layout must be explicit');
assert.ok(!/(^|[},\s])\.modal\s*\{/m.test(css), 'settings styles must not override a global modal selector');

console.log('settings modal wiring contract ok');
