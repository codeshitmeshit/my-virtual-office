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
    const humanCalls = [];
    global.i18n = {
        managementFetch: async (url, options = {}) => {
            humanCalls.push({
                url: String(url),
                body: options.body ? JSON.parse(options.body) : null,
            });
            if (String(url).endsWith('/confirmations')) {
                return new Response(JSON.stringify({
                    ok: true,
                    confirmation: { challengeToken: 'challenge-token' },
                }), { status: 201 });
            }
            if (String(url).endsWith('/commands')) {
                return new Response(JSON.stringify({ ok: true }), { status: 200 });
            }
            throw new Error('unexpected human route');
        },
    };
    const human = adapters.createHumanAdapter();
    const change = {
        targetAiId: 'codex-local',
        action: 'branch',
        before: { branch: 'hq' },
        after: { branch: 'finance' },
        revision: 0,
    };
    await human.applyHighRisk(change);
    assert.deepEqual(humanCalls, [
        { url: '/api/agent-management/confirmations', body: change },
        {
            url: '/api/agent-management/commands',
            body: Object.assign({}, change, { challengeToken: 'challenge-token' }),
        },
    ]);

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
    delete global.i18n;
    global.fetch = previousFetch;
    console.log('agent management adapters contract ok');
})().catch((error) => {
    delete global.i18n;
    global.fetch = previousFetch;
    console.error(error);
    process.exitCode = 1;
});
