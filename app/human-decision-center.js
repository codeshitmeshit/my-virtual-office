(function (root, factory) {
    if (typeof module === 'object' && module.exports) {
        module.exports = factory(root);
    } else {
        root.HumanDecisionCenter = factory(root);
    }
})(typeof globalThis !== 'undefined' ? globalThis : this, function (root) {
    'use strict';

    var RISK_WEIGHT = { high: 3, medium: 2, low: 1 };
    var URGENCY_WEIGHT = { critical: 3, urgent: 2, normal: 1 };

    function text(value) {
        return value == null ? '' : String(value);
    }

    function attention(item) {
        return Boolean(item && item.status === 'pending' && (item.risk === 'high' || item.nearTimeout));
    }

    function sortPendingDecisions(decisions) {
        return (Array.isArray(decisions) ? decisions : [])
            .map(function (item, index) { return { item: item, index: index }; })
            .filter(function (entry) { return entry.item && entry.item.status === 'pending'; })
            .sort(function (left, right) {
                var a = left.item;
                var b = right.item;
                var risk = (RISK_WEIGHT[b.risk] || 0) - (RISK_WEIGHT[a.risk] || 0);
                if (risk) return risk;
                var near = Number(Boolean(b.nearTimeout)) - Number(Boolean(a.nearTimeout));
                if (near) return near;
                var urgency = (URGENCY_WEIGHT[b.urgency] || 0) - (URGENCY_WEIGHT[a.urgency] || 0);
                if (urgency) return urgency;
                var deadline = text(a.deadlineAt).localeCompare(text(b.deadlineAt));
                if (deadline) return deadline;
                var created = text(a.createdAt).localeCompare(text(b.createdAt));
                return created || left.index - right.index;
            })
            .map(function (entry) { return entry.item; });
    }

    function shouldAutoOpenDecision(previous, next) {
        if (!attention(next)) return false;
        return !previous || !attention(previous);
    }

    function resolveDecisionAnswer(decision, draft) {
        var customAnswer = text(draft && draft.customAnswer).trim();
        if (customAnswer) return { answer: customAnswer, optionId: null };
        var optionId = text(draft && draft.optionId).trim().toUpperCase();
        var options = decision && Array.isArray(decision.options) ? decision.options : [];
        var selected = options.find(function (option) { return text(option && option.id).toUpperCase() === optionId; });
        if (!selected) return null;
        return { answer: text(selected.label).trim(), optionId: text(selected.id).toUpperCase() };
    }

    function createEl(doc, tag, className, textValue) {
        var element = doc.createElement(tag);
        if (className) element.className = className;
        if (textValue != null) element.textContent = text(textValue);
        return element;
    }

    function setData(element, name, value) {
        element.setAttribute('data-' + name, text(value));
    }

    function decisionMap(snapshot) {
        var map = new Map();
        (snapshot && Array.isArray(snapshot.decisions) ? snapshot.decisions : []).forEach(function (item) {
            if (item && text(item.id).trim()) map.set(text(item.id), item);
        });
        return map;
    }

    function validSnapshot(snapshot) {
        return Boolean(
            snapshot
            && Number.isSafeInteger(snapshot.revision)
            && snapshot.revision >= 0
            && Array.isArray(snapshot.decisions)
        );
    }

    function riskLabel(risk) {
        return { high: '高风险', medium: '中风险', low: '低风险' }[risk] || '风险待评估';
    }

    function sourceLabel(source) {
        var kind = source && source.type;
        var prefix = { task: '任务', meeting: '会议', chat: '聊天' }[kind] || 'VO';
        var label = text(source && source.label).trim();
        return label ? prefix + ' · ' + label : prefix;
    }

    function channelLabel(channel) {
        return { feishu: '飞书', local: 'VO 控制面板', timeout: '超时自动处理' }[channel] || '未知入口';
    }

    function formatTime(value) {
        var raw = text(value).trim();
        if (!raw) return '—';
        var date = new Date(raw);
        if (Number.isNaN(date.getTime())) return raw;
        try {
            return new Intl.DateTimeFormat('zh-CN', {
                month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', hour12: false,
            }).format(date);
        } catch (_error) {
            return raw;
        }
    }

    function appendMeta(doc, parent, label, value, className) {
        var item = createEl(doc, 'div', 'human-decision-center__meta-item' + (className ? ' ' + className : ''));
        item.appendChild(createEl(doc, 'span', 'human-decision-center__meta-label', label));
        item.appendChild(createEl(doc, 'strong', 'human-decision-center__meta-value', value));
        parent.appendChild(item);
    }

    function createController(rootObject, hosts, initialSnapshot, initialCallbacks) {
        var toggle = hosts && hosts.toggle;
        var panel = hosts && hosts.panel;
        var doc = panel && panel.ownerDocument;
        if (!toggle || !panel || !doc || typeof doc.createElement !== 'function') {
            throw new TypeError('HumanDecisionCenter.mount requires toggle and panel elements');
        }

        var callbacks = initialCallbacks || {};
        var decisionSnapshot = { revision: -1, decisions: [] };
        var snapshotRevision = -1;
        var destroyed = false;
        var centerState = {
            isOpen: false,
            activeTab: 'pending',
            selectedDecisionId: '',
            narrowView: 'list',
            expandedDetailIds: new Set(),
            drafts: new Map(),
            lastAutoOpenedRevision: -1,
            validationError: '',
        };

        toggle.className = (text(toggle.className) + ' human-decision-center-toggle').trim();
        toggle.setAttribute('aria-haspopup', 'dialog');
        toggle.setAttribute('aria-expanded', 'false');
        panel.className = (text(panel.className) + ' human-decision-center-host').trim();
        panel.setAttribute('tabindex', '-1');
        panel.hidden = true;

        function allDecisions() {
            return decisionSnapshot.decisions || [];
        }

        function currentDecision() {
            return decisionMap(decisionSnapshot).get(centerState.selectedDecisionId) || null;
        }

        function chooseDefault() {
            var pending = sortPendingDecisions(allDecisions());
            if (centerState.activeTab === 'pending' && pending.length) return pending[0].id;
            var history = allDecisions().filter(function (item) { return item && item.status !== 'pending'; });
            if (centerState.activeTab === 'history' && history.length) return history[0].id;
            return pending.length ? pending[0].id : (history[0] && history[0].id) || '';
        }

        function renderToggle() {
            var count = sortPendingDecisions(allDecisions()).length;
            var hasAttention = allDecisions().some(attention);
            toggle.setAttribute('data-count', text(count));
            toggle.setAttribute('data-attention', hasAttention ? 'true' : 'false');
            toggle.setAttribute('aria-label', '人工决策中枢，' + count + ' 项待处理');
            toggle.setAttribute('aria-expanded', centerState.isOpen ? 'true' : 'false');
            toggle.replaceChildren();
            toggle.appendChild(createEl(doc, 'span', 'human-decision-center-toggle__icon', '⚖️'));
            toggle.appendChild(createEl(doc, 'span', 'human-decision-center-toggle__label', '打开人工决策'));
            if (count) {
                var badge = createEl(doc, 'span', 'human-decision-center-toggle__badge', count > 99 ? '99+' : count);
                badge.setAttribute('aria-hidden', 'true');
                toggle.appendChild(badge);
            }
        }

        function renderList(listHost) {
            var items = centerState.activeTab === 'pending'
                ? sortPendingDecisions(allDecisions())
                : allDecisions().filter(function (item) { return item && item.status !== 'pending'; });
            if (!items.length) {
                listHost.appendChild(createEl(doc, 'div', 'human-decision-center__empty', centerState.activeTab === 'pending' ? '当前没有待决策事项' : '还没有已处理记录'));
                return;
            }
            items.forEach(function (item) {
                var button = createEl(doc, 'button', 'human-decision-center__list-item');
                button.type = 'button';
                setData(button, 'decision-id', item.id);
                setData(button, 'risk', item.risk || 'unknown');
                button.setAttribute('aria-selected', item.id === centerState.selectedDecisionId ? 'true' : 'false');
                var top = createEl(doc, 'span', 'human-decision-center__list-top');
                top.appendChild(createEl(doc, 'span', 'human-decision-center__source', sourceLabel(item.source)));
                top.appendChild(createEl(doc, 'span', 'human-decision-center__risk', riskLabel(item.risk)));
                button.appendChild(top);
                button.appendChild(createEl(doc, 'strong', 'human-decision-center__list-title', item.title || '未命名决策'));
                var statusText = item.status === 'pending'
                    ? (item.nearTimeout ? '即将超时 · ' : '') + '截止 ' + formatTime(item.deadlineAt)
                    : channelLabel(item.resolution && item.resolution.channel) + ' · ' + formatTime(item.resolution && item.resolution.resolvedAt);
                button.appendChild(createEl(doc, 'span', 'human-decision-center__list-status', statusText));
                button.addEventListener('click', function () { selectDecision(item.id); });
                listHost.appendChild(button);
            });
        }

        function renderTaskDetail(parent, item) {
            var detail = item.taskDetail || {};
            var details = createEl(doc, 'details', 'human-decision-center__task-detail');
            if (centerState.expandedDetailIds.has(item.id)) details.setAttribute('open', '');
            var summary = createEl(doc, 'summary', 'human-decision-center__task-summary', '任务详细信息');
            summary.setAttribute('aria-expanded', centerState.expandedDetailIds.has(item.id) ? 'true' : 'false');
            summary.addEventListener('click', function () {
                if (centerState.expandedDetailIds.has(item.id)) centerState.expandedDetailIds.delete(item.id);
                else centerState.expandedDetailIds.add(item.id);
            });
            details.appendChild(summary);
            var body = createEl(doc, 'div', 'human-decision-center__task-body');
            appendMeta(doc, body, '任务摘要', detail.summary || '—');
            appendMeta(doc, body, '已完成', Array.isArray(detail.completed) && detail.completed.length ? detail.completed.join('、') : '—');
            appendMeta(doc, body, '当前阻塞', detail.blocked || '—');
            appendMeta(doc, body, '相关上下文', detail.context || '—');
            appendMeta(doc, body, '决策后下一步', detail.nextStep || '—');
            details.appendChild(body);
            parent.appendChild(details);
        }

        function renderResolution(parent, item) {
            var resolution = item.resolution || {};
            var block = createEl(doc, 'section', 'human-decision-center__resolution');
            block.setAttribute('aria-live', 'polite');
            var eyebrow = resolution.channel === 'feishu' ? '飞书已处理 · 已实时同步' : '决策已处理';
            block.appendChild(createEl(doc, 'p', 'human-decision-center__eyebrow', eyebrow));
            block.appendChild(createEl(doc, 'h3', 'human-decision-center__resolution-answer', resolution.answer || '已处理'));
            var meta = createEl(doc, 'div', 'human-decision-center__resolution-meta');
            appendMeta(doc, meta, '处理入口', channelLabel(resolution.channel));
            appendMeta(doc, meta, '处理时间', formatTime(resolution.resolvedAt));
            block.appendChild(meta);
            if (resolution.nextAction) {
                var action = createEl(doc, 'div', 'human-decision-center__next-action');
                action.appendChild(createEl(doc, 'span', '', 'VO 下一步'));
                action.appendChild(createEl(doc, 'strong', '', resolution.nextAction));
                block.appendChild(action);
            }
            if (item.execution && item.execution.started) {
                block.appendChild(createEl(doc, 'p', 'human-decision-center__locked-note', 'VO 已开始执行，原决策已锁定。' + text(item.execution.impact)));
                var requestChange = createEl(doc, 'button', 'human-decision-center__secondary-button', '请求变更');
                requestChange.type = 'button';
                setData(requestChange, 'decision-request-change', item.id);
                requestChange.disabled = !(rootObject.VODialogs && typeof rootObject.VODialogs.showConfirm === 'function');
                requestChange.addEventListener('click', function () { requestLockedChange(item); });
                block.appendChild(requestChange);
            } else if (resolution.channel !== 'timeout') {
                var edit = createEl(doc, 'button', 'human-decision-center__secondary-button', '修改决策');
                edit.type = 'button';
                setData(edit, 'decision-edit', item.id);
                edit.addEventListener('click', function () {
                    if (typeof callbacks.onRequestChange === 'function') callbacks.onRequestChange({ decisionId: item.id, locked: false });
                });
                block.appendChild(edit);
            }
            parent.appendChild(block);
        }

        function renderPendingForm(parent, item) {
            var draft = centerState.drafts.get(item.id) || { optionId: '', customAnswer: '' };
            var recommendation = item.recommendation || {};
            var form = createEl(doc, 'section', 'human-decision-center__answer');
            form.appendChild(createEl(doc, 'h3', 'human-decision-center__section-title', '请选择决策方案'));
            var options = createEl(doc, 'div', 'human-decision-center__options');
            (Array.isArray(item.options) ? item.options : []).forEach(function (option) {
                var label = createEl(doc, 'label', 'human-decision-center__option');
                if (text(option.id) === text(recommendation.optionId)) label.className += ' is-recommended';
                var input = createEl(doc, 'input', 'human-decision-center__option-input');
                input.type = 'radio';
                input.value = text(option.id).toUpperCase();
                input.checked = draft.optionId === input.value;
                input.setAttribute('name', 'decision-option-' + item.id);
                setData(input, 'decision-option', input.value);
                input.addEventListener('change', function () {
                    var nextDraft = centerState.drafts.get(item.id) || { optionId: '', customAnswer: '' };
                    nextDraft.optionId = input.value;
                    centerState.drafts.set(item.id, nextDraft);
                    centerState.validationError = '';
                });
                label.appendChild(input);
                var copy = createEl(doc, 'span', 'human-decision-center__option-copy');
                var heading = createEl(doc, 'span', 'human-decision-center__option-heading');
                heading.appendChild(createEl(doc, 'strong', '', text(option.id).toUpperCase() + ' · ' + text(option.label)));
                if (text(option.id) === text(recommendation.optionId)) heading.appendChild(createEl(doc, 'em', 'human-decision-center__recommended-tag', 'VO 推荐'));
                copy.appendChild(heading);
                copy.appendChild(createEl(doc, 'span', 'human-decision-center__option-impact', option.impact || ''));
                label.appendChild(copy);
                options.appendChild(label);
            });
            form.appendChild(options);
            if (recommendation.reason) {
                var recommendationBlock = createEl(doc, 'div', 'human-decision-center__recommendation');
                recommendationBlock.appendChild(createEl(doc, 'strong', '', '为什么 VO 推荐 ' + text(recommendation.optionId) + '？'));
                recommendationBlock.appendChild(createEl(doc, 'p', '', recommendation.reason));
                form.appendChild(recommendationBlock);
            }
            var customLabel = createEl(doc, 'label', 'human-decision-center__custom');
            customLabel.appendChild(createEl(doc, 'span', '', '以上都不符合？输入你的决策（将优先采用）'));
            var custom = createEl(doc, 'textarea', 'human-decision-center__custom-input');
            custom.value = draft.customAnswer || '';
            custom.setAttribute('placeholder', '例如：先在内部团队灰度一周，再根据数据决定是否全量');
            setData(custom, 'decision-custom-answer', item.id);
            custom.addEventListener('input', function () {
                var nextDraft = centerState.drafts.get(item.id) || { optionId: '', customAnswer: '' };
                nextDraft.customAnswer = custom.value;
                centerState.drafts.set(item.id, nextDraft);
                centerState.validationError = '';
            });
            customLabel.appendChild(custom);
            form.appendChild(customLabel);
            var error = createEl(doc, 'p', 'human-decision-center__error', centerState.validationError);
            error.setAttribute('role', 'status');
            form.appendChild(error);
            var submit = createEl(doc, 'button', 'human-decision-center__submit', '提交决策');
            submit.type = 'button';
            setData(submit, 'decision-submit', item.id);
            submit.addEventListener('click', function () { submitDecision(item); });
            form.appendChild(submit);
            parent.appendChild(form);
        }

        function renderDetail(host) {
            var item = currentDecision();
            if (!item) {
                host.appendChild(createEl(doc, 'div', 'human-decision-center__empty-detail', '选择一个决策事项查看详情'));
                return;
            }
            setData(host, 'state', item.status);
            setData(host, 'risk', item.risk || 'unknown');
            var back = createEl(doc, 'button', 'human-decision-center__back', '← 返回列表');
            back.type = 'button';
            back.addEventListener('click', function () {
                centerState.narrowView = 'list';
                render();
            });
            host.appendChild(back);
            host.appendChild(createEl(doc, 'p', 'human-decision-center__eyebrow', sourceLabel(item.source)));
            host.appendChild(createEl(doc, 'h2', 'human-decision-center__title', item.title || '未命名决策'));
            var meta = createEl(doc, 'div', 'human-decision-center__meta');
            appendMeta(doc, meta, '风险等级', riskLabel(item.risk), 'is-risk-' + text(item.risk));
            appendMeta(doc, meta, '截止时间', formatTime(item.deadlineAt));
            appendMeta(doc, meta, '双端状态', item.status === 'pending' ? '飞书与本地均等待' : '飞书与本地均已处理');
            host.appendChild(meta);
            var context = createEl(doc, 'section', 'human-decision-center__context');
            context.appendChild(createEl(doc, 'h3', 'human-decision-center__section-title', '当前情景'));
            context.appendChild(createEl(doc, 'p', '', item.situation || '—'));
            context.appendChild(createEl(doc, 'h3', 'human-decision-center__section-title', '为什么需要你决策'));
            context.appendChild(createEl(doc, 'p', '', item.reason || '—'));
            var consequence = createEl(doc, 'div', 'human-decision-center__consequence');
            consequence.appendChild(createEl(doc, 'strong', '', '超时后果'));
            consequence.appendChild(createEl(doc, 'span', '', item.timeoutConsequence || '—'));
            context.appendChild(consequence);
            host.appendChild(context);
            var reminder = item.reminder || {};
            var reminderBlock = createEl(doc, 'section', 'human-decision-center__reminder');
            reminderBlock.appendChild(createEl(doc, 'span', '', '提醒 ' + (reminder.count || 0) + ' / ' + (reminder.limit || 3)));
            reminderBlock.appendChild(createEl(doc, 'strong', '', reminder.nextAt ? '下次提醒 ' + formatTime(reminder.nextAt) : '提醒周期已结束'));
            host.appendChild(reminderBlock);
            if (item.status === 'pending') renderPendingForm(host, item);
            else renderResolution(host, item);
            renderTaskDetail(host, item);
        }

        function render() {
            if (destroyed) return;
            renderToggle();
            panel.hidden = !centerState.isOpen;
            setData(panel, 'open', centerState.isOpen ? 'true' : 'false');
            setData(panel, 'narrow-view', centerState.narrowView);
            panel.replaceChildren();
            var shell = createEl(doc, 'section', 'human-decision-center');
            shell.setAttribute('role', 'dialog');
            shell.setAttribute('aria-label', '人工决策中枢');
            var header = createEl(doc, 'header', 'human-decision-center__header');
            var titleGroup = createEl(doc, 'div', 'human-decision-center__heading');
            titleGroup.appendChild(createEl(doc, 'p', 'human-decision-center__kicker', 'HUMAN IN THE LOOP'));
            titleGroup.appendChild(createEl(doc, 'h1', '', '人工决策中枢'));
            titleGroup.appendChild(createEl(doc, 'p', '', '只暂停真正需要你判断的分支，其余工作继续运行。'));
            header.appendChild(titleGroup);
            var closeButton = createEl(doc, 'button', 'human-decision-center__close', '关闭');
            closeButton.type = 'button';
            closeButton.setAttribute('aria-label', '关闭人工决策中枢');
            closeButton.addEventListener('click', close);
            header.appendChild(closeButton);
            shell.appendChild(header);
            var body = createEl(doc, 'div', 'human-decision-center__body');
            var rail = createEl(doc, 'aside', 'human-decision-center__rail');
            var tabs = createEl(doc, 'div', 'human-decision-center__tabs');
            tabs.setAttribute('role', 'tablist');
            [['pending', '待决策'], ['history', '已处理']].forEach(function (entry) {
                var count = entry[0] === 'pending'
                    ? sortPendingDecisions(allDecisions()).length
                    : allDecisions().filter(function (item) { return item.status !== 'pending'; }).length;
                var tab = createEl(doc, 'button', 'human-decision-center__tab', entry[1] + ' ' + count);
                tab.type = 'button';
                tab.setAttribute('role', 'tab');
                tab.setAttribute('aria-selected', centerState.activeTab === entry[0] ? 'true' : 'false');
                setData(tab, 'decision-tab', entry[0]);
                tab.addEventListener('click', function () {
                    centerState.activeTab = entry[0];
                    centerState.selectedDecisionId = chooseDefault();
                    centerState.narrowView = 'list';
                    render();
                });
                tabs.appendChild(tab);
            });
            rail.appendChild(tabs);
            var list = createEl(doc, 'div', 'human-decision-center__list');
            list.setAttribute('role', 'listbox');
            renderList(list);
            rail.appendChild(list);
            body.appendChild(rail);
            var detail = createEl(doc, 'main', 'human-decision-center__detail');
            detail.setAttribute('aria-live', 'polite');
            renderDetail(detail);
            body.appendChild(detail);
            shell.appendChild(body);
            panel.appendChild(shell);
        }

        function update(snapshot) {
            if (destroyed || !validSnapshot(snapshot) || snapshot.revision <= snapshotRevision) return false;
            var previousMap = decisionMap(decisionSnapshot);
            var previousSelected = centerState.selectedDecisionId;
            decisionSnapshot = snapshot;
            snapshotRevision = snapshot.revision;
            var nextMap = decisionMap(snapshot);
            centerState.drafts.forEach(function (_draft, id) {
                var item = nextMap.get(id);
                if (!item || item.status !== 'pending') centerState.drafts.delete(id);
            });
            if (previousSelected && nextMap.has(previousSelected)) centerState.selectedDecisionId = previousSelected;
            else centerState.selectedDecisionId = chooseDefault();
            var selectedItem = nextMap.get(centerState.selectedDecisionId);
            if (selectedItem && selectedItem.status !== 'pending') centerState.activeTab = 'history';
            var autoOpen = sortPendingDecisions(snapshot.decisions).find(function (item) {
                return shouldAutoOpenDecision(previousMap.get(text(item.id)), item);
            });
            if (autoOpen && centerState.lastAutoOpenedRevision !== snapshot.revision) {
                centerState.activeTab = 'pending';
                centerState.selectedDecisionId = autoOpen.id;
                centerState.narrowView = 'detail';
                centerState.isOpen = true;
                centerState.lastAutoOpenedRevision = snapshot.revision;
            }
            centerState.validationError = '';
            render();
            if (autoOpen && typeof panel.focus === 'function') panel.focus();
            return true;
        }

        function open(options) {
            if (destroyed) return;
            var decisionId = options && options.decisionId;
            if (decisionId && decisionMap(decisionSnapshot).has(decisionId)) centerState.selectedDecisionId = decisionId;
            centerState.isOpen = true;
            render();
            if (typeof panel.focus === 'function') panel.focus();
        }

        function close() {
            if (destroyed) return;
            centerState.isOpen = false;
            render();
            if (typeof toggle.focus === 'function') toggle.focus();
        }

        function selectDecision(decisionId) {
            var item = decisionMap(decisionSnapshot).get(text(decisionId));
            if (!item) return false;
            centerState.selectedDecisionId = item.id;
            centerState.activeTab = item.status === 'pending' ? 'pending' : 'history';
            centerState.narrowView = 'detail';
            centerState.validationError = '';
            render();
            return true;
        }

        function submitDecision(item) {
            var answer = resolveDecisionAnswer(item, centerState.drafts.get(item.id));
            if (!answer) {
                centerState.validationError = '请选择 A-D 中的一项，或输入你的自定义决策。';
                render();
                return;
            }
            centerState.validationError = '';
            if (typeof callbacks.onSubmit === 'function') {
                callbacks.onSubmit({ decisionId: item.id, answer: answer.answer, optionId: answer.optionId });
            }
        }

        function requestLockedChange(item) {
            var dialogs = rootObject.VODialogs;
            if (!dialogs || typeof dialogs.showConfirm !== 'function') return;
            Promise.resolve(dialogs.showConfirm(
                text(item.execution && item.execution.impact) || 'VO 已开始执行，变更可能需要撤销已完成的工作。',
                { title: '确认请求变更？', confirmText: '确认请求变更', tone: 'danger' }
            )).then(function (confirmed) {
                if (confirmed && typeof callbacks.onRequestChange === 'function') {
                    callbacks.onRequestChange({ decisionId: item.id, locked: true });
                }
            });
        }

        function onToggle() {
            if (centerState.isOpen) close();
            else open();
        }

        function destroy() {
            if (destroyed) return;
            destroyed = true;
            toggle.removeEventListener('click', onToggle);
            panel.replaceChildren();
            panel.hidden = true;
            toggle.setAttribute('aria-expanded', 'false');
        }

        toggle.addEventListener('click', onToggle);
        update(initialSnapshot || { revision: 0, decisions: [] });
        return {
            update: update,
            open: open,
            close: close,
            selectDecision: selectDecision,
            destroy: destroy,
        };
    }

    var HumanDecisionCenter = {
        mount: function (hosts, snapshot, callbacks) {
            return createController(root, hosts, snapshot, callbacks);
        },
    };

    return {
        mount: HumanDecisionCenter.mount,
        HumanDecisionCenter: HumanDecisionCenter,
        sortPendingDecisions: sortPendingDecisions,
        shouldAutoOpenDecision: shouldAutoOpenDecision,
        resolveDecisionAnswer: resolveDecisionAnswer,
    };
});
