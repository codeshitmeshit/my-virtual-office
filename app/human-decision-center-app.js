(function (root) {
    'use strict';

    var controller = null;
    var tr = root.HumanDecisionI18n && typeof root.HumanDecisionI18n.create === 'function'
        ? root.HumanDecisionI18n.create(root)
        : { t: function (_key, _params, fallback) { return fallback; } };

    function responseJson(response) {
        return response.json().then(function (payload) {
            if (!response.ok || payload.ok === false) {
                var error = new Error(payload.error || payload.code || tr.t('human_decision_request_failed', null, '决策请求失败'));
                error.status = response.status;
                error.code = payload.code || '';
                throw error;
            }
            return payload;
        });
    }

    function managementFetch(url, options) {
        if (root.i18n && typeof root.i18n.managementFetch === 'function') {
            return root.i18n.managementFetch(url, options || {});
        }
        return root.fetch(url, Object.assign({ credentials: 'same-origin' }, options || {}));
    }

    function reportError(error) {
        var message = error && error.message || tr.t('human_decision_unknown_error', null, '未知错误');
        if (typeof root.addGlobalLog === 'function') {
            root.addGlobalLog('⚠️ ' + tr.t('human_decision_submit_failed_log', { error: message }, '人工决策提交失败：{{error}}'));
        }
        if (root.VODialogs && typeof root.VODialogs.showAlert === 'function') {
            root.VODialogs.showAlert(error && error.message || tr.t('human_decision_submit_failed', null, '决策提交失败'), {
                title: tr.t('human_decision_center_title', null, '人工决策中枢'),
            });
        }
    }

    function applySnapshot(snapshot) {
        root.dashboardDecisions = snapshot || { revision: 0, decisions: [] };
        if (controller) controller.update(root.dashboardDecisions);
    }

    function post(path, body) {
        return managementFetch(path, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(body || {}),
        }).then(responseJson).then(function (payload) {
            if (payload.snapshot) applySnapshot(payload.snapshot);
            return payload;
        });
    }

    function mount() {
        if (controller || !root.HumanDecisionCenter || !root.document) return controller;
        var toggle = root.document.getElementById('human-decision-center-toggle');
        var panel = root.document.getElementById('human-decision-center-panel');
        if (!toggle || !panel) return null;
        controller = root.HumanDecisionCenter.mount(
            { toggle: toggle, panel: panel },
            root.dashboardDecisions || { revision: 0, decisions: [] },
            {
                onSubmit: function (payload) {
                    post('/api/human-decisions/' + encodeURIComponent(payload.decisionId) + '/resolve', {
                        optionId: payload.optionId,
                        customAnswer: payload.optionId ? '' : payload.answer,
                    }).catch(reportError);
                },
                onRequestChange: function (payload) {
                    if (payload.locked) {
                        reportError(new Error(tr.t('human_decision_execution_started_error', null, 'VO 已开始执行；请在对应任务中发起新的变更决策。')));
                        return;
                    }
                    post('/api/human-decisions/' + encodeURIComponent(payload.decisionId) + '/reopen', {}).catch(reportError);
                },
            }
        );
        root.humanDecisionCenter = controller;
        return controller;
    }

    root.HumanDecisionCenterApp = { mount: mount, applySnapshot: applySnapshot, post: post };
    if (root.document && root.document.readyState === 'loading') root.document.addEventListener('DOMContentLoaded', mount);
    else mount();
})(typeof globalThis !== 'undefined' ? globalThis : this);
