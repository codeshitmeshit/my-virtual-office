#!/usr/bin/env node
import assert from 'node:assert/strict';
import { spawn, spawnSync } from 'node:child_process';
import fs from 'node:fs';
import http from 'node:http';
import { closeCdpPage, createCdpPage, cdpVersion } from './cdp-test-utils.mjs';

if (typeof WebSocket === 'undefined') {
  const child = spawnSync(process.execPath, ['--experimental-websocket', ...process.argv.slice(1)], {
    env: process.env,
    stdio: 'inherit',
  });
  process.exit(child.status ?? 1);
}

const screenshotPath = 'openspec/changes/unify-all-frontend-ui/evidence/screenshots/final-unified-product-font.png';
fs.mkdirSync('openspec/changes/unify-all-frontend-ui/evidence/screenshots', { recursive: true });

let chromiumProcess = null;
let ownedUserDataDir = '';

async function ensureCdp() {
  try {
    await cdpVersion();
    return;
  } catch (_error) {
    const chromium = process.env.CHROMIUM_BIN || spawnSync('bash', ['-lc', 'command -v chromium || command -v chromium-browser || command -v google-chrome || command -v google-chrome-stable'], { encoding: 'utf8' }).stdout.trim();
    assert.ok(chromium, 'Chromium executable is required for unified-font visual checks');
    ownedUserDataDir = fs.mkdtempSync('/tmp/vo-unified-font-chrome-');
    chromiumProcess = spawn(chromium, [
      '--headless=new',
      '--remote-debugging-address=127.0.0.1',
      '--remote-debugging-port=9224',
      `--user-data-dir=${ownedUserDataDir}`,
      '--no-sandbox',
      '--disable-gpu',
      'about:blank',
    ], { stdio: 'ignore' });
    const started = Date.now();
    while (Date.now() - started < 8000) {
      try {
        await cdpVersion();
        return;
      } catch (_ignored) {
        await new Promise((resolve) => setTimeout(resolve, 120));
      }
    }
    throw new Error('Timed out starting Chromium for unified-font visual checks');
  }
}

const files = new Map([
  ['/fonts.css', ['text/css; charset=utf-8', 'app/fonts.css']],
  ['/ui-system.css', ['text/css; charset=utf-8', 'app/ui-system.css']],
  ['/assets/fonts/noto-sans-sc/NotoSansSC-VF.woff2', ['font/woff2', 'app/assets/fonts/noto-sans-sc/NotoSansSC-VF.woff2']],
]);
const requests = [];
const fixtureServer = http.createServer((request, response) => {
  const pathname = new URL(request.url, 'http://127.0.0.1').pathname;
  requests.push(pathname);
  if (files.has(pathname)) {
    const [contentType, filename] = files.get(pathname);
    response.writeHead(200, { 'Content-Type': contentType, 'Cache-Control': 'no-store' });
    response.end(fs.readFileSync(filename));
    return;
  }
  response.writeHead(200, { 'Content-Type': 'text/html; charset=utf-8' });
  response.end(`<!doctype html><html lang="zh"><head><meta charset="utf-8"><link rel="stylesheet" href="/fonts.css"><link rel="stylesheet" href="/ui-system.css"><style>
    body{margin:0;min-height:100vh;display:grid;place-items:center;background:var(--ui-canvas)}
    main{box-sizing:border-box;width:min(720px,calc(100vw - 32px));padding:28px;border:1px solid var(--ui-border-strong);border-radius:12px;background:var(--ui-surface)}
    h1{margin:0 0 14px;font-size:24px;line-height:32px}p{margin:8px 0;font-size:16px;line-height:24px;color:var(--ui-text-muted)}
    .sample{color:var(--ui-info);font-size:18px;font-weight:600}.technical{font-family:var(--vo-technical-font)}
  </style></head><body><main><h1>统一字体 · Unified Typography</h1><p class="sample">Agent Management · 智能体管理 · Save 保存 · 1234567890</p><p class="technical">/workspace/project · API Token · 技术字段</p></main></body></html>`);
});
await new Promise((resolve, reject) => {
  fixtureServer.once('error', reject);
  fixtureServer.listen(0, '127.0.0.1', resolve);
});

await ensureCdp();
const page = await createCdpPage(`http://127.0.0.1:${fixtureServer.address().port}/`);
const ws = new WebSocket(page.webSocketDebuggerUrl);
await new Promise((resolve, reject) => {
  const timer = setTimeout(() => reject(new Error('Timed out opening unified-font CDP page')), 8000);
  ws.addEventListener('open', () => { clearTimeout(timer); resolve(); }, { once: true });
  ws.addEventListener('error', reject, { once: true });
});

let sequence = 0;
const pending = new Map();
ws.addEventListener('message', (event) => {
  const message = JSON.parse(event.data.toString());
  if (!message.id || !pending.has(message.id)) return;
  const waiter = pending.get(message.id);
  pending.delete(message.id);
  clearTimeout(waiter.timer);
  if (message.error) waiter.reject(new Error(JSON.stringify(message.error)));
  else waiter.resolve(message.result || {});
});

function send(method, params = {}) {
  const id = ++sequence;
  ws.send(JSON.stringify({ id, method, params }));
  return new Promise((resolve, reject) => {
    const timer = setTimeout(() => { pending.delete(id); reject(new Error(`Timed out waiting for ${method}`)); }, 30000);
    pending.set(id, { resolve, reject, timer });
  });
}

async function evaluate(expression) {
  const response = await send('Runtime.evaluate', { expression, returnByValue: true, awaitPromise: true });
  if (response.exceptionDetails) throw new Error(response.exceptionDetails.text || JSON.stringify(response.exceptionDetails));
  return response.result?.value;
}

try {
  await send('Page.enable');
  await send('Runtime.enable');
  await send('Emulation.setDeviceMetricsOverride', { width: 800, height: 360, deviceScaleFactor: 1, mobile: false });
  const metrics = await evaluate(`(async () => {
    await document.fonts.load('400 16px "VO Sans"', '中文 Agent 123');
    await document.fonts.load('600 18px "VO Sans"', '智能体 Save 456');
    await document.fonts.ready;
    const sample = getComputedStyle(document.querySelector('.sample'));
    const technical = getComputedStyle(document.querySelector('.technical'));
    return {
      loaded: document.fonts.check('400 16px "VO Sans"', '中文 Agent 123'),
      sampleFamily: sample.fontFamily,
      sampleWeight: sample.fontWeight,
      technicalFamily: technical.fontFamily,
      overflow: document.documentElement.scrollWidth > document.documentElement.clientWidth,
    };
  })()`);
  assert.equal(metrics.loaded, true);
  assert.match(metrics.sampleFamily, /VO Sans/);
  assert.match(metrics.technicalFamily, /VO Sans/);
  assert.equal(metrics.sampleWeight, '600');
  assert.equal(metrics.overflow, false);
  assert.ok(requests.includes('/assets/fonts/noto-sans-sc/NotoSansSC-VF.woff2'));

  const shot = await send('Page.captureScreenshot', { format: 'png', captureBeyondViewport: false });
  fs.writeFileSync(screenshotPath, Buffer.from(shot.data, 'base64'));

  await send('Emulation.setDeviceMetricsOverride', { width: 390, height: 360, deviceScaleFactor: 1, mobile: false });
  await new Promise((resolve) => setTimeout(resolve, 100));
  const narrow = await evaluate(`({ overflow: document.documentElement.scrollWidth > document.documentElement.clientWidth, width: document.querySelector('main').getBoundingClientRect().width })`);
  assert.equal(narrow.overflow, false);
  assert.ok(narrow.width <= 358);
  console.log(JSON.stringify({ screenshot: screenshotPath, metrics, narrow }, null, 2));
} finally {
  try { ws.close(); } catch (_error) {}
  await closeCdpPage(page.id).catch(() => {});
  await new Promise((resolve) => fixtureServer.close(resolve));
  if (chromiumProcess) {
    chromiumProcess.kill('SIGTERM');
    if (chromiumProcess.exitCode === null && chromiumProcess.signalCode === null) {
      await Promise.race([
        new Promise((resolve) => chromiumProcess.once('exit', resolve)),
        new Promise((resolve) => setTimeout(resolve, 2000)),
      ]);
    }
  }
  if (ownedUserDataDir && fs.existsSync(ownedUserDataDir)) fs.rmSync(ownedUserDataDir, { recursive: true, force: true, maxRetries: 5, retryDelay: 100 });
}
