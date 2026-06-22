const assert = require('assert');
const fs = require('fs');
const path = require('path');

const root = path.resolve(__dirname, '..');
const game = fs.readFileSync(path.join(root, 'app', 'game.js'), 'utf8');

assert.ok(
  game.includes("const FUNCTIONAL_MEETING_SPACE_TYPES = ['meetingTable4', 'meetingTable6', 'meetingTable', 'meetingRoom'];"),
  'legacy meetingTable should be treated as a functional meeting space'
);
assert.ok(
  game.includes("if (item.type === 'meetingTable') return 10;"),
  'legacy meetingTable should expose its 10-seat capacity'
);
assert.ok(
  game.includes("['meetingTable', 'meetingRoom']"),
  'large meetings should prefer the legacy table before falling back to meeting rooms'
);
assert.ok(
  game.includes("if (item.type === 'meetingTable') {") &&
  game.includes("[27, 73, 120, 166, 213].forEach(function(dx) { pushSlot(item.x + dx, item.y + 15, 2, true); });") &&
  game.includes("[27, 73, 120, 166, 213].forEach(function(dx) { pushSlot(item.x + dx, item.y + 103, 0, true); });"),
  'legacy meetingTable should provide deterministic 10-seat slot assignment'
);
assert.ok(
  game.includes("if (item.type === 'meetingTable') return _tr('furniture_meeting_table');"),
  'legacy meetingTable should have a display label in meeting assignment metadata'
);

console.log('legacy meeting table assignment tests passed');
