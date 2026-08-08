(function (root, factory) {
    var api = factory(root);
    root.MeetingHumanDecisionUI = api;
    if (typeof module === 'object' && module.exports) module.exports = api;
})(typeof globalThis !== 'undefined' ? globalThis : this, function (root) {
    'use strict';

    function text(value) {
        return String(value == null ? '' : value).trim();
    }

    function turnFromEvent(event) {
        if (!event || event.type !== 'human_decision_resolved') return null;
        var payload = event.payload || {};
        return {
            type: 'human_decision_resolved',
            sequence: Number(event.sequence || 0),
            stage: text(payload.stage || event.stage),
            round: Number(payload.round || event.round || 0),
            decisionId: text(payload.decisionId),
            title: text(payload.title),
            answer: text(payload.answer),
            customAnswer: text(payload.customAnswer),
            createdAt: text(event.createdAt),
            actorType: 'user',
            speaker: 'human-decision-center',
            ok: true,
        };
    }

    function openDecision(decisionId) {
        if (root.humanDecisionCenter && typeof root.humanDecisionCenter.open === 'function') {
            root.humanDecisionCenter.open({ decisionId: text(decisionId) });
            return true;
        }
        return false;
    }

    function render(turn, helpers) {
        var options = helpers || {};
        var escape = typeof options.escape === 'function' ? options.escape : text;
        var t = typeof options.t === 'function' ? options.t : function (_key, fallback) { return fallback; };
        var formatTime = typeof options.formatTime === 'function' ? options.formatTime : text;
        var custom = text(turn.customAnswer);
        if (custom === text(turn.answer)) custom = '';
        var html = '<div class="mtg-turn mtg-turn-human-decision" data-decision-id="' + escape(turn.decisionId) + '">';
        html += '<div class="mtg-turn-header"><span class="mtg-response-emoji">👤</span>';
        html += '<span class="mtg-response-name">' + escape(t('meeting_human_decision', 'Human decision')) + '</span>';
        html += '<span class="mtg-turn-meta">' + escape(formatTime(turn.createdAt)) + '</span></div>';
        if (turn.title) html += '<div class="mtg-human-decision-title">' + escape(turn.title) + '</div>';
        html += '<div class="mtg-turn-text"><strong>' + escape(t('meeting_human_decision_result', 'Decision')) + ':</strong> ' + escape(turn.answer) + '</div>';
        if (custom) html += '<div class="mtg-turn-text"><strong>' + escape(t('meeting_human_decision_custom', 'Additional input')) + ':</strong> ' + escape(custom) + '</div>';
        html += '<button type="button" class="mtg-human-decision-detail" data-decision-id="' + escape(turn.decisionId) + '" onclick="MeetingHumanDecisionUI.openDecision(this.getAttribute(\'data-decision-id\'))">' + escape(t('meeting_human_decision_view_detail', 'View decision details')) + '</button>';
        html += '</div>';
        return html;
    }

    function renderMeetingCenter(turn, helpers) {
        var options = helpers || {};
        var escape = typeof options.escape === 'function' ? options.escape : text;
        var t = typeof options.t === 'function' ? options.t : function (_key, fallback) { return fallback; };
        var formatTime = typeof options.formatTime === 'function' ? options.formatTime : text;
        var custom = text(turn.customAnswer);
        if (custom === text(turn.answer)) custom = '';
        var stamp = formatTime(turn.createdAt);
        var html = '<article class="meeting-center-turn is-user is-human-decision" data-decision-id="' + escape(turn.decisionId) + '">';
        html += '<div class="meeting-center-turn-head"><span aria-hidden="true">👤</span>';
        html += '<span>' + escape(t('meeting_human_decision', 'Human decision')) + '</span>';
        html += '<span class="meeting-center-turn-marker">' + escape(t('human_decision_resolved', 'Decision completed')) + '</span>';
        if (stamp) html += '<time class="meeting-center-turn-time">' + escape(stamp) + '</time>';
        html += '</div>';
        if (turn.title) html += '<div class="meeting-center-human-decision-title">' + escape(turn.title) + '</div>';
        html += '<div class="meeting-center-position"><strong>' + escape(t('meeting_human_decision_result', 'Decision')) + ':</strong> ' + escape(turn.answer) + '</div>';
        if (custom) html += '<div class="meeting-center-position meeting-center-human-decision-custom"><strong>' + escape(t('meeting_human_decision_custom', 'Additional input')) + ':</strong> ' + escape(custom) + '</div>';
        html += '<button type="button" class="meeting-center-human-decision-detail" data-decision-id="' + escape(turn.decisionId) + '" onclick="MeetingHumanDecisionUI.openDecision(this.getAttribute(\'data-decision-id\'))">' + escape(t('meeting_human_decision_view_detail', 'View decision details')) + '</button>';
        html += '</article>';
        return html;
    }

    return { turnFromEvent: turnFromEvent, render: render, renderMeetingCenter: renderMeetingCenter, openDecision: openDecision };
});
