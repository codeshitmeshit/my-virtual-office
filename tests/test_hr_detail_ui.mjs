import assert from 'node:assert/strict';
import { createRequire } from 'node:module';


const require = createRequire(import.meta.url);
const hr = require('../app/human-resources.js');


function response(payload) {
  return { ok: true, text: async () => JSON.stringify(payload) };
}

let resolveAgentA;
globalThis.i18n = {
  managementFetch: async (url) => {
    if (url.includes('/agents/agent-a')) {
      return new Promise((resolve) => { resolveAgentA = resolve; });
    }
    if (url.includes('reportCursor=reports-next')) {
      return response({
        ok: true,
        agent: {
          reports: [
            { id: 'report-1', revision: 2 },
            { id: 'report-2', revision: 1 },
          ],
          reportNextCursor: null,
        },
      });
    }
    return response({
      ok: true,
      agent: {
        aiId: 'agent-b',
        name: 'Agent B',
        reports: [{ id: 'report-1', revision: 1 }],
        assessments: [{ id: 'assessment-1', version: 1 }],
        accessHistory: [{ id: 'access-1' }],
        reportNextCursor: 'reports-next',
        assessmentNextCursor: null,
        accessNextCursor: null,
      },
    });
  },
};

const staleRequest = hr.selectAgent('agent-a');
const currentRequest = hr.selectAgent('agent-b');
await currentRequest;
assert.equal(hr.state.detail.aiId, 'agent-b');
resolveAgentA(response({ ok: true, agent: { aiId: 'agent-a', name: 'Stale Agent' } }));
assert.equal(await staleRequest, false);
assert.equal(hr.state.detail.aiId, 'agent-b', 'late prior selection must not replace current detail');

assert.equal(await hr.loadMore('reports'), true);
assert.deepEqual(hr.state.detail.reports, [
  { id: 'report-1', revision: 2 },
  { id: 'report-2', revision: 1 },
]);
assert.equal(hr.state.detail.reportNextCursor, null);
assert.equal(await hr.loadMore('reports'), false, 'exhausted pagination does not request again');

assert.deepEqual(
  hr.helpers.mergeByKey(
    [{ id: 'one', value: 1 }, { id: 'two', value: 2 }],
    [{ id: 'two', value: 3 }, { id: 'three', value: 4 }],
    'id',
  ),
  [
    { id: 'one', value: 1 },
    { id: 'two', value: 3 },
    { id: 'three', value: 4 },
  ],
);
assert.equal(hr.helpers.workloadTone('overloaded'), 'warning');
assert.equal(hr.helpers.workloadTone('appropriate'), 'success');
assert.match(hr.helpers.prettyJson({ blocker: '<private>' }), /<private>/);

console.log('Human Resources detail stale-request and pagination checks passed');
