import fs from 'node:fs';
import path from 'node:path';

const root = path.resolve(path.dirname(new URL(import.meta.url).pathname), '..');
const testDir = path.join(root, 'tests');
const chromeFiles = fs.readdirSync(testDir)
  .filter((name) => /^chrome_.*\.mjs$/.test(name))
  .sort();

if (!chromeFiles.length) {
  throw new Error('expected chrome CDP scripts');
}

for (const file of chromeFiles) {
  const source = fs.readFileSync(path.join(testDir, file), 'utf8');
  if (!source.includes('cdp-test-utils.mjs')) {
    throw new Error(`${file} should import shared CDP test utilities`);
  }
  if (source.includes('127.0.0.1:9224')) {
    throw new Error(`${file} should not hardcode the CDP endpoint`);
  }
  if (source.includes('192.168.100.3') || source.includes('10.43.55.108') || source.includes('10.110.139.216')) {
    throw new Error(`${file} should not hardcode developer LAN app URLs`);
  }
}

console.log('chrome CDP script static checks passed');
