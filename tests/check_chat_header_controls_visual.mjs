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

const css = [
  fs.readFileSync('app/ui-system.css', 'utf8'),
  fs.readFileSync('app/style.css', 'utf8'),
  fs.readFileSync('app/window-controls.css', 'utf8'),
  fs.readFileSync('app/ui-main-shell.css', 'utf8'),
].join('\n');

const screenshotPath = 'openspec/changes/unify-all-frontend-ui/evidence/screenshots/final-chat-header-controls.png';
fs.mkdirSync('openspec/changes/unify-all-frontend-ui/evidence/screenshots', { recursive: true });

let chromiumProcess = null;
let ownedUserDataDir = '';

async function ensureCdp() {
  try {
    await cdpVersion();
    return;
  } catch (_error) {
    const chromium = process.env.CHROMIUM_BIN || spawnSync('bash', ['-lc', 'command -v chromium || command -v chromium-browser || command -v google-chrome || command -v google-chrome-stable'], { encoding: 'utf8' }).stdout.trim();
    assert.ok(chromium, 'Chromium executable is required for chat header visual checks');
    ownedUserDataDir = fs.mkdtempSync('/tmp/vo-chat-header-chrome-');
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
    throw new Error('Timed out starting Chromium for chat header visual checks');
  }
}

const fixtureServer = http.createServer((_request, response) => {
  response.writeHead(200, { 'Content-Type': 'text/html; charset=utf-8' });
  response.end('<!doctype html><html><head><meta charset="utf-8"><title>Chat Header Controls</title></head><body></body></html>');
});
await new Promise((resolve, reject) => {
  fixtureServer.once('error', reject);
  fixtureServer.listen(0, '127.0.0.1', resolve);
});

await ensureCdp();
const fixtureUrl = `http://127.0.0.1:${fixtureServer.address().port}/`;
const page = await createCdpPage(fixtureUrl);
const ws = new WebSocket(page.webSocketDebuggerUrl);
await new Promise((resolve, reject) => {
  const timer = setTimeout(() => reject(new Error('Timed out opening chat-header CDP page')), 8000);
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
    const timer = setTimeout(() => { pending.delete(id); reject(new Error(`Timed out waiting for ${method}`)); }, 20000);
    pending.set(id, { resolve, reject, timer });
  });
}

async function evaluate(expression) {
  const response = await send('Runtime.evaluate', { expression, returnByValue: true });
  if (response.exceptionDetails) throw new Error(response.exceptionDetails.text || JSON.stringify(response.exceptionDetails));
  return response.result?.value;
}

try {
  await send('Page.enable');
  await send('Runtime.enable');
  await send('Emulation.setDeviceMetricsOverride', { width: 760, height: 180, deviceScaleFactor: 1, mobile: false });
  await evaluate(`(() => {
    document.documentElement.innerHTML = ${JSON.stringify(`
      <head><meta charset="utf-8"><title>Chat Header Controls</title></head>
      <body>
        <div class="chat-panel open">
          <div class="chat-header">
            <button class="chat-sessions-toggle" type="button">☰</button>
            <select class="chat-agent-select"><option>⚡ Codex</option></select>
            <span class="chat-status connected">Codex 已就绪</span>
            <span class="chat-feishu-live-status">飞书实时：已连接</span>
            <span class="chat-header-spacer"></span>
            <div class="chat-header-btns" role="toolbar">
              <button class="chat-compact-context" type="button">⇲</button>
              <button class="chat-new-session" type="button">↻</button>
              <button class="chat-move-btn" type="button">⇱</button>
              <button class="chat-close" type="button">×</button>
            </div>
          </div>
        </div>
      </body>
    `)};
    const style = document.createElement('style');
    style.textContent = ${JSON.stringify(css)};
    document.head.appendChild(style);
    const fixtureStyle = document.createElement('style');
    fixtureStyle.textContent = 'html,body{width:760px;height:180px;margin:0;background:#0a0a0f}.chat-panel{position:static!important;display:block!important;width:380px!important;height:auto!important;transform:none!important}.chat-header{box-sizing:border-box;width:380px}';
    document.head.appendChild(fixtureStyle);
    return true;
  })()`);

  const metrics = await evaluate(`(() => {
    const header = document.querySelector('.chat-header').getBoundingClientRect();
    const group = document.querySelector('.chat-header-btns').getBoundingClientRect();
    const controls = [...document.querySelectorAll('.chat-header-btns button')].map((button) => {
      const rect = button.getBoundingClientRect();
      const style = getComputedStyle(button);
      return {
        width: rect.width,
        height: rect.height,
        right: rect.right,
        backgroundColor: style.backgroundColor,
        borderColor: style.borderColor,
      };
    });
    return { header: { right: header.right, scrollWidth: document.querySelector('.chat-header').scrollWidth, clientWidth: document.querySelector('.chat-header').clientWidth }, group: { width: group.width, right: group.right }, controls };
  })()`);

  assert.equal(metrics.controls.length, 4);
  assert.ok(metrics.controls.every((control) => control.width === 32 && control.height === 32));
  assert.ok(metrics.controls.every((control) => control.backgroundColor === 'rgba(0, 0, 0, 0)'));
  assert.ok(metrics.controls.every((control) => control.borderColor === 'rgba(0, 0, 0, 0)'));
  assert.ok(metrics.controls.every((control) => control.right <= metrics.header.right));
  assert.ok(metrics.group.right <= metrics.header.right);
  assert.ok(metrics.header.scrollWidth <= metrics.header.clientWidth);

  const shot = await send('Page.captureScreenshot', { format: 'png', captureBeyondViewport: false });
  fs.writeFileSync(screenshotPath, Buffer.from(shot.data, 'base64'));

  await send('Emulation.setDeviceMetricsOverride', { width: 390, height: 180, deviceScaleFactor: 1, mobile: false });
  await new Promise((resolve) => setTimeout(resolve, 100));
  const narrowMetrics = await evaluate(`(() => {
    const header = document.querySelector('.chat-header').getBoundingClientRect();
    const controls = [...document.querySelectorAll('.chat-header-btns button')].map((button) => {
      const rect = button.getBoundingClientRect();
      return { width: rect.width, height: rect.height, right: rect.right };
    });
    return { viewportWidth: innerWidth, narrowQuery: matchMedia('(max-width: 560px)').matches, headerRight: header.right, scrollWidth: document.querySelector('.chat-header').scrollWidth, clientWidth: document.querySelector('.chat-header').clientWidth, controls };
  })()`);
  console.log(JSON.stringify({ narrowMetrics }));
  assert.ok(narrowMetrics.controls.every((control) => control.width === 28 && control.height === 28));
  assert.ok(narrowMetrics.controls.every((control) => control.right <= narrowMetrics.headerRight));
  assert.ok(narrowMetrics.scrollWidth <= narrowMetrics.clientWidth);
  console.log(JSON.stringify({ screenshot: screenshotPath, desktop: metrics, narrow: narrowMetrics }, null, 2));
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
  if (ownedUserDataDir && fs.existsSync(ownedUserDataDir)) {
    fs.rmSync(ownedUserDataDir, { recursive: true, force: true, maxRetries: 5, retryDelay: 100 });
  }
}
