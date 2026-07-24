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
console.log('agent configuration audience contract ok');
