const assert = require('assert');
const fs = require('fs');
const path = require('path');

const root = path.resolve(__dirname, '..');
const style = fs.readFileSync(path.join(root, 'app', 'style.css'), 'utf8');
const meetings = fs.readFileSync(path.join(root, 'app', 'meetings-ui.js'), 'utf8');

assert.ok(
  /\.mtg-card-header\s*\{[^}]*display:\s*grid[^}]*grid-template-columns:\s*minmax\(0,\s*1fr\)\s*auto/s.test(style),
  'meeting card header should use a stable title/badge grid'
);
assert.ok(
  /\.mtg-card-header\s*>\s*div:first-child\s*\{[^}]*min-width:\s*0/s.test(style),
  'meeting card title column should be allowed to shrink'
);
assert.ok(
  /\.mtg-card-title\s*\{[^}]*overflow-wrap:\s*anywhere/s.test(style),
  'long meeting titles should wrap without pushing badges'
);
assert.ok(
  /\.mtg-card-badges\s*\{[^}]*justify-content:\s*flex-end[^}]*max-width:\s*min\(360px,\s*44vw\)/s.test(style),
  'meeting badges should stay right aligned with a bounded width'
);
assert.ok(
  /\.mtg-actions-bar\s*\{[^}]*flex-wrap:\s*wrap/s.test(style),
  'meeting action buttons should wrap consistently when space is tight'
);
assert.ok(
  meetings.includes('<div class="mtg-card-header" onclick="openMeetingDetailModal') &&
    meetings.includes('<div class="mtg-card-badges">') &&
    meetings.includes('<div class="mtg-actions-bar">'),
  'meeting history cards should still render header, badges, and actions'
);

console.log('meeting history card layout checks passed');
