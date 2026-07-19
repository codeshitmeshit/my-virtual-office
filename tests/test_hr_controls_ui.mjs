import assert from 'node:assert/strict';
import { createRequire } from 'node:module';


const require = createRequire(import.meta.url);
const hr = require('../app/human-resources.js');


function response(payload, ok = true) {
  return { ok, text: async () => JSON.stringify(payload) };
}

hr.state.overview = {
  ok: true,
  hr: { status: 'ready' },
  cycle: { cycleId: 'cycle-1', status: 'open' },
  availabilityCounts: { available: 1 },
};
hr.state.agents = [{ ai_id: 'agent-1', name: 'Agent One' }];
hr.state.detail = { aiId: 'agent-1', reports: [{ id: 'report-1' }] };

assert.deepEqual(hr.helpers.commandSpec('pause'), {
  url: '/api/human-resources/hr/pause',
  body: {},
});
assert.deepEqual(hr.helpers.commandSpec('close'), {
  url: '/api/human-resources/cycles/close',
  body: { cycleId: 'cycle-1' },
});
assert.equal(hr.helpers.commandSpec('unknown'), null);

const requests = [];
globalThis.confirm = () => true;
globalThis.i18n = {
  managementFetch: async (url, options = {}) => {
    requests.push({ url, options });
    if (options.method === 'POST') return response({ ok: true, command: { accepted: true } });
    if (url.includes('/overview')) {
      return response({
        ok: true,
        hr: { status: 'paused' },
        cycle: { cycleId: 'cycle-1', status: 'open' },
        availabilityCounts: { available: 1 },
      });
    }
    return response({ ok: true, export: { rows: [{ ai_id: 'agent-1', name: 'Agent One' }] } });
  },
};

assert.equal(await hr.runCommand('pause'), true);
assert.equal(requests[0].url, '/api/human-resources/hr/pause');
assert.equal(requests[0].options.method, 'POST');
assert.deepEqual(JSON.parse(requests[0].options.body), {});
assert.equal(hr.state.overview.hr.status, 'paused');
assert.equal(hr.state.agents.length, 1);
assert.match(hr.state.commandNotice, /pause/);
assert.equal(hr.state.commandBusy, '');

globalThis.confirm = () => false;
const requestCount = requests.length;
assert.equal(await hr.runCommand('resume'), false);
assert.equal(requests.length, requestCount, 'cancelled confirmation performs no request');

globalThis.confirm = () => true;
globalThis.i18n.managementFetch = async (url, options = {}) => {
  if (options.method === 'POST') return response({ ok: false, code: 'hr_disabled' }, false);
  throw new Error(`unexpected read after failed command: ${url}`);
};
const retainedOverview = hr.state.overview;
const retainedAgents = hr.state.agents;
const retainedDetail = hr.state.detail;
assert.equal(await hr.runCommand('resume'), false);
assert.equal(hr.state.overview, retainedOverview);
assert.equal(hr.state.agents, retainedAgents);
assert.equal(hr.state.detail, retainedDetail);
assert.equal(hr.state.commandError, 'hr_disabled');
assert.equal(hr.state.commandBusy, '');

console.log('Human Resources controls confirmation and degraded-read checks passed');
