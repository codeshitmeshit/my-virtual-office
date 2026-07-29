const assert = require('assert');
const fs = require('fs');
const path = require('path');
const vm = require('vm');

const root = path.resolve(__dirname, '..');
const source = fs.readFileSync(
  path.join(root, 'app', 'skills-library-organization-ui.js'),
  'utf8',
);

class FakeClassList {
  constructor(element) {
    this.element = element;
  }
  values() {
    return new Set(String(this.element.className || '').split(/\s+/).filter(Boolean));
  }
  add(...names) {
    const values = this.values();
    names.forEach((name) => values.add(name));
    this.element.className = [...values].join(' ');
  }
  remove(...names) {
    const values = this.values();
    names.forEach((name) => values.delete(name));
    this.element.className = [...values].join(' ');
  }
  contains(name) {
    return this.values().has(name);
  }
}

class FakeElement {
  constructor(tag, document) {
    this.tagName = String(tag).toUpperCase();
    this.ownerDocument = document;
    this.children = [];
    this.listeners = {};
    this.attributes = {};
    this.className = '';
    this.classList = new FakeClassList(this);
    this.style = {};
    this.textContent = '';
    this.value = '';
    this.disabled = false;
    this.title = '';
  }
  set id(value) {
    this._id = value;
    if (value) this.ownerDocument.byId.set(value, this);
  }
  get id() {
    return this._id || '';
  }
  appendChild(child) {
    this.children.push(child);
    return child;
  }
  append(...children) {
    children.forEach((child) => this.appendChild(child));
  }
  replaceChildren(...children) {
    this.children = [];
    this.append(...children);
  }
  addEventListener(type, listener) {
    (this.listeners[type] ||= []).push(listener);
  }
  setAttribute(name, value) {
    this.attributes[name] = String(value);
  }
  getAttribute(name) {
    return this.attributes[name] ?? null;
  }
}

function harness() {
  const document = {
    byId: new Map(),
    createElement(tag) {
      return new FakeElement(tag, document);
    },
    getElementById(id) {
      return document.byId.get(id) || null;
    },
  };
  for (const id of [
    'skillsLibraryModal',
    'skl-organization-marker',
    'skl-search-input',
    'skl-organize-btn',
    'skl-category-list',
    'skl-list-title',
    'skl-list-count',
    'skl-cards',
    'skl-detail',
  ]) {
    const element = new FakeElement('div', document);
    element.id = id;
  }
  document.getElementById('skl-organization-marker').className =
    'skl-organization-marker hidden';
  const timers = new Map();
  let timerId = 0;
  const window = {
    document,
    Date,
    clearTimeout(id) {
      timers.delete(id);
    },
    setTimeout(callback, delay) {
      const id = ++timerId;
      timers.set(id, { callback, delay });
      return id;
    },
    fetch: async () => {
      throw new Error('unexpected fetch');
    },
    refreshSkillsList: async () => {},
  };
  window.window = window;
  const context = {
    window,
    document,
    Date,
    console,
  };
  vm.runInNewContext(source, context, {
    filename: 'skills-library-organization-ui.js',
  });
  return { window, document, timers };
}

function data(overrides = {}) {
  return {
    skills: [
      {
        name: 'alpha',
        description: 'Alpha skill',
        primaryCategoryId: 'default',
        tags: [],
      },
    ],
    categories: [
      { id: 'default', name: '默认标签', kind: 'system' },
      { id: 'development-testing', name: '开发与测试', kind: 'general' },
    ],
    organization: null,
    archiveManager: { agentId: 'archive-manager', status: 'idle' },
    organizationEnabled: true,
    ...overrides,
  };
}

function markerText(document) {
  const marker = document.getElementById('skl-organization-marker');
  return marker.children[0] ? marker.children[0].textContent : '';
}

function findByClass(element, className) {
  if (element.classList && element.classList.contains(className)) return element;
  for (const child of element.children || []) {
    const match = findByClass(child, className);
    if (match) return match;
  }
  return null;
}

async function main() {
  {
    const { window, document, timers } = harness();
    const cases = [
      ['running', '档案管理员正在整理技能库…', 'is-running'],
      ['completed', '技能整理已完成', 'is-completed'],
      ['partial', '技能整理完成，2 个归类失败', 'is-partial'],
      ['failed', '技能整理未完成，2 个归类失败', 'is-partial'],
      ['resolved', '归类失败项已全部处理', 'is-resolved'],
    ];
    for (const [status, text, tone] of cases) {
      window.SkillLibraryOrganizationUI.update(
        data({
          organization: {
            runId: 'run-1',
            status,
            failureCount: 2,
            failures: [],
          },
        }),
      );
      const marker = document.getElementById('skl-organization-marker');
      assert.equal(markerText(document), text);
      assert(marker.classList.contains(tone));
      assert(!marker.classList.contains('hidden'));
      if (status === 'running') {
        assert.equal(marker.children.length, 1, 'running marker is not dismissible');
        assert.equal(timers.size, 1, 'running state starts one poll');
      } else {
        assert.equal(marker.children.length, 2, 'terminal marker is dismissible');
        assert.equal(timers.size, 0, 'terminal state stops polling');
      }
    }
    window.SkillLibraryOrganizationUI.update(
      data({
        organization: {
          status: 'completed',
          dismissedAt: '2026-07-30T11:00:00Z',
          failures: [],
        },
      }),
    );
    assert(
      document.getElementById('skl-organization-marker').classList.contains('hidden'),
      'dismissed marker stays hidden',
    );
  }

  {
    const { window, document, timers } = harness();
    const button = document.getElementById('skl-organize-btn');
    window.SkillLibraryOrganizationUI.update(data());
    assert.equal(button.disabled, false);
    window.SkillLibraryOrganizationUI.update(
      data({ archiveManager: { status: 'working', activeWork: { kind: 'archive-count-audit' } } }),
    );
    assert.equal(button.disabled, true);
    assert.match(button.title, /正在处理其他工作/);
    window.SkillLibraryOrganizationUI.update(
      data({ archiveManager: { status: 'unavailable' } }),
    );
    assert.equal(button.disabled, true);
    assert.match(button.title, /不可用/);
    window.SkillLibraryOrganizationUI.update(data({ skills: [] }));
    assert.equal(button.disabled, true);
    assert.match(button.title, /没有需要整理/);
    window.SkillLibraryOrganizationUI.update(
      data({ organizationEnabled: false }),
    );
    assert.equal(button.disabled, true);
    assert.match(button.title, /未启用/);

    window.SkillLibraryOrganizationUI.update(
      data({ organization: { status: 'running', failures: [] } }),
    );
    assert.equal(timers.size, 1);
    window.refreshSkillsList = async () => {
      window.SkillLibraryOrganizationUI.update(
        data({ organization: { status: 'completed', failures: [] } }),
      );
    };
    const [activePollId, activePoll] = [...timers.entries()][0];
    assert.equal(activePoll.delay, 2000);
    timers.delete(activePollId);
    await activePoll.callback();
    assert.equal(timers.size, 0, 'polling stops when refresh reaches a terminal state');

    window.SkillLibraryOrganizationUI.update(
      data({ organization: { status: 'running', failures: [] } }),
    );
    window.SkillLibraryOrganizationUI.update(
      data({ organization: { status: 'running', failures: [] } }),
    );
    assert.equal(timers.size, 1, 're-render must not duplicate polling timers');
    document.getElementById('skillsLibraryModal').classList.add('hidden');
    window.SkillLibraryOrganizationUI.update(
      data({ organization: { status: 'running', failures: [] } }),
    );
    assert.equal(timers.size, 0, 'closed modal does not poll');
  }

  {
    const { window, document } = harness();
    let requests = 0;
    let resolveResponse;
    window.i18n = {
      managementFetch() {
        requests += 1;
        return new Promise((resolve) => {
          resolveResponse = resolve;
        });
      },
    };
    let refreshes = 0;
    window.refreshSkillsList = async () => {
      refreshes += 1;
    };
    window.SkillLibraryOrganizationUI.update(data());
    const first = window.SkillLibraryOrganizationUI.startOrganization();
    const second = window.SkillLibraryOrganizationUI.startOrganization();
    assert.equal(requests, 1, 'duplicate click must not dispatch twice');
    assert.equal(document.getElementById('skl-organize-btn').disabled, true);
    resolveResponse({
      ok: true,
      async json() {
        return { runId: 'run-1', status: 'running', failures: [] };
      },
    });
    await first;
    await second;
    assert.equal(refreshes, 1);
  }

  {
    const { window, document } = harness();
    const calls = [];
    window.i18n = {
      async managementFetch(url) {
        calls.push(url);
        return {
          ok: true,
          async json() {
            return {
              organization: { dismissedAt: '2026-07-30T12:00:00Z' },
            };
          },
        };
      },
    };
    window.SkillLibraryOrganizationUI.update(
      data({ organization: { status: 'completed', failures: [] } }),
    );
    await window.SkillLibraryOrganizationUI.dismissMarker();
    assert.deepEqual(calls, ['/api/skills-library/organization/dismiss']);
    assert(
      document.getElementById('skl-organization-marker').classList.contains('hidden'),
    );
  }

  {
    const { window, document } = harness();
    window.SkillLibraryOrganizationUI.update(
      data({
        skills: [
          {
            name: 'alpha',
            description: 'Alpha skill',
            primaryCategoryId: 'default',
            tags: [],
          },
          {
            name: 'beta',
            description: 'Beta skill',
            primaryCategoryId: 'default',
            tags: [],
          },
          {
            name: 'gamma',
            description: 'Gamma skill',
            primaryCategoryId: 'development-testing',
            tags: [],
          },
        ],
        organization: {
          status: 'partial',
          failureCount: 2,
          failures: [{ slug: 'alpha' }, { slug: 'beta' }],
        },
      }),
    );
    window.SkillLibraryOrganizationUI.openFailures();
    assert.equal(window.SkillLibraryOrganizationUI.state.categoryId, 'default');
    assert.equal(window.SkillLibraryOrganizationUI.state.failureOnly, true);
    assert.equal(document.getElementById('skl-list-title').textContent, '归类失败');
    assert.equal(document.getElementById('skl-list-count').textContent, '2');
    const cards = document.getElementById('skl-cards').children;
    assert.deepEqual(
      cards.map((card) => card.getAttribute('data-skill-slug')),
      ['alpha', 'beta'],
    );
    assert(cards.every((card) => findByClass(card, 'skl-failure-badge')));
  }

  {
    const { window } = harness();
    let refreshes = 0;
    window.refreshSkillsList = async () => {
      refreshes += 1;
    };
    window.i18n = {
      async managementFetch() {
        return {
          ok: false,
          async json() {
            return {
              code: 'catalog_revision_conflict',
              error: 'catalog changed',
            };
          },
        };
      },
    };
    window.SkillLibraryOrganizationUI.update(
      data({
        catalogRevision: 4,
        organization: {
          status: 'partial',
          failureCount: 1,
          failures: [{ slug: 'alpha' }],
        },
      }),
    );
    await window.SkillLibraryOrganizationUI.moveSelectedSkill('development-testing');
    assert.equal(refreshes, 1, 'revision conflict refreshes authoritative data');
    assert.equal(
      window.SkillLibraryOrganizationUI.state.data.skills[0].primaryCategoryId,
      'default',
      'revision conflict must not overwrite the local category',
    );
  }

  {
    const { window, document } = harness();
    let correction = 0;
    window.refreshSkillsList = async () => {};
    window.i18n = {
      async managementFetch(url, options) {
        correction += 1;
        const body = JSON.parse(options.body);
        assert.match(url, /\/api\/skills-library\/(alpha|beta)\/category/);
        assert.equal(body.expectedRevision, correction === 1 ? 7 : 8);
        const remaining = correction === 1 ? [{ slug: 'beta' }] : [];
        return {
          ok: true,
          async json() {
            return {
              catalogRevision: 7 + correction,
              metadata: {
                primaryCategoryId: body.categoryId,
                tags: ['manual'],
              },
              organization: {
                status: remaining.length ? 'partial' : 'resolved',
                failureCount: remaining.length,
                failures: remaining,
              },
            };
          },
        };
      },
    };
    window.SkillLibraryOrganizationUI.update(
      data({
        catalogRevision: 7,
        skills: [
          {
            name: 'alpha',
            description: 'Alpha skill',
            primaryCategoryId: 'default',
            tags: [],
          },
          {
            name: 'beta',
            description: 'Beta skill',
            primaryCategoryId: 'default',
            tags: [],
          },
        ],
        organization: {
          status: 'partial',
          failureCount: 2,
          failures: [{ slug: 'alpha' }, { slug: 'beta' }],
        },
      }),
    );
    window.SkillLibraryOrganizationUI.openFailures();
    await window.SkillLibraryOrganizationUI.moveSelectedSkill('development-testing');
    assert.equal(document.getElementById('skl-list-count').textContent, '1');
    assert.equal(
      window.SkillLibraryOrganizationUI.state.data.skills[0].primaryCategoryId,
      'development-testing',
    );
    assert.equal(window.SkillLibraryOrganizationUI.state.selectedSlug, 'beta');

    await window.SkillLibraryOrganizationUI.moveSelectedSkill('development-testing');
    assert.equal(window.SkillLibraryOrganizationUI.state.failureOnly, false);
    assert.equal(markerText(document), '归类失败项已全部处理');
    assert.equal(
      window.SkillLibraryOrganizationUI.state.data.organization.failureCount,
      0,
    );
  }

  {
    const { window, document } = harness();
    window.SkillLibraryOrganizationUI.update(
      data({
        organization: {
          status: 'running',
          failureCount: 1,
          failures: [{ slug: 'alpha' }],
        },
      }),
    );
    assert.equal(document.getElementById('skl-category-select').disabled, true);
    assert.equal(document.getElementById('skl-category-move').disabled, true);
    const detailActions = findByClass(
      document.getElementById('skl-detail'),
      'skl-detail-actions',
    );
    assert.equal(detailActions.children[0].disabled, false);
    assert.equal(detailActions.children[1].disabled, true);
    assert.equal(detailActions.children[2].disabled, true);
  }

  console.log('skill library organization UI state contract ok');
}

main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
