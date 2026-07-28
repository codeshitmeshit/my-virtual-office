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

const evidenceDir = 'openspec/changes/add-project-task-orchestration/evidence/figma';
const screenshotPath = `${evidenceDir}/candidate-8.8-orchestration-overlay.png`;
const referenceOverlayPath = `${evidenceDir}/figma-147-2-reference.png`;
const referenceModalPath = `${evidenceDir}/figma-148-3-modal-reference.png`;
fs.mkdirSync(evidenceDir, { recursive: true });

function pngSize(path) {
  const data = fs.readFileSync(path);
  assert.equal(data.toString('ascii', 1, 4), 'PNG', `${path} must be a PNG`);
  return { width: data.readUInt32BE(16), height: data.readUInt32BE(20) };
}

let chromiumProcess = null;
let ownedUserDataDir = '';

function cdpEndpoint() {
  const endpoint = new URL(process.env.VO_CDP_URL || 'http://127.0.0.1:9224');
  return {
    address: endpoint.hostname || '127.0.0.1',
    port: endpoint.port || '9224',
  };
}

async function ensureCdp() {
  try {
    await cdpVersion();
    return;
  } catch (_error) {
    const chromium = process.env.CHROMIUM_BIN || spawnSync('bash', ['-lc', 'command -v chromium || command -v chromium-browser || command -v google-chrome || command -v google-chrome-stable'], { encoding: 'utf8' }).stdout.trim();
    assert.ok(chromium, 'Chromium executable is required for visual snapshot tests');
    const endpoint = cdpEndpoint();
    ownedUserDataDir = fs.mkdtempSync('/tmp/vo-orchestration-chrome-');
    chromiumProcess = spawn(chromium, [
      '--headless=new',
      `--remote-debugging-address=${endpoint.address}`,
      `--remote-debugging-port=${endpoint.port}`,
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
    throw new Error('Timed out starting local Chromium CDP on port 9224');
  }
}

const css = [
  fs.readFileSync('app/fonts.css', 'utf8'),
  fs.readFileSync('app/project-orchestration.css', 'utf8'),
].join('\n');
const apiJs = fs.readFileSync('app/project-orchestration-api.js', 'utf8');
const modalJs = fs.readFileSync('app/project-orchestration.js', 'utf8');
const project = {
  id: 'visual-project',
  title: '项目执行看板',
  orchestration: { revision: 7, state: 'draft', currentStage: null },
  tasks: [
    { id: 'research', title: '需求研究', executionStage: 1, executionState: 'executing', priority: 'high', assignee: 'PM' },
    { id: 'draft', title: '方案草稿', executionStage: 2, priority: 'medium', assignee: 'AI-1' },
    { id: 'review', title: '技术审查', executionStage: 2, executionState: 'reviewing', priority: 'critical', assignee: 'Reviewer' },
    { id: 'impl-a', title: '前端实现', executionStage: 3, priority: 'high', assignee: 'AI-2' },
    { id: 'impl-b', title: '后端实现', executionStage: 3, priority: 'high', assignee: 'AI-3' },
    { id: 'impl-c', title: '测试补齐', executionStage: 3, priority: 'medium', assignee: 'QA' },
    { id: 'accept', title: '人工验收', executionStage: 4, priority: 'medium', assignee: 'User' },
    { id: 'deploy', title: '发布准备', executionStage: 5, priority: 'low', assignee: 'Ops' },
    { id: 'report', title: '结果汇报', executionStage: 5, executionState: 'reviewing', priority: 'medium', assignee: 'PM' },
  ],
};

const fixtureServer = http.createServer((_request, response) => {
  response.writeHead(200, { 'Content-Type': 'text/html; charset=utf-8' });
  response.end('<!doctype html><html><head><meta charset="utf-8"><title>Project Orchestration Visual Fixture</title></head><body></body></html>');
});

await new Promise((resolve, reject) => {
  fixtureServer.once('error', reject);
  fixtureServer.listen(0, '127.0.0.1', resolve);
});

const fixtureUrl = `http://127.0.0.1:${fixtureServer.address().port}/`;
await ensureCdp();
const page = await createCdpPage(fixtureUrl);
const ws = new WebSocket(page.webSocketDebuggerUrl);
await new Promise((resolve, reject) => {
  const timer = setTimeout(() => reject(new Error(`Timed out opening CDP WebSocket for ${page.webSocketDebuggerUrl}`)), 8000);
  ws.addEventListener('open', () => {
    clearTimeout(timer);
    resolve();
  }, { once: true });
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

function send(method, params = {}, timeoutMs = 20000) {
  const id = ++sequence;
  ws.send(JSON.stringify({ id, method, params }));
  return new Promise((resolve, reject) => {
    const timer = setTimeout(() => {
      pending.delete(id);
      reject(new Error(`Timed out waiting for ${method}`));
    }, timeoutMs);
    pending.set(id, { resolve, reject, timer });
  });
}

async function evaluate(expression) {
  const response = await send('Runtime.evaluate', {
    expression,
    awaitPromise: true,
    returnByValue: true,
  });
  if (response.exceptionDetails) {
    throw new Error(response.exceptionDetails.text || JSON.stringify(response.exceptionDetails));
  }
  return response.result?.value;
}

function near(actual, expected, tolerance, label) {
  assert.ok(Math.abs(actual - expected) <= tolerance, `${label}: expected ${expected}, got ${actual}`);
}

try {
  await send('Page.enable');
  await send('Runtime.enable');
  await send('Emulation.setDeviceMetricsOverride', {
    width: 1512,
    height: 742,
    deviceScaleFactor: 1,
    mobile: false,
  });
  await evaluate(`(() => {
    document.documentElement.innerHTML = ${JSON.stringify(`
      <head><meta charset="utf-8"><title>Project Orchestration Visual Fixture</title></head>
      <body>
        <main class="fixture-project-shell"></main>
      </body>
    `)};
    const shellStyle = document.createElement('style');
    shellStyle.textContent = ${JSON.stringify(`
      html, body { width: 1512px; height: 742px; margin: 0; overflow: hidden; background: #0a0a0f; }
      .fixture-project-shell { position: absolute; left: 32px; top: 24px; width: 1448px; height: 694px; background: #111827; border: 1px solid #263445; }
    `)};
    document.head.appendChild(shellStyle);
    const style = document.createElement('style');
    style.textContent = ${JSON.stringify(css)};
    document.head.appendChild(style);
    const apiScript = document.createElement('script');
    apiScript.textContent = ${JSON.stringify(apiJs)};
    document.body.appendChild(apiScript);
    const modalScript = document.createElement('script');
    modalScript.textContent = ${JSON.stringify(modalJs)};
    document.body.appendChild(modalScript);
    window.ProjectOrchestration.open(${JSON.stringify(project)}, { api: { async saveCompletedDrag(payload) { return { ok: true, saved: true, assignments: payload.assignments, orchestration: { revision: 8, state: 'draft' } }; } } });
    return true;
  })()`);
  await evaluate('document.fonts && document.fonts.ready ? document.fonts.ready.then(() => true) : true');
  await new Promise((resolve) => setTimeout(resolve, 200));

  const metrics = await evaluate(`(() => {
    const rect = (selector) => {
      const node = document.querySelector(selector);
      const r = node.getBoundingClientRect();
      return {
        x: Math.round(r.x),
        y: Math.round(r.y),
        width: Math.round(r.width),
        height: Math.round(r.height),
      };
    };
    const text = (selector) => document.querySelector(selector).textContent;
    const styles = (selector) => {
      const computed = getComputedStyle(document.querySelector(selector));
      return {
        fontFamily: computed.fontFamily,
        backgroundColor: computed.backgroundColor,
        borderColor: computed.borderColor,
      };
    };
    return {
      viewport: { width: innerWidth, height: innerHeight },
      overlay: rect('.project-orchestration-overlay'),
      modal: rect('.project-orchestration-modal'),
      header: rect('.project-orchestration-header'),
      notice: rect('.project-orchestration-notice'),
      canvas: rect('.project-orchestration-canvas'),
      footer: rect('.project-orchestration-footer'),
      taskCount: document.querySelectorAll('.project-orchestration-task').length,
      stageCount: document.querySelectorAll('.project-orchestration-stage').length,
      connectorCount: document.querySelectorAll('.project-orchestration-connector').length,
      saveButtonCount: document.querySelectorAll('.project-orchestration-save').length,
      title: text('.project-orchestration-title'),
      count: text('.project-orchestration-count'),
      modalStyle: styles('.project-orchestration-modal'),
      canvasStyle: styles('.project-orchestration-canvas'),
    };
  })()`);

  assert.deepEqual(metrics.viewport, { width: 1512, height: 742 });
  assert.deepEqual(metrics.overlay, { x: 0, y: 0, width: 1512, height: 742 });
  near(metrics.modal.x, 146, 1, 'modal x');
  near(metrics.modal.y, 91, 1, 'modal y');
  near(metrics.modal.width, 1220, 1, 'modal width');
  near(metrics.modal.height, 560, 1, 'modal height');
  near(metrics.header.height, 57, 2, 'header height');
  near(metrics.notice.height, 30, 2, 'notice height');
  near(metrics.canvas.width, 1184, 2, 'canvas width');
  near(metrics.canvas.height, 350, 1, 'canvas height');
  near(metrics.footer.height, 53, 2, 'footer height');
  assert.equal(metrics.taskCount, 9);
  assert.equal(metrics.stageCount, 5);
  assert.equal(metrics.connectorCount, 4);
  assert.equal(metrics.saveButtonCount, 0);
  assert.equal(metrics.title, '任务流水线编排');
  assert.equal(metrics.count, '9 TASKS · 5 STEPS');
  assert.match(metrics.modalStyle.fontFamily, /Press Start 2P|Fusion Pixel/);
  assert.equal(metrics.modalStyle.backgroundColor, 'rgb(17, 17, 36)');
  assert.equal(metrics.modalStyle.borderColor, 'rgb(255, 215, 0)');
  assert.equal(metrics.canvasStyle.backgroundColor, 'rgb(9, 9, 26)');

  const screenshot = await send('Page.captureScreenshot', { format: 'png', fromSurface: true, captureBeyondViewport: false });
  fs.writeFileSync(screenshotPath, Buffer.from(screenshot.data, 'base64'));
  assert.deepEqual(pngSize(referenceOverlayPath), { width: 1512, height: 742 });
  assert.deepEqual(pngSize(referenceModalPath), { width: 1292, height: 632 });
  assert.deepEqual(pngSize(screenshotPath), { width: 1512, height: 742 });

  console.log(JSON.stringify({ screenshot: screenshotPath, metrics }, null, 2));
} finally {
  ws.close();
  await closeCdpPage(page);
  fixtureServer.close();
  if (chromiumProcess) chromiumProcess.kill('SIGTERM');
  if (ownedUserDataDir) fs.rmSync(ownedUserDataDir, { recursive: true, force: true });
}
