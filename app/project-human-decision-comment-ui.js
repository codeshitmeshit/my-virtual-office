(function (root, factory) {
    var api = factory(root);
    root.ProjectHumanDecisionCommentUI = api;
    if (typeof module === 'object' && module.exports) module.exports = api;
})(typeof globalThis !== 'undefined' ? globalThis : this, function (root) {
    'use strict';

    function text(value) {
        return String(value == null ? '' : value).trim();
    }

    function isDecisionComment(comment) {
        return !!comment && comment.kind === 'human_decision' && !!text(comment.decisionId);
    }

    function openDecision(decisionId) {
        if (root.humanDecisionCenter && typeof root.humanDecisionCenter.open === 'function') {
            root.humanDecisionCenter.open({ decisionId: text(decisionId) });
            return true;
        }
        return false;
    }

    function render(comment, helpers) {
        var options = helpers || {};
        var escape = typeof options.escape === 'function' ? options.escape : text;
        var t = typeof options.t === 'function' ? options.t : function (_key, fallback) { return fallback; };
        var timeAgo = typeof options.timeAgo === 'function' ? options.timeAgo : text;
        var answer = text(comment.decisionAnswer || comment.text);
        var custom = text(comment.customAnswer);
        if (custom === answer) custom = '';
        var html = '<div class="proj-comment proj-comment-human-decision" data-decision-id="' + escape(comment.decisionId) + '">';
        html += '<div class="proj-comment-header"><span class="proj-comment-author">👤 ' + escape(t('proj_human_decision_comment', 'Human decision')) + '</span>';
        html += '<span class="proj-comment-time">' + escape(timeAgo(comment.createdAt)) + '</span></div>';
        if (comment.decisionTitle) html += '<div class="proj-human-decision-title">' + escape(comment.decisionTitle) + '</div>';
        html += '<div class="proj-comment-text"><strong>' + escape(t('proj_human_decision_result', 'Decision')) + ':</strong> ' + escape(answer) + '</div>';
        if (custom) html += '<div class="proj-comment-text"><strong>' + escape(t('proj_human_decision_custom', 'Additional input')) + ':</strong> ' + escape(custom) + '</div>';
        html += '<button type="button" class="proj-human-decision-detail" data-decision-id="' + escape(comment.decisionId) + '" onclick="ProjectHumanDecisionCommentUI.openDecision(this.getAttribute(\'data-decision-id\'))">' + escape(t('proj_human_decision_view_detail', 'View decision details')) + '</button>';
        html += '</div>';
        return html;
    }

    return { isDecisionComment: isDecisionComment, render: render, openDecision: openDecision };
});
