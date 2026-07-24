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
assert.equal(configuration.helpers.previewProfile({ aiId: 'a', name: 'Agent A' }).__preview, true);
assert.equal(configuration.helpers.previewProfile({ aiId: 'a' }, 'unregistered').__previewState, 'unregistered');
assert.deepEqual(
    configuration.helpers.normalizeFieldValue('responsibilities', 'Backend, Reviewer, backend'),
    ['Backend', 'Reviewer'],
);
assert.equal(configuration.helpers.classifySaveError(409, ''), 'conflict');
assert.equal(configuration.helpers.classifySaveError(403, ''), 'denied');
assert.equal(configuration.helpers.classifySaveError(500, ''), 'failed');
assert.equal(configuration.helpers.isContextActive({ isActive: () => true }), true);
assert.equal(configuration.helpers.isContextActive({ isActive: () => false }), false);
assert(configuration.helpers.appearanceOptions.hairStyle.includes('curly'));
assert(configuration.helpers.appearanceOptions.deskItem.includes('checklist'));
global.i18n = {
    t(key) {
        return {
            option_female: '女',
            option_bald: '光头',
            option_short: '短发',
            option_medium: '中发',
            option_none: '无',
        }[key] || key;
    },
};
assert.equal(configuration.helpers.appearanceOptionLabel('F'), '女');
assert.equal(configuration.helpers.appearanceOptionLabel('short'), '短发');
const appearance = configuration.helpers.renderAppearance(
    { appearance: { hairStyle: 'short', hairColor: '#112233' } },
    true,
);
assert(appearance.includes('aria-haspopup="listbox"'));
assert(appearance.includes('data-appearance-color="hairColor"'));
assert(appearance.includes('<strong>短发</strong>'));
assert(appearance.includes('<span>无</span>'));
assert(!appearance.includes('<span>bald</span>'));
assert(!appearance.includes('<select'));
assert.equal(configuration.helpers.highRiskField('binding'), 'providerAgentId');
assert.match(
    configuration.helpers.fieldStatus('introduction'),
    /data-field-status="introduction" role="status"/,
);
console.log('agent configuration audience contract ok');
