import assert from 'node:assert/strict';
import fs from 'node:fs';
import { createRequire } from 'node:module';


const require = createRequire(import.meta.url);
const source = fs.readFileSync('app/human-resources.js', 'utf8');
const html = fs.readFileSync('app/index.html', 'utf8');
const en = JSON.parse(fs.readFileSync('app/locales/en.json', 'utf8'));
const zh = JSON.parse(fs.readFileSync('app/locales/zh.json', 'utf8'));
const hr = require('../app/human-resources.js');

const keys = new Set();
for (const match of source.matchAll(/\btr\('([^']+)'/g)) {
  if (!match[1].endsWith('_')) keys.add(match[1]);
}
const shell = html.slice(html.indexOf('<!-- Human Resources Modal -->'), html.indexOf('<!-- SMS Panel -->'));
for (const match of shell.matchAll(/data-i18n(?:-title|-aria-label)?="([^"]+)"/g)) keys.add(match[1]);
keys.add('human_resources');
keys.add('hr_action_activity');
for (const action of hr.helpers.actionNames) keys.add(`hr_action_${action}`);
for (const state of hr.helpers.semanticStates) keys.add(`hr_state_${state}`);
for (const code of hr.helpers.errorCodes) keys.add(`hr_error_${code.replace(/^hr_/, '')}`);

for (const key of keys) {
  assert.ok(Object.hasOwn(en, key), `missing English HR locale key: ${key}`);
  assert.ok(Object.hasOwn(zh, key), `missing Chinese HR locale key: ${key}`);
  assert.ok(String(en[key]).trim(), `empty English HR locale value: ${key}`);
  assert.ok(String(zh[key]).trim(), `empty Chinese HR locale value: ${key}`);
}

for (const required of [
  "event.key === 'Escape'",
  "event.key !== 'Tab'",
  'returnFocus',
  'aria-busy',
  'focusableElements',
  "addEventListener('keydown'",
]) {
  assert.ok(source.includes(required), `missing HR accessibility behavior: ${required}`);
}
for (const required of [
  'role="dialog"',
  'aria-modal="true"',
  'aria-labelledby="human-resources-title"',
  'id="human-resources-close"',
]) {
  assert.ok(shell.includes(required), `missing HR modal accessibility marker: ${required}`);
}

assert.equal(hr.helpers.semanticLabel('normalization_failed'), 'Normalization Failed');

console.log(`Human Resources i18n/accessibility checks passed (${keys.size} locale keys)`);
