#!/usr/bin/env node
import assert from 'node:assert/strict';
import { spawnSync } from 'node:child_process';
import { writeFileSync } from 'node:fs';
import {
  appURL,
  closeCdpPage,
  createCdpPage,
  cdpVersion,
} from './cdp-test-utils.mjs';

const managementToken = process.env.VO_MANAGEMENT_TOKEN || '';

if (typeof WebSocket === 'undefined') {
  const child = spawnSync(
    process.execPath,
    ['--experimental-websocket', ...process.argv.slice(1)],
    { env: process.env, stdio: 'inherit' },
  );
  process.exit(child.status ?? 1);
}

await cdpVersion();
const page = await createCdpPage(appURL);
const socket = new WebSocket(page.webSocketDebuggerUrl);
await new Promise((resolve, reject) => {
  socket.addEventListener('open', resolve, { once: true });
  socket.addEventListener('error', reject, { once: true });
});

let sequence = 0;
const pending = new Map();
socket.addEventListener('message', (event) => {
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
  socket.send(JSON.stringify({ id, method, params }));
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

async function waitFor(expression, timeoutMs = 12000) {
  const started = Date.now();
  while (Date.now() - started < timeoutMs) {
    if (await evaluate(expression)) return;
    await new Promise((resolve) => setTimeout(resolve, 80));
  }
  throw new Error(`Timed out waiting for ${expression}`);
}

try {
  await send('Page.enable');
  await send('Runtime.enable');
  await waitFor(`document.readyState === 'complete' && Boolean(window.AgentManagement)`);

  const initial = await evaluate(`(() => {
    const modal = document.getElementById('agentManagementModal');
    return {
      open: window.AgentManagement.state.open,
      hiddenClass: modal.classList.contains('hidden'),
      display: getComputedStyle(modal).display,
    };
  })()`);
  assert.deepEqual(initial, {
    open: false,
    hiddenClass: true,
    display: 'none',
  });

  await evaluate(`window.i18n.setLanguage('zh')`);
  await evaluate(`document.getElementById('btn-agent-settings').click()`);
  await waitFor(`window.AgentManagement.state.open &&
    getComputedStyle(document.getElementById('agentManagementModal')).display !== 'none'`);
  await waitFor(`Boolean(document.getElementById('management-token-dialog')) ||
    Boolean(document.querySelector('#agent-management-panel .ac-hero')) ||
    Boolean(document.querySelector('#agent-management-panel .ac-error'))`);

  const tokenDialogVisible = await evaluate(
    `Boolean(document.getElementById('management-token-dialog'))`
  );
  if (tokenDialogVisible) {
    const layers = await evaluate(`(() => ({
      agentManagement: Number(getComputedStyle(
        document.getElementById('agentManagementModal')
      ).zIndex),
      managementToken: Number(getComputedStyle(
        document.getElementById('management-token-dialog')
      ).zIndex),
    }))()`);
    assert.ok(
      layers.managementToken > layers.agentManagement,
      `management token dialog must be above Agent Management: ${JSON.stringify(layers)}`,
    );
    if (managementToken) {
      await evaluate(`(() => {
        const input = document.getElementById('management-token-input');
        input.value = ${JSON.stringify(managementToken)};
        input.dispatchEvent(new Event('input', { bubbles: true }));
        document.querySelector(
          '#management-token-dialog [data-management-token-confirm]'
        ).click();
      })()`);
    } else {
      await evaluate(
        `document.querySelector('#management-token-dialog [data-management-token-cancel]').click()`
      );
    }
  }
  await waitFor(
    managementToken
      ? `Boolean(document.querySelector('#agent-management-panel .ac-hero'))`
      : `Boolean(document.querySelector('#agent-management-panel .ac-hero')) ||
        Boolean(document.querySelector('#agent-management-panel .ac-error'))`
  );
  if (managementToken && await evaluate(`Boolean(document.getElementById('management-token-dialog'))`)) {
    await evaluate(`(() => {
      const input = document.getElementById('management-token-input');
      input.value = ${JSON.stringify(managementToken)};
      input.dispatchEvent(new Event('input', { bubbles: true }));
      document.querySelector(
        '#management-token-dialog [data-management-token-confirm]'
      ).click();
    })()`);
  }
  if (await evaluate(`Boolean(document.querySelector('#agent-management-panel .ac-hero'))`)) {
    if (managementToken) {
      await waitFor(`Boolean(document.querySelector('#agent-management-panel .ac-selector-current')) ||
        Boolean(document.getElementById('management-token-dialog'))`);
      if (await evaluate(`Boolean(document.getElementById('management-token-dialog'))`)) {
        await evaluate(`(() => {
          const input = document.getElementById('management-token-input');
          input.value = ${JSON.stringify(managementToken)};
          input.dispatchEvent(new Event('input', { bubbles: true }));
          document.querySelector(
            '#management-token-dialog [data-management-token-confirm]'
          ).click();
        })()`);
      }
    }
    await waitFor(`Boolean(document.querySelector('#agent-management-panel .ac-selector-current'))`);
    const visualContract = await evaluate(`(() => {
      const panel = document.getElementById('agent-management-panel');
      const config = panel.querySelector('.agent-configuration');
      const columns = panel.querySelector('.ac-profile-columns');
      const primary = panel.querySelector('.ac-profile-primary');
      const appearance = panel.querySelector('.ac-appearance-card');
      const avatar = panel.querySelector('[data-agent-appearance-preview]');
      const pixels = avatar.getContext('2d').getImageData(0, 0, avatar.width, avatar.height).data;
      let opaquePixels = 0;
      for (let index = 3; index < pixels.length; index += 4) {
        if (pixels[index] > 0) opaquePixels += 1;
      }
      const panelRect = panel.getBoundingClientRect();
      const configRect = config.getBoundingClientRect();
      return {
        activeTab: panel.getAttribute('data-active-tab'),
        overflowY: getComputedStyle(panel).overflowY,
        contentFits: configRect.bottom <= panelRect.bottom + 1,
        panelHeight: Math.round(panelRect.height),
        configHeight: Math.round(configRect.height),
        overflowBottom: Math.round(configRect.bottom - panelRect.bottom),
        summaries: panel.querySelectorAll('.ac-summary-item').length,
        appearanceGroups: panel.querySelectorAll('.ac-appearance-group').length,
        appearanceOverflowY: getComputedStyle(appearance).overflowY,
        appearanceScrollRange: appearance.scrollHeight - appearance.clientHeight,
        fontFamily: getComputedStyle(config).fontFamily,
        fontSize: getComputedStyle(config).fontSize,
        appearanceHeadingSize: getComputedStyle(
          panel.querySelector('.ac-appearance-heading strong')
        ).fontSize,
        appearanceGroupSize: getComputedStyle(
          panel.querySelector('.ac-appearance-group h5')
        ).fontSize,
        appearanceFieldSize: getComputedStyle(
          panel.querySelector('.ac-selector-label')
        ).fontSize,
        avatarWidth: avatar.width,
        avatarHeight: avatar.height,
        opaquePixels,
        columnsWidth: Math.round(columns.getBoundingClientRect().width),
        primaryWidth: Math.round(primary.getBoundingClientRect().width),
        appearanceWidth: Math.round(appearance.getBoundingClientRect().width),
      };
    })()`);
    assert.equal(visualContract.activeTab, 'configuration');
    assert.equal(visualContract.overflowY, 'hidden');
    assert.equal(visualContract.contentFits, true, JSON.stringify(visualContract));
    assert.equal(visualContract.summaries, 0);
    assert.equal(visualContract.appearanceGroups, 4);
    assert.equal(visualContract.appearanceOverflowY, 'auto');
    assert.ok(visualContract.appearanceScrollRange >= 0, JSON.stringify(visualContract));
    assert.match(visualContract.fontFamily, /Pixel/i);
    assert.equal(visualContract.fontSize, '7px');
    assert.equal(visualContract.appearanceHeadingSize, '10px');
    assert.equal(visualContract.appearanceGroupSize, '8px');
    assert.equal(visualContract.appearanceFieldSize, '7px');
    assert.equal(visualContract.avatarWidth, 80);
    assert.equal(visualContract.avatarHeight, 104);
    assert.ok(visualContract.opaquePixels > 500, JSON.stringify(visualContract));
    assert.ok(visualContract.primaryWidth >= 430, JSON.stringify(visualContract));
    assert.ok(
      visualContract.appearanceWidth >= 330 && visualContract.appearanceWidth <= 410,
      JSON.stringify(visualContract),
    );

    const initialDropdowns = await evaluate(`(() => {
      const popovers = [...document.querySelectorAll('.ac-option-popover')];
      return {
        total: popovers.length,
        visible: popovers.filter(node => getComputedStyle(node).display !== 'none').length,
      };
    })()`);
    assert.ok(initialDropdowns.total > 1, 'appearance dropdowns must be rendered');
    assert.equal(initialDropdowns.visible, 0, 'appearance dropdowns must start collapsed');

    await evaluate(`document.querySelectorAll('.ac-selector-current')[0].click()`);
    assert.equal(
      await evaluate(`[...document.querySelectorAll('.ac-option-popover')]
        .filter(node => getComputedStyle(node).display !== 'none').length`),
      1,
      'opening one appearance dropdown must reveal exactly one menu',
    );

    await evaluate(`document.querySelectorAll('.ac-selector-current')[1].click()`);
    const switchedDropdowns = await evaluate(`(() => {
      const toggles = [...document.querySelectorAll('.ac-selector-current')];
      const popovers = [...document.querySelectorAll('.ac-option-popover')];
      return {
        expanded: toggles.map(node => node.getAttribute('aria-expanded')),
        visible: popovers.filter(node => getComputedStyle(node).display !== 'none').length,
      };
    })()`);
    assert.equal(switchedDropdowns.visible, 1);
    assert.equal(switchedDropdowns.expanded[0], 'false');
    assert.equal(switchedDropdowns.expanded[1], 'true');
    const localizedHair = await evaluate(`(() => {
      const selector = document.querySelectorAll('[data-appearance-selector="hairStyle"]')[0];
      return {
        current: selector.querySelector('.ac-selector-current strong').textContent.trim(),
        labels: [...selector.querySelectorAll('[data-appearance-option] > span:last-child')]
          .map(node => node.textContent.trim()),
        rawValues: [...selector.querySelectorAll('[data-appearance-option]')]
          .map(node => node.getAttribute('data-appearance-option')),
      };
    })()`);
    assert.ok(localizedHair.labels.includes('光头'), JSON.stringify(localizedHair));
    assert.ok(localizedHair.labels.includes('中发'), JSON.stringify(localizedHair));
    assert.ok(!localizedHair.labels.includes('bald'), JSON.stringify(localizedHair));
    assert.ok(localizedHair.rawValues.includes('bald'), JSON.stringify(localizedHair));

    await evaluate(`(() => {
      const appearance = document.querySelector('.ac-appearance-card');
      appearance.scrollTop = appearance.scrollHeight;
      const toggles = document.querySelectorAll('.ac-selector-current');
      toggles.item(toggles.length - 1).click();
    })()`);
    const terminalDropdown = await evaluate(`(() => {
      const panel = document.getElementById('agent-management-panel');
      const appearance = document.querySelector('.ac-appearance-card');
      const selectors = [...document.querySelectorAll('.ac-selector')];
      const selector = selectors[selectors.length - 1];
      const menu = selector.querySelector('.ac-option-popover');
      const panelRect = panel.getBoundingClientRect();
      const menuRect = menu.getBoundingClientRect();
      return {
        opensUpward: selector.classList.contains('opens-upward'),
        menuFits: menuRect.top >= panelRect.top && menuRect.bottom <= panelRect.bottom,
        panelOverflowY: getComputedStyle(panel).overflowY,
        appearanceScrolled:
          appearance.scrollHeight <= appearance.clientHeight || appearance.scrollTop > 0,
        appearanceAtBottom:
          appearance.scrollTop + appearance.clientHeight >= appearance.scrollHeight - 1,
      };
    })()`);
    assert.equal(terminalDropdown.opensUpward, true, JSON.stringify(terminalDropdown));
    assert.equal(terminalDropdown.menuFits, true, JSON.stringify(terminalDropdown));
    assert.equal(terminalDropdown.panelOverflowY, 'hidden');
    assert.equal(terminalDropdown.appearanceScrolled, true, JSON.stringify(terminalDropdown));
    assert.equal(terminalDropdown.appearanceAtBottom, true, JSON.stringify(terminalDropdown));

    const screenshotPath = process.env.AGENT_MANAGEMENT_LIVE_SCREENSHOT || '';
    if (screenshotPath) {
      const capture = await send('Page.captureScreenshot', {
        format: 'png',
        captureBeyondViewport: false,
      });
      writeFileSync(screenshotPath, Buffer.from(capture.data, 'base64'));
    }
  }

  await evaluate(`window.AgentManagement.switchTab('humanResources')`);
  await waitFor(`Boolean(document.querySelector(
    '#agent-management-panel .hr-shell-embedded'
  ))`);
  assert.equal(
    await evaluate(`document.getElementById('agent-management-panel').textContent
      .includes('正在加载人事运营')`),
    false,
    'live Human Resources entry must replace the loading placeholder',
  );
  await waitFor(`window.HumanResources.state.loading === false`);

  // A fresh development profile may legitimately have an empty roster. Keep
  // the live entry assertion above, then use representative records to verify
  // the complete visual contract rather than skipping detail-only geometry.
  await evaluate(`(() => {
    const now = new Date().toISOString();
    HumanResources.state.detailSequence += 1;
    HumanResources.state.agents = [{
      aiId: 'codex-local',
      name: 'Codex',
      status: 'active',
      availability: 'available',
    }];
    HumanResources.state.overview = {
      agentTotal: 1,
      localDate: '2026-07-25',
      availabilityCounts: { available: 1 },
      hr: { name: 'HR', status: 'active' },
      reportSchedule: { enabled: true, dailyTime: '18:00' },
      activeCommands: [],
    };
    HumanResources.state.selectedAgentId = 'codex-local';
    HumanResources.state.detailLoading = false;
    HumanResources.state.detail = {
      aiId: 'codex-local',
      name: 'Codex',
      introduction: 'Backend / Reviewer',
      status: 'active',
      availability: 'available',
      agentKind: 'project',
      providerKind: 'codex',
      introductionProvenance: { source: 'vo-roster' },
      workflowState: 'submitted',
      identityHistory: [{
        aiId: 'codex-local',
        name: 'Codex',
        status: 'active',
        source: 'vo-roster',
        observedAt: now,
      }],
      reports: [{
        id: 'report-1',
        localDate: '2026-07-25',
        revision: 2,
        submissionState: 'submitted',
        rawResponse: 'Completed Agent Management layout regression.',
        normalized: { achievements: ['HR layout regression'], blockers: [] },
        submittedAt: now,
      }],
      assessments: [{
        id: 'assessment-1',
        localDate: '2026-07-25',
        version: 2,
        isCurrent: true,
        status: 'complete',
        workload: 'appropriate',
        workloadScore: 8,
        rationale: 'Delivery evidence is complete.',
        principalContributions: ['Completed merged HR frontend validation'],
        strengths: ['Clear evidence'],
        blockers: [],
        improvements: ['Continue visual regression'],
        runtimeDiagnosis: 'Healthy',
        updatedAt: now,
      }],
      accessHistory: [{
        id: 'access-1',
        viewerName: 'HR',
        scope: 'public',
        viewedAt: now,
      }],
    };
    HumanResources.state.detail.reports = Array.from({ length: 3 }, (_, index) => ({
      ...HumanResources.state.detail.reports[0],
      id: 'report-' + (index + 1),
      revision: 3 - index,
    }));
    HumanResources.state.detail.assessments = Array.from({ length: 3 }, (_, index) => ({
      ...HumanResources.state.detail.assessments[0],
      id: 'assessment-' + (index + 1),
      version: 3 - index,
      isCurrent: index === 0,
    }));
    HumanResources.render();
  })()`);
  await waitFor(`Boolean(document.querySelector(
    '#agent-management-panel .hr-detail-hero'
  ))`);
  const humanResourcesContract = await evaluate(`(() => {
    const panel = document.getElementById('agent-management-panel');
    const shell = panel.querySelector('.hr-shell-embedded');
    const detail = panel.querySelector('.hr-agent-detail');
    const metadata = panel.querySelector('.hr-detail-metadata');
    const report = panel.querySelector('.hr-reports-section');
    const assessment = panel.querySelector('.hr-assessments-section');
    const heroName = panel.querySelector('.hr-detail-hero h3');
    const sectionHeading = panel.querySelector('.hr-detail-section h4');
    const summaryValue = panel.querySelector('.hr-summary-card strong');
    const metadataColumns = metadata
      ? getComputedStyle(metadata).gridTemplateColumns.split(' ').filter(Boolean).length
      : 0;
    const panelRect = panel.getBoundingClientRect();
    const shellRect = shell.getBoundingClientRect();
    const detailRect = detail.getBoundingClientRect();
    return {
      activeTab: panel.getAttribute('data-active-tab'),
      placeholder: panel.textContent.includes('正在加载人事运营') ||
        panel.textContent.includes('正在加载人事管理'),
      shellFontFamily: getComputedStyle(shell).fontFamily,
      shellFontSize: getComputedStyle(shell).fontSize,
      panelOverflowY: getComputedStyle(panel).overflowY,
      detailOverflowY: getComputedStyle(detail).overflowY,
      detailScrollRange: detail.scrollHeight - detail.clientHeight,
      shellFillsPanel: Math.abs(shellRect.width - (panelRect.width - 24)) <= 2,
      detailFillsShell: Math.abs(detailRect.width - shellRect.width) <= 2,
      summaryCards: panel.querySelectorAll('.hr-summary-card').length,
      opsConsoles: panel.querySelectorAll('.hr-ops-console').length,
      metadataColumns,
      pairedRecords: !report || !assessment ||
        Math.abs(report.getBoundingClientRect().top - assessment.getBoundingClientRect().top) <= 1,
      heroNameSize: heroName ? getComputedStyle(heroName).fontSize : '',
      sectionHeadingSize: sectionHeading ? getComputedStyle(sectionHeading).fontSize : '',
      summaryValueSize: summaryValue ? getComputedStyle(summaryValue).fontSize : '',
    };
  })()`);
  assert.equal(humanResourcesContract.activeTab, 'humanResources');
  assert.equal(humanResourcesContract.placeholder, false, JSON.stringify(humanResourcesContract));
  assert.match(humanResourcesContract.shellFontFamily, /Pixel|Press Start/i);
  assert.equal(humanResourcesContract.shellFontSize, '7px');
  assert.equal(humanResourcesContract.panelOverflowY, 'hidden');
  assert.equal(humanResourcesContract.detailOverflowY, 'auto');
  assert.ok(humanResourcesContract.detailScrollRange > 0, JSON.stringify(humanResourcesContract));
  assert.equal(humanResourcesContract.shellFillsPanel, true, JSON.stringify(humanResourcesContract));
  assert.equal(humanResourcesContract.detailFillsShell, true, JSON.stringify(humanResourcesContract));
  assert.equal(humanResourcesContract.summaryCards, 4);
  assert.equal(humanResourcesContract.opsConsoles, 1);
  assert.equal(humanResourcesContract.metadataColumns, 4, JSON.stringify(humanResourcesContract));
  assert.equal(humanResourcesContract.pairedRecords, true, JSON.stringify(humanResourcesContract));
  assert.equal(humanResourcesContract.heroNameSize, '13px');
  assert.equal(humanResourcesContract.sectionHeadingSize, '9px');
  assert.equal(humanResourcesContract.summaryValueSize, '13px');

  const hrScreenshotPath = process.env.AGENT_MANAGEMENT_HR_SCREENSHOT || '';
  if (hrScreenshotPath) {
    const capture = await send('Page.captureScreenshot', {
      format: 'png',
      captureBeyondViewport: false,
    });
    writeFileSync(hrScreenshotPath, Buffer.from(capture.data, 'base64'));
  }

  await evaluate(`window.closeAgentManagement()`);
  const closed = await evaluate(`(() => {
    const modal = document.getElementById('agentManagementModal');
    return {
      open: window.AgentManagement.state.open,
      hiddenClass: modal.classList.contains('hidden'),
      display: getComputedStyle(modal).display,
    };
  })()`);
  assert.deepEqual(closed, {
    open: false,
    hiddenClass: true,
    display: 'none',
  });

  console.log('agent management live entry e2e ok');
} finally {
  socket.close();
  await closeCdpPage(page);
}
