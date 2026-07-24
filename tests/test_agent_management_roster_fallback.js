const assert = require('node:assert/strict');

global.agents = [
    { statusKey: 'codex-local', name: 'Codex' },
    { statusKey: 'claude-code-local', name: 'Claude Code' },
];
global.i18n = {
    async managementFetch(url) {
        if (String(url).endsWith('/overview')) {
            return new Response(JSON.stringify({ ok: true, agentTotal: 0 }), {
                status: 200,
            });
        }
        if (String(url).includes('/export?table=agents')) {
            return new Response(JSON.stringify({
                ok: true,
                export: { rows: [] },
            }), { status: 200 });
        }
        throw new Error(`unexpected route: ${url}`);
    },
};

const adapters = require('../app/agent-management-adapters.js');

(async () => {
    const result = await adapters.createHumanAdapter().bootstrap();
    assert.deepEqual(result.roster, global.agents);
    assert.notStrictEqual(result.roster, global.agents);
    console.log('agent management roster fallback ok');
})().finally(() => {
    delete global.agents;
    delete global.i18n;
});
