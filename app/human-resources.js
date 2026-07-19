(function (root) {
    'use strict';

    const state = {
        open: false,
        loading: false,
        selectedAgentId: '',
        overview: null,
        agents: [],
        errors: [],
        requestSequence: 0,
    };

    function escHtml(value) {
        return String(value == null ? '' : value)
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;')
            .replace(/'/g, '&#39;');
    }

    function tr(key, fallback, params) {
        if (root.i18n && typeof root.i18n.t === 'function') {
            const translated = root.i18n.t(key, params);
            if (translated && translated !== key) return translated;
        }
        let result = fallback;
        Object.keys(params || {}).forEach(function (name) {
            result = String(result).replace(
                new RegExp('\\{\\{' + name + '\\}\\}', 'g'),
                params[name]
            );
        });
        return result;
    }

    function array(value) {
        return Array.isArray(value) ? value : [];
    }

    function object(value) {
        return value && typeof value === 'object' && !Array.isArray(value) ? value : {};
    }

    function statusTone(status) {
        const value = String(status || '').toLowerCase();
        if (/failed|error|unavailable|disabled|deleted|unreachable/.test(value)) return 'danger';
        if (/pending|waiting|late|paused|retry|not_submitted|processing/.test(value)) return 'warning';
        if (/ready|active|available|complete|submitted|succeeded|ok/.test(value)) return 'success';
        return 'neutral';
    }

    function agentPriority(agent) {
        const value = object(agent);
        let score = 0;
        if (statusTone(value.status) === 'danger') score += 100;
        if (statusTone(value.availability) === 'danger') score += 60;
        if (!['ready', 'updated'].includes(String(value.skill_readiness || value.skillReadiness || ''))) score += 30;
        if (!['ready', 'issued', 'rotated', 'not_required'].includes(String(value.grant_readiness || value.grantReadiness || ''))) score += 20;
        return score;
    }

    function prioritizeAgents(agents) {
        return array(agents).slice().sort(function (left, right) {
            const score = agentPriority(right) - agentPriority(left);
            if (score) return score;
            return String(left.ai_id || left.aiId || '').localeCompare(String(right.ai_id || right.aiId || ''));
        });
    }

    function cycleCounts(overview) {
        const cycle = object(object(overview).cycle);
        const counts = object(cycle.counts);
        const order = [
            'failed', 'normalization_failed', 'not_submitted', 'late',
            'waiting', 'submitted', 'complete', 'skipped'
        ];
        return order
            .map(function (status) { return { status: status, count: Number(counts[status] || 0) }; })
            .filter(function (item) { return item.count > 0; });
    }

    function availabilityCounts(overview) {
        const counts = object(object(overview).availabilityCounts);
        return Object.keys(counts)
            .map(function (name) { return { name: name, count: Number(counts[name] || 0) }; })
            .filter(function (item) { return item.count > 0; })
            .sort(function (left, right) { return right.count - left.count || left.name.localeCompare(right.name); });
    }

    function modal() {
        return root.document ? root.document.getElementById('humanResourcesModal') : null;
    }

    function content() {
        return root.document ? root.document.getElementById('human-resources-content') : null;
    }

    function detail() {
        return root.document ? root.document.querySelector('.hr-agent-detail') : null;
    }

    async function parseResponse(response) {
        const text = await response.text();
        if (!text.trim()) throw new Error('hr_empty_response');
        let payload;
        try {
            payload = JSON.parse(text);
        } catch (_error) {
            throw new Error('hr_invalid_response');
        }
        if (!response.ok || payload.ok === false) {
            throw new Error(String(payload.code || 'hr_request_failed'));
        }
        return payload;
    }

    async function managementJson(url, options) {
        const request = root.i18n && typeof root.i18n.managementFetch === 'function'
            ? root.i18n.managementFetch.bind(root.i18n)
            : root.fetch.bind(root);
        return parseResponse(await request(url, options || {}));
    }

    function renderBadge(label, count, tone) {
        return '<div class="hr-metric hr-tone-' + escHtml(tone) + '">' +
            '<span class="hr-metric-value">' + escHtml(count) + '</span>' +
            '<span class="hr-metric-label">' + escHtml(label) + '</span>' +
            '</div>';
    }

    function agentId(agent) {
        return String(agent.ai_id || agent.aiId || '');
    }

    function agentName(agent) {
        return String(agent.name || agentId(agent) || tr('hr_unknown_agent', 'Unknown Agent'));
    }

    function renderAgent(agent) {
        const id = agentId(agent);
        const availability = String(agent.availability || agent.status || 'unknown');
        const issueCount = agentPriority(agent);
        const selected = state.selectedAgentId === id ? ' is-selected' : '';
        return '<button type="button" class="hr-agent-row' + selected + '" data-agent-id="' +
            escHtml(id) + '" onclick="HumanResources.selectAgent(this.dataset.agentId)">' +
            '<span class="hr-agent-avatar" aria-hidden="true">AI</span>' +
            '<span class="hr-agent-row-copy"><strong>' + escHtml(agentName(agent)) + '</strong>' +
            '<small>' + escHtml(id) + '</small></span>' +
            '<span class="hr-state-chip hr-tone-' + escHtml(statusTone(availability)) + '">' +
            escHtml(availability) + '</span>' +
            (issueCount ? '<span class="hr-attention-dot" title="Needs attention">!</span>' : '') +
            '</button>';
    }

    function renderActivity(item) {
        const activity = object(item);
        const action = String(activity.action || 'activity');
        const status = String(activity.status || 'unknown');
        const timestamp = String(activity.createdAt || activity.created_at || '');
        return '<li><span class="hr-state-chip hr-tone-' + escHtml(statusTone(status)) + '">' +
            escHtml(status) + '</span><span>' + escHtml(action) + '</span>' +
            (timestamp ? '<time datetime="' + escHtml(timestamp) + '">' + escHtml(timestamp) + '</time>' : '') +
            '</li>';
    }

    function renderOverviewPanel() {
        const overview = object(state.overview);
        if (!state.overview && !state.loading) {
            return (state.errors.length ? '<div class="hr-degraded-banner" role="status"><strong>' +
                escHtml(tr('hr_partial_data', 'Some Human Resources data could not be refreshed.')) +
                '</strong><span>' + escHtml(state.errors.join(', ')) + '</span></div>' : '') +
                '<div class="hr-empty-state"><h3>' + escHtml(tr('hr_no_overview', 'No Human Resources overview is available')) +
                '</h3><p>' + escHtml(tr('hr_no_overview_hint', 'Existing records will appear when the HR repository becomes available.')) + '</p></div>';
        }
        const hr = object(overview.hr);
        const hrStatus = String(hr.status || (state.loading ? 'loading' : 'unknown'));
        const availability = availabilityCounts(overview);
        const cycles = cycleCounts(overview);
        const activities = array(overview.recentActivity);
        const degraded = state.errors.length > 0;
        return '<div class="hr-overview">' +
            (degraded ? '<div class="hr-degraded-banner" role="status"><strong>' +
                escHtml(tr('hr_partial_data', 'Some Human Resources data could not be refreshed.')) +
                '</strong><span>' + escHtml(state.errors.join(', ')) + '</span></div>' : '') +
            '<section class="hr-overview-hero hr-tone-' + escHtml(statusTone(hrStatus)) + '">' +
                '<div><span class="hr-eyebrow">' + escHtml(tr('hr_global_agent', 'Global HR Agent')) + '</span>' +
                '<h3>' + escHtml(String(hr.name || 'HR')) + '</h3>' +
                '<p>' + escHtml(tr('hr_overview_date', 'Local reporting date: {{date}}', { date: overview.localDate || '—' })) + '</p></div>' +
                '<span class="hr-state-chip hr-tone-' + escHtml(statusTone(hrStatus)) + '">' + escHtml(hrStatus) + '</span>' +
            '</section>' +
            '<section><h3>' + escHtml(tr('hr_availability', 'Agent availability')) + '</h3><div class="hr-metric-grid">' +
                renderBadge(tr('hr_agent_total', 'Total Agents'), Number(overview.agentTotal || state.agents.length || 0), 'neutral') +
                availability.map(function (item) { return renderBadge(item.name, item.count, statusTone(item.name)); }).join('') +
            '</div></section>' +
            '<section><h3>' + escHtml(tr('hr_daily_status', 'Daily reporting status')) + '</h3>' +
                (cycles.length ? '<div class="hr-metric-grid">' + cycles.map(function (item) {
                    return renderBadge(item.status, item.count, statusTone(item.status));
                }).join('') + '</div>' : '<div class="hr-inline-empty">' + escHtml(tr('hr_no_active_cycle', 'No active or recent cycle')) + '</div>') +
            '</section>' +
            '<section><h3>' + escHtml(tr('hr_recent_activity', 'Recent activity')) + '</h3>' +
                (activities.length ? '<ul class="hr-activity-list">' + activities.map(renderActivity).join('') + '</ul>' :
                    '<div class="hr-inline-empty">' + escHtml(tr('hr_no_recent_activity', 'No recent activity')) + '</div>') +
            '</section>' +
        '</div>';
    }

    function render() {
        const element = content();
        if (!element) return;
        const orderedAgents = prioritizeAgents(state.agents);
        const roster = state.loading && !orderedAgents.length
            ? '<div class="hr-panel-placeholder">' + escHtml(tr('hr_roster_loading', 'Loading Agent roster...')) + '</div>'
            : orderedAgents.map(renderAgent).join('') || '<div class="hr-inline-empty">' + escHtml(tr('hr_empty_roster', 'No Agents are in the HR directory yet.')) + '</div>';
        element.innerHTML = '<div class="hr-shell">' +
            '<aside class="hr-agent-list" aria-label="' + escHtml(tr('hr_agent_roster', 'Agent roster')) + '">' +
                '<div class="hr-roster-header"><div><span class="hr-eyebrow">' + escHtml(tr('hr_directory', 'Directory')) + '</span>' +
                '<strong>' + escHtml(tr('hr_agents_count', '{{count}} Agents', { count: orderedAgents.length })) + '</strong></div>' +
                '<button type="button" class="hr-icon-button" onclick="HumanResources.reload()" aria-label="' + escHtml(tr('hr_refresh', 'Refresh')) + '">↻</button></div>' +
                '<div class="hr-agent-rows">' + roster + '</div>' +
            '</aside>' +
            '<main class="hr-agent-detail" tabindex="-1">' + renderOverviewPanel() + '</main>' +
        '</div>';
        const status = root.document.getElementById('human-resources-status');
        if (status) {
            const value = String(object(state.overview).hr && object(state.overview.hr).status || (state.loading ? 'loading' : 'unavailable'));
            status.textContent = value;
            status.className = 'hr-header-status hr-tone-' + statusTone(value);
        }
    }

    async function loadOverview() {
        const sequence = ++state.requestSequence;
        state.loading = true;
        state.errors = [];
        render();
        const results = await Promise.allSettled([
            managementJson('/api/human-resources/overview'),
            managementJson('/api/human-resources/export?table=agents&limit=100'),
        ]);
        if (sequence !== state.requestSequence) return false;
        if (results[0].status === 'fulfilled') state.overview = results[0].value;
        else state.errors.push(String(results[0].reason && results[0].reason.message || 'hr_overview_failed'));
        if (results[1].status === 'fulfilled') {
            state.agents = array(object(results[1].value.export).rows);
        } else {
            state.errors.push(String(results[1].reason && results[1].reason.message || 'hr_roster_failed'));
        }
        state.loading = false;
        render();
        return state.errors.length === 0;
    }

    function open() {
        const element = modal();
        if (!element) return false;
        state.open = true;
        element.classList.remove('hidden');
        loadOverview();
        const target = detail();
        if (target && typeof target.focus === 'function') target.focus();
        return true;
    }

    function close() {
        const element = modal();
        if (!element) return false;
        state.open = false;
        state.requestSequence += 1;
        element.classList.add('hidden');
        return true;
    }

    function selectAgent(aiId) {
        state.selectedAgentId = String(aiId || '');
        render();
    }

    const api = {
        state,
        open,
        close,
        reload: loadOverview,
        selectAgent,
        render,
        helpers: {
            escHtml,
            statusTone,
            agentPriority,
            prioritizeAgents,
            cycleCounts,
            availabilityCounts,
        },
    };
    root.HumanResources = api;
    root.openHumanResources = open;
    root.closeHumanResources = close;

    if (typeof module !== 'undefined' && module.exports) module.exports = api;
})(typeof window !== 'undefined' ? window : globalThis);
