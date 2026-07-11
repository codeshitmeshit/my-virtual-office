const assert = require('assert');
const fs = require('fs');
const path = require('path');

const root = path.resolve(__dirname, '..');
const source = fs.readFileSync(path.join(root, 'app', 'i18n.js'), 'utf8');
const styles = fs.readFileSync(path.join(root, 'app', 'style.css'), 'utf8');

assert(source.includes("function requestManagementToken()"));
assert(source.includes("input.type = 'password'"));
assert(source.includes("input.autocomplete = 'current-password'"));
assert(source.includes("event.key === 'Escape'"));
assert(source.includes("event.key === 'Enter'"));
assert(source.includes("event.target === modal"));
assert(source.includes("previouslyFocused.focus()"));
assert(source.includes("token = await requestManagementToken()"));
assert(!source.includes("window.prompt(t('management_token_prompt')"));
assert(styles.includes('.management-token-dialog'));
assert(styles.includes('.management-token-input:focus'));

for (const locale of ['en.json', 'zh.json']) {
  const messages = JSON.parse(fs.readFileSync(path.join(root, 'app', 'locales', locale), 'utf8'));
  for (const key of [
    'management_token_title',
    'management_token_placeholder',
    'management_token_cancel',
    'management_token_confirm',
  ]) {
    assert(messages[key], `${locale} missing ${key}`);
  }
}

console.log('management token dialog contract ok');
