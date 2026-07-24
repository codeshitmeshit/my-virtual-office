#!/usr/bin/env node
import assert from 'node:assert/strict';
import { spawnSync } from 'node:child_process';
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

await cdpVersion();
const fixture = JSON.parse(fs.readFileSync('tests/fixtures/agent-management-browser.json', 'utf8'));
const locale = JSON.parse(fs.readFileSync('app/locales/en.json', 'utf8'));
const sources = {
  shell: fs.readFileSync('app/agent-management.js', 'utf8'),
  configuration: fs.readFileSync('app/agent-configuration.js', 'utf8'),
  humanResources: fs.readFileSync('app/human-resources.js', 'utf8'),
  adapters: fs.readFileSync('app/agent-management-adapters.js', 'utf8'),
  css: [
    fs.readFileSync('app/agent-management.css', 'utf8'),
    fs.readFileSync('app/agent-configuration.css', 'utf8'),
    fs.readFileSync('app/human-resources.css', 'utf8'),
  ].join('\n'),
};
const screenshotDir = process.env.AGENT_MANAGEMENT_ACCEPTANCE_SCREENSHOT_DIR || '';
const fixtureServer = http.createServer((_request, response) => {
  response.writeHead(200, { 'Content-Type': 'text/html; charset=utf-8' });
  response.end('<!doctype html><html><head><title>Agent Management Live Fixture</title></head><body></body></html>');
});
await new Promise((resolve, reject) => {
  fixtureServer.once('error', reject);
  fixtureServer.listen(0, '127.0.0.1', resolve);
});
const fixtureAddress = fixtureServer.address();
const fixtureUrl = `http://127.0.0.1:${fixtureAddress.port}/`;
const page = await createCdpPage(fixtureUrl);
const ws = new WebSocket(page.webSocketDebuggerUrl);
await new Promise((resolve, reject) => {
  ws.addEventListener('open', resolve, { once: true });
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
    const timer = setTimeout(() => {
      pending.delete(id);
      reject(new Error(`Timed out waiting for ${method}`));
    }, 20000);
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

async function waitFor(expression, timeoutMs = 10000) {
  const started = Date.now();
  while (Date.now() - started < timeoutMs) {
    if (await evaluate(expression)) return;
    await new Promise((resolve) => setTimeout(resolve, 60));
  }
  throw new Error(`Timed out waiting for ${expression}`);
}

async function captureScreenshot(name) {
  if (!screenshotDir) return '';
  fs.mkdirSync(screenshotDir, { recursive: true });
  const result = await send('Page.captureScreenshot', {
    format: 'png',
    captureBeyondViewport: true,
  });
  const path = `${screenshotDir}/${name}.png`;
  fs.writeFileSync(path, Buffer.from(result.data, 'base64'));
  return path;
}

try {
  await send('Page.enable');
  await send('Runtime.enable');
  await send('Emulation.setDeviceMetricsOverride', {
    width: 1440,
    height: 1000,
    deviceScaleFactor: 1,
    mobile: false,
  });
  await evaluate(`(() => {
    document.documentElement.innerHTML = ${JSON.stringify(`
      <head><meta charset="utf-8"><title>Agent Management Acceptance</title></head>
      <body>
        <button id="open-agent-management" type="button">Agent Management</button>
        <div id="agentManagementModal" class="agent-management-modal hidden" role="dialog" aria-modal="true" aria-labelledby="agent-management-title">
          <div class="agent-management-dialog">
            <header class="agent-management-header">
              <h2 id="agent-management-title" class="agent-management-title">Agent Management<small>Configuration and Human Resources</small></h2>
              <div class="agent-management-tabs" role="tablist" aria-label="Agent Management">
                <button id="agent-management-tab-configuration" class="agent-management-tab active" type="button" role="tab" aria-selected="true" aria-controls="agent-management-panel" data-agent-management-tab="configuration">Agent Configuration</button>
                <button id="agent-management-tab-human-resources" class="agent-management-tab" type="button" role="tab" aria-selected="false" aria-controls="agent-management-panel" tabindex="-1" data-agent-management-tab="humanResources">Human Resources</button>
              </div>
              <button id="agent-management-close" class="agent-management-close" type="button" aria-label="Close Agent Management">×</button>
            </header>
            <div class="agent-management-body">
              <aside id="agent-management-roster" class="agent-management-roster" aria-label="Agent roster"></aside>
              <main id="agent-management-panel" class="agent-management-panel" role="tabpanel" aria-labelledby="agent-management-tab-configuration" tabindex="-1"></main>
            </div>
            <div id="agent-management-feedback" class="agent-management-feedback" aria-live="polite"></div>
          </div>
        </div>
      </body>
    `)};
    const style = document.createElement('style');
    style.textContent = '.hidden{display:none!important}' + ${JSON.stringify(sources.css)};
    document.head.appendChild(style);
    const fixture = ${JSON.stringify(fixture)};
    const locale = ${JSON.stringify(locale)};
    const clone = value => JSON.parse(JSON.stringify(value));
    window.__amFixture = {
      data: fixture,
      mode: 'human',
      requests: [],
      browserResponses: [],
      conflictNext: false,
      failExport: false,
      denyNextCommand: false,
      undo: {},
      confirmation: null,
      challengeCounter: 0,
    };
    const runtime = window.__amFixture;
    function json(payload, status = 200) {
      return new Response(JSON.stringify(payload), {
        status,
        headers: { 'Content-Type': 'application/json' },
      });
    }
    function profileResponse(aiId) {
      const profile = fixture.profiles[aiId];
      return profile ? json({ ok: true, profile: clone(profile) }) :
        json({ ok: false, code: 'agent_profile_not_found' }, 404);
    }
    function mutate(body) {
      const profile = fixture.profiles[body.targetAiId];
      if (!profile) return json({ ok: false, code: 'agent_profile_not_found' }, 404);
      if (runtime.conflictNext) {
        runtime.conflictNext = false;
        return json({ ok: false, code: 'agent_profile_revision_conflict' }, 409);
      }
      if (body.expectedRevision !== profile.revision) {
        return json({ ok: false, code: 'agent_profile_revision_conflict' }, 409);
      }
      const previous = clone(profile);
      const field = String(body.field || '');
      if (field.startsWith('appearance.')) {
        profile.appearance[field.slice('appearance.'.length)] = body.value;
      } else {
        profile[field] = body.value;
      }
      profile.revision += 1;
      const token = 'undo-' + body.targetAiId + '-' + profile.revision;
      runtime.undo[token] = previous;
      return json({
        ok: true,
        profile: clone(profile),
        revision: profile.revision,
        undoToken: token,
        undoExpiresAt: '2026-07-24T23:59:59+08:00',
      });
    }
    function undo(body) {
      const previous = runtime.undo[body.undoToken];
      if (!previous) return json({ ok: false, code: 'agent_profile_undo_expired' }, 410);
      const current = fixture.profiles[previous.aiId];
      if (!current || current.revision !== body.expectedRevision) {
        return json({ ok: false, code: 'agent_profile_revision_conflict' }, 409);
      }
      const restored = clone(previous);
      restored.revision = current.revision + 1;
      fixture.profiles[previous.aiId] = restored;
      delete runtime.undo[body.undoToken];
      return json({ ok: true, profile: clone(restored), revision: restored.revision });
    }
    window.confirm = () => true;
    window.i18n = {
      t(key, params) {
        let value = locale[key] || key;
        for (const [name, replacement] of Object.entries(params || {})) {
          value = String(value).replaceAll('{{' + name + '}}', replacement);
        }
        return value;
      },
      async managementFetch(input, options = {}) {
        const url = String(input || '');
        const method = String(options.method || 'GET').toUpperCase();
        const body = options.body ? JSON.parse(options.body) : null;
        runtime.requests.push({ audience: 'human', url, method, body });
        if (url === '/api/human-resources/overview') {
          return json(clone(fixture.overview));
        }
        if (url.startsWith('/api/human-resources/export?table=agents')) {
          if (runtime.failExport) return json({ ok: false, code: 'hr_repository_unavailable' }, 503);
          return json({ ok: true, export: { rows: clone(fixture.agents) } });
        }
        if (url.startsWith('/api/human-resources/agents/')) {
          const aiId = decodeURIComponent(url.split('/agents/')[1].split('?')[0]);
          return json({ ok: true, agent: clone(fixture.details[aiId] || {}) });
        }
        if (url.startsWith('/api/agent-management/profiles/')) {
          return profileResponse(decodeURIComponent(url.split('/profiles/')[1]));
        }
        if (url === '/api/agent-management/profile/mutate') return mutate(body);
        if (url === '/api/agent-management/profile/undo') return undo(body);
        if (url === '/api/agent-management/confirmations') {
          const challengeToken = 'challenge-' + String(++runtime.challengeCounter).padStart(24, '0');
          runtime.confirmation = { change: clone(body), challengeToken };
          return json({ ok: true, confirmation: { challengeToken } }, 201);
        }
        if (url === '/api/agent-management/commands') {
          if (runtime.denyNextCommand) {
            runtime.denyNextCommand = false;
            runtime.confirmation = null;
            return json({ ok: false, code: 'agent_management_command_denied' }, 403);
          }
          const expected = Object.assign({}, runtime.confirmation.change, {
            challengeToken: runtime.confirmation.challengeToken,
          });
          if (JSON.stringify(body) !== JSON.stringify(expected)) {
            return json({ ok: false, code: 'agent_management_confirmation_conflict' }, 409);
          }
          runtime.confirmation = null;
          return json({ ok: true });
        }
        if (method === 'POST' && url === '/api/human-resources/directory/sync') {
          fixture.overview.activeCommands = [{
            id: 'sync-browser-1',
            action: 'sync',
            status: 'processing',
          }];
          return json({ ok: true, command: { id: 'sync-browser-1', accepted: true } }, 202);
        }
        return json({ ok: false, code: 'fixture_route_not_found' }, 404);
      },
    };
    window.fetch = async (input, options = {}) => {
      const url = String(input || '');
      const method = String(options.method || 'GET').toUpperCase();
      const body = options.body ? JSON.parse(options.body) : null;
      runtime.requests.push({ audience: 'agent', url, method, body });
      if (runtime.mode !== 'agent') return json({ ok: false, code: 'session_required' }, 401);
      let payload;
      let status = 200;
      if (url === '/api/agent-management/browser/bootstrap') {
        payload = {
          ok: true,
          audience: { kind: 'agent', aiId: 'codex-local' },
          items: clone(fixture.agents),
        };
      } else if (url.startsWith('/api/agent-management/browser/agents/')) {
        const aiId = decodeURIComponent(url.split('/agents/')[1]);
        const profile = clone(fixture.profiles[aiId] || {});
        delete profile.providerKind;
        delete profile.branch;
        delete profile.workspace;
        delete profile.assignment;
        delete profile.providerAgentId;
        if (aiId !== 'codex-local') {
          delete profile.revision;
          delete profile.source;
          delete profile.updatedAt;
        }
        payload = {
          ok: true,
          scope: aiId === 'codex-local' ? 'self' : 'public',
          profile,
          hr: {
            aiId,
            name: profile.name,
            status: 'active',
            availability: aiId === 'codex-local' ? 'available' : 'busy',
            publicWorkSummary: clone((fixture.details[aiId] || {}).publicWorkSummary || []),
          },
        };
      } else if (url === '/api/agent-management/browser/profile/mutate') {
        return mutate(body);
      } else if (url === '/api/agent-management/browser/profile/undo') {
        return undo(body);
      } else if (url === '/api/agent-management/browser/access-log/self') {
        payload = { ok: true, items: [] };
      } else {
        payload = { ok: false, code: 'agent_management_route_denied' };
        status = 403;
      }
      runtime.browserResponses.push(clone(payload));
      return json(payload, status);
    };
    function load(source) {
      const script = document.createElement('script');
      script.textContent = source;
      document.body.appendChild(script);
    }
    load(${JSON.stringify(sources.shell)});
    load(${JSON.stringify(sources.configuration)});
    load(${JSON.stringify(sources.humanResources)});
    load(${JSON.stringify(sources.adapters)});
    document.getElementById('open-agent-management').onclick = () => AgentManagement.open('configuration');
    document.getElementById('agent-management-close').onclick = () => AgentManagement.close();
    document.querySelectorAll('[data-agent-management-tab]').forEach(button => {
      button.onclick = () => AgentManagement.switchTab(button.dataset.agentManagementTab);
    });
    return Boolean(window.AgentManagement && window.AgentConfiguration && window.HumanResources);
  })()`);

  await evaluate("document.getElementById('open-agent-management').click()");
  await waitFor("AgentManagement.state.audience.kind === 'human' && document.querySelector('.agent-configuration')");
  const initial = await evaluate(`(() => ({
    audience: AgentManagement.state.audience.kind,
    roster: document.querySelectorAll('.am-roster-item').length,
    closeControls: document.querySelectorAll('#agent-management-close').length,
    restricted: document.querySelectorAll('.ac-restricted').length,
  }))()`);
  assert.deepEqual(initial, {
    audience: 'human',
    roster: 2,
    closeControls: 1,
    restricted: 1,
  });

  await evaluate("AgentManagement.selectAgent('hermes-default'); AgentManagement.switchTab('humanResources')");
  await waitFor("AgentManagement.state.activeTab === 'humanResources' && HumanResources.state.selectedAgentId === 'hermes-default'");
  assert.equal(await evaluate("AgentManagement.state.selectedAiId"), 'hermes-default');
  await evaluate("AgentManagement.switchTab('configuration')");
  await waitFor("document.querySelector('.agent-configuration') && AgentManagement.state.selectedAiId === 'hermes-default'");

  await evaluate(`(() => {
    const input = document.querySelector('[data-profile-field="name"]');
    input.value = 'Hermes Updated';
    input.dispatchEvent(new Event('input', { bubbles: true }));
    input.dispatchEvent(new Event('blur', { bubbles: true }));
  })()`);
  await waitFor("document.querySelector('[data-field-status=\"name\"]')?.classList.contains('saved')");
  assert.equal(await evaluate("__amFixture.data.profiles['hermes-default'].name"), 'Hermes Updated');
  await evaluate("document.querySelector('[data-undo-field=\"name\"]').click()");
  await waitFor("__amFixture.data.profiles['hermes-default'].name === 'Hermes' && AgentConfiguration.state.saveState.get('name')?.state === 'undone'");

  await evaluate(`(() => {
    __amFixture.conflictNext = true;
    const input = document.querySelector('[data-profile-field="introduction"]');
    input.value = 'Stale value';
    input.dispatchEvent(new Event('input', { bubbles: true }));
    input.dispatchEvent(new Event('blur', { bubbles: true }));
  })()`);
  await waitFor("AgentConfiguration.state.saveState.get('introduction')?.state === 'conflict'");
  assert.equal(
    await evaluate("document.querySelector('[data-field-status=\"introduction\"]')?.classList.contains('conflict')"),
    true,
  );

  const keyboardSelector = await evaluate(`(() => {
    const toggle = document.querySelector('[data-appearance-selector] .ac-selector-current');
    toggle.click();
    const options = [...document.querySelectorAll('[data-appearance-selector] [data-appearance-option]')];
    const selected = options.find(option => option.getAttribute('aria-selected') === 'true') || options[0];
    selected.focus();
    selected.dispatchEvent(new KeyboardEvent('keydown', { key: 'ArrowRight', bubbles: true }));
    const moved = document.activeElement !== selected;
    document.activeElement.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }));
    return { moved, returned: document.activeElement === toggle };
  })()`);
  assert.deepEqual(keyboardSelector, { moved: true, returned: true });

  await evaluate("document.querySelector('[data-high-risk-action=\"branch\"]').click()");
  const impact = await evaluate(`(() => ({
    dialog: Boolean(document.querySelector('.ac-confirm-dialog')),
    labels: [...document.querySelectorAll('#ac-confirm-impact dt')].map(node => node.textContent),
    genericSave: [...document.querySelectorAll('button')].some(button => /save configuration/i.test(button.textContent)),
  }))()`);
  assert.deepEqual(impact, {
    dialog: true,
    labels: ['Agent', 'Action', 'Before', 'After'],
    genericSave: false,
  });
  await evaluate(`(() => {
    const input = document.querySelector('[data-high-risk-value]');
    input.value = 'operations';
    __amFixture.denyNextCommand = true;
    document.querySelector('[data-confirm-submit]').click();
  })()`);
  await waitFor("__amFixture.requests.filter(item => item.url === '/api/agent-management/commands').length === 1");
  await new Promise((resolve) => setTimeout(resolve, 100));
  await waitFor("Boolean(document.querySelector('.ac-confirm-dialog')) && !document.querySelector('[data-confirm-submit]')?.disabled");
  assert.match(
    await evaluate("document.querySelector('.ac-confirm-error')?.textContent || ''"),
    /agent_management_command_denied/,
  );
  assert.equal(await evaluate("Boolean(document.querySelector('.ac-confirm-dialog'))"), true);
  await evaluate("document.querySelector('[data-confirm-submit]').click()");
  await waitFor("!document.querySelector('.ac-confirm-dialog')");
  const highRiskRequests = await evaluate(`__amFixture.requests
    .filter(item => item.url.includes('/api/agent-management/confirmations') || item.url.includes('/api/agent-management/commands'))
    .map(item => ({ url: item.url, body: item.body }))`);
  assert.equal(highRiskRequests.length, 4);
  assert.deepEqual(highRiskRequests[0].body, {
    targetAiId: 'hermes-default',
    action: 'branch',
    before: { branch: 'research' },
    after: { branch: 'operations' },
    revision: 2,
  });
  assert.deepEqual(highRiskRequests[1].body, Object.assign({}, highRiskRequests[0].body, {
    challengeToken: 'challenge-000000000000000000000001',
  }));
  assert.deepEqual(highRiskRequests[2].body, highRiskRequests[0].body);
  assert.deepEqual(highRiskRequests[3].body, Object.assign({}, highRiskRequests[0].body, {
    challengeToken: 'challenge-000000000000000000000002',
  }));

  await evaluate("AgentManagement.switchTab('humanResources'); HumanResources.selectAgent('')");
  await waitFor("document.querySelector('.hr-overview')");
  await evaluate("HumanResources.runCommand('sync')");
  await waitFor("HumanResources.helpers.activeCommands(HumanResources.state.overview).length === 1");
  await evaluate("HumanResources.selectAgent('')");
  await waitFor("document.querySelector('.hr-command-panel')");
  assert.equal(await evaluate("document.querySelector('[onclick*=\"sync\"]')?.disabled"), true);
  await evaluate("__amFixture.data.overview.activeCommands = []; HumanResources.reload()");
  await waitFor("HumanResources.helpers.activeCommands(HumanResources.state.overview).length === 0");
  await evaluate("__amFixture.failExport = true; HumanResources.selectAgent(''); HumanResources.reload()");
  await waitFor("document.querySelector('.hr-degraded-banner')");
  assert.equal(await evaluate("Boolean(HumanResources.state.overview)"), true);
  assert.equal(await evaluate("AgentManagement.state.open"), true);
  const humanScreenshot = await captureScreenshot('agent-management-human');
  await evaluate("__amFixture.failExport = false; AgentManagement.setRoster([]); AgentManagement.switchTab('configuration')");
  await waitFor("document.querySelector('.am-empty')");
  assert.equal(await evaluate("document.querySelectorAll('.am-roster-item').length"), 0);

  await waitFor("!AgentManagement.state.bootstrapping");
  await evaluate(`(() => {
    __amFixture.mode = 'agent';
    __amFixture.requests = [];
    __amFixture.browserResponses = [];
    AgentConfiguration.state.profiles.clear();
    AgentManagement.setAdapters({
      human: null,
      agent: AgentManagementAdapters.createAgentAdapter(),
    });
  })()`);
  await waitFor("!AgentManagement.state.bootstrapping");
  await evaluate("AgentManagement.bootstrapAudience()");
  await waitFor("AgentManagement.state.audience.kind === 'agent' && AgentManagement.state.selectedAiId === 'codex-local'");
  await waitFor("document.querySelector('[data-profile-field=\"name\"]')");
  await evaluate(`(() => {
    const input = document.querySelector('[data-profile-field="name"]');
    input.value = 'Codex Self Updated';
    input.dispatchEvent(new Event('input', { bubbles: true }));
    input.dispatchEvent(new Event('blur', { bubbles: true }));
  })()`);
  await waitFor("__amFixture.data.profiles['codex-local'].name === 'Codex Self Updated'");
  await evaluate("document.querySelector('[data-undo-field=\"name\"]').click()");
  await waitFor("__amFixture.data.profiles['codex-local'].name === 'Codex Local'");
  await evaluate("AgentManagement.selectAgent('hermes-default'); AgentManagement.switchTab('configuration')");
  await waitFor("document.querySelector('.agent-configuration')");
  const agentProjection = await evaluate(`(() => ({
    audience: AgentManagement.state.audience.kind,
    restrictedDom: document.querySelectorAll('.ac-restricted, [data-restricted-field]').length,
    editableFields: document.querySelectorAll('[data-profile-field]').length,
    publicProfileKeys: Object.keys(
      __amFixture.browserResponses.find(item => item.scope === 'public')?.profile || {}
    ).sort(),
    hiddenText: document.body.textContent.includes(__amFixture.data.hiddenRestrictedSentinel),
    humanRoutes: __amFixture.requests.filter(item => item.url.startsWith('/api/human-resources')).length,
    responseContainsHidden: JSON.stringify(__amFixture.browserResponses).includes(__amFixture.data.hiddenRestrictedSentinel),
  }))()`);
  assert.deepEqual(agentProjection, {
    audience: 'agent',
    restrictedDom: 0,
    editableFields: 0,
    publicProfileKeys: [
      'aiId',
      'appearance',
      'introduction',
      'name',
      'responsibilities',
      'specialties',
    ],
    hiddenText: false,
    humanRoutes: 0,
    responseContainsHidden: false,
  });
  await evaluate("AgentManagement.switchTab('humanResources')");
  await waitFor("HumanResources.state.detail?.publicWorkSummary?.includes('Completed market research')");
  assert.equal(await evaluate("document.body.textContent.includes('Hermes')"), true);
  assert.equal(
    await evaluate("document.body.textContent.includes(__amFixture.data.hiddenRestrictedSentinel)"),
    false,
  );
  const agentScreenshot = await captureScreenshot('agent-management-agent');
  await evaluate("AgentManagement.switchTab('configuration')");
  await waitFor("AgentManagement.state.activeTab === 'configuration'");
  await evaluate(`(() => {
    __amFixture.mode = 'restarted';
    AgentManagement.state.tabs.configuration.error = '';
  })()`);
  assert.equal(await evaluate("AgentManagement.bootstrapAudience()"), false);
  await waitFor("document.querySelector('[role=\"alert\"]')?.textContent.includes('session expired')");
  const restartProjection = await evaluate(`(() => ({
    error: AgentManagement.state.tabs.configuration.error,
    alert: document.querySelector('[role="alert"]')?.textContent || '',
    restrictedDom: document.querySelectorAll('.ac-restricted, [data-restricted-field]').length,
  }))()`);
  assert.deepEqual(restartProjection, {
    error: 'agent_management_session_required',
    alert: 'Agent Management session expired. Reopen it from Virtual Office.',
    restrictedDom: 0,
  });
  const restartScreenshot = await captureScreenshot('agent-management-session-expired');

  console.log(JSON.stringify({
    ok: true,
    initial,
    keyboardSelector,
    impact,
    agentProjection,
    restartProjection,
    fixtureUrl,
    screenshots: [humanScreenshot, agentScreenshot, restartScreenshot].filter(Boolean),
  }, null, 2));
} finally {
  try {
    ws.close();
  } catch {}
  await closeCdpPage(page);
  fixtureServer.closeAllConnections();
  await new Promise((resolve) => fixtureServer.close(resolve));
}
