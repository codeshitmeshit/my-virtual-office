import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { createRequire } from 'node:module';
import { fileURLToPath } from 'node:url';

const require = createRequire(import.meta.url);
const here = path.dirname(fileURLToPath(import.meta.url));
const modulePath = path.join(here, '../app/human-decision-center.js');
const Center = fs.existsSync(modulePath) ? require(modulePath) : {};

assert.equal(typeof Center.sortPendingDecisions, 'function', 'exports pending decision sorting');
assert.equal(typeof Center.shouldAutoOpenDecision, 'function', 'exports attention transition rule');
assert.equal(typeof Center.resolveDecisionAnswer, 'function', 'exports answer resolution rule');

const sorted = Center.sortPendingDecisions([
  { id: 'normal', status: 'pending', risk: 'low', urgency: 'normal', deadlineAt: '2026-08-06T10:00:00+08:00' },
  { id: 'near', status: 'pending', risk: 'medium', urgency: 'urgent', nearTimeout: true, deadlineAt: '2026-08-03T10:30:00+08:00' },
  { id: 'high', status: 'pending', risk: 'high', urgency: 'normal', deadlineAt: '2026-08-05T10:00:00+08:00' },
  { id: 'done', status: 'resolved', risk: 'high', urgency: 'critical' },
]);
assert.deepEqual(sorted.map((item) => item.id), ['high', 'near', 'normal']);

assert.equal(
  Center.shouldAutoOpenDecision(
    { id: 'd1', status: 'pending', risk: 'medium', nearTimeout: false },
    { id: 'd1', status: 'pending', risk: 'medium', nearTimeout: true },
  ),
  true,
  'auto-opens when an existing decision first becomes near timeout',
);
assert.equal(
  Center.shouldAutoOpenDecision(
    { id: 'd1', status: 'pending', risk: 'high', nearTimeout: false },
    { id: 'd1', status: 'pending', risk: 'high', nearTimeout: false },
  ),
  false,
  'does not repeatedly auto-open an unchanged attention item',
);

assert.deepEqual(
  Center.resolveDecisionAnswer(
    { options: [{ id: 'B', label: '分阶段上线' }] },
    { optionId: 'B', customAnswer: '  先在内部团队灰度一周  ' },
  ),
  { answer: '先在内部团队灰度一周', optionId: null },
  'custom input overrides a selected option',
);
assert.deepEqual(
  Center.resolveDecisionAnswer(
    { options: [{ id: 'B', label: '分阶段上线' }] },
    { optionId: 'B', customAnswer: '   ' },
  ),
  { answer: '分阶段上线', optionId: 'B' },
  'selected option is used when custom input is empty',
);
assert.equal(Center.resolveDecisionAnswer({ options: [] }, {}), null);

class FakeElement {
  constructor(tag, document) {
    this.tagName = String(tag).toUpperCase();
    this.ownerDocument = document;
    this.children = [];
    this.attributes = {};
    this.listeners = {};
    this.parentNode = null;
    this.className = '';
    this._textContent = '';
    this.type = '';
    this.value = '';
    this.checked = false;
    this.disabled = false;
    this.hidden = false;
  }

  set textContent(value) {
    this._textContent = String(value ?? '');
    this.children = [];
  }

  get textContent() {
    return this._textContent;
  }

  appendChild(child) {
    child.parentNode = this;
    this.children.push(child);
    return child;
  }

  replaceChildren(...children) {
    this.children.forEach((child) => { child.parentNode = null; });
    this.children = [];
    this._textContent = '';
    children.forEach((child) => this.appendChild(child));
  }

  setAttribute(name, value) {
    this.attributes[name] = String(value);
  }

  getAttribute(name) {
    return this.attributes[name] ?? null;
  }

  removeAttribute(name) {
    delete this.attributes[name];
  }

  addEventListener(type, listener) {
    (this.listeners[type] ||= []).push(listener);
  }

  removeEventListener(type, listener) {
    this.listeners[type] = (this.listeners[type] || []).filter((item) => item !== listener);
  }

  dispatch(type, detail = {}) {
    const event = { target: this, currentTarget: this, preventDefault() {}, ...detail };
    for (const listener of this.listeners[type] || []) listener(event);
  }

  focus() {
    this.ownerDocument.activeElement = this;
  }
}

function createDocument() {
  const document = {
    activeElement: null,
    createElement(tag) {
      return new FakeElement(tag, document);
    },
  };
  return document;
}

function walk(node, visitor) {
  visitor(node);
  for (const child of node.children || []) walk(child, visitor);
}

function allText(node) {
  const parts = [];
  walk(node, (candidate) => {
    if (candidate.textContent) parts.push(candidate.textContent);
  });
  return parts.join(' ');
}

function findByAttribute(node, name, value) {
  let found = null;
  walk(node, (candidate) => {
    if (found) return;
    const actual = candidate.getAttribute ? candidate.getAttribute(name) : null;
    if (actual !== null && (value === undefined || actual === value)) found = candidate;
  });
  return found;
}

function findAllByAttribute(node, name) {
  const found = [];
  walk(node, (candidate) => {
    if (candidate.getAttribute && candidate.getAttribute(name) !== null) found.push(candidate);
  });
  return found;
}

function decision(overrides = {}) {
  return {
    id: 'decision-1',
    status: 'pending',
    source: { type: 'task', id: 'task-1', label: '官网改版' },
    title: '确认上线节奏',
    situation: '核心页面已完成，需要决定发布节奏。',
    reason: '不同节奏会影响风险和发布时间。',
    risk: 'medium',
    urgency: 'normal',
    nearTimeout: false,
    deadlineAt: '2026-08-03T12:00:00+08:00',
    timeoutConsequence: '低风险事项将采用 VO 推荐方案。',
    options: [
      { id: 'A', label: '立即全量', impact: '速度快，回滚压力高' },
      { id: 'B', label: '分阶段上线', impact: '更稳妥，需要多一天' },
      { id: 'C', label: '仅内部灰度', impact: '风险最低，发布时间延后' },
      { id: 'D', label: '暂缓', impact: '不引入风险，但阻塞后续' },
    ],
    recommendation: { optionId: 'B', reason: '兼顾发布时间与回滚风险。' },
    reminder: { count: 1, limit: 3, nextAt: '2026-08-03T11:00:00+08:00' },
    taskDetail: { summary: '完成上线决策', completed: ['页面开发'], blocked: '等待发布节奏', context: '营销活动将在两天后开始', nextStep: '按选择创建发布批次' },
    resolution: null,
    execution: { started: false, impact: '' },
    ...overrides,
  };
}

assert.equal(typeof Center.mount, 'function', 'exports the embeddable mount lifecycle');

const document = createDocument();
const toggle = document.createElement('button');
const panel = document.createElement('section');
const controller = Center.mount(
  { toggle, panel },
  { revision: 1, generatedAt: '2026-08-03T10:00:00+08:00', decisions: [decision()] },
  {},
);
assert.equal(toggle.getAttribute('data-count'), '1');
assert.match(allText(toggle), /⚖️/, 'sidebar entry uses the VO-style decision emoji');
assert.match(allText(toggle), /打开人工决策/, 'sidebar entry names the action clearly');
assert.equal(panel.hidden, true);

const customInput = findByAttribute(panel, 'data-decision-custom-answer');
customInput.value = '先向设计团队灰度';
customInput.dispatch('input');

controller.update({
  revision: 2,
  generatedAt: '2026-08-03T10:05:00+08:00',
  decisions: [decision({
    status: 'resolved',
    resolution: {
      answer: '分阶段上线',
      optionId: 'B',
      channel: 'feishu',
      resolvedAt: '2026-08-03T10:04:00+08:00',
      nextAction: 'VO 将创建 10% 灰度批次',
    },
  })],
});
assert.equal(toggle.getAttribute('data-count'), '0');
assert.match(allText(panel), /飞书/);
assert.match(allText(panel), /VO 将创建 10% 灰度批次/);
assert.equal(findByAttribute(panel, 'data-decision-submit'), null, 'resolved item cannot be submitted again');
assert.equal(
  findByAttribute(panel, 'data-decision-tab', 'history').getAttribute('aria-selected'),
  'true',
  'externally resolved selected item moves the center to processed history',
);

controller.update({ revision: 1, decisions: [decision()] });
assert.equal(toggle.getAttribute('data-count'), '0', 'stale snapshots cannot roll resolved state back');
assert.match(allText(panel), /飞书/);

controller.update({
  revision: 3,
  decisions: [
    decision({ id: 'normal-2', title: '普通新事项' }),
    decision({ id: 'high-1', title: '高风险权限变更', risk: 'high' }),
  ],
});
assert.equal(panel.hidden, false, 'new high-risk decision opens the center');
assert.match(allText(panel), /高风险权限变更/);
assert.equal(document.activeElement, panel, 'auto-open moves focus into the decision center');

controller.destroy();
assert.equal((toggle.listeners.click || []).length, 0, 'destroy removes host listeners');

const interactionDocument = createDocument();
const interactionToggle = interactionDocument.createElement('button');
const interactionPanel = interactionDocument.createElement('section');
const submissions = [];
const changes = [];
const normal = decision();
const interactionController = Center.mount(
  { toggle: interactionToggle, panel: interactionPanel },
  { revision: 10, decisions: [normal] },
  {
    onSubmit(payload) { submissions.push(payload); },
    onRequestChange(payload) { changes.push(payload); },
  },
);

interactionToggle.dispatch('click');
assert.equal(interactionPanel.hidden, false, 'toolbar entry opens the center');
assert.equal(interactionDocument.activeElement, interactionPanel, 'manual open moves focus into the center');
assert.match(allText(interactionPanel), /当前情景/);
assert.match(allText(interactionPanel), /任务详细信息/);
assert.equal(findAllByAttribute(interactionPanel, 'data-decision-option').length, 4);

const optionB = findByAttribute(interactionPanel, 'data-decision-option', 'B');
optionB.checked = true;
optionB.dispatch('change');
const answerInput = findByAttribute(interactionPanel, 'data-decision-custom-answer');
answerInput.value = '先灰度给内部团队';
answerInput.dispatch('input');
findByAttribute(interactionPanel, 'data-decision-submit').dispatch('click');
assert.deepEqual(submissions, [{ decisionId: 'decision-1', answer: '先灰度给内部团队', optionId: null }]);
assert.equal(interactionToggle.getAttribute('data-count'), '1', 'submit waits for a new authoritative snapshot');

interactionController.update({
  revision: 11,
  decisions: [decision({
    status: 'locked',
    resolution: {
      answer: '分阶段上线', optionId: 'B', channel: 'local',
      resolvedAt: '2026-08-03T10:20:00+08:00', nextAction: '创建灰度批次',
    },
    execution: { started: true, impact: '已创建发布批次，变更会撤销排期。' },
  })],
});

let confirmMessage = null;
let confirmOptions = null;
globalThis.VODialogs = {
  showConfirm(message, options) {
    confirmMessage = message;
    confirmOptions = options;
    return Promise.resolve(true);
  },
};
interactionController.update({
  revision: 12,
  decisions: [decision({
    status: 'locked',
    resolution: {
      answer: '分阶段上线', optionId: 'B', channel: 'local',
      resolvedAt: '2026-08-03T10:20:00+08:00', nextAction: '创建灰度批次',
    },
    execution: { started: true, impact: '已创建发布批次，变更会撤销排期。' },
  })],
});
findByAttribute(interactionPanel, 'data-decision-request-change').dispatch('click');
await Promise.resolve();
assert.equal(confirmMessage, '已创建发布批次，变更会撤销排期。', 'confirmation receives the impact as message');
assert.deepEqual(confirmOptions, {
  title: '确认请求变更？',
  confirmText: '确认请求变更',
  tone: 'danger',
});
assert.deepEqual(changes, [{ decisionId: 'decision-1', locked: true }]);

interactionToggle.dispatch('click');
assert.equal(interactionPanel.hidden, true, 'toolbar entry closes an open center');
interactionController.destroy();
delete globalThis.VODialogs;

const languageListeners = { ready: new Set(), changed: new Set() };
const enLocale = JSON.parse(fs.readFileSync(path.join(here, '../app/locales/en.json'), 'utf8'));
const zhLocale = JSON.parse(fs.readFileSync(path.join(here, '../app/locales/zh.json'), 'utf8'));
let activeLocale = enLocale;
let localeReady = false;
globalThis.i18n = {
  getLanguage() { return activeLocale === zhLocale ? 'zh' : 'en'; },
  t(key, params = {}) {
    if (!localeReady) return key;
    let value = activeLocale[key] || key;
    Object.entries(params).forEach(([name, replacement]) => {
      value = value.replaceAll(`{{${name}}}`, String(replacement));
    });
    return value;
  },
};
globalThis.addEventListener = (type, listener) => {
  if (type === 'i18n:ready') languageListeners.ready.add(listener);
  if (type === 'i18n:changed') languageListeners.changed.add(listener);
};
globalThis.removeEventListener = (type, listener) => {
  if (type === 'i18n:ready') languageListeners.ready.delete(listener);
  if (type === 'i18n:changed') languageListeners.changed.delete(listener);
};

const localizedDocument = createDocument();
const localizedToggle = localizedDocument.createElement('button');
const localizedPanel = localizedDocument.createElement('section');
const localizedController = Center.mount(
  { toggle: localizedToggle, panel: localizedPanel },
  { revision: 20, decisions: [decision()] },
  {},
);
assert.match(allText(localizedToggle), /打开人工决策/, 'uses a readable fallback while locale data is loading');
assert.equal(languageListeners.ready.size, 1, 'subscribes to initial locale readiness');
assert.equal(languageListeners.changed.size, 1, 'subscribes to subsequent language changes');

localeReady = true;
for (const listener of languageListeners.ready) listener({ detail: { lang: 'en' } });
assert.match(allText(localizedToggle), /Open decisions/, 'uses the shared English locale for the entry action');
assert.match(allText(localizedPanel), /Current situation/, 'uses the shared English locale for component chrome');
assert.match(allText(localizedPanel), /确认上线节奏/, 'keeps backend-provided decision content in its original language');

activeLocale = zhLocale;
for (const listener of languageListeners.changed) listener({ detail: { lang: 'zh' } });
assert.match(allText(localizedToggle), /打开人工决策/, 'rerenders the entry after a language change');
assert.match(allText(localizedPanel), /当前情景/, 'rerenders the open component after a language change');

localizedController.destroy();
assert.equal(languageListeners.ready.size, 0, 'destroy removes the locale-readiness listener');
assert.equal(languageListeners.changed.size, 0, 'destroy removes the language-change listener');
delete globalThis.i18n;
delete globalThis.addEventListener;
delete globalThis.removeEventListener;

const cssPath = path.join(here, '../app/human-decision-center.css');
const css = fs.existsSync(cssPath) ? fs.readFileSync(cssPath, 'utf8') : '';
assert.match(css, /\.human-decision-center\s*\{/u, 'defines the scoped center shell');
assert.match(css, /var\(--ui-surface/u, 'reuses the existing control-panel surface token');
assert.match(css, /var\(--ui-border/u, 'reuses the existing control-panel border token');
assert.match(css, /var\(--gold/u, 'reuses the existing control-panel accent token');
assert.match(css, /@media\s*\(max-width:\s*900px\)/u, 'defines the narrow list/detail layout');
assert.match(css, /:focus-visible/u, 'keeps keyboard focus visible');
assert.match(css, /overflow-wrap:\s*anywhere/u, 'long decision content cannot force horizontal scrolling');
assert.doesNotMatch(css, /\.sms-/u, 'does not couple decision styles to SMS business selectors');
assert.match(
  css,
  /\.human-decision-center-host\s*\{[^}]*align-items:\s*center;[^}]*justify-items:\s*center;/su,
  'decision details use a centered VO modal instead of a right-side drawer',
);
assert.match(css, /\.human-decision-center__heading h1\s*\{[^}]*font-size:\s*14px;/su, 'modal heading uses the VO title tier');
assert.match(css, /\.human-decision-center__title\s*\{[^}]*font-size:\s*12px;/su, 'decision heading uses the compact item-title tier');
assert.match(css, /\.human-decision-center__context > p,[^{]*\{[^}]*font-size:\s*10px;/su, 'decision body uses one consistent body tier');
assert.doesNotMatch(css, /font-size:\s*clamp\(/u, 'decision center does not introduce oversized responsive typography');

assert.doesNotMatch(fs.readFileSync(modulePath, 'utf8'), /DEMO_SNAPSHOTS/u, 'demo data stays outside the reusable component');

const productionHtml = fs.readFileSync(path.join(here, '../app/index.html'), 'utf8');
const productionAdapter = fs.readFileSync(path.join(here, '../app/human-decision-center-app.js'), 'utf8');
const realtimeSource = fs.readFileSync(path.join(here, '../app/dashboard-realtime.js'), 'utf8');
const toolbarMarkup = productionHtml.slice(
  productionHtml.indexOf('<div class="toolbar">'),
  productionHtml.indexOf('<div class="sidebar-edge"'),
);
const sidebarMarkup = productionHtml.slice(
  productionHtml.indexOf('<div class="sidebar" id="sidebar">'),
  productionHtml.indexOf('<div id="agentModal"'),
);
assert.doesNotMatch(toolbarMarkup, /id="human-decision-center-toggle"/u, 'VO toolbar does not duplicate the decision entry');
assert.match(sidebarMarkup, /class="human-decision-sidebar collapsible"/u, 'right control panel owns a decision section');
assert.match(sidebarMarkup, /⚖️ 人工决策/u, 'right control panel labels the decision section with a VO-style emoji');
assert.match(sidebarMarkup, /id="human-decision-center-toggle"/u, 'right control panel owns the production decision entry');
assert.match(productionHtml, /id="human-decision-center-panel"/u, 'VO page owns the production modal host');
assert.match(productionHtml, /human-decision-center\.css\?v=20260803-vo-shell/u, 'VO page invalidates cached decision styles for the new shell');
assert.match(productionHtml, /human-decision-center-i18n\.js\?v=20260804-i18n/u, 'VO page loads the decision translation adapter before the component');
assert.match(productionHtml, /human-decision-center\.js\?v=20260804-i18n/u, 'VO page invalidates cached decision component code for i18n');
assert.match(productionHtml, /human-decision-center-app\.js\?v=20260804-i18n/u, 'VO page loads the versioned production adapter');
assert.match(productionHtml, /dashboard-realtime\.js\?v=20260810-auth-ready/u, 'VO page invalidates cached realtime code that projects decisions');
assert.doesNotMatch(productionHtml, /human-decision-center-prototype\.js/u, 'VO page never loads the removable showcase controller');
assert.equal(fs.existsSync(path.join(here, '../app/human-decision-center-prototype.html')), false, 'approved showcase HTML is removed');
assert.equal(fs.existsSync(path.join(here, '../app/human-decision-center-prototype.js')), false, 'approved showcase controller is removed');
assert.match(productionAdapter, /\/api\/human-decisions\//u, 'production adapter submits to the authoritative API');
assert.match(realtimeSource, /dashboard\.decisions/u, 'existing dashboard realtime connection receives decision events');
assert.equal((realtimeSource.match(/new EventSource\(/gu) || []).length, 1, 'decision integration does not add another EventSource');

console.log('human decision center runtime contract ok');
