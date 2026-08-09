import assert from 'assert';
import fs from 'fs';


const index = fs.readFileSync('app/index.html', 'utf8');
const js = fs.readFileSync('app/personal-assets.js', 'utf8');
const css = fs.readFileSync('app/personal-assets.css', 'utf8');
const zh = JSON.parse(fs.readFileSync('app/locales/zh.json', 'utf8'));
const en = JSON.parse(fs.readFileSync('app/locales/en.json', 'utf8'));

assert.ok(index.includes('id="personal-assets-toggle"'), 'toolbar should include personal assets');
assert.ok(index.includes('onclick="openPersonalAssets()"'), 'toolbar entry should open the modal');
assert.ok(index.includes('id="personalAssetsModal"'), 'index should include the modal host');
assert.ok(index.includes('id="personal-assets-content"'), 'modal should include the focused content host');
assert.ok(index.includes('personal-assets.css'), 'index should load scoped styles');
assert.ok(index.includes('personal-assets.js'), 'index should load focused behavior');

for (const state of ['overview', 'editor', 'suggestions']) {
  assert.ok(js.includes(`'${state}'`) || js.includes(`"${state}"`), `UI should include ${state} state`);
}
assert.ok(!/view\s*[:=]\s*['"]onboarding/.test(js), 'UI must not have an onboarding view');
assert.ok(!/view\s*[:=]\s*['"]authorization/.test(js), 'UI must not have an authorization view');
assert.ok(js.includes('i18n.managementFetch'), 'UI should use the existing management fetch boundary');
assert.ok(js.includes('VODialogs.showConfirm'), 'delete should use the existing confirmation dialog');
assert.ok(js.includes('textContent'), 'dynamic form feedback should use safe DOM text');
assert.ok(js.includes('aria-current'), 'toolbar active state should be accessible');
assert.ok(js.includes('returnFocus'), 'modal should restore focus');
assert.ok(js.includes('/api/personal-assets/sync/preferences'), 'panel should own the auto-sync preference');
assert.ok(js.includes('/api/personal-assets/sync/now'), 'panel should expose background sync and retry');
assert.ok(js.includes('/api/personal-assets/sync/conflict'), 'panel should expose explicit conflict resolution');
assert.ok(js.includes('/api/personal-assets/sync/availability'), 'opening the panel should lazily check OSS availability');
assert.ok(js.includes('syncPollTimer'), 'active synchronization should poll only while the panel is open');
assert.ok(js.includes('data-sync-resolution="local"'), 'conflict UI should support keeping local data');
assert.ok(js.includes('data-sync-resolution="remote"'), 'conflict UI should support adopting cloud data');
assert.ok(!/oss_(endpoint|bucket|access_key)/.test(js), 'Personal Assets must not render OSS configuration fields');
assert.ok(js.includes('personal-assets-category-nav'), 'overview should separate profile types into category navigation');
assert.ok(js.includes('data-category-id'), 'category navigation should expose stable interaction targets');
assert.ok(js.includes('personal-assets-field-guide'), 'overview should explain field descriptions versus saved values');
assert.ok(js.includes('personal-assets-field-description'), 'each row should render a read-only field description');
assert.ok(js.includes('personal-assets-saved-value'), 'each row should render saved content in a distinct surface');
assert.ok(js.includes('personal-assets-edit-action'), 'each row should keep one stable edit affordance');
assert.ok(
  js.indexOf('personal-assets-overview-layout') < js.lastIndexOf('renderSyncPanel()'),
  'weak OSS synchronization should be rendered after the profile workspace',
);

assert.ok(css.includes('.personal-assets-'), 'styles should be scoped');
assert.ok(css.includes('@media (max-width:'), 'styles should include narrow viewport behavior');
assert.ok(!css.includes('.archive-room-'), 'styles must not override archive room');
assert.ok(!css.includes('.human-decision-'), 'styles must not override human decisions');
assert.match(
  css,
  /\.personal-assets-modal-content\s*\{[^}]*font-family:\s*var\(--ui-font-family/s,
  'Personal Assets should use the canonical readable UI font',
);
assert.match(
  css,
  /\.personal-assets-content\s*\{[^}]*font-size:\s*var\(--ui-font-size-body\)[^}]*line-height:\s*1\.55/s,
  'Personal Assets should use the canonical body type scale',
);

const required = [
  'personal_assets', 'personal_assets_title', 'personal_assets_description',
  'personal_assets_add', 'personal_assets_suggestions', 'personal_assets_empty',
  'personal_assets_sensitive', 'personal_assets_standard', 'personal_assets_save',
  'personal_assets_delete', 'personal_assets_accept', 'personal_assets_reject',
  'personal_assets_auto_sync', 'personal_assets_sync_now', 'personal_assets_sync_retry',
  'personal_assets_keep_local', 'personal_assets_use_cloud', 'personal_assets_sync_weak_hint',
  'personal_assets_oss_checking', 'personal_assets_oss_available',
  'personal_assets_oss_unconfigured', 'personal_assets_oss_unavailable',
  'personal_assets_all', 'personal_assets_basic_info', 'personal_assets_career_direction',
  'personal_assets_interests', 'personal_assets_chat_preferences', 'personal_assets_office_goals',
  'personal_assets_other', 'personal_assets_field_and_purpose', 'personal_assets_saved_content',
  'personal_assets_edit_action', 'personal_assets_sensitive_decision_hint',
];
for (const key of required) {
  assert.ok(Object.hasOwn(zh, key), `Chinese locale should include ${key}`);
  assert.ok(Object.hasOwn(en, key), `English locale should include ${key}`);
}

const runtimeKeys = [...js.matchAll(/tr\('([^']+)'/g)].map(match => match[1]);
for (const key of new Set(runtimeKeys)) {
  assert.ok(Object.hasOwn(zh, key), `Chinese locale should cover runtime key ${key}`);
  assert.ok(Object.hasOwn(en, key), `English locale should cover runtime key ${key}`);
}

console.log('personal assets UI checks passed');
