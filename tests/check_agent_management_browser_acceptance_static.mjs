import assert from 'node:assert/strict';
import fs from 'node:fs';


const script = fs.readFileSync('tests/agent_management_browser_acceptance.mjs', 'utf8');
const fixture = JSON.parse(
  fs.readFileSync('tests/fixtures/agent-management-browser.json', 'utf8'),
);

for (const marker of [
  "from './cdp-test-utils.mjs'",
  'AgentManagement.selectAgent',
  "AgentManagement.switchTab('humanResources')",
  'agent_profile_revision_conflict',
  "document.querySelector('[data-undo-field",
  "document.querySelector('[data-high-risk-action",
  "HumanResources.runCommand('sync')",
  'hr-degraded-banner',
  'restrictedDom',
  'responseContainsHidden',
  'closeControls',
]) {
  assert.ok(script.includes(marker), `browser acceptance is missing ${marker}`);
}
assert.ok(!script.includes('127.0.0.1:9224'), 'shared CDP configuration must be used');
assert.match(fixture.hiddenRestrictedSentinel, /^SECRET_/);
assert.equal(fixture.agents.length, 2);
assert.equal(Object.keys(fixture.profiles).length, 2);
console.log('agent management browser acceptance static contract ok');
