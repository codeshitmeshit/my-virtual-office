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
        detail: null,
        detailLoading: false,
        detailError: '',
        detailSequence: 0,
        detailPaging: '',
        commandBusy: '',
        commandNotice: '',
        commandError: '',
        commandPollTimer: null,
        dailySyncOpen: false,
        dailySyncSelected: [],
        dailySyncReturnFocus: null,
        returnFocus: null,
    };

    const SEMANTIC_STATES = [
        'accepted', 'active', 'appropriate', 'available', 'awaiting_hr_summary', 'busy',
        'clarification_pending', 'complete', 'conflict', 'creating', 'degraded',
        'deleted', 'delivery_unsupported', 'disabled', 'enablement_pending', 'error',
        'failed', 'high', 'insufficient_information',
        'introduction_pending', 'issued', 'late', 'late_submitted', 'loading', 'low',
        'normalization_failed', 'normalized', 'not_required', 'not_submitted', 'offline',
        'open', 'overloaded', 'paused', 'pending', 'processing', 'published', 'ready',
        'requested', 'response_received', 'retry', 'revoked', 'rotated', 'skill_conflict',
        'skipped', 'submitted', 'succeeded', 'unknown', 'unavailable', 'unreachable',
        'updated', 'waiting', 'working'
    ];
    const ERROR_CODES = [
        'hr_agent_not_found', 'hr_api_validation_failed', 'hr_audit_unavailable',
        'hr_directory_sync_running', 'hr_directory_sync_unavailable', 'hr_disabled', 'hr_empty_response',
        'hr_information_completion_hr_unavailable', 'hr_information_completion_running',
        'hr_information_completion_unavailable', 'hr_internal_error', 'hr_invalid_response',
        'hr_manual_daily_sync_hr_unavailable', 'hr_manual_daily_sync_running',
        'hr_manual_daily_sync_unavailable', 'hr_manual_daily_sync_validation_failed',
        'hr_repository_unavailable', 'hr_request_failed', 'hr_runtime_unavailable'
    ];
    const ACTION_NAMES = [
        'assessment', 'close', 'directory', 'lifecycle', 'pause', 'query',
        'report', 'resume', 'retry', 'run', 'skill', 'sync', 'complete_information', 'manual_daily_sync'
    ];

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

    function semanticLabel(value) {
        const normalized = String(value || 'unknown').toLowerCase().replace(/[^a-z0-9]+/g, '_');
        const fallback = normalized.split('_').map(function (part) {
            return part ? part.charAt(0).toUpperCase() + part.slice(1) : '';
        }).join(' ');
        return tr('hr_state_' + normalized, fallback || tr('hr_state_unknown', 'Unknown'));
    }

    function errorLabel(value) {
        const code = String(value || 'hr_request_failed');
        const normalized = code.toLowerCase().replace(/[^a-z0-9]+/g, '_');
        if (!ERROR_CODES.includes(normalized)) {
            return tr('hr_error_request_failed', 'Human Resources request failed');
        }
        return tr('hr_error_' + normalized.replace(/^hr_/, ''), 'Human Resources request failed');
    }

    function readableReason(value) {
        const raw = String(value == null ? '' : value).trim();
        if (!raw) return '';
        const normalized = raw.toLowerCase().replace(/[^a-z0-9]+/g, '_');
        if (ERROR_CODES.includes(normalized)) return errorLabel(normalized);
        if (SEMANTIC_STATES.includes(normalized)) return semanticLabel(normalized);
        return raw;
    }

    function activityFailureReason(item) {
        const activity = object(item);
        const status = String(activity.status || '').toLowerCase();
        const context = object(activity.context || activity.metadata);
        const candidates = [
            activity.error,
            activity.lastError,
            activity.code,
            activity.reason,
            context.error,
            context.lastError,
            context.code,
            context.reason,
        ];
        for (const candidate of candidates) {
            const label = readableReason(candidate);
            if (label) return label;
        }
        if (statusTone(status) === 'danger') {
            if (Number(context.failed || 0) > 0) {
                return tr('hr_activity_failed_count', '{{count}} failed', { count: Number(context.failed) });
            }
            return readableReason(activity.message);
        }
        return '';
    }

    function workloadTone(workload) {
        const value = String(workload || 'insufficient_information');
        if (value === 'overloaded' || value === 'high') return 'warning';
        if (value === 'appropriate') return 'success';
        return 'neutral';
    }

    function agentPriority(agent) {
        const value = object(agent);
        let score = 0;
        if (statusTone(value.status) === 'danger') score += 100;
        if (statusTone(value.availability) === 'danger') score += 60;
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

    function mergeByKey(current, incoming, key) {
        const result = [];
        const positions = new Map();
        array(current).concat(array(incoming)).forEach(function (item) {
            const value = object(item);
            const identity = String(value[key] == null ? '' : value[key]);
            if (!identity || !positions.has(identity)) {
                positions.set(identity, result.length);
                result.push(value);
            } else {
                result[positions.get(identity)] = value;
            }
        });
        return result;
    }

    function prettyJson(value) {
        try {
            return JSON.stringify(value == null ? {} : value, null, 2);
        } catch (_error) {
            return String(value == null ? '' : value);
        }
    }

    function formatTime(value) {
        if (!value) return '—';
        const date = new Date(value);
        return Number.isNaN(date.getTime()) ? String(value) : date.toLocaleString();
    }

    function reportScheduleLabel(value) {
        const schedule = object(value);
        const raw = String(schedule.nextLocalAt || '');
        const wallTime = raw.length >= 16 ? raw.slice(0, 16).replace('T', ' ') : '—';
        const display = [wallTime, schedule.timezone].filter(Boolean).join(' ');
        if (!raw) return tr('hr_next_report_unknown', 'Next daily report collection is unavailable');
        if (schedule.state === 'due') {
            return tr('hr_next_report_due', 'Daily report collection is due and awaiting the scheduler ({{time}})', { time: display });
        }
        if (!schedule.enabled) {
            return tr('hr_next_report_disabled', 'Next configured report collection after enabling: {{time}}', { time: display });
        }
        return tr('hr_next_report_at', 'Next daily report collection: {{time}}', { time: display });
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

    function captureScroll() {
        if (!root.document) return { roster: 0, detail: 0 };
        const roster = root.document.querySelector('.hr-agent-list');
        const panel = root.document.querySelector('.hr-agent-detail');
        return {
            roster: roster ? roster.scrollTop : 0,
            detail: panel ? panel.scrollTop : 0,
        };
    }

    function restoreScroll(snapshot) {
        if (!root.document || !snapshot) return;
        const callback = function () {
            const roster = root.document.querySelector('.hr-agent-list');
            const panel = root.document.querySelector('.hr-agent-detail');
            if (roster) roster.scrollTop = snapshot.roster || 0;
            if (panel) panel.scrollTop = snapshot.detail || 0;
        };
        if (typeof root.requestAnimationFrame === 'function') root.requestAnimationFrame(callback);
        else callback();
    }

    function focusableElements() {
        const element = state.dailySyncOpen && root.document
            ? root.document.querySelector('.hr-selection-dialog') || modal()
            : modal();
        if (!element) return [];
        return Array.from(element.querySelectorAll(
            'button:not([disabled]), a[href], input:not([disabled]), select:not([disabled]), ' +
            'textarea:not([disabled]), details > summary, [tabindex]:not([tabindex="-1"])'
        )).filter(function (item) { return !item.closest('.hidden'); });
    }

    function handleKeydown(event) {
        if (!state.open || !event) return;
        if (event.key === 'Escape') {
            event.preventDefault();
            if (state.dailySyncOpen) closeDailySync();
            else close();
            return;
        }
        if (event.key !== 'Tab') return;
        const items = focusableElements();
        if (!items.length) return;
        const first = items[0];
        const last = items[items.length - 1];
        if (event.shiftKey && root.document.activeElement === first) {
            event.preventDefault();
            last.focus();
        } else if (!event.shiftKey && root.document.activeElement === last) {
            event.preventDefault();
            first.focus();
        }
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
            escHtml(id) + '" onclick="HumanResources.selectAgent(this.dataset.agentId)"' +
            (selected ? ' aria-current="true"' : '') + '>' +
            '<span class="hr-agent-avatar" aria-hidden="true">AI</span>' +
            '<span class="hr-agent-row-copy"><strong>' + escHtml(agentName(agent)) + '</strong>' +
            '<small>' + escHtml(id) + '</small></span>' +
            '<span class="hr-state-chip hr-tone-' + escHtml(statusTone(availability)) + '">' +
            escHtml(semanticLabel(availability)) + '</span>' +
            (issueCount ? '<span class="hr-attention-dot" title="' + escHtml(tr('hr_needs_attention', 'Needs attention')) + '">!</span>' : '') +
            '</button>';
    }

    function renderActivity(item) {
        const activity = object(item);
        const action = String(activity.action || 'activity');
        const status = String(activity.status || 'unknown');
        const timestamp = String(activity.createdAt || activity.created_at || '');
        const reason = activityFailureReason(activity);
        return '<li><span class="hr-state-chip hr-tone-' + escHtml(statusTone(status)) + '">' +
            escHtml(semanticLabel(status)) + '</span><span>' + escHtml(actionLabel(action)) + '</span>' +
            (timestamp ? '<time datetime="' + escHtml(timestamp) + '">' + escHtml(timestamp) + '</time>' : '') +
            (reason ? '<small class="hr-activity-detail">' + escHtml(tr('hr_activity_failure_reason', 'Reason: {{reason}}', { reason })) + '</small>' : '') +
            '</li>';
    }

    function activeCommands(overview) {
        return array(object(overview).activeCommands).filter(function (item) {
            const status = String(object(item).status || '').toLowerCase();
            return status === 'accepted' || status === 'processing';
        });
    }

    function activeCommandFor(action) {
        return activeCommands(state.overview).find(function (item) {
            return String(object(item).action || '') === action;
        }) || null;
    }

    function renderOverviewPanel() {
        const overview = object(state.overview);
        if (!state.overview && !state.loading) {
            return (state.errors.length ? '<div class="hr-degraded-banner" role="status"><strong>' +
                escHtml(tr('hr_partial_data', 'Some Human Resources data could not be refreshed.')) +
                '</strong><span>' + escHtml(state.errors.map(errorLabel).join(', ')) + '</span></div>' : '') +
                '<div class="hr-empty-state"><h3>' + escHtml(tr('hr_no_overview', 'No Human Resources overview is available')) +
                '</h3><p>' + escHtml(tr('hr_no_overview_hint', 'Existing records will appear when the HR repository becomes available.')) + '</p></div>';
        }
        const hr = object(overview.hr);
        const hrStatus = String(hr.status || (state.loading ? 'loading' : 'unknown'));
        const reportSchedule = object(overview.reportSchedule);
        const availability = availabilityCounts(overview);
        const cycles = cycleCounts(overview);
        const activities = array(overview.recentActivity);
        const runningCommands = activeCommands(overview);
        const visibleHrStatus = runningCommands.length ? 'working' : hrStatus;
        const degraded = state.errors.length > 0;
        const cycle = object(overview.cycle);
        const lifecycleAction = hrStatus === 'paused' ? 'resume' : 'pause';
        const commandButton = function (action, label, danger) {
            const active = activeCommandFor(action);
            const busy = Boolean(state.commandBusy) || runningCommands.length > 0;
            return '<button type="button" class="hr-command-button' + (danger ? ' danger' : '') +
                '" onclick="HumanResources.runCommand(\'' + escHtml(action) + '\')"' +
                (busy ? ' disabled' : '') + '>' + escHtml(
                    state.commandBusy === action || active
                        ? tr('hr_command_working', 'Working...')
                        : label
                ) + '</button>';
        };
        const availableAgents = orderedAvailableAgents();
        const dailySyncDialog = state.dailySyncOpen ? renderDailySyncDialog(availableAgents) : '';
        return '<div class="hr-overview">' +
            (degraded ? '<div class="hr-degraded-banner" role="status"><strong>' +
                escHtml(tr('hr_partial_data', 'Some Human Resources data could not be refreshed.')) +
                '</strong><span>' + escHtml(state.errors.map(errorLabel).join(', ')) + '</span></div>' : '') +
            '<section class="hr-overview-hero hr-tone-' + escHtml(statusTone(visibleHrStatus)) + '">' +
                '<div><span class="hr-eyebrow">' + escHtml(tr('hr_global_agent', 'Global HR Agent')) + '</span>' +
                '<h3>' + escHtml(String(hr.name || 'HR')) + '</h3>' +
                '<p>' + escHtml(tr('hr_overview_date', 'Local reporting date: {{date}}', { date: overview.localDate || '—' })) + '</p>' +
                '<p class="hr-next-report-time">' + escHtml(reportScheduleLabel(reportSchedule)) + '</p></div>' +
                '<span class="hr-state-chip hr-tone-' + escHtml(statusTone(visibleHrStatus)) + '">' + escHtml(semanticLabel(visibleHrStatus)) + '</span>' +
            '</section>' +
            '<section class="hr-command-panel"><div><h3>' + escHtml(tr('hr_controls', 'HR controls')) + '</h3>' +
                '<p>' + escHtml(tr('hr_controls_hint', 'Commands run asynchronously; active sync discovers Agents, while complete information asks available Agents for missing introductions.')) + '</p></div>' +
                '<div class="hr-command-actions">' +
                    commandButton('sync', tr('hr_sync_team', 'Sync Agent team'), false) +
                    commandButton('complete_information', tr('hr_complete_information', 'Complete information'), false) +
                    '<button type="button" class="hr-command-button" onclick="HumanResources.openDailySync()"' +
                    (state.commandBusy || runningCommands.length ? ' disabled' : '') + '>' + escHtml(
                        activeCommandFor('manual_daily_sync')
                            ? tr('hr_command_working', 'Working...')
                            : tr('hr_daily_sync', 'Daily report')
                    ) + '</button>' +
                    commandButton(lifecycleAction, lifecycleAction === 'pause' ? tr('hr_pause', 'Pause HR') : tr('hr_resume', 'Resume HR'), lifecycleAction === 'pause') +
                    commandButton('run', tr('hr_run_cycle', 'Run cycle'), false) +
                    (cycle.cycleId && cycle.status === 'open' ? commandButton('close', tr('hr_close_cycle', 'Close cycle'), true) : '') +
                    (cycle.cycleId ? commandButton('retry', tr('hr_retry_cycle', 'Retry failed work'), false) : '') +
                '</div></section>' +
            (runningCommands.length ? '<div class="hr-command-message running" role="status" aria-live="polite">' +
                '<strong>' + escHtml(tr('hr_command_running_title', 'Task in progress')) + '</strong><span>' +
                escHtml(runningCommands.map(function (item) {
                    const command = object(item);
                    return actionLabel(String(command.action || 'activity')) + ' · ' +
                        semanticLabel(String(command.status || 'processing'));
                }).join(', ')) + '</span></div>' : '') +
            (state.commandNotice ? '<div class="hr-command-message success" role="status">' + escHtml(state.commandNotice) + '</div>' : '') +
            (state.commandError ? '<div class="hr-command-message error" role="alert">' + escHtml(errorLabel(state.commandError)) + '</div>' : '') +
            '<section><h3>' + escHtml(tr('hr_availability', 'Agent availability')) + '</h3><div class="hr-metric-grid">' +
                renderBadge(tr('hr_agent_total', 'Total Agents'), Number(overview.agentTotal || state.agents.length || 0), 'neutral') +
                availability.map(function (item) { return renderBadge(semanticLabel(item.name), item.count, statusTone(item.name)); }).join('') +
            '</div></section>' +
            '<section><h3>' + escHtml(tr('hr_daily_status', 'Daily reporting status')) + '</h3>' +
                (cycles.length ? '<div class="hr-metric-grid">' + cycles.map(function (item) {
                    return renderBadge(semanticLabel(item.status), item.count, statusTone(item.status));
                }).join('') + '</div>' : '<div class="hr-inline-empty">' + escHtml(tr('hr_no_active_cycle', 'No active or recent cycle')) + '</div>') +
            '</section>' + dailySyncDialog +
            '<section><h3>' + escHtml(tr('hr_recent_activity', 'Recent activity')) + '</h3>' +
                (activities.length ? '<ul class="hr-activity-list">' + activities.map(renderActivity).join('') + '</ul>' :
                    '<div class="hr-inline-empty">' + escHtml(tr('hr_no_recent_activity', 'No recent activity')) + '</div>') +
            '</section>' +
        '</div>';
    }

    function orderedAvailableAgents() {
        return prioritizeAgents(state.agents).filter(function (agent) {
            const id = agentId(agent);
            const status = String(agent.status || 'active').toLowerCase();
            const availability = String(agent.availability || '').toLowerCase();
            return id && id !== 'hr' && status === 'active' && !['offline', 'unavailable', 'unreachable', 'disabled', 'deleted'].includes(availability);
        });
    }

    function renderDailySyncDialog(agents) {
        const selected = new Set(state.dailySyncSelected);
        const allSelected = agents.length > 0 && agents.every(function (agent) { return selected.has(agentId(agent)); });
        return '<div class="hr-selection-backdrop" role="presentation"><section class="hr-selection-dialog" role="dialog" aria-modal="true" aria-labelledby="hr-daily-sync-title">' +
            '<header><div><h3 id="hr-daily-sync-title">' + escHtml(tr('hr_daily_sync_title', 'Resubmit daily reports')) + '</h3>' +
            '<p>' + escHtml(tr('hr_daily_sync_hint', 'Choose available Agents. Successful reports replace today’s report and immediately refresh the assessment.')) + '</p></div>' +
            '<button type="button" class="hr-icon-button" onclick="HumanResources.closeDailySync()" aria-label="' + escHtml(tr('hr_cancel', 'Cancel')) + '">×</button></header>' +
            '<label class="hr-selection-all"><input type="checkbox" onchange="HumanResources.toggleDailySyncAll(this.checked)"' + (allSelected ? ' checked' : '') + '> ' + escHtml(tr('hr_select_all', 'Select all')) + '</label>' +
            '<div class="hr-selection-list">' + agents.map(function (agent) {
                const id = agentId(agent);
                return '<label><input type="checkbox" value="' + escHtml(id) + '" onchange="HumanResources.toggleDailySyncAgent(this.value, this.checked)"' + (selected.has(id) ? ' checked' : '') + '><span><strong>' + escHtml(agentName(agent)) + '</strong><small>' + escHtml(id) + '</small></span></label>';
            }).join('') + '</div>' +
            '<footer><button type="button" class="hr-command-button" onclick="HumanResources.closeDailySync()">' + escHtml(tr('hr_cancel', 'Cancel')) + '</button>' +
            '<button type="button" class="hr-command-button" onclick="HumanResources.submitDailySync()"' + (!selected.size ? ' disabled' : '') + '>' + escHtml(tr('hr_submit_daily_sync', 'Sync selected')) + '</button></footer>' +
            '</section></div>';
    }

    function openDailySync() {
        state.dailySyncReturnFocus = root.document ? root.document.activeElement : null;
        state.dailySyncOpen = true;
        state.dailySyncSelected = [];
        render();
        const first = root.document && root.document.querySelector('.hr-selection-dialog input');
        if (first && typeof first.focus === 'function') first.focus();
    }

    function closeDailySync() {
        state.dailySyncOpen = false;
        state.dailySyncSelected = [];
        render();
        const target = state.dailySyncReturnFocus;
        state.dailySyncReturnFocus = null;
        if (target && typeof target.focus === 'function') target.focus();
    }

    function toggleDailySyncAll(checked) {
        state.dailySyncSelected = checked ? orderedAvailableAgents().map(agentId) : [];
        render();
    }

    function toggleDailySyncAgent(aiId, checked) {
        const selected = new Set(state.dailySyncSelected);
        if (checked) selected.add(String(aiId)); else selected.delete(String(aiId));
        state.dailySyncSelected = Array.from(selected);
        render();
    }

    async function submitDailySync() {
        if (!state.dailySyncSelected.length || state.commandBusy || activeCommands(state.overview).length) return false;
        const selected = state.dailySyncSelected.slice();
        state.dailySyncOpen = false;
        state.commandBusy = 'manual_daily_sync';
        state.commandError = '';
        render();
        try {
            await managementJson('/api/human-resources/daily-sync', {
                method: 'POST', headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ agentIds: selected }),
            });
            state.commandNotice = tr('hr_command_accepted', 'Command accepted: {{action}}', { action: actionLabel('manual_daily_sync') });
            await loadOverview();
            return true;
        } catch (error) {
            state.commandError = String(error && error.message || 'hr_request_failed');
            return false;
        } finally {
            state.commandBusy = '';
            state.dailySyncSelected = [];
            render();
        }
    }

    function renderTextList(values, emptyText) {
        const items = array(values);
        return items.length
            ? '<ul class="hr-detail-list">' + items.map(function (item) {
                return '<li>' + escHtml(typeof item === 'string' ? item : prettyJson(item)) + '</li>';
            }).join('') + '</ul>'
            : '<span class="hr-muted">' + escHtml(emptyText || '—') + '</span>';
    }

    function renderReport(report) {
        const item = object(report);
        const status = String(item.submissionState || 'unknown');
        return '<article class="hr-record-card">' +
            '<header><div><strong>' + escHtml(item.localDate || '—') + '</strong>' +
            '<small>' + escHtml(tr('hr_revision', 'Revision {{version}}', { version: item.revision || 1 })) + '</small></div>' +
            '<span class="hr-state-chip hr-tone-' + escHtml(statusTone(status)) + '">' + escHtml(semanticLabel(status)) + '</span></header>' +
            '<details><summary>' + escHtml(tr('hr_raw_report', 'Raw Agent report')) + '</summary>' +
            '<pre>' + escHtml(item.rawResponse || tr('hr_no_raw_report', 'No raw response')) + '</pre></details>' +
            '<details open><summary>' + escHtml(tr('hr_normalized_report', 'HR normalized report')) + '</summary>' +
            '<pre>' + escHtml(item.normalized ? prettyJson(item.normalized) : tr('hr_not_normalized', 'Not normalized')) + '</pre></details>' +
            '<footer>' + escHtml(formatTime(item.submittedAt || item.requestedAt)) + '</footer>' +
        '</article>';
    }

    function renderEvidence(evidence) {
        const item = object(evidence);
        return '<li><strong>' + escHtml(item.evidenceType || 'evidence') + '</strong>' +
            '<span>' + escHtml(item.summary || item.referenceId || '—') + '</span>' +
            (item.referenceId ? '<code>' + escHtml(item.referenceId) + '</code>' : '') + '</li>';
    }

    function renderAssessment(assessment) {
        const item = object(assessment);
        const workload = String(item.workload || 'insufficient_information');
        return '<article class="hr-record-card hr-assessment-card">' +
            '<header><div><strong>' + escHtml(item.localDate || '—') + '</strong>' +
            '<small>' + escHtml(tr('hr_assessment_version', 'Assessment v{{version}}', { version: item.version || 1 })) +
            (item.isCurrent ? ' · ' + escHtml(tr('hr_current', 'Current')) : '') + '</small></div>' +
            '<span class="hr-state-chip hr-tone-' + escHtml(statusTone(item.status)) + '">' + escHtml(semanticLabel(item.status)) + '</span></header>' +
            '<div class="hr-workload-line"><span>' + escHtml(tr('hr_workload', 'Workload')) + '</span>' +
            '<strong class="hr-tone-' + escHtml(workloadTone(workload)) + '">' + escHtml(semanticLabel(workload)) + '</strong></div>' +
            '<p>' + escHtml(item.rationale || tr('hr_no_rationale', 'No rationale recorded')) + '</p>' +
            '<div class="hr-assessment-grid">' +
                '<div><h5>' + escHtml(tr('hr_contributions', 'Principal contributions')) + '</h5>' + renderTextList(item.principalContributions) + '</div>' +
                '<div><h5>' + escHtml(tr('hr_strengths', 'Strengths')) + '</h5>' + renderTextList(item.strengths) + '</div>' +
                '<div><h5>' + escHtml(tr('hr_blockers', 'Blockers')) + '</h5>' + renderTextList(item.blockers) + '</div>' +
                '<div><h5>' + escHtml(tr('hr_improvements', 'Improvement opportunities')) + '</h5>' + renderTextList(item.improvements) + '</div>' +
            '</div>' +
            '<div class="hr-runtime-diagnosis"><strong>' + escHtml(tr('hr_runtime_diagnosis', 'Runtime diagnosis')) + '</strong><span>' +
            escHtml(item.runtimeDiagnosis || '—') + '</span></div>' +
            (array(item.evidence).length ? '<details><summary>' + escHtml(tr('hr_evidence', 'Evidence')) + '</summary><ul class="hr-evidence-list">' +
                array(item.evidence).map(renderEvidence).join('') + '</ul></details>' : '') +
            '<footer>' + escHtml(formatTime(item.updatedAt || item.createdAt)) + '</footer>' +
        '</article>';
    }

    function renderIdentityHistory(items) {
        return array(items).map(function (entry) {
            const item = object(entry);
            return '<li><strong>' + escHtml(item.name || item.aiId || '—') + '</strong>' +
                '<span>' + escHtml(semanticLabel(item.status)) + ' · ' + escHtml(item.source || semanticLabel('unknown')) + '</span>' +
                '<time>' + escHtml(formatTime(item.observedAt)) + '</time></li>';
        }).join('');
    }

    function renderAccessHistory(items) {
        return array(items).map(function (entry) {
            const item = object(entry);
            return '<li><strong>' + escHtml(item.viewerName || item.viewerAiId || '—') + '</strong>' +
                '<span>' + escHtml(item.scope || 'public') + '</span>' +
                '<time>' + escHtml(formatTime(item.viewedAt)) + '</time></li>';
        }).join('');
    }

    function loadMoreButton(kind, cursor) {
        const busy = state.detailPaging === kind;
        return cursor ? '<button type="button" class="hr-load-more" onclick="HumanResources.loadMore(\'' +
            escHtml(kind) + '\')"' + (busy ? ' disabled' : '') + '>' +
            escHtml(busy ? tr('hr_loading_more', 'Loading...') : tr('hr_load_more', 'Load more')) + '</button>' : '';
    }

    function renderAgentDetailPanel() {
        if (state.detailLoading && !state.detail) {
            return '<div class="hr-panel-placeholder">' + escHtml(tr('hr_detail_loading', 'Loading Agent Human Resources detail...')) + '</div>';
        }
        if (!state.detail) {
            return '<div class="hr-empty-state"><h3>' + escHtml(tr('hr_detail_unavailable', 'Agent detail is unavailable')) + '</h3>' +
                '<p>' + escHtml(state.detailError ? errorLabel(state.detailError) : tr('hr_select_agent', 'Select an Agent to inspect Human Resources records.')) + '</p></div>';
        }
        const agent = object(state.detail);
        const reports = array(agent.reports);
        const assessments = array(agent.assessments);
        const identities = array(agent.identityHistory);
        const accesses = array(agent.accessHistory);
        return '<div class="hr-detail-view">' +
            (state.detailError ? '<div class="hr-degraded-banner" role="status">' + escHtml(errorLabel(state.detailError)) + '</div>' : '') +
            '<button type="button" class="hr-back-button" onclick="HumanResources.selectAgent(\'\')">' + escHtml(tr('hr_back_overview', '← HR overview')) + '</button>' +
            '<section class="hr-detail-hero"><div><span class="hr-eyebrow">' + escHtml(agent.aiId || '—') + '</span>' +
                '<h3>' + escHtml(agent.name || agent.aiId || '—') + '</h3><p>' + escHtml(agent.introduction || tr('hr_no_introduction', 'No introduction')) + '</p></div>' +
                '<div class="hr-detail-statuses"><span class="hr-state-chip hr-tone-' + escHtml(statusTone(agent.status)) + '">' + escHtml(semanticLabel(agent.status)) + '</span>' +
                '<span class="hr-state-chip hr-tone-' + escHtml(statusTone(agent.availability)) + '">' + escHtml(semanticLabel(agent.availability)) + '</span></div></section>' +
            '<section class="hr-detail-metadata"><div><span>' + escHtml(tr('hr_agent_kind', 'Agent kind')) + '</span><strong>' + escHtml(agent.agentKind || '—') + '</strong></div>' +
                '<div><span>' + escHtml(tr('hr_provider', 'Provider')) + '</span><strong>' + escHtml(agent.providerKind || '—') + '</strong></div>' +
                '<div><span>' + escHtml(tr('hr_introduction_source', 'Introduction source')) + '</span><strong>' + escHtml(object(agent.introductionProvenance).source || '—') + '</strong></div>' +
                '<div><span>' + escHtml(tr('hr_workflow_state', 'Workflow state')) + '</span><strong>' + escHtml(semanticLabel(agent.workflowState)) + '</strong></div></section>' +
            '<section class="hr-detail-section"><h4>' + escHtml(tr('hr_identity_history', 'Identity and provenance')) + '</h4>' +
                (identities.length ? '<ul class="hr-history-list">' + renderIdentityHistory(identities) + '</ul>' : '<div class="hr-inline-empty">—</div>') + '</section>' +
            '<section class="hr-detail-section"><h4>' + escHtml(tr('hr_daily_reports', 'Daily reports')) + '</h4>' +
                (reports.length ? '<div class="hr-record-list">' + reports.map(renderReport).join('') + '</div>' : '<div class="hr-inline-empty">' + escHtml(tr('hr_no_reports', 'No daily reports')) + '</div>') +
                loadMoreButton('reports', agent.reportNextCursor) + '</section>' +
            '<section class="hr-detail-section"><h4>' + escHtml(tr('hr_assessments', 'HR assessments')) + '</h4>' +
                (assessments.length ? '<div class="hr-record-list">' + assessments.map(renderAssessment).join('') + '</div>' : '<div class="hr-inline-empty">' + escHtml(tr('hr_no_assessments', 'No assessments')) + '</div>') +
                loadMoreButton('assessments', agent.assessmentNextCursor) + '</section>' +
            '<section class="hr-detail-section"><h4>' + escHtml(tr('hr_access_history', 'Agent access history')) + '</h4>' +
                (accesses.length ? '<ul class="hr-history-list">' + renderAccessHistory(accesses) + '</ul>' : '<div class="hr-inline-empty">' + escHtml(tr('hr_no_access_history', 'No Agent has viewed this record')) + '</div>') +
                loadMoreButton('access', agent.accessNextCursor) + '</section>' +
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
            '<main class="hr-agent-detail" tabindex="-1">' +
                (state.selectedAgentId ? renderAgentDetailPanel() : renderOverviewPanel()) + '</main>' +
        '</div>';
        element.setAttribute(
            'aria-busy',
            state.loading || state.detailLoading || Boolean(state.commandBusy) || activeCommands(state.overview).length ? 'true' : 'false'
        );
        const closeButton = root.document.getElementById('human-resources-close');
        if (closeButton) closeButton.setAttribute('aria-label', tr('hr_close', 'Close Human Resources'));
    }

    function clearCommandPoll() {
        if (state.commandPollTimer !== null && typeof root.clearTimeout === 'function') {
            root.clearTimeout(state.commandPollTimer);
        }
        state.commandPollTimer = null;
    }

    function scheduleCommandPoll() {
        clearCommandPoll();
        if (!state.open || !activeCommands(state.overview).length || typeof root.setTimeout !== 'function') return;
        state.commandPollTimer = root.setTimeout(function () {
            state.commandPollTimer = null;
            loadOverview(captureScroll());
        }, 1500);
    }

    async function loadOverview(scrollSnapshot) {
        const sequence = ++state.requestSequence;
        state.loading = true;
        state.errors = [];
        render();
        restoreScroll(scrollSnapshot);
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
        restoreScroll(scrollSnapshot);
        scheduleCommandPoll();
        return state.errors.length === 0;
    }

    function commandSpec(action) {
        const cycleId = object(object(state.overview).cycle).cycleId;
        if (action === 'pause' || action === 'resume') {
            return { url: '/api/human-resources/hr/' + action, body: {} };
        }
        if (action === 'sync') return { url: '/api/human-resources/directory/sync', body: {} };
        if (action === 'complete_information') return { url: '/api/human-resources/directory/complete-information', body: {} };
        if (action === 'run') return { url: '/api/human-resources/cycles/run', body: {} };
        if ((action === 'close' || action === 'retry') && cycleId) {
            return { url: '/api/human-resources/cycles/' + action, body: { cycleId: cycleId } };
        }
        return null;
    }

    function actionLabel(action) {
        const fallbacks = {
            assessment: 'Assessment',
            pause: 'Pause HR',
            resume: 'Resume HR',
            run: 'Run cycle',
            close: 'Close cycle',
            directory: 'Directory',
            lifecycle: 'HR lifecycle',
            query: 'Query',
            report: 'Daily report',
            retry: 'Retry failed work',
            skill: 'Skill distribution',
            sync: 'Sync Agent team',
            complete_information: 'Complete information',
            manual_daily_sync: 'Daily report',
        };
        return ACTION_NAMES.includes(action)
            ? tr('hr_action_' + action, fallbacks[action] || action)
            : tr('hr_action_activity', 'HR activity');
    }

    async function runCommand(action) {
        if (state.commandBusy || activeCommands(state.overview).length) return false;
        const spec = commandSpec(action);
        if (!spec) return false;
        const confirmation = tr('hr_confirm_command', 'Confirm Human Resources action: {{action}}?', { action: actionLabel(action) });
        if (typeof root.confirm === 'function' && !root.confirm(confirmation)) return false;
        const scrollSnapshot = captureScroll();
        state.commandBusy = action;
        state.commandNotice = '';
        state.commandError = '';
        render();
        restoreScroll(scrollSnapshot);
        try {
            await managementJson(spec.url, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(spec.body),
            });
            state.commandNotice = tr('hr_command_accepted', 'Command accepted: {{action}}', { action: actionLabel(action) });
            await loadOverview(scrollSnapshot);
            return true;
        } catch (error) {
            state.commandError = String(error && error.message || 'hr_command_failed');
            return false;
        } finally {
            state.commandBusy = '';
            render();
            restoreScroll(scrollSnapshot);
        }
    }

    function open() {
        const element = modal();
        if (!element) return false;
        state.returnFocus = root.document ? root.document.activeElement : null;
        state.open = true;
        element.classList.remove('hidden');
        loadOverview();
        const closeButton = root.document.getElementById('human-resources-close');
        if (closeButton && typeof closeButton.focus === 'function') closeButton.focus();
        return true;
    }

    function close() {
        const element = modal();
        if (!element) return false;
        state.open = false;
        state.requestSequence += 1;
        state.detailSequence += 1;
        clearCommandPoll();
        element.classList.add('hidden');
        const target = state.returnFocus;
        state.returnFocus = null;
        if (target && typeof target.focus === 'function') target.focus();
        return true;
    }

    async function loadAgent(aiId, sequence, pageKind) {
        const params = new URLSearchParams({
            reportLimit: '10',
            assessmentLimit: '10',
            accessLimit: '10',
        });
        const current = object(state.detail);
        if (pageKind === 'reports' && current.reportNextCursor) {
            params.set('reportCursor', current.reportNextCursor);
        } else if (pageKind === 'assessments' && current.assessmentNextCursor) {
            params.set('assessmentCursor', current.assessmentNextCursor);
        } else if (pageKind === 'access' && current.accessNextCursor) {
            params.set('accessCursor', current.accessNextCursor);
        }
        try {
            const payload = await managementJson(
                '/api/human-resources/agents/' + encodeURIComponent(aiId) + '?' + params.toString()
            );
            if (sequence !== state.detailSequence || state.selectedAgentId !== aiId) return false;
            const incoming = object(payload.agent);
            if (!pageKind || !state.detail) {
                state.detail = incoming;
            } else if (pageKind === 'reports') {
                state.detail.reports = mergeByKey(state.detail.reports, incoming.reports, 'id');
                state.detail.reportNextCursor = incoming.reportNextCursor || null;
            } else if (pageKind === 'assessments') {
                state.detail.assessments = mergeByKey(state.detail.assessments, incoming.assessments, 'id');
                state.detail.assessmentNextCursor = incoming.assessmentNextCursor || null;
            } else if (pageKind === 'access') {
                state.detail.accessHistory = mergeByKey(state.detail.accessHistory, incoming.accessHistory, 'id');
                state.detail.accessNextCursor = incoming.accessNextCursor || null;
            }
            state.detailError = '';
            return true;
        } catch (error) {
            if (sequence !== state.detailSequence || state.selectedAgentId !== aiId) return false;
            state.detailError = String(error && error.message || 'hr_detail_failed');
            return false;
        } finally {
            if (sequence === state.detailSequence && state.selectedAgentId === aiId) {
                state.detailLoading = false;
                state.detailPaging = '';
                render();
                if (!pageKind) {
                    const target = detail();
                    if (target && typeof target.focus === 'function') target.focus();
                }
            }
        }
    }

    function selectAgent(aiId) {
        const selected = String(aiId || '');
        state.selectedAgentId = selected;
        state.detail = null;
        state.detailError = '';
        state.detailPaging = '';
        const sequence = ++state.detailSequence;
        if (!selected) {
            state.detailLoading = false;
            render();
            return Promise.resolve(true);
        }
        state.detailLoading = true;
        render();
        return loadAgent(selected, sequence, '');
    }

    function loadMore(kind) {
        if (!['reports', 'assessments', 'access'].includes(kind)) return Promise.resolve(false);
        if (!state.selectedAgentId || !state.detail || state.detailPaging) return Promise.resolve(false);
        const cursorKey = {
            reports: 'reportNextCursor',
            assessments: 'assessmentNextCursor',
            access: 'accessNextCursor',
        }[kind];
        if (!state.detail[cursorKey]) return Promise.resolve(false);
        state.detailPaging = kind;
        render();
        return loadAgent(state.selectedAgentId, state.detailSequence, kind);
    }

    const api = {
        state,
        open,
        close,
        reload: loadOverview,
        selectAgent,
        loadMore,
        runCommand,
        openDailySync,
        closeDailySync,
        toggleDailySyncAll,
        toggleDailySyncAgent,
        submitDailySync,
        render,
        helpers: {
            escHtml,
            statusTone,
            workloadTone,
            agentPriority,
            prioritizeAgents,
            cycleCounts,
            availabilityCounts,
            mergeByKey,
            prettyJson,
            reportScheduleLabel,
            activeCommands,
            commandSpec,
            semanticLabel,
            semanticStates: SEMANTIC_STATES.slice(),
            errorLabel,
            errorCodes: ERROR_CODES.slice(),
            readableReason,
            activityFailureReason,
            actionNames: ACTION_NAMES.slice(),
            handleKeydown,
        },
    };
    root.HumanResources = api;
    root.openHumanResources = open;
    root.closeHumanResources = close;

    if (root.document && typeof root.document.addEventListener === 'function') {
        root.document.addEventListener('keydown', handleKeydown);
    }

    if (typeof module !== 'undefined' && module.exports) module.exports = api;
})(typeof window !== 'undefined' ? window : globalThis);
