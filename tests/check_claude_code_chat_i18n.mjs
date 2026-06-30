import assert from 'node:assert/strict';
import fs from 'node:fs';

const chatJs = fs.readFileSync('app/chat.js', 'utf8');
const en = JSON.parse(fs.readFileSync('app/locales/en.json', 'utf8'));
const zh = JSON.parse(fs.readFileSync('app/locales/zh.json', 'utf8'));

const requiredKeys = [
  'claude_code_error',
  'claude_code_ready',
  'claude_code_send_failed',
  'claude_code_working',
  'new_claude_code_session',
];

for (const key of requiredKeys) {
  assert.ok(en[key], `missing en locale key: ${key}`);
  assert.ok(zh[key], `missing zh locale key: ${key}`);
  assert.ok(chatJs.includes(`_ct('${key}')`), `chat.js does not use locale key: ${key}`);
}

assert.ok(!chatJs.includes("'Claude Code working...'"), 'Claude Code working status should use i18n');
assert.ok(!chatJs.includes("'Claude Code ready'"), 'Claude Code ready status should use i18n');
assert.ok(!chatJs.includes("'Claude Code error'"), 'Claude Code error status should use i18n');
assert.ok(!chatJs.includes("'Claude Code send failed'"), 'Claude Code send failure should use i18n');
assert.ok(!chatJs.includes("'New Claude Code session started'"), 'Claude Code new-session text should use i18n');

console.log('Claude Code chat i18n check passed');
