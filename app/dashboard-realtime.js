(function () {
    'use strict';

    var source = null;
    var fallbackTimer = null;
    var reconnectTimer = null;
    var mode = 'starting';
    var seenActions = Object.create(null);
    var fallbackMs = 2000;

    function t(key, fallback) {
        try {
            if (typeof i18n !== 'undefined' && i18n && typeof i18n.t === 'function') {
                var value = i18n.t(key);
                return value && value !== key ? value : fallback;
            }
        } catch (_) {}
        return fallback;
    }

    function ensureIndicator() {
        var existing = document.getElementById('dashboard-realtime-status');
        if (existing) return existing;
        var panel = document.querySelector('.status-panel');
        if (!panel || !panel.parentNode) return null;
        var el = document.createElement('div');
        el.id = 'dashboard-realtime-status';
        el.className = 'dashboard-realtime-status starting';
        el.innerHTML = '<span class="drt-dot"></span><span class="drt-label"></span>';
        panel.parentNode.insertBefore(el, panel);
        return el;
    }

    function setMode(nextMode, detail) {
        mode = nextMode;
        var el = ensureIndicator();
        if (!el) return;
        var labels = {
            starting: t('dashboard_realtime_starting', 'Realtime: connecting...'),
            sse: t('dashboard_realtime_sse', 'Realtime: SSE connected'),
            reconnecting: t('dashboard_realtime_reconnecting', 'Realtime: SSE reconnecting'),
            polling: t('dashboard_realtime_polling', 'Realtime: polling fallback')
        };
        el.className = 'dashboard-realtime-status ' + nextMode;
        var label = el.querySelector('.drt-label');
        if (label) label.textContent = labels[nextMode] || labels.starting;
        el.title = detail || label && label.textContent || '';
    }

    function refreshModeLabel() {
        setMode(mode || 'starting');
    }

    function applyStatus(statusPayload) {
        if (!statusPayload || !statusPayload.agents) return;
        var snapshot = {};
        Object.keys(statusPayload.agents).forEach(function (key) {
            snapshot[key] = statusPayload.agents[key];
        });
        snapshot._meetings = statusPayload.meetings || [];
        if (typeof window.dashboardApplyStatusSnapshot === 'function') {
            window.dashboardApplyStatusSnapshot(snapshot, { logRoutine: false });
        }
    }

    function applyMeetings(meetingPayload) {
        if (!meetingPayload) return;
        var active = meetingPayload.active || [];
        var pending = meetingPayload.pendingRequests || [];
        if (typeof window._mtgData === 'object' && window._mtgData) {
            window._mtgData.active = active;
            window._mtgData.requests = typeof window._mtgSortRequestsByStatusThenTime === 'function'
                ? window._mtgSortRequestsByStatusThenTime(pending)
                : pending;
        }
        if (typeof window._mtgSeedLiveMeetings === 'function') window._mtgSeedLiveMeetings(active);
        if (Array.isArray(active) && typeof window._mtgMaybeAutoContinueDecisionMeeting === 'function') {
            active.forEach(window._mtgMaybeAutoContinueDecisionMeeting);
        }
        if (typeof window._updateSidebarMeetings === 'function') window._updateSidebarMeetings();
    }

    function applyProjects(projects) {
        if (!Array.isArray(projects)) return;
        if (typeof window.dashboardApplyProjectSummaries === 'function') {
            window.dashboardApplyProjectSummaries(projects);
        }
    }

    function actionText(action) {
        var title = action.title || 'Action required';
        var text = action.text ? ': ' + action.text : '';
        var agent = action.agentId ? ' [' + action.agentId + ']' : '';
        return '⚠️ ' + title + agent + text;
    }

    function applyActions(actions) {
        if (!Array.isArray(actions) || typeof window.addGlobalLog !== 'function') return;
        actions.forEach(function (action) {
            if (!action || !action.id || seenActions[action.id]) return;
            seenActions[action.id] = Date.now();
            window.addGlobalLog(actionText(action));
        });
        var cutoff = Date.now() - 24 * 60 * 60 * 1000;
        Object.keys(seenActions).forEach(function (id) {
            if (seenActions[id] < cutoff) delete seenActions[id];
        });
    }

    function actionsFromFallback(active, pending) {
        var actions = [];
        (pending || []).forEach(function (req) {
            if (!req || req.status !== 'pending') return;
            actions.push({
                id: 'meeting-request:' + req.id,
                type: 'meeting_request_pending',
                title: 'Meeting request needs confirmation',
                text: req.goal || req.title || req.expectedOutcome || 'AI meeting request'
            });
        });
        (active || []).forEach(function (meeting) {
            if (!meeting) return;
            (meeting.conflicts || []).forEach(function (conflict) {
                if (!conflict || ['resolved', 'cancelled', 'closed'].indexOf(conflict.status) >= 0) return;
                actions.push({
                    id: 'meeting-conflict:' + meeting.id + ':' + (conflict.id || conflict.agentId || ''),
                    type: 'meeting_conflict',
                    title: 'Meeting participant conflict',
                    text: meeting.topic || 'Untitled meeting',
                    agentId: conflict.agentId || ''
                });
            });
            (meeting.pendingCalls || []).forEach(function (call) {
                if (!call || !call.timedOut) return;
                actions.push({
                    id: 'provider-timeout:' + meeting.id + ':' + call.sequence,
                    type: 'provider_timeout',
                    title: 'Meeting provider call timed out',
                    text: meeting.topic || 'Untitled meeting',
                    agentId: call.speaker || ''
                });
            });
            if (meeting.stage === 'awaiting_user_decision') {
                actions.push({
                    id: 'meeting-user-decision:' + meeting.id + ':' + (meeting.decisionForStage || '') + ':' + (meeting.decisionForRound || 0),
                    type: 'meeting_user_decision',
                    title: 'Meeting needs user decision',
                    text: meeting.topic || 'Untitled meeting'
                });
            }
        });
        return actions;
    }

    function parse(evt) {
        try { return JSON.parse(evt.data || '{}'); } catch (_) { return {}; }
    }

    function applySnapshot(payload) {
        if (!payload) return;
        applyStatus(payload.status);
        applyMeetings(payload.meetings);
        applyProjects(payload.projects);
        applyActions(payload.actions);
    }

    function stopFallback() {
        if (fallbackTimer) clearInterval(fallbackTimer);
        fallbackTimer = null;
    }

    async function fetchFallbackOnce() {
        try {
            var statusPromise = fetch('/status').then(function (r) { return r.json(); });
            var meetingsPromise = fetch('/api/meetings/active').then(function (r) { return r.json(); });
            var requestsPromise = fetch('/api/meetings/requests?status=pending').then(function (r) { return r.json(); });
            var projectsPromise = fetch('/api/projects?status=active').then(function (r) { return r.json(); });
            var results = await Promise.all([statusPromise, meetingsPromise, requestsPromise, projectsPromise]);
            if (typeof window.dashboardApplyStatusSnapshot === 'function') {
                window.dashboardApplyStatusSnapshot(results[0], { logRoutine: false });
            }
            applyMeetings({
                active: (results[1] || {}).meetings || [],
                pendingRequests: (results[2] || {}).requests || []
            });
            applyProjects((results[3] || {}).projects || []);
            applyActions(actionsFromFallback((results[1] || {}).meetings || [], (results[2] || {}).requests || []));
        } catch (_) {}
    }

    function startFallback() {
        if (fallbackTimer) return;
        setMode('polling', t('dashboard_realtime_polling_hint', 'SSE is unavailable. The dashboard is using polling fallback.'));
        fetchFallbackOnce();
        fallbackTimer = setInterval(fetchFallbackOnce, fallbackMs);
    }

    function scheduleFallback() {
        if (reconnectTimer) return;
        reconnectTimer = setTimeout(function () {
            reconnectTimer = null;
            if (mode !== 'sse') startFallback();
        }, 3500);
    }

    function connect() {
        if (!window.EventSource) {
            startFallback();
            return;
        }
        setMode('starting');
        try {
            source = new EventSource('/api/dashboard/events');
        } catch (_) {
            startFallback();
            return;
        }
        source.onopen = function () {
            stopFallback();
            setMode('sse');
        };
        source.onerror = function () {
            if (mode !== 'polling') setMode('reconnecting');
            scheduleFallback();
        };
        source.addEventListener('dashboard.snapshot', function (evt) {
            stopFallback();
            setMode('sse');
            applySnapshot(parse(evt));
        });
        source.addEventListener('dashboard.status', function (evt) {
            stopFallback();
            setMode('sse');
            applyStatus(parse(evt).status);
        });
        source.addEventListener('dashboard.meetings', function (evt) {
            stopFallback();
            setMode('sse');
            applyMeetings(parse(evt).meetings);
        });
        source.addEventListener('dashboard.projects', function (evt) {
            stopFallback();
            setMode('sse');
            applyProjects(parse(evt).projects);
        });
        source.addEventListener('dashboard.actions', function (evt) {
            applyActions(parse(evt).actions);
        });
        source.addEventListener('dashboard.error', function () {
            setMode('reconnecting');
            scheduleFallback();
        });
    }

    window.dashboardRealtime = {
        connect: connect,
        setMode: setMode,
        fetchFallbackOnce: fetchFallbackOnce,
        _applySnapshot: applySnapshot,
        _applyActions: applyActions
    };

    window.addEventListener('i18n:ready', refreshModeLabel);
    window.addEventListener('i18n:changed', refreshModeLabel);

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', connect);
    } else {
        connect();
    }
})();
