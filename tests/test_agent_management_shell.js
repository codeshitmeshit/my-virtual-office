const assert = require('node:assert/strict');
const shell = require('../app/agent-management.js');

assert.deepEqual(shell.setAudience({ kind: 'agent', aiId: 'codex-local' }), {
    kind: 'agent',
    aiId: 'codex-local',
});
assert.equal(shell.setRoster([
    { id: 'legacy-id', statusKey: 'codex-local', name: 'Codex' },
    { aiId: 'hermes-default', name: 'Hermes' },
    { aiId: 'hermes-default', name: 'Hermes latest' },
]).length, 2);
assert.equal(shell.state.selectedAiId, 'codex-local');
assert.equal(shell.selectAgent('hermes-default'), true);
assert.equal(shell.state.selectedAiId, 'hermes-default');
assert.equal(shell.switchTab('humanResources'), true);
assert.equal(shell.state.activeTab, 'humanResources');
assert.equal(shell.mountTab('configuration', { mount() {} }), true);
shell.reportMutation({ state: 'saved' });
assert.equal(shell.state.mutations.at(-1).state, 'saved');
assert.equal(shell.helpers.stableId({ statusKey: 'stable' }), 'stable');
console.log('agent management shell contract ok');
