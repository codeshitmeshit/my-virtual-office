(function() {
    'use strict';

    var selected = { active: '', completed: '', requests: '' };
    var runtime = null;

    function esc(value) {
        if (typeof window._escMtg === 'function') return window._escMtg(value);
        return String(value == null ? '' : value)
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;')
            .replace(/'/g, '&#39;');
    }

    function jsArg(value) {
        if (typeof window._mtgJsArg === 'function') return window._mtgJsArg(value);
        return JSON.stringify(String(value == null ? '' : value)).replace(/</g, '\\u003c');
    }

    function jsCall(name) {
        var args = Array.prototype.slice.call(arguments, 1).map(jsArg).join(', ');
        return esc(String(name || '') + '(' + args + ')');
    }

    function isZh() {
        try {
            return ((window.i18n && window.i18n.getLanguage && window.i18n.getLanguage()) || document.documentElement.lang || 'en').indexOf('zh') === 0;
        } catch (e) {
            return false;
        }
    }

    function text(zh, en) {
        return isZh() ? zh : en;
    }

    function agentInfo(key, agentMap) {
        var map = agentMap || (runtime && runtime.agentMap) || {};
        return map[key] || { emoji: '🤖', name: key || text('未知', 'Unknown') };
    }

    function meetingStage(meeting) {
        var stage = meeting.executionStage || meeting.stage || meeting.status || '';
        return runtime && typeof runtime.meetingStageLabel === 'function' ? runtime.meetingStageLabel(stage) : stage;
    }

    function rawMeetingStage(meeting) {
        return String((meeting && (meeting.executionStage || meeting.stage || meeting.status)) || '');
    }

    function meetingIsTerminal(meeting) {
        return ['completed', 'cancelled', 'failed'].indexOf(rawMeetingStage(meeting)) >= 0;
    }

    function meetingIsRunning(meeting) {
        if (!meeting || meetingIsTerminal(meeting)) return false;
        return meeting.status === 'active';
    }

    function meetingTone(meeting) {
        if (meetingIsRunning(meeting)) return 'running';
        var stage = rawMeetingStage(meeting);
        if (stage === 'completed') return 'completed';
        if (stage === 'cancelled') return 'cancelled';
        if (stage === 'failed') return 'failed';
        return 'history';
    }

    function normalizeDetailRecord(record) {
        if (!record || !meetingIsTerminal(record)) return record;
        return Object.assign({}, record, { status: rawMeetingStage(record) });
    }

    function filteredMeetings() {
        if (runtime.currentTab === 'active') {
            return (runtime.data.active || []).map(runtime.mergeLiveMeeting);
        }
        if (runtime.currentTab === 'completed') {
            return runtime.filterMeetingHistory(runtime.data.history || []).map(runtime.mergeLiveMeeting);
        }
        return [];
    }

    function currentRecord(records) {
        var tab = runtime.currentTab;
        var id = selected[tab];
        var found = records.find(function(item) { return item && item.id === id; });
        if (!found && records.length) {
            found = records[0];
            selected[tab] = found.id;
        }
        return found || null;
    }

    function updateStatus() {
        var target = document.getElementById('meeting-center-status');
        if (!target) return;
        var running = (runtime.data.active || []).filter(function(item) {
            return item && item.status === 'active';
        }).length;
        var requests = (runtime.data.requests || []).filter(function(item) {
            return item && (item.status || 'pending') === 'pending';
        }).length;
        target.textContent = '● ' + running + ' RUNNING · ' + requests + ' REQUESTS';
    }

    function renderList(records, current) {
        var target = document.getElementById('meeting-center-list');
        if (!target) return;
        var title = text('会议与申请', 'Meetings & requests');
        var html = '<h3 class="meeting-center-pane-title">' + esc(title) + '</h3>';

        if (runtime.currentTab === 'requests') {
            records.forEach(function(request) {
                var proposal = runtime.requestProposal(request);
                var urgency = request.urgency || proposal.urgency || 3;
                html += '<button class="meeting-center-item' + (current && current.id === request.id ? ' is-selected' : '') + '" data-tone="request" data-record-id="' + esc(request.id) + '" type="button">' +
                    '<span class="meeting-center-item-title">' + esc(proposal.topic || proposal.goal || text('AI 会议申请', 'AI meeting request')) + '</span>' +
                    '<span class="meeting-center-item-meta">' + esc(text('AI 申请', 'AI request') + ' · P' + Math.max(0, 5 - Number(urgency || 3))) + '</span>' +
                    '</button>';
            });
        } else {
            records.forEach(function(meeting) {
                var active = meetingIsRunning(meeting);
                var round = Number(meeting.currentRound || 0);
                var maxRounds = Number(meeting.maxRounds || 0);
                var meta = active
                    ? text('运行中', 'Running') + (maxRounds ? ' · Round ' + round + '/' + maxRounds : '')
                    : meetingStage(meeting);
                html += '<button class="meeting-center-item' + (current && current.id === meeting.id ? ' is-selected' : '') + '" data-tone="' + esc(meetingTone(meeting)) + '" data-record-id="' + esc(meeting.id) + '" type="button">' +
                    '<span class="meeting-center-item-title">' + esc(meeting.topic || text('未命名会议', 'Untitled meeting')) + '</span>' +
                    '<span class="meeting-center-item-meta">' + esc(meta) + '</span>' +
                    '</button>';
            });
        }

        if (!records.length) {
            html += '<div class="meeting-center-empty">' + esc(text('当前没有内容', 'Nothing here yet')) + '</div>';
        }
        target.innerHTML = html;
        target.querySelectorAll('.meeting-center-item').forEach(function(button) {
            button.addEventListener('click', function() {
                selectItem(button.dataset.recordId);
            });
        });
    }

    function renderParticipants(meeting) {
        return '<div class="meeting-center-participants">' + ((meeting.participants || meeting.agents || []).map(function(key) {
            var info = agentInfo(key);
            return '<span class="meeting-center-participant">' +
                '<span class="meeting-center-avatar" aria-hidden="true">' + esc(info.emoji || '🤖') + '</span>' +
                '<span class="meeting-center-participant-name">' + esc(info.name || key) + '</span>' +
                '</span>';
        }).join('')) + '</div>';
    }

    function originalContext(meeting) {
        if (!meeting) return '';
        var candidates = [
            meeting.context,
            meeting.initialContext,
            meeting.originalContext,
            meeting.confirmedContext
        ];
        for (var i = 0; i < candidates.length; i++) {
            var value = candidates[i];
            if (Array.isArray(value)) value = value.filter(Boolean).join('\n\n');
            if (value && typeof value === 'object') value = JSON.stringify(value, null, 2);
            value = String(value || '').trim();
            if (value) return value;
        }
        return '';
    }

    function renderOriginalContext(meeting) {
        var value = originalContext(meeting);
        var isEmpty = !value;
        var isLong = value.length > 600;
        var shouldOpen = isEmpty || !isLong;
        var preview = isLong ? value.slice(0, 420).trim() + '…' : '';
        return '<details class="meeting-center-original-context"' + (shouldOpen ? ' open' : '') + '>' +
            '<summary>' + esc(text('原始上下文', 'Original context')) + '</summary>' +
            (preview ? '<div class="meeting-center-original-context-preview">' + esc(preview) + '</div>' : '') +
            '<div class="meeting-center-original-context-body' + (isEmpty ? ' is-empty' : '') + '">' +
            esc(isEmpty ? text('原始上下文为空', 'Original context is empty') : value) +
            '</div>' +
            '</details>';
    }

    function structuredValue(value, helper) {
        var valueHelper = helper || (runtime && runtime.structuredValue);
        if (typeof valueHelper === 'function') return valueHelper(value);
        if (Array.isArray(value)) return value.filter(Boolean).join('\n');
        return String(value || '').trim();
    }

    function structuredExtraFields(structured, helper) {
        var fields = [
            ['reasoning', text('推理', 'Reasoning')],
            ['disagreements', text('分歧', 'Disagreements')],
            ['questions', text('问题', 'Questions')],
            ['suggestedNextStep', text('建议下一步', 'Suggested next step')],
            ['confidence', text('置信度', 'Confidence')]
        ];
        return fields.map(function(field) {
            var value = structuredValue(structured && structured[field[0]], helper);
            if (!value) return '';
            return '<div class="meeting-center-detail-field">' +
                '<div class="meeting-center-detail-label">' + esc(field[1]) + '</div>' +
                '<div class="meeting-center-detail-value">' + esc(value) + '</div>' +
                '</div>';
        }).join('');
    }

    function turnTime(turn) {
        var value = turn && (turn.createdAt || turn.updatedAt || turn.finishedAt);
        if (!value) return '';
        var date = new Date(value);
        if (isNaN(date.getTime())) return '';
        function pad(num) { return String(num).padStart(2, '0'); }
        var datePart = isZh()
            ? date.getFullYear() + '年' + pad(date.getMonth() + 1) + '月' + pad(date.getDate()) + '日'
            : date.getFullYear() + '-' + pad(date.getMonth() + 1) + '-' + pad(date.getDate());
        return datePart + ' ' + pad(date.getHours()) + ':' + pad(date.getMinutes());
    }

    function renderTurn(turn, index) {
        var isUserTurn = turn.actorType === 'user' || turn.type === 'user_intervention' || String(turn.speaker || '').toLowerCase() === 'user';
        var info = isUserTurn
            ? { emoji: '👻', name: text('用户', 'User') }
            : agentInfo(turn.speaker);
        var isAgendaChange = turn.type === 'agenda_change';
        var isArbitration = turn.type === 'arbitration_decision';
        var isTargetedQuestion = turn.type === 'targeted_question';
        var structured = turn.structured || null;
        var position = structuredValue(structured && structured.position) || String(turn.text || '').trim();
        if (isUserTurn) {
            position = String(turn.text || '').trim();
            if (turn.context) {
                position += (position ? '\n\n' : '') + text('补充上下文', 'Additional context') + ': ' + String(turn.context || '').trim();
            }
            if (!position) position = text('用户插话', 'User intervention');
        }
        if (isAgendaChange) {
            position = text('新议程', 'New agenda') + ': ' + String(turn.text || '').trim();
            if (turn.reason) position += '\n' + text('原因', 'Reason') + ': ' + String(turn.reason || '').trim();
        }
        if (isArbitration) {
            position = text('动作', 'Action') + ': ' + String(turn.action || '').trim();
            if (turn.text) position += '\n' + text('裁决', 'Decision') + ': ' + String(turn.text || '').trim();
            if (turn.rationale) position += '\n' + text('裁决理由', 'Rationale') + ': ' + String(turn.rationale || '').trim();
        }
        if (turn.pending) position = text('正在生成立场…', 'Preparing position…');
        var extras = structuredExtraFields(structured);
        var details = extras
            ? '<details class="meeting-center-turn-details"><summary>' + esc(text('展开依据与补充', 'Show rationale & details')) + '</summary><div class="meeting-center-turn-details-body">' + extras + '</div></details>'
            : '';
        var marker = isTargetedQuestion ? text('定向提问', 'Targeted question') : isAgendaChange ? text('议程调整', 'Agenda change') : isArbitration ? text('用户裁决', 'Arbitration') : '';
        var targetInfo = isTargetedQuestion && turn.target ? agentInfo(turn.target) : null;
        var stamp = turnTime(turn);
        return '<article class="meeting-center-turn' + (turn.pending ? ' is-pending' : '') + (isUserTurn ? ' is-user' : '') + '" data-turn-index="' + index + '">' +
            '<div class="meeting-center-turn-head"><span aria-hidden="true">' + esc(info.emoji || '🤖') + '</span><span>' + esc(info.name || turn.speaker || text('未知', 'Unknown')) + '</span>' +
            (targetInfo ? '<span class="meeting-center-turn-arrow">→</span><span class="meeting-center-turn-target"><span aria-hidden="true">' + esc(targetInfo.emoji || '🤖') + '</span><span>' + esc(targetInfo.name || turn.target) + '</span></span>' : '') +
            (marker ? '<span class="meeting-center-turn-marker">' + esc(marker) + '</span>' : '') +
            (stamp ? '<time class="meeting-center-turn-time">' + esc(stamp) + '</time>' : '') +
            '</div>' +
            '<div class="meeting-center-position">' + esc(position || text('暂无立场', 'No position yet')) + '</div>' +
            details +
            '</article>';
    }

    function groupLabel(turn) {
        var stage = turn && turn.stage || '';
        var round = Number(turn && turn.round || 0);
        if (stage === 'active_opening') return text('开场轮', 'Opening round');
        if (stage === 'active_discussion') return text('讨论轮 ' + (round || 1), 'Discussion round ' + (round || 1));
        if (turn && turn.type === 'user_intervention') return text('用户插话', 'User intervention');
        if (turn && turn.type === 'agenda_change') return text('议题调整', 'Agenda changed');
        if (turn && turn.type === 'arbitration_decision') return text('用户裁决', 'Arbitration');
        return text('逐轮发言', 'Round transcript');
    }

    function renderRoundGroups(rows) {
        if (!rows.length) return '<div class="meeting-center-empty">' + esc(text('会议尚未产生发言', 'No meeting turns yet')) + '</div>';
        var groupsByKey = {};
        rows.forEach(function(row) {
            var formalStage = row.stage === 'active_opening' || row.stage === 'active_discussion';
            var key = formalStage
                ? String(row.stage || '') + ':' + String(Number(row.round || 0))
                : String(row.type || '') + ':' + String(row.stage || '') + ':' + String(Number(row.round || 0));
            if (!groupsByKey[key]) groupsByKey[key] = { sample: row, turns: [], latestSeq: 0 };
            groupsByKey[key].turns.push(row);
            groupsByKey[key].latestSeq = Math.max(groupsByKey[key].latestSeq, Number(row.sequence || 0));
        });
        var groups = Object.keys(groupsByKey).map(function(key) { return groupsByKey[key]; }).sort(function(a, b) {
            return Number(b.latestSeq || 0) - Number(a.latestSeq || 0);
        });
        return '<div class="meeting-center-timeline">' + groups.map(function(group) {
            var turns = group.turns.slice().sort(function(a, b) {
                return Number(a.sequence || 0) - Number(b.sequence || 0);
            });
            return '<section class="meeting-center-round-card">' +
                '<div class="meeting-center-round-head"><h4>' + esc(groupLabel(group.sample)) + '</h4><span>' + esc(text('按时间顺序', 'Chronological')) + '</span></div>' +
                turns.map(renderTurn).join('') +
                '</section>';
        }).join('') + '</div>';
    }

    function renderArbitrationControls(meeting) {
        if (!meeting || !meeting.arbitration || meeting.arbitration.reason !== 'no_consensus') return '';
        var id = meeting.id || '';
        var arb = meeting.arbitration || {};
        var positions = (arb.positions || []).map(function(item) {
            var info = agentInfo(item.speaker);
            return '<div class="meeting-center-arb-position"><strong>' + esc((info.emoji || '🤖') + ' ' + (info.name || item.speaker || '')) + '</strong><span>' + esc(item.position || '') + '</span></div>';
        }).join('');
        var disagreements = (arb.disagreements || []).map(function(item) { return '• ' + String(item || ''); }).join('\n');
        return '<section class="meeting-center-arbitration" data-meeting-id="' + esc(id) + '">' +
            '<div class="meeting-center-arbitration-title">' + esc(text('无共识裁决', 'No consensus arbitration')) + '</div>' +
            '<div class="meeting-center-arbitration-hint">' + esc(arb.moderatorSuggestion || text('会议存在未解决分歧。请选择裁决、继续讨论或以无共识结束。', 'Choose a decision, continue discussion, or end with no consensus.')) + '</div>' +
            (positions ? '<div class="meeting-center-arb-positions">' + positions + '</div>' : '') +
            (disagreements ? '<div class="meeting-center-arb-disagreements">' + esc(disagreements) + '</div>' : '') +
            '<div class="meeting-center-arbitration-route">' + esc(text('裁决动作请在右侧人工控制台处理。', 'Use the human controls panel for arbitration actions.')) + '</div>' +
            '</section>';
    }

    function liveRows(meeting) {
        var rows = (meeting.transcript || []).map(function(turn) {
            return Object.assign({ pending: false }, turn);
        });
        (meeting.pendingCalls || []).forEach(function(call) {
            var hydrated = typeof runtime.hydratePendingCall === 'function' ? runtime.hydratePendingCall(call) : call;
            rows.push(Object.assign({ pending: true }, hydrated));
        });
        rows.sort(function(a, b) { return Number(a.sequence || 0) - Number(b.sequence || 0); });
        return rows;
    }

    function renderLiveMain(meeting) {
        var target = document.getElementById('meeting-center-main');
        if (!target) return;
        if (!meeting) {
            target.innerHTML = '<div class="meeting-center-empty">' + esc(text('选择一场会议查看实时讨论', 'Select a meeting to view the live discussion')) + '</div>';
            return;
        }
        var rows = liveRows(meeting);
        var html = '<div class="meeting-center-live-header">' +
            '<h3 class="meeting-center-live-title">' + esc(meeting.topic || text('未命名会议', 'Untitled meeting')) + '</h3>' +
            '<span class="meeting-center-round">ROUND ' + esc(String(meeting.currentRound || 0)) + ' / ' + esc(String(meeting.maxRounds || 0)) + '</span>' +
            '</div>' +
            '<p class="meeting-center-goal">' + esc(text('目标：', 'Goal: ') + (meeting.purpose || meeting.agenda || meeting.topic || '')) + '</p>' +
            renderParticipants(meeting) +
            renderOriginalContext(meeting) +
            renderArbitrationControls(meeting) +
            renderRoundGroups(rows);
        target.innerHTML = html;
    }

    function controlCard(tone, title, description, body, open) {
        return '<details class="meeting-center-control" data-tone="' + esc(tone) + '"' + (open ? ' open' : '') + '>' +
            '<summary><span>' + esc(title) + '</span><small>' + esc(description) + '</small></summary>' +
            '<div class="meeting-center-control-body">' + body + '</div>' +
            '</details>';
    }

    function participantOptions(meeting, exclude) {
        return (meeting.participants || meeting.agents || []).map(function(key) {
            var info = agentInfo(key);
            return '<option value="' + esc(key) + '"' + (key === exclude ? ' disabled' : '') + '>' +
                esc((info.emoji || '🤖') + ' ' + (info.name || key) + (key === exclude ? ' (' + text('当前', 'current') + ')' : '')) +
                '</option>';
        }).join('');
    }

    function decisionCountdownText(meeting) {
        if (typeof window._mtgDecisionCountdownText === 'function') return window._mtgDecisionCountdownText(meeting);
        if (!meeting.decisionDeadlineAt) return text('等待人工决策。', 'Waiting for human decision.');
        return text('决策窗口截止：', 'Decision deadline: ') + new Date(meeting.decisionDeadlineAt).toLocaleString();
    }

    function renderDecisionControl(meeting) {
        if ((meeting.executionStage || '') !== 'awaiting_user_decision') return '';
        var id = esc(meeting.id);
        var isNoConsensus = meeting.arbitration && meeting.arbitration.reason === 'no_consensus';
        var willSummarize = !isNoConsensus && meeting.decisionNextStage === 'summarizing';
        var hint = isNoConsensus
            ? text('会议存在未解决分歧。请在下方做裁决、继续讨论或无共识结束。', 'The meeting found unresolved disagreement. Choose a decision, continue discussion, or end with no consensus.')
            : (willSummarize
                ? text('最后一轮已完成。可以定向提问、补充上下文，或继续让主持人总结。', 'The final round is complete. Ask a participant, add context, or continue to moderator summary.')
                : text('一轮讨论已完成。可以定向提问、补充上下文，或继续下一轮。', 'A round is complete. Ask a participant, add context, or continue.'));
        var countdown = isNoConsensus ? '' : '<div class="meeting-center-decision-countdown mtg-decision-countdown" data-meeting-id="' + id + '" data-deadline="' + esc(meeting.decisionDeadlineAt || '') + '" data-auto-continue="1">' + esc(decisionCountdownText(meeting)) + '</div>';
        return controlCard(
            'decision',
            text('轮次决策', 'Round decision'),
            isNoConsensus ? text('等待无共识裁决', 'Waiting for no-consensus arbitration') : text('提问或继续会议', 'Ask or continue the meeting'),
            countdown +
            '<div class="meeting-center-note">' + esc(hint) + '</div>' +
            (!isNoConsensus
                ? '<select id="mtg-target-participant-' + id + '" class="skl-input">' + participantOptions(meeting) + '</select>' +
                    '<textarea id="mtg-target-question-' + id + '" class="mtg-textarea" rows="3" placeholder="' + esc(text('输入问题', 'Enter a question')) + '"></textarea>' +
                    '<div id="mtg-target-error-' + id + '" class="mtg-inline-error"></div>' +
                    '<div class="meeting-center-control-actions">' +
                    '<button id="mtg-target-submit-' + id + '" class="mtg-btn mtg-btn-end" onclick="' + jsCall('submitMeetingTargetedQuestion', meeting.id) + '">' + esc(text('提问', 'Ask')) + '</button>' +
                    '<button id="mtg-continue-' + id + '" class="mtg-btn" onclick="' + jsCall('continueMeetingDecisionWindow', meeting.id) + '">▶ ' + esc(text('继续', 'Continue')) + '</button>' +
                    '</div>'
                : ''),
            true
        );
    }

    function renderArbitrationActionControl(meeting) {
        if (!meeting.arbitration || meeting.arbitration.reason !== 'no_consensus') return '';
        var id = esc(meeting.id);
        return controlCard(
            'arbitration',
            text('无共识裁决', 'No consensus arbitration'),
            text('采纳裁决、继续一轮或结束', 'Decide, continue one round, or end'),
            '<label class="mtg-label" for="mtg-arb-decision-' + id + '">' + esc(text('裁决', 'Decision')) + '</label>' +
            '<textarea id="mtg-arb-decision-' + id + '" class="mtg-textarea" rows="3" placeholder="' + esc(text('填写最终采纳的用户裁决', 'Write the user decision to finalize.')) + '"></textarea>' +
            '<label class="mtg-label" for="mtg-arb-rationale-' + id + '">' + esc(text('裁决理由', 'Rationale')) + '</label>' +
            '<input id="mtg-arb-rationale-' + id + '" class="skl-input" type="text" placeholder="' + esc(text('可选，说明裁决依据', 'Optional rationale.')) + '">' +
            '<div id="mtg-arb-error-' + id + '" class="mtg-inline-error"></div>' +
            '<div class="meeting-center-control-actions">' +
            '<button id="mtg-arb-consensus-' + id + '" class="mtg-btn mtg-btn-end" onclick="' + jsCall('submitMeetingArbitration', meeting.id, 'consensus_summary') + '">' + esc(text('达成共识并总结', 'Consensus reached, summarize')) + '</button>' +
            '<button id="mtg-arb-decide-' + id + '" class="mtg-btn mtg-btn-end" onclick="' + jsCall('submitMeetingArbitration', meeting.id, 'decide') + '">' + esc(text('采纳裁决并结束', 'Finalize decision')) + '</button>' +
            '<button id="mtg-arb-continue-' + id + '" class="mtg-btn" onclick="' + jsCall('submitMeetingArbitration', meeting.id, 'continue_discussion') + '">' + esc(text('继续一轮', 'Continue one round')) + '</button>' +
            '<button id="mtg-arb-end-' + id + '" class="mtg-btn mtg-btn-delete" onclick="' + jsCall('submitMeetingArbitration', meeting.id, 'end_no_consensus') + '">' + esc(text('无共识结束', 'End no consensus')) + '</button>' +
            '</div>',
            true
        );
    }

    function renderModeratorTakeoverControl(meeting) {
        var failure = meeting.moderatorFailure || {};
        if (failure.reason !== 'moderator_failed') return '';
        var id = esc(meeting.id);
        var currentModerator = meeting.moderator || failure.moderator || '';
        return controlCard(
            'takeover',
            text('主持人接管', 'Moderator takeover'),
            text('人工总结或更换主持人重试', 'Close manually or retry with a replacement'),
            '<div class="mtg-inline-error" style="display:block">' + esc(failure.error || '') + '</div>' +
            '<label class="mtg-label" for="mtg-takeover-summary-' + id + '">' + esc(text('人工总结', 'User summary')) + '</label>' +
            '<textarea id="mtg-takeover-summary-' + id + '" class="mtg-textarea" rows="3" placeholder="' + esc(text('填写最终总结并关闭会议', 'Write the final summary to close the meeting.')) + '"></textarea>' +
            '<label class="mtg-label" for="mtg-takeover-decision-' + id + '">' + esc(text('最终决策', 'Decision')) + '</label>' +
            '<input id="mtg-takeover-decision-' + id + '" class="skl-input" type="text" placeholder="' + esc(text('可选最终决策', 'Optional final decision.')) + '">' +
            '<div id="mtg-takeover-error-' + id + '" class="mtg-inline-error"></div>' +
            '<button id="mtg-takeover-submit-' + id + '" class="mtg-btn mtg-btn-end" onclick="' + jsCall('submitModeratorTakeover', meeting.id, 'user_takeover') + '">' + esc(text('接管并关闭', 'Take over and close')) + '</button>' +
            '<select id="mtg-replacement-moderator-' + id + '" class="skl-input">' + participantOptions(meeting, currentModerator) + '</select>' +
            '<button id="mtg-replacement-submit-' + id + '" class="mtg-btn" onclick="' + jsCall('submitModeratorTakeover', meeting.id, 'replace_moderator') + '">' + esc(text('更换主持人重试', 'Retry with moderator')) + '</button>',
            true
        );
    }

    function renderConflictControl(meeting) {
        var conflicts = Array.isArray(meeting.conflicts)
            ? meeting.conflicts.filter(function(item) { return item && ['open', 'waiting', 'reserved'].indexOf(item.status || 'open') >= 0; })
            : [];
        if ((meeting.executionStage || '') !== 'conflict' && !conflicts.length) return '';
        var id = esc(meeting.id);
        var body = '<button id="mtg-refresh-conflict-' + id + '" class="mtg-btn" onclick="' + jsCall('refreshMeetingConflicts', meeting.id) + '">' + esc(text('重新检查冲突', 'Recheck conflicts')) + '</button>';
        if (!conflicts.length) {
            body += '<div class="meeting-center-note">' + esc(text('当前没有打开的参会冲突。', 'No open participant conflicts.')) + '</div>';
        }
        conflicts.forEach(function(conflict) {
            var info = agentInfo(conflict.agentId);
            var agentId = conflict.agentId || '';
            body += '<div class="meeting-center-conflict-card">' +
                '<strong>' + esc((info.emoji || '🤖') + ' ' + (info.name || agentId || text('Agent', 'Agent'))) + '</strong>' +
                '<span>' + esc(conflict.summary || conflict.reason || '') + '</span>' +
                '<small>' + esc(text('可用性：', 'Availability: ') + (conflict.estimatedAvailability || 'unknown')) + '</small>' +
                '<div class="meeting-center-control-actions">' +
                '<button class="mtg-btn" onclick="' + jsCall('resolveMeetingConflict', meeting.id, agentId, 'wait') + '">' + esc(text('等待', 'Wait')) + '</button>' +
                '<button class="mtg-btn" onclick="' + jsCall('reserveMeetingConflict', meeting.id, agentId) + '">' + esc(text('稍后重试', 'Try later')) + '</button>' +
                '<button class="mtg-btn" onclick="' + jsCall('replaceMeetingConflict', meeting.id, agentId) + '">' + esc(text('替换', 'Replace')) + '</button>' +
                '<button class="mtg-btn mtg-btn-delete" onclick="' + jsCall('forceJoinMeetingConflict', meeting.id, agentId) + '">' + esc(text('强制加入', 'Force join')) + '</button>' +
                '</div>' +
                '</div>';
        });
        if (meeting.reservation && Object.keys(meeting.reservation).length) {
            body += '<div class="meeting-center-note">' + esc(text('预约只作为提醒；会议启动前仍会重新检查冲突。', 'Reservations are reminders only; conflicts are rechecked before start.')) + '</div>';
        }
        return controlCard('conflict', text('参会冲突', 'Participant conflicts'), text('等待、预约、替换或强制加入', 'Wait, reserve, replace, or force join'), body, true);
    }

    function renderLifecycleControl(meeting) {
        var id = esc(meeting.id);
        var stage = meeting.executionStage || '';
        var body = '<div class="meeting-center-control-actions">';
        if (stage === 'preparing') {
            body += '<button id="mtg-start-' + id + '" class="mtg-btn mtg-btn-end" onclick="' + jsCall('startExecutableMeeting', meeting.id) + '">▶ ' + esc(text('启动会议', 'Start meeting')) + '</button>';
        } else if (stage === 'conflict') {
            body += '<button id="mtg-refresh-conflict-top-' + id + '" class="mtg-btn" onclick="' + jsCall('refreshMeetingConflicts', meeting.id) + '">' + esc(text('重新检查冲突', 'Recheck conflicts')) + '</button>';
        } else if (stage === 'paused') {
            body += '<button id="mtg-resume-' + id + '" class="mtg-btn mtg-btn-end" onclick="' + jsCall('resumeExecutableMeeting', meeting.id) + '">▶ ' + esc(text('恢复会议', 'Resume meeting')) + '</button>';
        } else {
            body += '<button id="mtg-pause-' + id + '" class="mtg-btn" onclick="' + jsCall('pauseExecutableMeeting', meeting.id) + '">⏸ ' + esc(text('暂停会议', 'Pause meeting')) + '</button>' +
                '<button id="mtg-ai-end-' + id + '" class="mtg-btn mtg-btn-end" onclick="' + jsCall('endExecutableMeetingWithAI', meeting.id) + '">✅ ' + esc(text('请主持人结束', 'Ask moderator to end')) + '</button>';
        }
        body += '<button id="mtg-cancel-' + id + '" class="mtg-btn mtg-btn-delete" onclick="' + jsCall('cancelExecutableMeeting', meeting.id) + '">✕ ' + esc(text('取消会议', 'Cancel')) + '</button>' +
            '</div>';
        return controlCard('lifecycle', text('会议控制', 'Meeting controls'), text('启动、暂停、恢复、结束或取消', 'Start, pause, resume, end, or cancel'), body, true);
    }

    function renderControls(meeting) {
        var target = document.getElementById('meeting-center-controls');
        if (!target) return;
        var html = '<h3 class="meeting-center-pane-title">' + esc(text('人工控制台', 'Human controls')) + '</h3>';
        if (!meeting || meeting.status !== 'active' || !meeting.executableMeeting) {
            target.innerHTML = html + '<div class="meeting-center-empty">' + esc(text('进行中的可执行会议会显示人工控制项', 'Controls appear for an active executable meeting')) + '</div>';
            return;
        }

        var id = esc(meeting.id);
        html += renderLifecycleControl(meeting);
        html += renderDecisionControl(meeting);
        html += renderArbitrationActionControl(meeting);
        html += renderModeratorTakeoverControl(meeting);
        html += renderConflictControl(meeting);
        html += controlCard(
            'context',
            text('补充上下文', 'Add context'),
            text('向所有参会者注入新事实', 'Inject new facts for all participants'),
            '<textarea id="mtg-intervention-text-' + id + '" class="mtg-textarea" rows="2" placeholder="' + esc(text('可选：给参会者的消息', 'Optional message')) + '"></textarea>' +
            '<textarea id="mtg-intervention-context-' + id + '" class="mtg-textarea" rows="3" placeholder="' + esc(text('补充事实或约束', 'Add facts or constraints')) + '"></textarea>' +
            '<div id="mtg-intervention-error-' + id + '" class="mtg-inline-error"></div>' +
            '<button id="mtg-intervention-submit-' + id + '" class="mtg-btn mtg-btn-end" onclick="' + jsCall('submitMeetingIntervention', meeting.id) + '">' + esc(text('发送', 'Send')) + '</button>'
        );
        html += controlCard(
            'agenda',
            text('调整议程', 'Adjust agenda'),
            text('改变下一轮讨论重点', 'Change the focus of the next round'),
            '<textarea id="mtg-agenda-text-' + id + '" class="mtg-textarea" rows="2">' + esc(meeting.agenda || meeting.topic || '') + '</textarea>' +
            '<input id="mtg-agenda-reason-' + id + '" class="skl-input" type="text" placeholder="' + esc(text('调整原因（可选）', 'Reason (optional)')) + '">' +
            '<div id="mtg-agenda-error-' + id + '" class="mtg-inline-error"></div>' +
            '<button id="mtg-agenda-submit-' + id + '" class="mtg-btn" onclick="' + jsCall('submitMeetingAgendaChange', meeting.id) + '">' + esc(text('保存议程', 'Save agenda')) + '</button>'
        );
        html += '<p class="meeting-center-note">' + esc(text('会议结论与行动项需人工确认后回写项目。', 'Meeting decisions and action items require human confirmation before project write-back.')) + '</p>';
        target.innerHTML = html;
    }

    function renderRecordControls(record) {
        var target = document.getElementById('meeting-center-controls');
        if (!target) return;
        var html = '<h3 class="meeting-center-pane-title">' + esc(text('详情', 'Details')) + '</h3>';
        if (!record) {
            target.innerHTML = html;
            return;
        }
        if (runtime.currentTab === 'requests') {
            var proposal = runtime.requestProposal(record);
            html += '<div class="meeting-center-record-summary">' +
                '<strong>' + esc(proposal.topic || proposal.goal || text('AI 会议申请', 'AI meeting request')) + '</strong>' +
                '<span>' + esc(text('状态：', 'Status: ') + (record.status || 'pending')) + '</span>' +
                '</div>' +
                '<button class="mtg-btn mtg-btn-end" type="button" onclick="' + jsCall('openMeetingRequestDetailModal', record.id) + '">' + esc(text('打开完整审查', 'Open full review')) + '</button>';
        } else {
            var detailRecord = normalizeDetailRecord(record);
            html += '<div class="meeting-center-record-summary">' +
                '<strong>' + esc(record.topic || text('未命名会议', 'Untitled meeting')) + '</strong>' +
                '<span>' + esc(text('状态：', 'Status: ') + meetingStage(record)) + '</span>' +
                (record.projectTitle ? '<span>' + esc(text('项目：', 'Project: ') + record.projectTitle) + '</span>' : '') +
                '</div>' +
                '<div class="meeting-center-aside-detail">' + runtime.renderMeetingDetail(detailRecord, { includeTranscript: false }) + '</div>';
        }
        target.innerHTML = html;
    }

    function renderRecordMain(record) {
        var target = document.getElementById('meeting-center-main');
        if (!target) return;
        if (!record) {
            target.innerHTML = '<div class="meeting-center-empty">' + esc(text('选择一条记录查看详情', 'Select a record to view details')) + '</div>';
            renderRecordControls(null);
            return;
        }
        if (runtime.currentTab === 'requests') {
            var proposal = runtime.requestProposal(record);
            target.innerHTML = '<div class="meeting-center-live-header meeting-center-record-header">' +
                '<h3 class="meeting-center-live-title">' + esc(proposal.topic || proposal.goal || text('AI 会议申请', 'AI meeting request')) + '</h3>' +
                '<span class="meeting-center-round">' + esc(record.status || 'pending') + '</span>' +
                '</div>' +
                runtime.renderRequestDetail(record);
            setTimeout(function() { runtime.updateRequestModeratorOptions(record.id); }, 0);
            renderRecordControls(record);
            return;
        }
        if (record.detailLoading) {
            target.innerHTML = '<div class="meeting-center-live-header meeting-center-record-header">' +
                '<h3 class="meeting-center-live-title">' + esc(record.topic || text('未命名会议', 'Untitled meeting')) + '</h3>' +
                '<span class="meeting-center-round">' + esc(text('加载中', 'Loading')) + '</span>' +
                '</div>' +
                '<div class="meeting-center-empty">' + esc(text('正在加载会议详情…', 'Loading meeting detail...')) + '</div>';
            renderRecordControls(record);
            return;
        }
        target.innerHTML = '<div class="meeting-center-live-header meeting-center-record-header">' +
            '<h3 class="meeting-center-live-title">' + esc(record.topic || text('未命名会议', 'Untitled meeting')) + '</h3>' +
            '<span class="meeting-center-round">' + esc(meetingStage(record)) + '</span>' +
            '</div>' +
            renderOriginalContext(record) +
            runtime.renderMeetingTranscript(record);
        renderRecordControls(record);
    }

    function render() {
        if (!runtime || !runtime.data) return;
        updateStatus();
        var searchTools = document.getElementById('mtg-history-tools');
        if (searchTools) searchTools.classList.toggle('hidden', runtime.currentTab !== 'completed');
        var records = runtime.currentTab === 'requests'
            ? runtime.sortRequests(runtime.data.requests || [])
            : filteredMeetings();
        var current = currentRecord(records);
        if (runtime.currentTab === 'completed' && current && current.detailLoaded === false && current.executableMeeting && !current.detailLoading && typeof runtime.ensureMeetingDetail === 'function') {
            current.detailLoading = true;
            runtime.ensureMeetingDetail(current.id)
                .catch(function(error) {
                    current.detailError = error && error.message ? error.message : String(error || '');
                })
                .finally(function() {
                    current.detailLoading = false;
                    if (selected.completed === current.id) {
                        if (typeof runtime.requestRender === 'function') runtime.requestRender();
                        else render();
                    }
                });
        }
        renderList(records, current);
        if (runtime.currentTab === 'active') {
            renderLiveMain(current);
            renderControls(current);
        } else {
            renderRecordMain(current);
        }
    }

    function selectItem(id) {
        if (!runtime) return;
        var tab = runtime.currentTab;
        selected[runtime.currentTab] = String(id || '');
        if (tab === 'completed' && typeof runtime.ensureMeetingDetail === 'function') {
            var records = filteredMeetings();
            var record = records.find(function(item) { return item && item.id === selected[tab]; });
            if (record && record.detailLoaded === false && record.executableMeeting && !record.detailLoading) {
                record.detailLoading = true;
                render();
                runtime.ensureMeetingDetail(record.id)
                    .catch(function(error) {
                        record.detailError = error && error.message ? error.message : String(error || '');
                    })
                    .finally(function() {
                        record.detailLoading = false;
                        if (selected[tab] === record.id) {
                            if (typeof runtime.requestRender === 'function') runtime.requestRender();
                            else render();
                        }
                    });
                return;
            }
        }
        if (typeof runtime.requestRender === 'function') {
            runtime.requestRender();
            return;
        }
        render();
    }

    function renderParticipantRow(key, agentMap) {
        var info = agentInfo(key, agentMap);
        return '<div class="mtg-participant-row">' +
            '<span class="mtg-participant-emoji">' + esc(info.emoji || '🤖') + '</span>' +
            '<div class="mtg-participant-main"><div class="mtg-participant-name">' + esc(info.name || key) + '</div></div>' +
            '</div>';
    }

    function renderStructuredTurn(structured, helper) {
        structured = structured || {};
        var position = structuredValue(structured.position, helper);
        var extras = structuredExtraFields(structured, helper);
        var html = '<div class="mtg-structured-turn mtg-structured-turn-compact">';
        if (position) {
            html += '<div class="mtg-structured-field mtg-structured-position">' +
                '<div class="mtg-structured-label">' + esc(text('立场', 'Position')) + '</div>' +
                '<div class="mtg-structured-value">' + esc(position) + '</div>' +
                '</div>';
        }
        if (extras) {
            html += '<details class="meeting-center-turn-details"><summary>' + esc(text('展开依据与补充', 'Show rationale & details')) + '</summary>' +
                '<div class="meeting-center-turn-details-body">' + extras + '</div></details>';
        }
        html += '</div>';
        return html;
    }

    window.MeetingCenterUI = {
        render: function(context) {
            runtime = context;
            render();
        },
        selectItem: selectItem,
        renderParticipantRow: renderParticipantRow,
        renderStructuredTurn: renderStructuredTurn
    };
})();
