const assert = require('node:assert/strict');
const configuration = require('../app/agent-configuration.js');

const human = { audience: { kind: 'human', aiId: '' }, selectedAiId: 'a' };
const self = { audience: { kind: 'agent', aiId: 'a' }, selectedAiId: 'a' };
const peer = { audience: { kind: 'agent', aiId: 'a' }, selectedAiId: 'b' };

assert.equal(configuration.helpers.canEdit(human), true);
assert.equal(configuration.helpers.canEdit(self), true);
assert.equal(configuration.helpers.canEdit(peer), false);
assert.equal(configuration.helpers.canSeeRestricted(human), true);
assert.equal(configuration.helpers.canSeeRestricted(self), false);
assert(configuration.helpers.visibleSections(human).includes('provider'));
assert(!configuration.helpers.visibleSections(self).includes('provider'));
assert.deepEqual(
    configuration.helpers.normalizeProfile(null, { aiId: 'a', role: 'Backend' }).responsibilities,
    ['Backend'],
);
assert.deepEqual(
    configuration.helpers.normalizeFieldValue('responsibilities', 'Backend, Reviewer, backend'),
    ['Backend', 'Reviewer'],
);
assert.equal(configuration.helpers.classifySaveError(409, ''), 'conflict');
assert.equal(configuration.helpers.classifySaveError(403, ''), 'denied');
assert.equal(configuration.helpers.classifySaveError(500, ''), 'failed');
assert(configuration.helpers.appearanceOptions.hairStyle.includes('curly'));
assert(configuration.helpers.appearanceOptions.deskItem.includes('checklist'));
const appearance = configuration.helpers.renderAppearance(
    { appearance: { hairStyle: 'short', hairColor: '#112233' } },
    true,
);
assert(appearance.includes('aria-haspopup="listbox"'));
assert(appearance.includes('data-appearance-color="hairColor"'));
assert(!appearance.includes('<select'));
console.log('agent configuration audience contract ok');
