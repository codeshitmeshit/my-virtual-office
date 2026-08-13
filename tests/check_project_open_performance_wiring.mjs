import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { join } from 'node:path';

const root = process.cwd();
const projectsJs = readFileSync(join(root, 'app/projects.js'), 'utf8');
const gameJs = readFileSync(join(root, 'app/game.js'), 'utf8');
const browserPanelJs = readFileSync(join(root, 'app/browser-panel.js'), 'utf8');
const dashboardRealtimeJs = readFileSync(join(root, 'app/dashboard-realtime.js'), 'utf8');

assert.ok(
  projectsJs.includes('scheduleProjectIdleWork(populateBoardScoreboard)')
    && projectsJs.includes('scheduleProjectIdleWork(() => loadProjectBoardAuxiliaryData(id), 80)'),
  'project open should render the board before auxiliary project panel fetches'
);

assert.ok(
  projectsJs.includes('listProjectsAbort')
    && projectsJs.includes('sidebarProjectsAbort')
    && projectsJs.includes("Object.assign({ priority: 'high' }")
    && projectsJs.includes('abortController(state.listProjectsAbort)')
    && projectsJs.includes('abortController(state.sidebarProjectsAbort)'),
  'opening a project should cancel lower-priority project list refreshes and prioritize the detail fetch'
);

assert.ok(
  projectsJs.includes("scheduleProjectIdleWork(initSidebar, 700)")
    && projectsJs.includes("if (state.listProjectsAbort !== controller || state.view !== 'list') return;"),
  'initial sidebar/list refreshes should be deferred and must not overwrite the board after navigation'
);

assert.ok(
  !projectsJs.includes('await Promise.allSettled(jobs);'),
  'auxiliary project panel fetches should not be joined on the slowest request'
);

assert.ok(
  projectsJs.includes('{ lightweight: true, skipAuxiliary: true }'),
  'orchestration refreshes should skip auxiliary meeting reloads'
);

assert.ok(
  gameJs.includes('setTimeout(function () {\n    pollStatus();')
    && gameJs.includes('setTimeout(function () {\n    pollAgentChat();'),
  'global status/chat polling should be delayed until after startup'
);

assert.ok(
  gameJs.includes('var _statusPollInFlight = false;')
    && gameJs.includes('var _agentChatPollInFlight = false;')
    && gameJs.includes("typeof document.hidden === 'boolean' && document.hidden"),
  'status and agent chat polling should not overlap or run in hidden tabs'
);

assert.ok(
  browserPanelJs.includes('setTimeout(_initBrowserPanel, 1400)')
    && browserPanelJs.includes('setTimeout(() => {\n    pollBrowserController();'),
  'browser panel background polling should be delayed until after startup'
);

assert.ok(
  browserPanelJs.includes('let _browserUrlPollInFlight = false;')
    && browserPanelJs.includes('let _browserControllerPollInFlight = false;')
    && browserPanelJs.includes("typeof document.hidden === 'boolean' && document.hidden"),
  'browser panel polling should not overlap or run in hidden tabs'
);

assert.ok(
  dashboardRealtimeJs.includes('function connectAfterStartup()')
    && dashboardRealtimeJs.includes('setTimeout(connect, 1800);')
    && dashboardRealtimeJs.includes('VOManagementSessionReadiness.whenAuthenticated'),
  'dashboard realtime connection should be delayed until after startup'
);

console.log('project open performance wiring checks passed');
