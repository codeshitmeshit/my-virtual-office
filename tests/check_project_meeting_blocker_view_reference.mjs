import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { join } from 'node:path';

const root = process.cwd();
const gameJs = readFileSync(join(root, 'app/game.js'), 'utf8');
const projectsJs = readFileSync(join(root, 'app/projects.js'), 'utf8');

assert.ok(
  projectsJs.includes('ProjMgr.viewMeetingBlocker(${jsArg(blocker.requestId || \'\')}, ${jsArg(blocker.meetingId || \'\')})'),
  'project meeting blocker view button should pass both requestId and meetingId'
);
assert.ok(
  gameJs.includes('async function _mtgFetchRequestDetail(requestId)'),
  'meeting reference opening should be able to fetch a request detail when the list cache is stale'
);
assert.ok(
  gameJs.includes('if (requestId && !request) request = await _mtgFetchRequestDetail(requestId);'),
  'openMeetingReference should hydrate missing request details before deciding what modal to open'
);
assert.ok(
  gameJs.includes('if (request && !meetingId) meetingId = _mtgMeetingIdFromRequest(request);'),
  'openMeetingReference should derive a meeting id from request conversion/taskBlocker data'
);

console.log('project meeting blocker view reference check passed');
