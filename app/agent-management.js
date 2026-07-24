(function (root) {
    'use strict';

    const state = {
        open: false,
        audience: { kind: 'human', aiId: '' },
        roster: [],
        selectedAiId: '',
        activeTab: 'configuration',
        tabs: {
            configuration: { loading: false, error: '', scrollTop: 0 },
            humanResources: { loading: false, error: '', scrollTop: 0 },
        },
        adapters: { human: null, agent: null },
        panels: {},
        returnFocus: null,
        mutations: [],
        bootstrapping: false,
        bootstrappedAudience: '',
    };

    function tr(key, fallback) {
        if (root.i18n && typeof root.i18n.t === 'function') {
            const value = root.i18n.t(key);
            if (value && value !== key) return value;
        }
        return fallback;
    }

    function esc(value) {
        return String(value == null ? '' : value)
            .replace(/&/g, '&amp;').replace(/</g, '&lt;')
            .replace(/>/g, '&gt;').replace(/"/g, '&quot;')
            .replace(/'/g, '&#39;');
    }

    function stableId(agent) {
        return String(agent && (
            agent.aiId || agent.ai_id || agent.statusKey || agent.id
        ) || '');
    }

    function normalizedRoster(roster) {
        const byId = new Map();
        (Array.isArray(roster) ? roster : []).forEach(function (agent) {
            const aiId = stableId(agent);
            if (aiId) byId.set(aiId, Object.assign({}, agent, { aiId: aiId }));
        });
        return Array.from(byId.values());
    }

    function modal() {
        return root.document && root.document.getElementById('agentManagementModal');
    }

    function panel() {
        return root.document && root.document.getElementById('agent-management-panel');
    }

    function saveScroll() {
        const element = panel();
        if (element) state.tabs[state.activeTab].scrollTop = element.scrollTop;
    }

    function restoreScroll() {
        const element = panel();
        if (!element) return;
        element.scrollTop = state.tabs[state.activeTab].scrollTop || 0;
    }

    function setRoster(roster) {
        state.roster = normalizedRoster(roster);
        if (!state.roster.some(function (item) {
            return item.aiId === state.selectedAiId;
        })) {
            state.selectedAiId = (
                state.audience.kind === 'agent' &&
                state.roster.some(function (item) {
                    return item.aiId === state.audience.aiId;
                })
            ) ? state.audience.aiId : (state.roster[0] || {}).aiId || '';
        }
        renderRoster();
        mountActiveTab();
        return state.roster.slice();
    }

    function selectAgent(aiId) {
        const selected = String(aiId || '');
        if (!state.roster.some(function (item) { return item.aiId === selected; })) {
            return false;
        }
        state.selectedAiId = selected;
        renderRoster();
        mountActiveTab();
        return true;
    }

    function setAudience(audience) {
        const kind = audience && audience.kind === 'agent' ? 'agent' : 'human';
        state.audience = {
            kind: kind,
            aiId: kind === 'agent' ? String(audience.aiId || '') : '',
        };
        if (kind === 'agent' && state.audience.aiId) {
            state.selectedAiId = state.audience.aiId;
        }
        render();
        return Object.assign({}, state.audience);
    }

    function setAdapters(adapters) {
        state.adapters = Object.assign({ human: null, agent: null }, adapters || {});
        if (state.open) bootstrapAudience();
    }

    async function bootstrapAudience() {
        if (state.bootstrapping) return false;
        state.bootstrapping = true;
        let result = null;
        try {
            if (state.adapters.agent && typeof state.adapters.agent.bootstrap === 'function') {
                try {
                    result = await state.adapters.agent.bootstrap();
                } catch (_agentError) {
                    result = null;
                }
            }
            if (!result && state.adapters.human && typeof state.adapters.human.bootstrap === 'function') {
                result = await state.adapters.human.bootstrap();
            }
            if (!result) {
                state.tabs[state.activeTab].error = 'agent_management_session_required';
                mountActiveTab();
                return false;
            }
            state.tabs[state.activeTab].error = '';
            setAudience(result.audience || { kind: 'human', aiId: '' });
            setRoster(result.roster || []);
            state.bootstrappedAudience = state.audience.kind;
            return true;
        } catch (error) {
            state.tabs[state.activeTab].error = String(error && error.message || 'agent_management_bootstrap_failed');
            mountActiveTab();
            return false;
        } finally {
            state.bootstrapping = false;
        }
    }

    function mountTab(name, implementation) {
        if (!['configuration', 'humanResources'].includes(name)) return false;
        state.panels[name] = implementation || null;
        if (state.open && state.activeTab === name) mountActiveTab();
        return true;
    }

    function reportMutation(result) {
        state.mutations.push(Object.assign({ at: Date.now() }, result || {}));
        state.mutations = state.mutations.slice(-20);
        const live = root.document && root.document.getElementById('agent-management-feedback');
        if (live) live.textContent = String(result && (result.message || result.state) || '');
    }

    function renderRoster() {
        const container = root.document && root.document.getElementById('agent-management-roster');
        if (!container) return;
        container.innerHTML = state.roster.map(function (agent) {
            const id = agent.aiId;
            const selected = id === state.selectedAiId;
            return '<button type="button" class="am-roster-item' + (selected ? ' selected' : '') +
                '" data-ai-id="' + esc(id) + '" aria-current="' + (selected ? 'true' : 'false') + '">' +
                '<span class="am-roster-avatar">' + esc(agent.emoji || '🤖') + '</span>' +
                '<span><strong>' + esc(agent.name || agent.displayName || id) + '</strong>' +
                '<small>' + esc(id) + '</small></span></button>';
        }).join('') || '<div class="am-empty">' + esc(tr('agent_management_empty', 'No Agents')) + '</div>';
        container.querySelectorAll('[data-ai-id]').forEach(function (button) {
            button.addEventListener('click', function () {
                selectAgent(button.getAttribute('data-ai-id'));
            });
        });
    }

    function mountActiveTab() {
        const container = panel();
        if (!container) return;
        const tabState = state.tabs[state.activeTab];
        if (tabState && tabState.error) {
            container.innerHTML = '<div class="am-empty ac-error" role="alert">' +
                esc(tr(tabState.error, 'Agent Management session expired. Reopen it from Virtual Office.')) +
                '</div>';
            return;
        }
        const implementation = state.panels[state.activeTab];
        const context = {
            container: container,
            audience: Object.assign({}, state.audience),
            roster: state.roster.slice(),
            selectedAiId: state.selectedAiId,
            adapter: state.audience.kind === 'agent'
                ? state.adapters.agent : state.adapters.human,
            reportMutation: reportMutation,
            setRoster: setRoster,
            selectAgent: selectAgent,
        };
        if (implementation && typeof implementation.mount === 'function') {
            implementation.mount(context);
        } else {
            container.innerHTML = '<div class="am-empty">' +
                esc(state.activeTab === 'configuration'
                    ? tr('agent_configuration_loading', 'Loading Agent configuration…')
                    : tr('human_resources_loading', 'Loading Human Resources…')) +
                '</div>';
        }
        restoreScroll();
    }

    function switchTab(name) {
        if (!['configuration', 'humanResources'].includes(name)) return false;
        saveScroll();
        state.activeTab = name;
        renderTabs();
        mountActiveTab();
        return true;
    }

    function renderTabs() {
        if (!root.document) return;
        root.document.querySelectorAll('[data-agent-management-tab]').forEach(function (button) {
            const active = button.getAttribute('data-agent-management-tab') === state.activeTab;
            button.classList.toggle('active', active);
            button.setAttribute('aria-selected', active ? 'true' : 'false');
            button.setAttribute('tabindex', active ? '0' : '-1');
        });
        const container = panel();
        if (container) {
            container.setAttribute(
                'aria-labelledby',
                state.activeTab === 'configuration'
                    ? 'agent-management-tab-configuration'
                    : 'agent-management-tab-human-resources'
            );
        }
    }

    function render() {
        renderTabs();
        renderRoster();
        mountActiveTab();
        const dialog = modal();
        if (dialog) {
            dialog.setAttribute('data-audience', state.audience.kind);
            dialog.classList.toggle('hidden', !state.open);
        }
    }

    function open(tab) {
        const dialog = modal();
        if (!dialog) return false;
        state.returnFocus = root.document.activeElement;
        state.open = true;
        if (tab) state.activeTab = tab === 'humanResources' ? tab : 'configuration';
        if (!state.roster.length && Array.isArray(root.agents)) setRoster(root.agents);
        render();
        bootstrapAudience();
        const close = root.document.getElementById('agent-management-close');
        if (close && typeof close.focus === 'function') close.focus();
        return true;
    }

    function close() {
        const dialog = modal();
        if (!dialog) return false;
        saveScroll();
        state.open = false;
        dialog.classList.add('hidden');
        const target = state.returnFocus;
        state.returnFocus = null;
        if (target && typeof target.focus === 'function') target.focus();
        return true;
    }

    function handleKeydown(event) {
        if (!state.open) return;
        const tab = event.target && typeof event.target.getAttribute === 'function'
            ? event.target.getAttribute('data-agent-management-tab') : '';
        if (tab && ['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(event.key)) {
            event.preventDefault();
            const next = (
                event.key === 'Home' || (event.key === 'ArrowLeft' && tab === 'humanResources')
            ) ? 'configuration' : (
                event.key === 'End' || (event.key === 'ArrowRight' && tab === 'configuration')
            ) ? 'humanResources' : tab;
            switchTab(next);
            const nextButton = root.document.querySelector(
                '[data-agent-management-tab="' + next + '"]'
            );
            if (nextButton) nextButton.focus();
            return;
        }
        if (event.key === 'Escape') {
            event.preventDefault();
            close();
            return;
        }
        if (event.key === 'Tab') {
            const dialog = modal() && modal().querySelector('.agent-management-dialog');
            if (!dialog) return;
            const focusable = Array.from(dialog.querySelectorAll(
                'button:not([disabled]), [href], input:not([disabled]), textarea:not([disabled]), select:not([disabled]), [tabindex]:not([tabindex="-1"])'
            ));
            if (!focusable.length) return;
            const first = focusable[0];
            const last = focusable[focusable.length - 1];
            if (event.shiftKey && root.document.activeElement === first) {
                event.preventDefault();
                last.focus();
            } else if (!event.shiftKey && root.document.activeElement === last) {
                event.preventDefault();
                first.focus();
            }
        }
    }

    const api = {
        state: state,
        open: open,
        close: close,
        switchTab: switchTab,
        setRoster: setRoster,
        selectAgent: selectAgent,
        setAudience: setAudience,
        setAdapters: setAdapters,
        bootstrapAudience: bootstrapAudience,
        mountTab: mountTab,
        reportMutation: reportMutation,
        render: render,
        helpers: { stableId: stableId, normalizedRoster: normalizedRoster },
    };

    root.AgentManagement = api;
    root.openAgentManagement = open;
    root.closeAgentManagement = close;
    if (root.AgentConfiguration) mountTab('configuration', root.AgentConfiguration);
    if (root.HumanResources) mountTab('humanResources', root.HumanResources);
    root.toggleAgentPanel = function () {
        return state.open ? close() : open('configuration');
    };
    root.openHumanResources = function () { return open('humanResources'); };
    root.closeHumanResources = close;

    if (root.document) {
        root.document.addEventListener('keydown', handleKeydown);
        root.document.addEventListener('DOMContentLoaded', function () {
            [
                'agent-management.css?v=1784910000-merged-shell',
                'agent-configuration.css?v=1784910000-configuration-panel',
            ].forEach(function (href) {
                const name = href.split('?')[0];
                if (root.document.querySelector('link[href*="' + name + '"]')) return;
                const stylesheet = root.document.createElement('link');
                stylesheet.rel = 'stylesheet';
                stylesheet.href = href;
                root.document.head.appendChild(stylesheet);
            });
            if (!root.AgentConfiguration && !root.document.querySelector('script[src*="agent-configuration.js"]')) {
                const script = root.document.createElement('script');
                script.src = 'agent-configuration.js?v=1784910000-configuration-panel';
                root.document.body.appendChild(script);
            }
            if (!root.AgentManagementAdapters && !root.document.querySelector('script[src*="agent-management-adapters.js"]')) {
                const script = root.document.createElement('script');
                script.src = 'agent-management-adapters.js?v=1784910000-audience-adapters';
                root.document.body.appendChild(script);
            }
            const dialog = modal();
            if (dialog) dialog.addEventListener('click', function (event) {
                if (event.target === dialog) close();
            });
            render();
        });
    }

    if (typeof module !== 'undefined' && module.exports) module.exports = api;
})(typeof window !== 'undefined' ? window : globalThis);
