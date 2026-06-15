const fs = require('fs');
const path = require('path');

const root = path.resolve(__dirname, '..');
const localeDir = path.join(root, 'app', 'locales');
const en = JSON.parse(fs.readFileSync(path.join(localeDir, 'en.json'), 'utf8'));
const zh = JSON.parse(fs.readFileSync(path.join(localeDir, 'zh.json'), 'utf8'));

const enKeys = Object.keys(en).sort();
const zhKeys = Object.keys(zh).sort();
if (JSON.stringify(enKeys) !== JSON.stringify(zhKeys)) {
  const missingZh = enKeys.filter((key) => !(key in zh));
  const missingEn = zhKeys.filter((key) => !(key in en));
  throw new Error(`Locale keys differ. Missing zh: ${missingZh.join(', ')}; missing en: ${missingEn.join(', ')}`);
}

const sourceFiles = [];
function walk(dir) {
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    const file = path.join(dir, entry.name);
    if (entry.isDirectory()) {
      if (entry.name !== 'locales') walk(file);
    } else if (/\.(html|js)$/.test(entry.name) && entry.name !== 'marked.min.js') {
      sourceFiles.push(file);
    }
  }
}
walk(path.join(root, 'app'));
walk(path.join(root, 'website'));

const referenced = new Map();
const patterns = [
  /data-i18n(?:-html|-title|-placeholder)?\s*=\s*["']([^"']+)["']/g,
  /\bi18n\.t\(\s*["']([^"']+)["']/g,
  /\b_t\(\s*["']([^"']+)["']/g
];

for (const file of sourceFiles) {
  const source = fs.readFileSync(file, 'utf8');
  for (const pattern of patterns) {
    let match;
    while ((match = pattern.exec(source))) {
      const key = match[1];
      if (key === 'key' || key.endsWith('_')) continue;
      if (!referenced.has(key)) referenced.set(key, []);
      referenced.get(key).push(path.relative(root, file));
    }
  }
}

const missing = [...referenced.keys()].filter((key) => !(key in en));
if (missing.length) {
  const details = missing.map((key) => `${key} (${[...new Set(referenced.get(key))].join(', ')})`);
  throw new Error(`Referenced locale keys are missing: ${details.join('; ')}`);
}

console.log(`i18n integrity ok: ${enKeys.length} keys, ${referenced.size} static references`);
