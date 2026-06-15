const crypto = require('crypto');
const fs = require('fs');
const path = require('path');

const root = path.resolve(__dirname, '..');
const fontDir = path.join(root, 'app', 'assets', 'fonts', 'fusion-pixel-font');
const fontFile = path.join(fontDir, 'fusion-pixel-12px-proportional-zh_hans.otf.woff2');
const expectedSha256 = 'd44f6262ac033348d271e95af84beb0b2de56cf981bbf1bba29a34c65b389613';

for (const filename of ['OFL.txt', 'ark-pixel.txt', 'cubic-11.txt', 'galmuri.txt', 'SOURCE.md']) {
  const file = path.join(fontDir, filename);
  if (!fs.existsSync(file) || fs.statSync(file).size === 0) {
    throw new Error(`Missing Fusion Pixel Font license/source file: ${filename}`);
  }
}

if (!fs.existsSync(fontFile)) {
  throw new Error(`Missing Fusion Pixel Font asset: ${path.relative(root, fontFile)}`);
}

const font = fs.readFileSync(fontFile);
const sha256 = crypto.createHash('sha256').update(font).digest('hex');
if (sha256 !== expectedSha256) {
  throw new Error(`Unexpected Fusion Pixel Font SHA-256: ${sha256}`);
}

const css = fs.readFileSync(path.join(root, 'app', 'fonts.css'), 'utf8');
for (const required of [
  "font-family: 'Fusion Pixel 12px Proportional SC'",
  'fusion-pixel-12px-proportional-zh_hans.otf.woff2',
  'font-display: swap',
  'html[lang="zh"]',
  '--vo-technical-font'
]) {
  if (!css.includes(required)) throw new Error(`fonts.css is missing: ${required}`);
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

console.log(`font assets ok: ${font.length} bytes, sha256 ${sha256}`);
