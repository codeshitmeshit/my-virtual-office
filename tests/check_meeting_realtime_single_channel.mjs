import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const meetingUi = fs.readFileSync(path.join(root, 'app', 'meetings-ui.js'), 'utf8');
const bundledUi = fs.readFileSync(path.join(root, 'app', 'game.js'), 'utf8');
const realtime = fs.readFileSync(path.join(root, 'app', 'dashboard-realtime.js'), 'utf8');

for (const source of [meetingUi, bundledUi]) {
  assert.ok(!source.includes('/events?after='), 'Meeting UI must not create one event request per active Meeting');
  assert.ok(!source.includes('_mtgPollLiveMeetings'), 'legacy per-Meeting polling loop must be removed');
  assert.ok(!source.includes('_mtgEnsureLivePolling'), 'legacy polling lifecycle names must be removed');
  assert.ok(source.includes('_mtgTickLiveMeetings'), 'local timeout display should keep its side-effect-free timer');
  assert.ok(source.includes('next.timeoutRunBySeq = previous && previous.timeoutRunBySeq'), 'SSE snapshots must preserve timeout-action deduplication');
}
assert.ok(realtime.includes("source.addEventListener('dashboard.meetings'"), 'Meeting updates must use the shared dashboard SSE');
assert.ok(realtime.includes('window._mtgRender()'), 'shared Meeting snapshots must refresh an open Meeting surface');
