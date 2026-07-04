import fs from 'fs';
import assert from 'assert';

const index = fs.readFileSync('app/index.html', 'utf8');
const js = fs.readFileSync('app/dashboard-realtime.js', 'utf8');
const py = fs.readFileSync('app/dashboard_realtime.py', 'utf8');
const game = fs.readFileSync('app/game.js', 'utf8');
const server = fs.readFileSync('app/server.py', 'utf8');
const style = fs.readFileSync('app/style.css', 'utf8');
const zh = fs.readFileSync('app/locales/zh.json', 'utf8');

assert.ok(index.includes('dashboard-realtime.js'), 'index should load the focused dashboard realtime JS module');
assert.ok(js.includes("new EventSource('/api/dashboard/events')"), 'dashboard realtime JS should own the SSE connection');
assert.ok(js.includes('Polling fallback') || js.includes('polling fallback'), 'dashboard realtime JS should expose polling fallback mode');
assert.ok(js.includes('dashboardApplyStatusSnapshot'), 'dashboard realtime JS should use the thin game.js status hook');
assert.ok(js.includes('dashboard.projects'), 'dashboard realtime JS should listen for project summary changes');
assert.ok(js.includes('dashboardApplyProjectSummaries'), 'dashboard realtime JS should use the thin projects.js summary hook');
assert.ok(py.includes('class DashboardRealtimeStream'), 'backend focused module should own the stream class');
assert.ok(py.includes('def build_dashboard_snapshot'), 'backend focused module should own snapshot shaping');
assert.ok(py.includes('"projects": _signature(project_projection)'), 'backend snapshot should sign project summaries');
assert.ok(server.includes('DashboardRealtimeStream('), 'server.py should wire the route to the focused backend module');
assert.ok(server.includes('projects_loader='), 'server.py should feed project summaries into dashboard SSE');
assert.ok(game.includes('window.dashboardApplyStatusSnapshot = applyStatusSnapshot'), 'game.js should expose a thin status hook');
assert.ok(style.includes('.dashboard-realtime-status'), 'dashboard realtime mode indicator should have styles');
assert.ok(zh.includes('控制面板：SSE 实时连接'), 'Chinese UI copy should identify SSE mode');

console.log('dashboard realtime static checks passed');
