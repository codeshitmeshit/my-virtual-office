import assert from 'node:assert/strict';
import { createRequire } from 'node:module';


const require = createRequire(import.meta.url);
const hr = require('../app/human-resources.js');
const helpers = hr.helpers;


assert.equal(helpers.escHtml('<img src=x onerror="boom">'), '&lt;img src=x onerror=&quot;boom&quot;&gt;');
assert.equal(helpers.statusTone('normalization_failed'), 'danger');
assert.equal(helpers.statusTone('not_submitted'), 'warning');
assert.equal(helpers.statusTone('ready'), 'success');
assert.equal(helpers.statusTone('something-new'), 'neutral');

const prioritized = helpers.prioritizeAgents([
  { ai_id: 'ready', status: 'active', availability: 'available', grant_readiness: 'ready' },
  { ai_id: 'failed', status: 'disabled', availability: 'unavailable', grant_readiness: 'revoked' },
  { ai_id: 'pending', status: 'active', availability: 'available', grant_readiness: 'pending' },
]);
assert.deepEqual(prioritized.map((agent) => agent.ai_id), ['failed', 'pending', 'ready']);

assert.deepEqual(
  helpers.cycleCounts({ cycle: { counts: { complete: 3, failed: 1, waiting: 2, skipped: 0 } } }),
  [
    { status: 'failed', count: 1 },
    { status: 'waiting', count: 2 },
    { status: 'complete', count: 3 },
  ],
);
assert.equal(
  helpers.reportScheduleLabel({
    enabled: true,
    state: 'scheduled',
    nextLocalAt: '2026-07-20T18:00:00+08:00',
    timezone: 'Asia/Shanghai',
  }),
  'Next daily report collection: 2026-07-20 18:00 Asia/Shanghai',
);
assert.match(
  helpers.reportScheduleLabel({
    enabled: false,
    state: 'disabled',
    nextLocalAt: '2026-07-20T18:00:00+08:00',
    timezone: 'Asia/Shanghai',
  }),
  /after enabling/,
);
assert.deepEqual(
  helpers.availabilityCounts({ availabilityCounts: { available: 4, busy: 2, unavailable: 1 } }),
  [
    { name: 'available', count: 4 },
    { name: 'busy', count: 2 },
    { name: 'unavailable', count: 1 },
  ],
);

function response(payload, ok = true) {
  return {
    ok,
    text: async () => JSON.stringify(payload),
  };
}

globalThis.i18n = {
  managementFetch: async (url) => {
    if (url.includes('/overview')) {
      return response({
        ok: true,
        hr: { name: 'HR', status: 'ready' },
        agentTotal: 2,
        availabilityCounts: { available: 2 },
        recentActivity: [],
        reportSchedule: {
          enabled: true,
          state: 'scheduled',
          nextLocalAt: '2026-07-20T18:00:00+08:00',
          timezone: 'Asia/Shanghai',
        },
      });
    }
    return response({ ok: true, export: { rows: [{ ai_id: 'agent-1' }, { ai_id: 'agent-2' }] } });
  },
};

assert.equal(await hr.reload(), true);
assert.equal(hr.state.overview.hr.status, 'ready');
assert.equal(hr.state.agents.length, 2);
assert.deepEqual(hr.state.errors, []);

globalThis.i18n.managementFetch = async (url) => {
  if (url.includes('/overview')) return response({ ok: false, code: 'hr_repository_unavailable' }, false);
  return response({ ok: true, export: { rows: [{ ai_id: 'agent-2' }] } });
};
assert.equal(await hr.reload(), false);
assert.equal(hr.state.overview.hr.status, 'ready', 'last valid overview remains readable');
assert.deepEqual(hr.state.agents.map((agent) => agent.ai_id), ['agent-2']);
assert.deepEqual(hr.state.errors, ['hr_repository_unavailable']);

console.log('Human Resources overview helpers and degraded loading passed');
