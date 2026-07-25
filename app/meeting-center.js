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
                var active = meeting.status === 'active';
                var round = Number(meeting.currentRound || 0);
                var maxRounds = Number(meeting.maxRounds || 0);
                var meta = active
                    ? text('运行中', 'Running') + (maxRounds ? ' · Round ' + round + '/' + maxRounds : '')
                    : meetingStage(meeting);
                html += '<button class="meeting-center-item' + (current && current.id === meeting.id ? ' is-selected' : '') + '" data-tone="' + (active ? 'running' : 'history') + '" data-record-id="' + esc(meeting.id) + '" type="button">' +
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

    function renderTurn(turn, index) {
        var info = turn.actorType === 'user' || turn.type === 'user_intervention'
            ? { emoji: '👤', name: text('用户', 'User') }
            : agentInfo(turn.speaker);
        var structured = turn.structured || null;
        var position = structuredValue(structured && structured.position) || String(turn.text || '').trim();
        if (turn.pending) position = text('正在生成立场…', 'Preparing position…');
        var extras = structuredExtraFields(structured);
        var details = extras
            ? '<details class="meeting-center-turn-details"><summary>' + esc(text('展开依据与补充', 'Show rationale & details')) + '</summary><div class="meeting-center-turn-details-body">' + extras + '</div></details>'
            : '';
        return '<article class="meeting-center-turn" data-turn-index="' + index + '">' +
            '<div class="meeting-center-turn-head"><span aria-hidden="true">' + esc(info.emoji || '🤖') + '</span><span>' + esc(info.name || turn.speaker || text('未知', 'Unknown')) + '</span></div>' +
            '<div class="meeting-center-position">' + esc(position || text('暂无立场', 'No position yet')) + '</div>' +
            details +
            '</article>';
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
            '<div class="meeting-center-timeline">' + rows.map(renderTurn).join('') + '</div>';
        if (!rows.length) {
            html += '<div class="meeting-center-empty">' + esc(text('会议尚未产生发言', 'No meeting turns yet')) + '</div>';
        }
        target.innerHTML = html;
    }

    function controlCard(tone, title, description, body, open) {
        return '<details class="meeting-center-control" data-tone="' + esc(tone) + '"' + (open ? ' open' : '') + '>' +
            '<summary><span>' + esc(title) + '</span><small>' + esc(description) + '</small></summary>' +
            '<div class="meeting-center-control-body">' + body + '</div>' +
            '</details>';
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
        html += controlCard(
            'context',
            text('补充上下文', 'Add context'),
            text('向所有参会者注入新事实', 'Inject new facts for all participants'),
            '<textarea id="mtg-intervention-text-' + id + '" class="mtg-textarea" rows="2" placeholder="' + esc(text('可选：给参会者的消息', 'Optional message')) + '"></textarea>' +
            '<textarea id="mtg-intervention-context-' + id + '" class="mtg-textarea" rows="3" placeholder="' + esc(text('补充事实或约束', 'Add facts or constraints')) + '"></textarea>' +
            '<div id="mtg-intervention-error-' + id + '" class="mtg-inline-error"></div>' +
            '<button id="mtg-intervention-submit-' + id + '" class="mtg-btn mtg-btn-end" onclick="submitMeetingIntervention(' + jsArg(meeting.id) + ')">' + esc(text('发送', 'Send')) + '</button>'
        );
        html += controlCard(
            'agenda',
            text('调整议程', 'Adjust agenda'),
            text('改变下一轮讨论重点', 'Change the focus of the next round'),
            '<textarea id="mtg-agenda-text-' + id + '" class="mtg-textarea" rows="2">' + esc(meeting.agenda || meeting.topic || '') + '</textarea>' +
            '<input id="mtg-agenda-reason-' + id + '" class="skl-input" type="text" placeholder="' + esc(text('调整原因（可选）', 'Reason (optional)')) + '">' +
            '<div id="mtg-agenda-error-' + id + '" class="mtg-inline-error"></div>' +
            '<button id="mtg-agenda-submit-' + id + '" class="mtg-btn" onclick="submitMeetingAgendaChange(' + jsArg(meeting.id) + ')">' + esc(text('保存议程', 'Save agenda')) + '</button>'
        );

        if ((meeting.executionStage || '') === 'awaiting_user_decision') {
            var options = (meeting.participants || meeting.agents || []).map(function(key) {
                var info = agentInfo(key);
                return '<option value="' + esc(key) + '">' + esc((info.emoji || '🤖') + ' ' + (info.name || key)) + '</option>';
            }).join('');
            html += controlCard(
                'question',
                text('定向提问', 'Targeted question'),
                text('指定 Agent 回答问题', 'Ask a specific agent'),
                '<select id="mtg-target-participant-' + id + '" class="skl-input">' + options + '</select>' +
                '<textarea id="mtg-target-question-' + id + '" class="mtg-textarea" rows="3" placeholder="' + esc(text('输入问题', 'Enter a question')) + '"></textarea>' +
                '<div id="mtg-target-error-' + id + '" class="mtg-inline-error"></div>' +
                '<button id="mtg-target-submit-' + id + '" class="mtg-btn mtg-btn-end" onclick="submitMeetingTargetedQuestion(' + jsArg(meeting.id) + ')">' + esc(text('提问', 'Ask')) + '</button>'
            );
        } else {
            html += controlCard(
                'question',
                text('定向提问', 'Targeted question'),
                text('每轮决策窗口开放后可用', 'Available during a round decision window'),
                '<div class="meeting-center-note">' + esc(text('当前轮次尚未进入定向提问窗口。', 'The targeted-question window is not open yet.')) + '</div>'
            );
        }

        var stage = meeting.executionStage || '';
        var pauseBody = stage === 'paused'
            ? '<button id="mtg-resume-' + id + '" class="mtg-btn mtg-btn-end" onclick="resumeExecutableMeeting(' + jsArg(meeting.id) + ')">▶ ' + esc(text('恢复会议', 'Resume meeting')) + '</button>'
            : '<button id="mtg-pause-' + id + '" class="mtg-btn mtg-btn-delete" onclick="pauseExecutableMeeting(' + jsArg(meeting.id) + ')">⏸ ' + esc(text('暂停会议', 'Pause meeting')) + '</button>';
        html += controlCard(
            'danger',
            stage === 'paused' ? text('恢复会议', 'Resume meeting') : text('暂停会议', 'Pause meeting'),
            text('保留会议快照与当前进度', 'Keep the meeting snapshot and progress'),
            pauseBody
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
                '<button class="mtg-btn mtg-btn-end" type="button" onclick="openMeetingRequestDetailModal(' + jsArg(record.id) + ')">' + esc(text('打开完整审查', 'Open full review')) + '</button>';
        } else {
            html += '<div class="meeting-center-record-summary">' +
                '<strong>' + esc(record.topic || text('未命名会议', 'Untitled meeting')) + '</strong>' +
                '<span>' + esc(text('状态：', 'Status: ') + meetingStage(record)) + '</span>' +
                (record.projectTitle ? '<span>' + esc(text('项目：', 'Project: ') + record.projectTitle) + '</span>' : '') +
                '</div>' +
                '<div class="meeting-center-aside-detail">' + runtime.renderMeetingDetail(record, { includeTranscript: false }) + '</div>';
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
        target.innerHTML = '<div class="meeting-center-live-header meeting-center-record-header">' +
            '<h3 class="meeting-center-live-title">' + esc(record.topic || text('未命名会议', 'Untitled meeting')) + '</h3>' +
            '<span class="meeting-center-round">' + esc(meetingStage(record)) + '</span>' +
            '</div>' +
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
        selected[runtime.currentTab] = String(id || '');
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
