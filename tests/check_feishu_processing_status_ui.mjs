import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';

const html = fs.readFileSync('app/index.html', 'utf8');
const game = fs.readFileSync('app/game.js', 'utf8');
const en = JSON.parse(fs.readFileSync('app/locales/en.json', 'utf8'));
const zh = JSON.parse(fs.readFileSync('app/locales/zh.json', 'utf8'));

assert.match(html, /id="mm-feishu-chat-processing-status"/, 'Chat settings must include a processing status bar');
assert.match(game, /setInterval\(mmRefreshFeishuChatProcessingStatus, 5000\)/, 'visible settings polling must use a five-second interval');
assert.match(game, /if \(document\.hidden\) mmStopFeishuChatProcessingPolling\(\)/, 'polling must stop when the panel is not visible');
for (const locale of [en, zh]) {
  for (const key of ['feishu_chat_processing_legacy', 'feishu_chat_processing_state_healthy', 'feishu_chat_processing_state_degraded', 'feishu_chat_processing_state_recovering']) {
    assert.ok(locale[key], `missing localized processing key ${key}`);
  }
}

const start = game.indexOf('// Feishu chat processing health: intentionally separate from WebSocket health.');
const end = game.indexOf('function mmClearMisplacedFeishuChatStatus', start);
assert.ok(start >= 0 && end > start, 'processing UI functions must remain a focused testable block');

let visibilityHandler;
let fetches = 0;
let intervalDelay = 0;
let clearedTimer = null;
const processingElement = {
  style: {},
  _text: '',
  set textContent(value) { this._text = String(value); },
  get textContent() { return this._text; },
  set innerHTML(_value) { throw new Error('processing status must never write innerHTML'); },
};
const translations = { ...en };
const context = {
  console,
  Date,
  Promise,
  _mainMenuOpen: true,
  _feishuChatProcessingPollTimer: null,
  _feishuChatProcessingPollInFlight: false,
  document: {
    hidden: false,
    getElementById(id) { return id === 'mm-feishu-chat-processing-status' ? processingElement : null; },
    addEventListener(name, handler) { if (name === 'visibilitychange') visibilityHandler = handler; },
  },
  _tr(key, values = {}) {
    return String(translations[key] || key).replace(/\{\{(\w+)\}\}/g, (_match, name) => String(values[name] ?? ''));
  },
  mmRenderFeishuChatLongConnectionStatus() {},
  fetch: async () => {
    fetches += 1;
    return { async json() { return { longConnection: { processing: { state: 'healthy', backlog: 0 } } }; } };
  },
  setInterval(_callback, delay) { intervalDelay = delay; return 73; },
  clearInterval(timer) { clearedTimer = timer; },
};
vm.createContext(context);
vm.runInContext(game.slice(start, end), context);

context.mmRenderFeishuChatProcessingStatus({ longConnection: {} });
assert.equal(processingElement.textContent, en.feishu_chat_processing_legacy);
context.mmRenderFeishuChatProcessingStatus({
  longConnection: {
    processing: {
      state: 'degraded', backlog: 2, blocked: 1, oldestPendingAt: Date.now() - 5_000,
      lastAckAt: 0, warning: true, lastErrorCategory: '<img src=x onerror=alert(1)>',
    },
  },
});
assert.match(processingElement.textContent, /degraded/);
assert.match(processingElement.textContent, /backlog 2/);
assert.match(processingElement.textContent, /<img src=x/, 'untrusted text may be displayed only through textContent');

context.mmStartFeishuChatProcessingPolling();
await Promise.resolve();
await Promise.resolve();
assert.equal(intervalDelay, 5000);
assert.equal(fetches, 1);
context.mmStopFeishuChatProcessingPolling();
assert.equal(clearedTimer, 73);
context.document.hidden = true;
context.mmStartFeishuChatProcessingPolling();
assert.equal(context._feishuChatProcessingPollTimer, null);
assert.equal(typeof visibilityHandler, 'function');

console.log('check_feishu_processing_status_ui.mjs passed');
