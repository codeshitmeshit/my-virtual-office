const assert = require('node:assert/strict');
const adapters = require('../app/agent-management-adapters.js');

const projected = adapters.helpers.stripEvidence({
    name: 'Agent',
    evidence: [{ secretToken: 'hidden' }],
    nested: { providerEnvelope: 'hidden', safe: 'visible' },
});
assert.deepEqual(projected, { name: 'Agent', nested: { safe: 'visible' } });

const previousFetch = global.fetch;
global.fetch = async (url, options = {}) => {
    assert.equal(options.credentials, 'same-origin');
    if (String(url).endsWith('/bootstrap')) {
        return new Response(JSON.stringify({
            ok: true,
            audience: { kind: 'agent', aiId: 'codex-local' },
            items: [{ aiId: 'codex-local' }, { aiId: 'hermes-default' }],
        }), { status: 200 });
    }
    if (String(url).includes('/agents/')) {
        return new Response(JSON.stringify({
            ok: true,
            hr: {
                aiId: 'hermes-default',
                reports: ['hidden'],
                assessments: [{ evidence: 'hidden' }],
                accessHistory: ['hidden'],
                publicWorkSummary: ['visible'],
            },
            profile: { aiId: 'hermes-default' },
        }), { status: 200 });
    }
    throw new Error('unexpected route');
};

(async () => {
    const agent = adapters.createAgentAdapter();
    const bootstrap = await agent.bootstrap();
    assert.equal(bootstrap.audience.aiId, 'codex-local');
    const detail = await agent.hrRequest('/api/human-resources/agents/hermes-default');
    assert.deepEqual(detail.agent.publicWorkSummary, ['visible']);
    assert.equal('reports' in detail.agent, false);
    assert.equal('assessments' in detail.agent, false);
    assert.equal('accessHistory' in detail.agent, false);
    await assert.rejects(
        () => agent.hrRequest('/api/human-resources/cycles/run', { method: 'POST' }),
        /agent_management_command_denied/,
    );
    global.fetch = previousFetch;
    console.log('agent management adapters contract ok');
})().catch((error) => {
    global.fetch = previousFetch;
    console.error(error);
    process.exitCode = 1;
});
