import assert from 'node:assert/strict';
import fs from 'node:fs';

const skill = fs.readFileSync('skills/vo-operating-guidelines/SKILL.md', 'utf8');
const meetingPath = '/skills/vo-operating-guidelines/references/meeting-requests.md';

assert.ok(skill.includes(meetingPath), 'VO operating guide should expose the full meeting request skill path');
assert.ok(!skill.includes('/skills/references/meeting-requests.md'), 'VO operating guide must not suggest the non-existent flat references path');

console.log('vo operating guide meeting reference path is explicit');
