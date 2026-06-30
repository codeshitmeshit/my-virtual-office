import assert from 'node:assert/strict';
import fs from 'node:fs';

const game = fs.readFileSync('app/game.js', 'utf8');

assert.ok(game.includes('function _agentWorkspaceProjectMeta'), 'project context meta helper should exist');
assert.ok(game.includes('function _agentWorkspaceProjectBadges'), 'project context badge helper should exist');
assert.ok(game.includes('agent-workspace-project-card'), 'project cards should have a dedicated read-only card class');
assert.ok(game.includes('Meeting blocker:'), 'project cards should surface meeting blocker context');
assert.ok(game.includes('projectExecutionFlowStopReason'), 'project cards should surface project execution flow stop reason');

const projectCardsStart = game.indexOf('<div class="agent-workspace-card" style="margin-top:10px"><h3>Project Cards</h3>');
assert.notEqual(projectCardsStart, -1, 'project cards render block should exist');
const projectCardsEnd = game.indexOf("}) + '</div>';", projectCardsStart);
assert.ok(projectCardsEnd > projectCardsStart, 'project cards render block should be bounded');
const projectCardsBlock = game.slice(projectCardsStart, projectCardsEnd);

for (const action of ['startTask', 'completeTask', 'toggleTask', 'deleteTask']) {
  assert.ok(
    !projectCardsBlock.includes(`data-aw-action="${action}"`),
    `project cards must not expose ${action}`
  );
}

const overviewStart = game.indexOf('<div class="agent-workspace-card"><h3>Project Work</h3>');
assert.notEqual(overviewStart, -1, 'overview project work block should exist');
const overviewEnd = game.indexOf('<div class="agent-workspace-card agent-workspace-wide"><h3>Recent Activity</h3>', overviewStart);
assert.ok(overviewEnd > overviewStart, 'overview project work block should be bounded');
const overviewBlock = game.slice(overviewStart, overviewEnd);
assert.ok(overviewBlock.includes('_agentWorkspaceProjectMeta(t, true)'), 'overview should use read-only project meta');
assert.ok(overviewBlock.includes('_agentWorkspaceProjectBadges(t)'), 'overview should use read-only project badges');

console.log('agent workspace project context read-only UI checks passed');
