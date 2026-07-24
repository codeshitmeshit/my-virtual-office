(function (root) {
    'use strict';

    const state = {
        context: null,
        profiles: new Map(),
        loading: new Set(),
        errors: new Map(),
        saveState: new Map(),
        undo: new Map(),
        debounce: new Map(),
        saveSequence: new Map(),
    };

    function esc(value) {
        return String(value == null ? '' : value)
            .replace(/&/g, '&amp;').replace(/</g, '&lt;')
            .replace(/>/g, '&gt;').replace(/"/g, '&quot;')
            .replace(/'/g, '&#39;');
    }

    function tr(key, fallback) {
        if (root.i18n && typeof root.i18n.t === 'function') {
            const value = root.i18n.t(key);
            if (value && value !== key) return value;
        }
        return fallback;
    }

    function selectedAgent(context) {
        return (context.roster || []).find(function (item) {
            return item.aiId === context.selectedAiId;
        }) || { aiId: context.selectedAiId };
    }

    function canEdit(context) {
        if (!context || !context.selectedAiId) return false;
        return context.audience.kind === 'human' ||
            context.audience.aiId === context.selectedAiId;
    }

    function canSeeRestricted(context) {
        return Boolean(context && context.audience.kind === 'human');
    }

    function visibleSections(context) {
        const sections = ['identity', 'introduction', 'responsibilities', 'appearance'];
        if (canSeeRestricted(context)) {
            sections.push('assignment', 'provider', 'branch', 'workspace', 'binding');
        }
        return sections;
    }

    function normalizeProfile(payload, agent) {
        const profile = payload && (payload.profile || payload);
        return Object.assign({
            aiId: agent.aiId,
            revision: 0,
            name: agent.name || agent.displayName || agent.aiId,
            introduction: agent.introduction || '',
            responsibilities: agent.responsibilities || (agent.role ? [agent.role] : []),
            specialties: agent.specialties || [],
            appearance: agent.appearance || {},
        }, profile || {});
    }

    async function requestProfile(context, aiId) {
        if (context.adapter && typeof context.adapter.getConfiguration === 'function') {
            return context.adapter.getConfiguration(aiId);
        }
        if (!root.i18n || typeof root.i18n.managementFetch !== 'function') {
            return null;
        }
        const response = await root.i18n.managementFetch(
            '/api/agent-management/profiles/' + encodeURIComponent(aiId)
        );
        const payload = await response.json();
        if (!response.ok || payload.ok === false) throw new Error(payload.code || 'agent_profile_load_failed');
        return payload;
    }

    function fieldStatus(field) {
        const entry = state.saveState.get(field);
        if (!entry) return '';
        const label = {
            saving: tr('agent_save_saving', 'Saving…'),
            saved: tr('agent_save_saved', 'Saved'),
            conflict: tr('agent_save_conflict', 'Conflict'),
            denied: tr('agent_save_denied', 'Denied'),
            failed: tr('agent_save_failed', 'Save failed'),
            undone: tr('agent_save_undone', 'Undone'),
        }[entry.state] || entry.state;
        const undo = state.undo.get(field);
        return '<span class="ac-field-feedback"><span class="ac-field-status ' + esc(entry.state) +
            '" data-field-status="' + esc(field) + '" role="status">' + esc(label) + '</span>' +
            (undo ? '<button type="button" class="ac-undo" data-undo-field="' + esc(field) + '">' +
                esc(tr('undo', 'Undo')) + '</button>' : '') + '</span>';
    }

    function textField(label, field, value, editable, multiline) {
        const tag = multiline ? 'textarea' : 'input';
        const valueMarkup = multiline
            ? '>' + esc(value) + '</textarea>'
            : ' value="' + esc(value) + '">';
        if (!editable) {
            return '<div class="ac-field ac-readonly"><span>' + esc(label) +
                '</span><strong>' + esc(value || '—') + '</strong></div>';
        }
        return '<label class="ac-field"><span>' + esc(label) + '</span><' + tag +
            ' data-profile-field="' + esc(field) + '"' +
            (multiline ? ' rows="4"' : ' type="text"') + valueMarkup +
            fieldStatus(field) + '</label>';
    }

    function tagsField(label, field, values, editable) {
        const text = (Array.isArray(values) ? values : []).join(', ');
        return textField(label, field, text, editable, false);
    }

    function restrictedCard(title, field, value) {
        return '<section class="ac-restricted-card" data-restricted-field="' + esc(field) + '">' +
            '<span>' + esc(title) + '</span><strong>' + esc(value || '—') + '</strong>' +
            '<button type="button" data-high-risk-action="' + esc(field) + '">' +
            esc(tr('agent_change', 'Change')) + '</button></section>';
    }

    function renderProfile(context, profile) {
        const container = context.container;
        const agent = selectedAgent(context);
        const editable = canEdit(context);
        const restricted = canSeeRestricted(context);
        const appearance = profile.appearance || {};
        container.innerHTML =
            '<div class="agent-configuration" data-audience="' + esc(context.audience.kind) + '">' +
                '<section class="ac-hero"><div class="ac-avatar">' + esc(appearance.emoji || agent.emoji || '🤖') + '</div>' +
                    '<div><span class="ac-eyebrow">' + esc(profile.aiId) + '</span>' +
                    '<h3>' + esc(profile.name || profile.aiId) + '</h3>' +
                    '<p>' + esc(tr('agent_responsibility_hint', 'Responsibilities and specialties guide discovery and recommendations; they are not permission gates.')) + '</p></div>' +
                    '<span class="ac-revision">v' + esc(profile.revision) + '</span></section>' +
                '<div class="ac-grid">' +
                    '<section class="ac-card" data-section="identity"><h4>' + esc(tr('agent_identity', 'Identity')) + '</h4>' +
                        textField(tr('agent_name', 'Name'), 'name', profile.name, editable, false) + '</section>' +
                    '<section class="ac-card" data-section="introduction"><h4>' + esc(tr('agent_introduction', 'Introduction')) + '</h4>' +
                        textField(tr('agent_introduction', 'Introduction'), 'introduction', profile.introduction, editable, true) + '</section>' +
                    '<section class="ac-card" data-section="responsibilities"><h4>' + esc(tr('agent_responsibilities', 'Responsibilities & specialties')) + '</h4>' +
                        tagsField(tr('agent_responsibilities', 'Responsibilities'), 'responsibilities', profile.responsibilities, editable) +
                        tagsField(tr('agent_specialties', 'Specialties'), 'specialties', profile.specialties, editable) + '</section>' +
                    '<section class="ac-card" data-section="appearance"><h4>' + esc(tr('agent_appearance', 'Appearance')) + '</h4>' +
                        '<div id="agent-appearance-editor" class="ac-appearance-editor" data-editable="' + (editable ? 'true' : 'false') + '"></div></section>' +
                '</div>' +
                (restricted ? '<section class="ac-restricted"><h4>' + esc(tr('agent_restricted_configuration', 'Authenticated human configuration')) + '</h4>' +
                    restrictedCard(tr('agent_provider', 'Provider'), 'provider', agent.providerKind || agent.provider) +
                    restrictedCard(tr('agent_branch', 'Branch'), 'branch', agent.branchName || agent.branch) +
                    restrictedCard(tr('agent_workspace', 'Workspace'), 'workspace', agent.workspace || agent.workspacePath) +
                    restrictedCard(tr('agent_assignment', 'Assignment'), 'assignment', agent.assignment || agent.role) +
                    restrictedCard(tr('agent_binding', 'Provider-Agent binding'), 'binding', agent.providerAgentId || agent.profile) +
                '</section>' : '') +
            '</div>';
        bindFieldEvents(context);
    }

    function normalizeFieldValue(field, raw) {
        if (field === 'responsibilities' || field === 'specialties') {
            const seen = new Set();
            return String(raw || '').split(',').map(function (item) { return item.trim(); })
                .filter(function (item) {
                    const key = item.toLowerCase();
                    if (!item || seen.has(key)) return false;
                    seen.add(key);
                    return true;
                }).slice(0, 12);
        }
        return String(raw == null ? '' : raw).trim();
    }

    function classifySaveError(status, code) {
        if (status === 409 || /conflict/.test(String(code || ''))) return 'conflict';
        if (status === 401 || status === 403 || /denied|forbidden/.test(String(code || ''))) return 'denied';
        return 'failed';
    }

    function setSaveState(field, nextState, code) {
        state.saveState.set(field, { state: nextState, code: code || '' });
        const context = state.context;
        if (!context || !context.container) return;
        const status = context.container.querySelector('[data-field-status="' + field + '"]');
        if (status) {
            status.className = 'ac-field-status ' + nextState;
            status.textContent = {
                saving: tr('agent_save_saving', 'Saving…'),
                saved: tr('agent_save_saved', 'Saved'),
                conflict: tr('agent_save_conflict', 'Conflict'),
                denied: tr('agent_save_denied', 'Denied'),
                failed: tr('agent_save_failed', 'Save failed'),
                undone: tr('agent_save_undone', 'Undone'),
            }[nextState] || nextState;
        }
        if (context.reportMutation) {
            context.reportMutation({ field: field, state: nextState, code: code || '' });
        }
    }

    async function mutationRequest(context, path, body) {
        if (context.adapter && typeof context.adapter.mutateConfiguration === 'function') {
            return context.adapter.mutateConfiguration(path, body);
        }
        if (!root.i18n || typeof root.i18n.managementFetch !== 'function') {
            throw Object.assign(new Error('agent_management_adapter_unavailable'), { status: 503 });
        }
        const response = await root.i18n.managementFetch(path, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(body),
        });
        const payload = await response.json();
        if (!response.ok || payload.ok === false) {
            throw Object.assign(new Error(payload.code || 'agent_profile_mutation_failed'), {
                status: response.status,
                code: payload.code || '',
            });
        }
        return payload;
    }

    async function commitField(field, value) {
        const context = state.context;
        const profile = context && state.profiles.get(context.selectedAiId);
        if (!context || !profile || !canEdit(context)) return false;
        const sequence = (state.saveSequence.get(field) || 0) + 1;
        state.saveSequence.set(field, sequence);
        setSaveState(field, 'saving');
        try {
            const payload = await mutationRequest(
                context,
                context.audience.kind === 'agent'
                    ? '/api/agent-management/browser/profile/mutate'
                    : '/api/agent-management/profile/mutate',
                {
                    targetAiId: context.selectedAiId,
                    field: field,
                    value: normalizeFieldValue(field, value),
                    expectedRevision: profile.revision,
                }
            );
            if (state.saveSequence.get(field) !== sequence) return false;
            state.profiles.set(context.selectedAiId, normalizeProfile(payload, selectedAgent(context)));
            if (payload.undoToken) {
                state.undo.set(field, {
                    token: payload.undoToken,
                    revision: payload.revision,
                    expiresAt: payload.undoExpiresAt,
                });
            }
            setSaveState(field, 'saved');
            renderProfile(context, state.profiles.get(context.selectedAiId));
            return true;
        } catch (error) {
            if (state.saveSequence.get(field) !== sequence) return false;
            setSaveState(field, classifySaveError(error.status, error.code || error.message), error.code || error.message);
            return false;
        }
    }

    async function undoField(field) {
        const context = state.context;
        const undo = state.undo.get(field);
        if (!context || !undo) return false;
        try {
            const payload = await mutationRequest(
                context,
                context.audience.kind === 'agent'
                    ? '/api/agent-management/browser/profile/undo'
                    : '/api/agent-management/profile/undo',
                { undoToken: undo.token, expectedRevision: undo.revision }
            );
            state.undo.delete(field);
            state.profiles.set(context.selectedAiId, normalizeProfile(payload, selectedAgent(context)));
            setSaveState(field, 'undone');
            renderProfile(context, state.profiles.get(context.selectedAiId));
            return true;
        } catch (error) {
            state.undo.delete(field);
            setSaveState(field, classifySaveError(error.status, error.code || error.message), error.code || error.message);
            return false;
        }
    }

    function scheduleTextSave(field, value) {
        if (state.debounce.has(field) && typeof root.clearTimeout === 'function') {
            root.clearTimeout(state.debounce.get(field));
        }
        if (typeof root.setTimeout !== 'function') return commitField(field, value);
        const timer = root.setTimeout(function () {
            state.debounce.delete(field);
            commitField(field, value);
        }, 450);
        state.debounce.set(field, timer);
        return timer;
    }

    function bindFieldEvents(context) {
        if (!context.container || !canEdit(context)) return;
        context.container.querySelectorAll('[data-profile-field]').forEach(function (control) {
            const field = control.getAttribute('data-profile-field');
            control.addEventListener('input', function () {
                scheduleTextSave(field, control.value);
            });
            control.addEventListener('blur', function () {
                if (!state.debounce.has(field)) return;
                if (typeof root.clearTimeout === 'function') root.clearTimeout(state.debounce.get(field));
                state.debounce.delete(field);
                commitField(field, control.value);
            });
        });
        context.container.querySelectorAll('[data-undo-field]').forEach(function (button) {
            button.addEventListener('click', function () {
                undoField(button.getAttribute('data-undo-field'));
            });
        });
    }

    async function load(context) {
        const aiId = context.selectedAiId;
        if (!aiId) {
            context.container.innerHTML = '<div class="am-empty">' + esc(tr('agent_management_empty', 'No Agent selected')) + '</div>';
            return;
        }
        const agent = selectedAgent(context);
        if (state.profiles.has(aiId)) {
            renderProfile(context, state.profiles.get(aiId));
            return;
        }
        context.container.innerHTML = '<div class="am-empty">' + esc(tr('agent_configuration_loading', 'Loading Agent configuration…')) + '</div>';
        state.loading.add(aiId);
        try {
            const payload = await requestProfile(context, aiId);
            const profile = normalizeProfile(payload, agent);
            state.profiles.set(aiId, profile);
            if (state.context && state.context.selectedAiId === aiId) renderProfile(state.context, profile);
        } catch (error) {
            state.errors.set(aiId, String(error && error.message || 'agent_profile_load_failed'));
            if (state.context && state.context.selectedAiId === aiId) {
                state.context.container.innerHTML = '<div class="am-empty ac-error">' +
                    esc(tr('agent_configuration_failed', 'Agent configuration could not be loaded')) + '</div>';
            }
        } finally {
            state.loading.delete(aiId);
        }
    }

    function mount(context) {
        state.context = context;
        load(context);
    }

    const api = {
        state: state,
        mount: mount,
        reload: function (aiId) {
            state.profiles.delete(aiId || (state.context && state.context.selectedAiId));
            if (state.context) return load(state.context);
        },
        commitField: commitField,
        undoField: undoField,
        helpers: {
            canEdit: canEdit,
            canSeeRestricted: canSeeRestricted,
            visibleSections: visibleSections,
            normalizeProfile: normalizeProfile,
            normalizeFieldValue: normalizeFieldValue,
            classifySaveError: classifySaveError,
        },
    };

    root.AgentConfiguration = api;
    if (root.AgentManagement) root.AgentManagement.mountTab('configuration', api);
    if (typeof module !== 'undefined' && module.exports) module.exports = api;
})(typeof window !== 'undefined' ? window : globalThis);
