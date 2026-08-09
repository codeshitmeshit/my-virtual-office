const crypto = require('crypto');
const fs = require('fs');
const path = require('path');

const root = path.resolve(__dirname, '..');
const fontDir = path.join(root, 'app', 'assets', 'fonts', 'noto-sans-sc');
const fontFile = path.join(fontDir, 'NotoSansSC-VF.woff2');
const expectedSha256 = '38e67873e8dd3ba0b7329399d850576439e59779a80999868a227beb7c7b760e';

for (const filename of ['LICENSE', 'SOURCE.md']) {
  const file = path.join(fontDir, filename);
  if (!fs.existsSync(file) || fs.statSync(file).size === 0) {
    throw new Error(`Missing Noto Sans SC license/source file: ${filename}`);
  }
}

if (!fs.existsSync(fontFile)) {
  throw new Error(`Missing Noto Sans SC asset: ${path.relative(root, fontFile)}`);
}

const font = fs.readFileSync(fontFile);
const sha256 = crypto.createHash('sha256').update(font).digest('hex');
if (sha256 !== expectedSha256) {
  throw new Error(`Unexpected Noto Sans SC SHA-256: ${sha256}`);
}

const css = fs.readFileSync(path.join(root, 'app', 'fonts.css'), 'utf8');
const systemCss = fs.readFileSync(path.join(root, 'app', 'ui-system.css'), 'utf8');
for (const required of [
  "font-family: 'VO Sans'",
  'NotoSansSC-VF.woff2',
  'font-weight: 100 900',
  'font-display: swap',
]) {
  if (!css.includes(required)) throw new Error(`fonts.css is missing: ${required}`);
}

for (const required of [
  '--ui-font-family:',
  '--vo-pixel-ui-font:',
  '--vo-technical-font: var(--ui-font-family)',
  '--vo-pixel-ui-font: var(--ui-font-family)',
  '.vo-pixel-ui',
  '[data-ui-font="pixel"]',
  '[data-ui-font="technical"]'
]) {
  if (!systemCss.includes(required)) throw new Error(`ui-system.css is missing font boundary: ${required}`);
}
if (/:root\s*\{/.test(css)) {
  throw new Error('fonts.css must not own a competing :root token block');
}

const pages = [
  ['app/index.html', /href="fonts\.css\?v=[^"]+"/],
  ['app/setup.html', /href="fonts\.css\?v=[^"]+"/],
  ['app/models.html', /href="fonts\.css\?v=[^"]+"/],
  ['app/cron.html', /href="fonts\.css\?v=[^"]+"/],
  ['website/index.html', /href="\/fonts\.css\?v=[^"]+"/]
];
for (const [filename, referencePattern] of pages) {
  const source = fs.readFileSync(path.join(root, filename), 'utf8');
  if (!referencePattern.test(source)) {
    throw new Error(`${filename} does not reference the shared font stylesheet`);
  }
}

const main = fs.readFileSync(path.join(root, 'app', 'index.html'), 'utf8');
if (main.indexOf('ui-system.css') > main.indexOf('style.css')) {
  throw new Error('app/index.html must load ui-system.css before style.css');
}

console.log(`font assets ok: ${font.length} bytes, sha256 ${sha256}`);
