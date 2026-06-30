import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { join } from 'node:path';

const root = process.cwd();
const gameJs = readFileSync(join(root, 'app/game.js'), 'utf8');

assert.ok(gameJs.includes('function _mtgJsArg'), 'meeting sidebar click should use a JS argument encoder');
assert.ok(
  gameJs.includes('onclick="openMeetingReference({ meetingId: '),
  'sidebar active meeting card should open the referenced meeting detail directly'
);
assert.ok(
  !gameJs.includes('return \'<div class="sidebar-mtg-item" onclick="openMeetingsDashboard()">\''),
  'sidebar active meeting card must not open only the meetings dashboard'
);

console.log('sidebar meeting direct detail check passed');
