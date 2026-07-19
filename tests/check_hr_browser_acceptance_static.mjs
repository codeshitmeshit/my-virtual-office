import assert from 'node:assert/strict';
import fs from 'node:fs';


const script = fs.readFileSync('tests/hr_ui_browser_acceptance.mjs', 'utf8');
const fixture = JSON.parse(fs.readFileSync('tests/fixtures/hr-browser-acceptance.json', 'utf8'));

assert.ok(script.includes("from './cdp-test-utils.mjs'"));
assert.ok(!script.includes('127.0.0.1:9224'), 'shared CDP configuration must be used');
for (const marker of [
  'btn-human-resources',
  'hr-agent-row',
  'hr-assessment-card',
  "loadMore('reports')",
  "loadMore('access')",
  "runCommand('pause')",
  "runCommand('resume')",
  'openDailySync',
  'submitDailySync',
  'hr-selection-dialog',
  'failExport',
  'failDetail',
  'hr-degraded-banner',
]) {
  assert.ok(script.includes(marker), `missing HR browser acceptance marker: ${marker}`);
}
assert.equal(fixture.agents.length, 2);
assert.ok(fixture.agent.reports[0].rawResponse);
assert.ok(fixture.agent.reports[0].normalized);
assert.equal(fixture.agent.assessments.length, 1);
assert.ok(fixture.agent.accessNextCursor);
assert.ok(fixture.reportPage.reports.length);
assert.ok(fixture.accessPage.accessHistory.length);

console.log('Human Resources deterministic browser acceptance fixture checks passed');
