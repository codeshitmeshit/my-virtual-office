(function (root) {
    'use strict';

    async function responseJson(response) {
        const payload = await response.json();
        if (!response.ok || payload.ok === false) {
            throw Object.assign(new Error(payload.code || 'agent_management_request_failed'), {
                status: response.status,
                code: payload.code || '',
            });
        }
        return payload;
    }

    function humanFetch(url, options) {
        if (!root.i18n || typeof root.i18n.managementFetch !== 'function') {
            return Promise.reject(new Error('management_fetch_unavailable'));
        }
        return root.i18n.managementFetch(url, options || {});
    }

    function browserFetch(url, options) {
        return root.fetch(url, Object.assign({ credentials: 'same-origin' }, options || {}));
    }

    function stripEvidence(value) {
        if (Array.isArray(value)) return value.map(stripEvidence);
        if (!value || typeof value !== 'object') return value;
        return Object.keys(value).reduce(function (result, key) {
            const normalized = key.toLowerCase();
            if (
                normalized.includes('evidence') ||
                normalized.includes('providerenvelope') ||
                normalized.includes('token') ||
                normalized.includes('secret')
            ) return result;
            result[key] = stripEvidence(value[key]);
            return result;
        }, {});
    }

    function createHumanAdapter() {
        return {
            kind: 'human',
            async bootstrap() {
                const results = await Promise.all([
                    responseJson(await humanFetch('/api/human-resources/overview')),
                    responseJson(await humanFetch('/api/human-resources/export?table=agents&limit=100')),
                ]);
                return {
                    audience: { kind: 'human', aiId: '' },
                    roster: ((results[1].export || {}).rows || []),
                    overview: results[0],
                };
            },
            async getConfiguration(aiId) {
                return responseJson(await humanFetch(
                    '/api/agent-management/profiles/' + encodeURIComponent(aiId)
                ));
            },
            async mutateConfiguration(path, body) {
                return responseJson(await humanFetch(path, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(body),
                }));
            },
            async hrRequest(url, options) {
                return responseJson(await humanFetch(url, options));
            },
        };
    }

    function createAgentAdapter() {
        let bootstrapPayload = null;

        async function bootstrap() {
            bootstrapPayload = responseJson(await browserFetch(
                '/api/agent-management/browser/bootstrap'
            ));
            const payload = await bootstrapPayload;
            return {
                audience: payload.audience,
                roster: payload.items || [],
                overview: {
                    ok: true,
                    agentTotal: (payload.items || []).length,
                    activeCommands: [],
                    hr: { status: 'read_only' },
                },
            };
        }

        async function ensureBootstrap() {
            if (!bootstrapPayload) await bootstrap();
            return bootstrapPayload;
        }

        return {
            kind: 'agent',
            bootstrap: bootstrap,
            async getConfiguration(aiId) {
                const payload = await responseJson(await browserFetch(
                    '/api/agent-management/browser/agents/' + encodeURIComponent(aiId)
                ));
                return { ok: true, profile: payload.profile };
            },
            async mutateConfiguration(path, body) {
                if (!path.startsWith('/api/agent-management/browser/profile/')) {
                    throw Object.assign(new Error('agent_profile_mutation_denied'), { status: 403 });
                }
                return responseJson(await browserFetch(path, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(body),
                }));
            },
            async hrRequest(url, options) {
                if (options && String(options.method || 'GET').toUpperCase() !== 'GET') {
                    throw Object.assign(new Error('agent_management_command_denied'), { status: 403 });
                }
                const bootstrap = await ensureBootstrap();
                const audience = bootstrap.audience || {};
                if (url.includes('/overview')) {
                    return {
                        ok: true,
                        agentTotal: (bootstrap.items || []).length,
                        activeCommands: [],
                        hr: { status: 'read_only' },
                    };
                }
                if (url.includes('/export?table=agents')) {
                    return { ok: true, export: { rows: bootstrap.items || [] } };
                }
                const detailMatch = url.match(/\/agents\/([^?]+)/);
                if (detailMatch) {
                    const target = decodeURIComponent(detailMatch[1]);
                    const payload = await responseJson(await browserFetch(
                        '/api/agent-management/browser/agents/' + encodeURIComponent(target)
                    ));
                    const projected = stripEvidence(payload.hr || {});
                    if (target !== audience.aiId) {
                        delete projected.reports;
                        delete projected.assessments;
                        delete projected.improvements;
                        delete projected.accessHistory;
                    } else {
                        delete projected.assessments;
                    }
                    return { ok: true, agent: projected };
                }
                if (url.includes('/access-log')) {
                    return responseJson(await browserFetch(
                        '/api/agent-management/browser/access-log/self'
                    ));
                }
                throw Object.assign(new Error('agent_management_route_denied'), { status: 403 });
            },
            helpers: { stripEvidence: stripEvidence },
        };
    }

    const api = {
        createHumanAdapter: createHumanAdapter,
        createAgentAdapter: createAgentAdapter,
        helpers: { stripEvidence: stripEvidence },
    };
    root.AgentManagementAdapters = api;
    if (root.AgentManagement) {
        root.AgentManagement.setAdapters({
            human: createHumanAdapter(),
            agent: createAgentAdapter(),
        });
    }
    if (typeof module !== 'undefined' && module.exports) module.exports = api;
})(typeof window !== 'undefined' ? window : globalThis);
