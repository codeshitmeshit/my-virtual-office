// Meetings dashboard, executable meeting controls, and sidebar meeting widget.
// ─── MEETINGS DASHBOARD ──────────────────────────────────────────
var _mtgAgentMap = {};  // key → {name, emoji, role}
var _mtgAgents = [];
var _mtgCurrentTab = 'active';
var _mtgData = { active: [], history: [], requests: [], projects: [] };
var _mtgOpenCards = {};
var _mtgLiveEvents = {};
var _mtgLivePollTimer = null;
var _mtgHistorySearch = '';
var _mtgDecisionAutoContinuing = {};
var _mtgDetailMeetingId = '';

function openMeetingsDashboard() {
    ['meetingsModal', 'meetingDetailModal', 'meetingRequestDetailModal', 'newMeetingModal'].forEach(function(id) {
        var el = document.getElementById(id);
        if (el) el.classList.add('modal-above-projects');
    });
    document.getElementById('meetingsModal').classList.remove('hidden');
    updateMeetingLabels();
    _mtgRefresh();
    _mtgEnsureLivePolling();
}

function closeMeetingsModal() {
    document.getElementById('meetingsModal').classList.add('hidden');
    toggleNewMeetingForm(false);
    closeMeetingRequestDetailModal();
    closeMeetingDetailModal();
    _mtgStopLivePolling();
}

function switchMtgTab(tab) {
    _mtgCurrentTab = tab;
    document.querySelectorAll('.mtg-tab').forEach(function(t) {
        t.classList.toggle('active', t.dataset.tab === tab);
    });
    _mtgRender();
}

function setMeetingHistorySearch(value) {
    _mtgHistorySearch = String(value || '').trim().toLowerCase();
    _mtgRender();
}

function _mtgMeetingTime(m) {
    if (!m) return 0;
    var candidates = [m.endedAt, m.updatedAt, m.createdAt, m.startedAt];
    for (var i = 0; i < candidates.length; i++) {
        var value = candidates[i];
        if (!value) continue;
        if (typeof value === 'number') return value > 1000000000000 ? value : value * 1000;
        var parsed = Date.parse(value);
        if (!isNaN(parsed)) return parsed;
    }
    return 0;
}

function _mtgSortMeetingsByTime(meetings) {
    return (meetings || []).slice().sort(function(a, b) {
        return _mtgMeetingTime(b) - _mtgMeetingTime(a);
    });
}

function _mtgMeetingCompleted(m) {
    if (!m) return false;
    var state = m.stage || m.executionStage || m.status || '';
    return state === 'completed' || state === 'cancelled';
}

function _mtgHistorySearchText(m) {
    var parts = [
        m && m.topic,
        m && m.purpose,
        m && m.summary,
        m && m.resolution,
        m && m.organizer,
        m && m.moderator,
        m && m.contextMode
    ];
    ((m && (m.participants || m.agents)) || []).forEach(function(p) { parts.push(p); });
    ((m && m.actionItems) || []).forEach(function(item) { parts.push(_mtgActionText(item)); });
    var responses = (m && m.responses) || {};
    Object.keys(responses).forEach(function(key) { parts.push(key, responses[key]); });
    if (m && m.result) {
        parts.push(m.result.summary, m.result.decision);
        (m.result.unresolvedQuestions || []).forEach(function(item) { parts.push(item); });
        (m.result.disagreements || []).forEach(function(item) { parts.push(item); });
        Object.keys(m.result.contributions || {}).forEach(function(key) { parts.push(key, m.result.contributions[key]); });
    }
    ((m && m.transcript) || []).forEach(function(turn) {
        parts.push(turn.speaker, turn.text, turn.rawText);
    });
    return parts.filter(Boolean).join(' ').toLowerCase();
}

function _mtgFilterMeetingHistory(meetings) {
    var sorted = _mtgSortMeetingsByTime(meetings);
    if (!_mtgHistorySearch) return sorted;
    return sorted.filter(function(m) {
        return _mtgHistorySearchText(m).indexOf(_mtgHistorySearch) >= 0;
    });
}

function _mtgHistorySnippet(m) {
    var text = m.summary || m.resolution || (m.result && (m.result.summary || m.result.decision)) || m.purpose || '';
    return String(text || '').trim().slice(0, 180);
}

function _mtgRequestProcessed(req) {
    var status = req && req.status;
    if (status === 'confirmed' || status === 'rejected') return true;
    var review = (req && req.review) || {};
    var conversion = (req && req.conversion) || {};
    return !!(review.confirmedAt || review.rejectedAt || conversion.meetingId);
}

function _mtgRequestTime(req) {
    var raw = (req && (req.updatedAt || req.createdAt)) || '';
    var ms = Date.parse(raw);
    return Number.isFinite(ms) ? ms : 0;
}

function _mtgSortRequestsByStatusThenTime(requests) {
    return (requests || []).slice().sort(function(a, b) {
        var statusDelta = Number(_mtgRequestProcessed(a)) - Number(_mtgRequestProcessed(b));
        if (statusDelta) return statusDelta;
        return _mtgRequestTime(b) - _mtgRequestTime(a);
    });
}

async function _mtgRefresh() {
    try {
        var [activeRes, histRes, requestsRes, agentsRes, projectsRes] = await Promise.all([
            fetch('/api/meetings/active').then(function(r) { return r.json(); }),
            fetch('/api/meetings/history').then(function(r) { return r.json(); }),
            fetch('/api/meetings/requests').then(function(r) { return r.json(); }),
            fetch('/agents-list').then(function(r) { return r.json(); }),
            fetch('/api/projects').then(function(r) { return r.json(); }).catch(function() { return { projects: [] }; })
        ]);
        _mtgData.active = activeRes.meetings || [];
        _mtgData.history = _mtgSortMeetingsByTime(histRes.history || []);
        _mtgData.requests = _mtgSortRequestsByStatusThenTime(requestsRes.requests || []);
        _mtgData.projects = projectsRes.projects || [];
        _mtgSeedLiveMeetings(_mtgData.active);
        (_mtgData.active || []).forEach(_mtgMaybeAutoContinueDecisionMeeting);
        _mtgAgentMap = {};
        var agentsList = agentsRes.agents || agentsRes || [];
        _mtgAgents = Array.isArray(agentsList) ? agentsList : [];
        if (Array.isArray(agentsList)) {
            agentsList.forEach(function(a) {
                _mtgAgentMap[a.key || a.agentId || a.id] = {
                    name: a.name || a.key || 'Unknown',
                    emoji: a.emoji || '🤖',
                    role: a.role || ''
                };
            });
        }
        _mtgRender();
        _updateSidebarMeetings();
    } catch (e) {
        console.warn('[meetings] refresh error:', e);
    }
}

async function openMeetingReference(ref) {
    ref = ref || {};
    var requestId = String(ref.requestId || '').trim();
    var meetingId = String(ref.meetingId || '').trim();
    updateMeetingLabels();
    _mtgEnsureLivePolling();
    ['meetingsModal', 'meetingDetailModal', 'meetingRequestDetailModal'].forEach(function(id) {
        var el = document.getElementById(id);
        if (el) el.classList.add('modal-above-projects');
    });
    await _mtgRefresh();

    var request = requestId ? _mtgFindRequest(requestId) : null;
    if (requestId && !request) request = await _mtgFetchRequestDetail(requestId);
    if (request && !meetingId) meetingId = _mtgMeetingIdFromRequest(request);

    var meeting = meetingId ? _mtgFindMeeting(meetingId) : null;
    if (!meeting && requestId) {
        meeting = _mtgFindMeetingByRequestId(requestId);
        if (meeting && meeting.id) meetingId = meeting.id;
    }
    if (meeting) {
        switchMtgTab(meeting && meeting.status === 'active' ? 'active' : 'completed');
        openMeetingDetailModal(meetingId);
        return;
    }

    if (meetingId) {
        switchMtgTab('completed');
        openMeetingDetailModal(meetingId);
        return;
    }

    if (requestId) {
        var modal = document.getElementById('meetingsModal');
        if (modal) modal.classList.remove('hidden');
        switchMtgTab('requests');
        if (!request) request = await _mtgFetchRequestDetail(requestId);
        if (request) {
            openMeetingRequestDetailModal(requestId);
        } else if (meetingId) {
            switchMtgTab('completed');
        }
    }
}

function _mtgProjectName(projectId) {
    if (!projectId) return '';
    var p = (_mtgData.projects || []).find(function(item) { return item.id === projectId; });
    return (p && p.title) || projectId;
}

function _mtgProjectMetaLabel(m) {
    var name = '';
    if (m && m.projectId) name = m.projectTitle || _mtgProjectName(m.projectId);
    if (!name && m && m.source && m.source.projectId) name = m.source.projectTitle || _mtgProjectName(m.source.projectId);
    if (!name) name = _mtgT('meeting_project_none', 'No project');
    return '📁 ' + _escMtg(_mtgT('meeting_project', 'Project')) + ': ' + _escMtg(name);
}

function _mtgProjectSelectHtml(id, selectedProjectId, allowEmpty) {
    var projects = _mtgData.projects || [];
    var html = '<select id="' + _escMtg(id) + '" class="skl-input">';
    if (allowEmpty !== false) html += '<option value="">' + _escMtg(_mtgT('meeting_project_none', 'No project')) + '</option>';
    projects.forEach(function(p) {
        html += '<option value="' + _escMtg(p.id) + '"' + (p.id === selectedProjectId ? ' selected' : '') + '>' + _escMtg(p.title || p.id) + '</option>';
    });
    html += '</select>';
    return html;
}

function _mtgRender() {
    var container = document.getElementById('mtg-cards');
    var searchTools = document.getElementById('mtg-history-tools');
    if (searchTools) searchTools.classList.toggle('hidden', _mtgCurrentTab !== 'completed');
    if (_mtgCurrentTab === 'requests') {
        _mtgRenderRequests(container);
        return;
    }
    var meetings = [];
    if (_mtgCurrentTab === 'active') meetings = _mtgData.active;
    else if (_mtgCurrentTab === 'completed') meetings = _mtgFilterMeetingHistory(_mtgData.history);
    else meetings = _mtgData.active.concat(_mtgData.history);
    meetings = meetings.map(_mtgMergeLiveMeeting);

    if (!meetings.length) {
        container.innerHTML = '<div class="mtg-empty">' + _escMtg(_tr('meeting_empty', { status: _tr(_mtgCurrentTab === 'completed' ? 'completed' : 'active') })) + '</div>';
        return;
    }

    container.innerHTML = meetings.map(function(m) {
        var isActive = m.status === 'active';
        var participants = m.participants || m.agents || [];

        var isHistory = !isActive;

        // Header (clickable to open detail modal)
        var html = '<div class="mtg-card">';
        html += '<div class="mtg-card-header" onclick="openMeetingDetailModal(\'' + _escMtg(m.id) + '\')">';
        html += '<div><div class="mtg-card-title">' + _escMtg(m.topic || _tr('untitled_meeting')) + '</div>';
        if (m.purpose && m.purpose !== m.topic) {
            html += '<div class="mtg-card-purpose">' + _escMtg(m.purpose) + '</div>';
        }
        html += '</div>';
        html += '<div class="mtg-card-badges">';
        if (isActive && m.executableMeeting && (m.executionStage || '') === 'awaiting_user_decision') {
            var isNoConsensus = m.arbitration && m.arbitration.reason === 'no_consensus';
            if (isNoConsensus) {
                html += '<span id="mtg-decision-countdown-' + _escMtg(m.id) + '" class="mtg-badge mtg-badge-countdown" data-meeting-id="' + _escMtg(m.id) + '" data-auto-continue="0">⏳ ' + _escMtg(_mtgT('meeting_arbitration_waiting', 'Waiting for arbitration')) + '</span>';
            } else {
                html += '<span id="mtg-decision-countdown-' + _escMtg(m.id) + '" class="mtg-badge mtg-badge-countdown mtg-decision-countdown" data-meeting-id="' + _escMtg(m.id) + '" data-deadline="' + _escMtg(m.decisionDeadlineAt || '') + '" data-auto-continue="1">' + _escMtg(_mtgDecisionCountdownText(m)) + '</span>';
            }
        }
        var statusInfo = _mtgMeetingStatusInfo(m);
        html += '<span class="mtg-badge ' + _escMtg(statusInfo.className) + '">' + _escMtg(statusInfo.icon + ' ' + statusInfo.label) + '</span>';
        if (m.kind) html += '<span class="mtg-badge mtg-badge-kind">' + _escMtg(m.kind) + '</span>';
        if (m.executableMeeting) html += '<span class="mtg-badge mtg-badge-kind">' + _escMtg(_mtgT('meeting_executable', 'Executable')) + ' · ' + _escMtg(_mtgMeetingStageLabel(m.executionStage || m.status || '')) + '</span>';
        html += '</div></div>';

        if (isActive) {
            html += '<div class="mtg-card-summary">';
            var activeOrgInfo = _mtgAgentMap[m.organizer] || { emoji: '🤖', name: m.organizer || 'Unknown' };
            var activeLeftMeta = [
                '👑 ' + activeOrgInfo.emoji + ' ' + _escMtg(activeOrgInfo.name),
                '🪪 ' + _escMtg(_mtgCreatedByLabel(m)),
                '👥 ' + _escMtg(_tr('participants_count', { count: participants.length }))
            ];
            var activeRightMeta = [];
            if (m.type) activeRightMeta.push('📋 ' + _escMtg(m.type));
            if (m.executableMeeting) {
                activeRightMeta.push('⚙️ ' + _escMtg(_mtgT('meeting_stage', 'Stage')) + ': ' + _escMtg(_mtgMeetingStageLabel(m.executionStage || '')));
                activeRightMeta.push('🔁 ' + _escMtg(_mtgT('meeting_version', 'Version')) + ': ' + _escMtg(m.executionVersion || 0));
                activeRightMeta.push('🧭 ' + _escMtg(_mtgT('meeting_round', 'Round')) + ': ' + _escMtg((m.currentRound || 0) + '/' + (m.maxRounds || 0)));
                if (m.moderator) activeRightMeta.push('🎙️ ' + _escMtg(_mtgT('meeting_moderator', 'Moderator')) + ': ' + _escMtg(m.moderator));
                if (m.agenda && m.agenda !== m.topic) activeRightMeta.push('📝 ' + _escMtg(_mtgT('meeting_current_agenda', 'Current agenda')) + ': ' + _escMtg(m.agenda));
                if (m.contextMode) activeRightMeta.push('🧩 ' + _escMtg(_mtgT('meeting_context_mode', 'Context')) + ': ' + _escMtg(m.contextMode));
                if (m.currentSpeaker) activeRightMeta.push('🗣️ ' + _escMtg(_mtgT('meeting_current_speaker', 'Speaker')) + ': ' + _escMtg(m.currentSpeaker));
                if (m.resolutionPolicy) activeRightMeta.push('⚖️ ' + _escMtg(_mtgResolutionPolicyLabel(m.resolutionPolicy)));
                var activePreparingTimeoutLabel = _mtgPreparingTimeoutLabel(m);
                if (activePreparingTimeoutLabel) activeRightMeta.push('⏱️ ' + _escMtg(activePreparingTimeoutLabel));
                if (m.urgency) activeRightMeta.push('🚦 ' + _escMtg(_mtgUrgencyLabel(m.urgency)));
            }
            activeRightMeta.push(_mtgProjectMetaLabel(m));
            var activeTs = _mtgMeetingTime(m);
            if (activeTs) activeRightMeta.push('🕐 ' + new Date(activeTs).toLocaleString());
            html += _mtgRenderMetaColumns(activeLeftMeta, activeRightMeta);
            var activeSnippet = _mtgHistorySnippet(m);
            if (activeSnippet) {
                html += '<div class="mtg-section-text mtg-history-snippet">' + _escMtg(activeSnippet) + '</div>';
            }
            html += '<div class="mtg-actions-bar">';
            html += '<button class="mtg-btn mtg-btn-end" onclick="event.stopPropagation(); openMeetingDetailModal(\'' + _escMtg(m.id) + '\')">' + _escMtg(_mtgT('meeting_view_detail', 'View detail')) + '</button>';
            html += '</div>';
            html += '</div></div>';
            return html;
        }

        // Body (collapsible)
        html += '<div class="mtg-card-body open" id="mtg-body-' + _escMtg(m.id) + '">';

        // Meta
        var orgInfo = _mtgAgentMap[m.organizer] || { emoji: '🤖', name: m.organizer || 'Unknown' };
        var leftMeta = [
            '👑 ' + orgInfo.emoji + ' ' + _escMtg(orgInfo.name),
            '🪪 ' + _escMtg(_mtgCreatedByLabel(m)),
            '👥 ' + _escMtg(_tr('participants_count', { count: participants.length }))
        ];
        var rightMeta = [];
        if (m.type) rightMeta.push('📋 ' + _escMtg(m.type));
        if (m.executableMeeting) {
            rightMeta.push('⚙️ ' + _escMtg(_mtgT('meeting_stage', 'Stage')) + ': ' + _escMtg(_mtgMeetingStageLabel(m.executionStage || '')));
            rightMeta.push('🔁 ' + _escMtg(_mtgT('meeting_version', 'Version')) + ': ' + _escMtg(m.executionVersion || 0));
            rightMeta.push('🧭 ' + _escMtg(_mtgT('meeting_round', 'Round')) + ': ' + _escMtg((m.currentRound || 0) + '/' + (m.maxRounds || 0)));
            if (m.moderator) rightMeta.push('🎙️ ' + _escMtg(_mtgT('meeting_moderator', 'Moderator')) + ': ' + _escMtg(m.moderator));
            if (m.agenda && m.agenda !== m.topic) rightMeta.push('📝 ' + _escMtg(_mtgT('meeting_current_agenda', 'Current agenda')) + ': ' + _escMtg(m.agenda));
            if (m.contextMode) rightMeta.push('🧩 ' + _escMtg(_mtgT('meeting_context_mode', 'Context')) + ': ' + _escMtg(m.contextMode));
            if (m.resolutionPolicy) rightMeta.push('⚖️ ' + _escMtg(_mtgT('meeting_resolution_policy', 'Resolution policy')) + ': ' + _escMtg(_mtgResolutionPolicyLabel(m.resolutionPolicy)));
            var cardPreparingTimeoutLabel = _mtgPreparingTimeoutLabel(m);
            if (cardPreparingTimeoutLabel) rightMeta.push('⏱️ ' + _escMtg(cardPreparingTimeoutLabel));
            if (m.currentSpeaker) rightMeta.push('🗣️ ' + _escMtg(_mtgT('meeting_current_speaker', 'Speaker')) + ': ' + _escMtg(m.currentSpeaker));
            if (m.urgency) rightMeta.push('🚦 ' + _escMtg(_mtgUrgencyLabel(m.urgency)));
        }
        if (m.endedAt) {
            var d = new Date(m.endedAt * 1000);
            rightMeta.push('🕐 ' + d.toLocaleString(typeof i18n !== 'undefined' && i18n.getLanguage() === 'zh' ? 'zh-CN' : 'en-US'));
        }
        rightMeta.push(_mtgProjectMetaLabel(m));
        html += _mtgRenderMetaColumns(leftMeta, rightMeta);

        if (isHistory) {
            var snippet = _mtgHistorySnippet(m);
            if (snippet) {
                html += '<div class="mtg-section-text mtg-history-snippet">' + _escMtg(snippet) + '</div>';
            }
            html += '<div class="mtg-actions-bar">';
            html += '<button class="mtg-btn mtg-btn-end" onclick="event.stopPropagation(); openMeetingDetailModal(\'' + _escMtg(m.id) + '\')">' + _escMtg(_mtgT('meeting_view_detail', 'View detail')) + '</button>';
            html += '<button class="mtg-btn mtg-btn-delete" onclick="event.stopPropagation(); deleteMeetingHistory(\'' + _escMtg(m.id) + '\')">' + _escMtg(_tr('delete')) + '</button>';
            html += '</div>';
            html += '</div>';  // close mtg-card-body
            html += '</div>';  // close mtg-card
            return html;
        }

        // Participants
        html += _mtgRenderParticipants(participants, m, {
            id: 'card-' + m.id,
            limit: 3,
            showActions: !isActive
        });

        if (isActive && m.executableMeeting) {
            if ((m.executionStage || '') === 'awaiting_user_decision') {
                html += _mtgRenderDecisionWindowControls(m);
            }
            if (m.moderatorFailure && m.moderatorFailure.reason === 'moderator_failed') {
                html += _mtgRenderModeratorTakeoverControls(m);
            }
            html += _mtgRenderInterventionForm(m);
        }

        if (m.executableMeeting && ((Array.isArray(m.transcript) && m.transcript.length) || (Array.isArray(m.pendingCalls) && m.pendingCalls.length))) {
            html += _mtgRenderTranscript(m);
        }

        // Per-agent responses
        var responses = m.responses || {};
        if (!isActive && Object.keys(responses).length > 0) {
            html += '<div class="mtg-section"><div class="mtg-section-title">' + _escMtg(_tr('agent_responses')) + '</div>';
            html += '<div class="mtg-responses">';
            participants.forEach(function(pKey) {
                var info = _mtgAgentMap[pKey] || { emoji: '🤖', name: pKey, role: '' };
                var resp = responses[pKey] || '';
                html += '<div class="mtg-response">';
                html += '<div class="mtg-response-header">';
                html += '<span class="mtg-response-emoji">' + info.emoji + '</span>';
                html += '<span class="mtg-response-name">' + _escMtg(info.name) + '</span>';
                if (info.role) html += '<span class="mtg-response-role">' + _escMtg(info.role) + '</span>';
                html += '</div>';
                if (resp) {
                    var respId = 'mtg-resp-' + _escMtg(m.id) + '-' + _escMtg(pKey);
                    html += '<div class="mtg-response-text" id="' + respId + '">' + _escMtg(resp) + '</div>';
                    html += '<span class="mtg-response-expand" onclick="toggleMtgResponse(\'' + respId + '\', this)">' + _escMtg(_tr('expand')) + '</span>';
                } else {
                    html += '<div class="mtg-response-none">' + _escMtg(_tr('no_response_recorded')) + '</div>';
                }
                html += '</div>';
            });
            html += '</div></div>';
        }

        // Completed details
        if (!isActive) {
            if (m.summary) {
                html += '<div class="mtg-section"><div class="mtg-section-title">' + _escMtg(_tr('summary')) + '</div>';
                html += '<div class="mtg-section-text">' + _escMtg(m.summary) + '</div></div>';
            }
            if (m.resolution) {
                html += '<div class="mtg-section"><div class="mtg-section-title">' + _escMtg(_tr('resolution')) + '</div>';
                html += '<div class="mtg-section-text">' + _escMtg(m.resolution) + '</div></div>';
            }
            if (m.actionItems && m.actionItems.length) {
                html += '<div class="mtg-section"><div class="mtg-section-title">' + _escMtg(_tr('action_items')) + '</div>';
                html += '<div class="mtg-section-text">' + m.actionItems.map(function(a) { return '• ' + _escMtg(_mtgActionText(a)); }).join('\n') + '</div></div>';
            }
            if (m.executableMeeting && m.result && m.result.contributions) {
                html += '<div class="mtg-section"><div class="mtg-section-title">' + _escMtg(_mtgT('meeting_contributions', 'Contributions')) + '</div>';
                Object.keys(m.result.contributions).forEach(function(agentId) {
                    var info = _mtgAgentMap[agentId] || { emoji: '🤖', name: agentId };
                    html += '<div class="mtg-response"><div class="mtg-response-header"><span class="mtg-response-emoji">' + info.emoji + '</span><span class="mtg-response-name">' + _escMtg(info.name) + '</span></div>';
                    html += '<div class="mtg-response-text">' + _mtgRenderContributionText(m.result.contributions[agentId] || '') + '</div></div>';
                });
                html += '</div>';
            }
            if (m.endedBy) {
                var endInfo = _mtgAgentMap[m.endedBy] || { emoji: '🤖', name: m.endedBy };
                html += '<div class="mtg-section"><div class="mtg-section-title">' + _escMtg(_tr('ended_by')) + '</div>';
                html += '<div class="mtg-section-text">' + endInfo.emoji + ' ' + _escMtg(endInfo.name) + '</div></div>';
            }
        }

        // Actions bar
        html += '<div class="mtg-actions-bar">';
        if (m.executableMeeting) {
            var stage = m.executionStage || '';
            if (stage === 'preparing') {
                html += '<button id="mtg-start-' + _escMtg(m.id) + '" class="mtg-btn mtg-btn-end" onclick="startExecutableMeeting(\'' + _escMtg(m.id) + '\')">▶ ' + _escMtg(_mtgT('meeting_start_existing', 'Start meeting')) + '</button>';
            } else if (stage === 'paused') {
                html += '<button id="mtg-resume-' + _escMtg(m.id) + '" class="mtg-btn mtg-btn-end" onclick="resumeExecutableMeeting(\'' + _escMtg(m.id) + '\')">▶ ' + _escMtg(_mtgT('meeting_resume', 'Resume')) + '</button>';
            } else {
                html += '<button id="mtg-pause-' + _escMtg(m.id) + '" class="mtg-btn" onclick="pauseExecutableMeeting(\'' + _escMtg(m.id) + '\')">⏸ ' + _escMtg(_mtgT('meeting_pause', 'Pause')) + '</button>';
                html += '<button id="mtg-ai-end-' + _escMtg(m.id) + '" class="mtg-btn mtg-btn-end" onclick="endExecutableMeetingWithAI(\'' + _escMtg(m.id) + '\')">✅ ' + _escMtg(_mtgT('meeting_ai_end', 'Ask moderator to end')) + '</button>';
            }
            html += '<button id="mtg-cancel-' + _escMtg(m.id) + '" class="mtg-btn mtg-btn-delete" onclick="cancelExecutableMeeting(\'' + _escMtg(m.id) + '\')">✕ ' + _escMtg(_mtgT('meeting_cancel', 'Cancel')) + '</button>';
        } else {
            html += '<button class="mtg-btn mtg-btn-end" onclick="openEndMeetingForm(\'' + _escMtg(m.id) + '\')">✅ ' + _escMtg(_tr('end_meeting')) + '</button>';
        }
        html += '</div>';

        html += '</div>';  // close mtg-card-body
        html += '</div>';  // close mtg-card
        return html;
    }).join('');
}

function _mtgParticipantDescription(info) {
    if (!info) return '';
    return String(info.role || '').trim();
}

function _mtgRenderParticipantRow(pKey, meeting, opts) {
    opts = opts || {};
    var info = _mtgAgentMap[pKey] || { emoji: '🤖', name: pKey, role: '' };
    var desc = _mtgParticipantDescription(info);
    var html = '<div class="mtg-participant-row">';
    html += '<span class="mtg-participant-emoji">' + _escMtg(info.emoji || '🤖') + '</span>';
    html += '<div class="mtg-participant-main">';
    html += '<div class="mtg-participant-name">' + _escMtg(info.name || pKey) + '</div>';
    if (desc) html += '<div class="mtg-participant-role" title="' + _escMtg(desc) + '">' + _escMtg(desc) + '</div>';
    if (opts.showActions && meeting && meeting.actionItems && meeting.actionItems.length) {
        var agentActions = meeting.actionItems.filter(function(item) {
            var text = _mtgActionText(item).toLowerCase();
            var name = String(info.name || '').toLowerCase();
            return (name && text.indexOf(name) >= 0) || text.indexOf(String(pKey || '').toLowerCase()) >= 0;
        });
        if (agentActions.length) {
            html += '<div class="mtg-participant-actions">→ ' + agentActions.map(function(item) { return _escMtg(_mtgActionText(item)); }).join('<br>→ ') + '</div>';
        }
    }
    html += '</div></div>';
    return html;
}

function _mtgRenderParticipants(participants, meeting, opts) {
    participants = participants || [];
    opts = opts || {};
    var limit = Number(opts.limit || 3);
    var id = String(opts.id || (meeting && meeting.id) || 'meeting').replace(/[^a-zA-Z0-9_-]/g, '-');
    var canCollapse = participants.length > limit;
    var visible = canCollapse ? participants.slice(0, limit) : participants;
    var hidden = canCollapse ? participants.slice(limit) : [];
    var html = '<div class="mtg-participants-block">';
    html += '<div class="mtg-participants-title">' + _escMtg(_mtgT('meeting_participants', 'Participants')) + '</div>';
    html += '<div class="mtg-participants mtg-participants-list" id="mtg-participants-' + _escMtg(id) + '">';
    visible.forEach(function(pKey) {
        html += _mtgRenderParticipantRow(pKey, meeting, opts);
    });
    if (hidden.length) {
        html += '<div class="mtg-participants-extra" id="mtg-participants-extra-' + _escMtg(id) + '">';
        hidden.forEach(function(pKey) {
            html += _mtgRenderParticipantRow(pKey, meeting, opts);
        });
        html += '</div>';
        html += '<button type="button" class="mtg-participants-toggle" data-expanded="0" data-total="' + _escMtg(String(participants.length)) + '" onclick="toggleMtgParticipants(\'' + _escMtg(id) + '\', this)">查看全部 ' + _escMtg(String(participants.length)) + '</button>';
    }
    html += '</div></div>';
    return html;
}

function _mtgRequestStatusLabel(status) {
    if (status === 'confirmed') return _mtgT('meeting_request_status_confirmed', 'Confirmed');
    if (status === 'rejected') return _mtgT('meeting_request_status_rejected', 'Rejected');
    return _mtgT('meeting_request_status_pending', 'Pending');
}

function _mtgRequestStatusClass(status) {
    if (status === 'confirmed') return 'status-confirmed';
    if (status === 'rejected') return 'status-rejected';
    return 'status-pending';
}

function _mtgMeetingStageLabel(stage) {
    var key = String(stage || '').trim();
    var map = {
        active: 'active',
        completed: 'meeting_status_completed',
        cancelled: 'meeting_status_cancelled',
        failed: 'meeting_status_failed',
        preparing: 'meeting_stage_preparing',
        conflict: 'meeting_stage_conflict',
        active_opening: 'meeting_stage_active_opening',
        active_discussion: 'meeting_stage_active_discussion',
        awaiting_user_decision: 'meeting_stage_awaiting_user_decision',
        paused: 'meeting_stage_paused',
        summarizing: 'meeting_stage_summarizing'
    };
    return map[key] ? _mtgT(map[key], key) : key;
}

function _mtgNormalizePreparingTimeoutSec(value) {
    var seconds = parseInt(value, 10);
    if (!isFinite(seconds) || seconds < 30) seconds = 300;
    if (seconds > 86400) seconds = 86400;
    return seconds;
}

function _mtgPreparingRemainingSec(m) {
    if (!m || (m.executionStage || '') !== 'preparing') return null;
    var started = Date.parse(m.preparingStartedAt || m.createdAt || '');
    if (!started) return null;
    var timeout = _mtgNormalizePreparingTimeoutSec(m.preparingTimeoutSec || 300);
    return Math.max(0, Math.ceil((started + timeout * 1000 - Date.now()) / 1000));
}

function _mtgPreparingTimeoutLabel(m) {
    if (!m || !m.executableMeeting) return '';
    if (m.cancelReason === 'preparing_timeout') {
        return _mtgT('meeting_preparing_timeout_released', 'Preparing timeout released');
    }
    var remaining = _mtgPreparingRemainingSec(m);
    if (remaining === null) return '';
    return _mtgT('meeting_preparing_timeout_remaining', 'Auto-release in {seconds}s').replace('{seconds}', String(remaining));
}

function _mtgMeetingStatusInfo(m) {
    var stage = String((m && (m.executionStage || m.status)) || '').trim();
    if ((m && m.status) === 'active' && stage !== 'cancelled' && stage !== 'failed' && stage !== 'completed') {
        return { icon: '●', label: _tr('active'), className: 'mtg-badge-active' };
    }
    if (stage === 'cancelled') {
        var cancelledLabel = (m && m.cancelReason === 'preparing_timeout')
            ? _mtgT('meeting_preparing_timeout_released', 'Preparing timeout released')
            : _mtgT('meeting_status_cancelled', 'Cancelled');
        return { icon: '✕', label: cancelledLabel, className: 'mtg-badge-kind' };
    }
    if (stage === 'failed') {
        return { icon: '!', label: _mtgT('meeting_status_failed', 'Failed'), className: 'mtg-badge-countdown' };
    }
    return { icon: '✓', label: _mtgT('meeting_status_completed', _tr('completed')), className: 'mtg-badge-completed' };
}

function _mtgRequestProposal(req) {
    return (req && req.originalProposal) || {};
}

function _mtgRequestSource(req) {
    return (req && req.source) || {};
}

function _mtgRequestAgentName(agentId) {
    var info = _mtgAgentMap[agentId] || {};
    return ((info.emoji || '🤖') + ' ' + (info.name || agentId || 'AI')).trim();
}

function _mtgUrgencyLabel(value) {
    var score = Math.max(1, Math.min(5, Number(value || 3)));
    return _mtgT('meeting_urgency', 'Urgency') + ': ' + score + '/5';
}

function _mtgCreatedByLabel(m) {
    var source = (m && m.source) || {};
    var agentId = m.createdByAgentId || source.requestingAgentId || '';
    if ((m.createdByType || '') === 'agent' || source.meetingRequestId || agentId) {
        return _mtgT('meeting_created_by_agent', 'Agent started') + ': ' + _mtgRequestAgentName(agentId || m.organizer);
    }
    return _mtgT('meeting_created_by_user', 'User started');
}

function _mtgSourceKindLabel(kind) {
    if (kind === 'project') return _mtgT('meeting_context_source_project', 'Project');
    if (kind === 'task') return _mtgT('meeting_context_source_task', 'Task');
    if (kind === 'related_task') return _mtgT('meeting_context_source_related_task', 'Related task');
    if (kind === 'meeting') return _mtgT('meeting_context_source_meeting', 'Meeting');
    if (kind === 'supplemental') return _mtgT('meeting_context_source_supplemental', 'Supplemental');
    return kind || '';
}

function _mtgDisplayText(text) {
    var raw = String(text || '');
    var normalized = raw.trim().toLowerCase();
    var map = {
        'user requested ai meeting': _mtgT('meeting_fixture_user_requested_ai_meeting', 'User requested AI meeting'),
        'invite gg to urgency 3 ai meeting': _mtgT('meeting_fixture_invite_gg_urgency_3', 'Invite gg to urgency 3 AI meeting'),
        'user requested codex to start an urgency 3 ai meeting and invite gg. this task exists as the required project-task source for the meeting request.': _mtgT('meeting_fixture_invite_gg_urgency_3_summary', 'User requested Codex to start an urgency 3 AI meeting and invite gg. This task exists as the required project-task source for the meeting request.')
    };
    return map[normalized] || raw;
}

function _mtgRenderMetaColumns(itemsLeft, itemsRight) {
    var left = (itemsLeft || []).filter(Boolean);
    var right = (itemsRight || []).filter(Boolean);
    var row1 = left.slice();
    var row2 = [];
    var row3 = [];
    var row4 = [];
    right.forEach(function(item) {
        var text = String(item || '');
        if (text.indexOf('📋') === 0) row1.push(item);
        else if (text.indexOf('🆔') === 0) row4.push(item);
        else if (text.indexOf('⚙️') === 0 || text.indexOf('🔁') === 0 || text.indexOf('🧭') === 0 || text.indexOf('🔢') === 0 || text.indexOf('🎙️') === 0 || text.indexOf('🗣️') === 0 || text.indexOf('📝') === 0) row2.push(item);
        else row3.push(item);
    });
    var rows = [row1, row2, row3, row4].filter(function(row) { return row.length; });
    return '<div class="mtg-meta mtg-meta-grid">' + rows.map(function(items) {
        return '<div class="mtg-meta-row">' + items.map(function(item) {
            return '<div class="mtg-meta-item">' + item + '</div>';
        }).join('') + '</div>';
    }).join('') + '</div>';
}

function _mtgRenderRequestContext(req) {
    var candidates = req.contextCandidates || [];
    if (!candidates.length) return '<div class="mtg-section-text">' + _escMtg(_mtgT('meeting_request_no_context', 'No context candidates.')) + '</div>';
    return '<div class="mtg-request-context-list">' + candidates.map(function(c) {
        var title = c.title || c.sourceKind || 'Context';
        var summary = c.summary || '';
        return '<label class="mtg-request-context-item">' +
            '<input type="checkbox" class="mtg-request-context" data-request-id="' + _escMtg(req.id) + '" value="' + _escMtg(c.id || '') + '">' +
            '<span><strong>' + _escMtg(_mtgDisplayText(title)) + '</strong><small>' + _escMtg(_mtgSourceKindLabel(c.sourceKind || '')) + '</small><em>' + _escMtg(_mtgDisplayText(summary)) + '</em></span>' +
            '</label>';
    }).join('') + '</div>';
}

function _mtgRenderRequestReview(req) {
    if (req.status !== 'pending') return '';
    var proposal = _mtgRequestProposal(req);
    var participants = proposal.suggestedParticipants || [];
    var participantOptions = _mtgParticipantSelectorHtml({
        selected: participants,
        participantClass: 'mtg-request-participant mtg-request-participant-' + req.id,
        branchClass: 'mtg-request-branch mtg-request-branch-' + req.id,
        participantAttrs: ' data-request-id="' + _escMtg(req.id) + '" onchange="_mtgUpdateRequestModeratorOptions(\'' + _escMtg(req.id) + '\')"',
        branchAttrs: ' data-request-id="' + _escMtg(req.id) + '" onchange="_mtgToggleRequestBranch(\'' + _escMtg(req.id) + '\', this)"'
    });
    return '<div class="mtg-request-review" id="mtg-request-review-' + _escMtg(req.id) + '">' +
        '<label class="mtg-label">' + _escMtg(_mtgT('meeting_topic', 'Topic')) + '</label>' +
        '<input id="mtg-request-topic-' + _escMtg(req.id) + '" class="skl-input" type="text" value="' + _escMtg(proposal.topic || '') + '">' +
        '<label class="mtg-label">' + _escMtg(_mtgT('meeting_purpose', 'Purpose')) + '</label>' +
        '<input id="mtg-request-purpose-' + _escMtg(req.id) + '" class="skl-input" type="text" value="' + _escMtg(proposal.purpose || proposal.goal || '') + '">' +
        '<label class="mtg-label">' + _escMtg(_mtgT('meeting_type', 'Meeting type')) + '</label>' +
        '<select id="mtg-request-type-' + _escMtg(req.id) + '" class="skl-input"><option value="information"' + (proposal.meetingType === 'information' ? ' selected' : '') + '>' + _escMtg(_mtgT('meeting_type_information', 'Information gathering')) + '</option><option value="discussion"' + (proposal.meetingType !== 'information' && proposal.meetingType !== 'task' ? ' selected' : '') + '>' + _escMtg(_mtgT('meeting_type_discussion', 'Decision discussion')) + '</option><option value="task"' + (proposal.meetingType === 'task' ? ' selected' : '') + '>' + _escMtg(_mtgT('meeting_type_task', 'Task collaboration')) + '</option></select>' +
        '<label class="mtg-label">' + _escMtg(_mtgT('meeting_project', 'Project')) + '</label>' +
        _mtgProjectSelectHtml('mtg-request-project-' + req.id, (req.source || {}).projectId || '', true) +
        '<label class="mtg-label">' + _escMtg(_mtgT('meeting_participants', 'Participants')) + '</label>' +
        '<div>' + participantOptions + '</div>' +
        '<label class="mtg-label">' + _escMtg(_mtgT('meeting_moderator', 'Moderator')) + '</label>' +
        '<select id="mtg-request-moderator-' + _escMtg(req.id) + '" class="skl-input"></select>' +
        '<label class="mtg-label">' + _escMtg(_mtgT('meeting_max_rounds', 'Max discussion rounds')) + '</label>' +
        '<input id="mtg-request-max-rounds-' + _escMtg(req.id) + '" class="skl-input" type="number" min="1" max="5" value="' + _escMtg(proposal.maxRounds || 2) + '">' +
        '<div class="mtg-section-title">' + _escMtg(_mtgT('meeting_request_context_candidates', 'Context candidates')) + '</div>' +
        _mtgRenderRequestContext(req) +
        '<label class="mtg-label">' + _escMtg(_mtgT('meeting_add_context', 'Additional context')) + '</label>' +
        '<textarea id="mtg-request-supplemental-' + _escMtg(req.id) + '" class="mtg-textarea" rows="3"></textarea>' +
        '<label class="mtg-label">' + _escMtg(_mtgT('meeting_request_reject_reason', 'Reject reason')) + '</label>' +
        '<input id="mtg-request-reject-reason-' + _escMtg(req.id) + '" class="skl-input" type="text">' +
        '<div id="mtg-request-error-' + _escMtg(req.id) + '" class="mtg-inline-error"></div>' +
        '<div class="mtg-actions-bar">' +
        '<button id="mtg-request-confirm-' + _escMtg(req.id) + '" class="mtg-btn mtg-btn-end" onclick="_mtgConfirmRequest(\'' + _escMtg(req.id) + '\')">▶ ' + _escMtg(_mtgT('meeting_request_confirm_start', 'Confirm and start')) + '</button>' +
        '<button id="mtg-request-reject-' + _escMtg(req.id) + '" class="mtg-btn mtg-btn-delete" onclick="_mtgRejectRequest(\'' + _escMtg(req.id) + '\')">✕ ' + _escMtg(_mtgT('meeting_request_reject', 'Reject')) + '</button>' +
        '</div>' +
        '</div>';
}

function _mtgRenderRequests(container) {
    if (!container) return;
    var requests = _mtgData.requests || [];
    if (!requests.length) {
        container.innerHTML = '<div class="mtg-empty">' + _escMtg(_mtgT('meeting_request_empty', 'No AI meeting requests')) + '</div>';
        return;
    }
    container.innerHTML = requests.map(function(req) {
        var proposal = _mtgRequestProposal(req);
        var source = _mtgRequestSource(req);
        var status = req.status || 'pending';
        var urgency = req.urgency || proposal.urgency || 3;
        var statusClass = _mtgRequestStatusClass(status);
        var html = '<div class="mtg-card mtg-request-card ' + statusClass + '" data-request-id="' + _escMtg(req.id) + '">';
        html += '<div class="mtg-card-header" onclick="openMeetingRequestDetailModal(\'' + _escMtg(req.id) + '\')"><div><div class="mtg-card-title">' + _escMtg(proposal.topic || proposal.goal || _mtgT('meeting_request_title', 'AI meeting request')) + '</div>';
        html += '<div class="mtg-card-purpose">' + _escMtg(source.projectTitle || '') + (source.taskTitle ? ' · ' + _escMtg(source.taskTitle) : '') + '</div></div>';
        html += '<div class="mtg-card-badges"><span class="mtg-badge mtg-request-status ' + statusClass + '">' + _escMtg(_mtgRequestStatusLabel(status)) + '</span></div></div>';
        html += '<div class="mtg-card-summary mtg-request-summary">';
        html += _mtgRenderMetaColumns([
            '🤖 ' + _escMtg(_mtgT('meeting_requesting_agent', 'Requesting agent')) + ': ' + _escMtg(_mtgRequestAgentName(req.requestingAgentId)),
            '📌 ' + _escMtg(source.taskTitle || '')
        ], [
            '🚦 ' + _escMtg(_mtgUrgencyLabel(urgency)),
            urgency >= 4 ? '⚡ ' + _escMtg(_mtgT('meeting_auto_start_high_urgency', 'High urgency auto-starts')) : ''
        ]);
        html += '<div class="mtg-section-text mtg-request-preview">' + _escMtg(proposal.goal || proposal.cannotCompleteAloneReason || '') + '</div>';
        if (status === 'confirmed' && req.conversion && req.conversion.meetingId) {
            html += '<div class="mtg-section-text">' + _escMtg(_mtgT('meeting_request_created_meeting', 'Created meeting')) + ': ' + _escMtg(req.conversion.meetingId) + '</div>';
        }
        if (req.review && req.review.autoConfirmed) {
            html += '<div class="mtg-section-text">' + _escMtg(req.review.autoConfirmLabel || req.review.autoConfirmReason || _mtgT('meeting_request_auto_confirmed', 'Auto-approved')) + '</div>';
        }
        if (status === 'rejected' && req.review && req.review.rejectionReason) {
            html += '<div class="mtg-inline-error" style="display:block">' + _escMtg(req.review.rejectionReason) + '</div>';
        }
        html += '<div class="mtg-actions-bar"><button class="mtg-btn" onclick="openMeetingRequestDetailModal(\'' + _escMtg(req.id) + '\')">' + _escMtg(_mtgT('meeting_request_view_detail', 'View details')) + '</button></div>';
        html += '</div></div>';
        return html;
    }).join('');
}

function _mtgFindRequest(requestId) {
    return (_mtgData.requests || []).find(function(req) { return req && req.id === requestId; });
}

function _mtgRenderRequestDetail(req) {
    var proposal = _mtgRequestProposal(req);
    var source = _mtgRequestSource(req);
    var status = req.status || 'pending';
    var urgency = req.urgency || proposal.urgency || 3;
    var html = '<div class="mtg-request-detail" data-request-id="' + _escMtg(req.id) + '">';
    html += _mtgRenderMetaColumns([
        '🤖 ' + _escMtg(_mtgT('meeting_requesting_agent', 'Requesting agent')) + ': ' + _escMtg(_mtgRequestAgentName(req.requestingAgentId)),
        '📋 ' + _escMtg(source.projectTitle || ''),
        '📌 ' + _escMtg(source.taskTitle || '')
    ], [
        '🚦 ' + _escMtg(_mtgUrgencyLabel(urgency)),
        '<span class="mtg-badge mtg-request-status ' + _mtgRequestStatusClass(status) + '">' + _escMtg(_mtgRequestStatusLabel(status)) + '</span>'
    ]);
    html += '<div class="mtg-section"><div class="mtg-section-title">' + _escMtg(_mtgT('meeting_request_goal', 'Goal')) + '</div><div class="mtg-section-text">' + _escMtg(proposal.goal || '') + '</div></div>';
    html += '<div class="mtg-section"><div class="mtg-section-title">' + _escMtg(_mtgT('meeting_request_expected', 'Expected outcome')) + '</div><div class="mtg-section-text">' + _escMtg(proposal.expectedOutcome || '') + '</div></div>';
    html += '<div class="mtg-section"><div class="mtg-section-title">' + _escMtg(_mtgT('meeting_request_reason', 'Why meeting is needed')) + '</div><div class="mtg-section-text">' + _escMtg(proposal.cannotCompleteAloneReason || '') + '</div></div>';
    if (status === 'confirmed' && req.conversion && req.conversion.meetingId) {
        html += '<div class="mtg-section-text">' + _escMtg(_mtgT('meeting_request_created_meeting', 'Created meeting')) + ': ' + _escMtg(req.conversion.meetingId) + '</div>';
    }
    if (req.review && req.review.autoConfirmed) {
        html += '<div class="mtg-section-text">' + _escMtg(req.review.autoConfirmLabel || req.review.autoConfirmReason || _mtgT('meeting_request_auto_confirmed', 'Auto-approved')) + '</div>';
    }
    if (status === 'rejected' && req.review && req.review.rejectionReason) {
        html += '<div class="mtg-inline-error" style="display:block">' + _escMtg(req.review.rejectionReason) + '</div>';
    }
    html += _mtgRenderRequestReview(req);
    html += '</div>';
    return html;
}

function openMeetingRequestDetailModal(requestId) {
    var req = _mtgFindRequest(requestId);
    var modal = document.getElementById('meetingRequestDetailModal');
    var body = document.getElementById('meeting-request-detail-body');
    var title = document.getElementById('meeting-request-detail-title');
    if (!req || !modal || !body) return;
    var proposal = _mtgRequestProposal(req);
    if (title) title.textContent = proposal.topic || proposal.goal || _mtgT('meeting_request_title', 'AI meeting request');
    body.innerHTML = _mtgRenderRequestDetail(req);
    modal.classList.remove('hidden');
    setTimeout(function() { _mtgUpdateRequestModeratorOptions(req.id); }, 0);
}

function closeMeetingRequestDetailModal() {
    var modal = document.getElementById('meetingRequestDetailModal');
    var body = document.getElementById('meeting-request-detail-body');
    if (modal) modal.classList.add('hidden');
    if (body) body.innerHTML = '';
}

function _mtgToggleRequestBranch(requestId, branchEl) {
    var branchId = branchEl.getAttribute('data-branch-id') || '';
    _mtgApplyBranchSelection('[data-request-id="' + requestId + '"].mtg-request-branch', '[data-request-id="' + requestId + '"].mtg-request-participant', branchId, branchEl.checked);
    _mtgUpdateRequestModeratorOptions(requestId);
}

function _mtgUpdateRequestModeratorOptions(requestId) {
    var req = (_mtgData.requests || []).find(function(item) { return item.id === requestId; }) || {};
    var proposal = _mtgRequestProposal(req);
    _mtgSyncBranchSelectionState('[data-request-id="' + requestId + '"].mtg-request-branch', '[data-request-id="' + requestId + '"].mtg-request-participant');
    _mtgUpdateModeratorOptions('mtg-request-moderator-' + requestId, '[data-request-id="' + requestId + '"].mtg-request-participant', proposal.suggestedModerator);
}

function _mtgRequestError(requestId, msg) {
    var err = document.getElementById('mtg-request-error-' + requestId);
    if (err) {
        err.textContent = msg || '';
        err.style.display = msg ? 'block' : 'none';
    }
}

async function _mtgConfirmRequest(requestId) {
    _mtgRequestError(requestId, '');
    var participants = _mtgFilterAssignableParticipants(Array.prototype.slice.call(document.querySelectorAll('[data-request-id="' + requestId + '"].mtg-request-participant:checked')).map(function(el) { return el.value; }));
    var selectedContextIds = Array.prototype.slice.call(document.querySelectorAll('[data-request-id="' + requestId + '"].mtg-request-context:checked')).map(function(el) { return el.value; });
    var body = {
        topic: ((document.getElementById('mtg-request-topic-' + requestId) || {}).value || '').trim(),
        purpose: ((document.getElementById('mtg-request-purpose-' + requestId) || {}).value || '').trim(),
        meetingType: (document.getElementById('mtg-request-type-' + requestId) || {}).value || 'discussion',
        participants: participants,
        moderator: (document.getElementById('mtg-request-moderator-' + requestId) || {}).value || '',
        projectId: (document.getElementById('mtg-request-project-' + requestId) || {}).value || '',
        maxRounds: Number((document.getElementById('mtg-request-max-rounds-' + requestId) || {}).value || 2),
        selectedContextIds: selectedContextIds,
        supplementalContext: ((document.getElementById('mtg-request-supplemental-' + requestId) || {}).value || '').trim(),
        idempotencyKey: 'ui-confirm-' + requestId
    };
    if (participants.length < 2) return _mtgRequestError(requestId, _mtgT('meeting_error_participants_required', 'Select at least two participants.'));
    try {
        var res = await fetch('/api/meetings/requests/' + encodeURIComponent(requestId) + '/confirm', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(body)
        });
        var data = await res.json();
        if (!res.ok || data.error) throw new Error(data.error || 'Failed to confirm request');
        var meetingId = data.meetingId || (data.meeting && data.meeting.id) || (data.request && data.request.conversion && data.request.conversion.meetingId) || '';
        var ran = null;
        if (meetingId) {
            ran = await _mtgRunMeeting(meetingId, { action: 'confirmed_start' });
        }
        closeMeetingRequestDetailModal();
        await _mtgRefresh();
        var latest = meetingId ? _mtgFindMeeting(meetingId) : null;
        var current = latest || (ran && ran.meeting) || data.meeting || null;
        switchMtgTab(_mtgMeetingCompleted(current) ? 'completed' : 'active');
        if (current) openMeetingDetailRecord(current);
        else if (meetingId) openMeetingDetailModal(meetingId);
    } catch (e) {
        _mtgRequestError(requestId, e.message || String(e));
    }
}

async function _mtgRejectRequest(requestId) {
    _mtgRequestError(requestId, '');
    var reason = ((document.getElementById('mtg-request-reject-reason-' + requestId) || {}).value || '').trim();
    if (!reason) return _mtgRequestError(requestId, _mtgT('meeting_request_reject_reason_required', 'Enter a rejection reason.'));
    try {
        var res = await fetch('/api/meetings/requests/' + encodeURIComponent(requestId) + '/reject', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ reason: reason })
        });
        var data = await res.json();
        if (!res.ok || data.error) throw new Error(data.error || 'Failed to reject request');
        closeMeetingRequestDetailModal();
        await _mtgRefresh();
        switchMtgTab('requests');
    } catch (e) {
        _mtgRequestError(requestId, e.message || String(e));
    }
}

function _mtgDecisionSecondsRemaining(deadlineAt) {
    if (!deadlineAt) return null;
    var deadline = new Date(deadlineAt).getTime();
    if (!Number.isFinite(deadline)) return null;
    return Math.max(0, Math.ceil((deadline - Date.now()) / 1000));
}

function _mtgResolutionPolicyLabel(policy) {
    if (policy === 'moderator_decision') return _mtgT('meeting_resolution_moderator_decision', 'Moderator decides and closes');
    return _mtgT('meeting_resolution_user_decision', 'User decides disagreements');
}

function _mtgOutcomeLabel(outcome) {
    if (outcome === 'approved') return _mtgT('meeting_outcome_approved', 'Approved');
    if (outcome === 'rejected') return _mtgT('meeting_outcome_rejected', 'Rejected');
    if (outcome === 'no_consensus') return _mtgT('meeting_outcome_no_consensus', 'No consensus');
    if (outcome === 'needs_user_decision') return _mtgT('meeting_outcome_needs_user_decision', 'Needs user decision');
    return outcome || '';
}

function _mtgRenderResultSummary(m) {
    var result = (m && m.result) || {};
    var hasStructured = !!(result.outcome || result.rationale || (result.unresolvedQuestions || []).length || (result.disagreements || []).length || (result.actionItems || []).length);
    if (!m || (!m.summary && !m.resolution && !hasStructured)) return '';
    var html = '<div class="mtg-section mtg-result-summary">';
    html += '<div class="mtg-section-title">' + _escMtg(_mtgT('meeting_result_summary', 'Meeting result')) + '</div>';
    if (result.outcome) {
        html += '<div class="mtg-result-outcome mtg-result-outcome-' + _escMtg(result.outcome) + '">' + _escMtg(_mtgOutcomeLabel(result.outcome)) + '</div>';
    }
    if (m.summary) {
        html += '<div class="mtg-result-block"><div class="mtg-result-label">' + _escMtg(_tr('summary')) + '</div><div class="mtg-section-text">' + _escMtg(m.summary) + '</div></div>';
    }
    if (m.resolution) {
        html += '<div class="mtg-result-block"><div class="mtg-result-label">' + _escMtg(_tr('resolution')) + '</div><div class="mtg-section-text">' + _escMtg(m.resolution) + '</div></div>';
    }
    if (result.rationale) {
        html += '<div class="mtg-result-block"><div class="mtg-result-label">' + _escMtg(_mtgT('meeting_rationale', 'Rationale')) + '</div><div class="mtg-section-text">' + _escMtg(result.rationale) + '</div></div>';
    }
    if (result.unresolvedQuestions && result.unresolvedQuestions.length) {
        html += '<div class="mtg-result-block"><div class="mtg-result-label">' + _escMtg(_mtgT('meeting_unresolved_questions', 'Unresolved questions')) + '</div><div class="mtg-section-text">' + result.unresolvedQuestions.map(function(item) { return '• ' + _escMtg(item); }).join('\n') + '</div></div>';
    }
    if (result.disagreements && result.disagreements.length) {
        html += '<div class="mtg-result-block"><div class="mtg-result-label">' + _escMtg(_mtgT('meeting_disagreements', 'Disagreements')) + '</div><div class="mtg-section-text">' + result.disagreements.map(function(item) { return '• ' + _escMtg(item); }).join('\n') + '</div></div>';
    }
    if (m.actionItems && m.actionItems.length) {
        html += '<div class="mtg-result-block"><div class="mtg-result-label">' + _escMtg(_tr('action_items')) + '</div><div class="mtg-section-text">' + m.actionItems.map(function(a) { return '• ' + _escMtg(_mtgActionText(a)); }).join('\n') + '</div></div>';
    }
    html += '</div>';
    return html;
}

function _mtgDecisionCountdownText(m) {
    var seconds = _mtgDecisionSecondsRemaining(m && m.decisionDeadlineAt);
    if (seconds == null) return '⏳ ' + _mtgT('meeting_decision_waiting', 'Waiting');
    if (seconds <= 0) return '⏳ 0s';
    return '⏳ ' + seconds + 's';
}

function _mtgUpdateDecisionCountdowns() {
    document.querySelectorAll('.mtg-decision-countdown').forEach(function(el) {
        var seconds = _mtgDecisionSecondsRemaining(el.dataset.deadline || '');
        if (seconds == null) {
            el.textContent = '⏳ ' + _mtgT('meeting_decision_waiting', 'Waiting');
        } else {
            el.textContent = '⏳ ' + Math.max(0, seconds) + 's';
        }
        el.classList.toggle('mtg-badge-countdown-expired', seconds === 0);
        if (seconds === 0 && el.dataset.autoContinue === '1') {
            _mtgAutoContinueDecisionWindow(el.dataset.meetingId || '');
        }
    });
}

function _mtgMaybeAutoContinueDecisionMeeting(m) {
    if (!m || !m.executableMeeting || (m.executionStage || '') !== 'awaiting_user_decision') return;
    if (m.arbitration && m.arbitration.reason === 'no_consensus') return;
    if (_mtgDecisionSecondsRemaining(m.decisionDeadlineAt || '') === 0) {
        _mtgAutoContinueDecisionWindow(m.id || '');
    }
}

async function _mtgAutoContinueDecisionWindow(meetingId) {
    if (!meetingId || _mtgDecisionAutoContinuing[meetingId]) return;
    _mtgDecisionAutoContinuing[meetingId] = true;
    var badge = document.getElementById('mtg-decision-countdown-' + meetingId);
    if (badge) {
        badge.textContent = '⏳ ' + _mtgT('meeting_decision_continuing', 'Continuing');
        badge.dataset.autoContinue = '0';
    }
    _mtgSetDecisionControlsDisabled(meetingId, true);
    try {
        var ran = await _mtgRunMeeting(meetingId, { action: 'timeout' });
        await _mtgAfterMeetingRefresh();
        if (_mtgMeetingCompleted(ran && ran.meeting)) switchMtgTab('completed');
        else switchMtgTab('active');
    } catch (e) {
        console.warn('[meetings] decision window auto-continue failed:', e);
        if (badge) {
            badge.textContent = '⏳ 0s';
            badge.dataset.autoContinue = '1';
        }
        _mtgSetDecisionControlsDisabled(meetingId, false);
    } finally {
        delete _mtgDecisionAutoContinuing[meetingId];
    }
}

function _mtgSetDecisionControlsDisabled(meetingId, disabled) {
    ['mtg-target-submit-', 'mtg-continue-', 'mtg-target-participant-', 'mtg-target-question-', 'mtg-agenda-submit-', 'mtg-agenda-text-', 'mtg-agenda-reason-', 'mtg-arb-decision-', 'mtg-arb-rationale-', 'mtg-arb-consensus-', 'mtg-arb-decide-', 'mtg-arb-end-', 'mtg-arb-continue-', 'mtg-takeover-submit-', 'mtg-replacement-submit-', 'mtg-takeover-summary-', 'mtg-takeover-decision-', 'mtg-replacement-moderator-'].forEach(function(prefix) {
        var el = document.getElementById(prefix + meetingId);
        if (el) el.disabled = !!disabled;
    });
}

function _mtgRenderInterventionForm(m) {
    var id = _escMtg(m.id);
    var agendaValue = _escMtg(m.agenda || m.topic || '');
    return '<div class="mtg-section mtg-intervention" data-meeting-id="' + id + '">' +
        '<div class="mtg-section-title">' + _escMtg(_mtgT('meeting_user_intervention', 'User intervention')) + '</div>' +
        '<label class="mtg-label">' + _escMtg(_mtgT('meeting_user_message', 'Message')) + '</label>' +
        '<textarea id="mtg-intervention-text-' + id + '" class="mtg-textarea" rows="3" placeholder="' + _escMtg(_mtgT('meeting_user_message_placeholder', 'Add a live comment for the agents.')) + '"></textarea>' +
        '<label class="mtg-label">' + _escMtg(_mtgT('meeting_add_context', 'Additional context')) + '</label>' +
        '<textarea id="mtg-intervention-context-' + id + '" class="mtg-textarea" rows="3" placeholder="' + _escMtg(_mtgT('meeting_add_context_placeholder', 'Add facts or constraints for later turns.')) + '"></textarea>' +
        '<div id="mtg-intervention-error-' + id + '" class="mtg-inline-error"></div>' +
        '<button id="mtg-intervention-submit-' + id + '" class="mtg-btn mtg-btn-end" onclick="submitMeetingIntervention(\'' + id + '\')">' + _escMtg(_mtgT('meeting_send_intervention', 'Send')) + '</button>' +
        '<div class="mtg-subsection">' +
        '<div class="mtg-section-title mtg-section-title-small">' + _escMtg(_mtgT('meeting_adjust_agenda', 'Adjust agenda')) + '</div>' +
        '<label class="mtg-label">' + _escMtg(_mtgT('meeting_new_agenda', 'New agenda')) + '</label>' +
        '<textarea id="mtg-agenda-text-' + id + '" class="mtg-textarea" rows="2" placeholder="' + _escMtg(_mtgT('meeting_new_agenda_placeholder', 'Set the agenda for upcoming turns.')) + '">' + agendaValue + '</textarea>' +
        '<label class="mtg-label">' + _escMtg(_mtgT('meeting_agenda_reason', 'Reason')) + '</label>' +
        '<input id="mtg-agenda-reason-' + id + '" class="skl-input" type="text" placeholder="' + _escMtg(_mtgT('meeting_agenda_reason_placeholder', 'Optional reason for the change.')) + '">' +
        '<div id="mtg-agenda-error-' + id + '" class="mtg-inline-error"></div>' +
        '<button id="mtg-agenda-submit-' + id + '" class="mtg-btn" onclick="submitMeetingAgendaChange(\'' + id + '\')">' + _escMtg(_mtgT('meeting_save_agenda', 'Save agenda')) + '</button>' +
        '</div>' +
        '</div>';
}

function _mtgRenderDecisionWindowControls(m) {
    var id = _escMtg(m.id);
    var participants = m.participants || m.agents || [];
    var options = participants.map(function(p) {
        var info = _mtgAgentMap[p] || { emoji: '🤖', name: p };
        return '<option value="' + _escMtg(p) + '">' + _escMtg((info.emoji || '🤖') + ' ' + (info.name || p)) + '</option>';
    }).join('');
    var deadline = m.decisionDeadlineAt ? new Date(m.decisionDeadlineAt).toLocaleTimeString() : '';
    var isNoConsensus = m.arbitration && m.arbitration.reason === 'no_consensus';
    var willSummarize = !isNoConsensus && (m.decisionNextStage === 'summarizing');
    var hint = isNoConsensus
        ? _mtgT('meeting_arbitration_waiting_hint', 'The meeting found unresolved disagreement. Choose a decision, continue discussion, or end with no consensus.')
        : (willSummarize
            ? _mtgT('meeting_decision_summary_hint', 'The final formal round is complete. Ask one participant, add context, or wait for the moderator to summarize and end.')
            : _mtgT('meeting_decision_window_hint', 'A formal round is complete. Ask one participant, add context, or continue the agenda.'));
    if (!isNoConsensus && m.decisionWindowSec) hint += ' ' + _mtgT('meeting_decision_window_timeout', 'Timeout') + ': ' + m.decisionWindowSec + 's';
    if (!isNoConsensus && deadline) hint += ' · ' + _mtgT('meeting_decision_deadline', 'Deadline') + ': ' + deadline;
    var html = '<div class="mtg-section mtg-decision-window" data-meeting-id="' + id + '">' +
        '<div class="mtg-section-title">' + _escMtg(_mtgT('meeting_decision_window', 'Round decision window')) + '</div>' +
        (!isNoConsensus ? '<div class="mtg-section-text mtg-decision-countdown" data-meeting-id="' + id + '" data-deadline="' + _escMtg(m.decisionDeadlineAt || '') + '" data-auto-continue="1">' + _escMtg(_mtgDecisionCountdownText(m)) + '</div>' : '') +
        '<div class="mtg-section-text">' + _escMtg(hint) + '</div>' +
        '<label class="mtg-label">' + _escMtg(_mtgT('meeting_target_participant', 'Target participant')) + '</label>' +
        '<select id="mtg-target-participant-' + id + '" class="skl-input">' + options + '</select>' +
        '<label class="mtg-label">' + _escMtg(_mtgT('meeting_target_question', 'Targeted question')) + '</label>' +
        '<textarea id="mtg-target-question-' + id + '" class="mtg-textarea" rows="3" placeholder="' + _escMtg(_mtgT('meeting_target_question_placeholder', 'Ask this participant to respond before the next round.')) + '"></textarea>' +
        '<div id="mtg-target-error-' + id + '" class="mtg-inline-error"></div>' +
        '<div class="mtg-decision-actions">' +
        '<button id="mtg-target-submit-' + id + '" class="mtg-btn mtg-btn-end" onclick="submitMeetingTargetedQuestion(\'' + id + '\')">' + _escMtg(_mtgT('meeting_send_targeted_question', 'Ask participant')) + '</button>' +
        '<button id="mtg-continue-' + id + '" class="mtg-btn" onclick="continueMeetingDecisionWindow(\'' + id + '\')">▶ ' + _escMtg(_mtgT('meeting_continue', 'Continue')) + '</button>' +
        '</div>' +
        '</div>';
    if (isNoConsensus) {
        html += _mtgRenderArbitrationControls(m);
    }
    return html;
}

function _mtgRenderArbitrationControls(m) {
    var id = _escMtg(m.id);
    var arb = m.arbitration || {};
    var positions = (arb.positions || []).map(function(item) {
        var info = _mtgAgentMap[item.speaker] || { emoji: '🤖', name: item.speaker || '' };
        return '<div class="mtg-arb-position"><strong>' + _escMtg((info.emoji || '🤖') + ' ' + (info.name || item.speaker || '')) + '</strong><span>' + _escMtg(item.position || '') + '</span></div>';
    }).join('');
    var disagreements = (arb.disagreements || []).map(function(item) { return '• ' + _escMtg(item); }).join('\n');
    return '<div class="mtg-section mtg-arbitration" data-meeting-id="' + id + '">' +
        '<div class="mtg-section-title">' + _escMtg(_mtgT('meeting_arbitration_title', 'No consensus arbitration')) + '</div>' +
        '<div class="mtg-section-text">' + _escMtg(arb.moderatorSuggestion || _mtgT('meeting_arbitration_hint', 'Choose a decision, continue discussion, or end with no consensus.')) + '</div>' +
        (positions ? '<div class="mtg-arb-positions">' + positions + '</div>' : '') +
        (disagreements ? '<div class="mtg-section-text mtg-arb-disagreements">' + disagreements + '</div>' : '') +
        '<label class="mtg-label">' + _escMtg(_mtgT('meeting_arbitration_decision', 'Decision')) + '</label>' +
        '<textarea id="mtg-arb-decision-' + id + '" class="mtg-textarea" rows="2" placeholder="' + _escMtg(_mtgT('meeting_arbitration_decision_placeholder', 'Write the user decision to finalize.')) + '"></textarea>' +
        '<label class="mtg-label">' + _escMtg(_mtgT('meeting_arbitration_rationale', 'Rationale')) + '</label>' +
        '<input id="mtg-arb-rationale-' + id + '" class="skl-input" type="text" placeholder="' + _escMtg(_mtgT('meeting_arbitration_rationale_placeholder', 'Optional rationale.')) + '">' +
        '<div id="mtg-arb-error-' + id + '" class="mtg-inline-error"></div>' +
        '<div class="mtg-decision-actions">' +
        '<button id="mtg-arb-consensus-' + id + '" class="mtg-btn mtg-btn-end" onclick="submitMeetingArbitration(\'' + id + '\', \'consensus_summary\')">' + _escMtg(_mtgT('meeting_arbitration_consensus_summary', 'Consensus reached, summarize')) + '</button>' +
        '<button id="mtg-arb-decide-' + id + '" class="mtg-btn mtg-btn-end" onclick="submitMeetingArbitration(\'' + id + '\', \'decide\')">' + _escMtg(_mtgT('meeting_arbitration_decide', 'Finalize decision')) + '</button>' +
        '<button id="mtg-arb-continue-' + id + '" class="mtg-btn" onclick="submitMeetingArbitration(\'' + id + '\', \'continue_discussion\')">' + _escMtg(_mtgT('meeting_arbitration_continue', 'Continue one round')) + '</button>' +
        '<button id="mtg-arb-end-' + id + '" class="mtg-btn mtg-btn-delete" onclick="submitMeetingArbitration(\'' + id + '\', \'end_no_consensus\')">' + _escMtg(_mtgT('meeting_arbitration_end', 'End no consensus')) + '</button>' +
        '</div>' +
        '</div>';
}

function _mtgRenderModeratorTakeoverControls(m) {
    var id = _escMtg(m.id);
    var failure = m.moderatorFailure || {};
    var participants = m.participants || m.agents || [];
    var currentModerator = m.moderator || failure.moderator || '';
    var options = participants.map(function(p) {
        var info = _mtgAgentMap[p] || { emoji: '🤖', name: p };
        return '<option value="' + _escMtg(p) + '"' + (p === currentModerator ? ' disabled' : '') + '>' + _escMtg((info.emoji || '🤖') + ' ' + (info.name || p)) + (p === currentModerator ? ' (' + _escMtg(_mtgT('meeting_current_moderator', 'current')) + ')' : '') + '</option>';
    }).join('');
    return '<div class="mtg-section mtg-moderator-takeover" data-meeting-id="' + id + '">' +
        '<div class="mtg-section-title">' + _escMtg(_mtgT('meeting_moderator_takeover_title', 'Moderator takeover')) + '</div>' +
        '<div class="mtg-section-text">' + _escMtg(_mtgT('meeting_moderator_takeover_hint', 'The moderator failed while summarizing. Take over manually or choose another moderator to retry.')) + '</div>' +
        '<div class="mtg-inline-error" style="display:block">' + _escMtg(failure.error || '') + '</div>' +
        '<label class="mtg-label">' + _escMtg(_mtgT('meeting_takeover_summary', 'User summary')) + '</label>' +
        '<textarea id="mtg-takeover-summary-' + id + '" class="mtg-textarea" rows="3" placeholder="' + _escMtg(_mtgT('meeting_takeover_summary_placeholder', 'Write the final summary to close the meeting.')) + '"></textarea>' +
        '<label class="mtg-label">' + _escMtg(_mtgT('meeting_takeover_decision', 'Decision')) + '</label>' +
        '<input id="mtg-takeover-decision-' + id + '" class="skl-input" type="text" placeholder="' + _escMtg(_mtgT('meeting_takeover_decision_placeholder', 'Optional final decision.')) + '">' +
        '<div id="mtg-takeover-error-' + id + '" class="mtg-inline-error"></div>' +
        '<div class="mtg-decision-actions">' +
        '<button id="mtg-takeover-submit-' + id + '" class="mtg-btn mtg-btn-end" onclick="submitModeratorTakeover(\'' + id + '\', \'user_takeover\')">' + _escMtg(_mtgT('meeting_takeover_submit', 'Take over and close')) + '</button>' +
        '</div>' +
        '<div class="mtg-subsection">' +
        '<label class="mtg-label">' + _escMtg(_mtgT('meeting_replacement_moderator', 'Replacement moderator')) + '</label>' +
        '<select id="mtg-replacement-moderator-' + id + '" class="skl-input">' + options + '</select>' +
        '<button id="mtg-replacement-submit-' + id + '" class="mtg-btn" onclick="submitModeratorTakeover(\'' + id + '\', \'replace_moderator\')">' + _escMtg(_mtgT('meeting_replace_moderator_submit', 'Retry with moderator')) + '</button>' +
        '</div>' +
        '</div>';
}

function _escMtg(s) {
    if (!s) return '';
    return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;').replace(/'/g, '&#39;');
}

function _mtgJsArg(value) {
    return JSON.stringify(value == null ? '' : String(value)).replace(/</g, '\\u003c');
}

function _mtgT(key, fallback) {
    if (typeof i18n !== 'undefined' && i18n && typeof i18n.t === 'function') {
        var translated = i18n.t(key);
        if (translated && translated !== key) return translated;
    }
    var lang = 'en';
    try { lang = (typeof i18n !== 'undefined' && i18n.getLanguage && i18n.getLanguage()) || document.documentElement.lang || 'en'; } catch (e) {}
    var zhFallback = {
        new_meeting: '新建会议',
        meeting_executable: '可执行会议',
        meeting_stage: '阶段',
        meeting_preparing_timeout_remaining: '{seconds} 秒后自动释放',
        meeting_preparing_timeout_released: '准备超时已释放',
        meeting_version: '版本',
        meeting_id: '会议ID',
        meeting_round: '轮次',
        meeting_moderator: '主持人',
        meeting_context_mode: '上下文模式',
        meeting_current_speaker: '当前发言者',
        meeting_contributions: '主要贡献',
        meeting_transcript: '逐轮发言',
        meeting_opening_round: '开场轮',
        meeting_discussion_round: '讨论轮',
        meeting_turn_failed: '调用失败',
        meeting_provider_calling: '正在调用',
        meeting_live_discussion: '实时讨论',
        meeting_user_intervention: '用户插话',
        meeting_user_message: '发言',
        meeting_user_message_placeholder: '给正在讨论的 Agent 补充一段发言',
        meeting_add_context: '补充上下文',
        meeting_add_context_placeholder: '补充事实、约束或用户确认信息，后续发言会看到',
        meeting_send_intervention: '发送',
        meeting_intervention_required: '请输入发言或补充上下文。',
        meeting_user: '用户',
        meeting_turn_position: '立场',
        meeting_turn_reasoning: '理由',
        meeting_turn_disagreements: '分歧',
        meeting_turn_questions: '问题',
        meeting_turn_next_step: '下一步',
        meeting_turn_confidence: '信心',
        meeting_parse_fallback: '已保留原文',
        meeting_ai_end: '请主持人总结并结束',
        meeting_ai_ending: '主持人总结中...',
        meeting_start_existing: '开始会议',
        meeting_starting: '启动中...',
        meeting_start_failed: '开始会议失败',
        meeting_decision_window: '轮末决策窗口',
        meeting_decision_window_hint: '本轮正式发言已结束。可以点名、补充上下文，或继续原议程。',
        meeting_decision_summary_hint: '最后一轮正式发言已结束。可以点名、补充上下文，或等待主持人总结并结束。',
        meeting_decision_window_timeout: '等待',
        meeting_decision_deadline: '截止',
        meeting_decision_waiting: '等待中',
        meeting_decision_continuing: '继续中',
        meeting_target_participant: '点名对象',
        meeting_target_question: '点名问题',
        meeting_target_question_placeholder: '请指定参会 Agent 在进入下一轮前补充回答',
        meeting_send_targeted_question: '点名提问',
        meeting_continue: '继续',
        meeting_targeted_question: '点名提问',
        meeting_targeted_response: '点名回答',
        meeting_target_required: '请选择点名对象。',
        meeting_target_question_required: '请输入点名问题。',
        meeting_targeted_calling: '正在回答点名',
        meeting_current_agenda: '当前议题',
        meeting_adjust_agenda: '调整议题',
        meeting_new_agenda: '新议题',
        meeting_new_agenda_placeholder: '设置后续轮次要讨论的议题',
        meeting_agenda_reason: '调整原因',
        meeting_agenda_reason_placeholder: '可选，说明为什么调整',
        meeting_save_agenda: '保存议题',
        meeting_agenda_required: '请填写新议题。',
        meeting_agenda_changed: '议题调整',
        meeting_previous_agenda: '原议题',
        meeting_arbitration_title: '无共识裁决',
        meeting_arbitration_hint: '请选择裁决、继续讨论或以无共识结束。',
        meeting_arbitration_waiting: '等待裁决',
        meeting_arbitration_waiting_hint: '会议存在未解决分歧。请选择裁决、继续讨论或以无共识结束。',
        meeting_arbitration_decision: '裁决',
        meeting_arbitration_decision_placeholder: '填写最终采纳的用户裁决',
        meeting_arbitration_rationale: '裁决理由',
        meeting_arbitration_rationale_placeholder: '可选，说明裁决依据',
        meeting_arbitration_consensus_summary: '达成共识并总结',
        meeting_arbitration_decide: '采纳裁决并结束',
        meeting_arbitration_continue: '继续一轮',
        meeting_arbitration_end: '无共识结束',
        meeting_arbitration_decision_required: '请填写裁决内容。',
        meeting_arbitration_marker: '用户裁决',
        meeting_arbitration_action: '动作',
        meeting_moderator_takeover_title: '主持接管',
        meeting_moderator_takeover_hint: '主持人在总结时失败。你可以手动接管结束，或选择另一位主持人重试。',
        meeting_takeover_summary: '用户总结',
        meeting_takeover_summary_placeholder: '填写最终总结以结束会议',
        meeting_takeover_decision: '决议',
        meeting_takeover_decision_placeholder: '可选，填写最终决议',
        meeting_takeover_summary_required: '请填写用户总结。',
        meeting_takeover_submit: '接管并结束',
        meeting_replacement_moderator: '替换主持人',
        meeting_replace_moderator_submit: '用新主持重试',
        meeting_current_moderator: '当前',
        meeting_view_detail: '查看详情',
        meeting_detail_title: '会议详情',
        meeting_history_search_placeholder: '搜索历史会议',
        meeting_topic: '主题',
        meeting_topic_placeholder: '这场会议要讨论什么？',
        meeting_purpose: '目的',
        meeting_purpose_placeholder: '这场会议需要产出什么结果？',
        meeting_type: '会议类型',
        meeting_project: '项目',
        meeting_project_none: '不绑定项目',
        meeting_type_information: '信息收集',
        meeting_type_discussion: '讨论决策',
        meeting_type_task: '任务协作',
        meeting_participants: '参会者',
        meeting_branch_quick_select: '按部门快捷选择',
        meeting_branch_quick_select_hint: '先选择部门，再手动调整单个 Agent。',
        meeting_context_incremental: '增量',
        meeting_context_summary: '摘要',
        meeting_context_full: '完整',
        meeting_resolution_policy: '裁决策略',
        meeting_resolution_user_decision: '用户裁决分歧',
        meeting_resolution_moderator_decision: '主持裁决并关闭',
        meeting_result_summary: '会议结论',
        meeting_outcome: '结果',
        meeting_outcome_approved: '通过',
        meeting_outcome_rejected: '不通过',
        meeting_outcome_no_consensus: '无共识',
        meeting_outcome_needs_user_decision: '需要用户裁决',
        meeting_rationale: '理由',
        meeting_unresolved_questions: '未解决问题',
        meeting_disagreements: '分歧',
        meeting_max_rounds: '最大讨论轮次',
        meeting_initial_context: '初始上下文',
        meeting_initial_context_placeholder: '用户确认后提供给所有 Agent 的上下文',
        meeting_start: '开始会议',
        meeting_running: '会议运行中...',
        meeting_error_topic_required: '请填写会议主题。',
        meeting_error_participants_required: '至少选择两名参会者。',
        meeting_error_moderator_required: '请选择主持人。',
        meeting_action_drafts: '行动项草稿',
        meeting_action_drafts_hint: '确认后会加入来源任务的会议行动项，草稿不会自动执行。',
        meeting_action_untitled: '未命名行动项',
        meeting_action_status_draft: '待确认',
        meeting_action_status_confirmed: '已加入当前任务',
        meeting_action_status_rejected: '已拒绝',
        meeting_action_status_kept: '仅保存',
        meeting_action_edit: '编辑',
        meeting_action_owner: '负责人',
        meeting_action_title: '任务标题',
        meeting_action_description: '说明',
        meeting_action_save_draft: '保存草稿',
        meeting_action_confirm_task: '加入当前任务',
        meeting_action_keep: '仅保存',
        meeting_action_reject: '拒绝',
        meeting_action_open_task: '打开来源任务',
        meeting_action_task_created: '已加入来源任务',
        meeting_action_rejected_by_user: '用户拒绝'
    };
    if (String(lang).toLowerCase().indexOf('zh') === 0 && zhFallback[key]) return zhFallback[key];
    return fallback || key;
}

function _mtgLiveStateFromMeeting(m) {
    var state = {
        lastSeq: Number(m.lastEventSequence || 0),
        transcript: [],
        pendingBySeq: {},
        turnBySeq: {},
        timeoutRunBySeq: {}
    };
    (m.transcript || []).forEach(function(turn) {
        var seq = Number(turn.sequence || 0);
        if (seq) state.turnBySeq[seq] = true;
        state.transcript.push(turn);
    });
    (m.pendingCalls || []).forEach(function(call) {
        var seq = Number(call.sequence || 0);
        if (seq) state.pendingBySeq[seq] = call;
    });
    return state;
}

function _mtgSeedLiveMeetings(meetings) {
    (meetings || []).forEach(function(m) {
        if (!m.executableMeeting || m.status !== 'active') return;
        _mtgLiveEvents[m.id] = _mtgLiveStateFromMeeting(m);
    });
}

function _mtgMergeLiveMeeting(m) {
    if (!m || !m.executableMeeting || m.status !== 'active') return m;
    var state = _mtgLiveEvents[m.id];
    if (!state) return m;
    var copy = Object.assign({}, m);
    copy.transcript = state.transcript.slice();
    copy.pendingCalls = Object.keys(state.pendingBySeq).map(function(key) { return state.pendingBySeq[key]; });
    copy.lastEventSequence = Math.max(Number(copy.lastEventSequence || 0), Number(state.lastSeq || 0));
    return copy;
}

function _mtgTurnFromParticipantEvent(event) {
    var payload = event.payload || {};
    return {
        type: 'participant_turn',
        sequence: event.sequence,
        stage: payload.stage || event.stage || '',
        round: Number(payload.round || event.round || 0),
        speaker: payload.speaker || (event.actor || {}).id || '',
        text: payload.text || '',
        rawText: payload.rawText || payload.text || '',
        structured: payload.structured || {},
        parseError: payload.parseError || '',
        ok: !!payload.ok,
        durationMs: Number(payload.durationMs || 0),
        providerRef: payload.providerRef || {},
        kind: payload.kind || '',
        targetQuestion: payload.targetQuestion || '',
        createdAt: event.createdAt || ''
    };
}

function _mtgTurnFromUserInterventionEvent(event) {
    var payload = event.payload || {};
    return {
        type: 'user_intervention',
        sequence: event.sequence,
        stage: payload.stage || event.stage || '',
        round: Number(payload.round || event.round || 0),
        speaker: payload.actorId || (event.actor || {}).id || 'user',
        actorType: 'user',
        text: payload.text || '',
        context: payload.context || '',
        ok: true,
        durationMs: 0,
        providerRef: {},
        createdAt: event.createdAt || ''
    };
}

function _mtgTurnFromTargetedQuestionEvent(event) {
    var payload = event.payload || {};
    return {
        type: 'targeted_question',
        sequence: event.sequence,
        stage: payload.stage || event.stage || '',
        round: Number(payload.round || event.round || 0),
        speaker: payload.actorId || (event.actor || {}).id || 'user',
        actorType: 'user',
        target: payload.target || '',
        text: payload.question || '',
        ok: true,
        durationMs: 0,
        providerRef: {},
        createdAt: event.createdAt || ''
    };
}

function _mtgTurnFromAgendaChangeEvent(event) {
    var payload = event.payload || {};
    return {
        type: 'agenda_change',
        sequence: event.sequence,
        stage: payload.stage || event.stage || '',
        round: Number(payload.round || event.round || 0),
        speaker: payload.actorId || (event.actor || {}).id || 'user',
        actorType: 'user',
        text: payload.agenda || '',
        previousAgenda: payload.previousAgenda || '',
        reason: payload.reason || '',
        ok: true,
        durationMs: 0,
        providerRef: {},
        createdAt: event.createdAt || ''
    };
}

function _mtgTurnFromArbitrationEvent(event) {
    var payload = event.payload || {};
    return {
        type: 'arbitration_decision',
        sequence: event.sequence,
        stage: payload.stage || event.stage || '',
        round: Number(payload.round || event.round || 0),
        speaker: payload.actorId || (event.actor || {}).id || 'user',
        actorType: 'user',
        text: payload.decision || payload.action || '',
        action: payload.action || '',
        rationale: payload.rationale || '',
        ok: true,
        durationMs: 0,
        providerRef: {},
        createdAt: event.createdAt || ''
    };
}

function _mtgPendingFromProviderEvent(event) {
    var payload = event.payload || {};
    return {
        sequence: event.sequence,
        stage: payload.stage || event.stage || '',
        round: Number(payload.round || event.round || 0),
        speaker: payload.speaker || (event.actor || {}).id || '',
        purpose: payload.purpose || '',
        promptChars: Number(payload.promptChars || 0),
        contextMode: payload.contextMode || '',
        createdAt: event.createdAt || '',
        elapsedSec: Number(payload.elapsedSec || 0),
        timeoutSec: Number(payload.timeoutSec || 0),
        timedOut: !!payload.timedOut
    };
}

function _mtgProviderTimeoutSec() {
    return 120;
}

function _mtgCallElapsedSec(call) {
    if (!call) return 0;
    if (Number(call.elapsedSec || 0) > 0) return Number(call.elapsedSec || 0);
    if (!call.createdAt) return 0;
    var ts = Date.parse(call.createdAt);
    if (!isFinite(ts)) return 0;
    return Math.max(0, Math.floor((Date.now() - ts) / 1000));
}

function _mtgHydratePendingCall(call) {
    if (!call) return call;
    var copy = Object.assign({}, call);
    copy.elapsedSec = _mtgCallElapsedSec(copy);
    copy.timeoutSec = Number(copy.timeoutSec || _mtgProviderTimeoutSec());
    copy.timedOut = !!copy.timedOut || (copy.timeoutSec > 0 && copy.elapsedSec >= copy.timeoutSec);
    return copy;
}

function _mtgApplyLiveEvent(meetingId, event) {
    var state = _mtgLiveEvents[meetingId] || { lastSeq: 0, transcript: [], pendingBySeq: {}, turnBySeq: {}, timeoutRunBySeq: {} };
    var seq = Number(event.sequence || 0);
    if (seq) state.lastSeq = Math.max(Number(state.lastSeq || 0), seq);
    if (event.type === 'provider_call_started') {
        state.pendingBySeq[seq] = _mtgPendingFromProviderEvent(event);
    } else if (event.type === 'participant_turn') {
        var turn = _mtgTurnFromParticipantEvent(event);
        if (turn.sequence && !state.turnBySeq[turn.sequence]) {
            state.turnBySeq[turn.sequence] = true;
            state.transcript.push(turn);
        }
        var inReplyTo = (event.payload || {}).inReplyToSequence;
        if (inReplyTo != null) delete state.pendingBySeq[inReplyTo];
    } else if (event.type === 'user_intervention') {
        var intervention = _mtgTurnFromUserInterventionEvent(event);
        if (intervention.sequence && !state.turnBySeq[intervention.sequence]) {
            state.turnBySeq[intervention.sequence] = true;
            state.transcript.push(intervention);
        }
    } else if (event.type === 'targeted_question') {
        var targeted = _mtgTurnFromTargetedQuestionEvent(event);
        if (targeted.sequence && !state.turnBySeq[targeted.sequence]) {
            state.turnBySeq[targeted.sequence] = true;
            state.transcript.push(targeted);
        }
    } else if (event.type === 'agenda_change') {
        var agendaChange = _mtgTurnFromAgendaChangeEvent(event);
        if (agendaChange.sequence && !state.turnBySeq[agendaChange.sequence]) {
            state.turnBySeq[agendaChange.sequence] = true;
            state.transcript.push(agendaChange);
        }
    } else if (event.type === 'arbitration_decision') {
        var arbitration = _mtgTurnFromArbitrationEvent(event);
        if (arbitration.sequence && !state.turnBySeq[arbitration.sequence]) {
            state.turnBySeq[arbitration.sequence] = true;
            state.transcript.push(arbitration);
        }
    }
    _mtgLiveEvents[meetingId] = state;
}

function _mtgEnsureLivePolling() {
    if (_mtgLivePollTimer) return;
    _mtgLivePollTimer = setInterval(_mtgPollLiveMeetings, 2000);
}

function _mtgStopLivePolling() {
    if (_mtgLivePollTimer) clearInterval(_mtgLivePollTimer);
    _mtgLivePollTimer = null;
}

async function _mtgPollLiveMeetings() {
    var modal = document.getElementById('meetingsModal');
    if (!modal || modal.classList.contains('hidden')) {
        _mtgStopLivePolling();
        return;
    }
    var meetings = (_mtgData.active || []).filter(function(m) { return m.executableMeeting && m.status === 'active'; });
    if (!meetings.length) return;
    var changed = false;
    var shouldRefresh = false;
    await Promise.all(meetings.map(async function(m) {
        var state = _mtgLiveEvents[m.id] || _mtgLiveStateFromMeeting(m);
        _mtgLiveEvents[m.id] = state;
        try {
            var res = await fetch('/api/meetings/executable/' + encodeURIComponent(m.id) + '/events?after=' + encodeURIComponent(state.lastSeq || 0));
            var data = await res.json();
            if (!res.ok || data.error) return;
            _mtgMaybeAutoContinueDecisionMeeting(m);
            (data.events || []).forEach(function(event) {
                _mtgApplyLiveEvent(m.id, event);
                changed = true;
                if (event.type === 'meeting_result' || (event.type === 'meeting_transitioned' && (event.payload || {}).to === 'completed')) {
                    shouldRefresh = true;
                }
            });
            var hydratedPending = Object.keys(state.pendingBySeq || {}).map(function(key) {
                var call = _mtgHydratePendingCall(state.pendingBySeq[key]);
                state.pendingBySeq[key] = call;
                return call;
            });
            if (hydratedPending.some(function(call) { return call.timedOut; })) changed = true;
            hydratedPending.forEach(function(call) {
                if (!call.timedOut || !call.sequence || state.timeoutRunBySeq[call.sequence]) return;
                state.timeoutRunBySeq[call.sequence] = Date.now();
                fetch('/api/meetings/executable/' + encodeURIComponent(m.id) + '/run', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ action: 'provider_timeout_skip', pendingSequence: call.sequence })
                }).catch(function(e) {
                    console.warn('[meetings] provider timeout skip failed:', e);
                });
            });
        } catch (e) {
            console.warn('[meetings] live poll error:', e);
        }
    }));
    if (shouldRefresh) {
        await _mtgAfterMeetingRefresh();
        switchMtgTab('completed');
    } else if (changed && !modal.classList.contains('hidden')) {
        _mtgRender();
        _mtgRefreshDetailModal();
    }
}

function _mtgTranscriptGroupLabel(turn) {
    var stage = turn.stage || '';
    var round = Number(turn.round || 0);
    if (stage === 'active_opening') return _mtgT('meeting_opening_round', 'Opening round');
    if (stage === 'active_discussion') return _mtgT('meeting_discussion_round', 'Discussion round') + ' ' + (round || 1);
    return (stage || 'round') + ' ' + (round || 0);
}

function _mtgRenderTranscript(m) {
    var groups = [];
    var indexByKey = {};
    var rows = (m.transcript || []).map(function(turn) {
        return Object.assign({ pending: false }, turn);
    });
    (m.pendingCalls || []).forEach(function(call) {
        rows.push(Object.assign({ pending: true }, _mtgHydratePendingCall(call)));
    });
    rows.sort(function(a, b) { return Number(a.sequence || 0) - Number(b.sequence || 0); });
    rows.forEach(function(turn) {
        var key = (turn.stage || '') + ':' + (turn.round || 0);
        if (indexByKey[key] == null) {
            indexByKey[key] = groups.length;
            groups.push({ label: _mtgTranscriptGroupLabel(turn), turns: [] });
        }
        groups[indexByKey[key]].turns.push(turn);
    });
    var titleKey = m.status === 'active' ? 'meeting_live_discussion' : 'meeting_transcript';
    var titleFallback = m.status === 'active' ? 'Live discussion' : 'Round transcript';
    var html = '<div class="mtg-section"><div class="mtg-section-title">' + _escMtg(_mtgT(titleKey, titleFallback)) + '</div>';
    groups.forEach(function(group) {
        html += '<div class="mtg-round">';
        html += '<div class="mtg-round-title">' + _escMtg(group.label) + '</div>';
        group.turns.forEach(function(turn) {
            var isTargetedQuestion = turn.type === 'targeted_question';
            var isTargetedResponse = turn.kind === 'targeted_response';
            var isTargetedPending = turn.pending && turn.purpose === 'targeted_response';
            var isAgendaChange = turn.type === 'agenda_change';
            var isArbitration = turn.type === 'arbitration_decision';
            var isUserTurn = turn.type === 'user_intervention' || turn.actorType === 'user';
            var info = isUserTurn ? { emoji: '👤', name: _mtgT('meeting_user', 'User') } : (_mtgAgentMap[turn.speaker] || { emoji: '🤖', name: turn.speaker || 'Unknown' });
            var providerKind = ((turn.providerRef || {}).providerKind || '').trim();
            var pendingStatus = turn.timedOut ? _mtgT('meeting_provider_call_timeout', 'call timed out') : _mtgT('meeting_provider_calling', 'calling');
            var status = isUserTurn ? '' : (turn.pending ? ' · ' + pendingStatus : (turn.ok ? '' : ' · ' + _mtgT('meeting_turn_failed', 'failed')));
            var duration = turn.durationMs ? ' · ' + Math.round(turn.durationMs / 1000) + 's' : '';
            var pendingText = isTargetedPending ? _mtgT('meeting_targeted_calling', 'Answering targeted question...') : _mtgT('meeting_provider_calling', 'Calling provider...');
            if (turn.pending && turn.timedOut) {
                pendingText = _mtgT('meeting_provider_timeout_monitor', 'Provider call has exceeded the timeout and will be skipped so the meeting can continue.');
            } else if (turn.pending && turn.elapsedSec) {
                pendingText += ' · ' + _mtgT('meeting_provider_waited', 'waited') + ' ' + Math.round(turn.elapsedSec) + 's';
            }
            var text = turn.pending ? pendingText : (turn.text || '');
            var marker = '';
            if (isTargetedQuestion) {
                var targetInfo = _mtgAgentMap[turn.target] || { emoji: '🤖', name: turn.target || '' };
                marker = _mtgT('meeting_targeted_question', 'Targeted question') + (turn.target ? ' → ' + (targetInfo.name || turn.target) : '');
            } else if (isTargetedResponse) {
                marker = _mtgT('meeting_targeted_response', 'Targeted response');
            } else if (isAgendaChange) {
                marker = _mtgT('meeting_agenda_changed', 'Agenda changed');
            } else if (isArbitration) {
                marker = _mtgT('meeting_arbitration_marker', 'Arbitration');
            }
            if (isUserTurn && turn.context) {
                text += (text ? '\n\n' : '') + _mtgT('meeting_add_context', 'Additional context') + ': ' + turn.context;
            }
            if (isAgendaChange) {
                text = _mtgT('meeting_new_agenda', 'New agenda') + ': ' + (turn.text || '');
                if (turn.previousAgenda) text += '\n' + _mtgT('meeting_previous_agenda', 'Previous agenda') + ': ' + turn.previousAgenda;
                if (turn.reason) text += '\n' + _mtgT('meeting_agenda_reason', 'Reason') + ': ' + turn.reason;
            }
            if (isArbitration) {
                text = _mtgT('meeting_arbitration_action', 'Action') + ': ' + (turn.action || '') + (turn.text ? '\n' + _mtgT('meeting_arbitration_decision', 'Decision') + ': ' + turn.text : '');
                if (turn.rationale) text += '\n' + _mtgT('meeting_arbitration_rationale', 'Rationale') + ': ' + turn.rationale;
            }
            if (isTargetedResponse && turn.targetQuestion) {
                text = _mtgT('meeting_targeted_question', 'Targeted question') + ': ' + turn.targetQuestion + '\n\n' + text;
            }
            html += '<div class="mtg-turn' + (turn.pending ? ' mtg-turn-pending' : '') + (turn.timedOut ? ' mtg-turn-timeout' : '') + (isUserTurn ? ' mtg-turn-user' : '') + '">';
            html += '<div class="mtg-turn-header"><span class="mtg-response-emoji">' + _escMtg(info.emoji || '🤖') + '</span><span class="mtg-response-name">' + _escMtg(info.name || turn.speaker || 'Unknown') + '</span>';
            html += '<span class="mtg-turn-meta">' + _escMtg([marker, providerKind + status + duration].filter(Boolean).join(' · ')) + '</span></div>';
            if (!turn.pending && !isUserTurn && _mtgHasStructuredTurn(turn.structured)) {
                html += _mtgRenderStructuredTurn(turn.structured);
                if (turn.parseError) html += '<div class="mtg-turn-parse">' + _escMtg(_mtgT('meeting_parse_fallback', 'Fallback text retained')) + '</div>';
            } else {
                html += '<div class="mtg-turn-text">' + _escMtg(text) + '</div>';
                if (!turn.pending && !isUserTurn && turn.parseError) {
                    html += '<div class="mtg-turn-parse">' + _escMtg(_mtgT('meeting_parse_fallback', 'Fallback text retained')) + '</div>';
                }
            }
            html += '</div>';
        });
        html += '</div>';
    });
    html += '</div>';
    return html;
}

function _mtgHasStructuredTurn(structured) {
    if (!structured || typeof structured !== 'object') return false;
    return ['position', 'reasoning', 'suggestedNextStep', 'confidence'].some(function(key) {
        return !!String(structured[key] || '').trim();
    }) || ['disagreements', 'questions'].some(function(key) {
        return Array.isArray(structured[key]) && structured[key].length > 0;
    });
}

function _mtgStructuredValue(value) {
    if (Array.isArray(value)) return value.filter(function(item) { return String(item || '').trim(); }).join('\n');
    return String(value || '').trim();
}

function _mtgStripJsonFence(text) {
    var raw = String(text || '').trim();
    if (raw.indexOf('```') === 0) {
        var lines = raw.split(/\r?\n/);
        if (lines.length && lines[0].trim().indexOf('```') === 0) lines.shift();
        if (lines.length && lines[lines.length - 1].trim().indexOf('```') === 0) lines.pop();
        raw = lines.join('\n').trim();
    }
    return raw;
}

function _mtgParseJsonObject(text) {
    var raw = _mtgStripJsonFence(text);
    if (!raw) return null;
    try {
        var parsed = JSON.parse(raw);
        return parsed && typeof parsed === 'object' && !Array.isArray(parsed) ? parsed : null;
    } catch (e) {}
    var idx = raw.indexOf('{');
    while (idx >= 0) {
        var end = raw.lastIndexOf('}');
        while (end > idx) {
            try {
                var obj = JSON.parse(raw.slice(idx, end + 1));
                return obj && typeof obj === 'object' && !Array.isArray(obj) ? obj : null;
            } catch (e2) {
                end = raw.lastIndexOf('}', end - 1);
            }
        }
        idx = raw.indexOf('{', idx + 1);
    }
    return null;
}

function _mtgNormalizeStructuredContribution(obj) {
    var keyMap = {
        position: 'position',
        reasoning: 'reasoning',
        disagreements: 'disagreements',
        questions: 'questions',
        suggestednextstep: 'suggestedNextStep',
        suggested_next_step: 'suggestedNextStep',
        confidence: 'confidence'
    };
    var structured = {};
    Object.keys(obj || {}).forEach(function(rawKey) {
        var normalized = String(rawKey || '').replace(/[^A-Za-z_]/g, '').toLowerCase();
        var key = keyMap[normalized];
        if (!key) return;
        if (key === 'disagreements' || key === 'questions') {
            var value = obj[rawKey];
            structured[key] = Array.isArray(value) ? value.map(function(item) { return String(item || '').trim(); }).filter(Boolean) : [String(value || '').trim()].filter(Boolean);
        } else {
            structured[key] = String(obj[rawKey] || '').trim();
        }
    });
    if (structured.position || structured.reasoning || structured.suggestedNextStep || structured.confidence || (structured.disagreements || []).length || (structured.questions || []).length) {
        structured.disagreements = structured.disagreements || [];
        structured.questions = structured.questions || [];
        return structured;
    }
    return null;
}

function _mtgParseLabeledContribution(text) {
    var labelMap = {
        position: 'position',
        reasoning: 'reasoning',
        disagreements: 'disagreements',
        questions: 'questions',
        suggestednextstep: 'suggestedNextStep',
        confidence: 'confidence'
    };
    var structured = {};
    var currentKey = '';
    String(text || '').split(/\r?\n/).forEach(function(line) {
        var match = line.match(/^\s*([A-Za-z][A-Za-z ]{1,40}):\s*(.*)$/);
        var mapped = match ? labelMap[String(match[1] || '').replace(/[^A-Za-z]/g, '').toLowerCase()] : '';
        if (mapped) {
            currentKey = mapped;
            if (mapped === 'disagreements' || mapped === 'questions') {
                structured[mapped] = structured[mapped] || [];
                if (String(match[2] || '').trim()) structured[mapped].push(String(match[2] || '').trim());
            } else {
                structured[mapped] = [structured[mapped], String(match[2] || '').trim()].filter(Boolean).join('\n\n');
            }
            return;
        }
        if (!currentKey || !line.trim()) return;
        if (currentKey === 'disagreements' || currentKey === 'questions') {
            structured[currentKey] = structured[currentKey] || [];
            structured[currentKey].push(line.trim().replace(/^[-*]\s*/, ''));
        } else {
            structured[currentKey] = [structured[currentKey], line.trim()].filter(Boolean).join('\n');
        }
    });
    return _mtgNormalizeStructuredContribution(structured);
}

function _mtgRenderContributionText(text) {
    var raw = String(text || '').trim();
    var structured = _mtgNormalizeStructuredContribution(_mtgParseJsonObject(raw)) || _mtgParseLabeledContribution(raw);
    if (structured && _mtgHasStructuredTurn(structured)) return _mtgRenderStructuredTurn(structured);
    return _escMtg(raw);
}

function _mtgRenderStructuredTurn(structured) {
    var fields = [
        ['position', 'meeting_turn_position', 'Position'],
        ['reasoning', 'meeting_turn_reasoning', 'Reasoning'],
        ['disagreements', 'meeting_turn_disagreements', 'Disagreements'],
        ['questions', 'meeting_turn_questions', 'Questions'],
        ['suggestedNextStep', 'meeting_turn_next_step', 'Suggested next step'],
        ['confidence', 'meeting_turn_confidence', 'Confidence']
    ];
    var html = '<div class="mtg-structured-turn">';
    fields.forEach(function(field) {
        var value = _mtgStructuredValue(structured[field[0]]);
        if (!value) return;
        html += '<div class="mtg-structured-field">';
        html += '<div class="mtg-structured-label">' + _escMtg(_mtgT(field[1], field[2])) + '</div>';
        html += '<div class="mtg-structured-value">' + _escMtg(value) + '</div>';
        html += '</div>';
    });
    html += '</div>';
    return html;
}

async function submitMeetingIntervention(meetingId) {
    var textEl = document.getElementById('mtg-intervention-text-' + meetingId);
    var contextEl = document.getElementById('mtg-intervention-context-' + meetingId);
    var err = document.getElementById('mtg-intervention-error-' + meetingId);
    var btn = document.getElementById('mtg-intervention-submit-' + meetingId);
    var text = (textEl && textEl.value || '').trim();
    var context = (contextEl && contextEl.value || '').trim();
    function fail(message) {
        if (err) {
            err.textContent = message;
            err.style.display = 'block';
        }
    }
    if (!text && !context) return fail(_mtgT('meeting_intervention_required', 'Enter a message or additional context.'));
    if (err) err.style.display = 'none';
    if (btn) btn.disabled = true;
    try {
        var res = await fetch('/api/meetings/executable/' + encodeURIComponent(meetingId) + '/intervention', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                text: text,
                context: context,
                actorId: 'user',
                idempotencyKey: 'ui-intervention-' + Date.now() + '-' + Math.random().toString(16).slice(2)
            })
        });
        var data = await res.json();
        if (!res.ok || data.error) throw new Error(data.error || 'Failed to send intervention');
        if (textEl) textEl.value = '';
        if (contextEl) contextEl.value = '';
        if (data.event) _mtgApplyLiveEvent(meetingId, data.event);
        await _mtgAfterMeetingRefresh();
    } catch (e) {
        fail(e.message || String(e));
    } finally {
        if (btn) btn.disabled = false;
    }
}

async function submitMeetingAgendaChange(meetingId) {
    var agendaEl = document.getElementById('mtg-agenda-text-' + meetingId);
    var reasonEl = document.getElementById('mtg-agenda-reason-' + meetingId);
    var err = document.getElementById('mtg-agenda-error-' + meetingId);
    var btn = document.getElementById('mtg-agenda-submit-' + meetingId);
    var agenda = (agendaEl && agendaEl.value || '').trim();
    var reason = (reasonEl && reasonEl.value || '').trim();
    function fail(message) {
        if (err) {
            err.textContent = message;
            err.style.display = 'block';
        }
    }
    if (!agenda) return fail(_mtgT('meeting_agenda_required', 'Enter a new agenda.'));
    if (err) err.style.display = 'none';
    if (btn) btn.disabled = true;
    try {
        var res = await fetch('/api/meetings/executable/' + encodeURIComponent(meetingId) + '/agenda-change', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                agenda: agenda,
                reason: reason,
                actorId: 'user',
                idempotencyKey: 'ui-agenda-' + Date.now() + '-' + Math.random().toString(16).slice(2)
            })
        });
        var data = await res.json();
        if (!res.ok || data.error) throw new Error(data.error || 'Failed to save agenda');
        if (reasonEl) reasonEl.value = '';
        if (data.event) _mtgApplyLiveEvent(meetingId, data.event);
        await _mtgAfterMeetingRefresh();
    } catch (e) {
        fail(e.message || String(e));
    } finally {
        if (btn) btn.disabled = false;
    }
}

async function submitMeetingTargetedQuestion(meetingId) {
    var targetEl = document.getElementById('mtg-target-participant-' + meetingId);
    var questionEl = document.getElementById('mtg-target-question-' + meetingId);
    var err = document.getElementById('mtg-target-error-' + meetingId);
    var btn = document.getElementById('mtg-target-submit-' + meetingId);
    var target = (targetEl && targetEl.value || '').trim();
    var question = (questionEl && questionEl.value || '').trim();
    function fail(message) {
        if (err) {
            err.textContent = message;
            err.style.display = 'block';
        }
    }
    if (!target) return fail(_mtgT('meeting_target_required', 'Select a target participant.'));
    if (!question) return fail(_mtgT('meeting_target_question_required', 'Enter a targeted question.'));
    if (err) err.style.display = 'none';
    if (btn) btn.disabled = true;
    try {
        var res = await fetch('/api/meetings/executable/' + encodeURIComponent(meetingId) + '/targeted-question', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                target: target,
                question: question,
                actorId: 'user',
                idempotencyKey: 'ui-targeted-' + Date.now() + '-' + Math.random().toString(16).slice(2)
            })
        });
        var data = await res.json();
        if (!res.ok || data.error) throw new Error(data.error || 'Failed to ask targeted question');
        if (questionEl) questionEl.value = '';
        if (data.questionEvent) _mtgApplyLiveEvent(meetingId, data.questionEvent);
        if (data.pending) _mtgApplyLiveEvent(meetingId, data.pending);
        if (data.event) _mtgApplyLiveEvent(meetingId, data.event);
        await _mtgAfterMeetingRefresh();
    } catch (e) {
        fail(e.message || String(e));
    } finally {
        if (btn) btn.disabled = false;
    }
}

async function submitMeetingArbitration(meetingId, action) {
    var decisionEl = document.getElementById('mtg-arb-decision-' + meetingId);
    var rationaleEl = document.getElementById('mtg-arb-rationale-' + meetingId);
    var err = document.getElementById('mtg-arb-error-' + meetingId);
    var decision = (decisionEl && decisionEl.value || '').trim();
    var rationale = (rationaleEl && rationaleEl.value || '').trim();
    function fail(message) {
        if (err) {
            err.textContent = message;
            err.style.display = 'block';
        }
    }
    if (action === 'decide' && !decision) return fail(_mtgT('meeting_arbitration_decision_required', 'Enter a decision.'));
    if (err) err.style.display = 'none';
    _mtgSetDecisionControlsDisabled(meetingId, true);
    try {
        var res = await fetch('/api/meetings/executable/' + encodeURIComponent(meetingId) + '/arbitration', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                action: action,
                decision: decision,
                rationale: rationale,
                actorId: 'user',
                idempotencyKey: 'ui-arbitration-' + action + '-' + Date.now() + '-' + Math.random().toString(16).slice(2)
            })
        });
        var data = await res.json();
        if (!res.ok || data.error) throw new Error(data.error || 'Failed to submit arbitration');
        if (data.event) _mtgApplyLiveEvent(meetingId, data.event);
        var latest = data;
        if (action === 'continue_discussion' && data.meeting && data.meeting.stage !== 'completed') {
            latest = await _mtgRunMeeting(meetingId, { action: 'continue' });
        }
        await _mtgAfterMeetingRefresh();
        if (_mtgMeetingCompleted(latest && latest.meeting)) switchMtgTab('completed');
        else switchMtgTab('active');
    } catch (e) {
        fail(e.message || String(e));
        await _mtgAfterMeetingRefresh();
        _mtgSetDecisionControlsDisabled(meetingId, false);
    }
}

async function submitModeratorTakeover(meetingId, action) {
    var summaryEl = document.getElementById('mtg-takeover-summary-' + meetingId);
    var decisionEl = document.getElementById('mtg-takeover-decision-' + meetingId);
    var replacementEl = document.getElementById('mtg-replacement-moderator-' + meetingId);
    var err = document.getElementById('mtg-takeover-error-' + meetingId);
    var summary = (summaryEl && summaryEl.value || '').trim();
    var decision = (decisionEl && decisionEl.value || '').trim();
    var replacement = (replacementEl && replacementEl.value || '').trim();
    function fail(message) {
        if (err) {
            err.textContent = message;
            err.style.display = 'block';
        }
    }
    if (action === 'user_takeover' && !summary) return fail(_mtgT('meeting_takeover_summary_required', 'Enter a user summary.'));
    if (err) err.style.display = 'none';
    _mtgSetDecisionControlsDisabled(meetingId, true);
    ['mtg-takeover-submit-', 'mtg-replacement-submit-', 'mtg-takeover-summary-', 'mtg-takeover-decision-', 'mtg-replacement-moderator-'].forEach(function(prefix) {
        var el = document.getElementById(prefix + meetingId);
        if (el) el.disabled = true;
    });
    try {
        var res = await fetch('/api/meetings/executable/' + encodeURIComponent(meetingId) + '/moderator-takeover', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                action: action,
                summary: summary,
                decision: decision,
                moderator: replacement,
                actorId: 'user',
                idempotencyKey: 'ui-moderator-takeover-' + action + '-' + Date.now() + '-' + Math.random().toString(16).slice(2)
            })
        });
        var data = await res.json();
        if (!res.ok || data.error) throw new Error(data.error || 'Failed to submit moderator takeover');
        if (data.event) _mtgApplyLiveEvent(meetingId, data.event);
        if (data.takeoverEvent) _mtgApplyLiveEvent(meetingId, data.takeoverEvent);
        await _mtgAfterMeetingRefresh();
        if (_mtgMeetingCompleted(data.meeting)) switchMtgTab('completed');
        else switchMtgTab('active');
    } catch (e) {
        fail(e.message || String(e));
        _mtgSetDecisionControlsDisabled(meetingId, false);
        ['mtg-takeover-submit-', 'mtg-replacement-submit-', 'mtg-takeover-summary-', 'mtg-takeover-decision-', 'mtg-replacement-moderator-'].forEach(function(prefix) {
            var el = document.getElementById(prefix + meetingId);
            if (el) el.disabled = false;
        });
    }
}

async function continueMeetingDecisionWindow(meetingId) {
    var btn = document.getElementById('mtg-continue-' + meetingId);
    _mtgSetDecisionControlsDisabled(meetingId, true);
    try {
        var ran = await _mtgRunMeeting(meetingId, { action: 'continue' });
        await _mtgAfterMeetingRefresh();
        if (_mtgMeetingCompleted(ran && ran.meeting)) switchMtgTab('completed');
        else switchMtgTab('active');
    } catch (e) {
        alert(_mtgT('meeting_control_failed', 'Meeting control failed') + ': ' + (e.message || String(e)));
        _mtgSetDecisionControlsDisabled(meetingId, false);
    } finally {
        if (btn) btn.disabled = false;
    }
}

async function _mtgRunMeeting(meetingId, body) {
    var res = await fetch('/api/meetings/executable/' + encodeURIComponent(meetingId) + '/run', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body || {})
    });
    var data = await res.json();
    if (!res.ok || data.error) throw new Error(data.error || 'Failed to run meeting');
    return data;
}

async function startExecutableMeeting(meetingId) {
    var btn = document.getElementById('mtg-start-' + meetingId);
    if (btn) {
        btn.disabled = true;
        btn.textContent = _mtgT('meeting_starting', 'Starting...');
    }
    try {
        var ran = await _mtgRunMeeting(meetingId, { action: 'start' });
        await _mtgAfterMeetingRefresh();
        if (_mtgMeetingCompleted(ran && ran.meeting)) switchMtgTab('completed');
        else switchMtgTab('active');
    } catch (e) {
        alert(_mtgT('meeting_start_failed', 'Failed to start meeting') + ': ' + (e.message || String(e)));
        if (btn) {
            btn.disabled = false;
            btn.textContent = '▶ ' + _mtgT('meeting_start_existing', 'Start meeting');
        }
    }
}

function updateMeetingLabels() {
    var btn = document.getElementById('new-mtg-btn-label');
    if (btn) btn.textContent = _mtgT('new_meeting', 'New Meeting');
    var search = document.getElementById('mtg-history-search');
    if (search) search.placeholder = _mtgT('meeting_history_search_placeholder', 'Search meeting history');
}

function _mtgAgentKey(agent) {
    return agent.key || agent.statusKey || agent.agentId || agent.id || '';
}

function _mtgNormalizeBranchToken(value) {
    return String(value || '').trim().toLowerCase();
}

function _mtgParticipantBranchId(agent) {
    var rawBranch = (agent && agent.branch) || '';
    var normalized = _mtgNormalizeBranchToken(rawBranch);
    var branches = getBranchList();
    var matched = branches.find(function(b) {
        return b.id === rawBranch ||
            _mtgNormalizeBranchToken(b.id) === normalized ||
            _mtgNormalizeBranchToken(b.name) === normalized;
    });
    if (matched) return matched.id;
    var unassignedNames = [
        'unassigned',
        _mtgT('branch_unassigned', 'Unassigned')
    ].map(_mtgNormalizeBranchToken);
    if (!normalized || unassignedNames.indexOf(normalized) >= 0) return 'UNASSIGNED';
    if (agent && agent.providerKind) {
        var providerMatched = branches.find(function(b) {
            return _mtgNormalizeBranchToken(b.name) === _mtgNormalizeBranchToken(agent.providerKind) ||
                _mtgNormalizeBranchToken(b.id) === _mtgNormalizeBranchToken(agent.providerKind);
        });
        if (providerMatched) return providerMatched.id;
    }
    return 'UNASSIGNED';
}

function _mtgBranchDisplayLabel(branch) {
    if (!branch) return _mtgT('branch_unassigned', 'Unassigned');
    var name = branch.id === 'UNASSIGNED' ? _mtgT('branch_unassigned', 'Unassigned') : (branch.name || branch.id);
    if (typeof name === 'string' && name.indexOf('branch_') === 0) name = _mtgT(name, branch.id || name);
    return (branch.emoji || '🏢') + ' ' + name;
}

function _mtgIsAssignableMeetingAgent(agent) {
    return !!(agent && agent.assignable !== false && agent.systemRole !== 'archive_manager' && !agent.archiveManager);
}

function _mtgMeetingAgents() {
    return (_mtgAgents || []).filter(_mtgIsAssignableMeetingAgent);
}

function _mtgAssignableParticipantSet() {
    return new Set(_mtgMeetingAgents().map(function(agent) { return _mtgAgentKey(agent); }));
}

function _mtgFilterAssignableParticipants(participants) {
    var allowed = _mtgAssignableParticipantSet();
    return (participants || []).filter(function(key) { return allowed.has(key); });
}

function _mtgParticipantSelectorHtml(opts) {
    opts = opts || {};
    var participantClass = opts.participantClass || '';
    var branchClass = opts.branchClass || '';
    var branchAttrs = opts.branchAttrs || '';
    var participantAttrs = opts.participantAttrs || '';
    var allowed = _mtgAssignableParticipantSet();
    var selected = new Set((opts.selected || []).map(function(item) { return String(item); }).filter(function(key) { return allowed.has(key); }));
    var byBranch = {};
    getBranchList().forEach(function(branch) { byBranch[branch.id] = []; });
    _mtgMeetingAgents().forEach(function(agent) {
        var branchId = _mtgParticipantBranchId(agent);
        if (!byBranch[branchId]) byBranch[branchId] = [];
        byBranch[branchId].push(agent);
    });
    var branchHtml = getBranchList().map(function(branch) {
        var branchAgents = byBranch[branch.id] || [];
        if (!branchAgents.length) return '';
        return '<label class="mtg-label" style="display:inline-flex;align-items:center;gap:4px;margin-right:10px;margin-top:4px;">' +
            '<input type="checkbox" class="' + _escMtg(branchClass) + '" data-branch-id="' + _escMtg(branch.id) + '"' + branchAttrs + '> ' +
            _escMtg(_mtgBranchDisplayLabel(branch)) +
            '</label>';
    }).join('');
    var agentHtml = getBranchList().map(function(branch) {
        var branchAgents = byBranch[branch.id] || [];
        if (!branchAgents.length) return '';
        var items = branchAgents.map(function(agent) {
            var key = _mtgAgentKey(agent);
            var checked = selected.has(key) ? ' checked' : '';
            return '<label class="mtg-label" style="display:inline-flex;align-items:center;gap:4px;margin-right:10px;margin-top:4px;">' +
                '<input type="checkbox" class="' + _escMtg(participantClass) + '" data-branch-id="' + _escMtg(branch.id) + '" value="' + _escMtg(key) + '"' + checked + participantAttrs + '> ' +
                _escMtg((agent.emoji || '🤖') + ' ' + (agent.name || key)) +
                '</label>';
        }).join('');
        return '<div class="mtg-participant-branch-group" data-branch-id="' + _escMtg(branch.id) + '" style="margin-top:6px;">' +
            '<div class="mtg-section-text" style="font-size:10px;color:#aaa;">' + _escMtg(_mtgBranchDisplayLabel(branch)) + '</div>' +
            '<div>' + items + '</div>' +
            '</div>';
    }).join('');
    return '<div class="mtg-participant-selector">' +
        '<div class="mtg-section-text" style="font-size:10px;color:#aaa;margin:2px 0 4px;">' + _escMtg(_mtgT('meeting_branch_quick_select', 'Quick select by branch')) + '</div>' +
        '<div class="mtg-branch-selectors">' + branchHtml + '</div>' +
        '<div class="mtg-section-text" style="font-size:10px;color:#777;margin-top:4px;">' + _escMtg(_mtgT('meeting_branch_quick_select_hint', 'Choose a branch, then manually adjust individual agents.')) + '</div>' +
        '<div class="mtg-agent-selectors" style="margin-top:6px;">' + agentHtml + '</div>' +
        '</div>';
}

function _mtgSelectedParticipantValues(selector) {
    return Array.prototype.slice.call(document.querySelectorAll(selector + ':checked')).map(function(el) { return el.value; });
}

function _mtgApplyBranchSelection(branchSelector, participantSelector, branchId, checked) {
    Array.prototype.slice.call(document.querySelectorAll(participantSelector + '[data-branch-id="' + branchId + '"]')).forEach(function(el) {
        el.checked = checked;
    });
}

function _mtgSyncBranchSelectionState(branchSelector, participantSelector) {
    Array.prototype.slice.call(document.querySelectorAll(branchSelector)).forEach(function(branchEl) {
        var branchId = branchEl.getAttribute('data-branch-id') || '';
        var items = Array.prototype.slice.call(document.querySelectorAll(participantSelector + '[data-branch-id="' + branchId + '"]'));
        var checkedCount = items.filter(function(el) { return el.checked; }).length;
        branchEl.checked = items.length > 0 && checkedCount === items.length;
        branchEl.indeterminate = checkedCount > 0 && checkedCount < items.length;
    });
}

function _mtgUpdateModeratorOptions(selectId, participantSelector, preferredModerator) {
    var select = document.getElementById(selectId);
    if (!select) return;
    var previous = select.value || preferredModerator || '';
    var selected = _mtgSelectedParticipantValues(participantSelector);
    var selectedSet = new Set(selected);
    var target = selectedSet.has(previous) ? previous : (selected[0] || '');
    select.innerHTML = selected.map(function(key) {
        var info = _mtgAgentMap[key] || { name: key, emoji: '🤖' };
        return '<option value="' + _escMtg(key) + '"' + (key === target ? ' selected' : '') + '>' + _escMtg((info.emoji || '🤖') + ' ' + (info.name || key)) + '</option>';
    }).join('');
    if (target) select.value = target;
}

function toggleNewMeetingForm(forceOpen) {
    var modal = document.getElementById('newMeetingModal');
    var panel = document.getElementById('new-meeting-panel');
    if (!modal || !panel) return;
    var shouldOpen = typeof forceOpen === 'boolean' ? forceOpen : modal.classList.contains('hidden');
    modal.classList.toggle('modal-above-projects', shouldOpen);
    modal.classList.toggle('hidden', !shouldOpen);
    if (shouldOpen) {
        renderNewMeetingForm();
        var title = document.getElementById('new-meeting-modal-title');
        if (title) title.textContent = _mtgT('new_meeting', 'New Meeting');
        setTimeout(function() {
            var topic = document.getElementById('new-mtg-topic');
            if (topic) topic.focus();
        }, 0);
    } else {
        panel.innerHTML = '';
        modal.classList.remove('modal-above-projects');
    }
}

function renderNewMeetingForm() {
    var panel = document.getElementById('new-meeting-panel');
    if (!panel) return;
    var agentOptions = _mtgParticipantSelectorHtml({
        selected: [],
        participantClass: 'new-mtg-participant',
        branchClass: 'new-mtg-branch',
        participantAttrs: ' onchange="updateNewMeetingModeratorOptions()"',
        branchAttrs: ' onchange="toggleNewMeetingBranch(this)"'
    });
    panel.innerHTML =
        '<div class="mtg-section-title">' + _escMtg(_mtgT('new_meeting', 'New Meeting')) + '</div>' +
        '<label class="mtg-label">' + _escMtg(_mtgT('meeting_topic', 'Topic')) + '</label>' +
        '<input id="new-mtg-topic" class="skl-input" type="text" placeholder="' + _escMtg(_mtgT('meeting_topic_placeholder', 'What should the agents discuss?')) + '">' +
        '<label class="mtg-label">' + _escMtg(_mtgT('meeting_purpose', 'Purpose')) + '</label>' +
        '<input id="new-mtg-purpose" class="skl-input" type="text" placeholder="' + _escMtg(_mtgT('meeting_purpose_placeholder', 'What result should this meeting produce?')) + '">' +
        '<label class="mtg-label">' + _escMtg(_mtgT('meeting_type', 'Meeting type')) + '</label>' +
        '<select id="new-mtg-type" class="skl-input"><option value="information">' + _escMtg(_mtgT('meeting_type_information', 'Information gathering')) + '</option><option value="discussion" selected>' + _escMtg(_mtgT('meeting_type_discussion', 'Decision discussion')) + '</option><option value="task">' + _escMtg(_mtgT('meeting_type_task', 'Task collaboration')) + '</option></select>' +
        '<label class="mtg-label">' + _escMtg(_mtgT('meeting_project', 'Project')) + '</label>' +
        _mtgProjectSelectHtml('new-mtg-project', '', true) +
        '<label class="mtg-label">' + _escMtg(_mtgT('meeting_participants', 'Participants')) + '</label>' +
        '<div id="new-mtg-participants">' + agentOptions + '</div>' +
        '<label class="mtg-label">' + _escMtg(_mtgT('meeting_moderator', 'Moderator')) + '</label>' +
        '<select id="new-mtg-moderator" class="skl-input"></select>' +
        '<label class="mtg-label">' + _escMtg(_mtgT('meeting_context_mode', 'Context mode')) + '</label>' +
        '<select id="new-mtg-context-mode" class="skl-input"><option value="incremental" selected>' + _escMtg(_mtgT('meeting_context_incremental', 'Incremental')) + '</option><option value="summary">' + _escMtg(_mtgT('meeting_context_summary', 'Summary')) + '</option><option value="full">' + _escMtg(_mtgT('meeting_context_full', 'Full')) + '</option></select>' +
        '<label class="mtg-label">' + _escMtg(_mtgT('meeting_resolution_policy', 'Resolution policy')) + '</label>' +
        '<select id="new-mtg-resolution-policy" class="skl-input"><option value="user_decision" selected>' + _escMtg(_mtgT('meeting_resolution_user_decision', 'User decides disagreements')) + '</option><option value="moderator_decision">' + _escMtg(_mtgT('meeting_resolution_moderator_decision', 'Moderator decides and closes')) + '</option></select>' +
        '<label class="mtg-label">' + _escMtg(_mtgT('meeting_max_rounds', 'Max discussion rounds')) + '</label>' +
        '<input id="new-mtg-max-rounds" class="skl-input" type="number" min="1" max="5" value="1">' +
        '<label class="mtg-label">' + _escMtg(_mtgT('meeting_initial_context', 'Initial context')) + '</label>' +
        '<textarea id="new-mtg-context" class="mtg-textarea" rows="4" placeholder="' + _escMtg(_mtgT('meeting_initial_context_placeholder', 'User-confirmed context for all agents')) + '"></textarea>' +
        '<div id="new-mtg-error" style="color:#e74c3c;font-size:10px;margin:6px 0;display:none;"></div>' +
        '<button id="new-mtg-submit" class="mtg-btn mtg-btn-end" onclick="submitNewMeeting()">▶ ' + _escMtg(_mtgT('meeting_start', 'Start meeting')) + '</button>' +
        '<button class="mtg-btn" onclick="toggleNewMeetingForm(false)">' + _escMtg(_mtgT('cancel', 'Cancel')) + '</button>';
    updateNewMeetingModeratorOptions();
}

function toggleNewMeetingBranch(branchEl) {
    var branchId = branchEl.getAttribute('data-branch-id') || '';
    _mtgApplyBranchSelection('.new-mtg-branch', '.new-mtg-participant', branchId, branchEl.checked);
    updateNewMeetingModeratorOptions();
}

function updateNewMeetingModeratorOptions() {
    _mtgSyncBranchSelectionState('.new-mtg-branch', '.new-mtg-participant');
    _mtgUpdateModeratorOptions('new-mtg-moderator', '.new-mtg-participant', '');
}

async function submitNewMeeting() {
    var err = document.getElementById('new-mtg-error');
    var btn = document.getElementById('new-mtg-submit');
    function fail(msg) {
        if (err) { err.textContent = msg; err.style.display = 'block'; }
    }
    var participants = _mtgFilterAssignableParticipants(Array.prototype.slice.call(document.querySelectorAll('.new-mtg-participant:checked')).map(function(el) { return el.value; }));
    var topic = (document.getElementById('new-mtg-topic') || {}).value || '';
    var moderator = (document.getElementById('new-mtg-moderator') || {}).value || '';
    if (!topic.trim()) return fail(_mtgT('meeting_error_topic_required', 'Topic is required.'));
    if (participants.length < 2) return fail(_mtgT('meeting_error_participants_required', 'Select at least two participants.'));
    if (!moderator) return fail(_mtgT('meeting_error_moderator_required', 'Select a moderator.'));
    if (btn) { btn.disabled = true; btn.textContent = _mtgT('meeting_running', 'Running...'); }
    if (err) err.style.display = 'none';
    try {
        var createRes = await fetch('/api/meetings/executable/create', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                topic: topic.trim(),
                purpose: ((document.getElementById('new-mtg-purpose') || {}).value || '').trim(),
                meetingType: (document.getElementById('new-mtg-type') || {}).value || 'discussion',
                projectId: (document.getElementById('new-mtg-project') || {}).value || '',
                participants: participants,
                moderator: moderator,
                contextMode: (document.getElementById('new-mtg-context-mode') || {}).value || 'incremental',
                resolutionPolicy: (document.getElementById('new-mtg-resolution-policy') || {}).value || 'user_decision',
                maxRounds: Number((document.getElementById('new-mtg-max-rounds') || {}).value || 1),
                context: ((document.getElementById('new-mtg-context') || {}).value || '').trim(),
                allowConflicts: true,
                idempotencyKey: 'ui-' + Date.now() + '-' + Math.random().toString(16).slice(2)
            })
        });
        var created = await createRes.json();
        if (!createRes.ok || created.error) throw new Error(created.error || 'Failed to create meeting');
        if (created.meeting && created.meeting.stage === 'conflict') {
            toggleNewMeetingForm(false);
            await _mtgAfterMeetingRefresh();
            switchMtgTab('active');
            openMeetingDetailModal(created.meeting.id);
            return;
        }
        var ran = await _mtgRunMeeting(created.meeting.id);
        toggleNewMeetingForm(false);
        await _mtgAfterMeetingRefresh();
        switchMtgTab(_mtgMeetingCompleted(ran && ran.meeting) ? 'completed' : 'active');
    } catch (e) {
        fail(e.message || String(e));
    } finally {
        if (btn) { btn.disabled = false; btn.textContent = '▶ ' + _mtgT('meeting_start', 'Start meeting'); }
    }
}

function _mtgActionText(action) {
    if (!action) return '';
    if (typeof action === 'string') return action;
    if (typeof action === 'object') {
        var owner = action.owner || action.agent || action.assignee || '';
        var item = action.item || action.text || action.task || action.action || action.summary || '';
        if (owner && item) return owner + ': ' + item;
        if (item) return item;
        if (owner) return owner;
        try { return JSON.stringify(action); } catch (e) { return String(action); }
    }
    return String(action);
}

function mtgExpandAll() {
    (_mtgData.active || []).concat(_mtgData.history || []).forEach(function(m) { if (m.id) _mtgOpenCards[m.id] = true; });
    document.querySelectorAll('.mtg-card-body').forEach(function(el) { el.classList.add('open'); });
    document.querySelectorAll('.mtg-card-toggle').forEach(function(el) { el.classList.add('open'); });
}

function mtgCollapseAll() {
    (_mtgData.active || []).concat(_mtgData.history || []).forEach(function(m) { if (m.id) delete _mtgOpenCards[m.id]; });
    document.querySelectorAll('.mtg-card-body').forEach(function(el) { el.classList.remove('open'); });
    document.querySelectorAll('.mtg-card-toggle').forEach(function(el) { el.classList.remove('open'); });
}

function toggleMtgCard(meetingId) {
    var body = document.getElementById('mtg-body-' + meetingId);
    var toggle = document.getElementById('mtg-toggle-' + meetingId);
    if (body) {
        body.classList.toggle('open');
        _mtgOpenCards[meetingId] = body.classList.contains('open');
        if (toggle) toggle.classList.toggle('open');
    }
}

function toggleMtgResponse(respId, btn) {
    var el = document.getElementById(respId);
    if (!el) return;
    el.classList.toggle('expanded');
    if (el.classList.contains('expanded')) {
        btn.textContent = _tr('collapse');
    } else {
        btn.textContent = _tr('expand');
    }
}

function toggleMtgParticipants(id, btn) {
    var extra = document.getElementById('mtg-participants-extra-' + id);
    if (!extra || !btn) return;
    var expanded = extra.classList.toggle('open');
    btn.dataset.expanded = expanded ? '1' : '0';
    btn.textContent = expanded ? _tr('collapse') : ('查看全部 ' + String(btn.dataset.total || ''));
}

function _mtgFindMeeting(meetingId) {
    return (_mtgData.active || []).concat(_mtgData.history || []).find(function(m) {
        return m && m.id === meetingId;
    });
}

function _mtgFindMeetingByRequestId(requestId) {
    if (!requestId) return null;
    return (_mtgData.active || []).concat(_mtgData.history || []).find(function(m) {
        var source = (m && m.source) || {};
        return source.meetingRequestId === requestId;
    }) || null;
}

function _mtgMeetingIdFromRequest(req) {
    if (!req) return '';
    var conversion = req.conversion && typeof req.conversion === 'object' ? req.conversion : {};
    var taskBlocker = req.taskBlocker && typeof req.taskBlocker === 'object' ? req.taskBlocker : {};
    return String(conversion.meetingId || taskBlocker.meetingId || '').trim();
}

function _mtgUpsertRequest(req) {
    if (!req || !req.id) return null;
    var requests = Array.isArray(_mtgData.requests) ? _mtgData.requests : [];
    var idx = requests.findIndex(function(item) { return item && item.id === req.id; });
    if (idx >= 0) requests[idx] = req;
    else requests.unshift(req);
    _mtgData.requests = _mtgSortRequestsByStatusThenTime(requests);
    return req;
}

async function _mtgFetchRequestDetail(requestId) {
    if (!requestId) return null;
    try {
        var res = await fetch('/api/meetings/requests/' + encodeURIComponent(requestId));
        var data = await res.json();
        if (!res.ok || data.error || !data.request) return null;
        return _mtgUpsertRequest(data.request);
    } catch (e) {
        console.warn('[meetings] request detail fetch error:', e);
        return null;
    }
}

function openMeetingDetailModal(meetingId) {
    var meeting = _mtgFindMeeting(meetingId);
    if (meeting) {
        openMeetingDetailRecord(meeting, meetingId);
        return;
    }
    openMeetingDetailPlaceholder(meetingId, _mtgT('loading', 'Loading...'));
    _mtgFetchMeetingDetail(meetingId);
}

function openMeetingDetailRecord(meeting, fallbackMeetingId) {
    var modal = document.getElementById('meetingDetailModal');
    var body = document.getElementById('meeting-detail-body');
    var title = document.getElementById('meeting-detail-title');
    if (!meeting || !modal || !body) return;
    _mtgDetailMeetingId = meeting.id || fallbackMeetingId || '';
    if (title) title.textContent = meeting.topic || _tr('untitled_meeting');
    body.innerHTML = _mtgRenderMeetingDetail(_mtgMergeLiveMeeting(meeting));
    modal.classList.remove('hidden');
}

function openMeetingDetailPlaceholder(meetingId, message) {
    var modal = document.getElementById('meetingDetailModal');
    var body = document.getElementById('meeting-detail-body');
    var title = document.getElementById('meeting-detail-title');
    if (!meetingId || !modal || !body) return;
    _mtgDetailMeetingId = meetingId;
    if (title) title.textContent = _mtgT('meeting_detail_title', 'Meeting Detail');
    body.innerHTML = '<div class="mtg-empty">' + _escMtg(message || '') + '</div>';
    modal.classList.remove('hidden');
}

async function _mtgFetchMeetingDetail(meetingId) {
    if (!meetingId) return;
    try {
        var res = await fetch('/api/meetings/executable/' + encodeURIComponent(meetingId));
        var data = await res.json();
        if (!res.ok || data.error || !data.meeting) {
            throw new Error(data.error || _mtgT('meeting_not_found', 'Meeting not found'));
        }
        if (Array.isArray(data.events)) {
            _mtgLiveEvents[meetingId] = _mtgLiveStateFromMeeting(data.meeting);
            data.events.forEach(function(event) { _mtgApplyLiveEvent(meetingId, event); });
        }
        openMeetingDetailRecord(data.meeting, meetingId);
    } catch (e) {
        var body = document.getElementById('meeting-detail-body');
        if (_mtgDetailMeetingId === meetingId && body) {
            body.innerHTML = '<div class="mtg-inline-error" style="display:block">' + _escMtg(e.message || String(e)) + '</div>';
        }
    }
}

function closeMeetingDetailModal() {
    var modal = document.getElementById('meetingDetailModal');
    var body = document.getElementById('meeting-detail-body');
    _mtgDetailMeetingId = '';
    if (modal) modal.classList.add('hidden');
    if (body) body.innerHTML = '';
}

function _mtgRefreshDetailModal() {
    var modal = document.getElementById('meetingDetailModal');
    var body = document.getElementById('meeting-detail-body');
    var title = document.getElementById('meeting-detail-title');
    if (!modal || modal.classList.contains('hidden') || !body || !_mtgDetailMeetingId) return;
    var meeting = _mtgFindMeeting(_mtgDetailMeetingId);
    if (!meeting) {
        closeMeetingDetailModal();
        return;
    }
    meeting = _mtgMergeLiveMeeting(meeting);
    if (title) title.textContent = meeting.topic || _tr('untitled_meeting');
    body.innerHTML = _mtgRenderMeetingDetail(meeting);
}

async function _mtgAfterMeetingRefresh() {
    await _mtgRefresh();
    _mtgRefreshDetailModal();
}

function _mtgRenderMeetingDetail(m) {
    var participants = m.participants || m.agents || [];
    var isActive = m.status === 'active';
    var html = '';
    if (m.purpose && m.purpose !== m.topic) {
        html += '<div class="mtg-card-purpose mtg-detail-purpose">' + _escMtg(m.purpose) + '</div>';
    }
    var orgInfo = _mtgAgentMap[m.organizer] || { emoji: '🤖', name: m.organizer || 'Unknown' };
    var leftMeta = [
        '👑 ' + orgInfo.emoji + ' ' + _escMtg(orgInfo.name),
        '🪪 ' + _escMtg(_mtgCreatedByLabel(m)),
        '👥 ' + _escMtg(_tr('participants_count', { count: participants.length }))
    ];
    var rightMeta = [];
    if (m.executableMeeting) {
        rightMeta.push('⚙️ ' + _escMtg(_mtgT('meeting_stage', 'Stage')) + ': ' + _escMtg(_mtgMeetingStageLabel(m.executionStage || m.status || '')));
        if (m.maxRounds) rightMeta.push('🔢 ' + _escMtg(_mtgT('meeting_max_rounds', 'Max discussion rounds')) + ': ' + _escMtg(m.maxRounds));
        if (m.id) rightMeta.push('🆔 ' + _escMtg(_mtgT('meeting_id', 'Meeting ID')) + ': ' + _escMtg(m.id));
        if (m.moderator) rightMeta.push('🎙️ ' + _escMtg(_mtgT('meeting_moderator', 'Moderator')) + ': ' + _escMtg(m.moderator));
        if (m.contextMode) rightMeta.push('🧩 ' + _escMtg(_mtgT('meeting_context_mode', 'Context')) + ': ' + _escMtg(m.contextMode));
        if (m.resolutionPolicy) rightMeta.push('⚖️ ' + _escMtg(_mtgT('meeting_resolution_policy', 'Resolution policy')) + ': ' + _escMtg(_mtgResolutionPolicyLabel(m.resolutionPolicy)));
        var preparingTimeoutLabel = _mtgPreparingTimeoutLabel(m);
        if (preparingTimeoutLabel) rightMeta.push('⏱️ ' + _escMtg(preparingTimeoutLabel));
        if (m.urgency) rightMeta.push('🚦 ' + _escMtg(_mtgUrgencyLabel(m.urgency)));
        rightMeta.push(_mtgProjectMetaLabel(m));
    }
    var ts = _mtgMeetingTime(m);
    if (ts) rightMeta.push('🕐 ' + new Date(ts).toLocaleString());
    html += _mtgRenderMetaColumns(leftMeta, rightMeta);

    html += _mtgRenderParticipants(participants, m, {
        id: 'detail-' + m.id,
        limit: 3
    });

    html += _mtgRenderResultSummary(m);
    html += _mtgRenderActionItemDrafts(m);

    if (isActive && m.executableMeeting) {
        if ((m.executionStage || '') === 'conflict' || (Array.isArray(m.conflicts) && m.conflicts.length)) {
            html += _mtgRenderConflictPanel(m);
        }
        if ((m.executionStage || '') === 'awaiting_user_decision') {
            html += _mtgRenderDecisionWindowControls(m);
        }
        if (m.moderatorFailure && m.moderatorFailure.reason === 'moderator_failed') {
            html += _mtgRenderModeratorTakeoverControls(m);
        }
        html += _mtgRenderInterventionForm(m);
    }

    if (m.executableMeeting && ((Array.isArray(m.transcript) && m.transcript.length) || (Array.isArray(m.pendingCalls) && m.pendingCalls.length))) {
        html += _mtgRenderTranscript(m);
    }

    var responses = m.responses || {};
    if (Object.keys(responses).length > 0) {
        html += '<div class="mtg-section"><div class="mtg-section-title">' + _escMtg(_tr('agent_responses')) + '</div><div class="mtg-responses">';
        participants.forEach(function(pKey) {
            var info = _mtgAgentMap[pKey] || { emoji: '🤖', name: pKey, role: '' };
            var resp = responses[pKey] || '';
            html += '<div class="mtg-response"><div class="mtg-response-header"><span class="mtg-response-emoji">' + info.emoji + '</span><span class="mtg-response-name">' + _escMtg(info.name) + '</span></div>';
            html += '<div class="mtg-response-text expanded">' + _escMtg(resp || _tr('no_response_recorded')) + '</div></div>';
        });
        html += '</div></div>';
    }

    if (m.executableMeeting && m.result && m.result.contributions) {
        html += '<div class="mtg-section"><div class="mtg-section-title">' + _escMtg(_mtgT('meeting_contributions', 'Contributions')) + '</div>';
        Object.keys(m.result.contributions).forEach(function(agentId) {
            var info = _mtgAgentMap[agentId] || { emoji: '🤖', name: agentId };
            html += '<div class="mtg-response"><div class="mtg-response-header"><span class="mtg-response-emoji">' + info.emoji + '</span><span class="mtg-response-name">' + _escMtg(info.name) + '</span></div>';
            html += '<div class="mtg-response-text expanded">' + _mtgRenderContributionText(m.result.contributions[agentId] || '') + '</div></div>';
        });
        html += '</div>';
    }

    if (m.endedBy) {
        var endInfo = _mtgAgentMap[m.endedBy] || { emoji: '🤖', name: m.endedBy };
        html += '<div class="mtg-section"><div class="mtg-section-title">' + _escMtg(_tr('ended_by')) + '</div><div class="mtg-section-text">' + endInfo.emoji + ' ' + _escMtg(endInfo.name) + '</div></div>';
    }
    if (isActive) {
        html += '<div class="mtg-actions-bar mtg-detail-actions">';
        if (m.executableMeeting) {
            var stage = m.executionStage || '';
            if (stage === 'preparing') {
                html += '<button id="mtg-start-' + _escMtg(m.id) + '" class="mtg-btn mtg-btn-end" onclick="startExecutableMeeting(\'' + _escMtg(m.id) + '\')">▶ ' + _escMtg(_mtgT('meeting_start_existing', 'Start meeting')) + '</button>';
            } else if (stage === 'conflict') {
                html += '<button id="mtg-refresh-conflict-' + _escMtg(m.id) + '" class="mtg-btn" onclick="refreshMeetingConflicts(\'' + _escMtg(m.id) + '\')">' + _escMtg(_mtgT('meeting_conflict_refresh', 'Recheck conflicts')) + '</button>';
            } else if (stage === 'paused') {
                html += '<button id="mtg-resume-' + _escMtg(m.id) + '" class="mtg-btn mtg-btn-end" onclick="resumeExecutableMeeting(\'' + _escMtg(m.id) + '\')">▶ ' + _escMtg(_mtgT('meeting_resume', 'Resume')) + '</button>';
            } else {
                html += '<button id="mtg-pause-' + _escMtg(m.id) + '" class="mtg-btn" onclick="pauseExecutableMeeting(\'' + _escMtg(m.id) + '\')">⏸ ' + _escMtg(_mtgT('meeting_pause', 'Pause')) + '</button>';
                html += '<button id="mtg-ai-end-' + _escMtg(m.id) + '" class="mtg-btn mtg-btn-end" onclick="endExecutableMeetingWithAI(\'' + _escMtg(m.id) + '\')">✅ ' + _escMtg(_mtgT('meeting_ai_end', 'Ask moderator to end')) + '</button>';
            }
            html += '<button id="mtg-cancel-' + _escMtg(m.id) + '" class="mtg-btn mtg-btn-delete" onclick="cancelExecutableMeeting(\'' + _escMtg(m.id) + '\')">✕ ' + _escMtg(_mtgT('meeting_cancel', 'Cancel')) + '</button>';
        } else {
            html += '<button class="mtg-btn mtg-btn-end" onclick="openEndMeetingForm(\'' + _escMtg(m.id) + '\')">✅ ' + _escMtg(_tr('end_meeting')) + '</button>';
        }
        html += '</div>';
    }
    return html;
}

function _mtgActionStatusLabel(status) {
    var map = {
        draft: 'meeting_action_status_draft',
        confirmed: 'meeting_action_status_confirmed',
        rejected: 'meeting_action_status_rejected',
        kept_as_meeting_item: 'meeting_action_status_kept'
    };
    return _mtgT(map[status] || 'meeting_action_status_draft', status || 'draft');
}

function _mtgRenderActionItemDrafts(m) {
    var drafts = Array.isArray(m.actionItemDrafts) ? m.actionItemDrafts : [];
    if (!drafts.length && m.result && Array.isArray(m.result.actionItems) && m.result.actionItems.length) {
        drafts = m.result.actionItems.map(function(item, idx) {
            return { id: 'ai-' + (idx + 1), title: _mtgActionText(item), status: 'draft', targetProjectId: m.projectId || '' };
        });
    }
    if (!drafts.length) return '';
    var html = '<div class="mtg-section mtg-action-drafts"><div class="mtg-section-title">' + _escMtg(_mtgT('meeting_action_drafts', 'Action item drafts')) + '</div>';
    html += '<div class="mtg-section-text">' + _escMtg(_mtgT('meeting_action_drafts_hint', 'Confirming adds the item to the source task. Drafts do not execute automatically.')) + '</div>';
    drafts.forEach(function(d) {
        var id = _escMtg(d.id || '');
        var formId = 'mtg-action-form-' + _escMtg(m.id) + '-' + id;
        var projectSelectId = 'mtg-action-project-' + _escMtg(m.id) + '-' + id;
        html += '<div class="mtg-action-draft" data-action-item-id="' + id + '">';
        html += '<div class="mtg-action-draft-title">' + _escMtg(d.title || _mtgT('meeting_action_untitled', 'Untitled action item')) + '</div>';
        if (d.description || d.sourceText) html += '<div class="mtg-section-text">' + _escMtg(d.description || d.sourceText || '') + '</div>';
        html += '<div class="mtg-action-draft-row">';
        html += '<span class="mtg-badge mtg-badge-kind">' + _escMtg(_mtgActionStatusLabel(d.status)) + '</span>';
        html += '<span class="mtg-action-draft-meta">' + _escMtg(_mtgT('meeting_action_owner', 'Owner')) + ': ' + _escMtg(d.assignee || d.suggestedOwner || _mtgT('meeting_unknown', 'unknown')) + ' · ' + _escMtg(_mtgT('meeting_project', 'Project')) + ': ' + _escMtg(_mtgProjectName(d.targetProjectId || m.projectId) || _mtgT('meeting_project_none', 'No project')) + '</span>';
        if (d.status === 'confirmed' && d.taskId) {
            html += '<div class="mtg-action-draft-actions"><button class="mtg-btn mtg-btn-end" onclick="openMeetingTaskLink(\'' + _escMtg(d.targetProjectId || m.projectId) + '\',\'' + _escMtg(d.sourceTaskId || d.taskId) + '\')">' + _escMtg(_mtgT('meeting_action_open_task', 'Open source task')) + '</button></div>';
        } else if (d.status !== 'rejected' && d.status !== 'kept_as_meeting_item') {
            html += '<div class="mtg-action-draft-actions">';
            html += '<button class="mtg-btn" onclick="toggleMeetingActionItemEditor(\'' + _escMtg(m.id) + '\',\'' + id + '\')">' + _escMtg(_mtgT('meeting_action_edit', 'Edit')) + '</button>';
            html += '<button class="mtg-btn mtg-btn-end" onclick="confirmMeetingActionItem(\'' + _escMtg(m.id) + '\',\'' + id + '\')">' + _escMtg(_mtgT('meeting_action_confirm_task', 'Add to source task')) + '</button>';
            html += '<button class="mtg-btn" onclick="keepMeetingActionItem(\'' + _escMtg(m.id) + '\',\'' + id + '\')">' + _escMtg(_mtgT('meeting_action_keep', 'Keep only')) + '</button>';
            html += '<button class="mtg-btn mtg-btn-delete" onclick="rejectMeetingActionItem(\'' + _escMtg(m.id) + '\',\'' + id + '\')">' + _escMtg(_mtgT('meeting_action_reject', 'Reject')) + '</button>';
            html += '</div>';
            html += '<div id="' + formId + '" class="mtg-action-form hidden">';
            html += '<div class="mtg-field"><label class="mtg-label">' + _escMtg(_mtgT('meeting_action_title', 'Task title')) + '</label>';
            html += '<input id="mtg-action-title-' + _escMtg(m.id) + '-' + id + '" class="skl-input" type="text" value="' + _escMtg(d.title || '') + '">';
            html += '</div>';
            html += '<div class="mtg-field"><label class="mtg-label">' + _escMtg(_mtgT('meeting_action_description', 'Description')) + '</label>';
            html += '<textarea id="mtg-action-desc-' + _escMtg(m.id) + '-' + id + '" class="mtg-textarea" rows="3">' + _escMtg(d.description || '') + '</textarea>';
            html += '</div>';
            html += '<div class="mtg-field"><label class="mtg-label">' + _escMtg(_mtgT('meeting_project', 'Project')) + '</label>';
            html += _mtgProjectSelectHtml(projectSelectId, d.targetProjectId || m.projectId || '', true);
            html += '</div>';
            html += '<div id="mtg-action-error-' + _escMtg(m.id) + '-' + id + '" class="mtg-inline-error"></div>';
            html += '<div class="mtg-actions-bar">';
            html += '<button class="mtg-btn" onclick="updateMeetingActionItem(\'' + _escMtg(m.id) + '\',\'' + id + '\')">' + _escMtg(_mtgT('meeting_action_save_draft', 'Save draft')) + '</button>';
            html += '</div>';
            html += '</div>';
        }
        html += '</div></div>';
    });
    html += '</div>';
    return html;
}

function toggleMeetingActionItemEditor(meetingId, actionItemId) {
    var form = document.getElementById('mtg-action-form-' + meetingId + '-' + actionItemId);
    if (form) form.classList.toggle('hidden');
}

function _mtgActionInput(meetingId, actionItemId, suffix) {
    return document.getElementById('mtg-action-' + suffix + '-' + meetingId + '-' + actionItemId);
}

function _mtgActionError(meetingId, actionItemId, msg) {
    var el = document.getElementById('mtg-action-error-' + meetingId + '-' + actionItemId);
    if (el) {
        el.textContent = msg || '';
        el.style.display = msg ? 'block' : 'none';
    }
}

async function _mtgActionItemRequest(meetingId, actionItemId, body) {
    var res = await fetch('/api/meetings/executable/' + encodeURIComponent(meetingId) + '/action-items/' + encodeURIComponent(actionItemId), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(Object.assign({ idempotencyKey: body.action + '-' + Date.now() + '-' + Math.random().toString(16).slice(2) }, body))
    });
    var data = await res.json();
    if (!res.ok || data.error) throw new Error(data.error || 'Action item update failed');
    await _mtgAfterMeetingRefresh();
    return data;
}

async function updateMeetingActionItem(meetingId, actionItemId) {
    try {
        await _mtgActionItemRequest(meetingId, actionItemId, {
            action: 'update',
            title: (_mtgActionInput(meetingId, actionItemId, 'title') || {}).value || '',
            description: (_mtgActionInput(meetingId, actionItemId, 'desc') || {}).value || '',
            targetProjectId: (_mtgActionInput(meetingId, actionItemId, 'project') || {}).value || ''
        });
    } catch (e) {
        _mtgActionError(meetingId, actionItemId, e.message || String(e));
    }
}

async function confirmMeetingActionItem(meetingId, actionItemId) {
    try {
        await _mtgActionItemRequest(meetingId, actionItemId, {
            action: 'confirm',
            title: (_mtgActionInput(meetingId, actionItemId, 'title') || {}).value || '',
            description: (_mtgActionInput(meetingId, actionItemId, 'desc') || {}).value || '',
            targetProjectId: (_mtgActionInput(meetingId, actionItemId, 'project') || {}).value || ''
        });
    } catch (e) {
        _mtgActionError(meetingId, actionItemId, e.message || String(e));
    }
}

async function keepMeetingActionItem(meetingId, actionItemId) {
    try {
        await _mtgActionItemRequest(meetingId, actionItemId, { action: 'keep' });
    } catch (e) {
        _mtgActionError(meetingId, actionItemId, e.message || String(e));
    }
}

async function rejectMeetingActionItem(meetingId, actionItemId) {
    try {
        await _mtgActionItemRequest(meetingId, actionItemId, { action: 'reject', reason: _mtgT('meeting_action_rejected_by_user', 'Rejected by user') });
    } catch (e) {
        _mtgActionError(meetingId, actionItemId, e.message || String(e));
    }
}

function openMeetingTaskLink(projectId, taskId) {
    if (!projectId || !taskId) return;
    window.location.hash = '#projects';
    window.dispatchEvent(new CustomEvent('vo-open-project-task', { detail: { projectId: projectId, taskId: taskId } }));
    alert(_mtgT('meeting_action_task_created', 'Task created') + ': ' + taskId);
}

function _mtgRenderConflictPanel(m) {
    var conflicts = Array.isArray(m.conflicts) ? m.conflicts.filter(function(c) { return c && ['open', 'waiting', 'reserved'].indexOf(c.status || 'open') >= 0; }) : [];
    if (!conflicts.length && !(m.reservation && Object.keys(m.reservation).length)) return '';
    var html = '<div class="mtg-section mtg-conflict-panel"><div class="mtg-section-title">' + _escMtg(_mtgT('meeting_conflicts', 'Participant conflicts')) + '</div>';
    conflicts.forEach(function(c) {
        var info = _mtgAgentMap[c.agentId] || { emoji: '🤖', name: c.agentId || 'Agent' };
        var advisory = c.advisory || {};
        html += '<div class="mtg-conflict-card">';
        html += '<div class="mtg-conflict-head"><strong>' + _escMtg((info.emoji || '🤖') + ' ' + (info.name || c.agentId)) + '</strong><span class="mtg-badge mtg-badge-countdown">' + _escMtg(_mtgConflictLabel('risk', c.riskLevel || 'busy')) + '</span></div>';
        html += '<div class="mtg-section-text">' + _escMtg(_mtgConflictText(c.summary || c.reason || '')) + '</div>';
        html += '<div class="mtg-meta"><span>' + _escMtg(_mtgT('meeting_conflict_estimated', 'Availability')) + ': ' + _escMtg(_mtgConflictText(c.estimatedAvailability || 'unknown')) + '</span><span>' + _escMtg(_mtgT('meeting_pause_capability', 'Pause')) + ': ' + _escMtg(_mtgConflictLabel('pause', c.pauseCapability || 'logical')) + '</span></div>';
        if (advisory && advisory.status) {
            html += '<div class="mtg-result-summary mtg-conflict-advisory">';
            html += '<div class="mtg-result-label">' + _escMtg(_mtgT('meeting_advisory', 'Advisory recommendation')) + ': ' + _escMtg(_mtgConflictLabel('recommendation', advisory.recommendation || '')) + '</div>';
            if (advisory.interruptionRisk) html += '<div class="mtg-section-text">' + _escMtg(_mtgConflictText(advisory.interruptionRisk)) + '</div>';
            if (advisory.resumeNotes) html += '<div class="mtg-section-text">' + _escMtg(_mtgConflictText(advisory.resumeNotes)) + '</div>';
            if (advisory.source) html += '<div class="mtg-meta"><span>' + _escMtg(_mtgT('meeting_advisory_source', 'Source')) + ': ' + _escMtg(_mtgConflictLabel('advisory_source', advisory.source)) + '</span></div>';
            html += '</div>';
        }
        html += '<div class="mtg-actions-bar">';
        html += '<button class="mtg-btn" onclick="resolveMeetingConflict(\'' + _escMtg(m.id) + '\',\'' + _escMtg(c.agentId) + '\',\'wait\')">' + _escMtg(_mtgT('meeting_conflict_wait', 'Wait')) + '</button>';
        html += '<button class="mtg-btn" onclick="reserveMeetingConflict(\'' + _escMtg(m.id) + '\',\'' + _escMtg(c.agentId) + '\')">' + _escMtg(_mtgT('meeting_conflict_reserve', 'Try later')) + '</button>';
        html += '<button class="mtg-btn" onclick="replaceMeetingConflict(\'' + _escMtg(m.id) + '\',\'' + _escMtg(c.agentId) + '\')">' + _escMtg(_mtgT('meeting_conflict_replace', 'Replace')) + '</button>';
        html += '<button class="mtg-btn mtg-btn-delete" onclick="forceJoinMeetingConflict(\'' + _escMtg(m.id) + '\',\'' + _escMtg(c.agentId) + '\')">' + _escMtg(_mtgT('meeting_conflict_force', 'Force join')) + '</button>';
        html += '</div></div>';
    });
    if (m.reservation && Object.keys(m.reservation).length) {
        html += '<div class="mtg-section-text">' + _escMtg(_mtgT('meeting_reservation_notice', 'Reservations are reminders only; conflicts are rechecked before the meeting starts.')) + '</div>';
    }
    html += '</div>';
    return html;
}

function _mtgConflictLabel(kind, value) {
    var key = String(value || '').trim();
    if (!key) return '';
    var map = {
        risk: {
            high: 'meeting_conflict_risk_high',
            medium: 'meeting_conflict_risk_medium',
            low: 'meeting_conflict_risk_low',
            busy: 'meeting_conflict_risk_busy',
            idle: 'meeting_conflict_risk_idle'
        },
        pause: {
            unavailable: 'meeting_pause_unavailable',
            logical: 'meeting_pause_logical',
            none: 'meeting_pause_none',
            unknown: 'meeting_unknown'
        },
        recommendation: {
            wait: 'meeting_recommend_wait',
            reserve: 'meeting_recommend_reserve',
            replace: 'meeting_recommend_replace',
            force_join: 'meeting_recommend_force_join'
        },
        advisory_source: {
            agent_advisory_turn: 'meeting_advisory_source_agent',
            local_fallback: 'meeting_advisory_source_local',
            local_fallback_after_provider_failure: 'meeting_advisory_source_local_failed'
        }
    };
    var dict = map[kind] || {};
    return dict[key] ? _mtgT(dict[key], key) : key;
}

function _mtgConflictText(value) {
    var text = String(value || '').trim();
    if (!text) return '';
    var exact = {
        'unknown': 'meeting_unknown',
        'Idle': 'meeting_conflict_idle',
        'Provider call in progress': 'meeting_conflict_provider_call',
        'Agent is already in another active meeting. Do not force join unless the existing meeting is cancelled.': 'meeting_conflict_risk_meeting_occupied',
        'No original task can be resumed from this meeting conflict.': 'meeting_conflict_resume_none',
        'A provider call is in progress. Interrupting can lose an in-flight response.': 'meeting_conflict_risk_provider_call',
        'Wait for the provider call to finish, then retry conflict handling.': 'meeting_conflict_resume_provider_call',
        'The current task can only be logically paused; the provider process may not stop immediately.': 'meeting_conflict_risk_logical_pause',
        'Save current task context and resume from the recorded task state after the meeting.': 'meeting_conflict_resume_logical_pause',
        'Pause safety is uncertain.': 'meeting_conflict_risk_uncertain',
        'Recheck the agent state before forcing a meeting.': 'meeting_conflict_resume_recheck'
    };
    if (exact[text]) return _mtgT(exact[text], text);
    var prefix = 'Already in meeting: ';
    if (text.indexOf(prefix) === 0) {
        return _mtgT('meeting_conflict_already_in_meeting', 'Already in meeting: {topic}', { topic: text.slice(prefix.length) });
    }
    return text;
}

function openEndMeetingForm(meetingId) {
    document.getElementById('end-mtg-id').value = meetingId;
    document.getElementById('end-mtg-summary').value = '';
    document.getElementById('end-mtg-resolution').value = '';
    document.getElementById('end-mtg-actions').value = '';
    document.getElementById('end-mtg-error').style.display = 'none';

    // Build per-agent response fields
    var respSection = document.getElementById('end-mtg-responses-section');
    respSection.innerHTML = '';
    var meeting = _mtgData.active.find(function(m) { return m.id === meetingId; });
    if (meeting) {
        var participants = meeting.participants || meeting.agents || [];
        if (participants.length) {
            respSection.innerHTML = '<label class="mtg-label" style="margin-top:6px">' + _escMtg(_tr('agent_responses')) + '</label>';
            participants.forEach(function(pKey) {
                var info = _mtgAgentMap[pKey] || { emoji: '🤖', name: pKey };
                var div = document.createElement('div');
                div.style.cssText = 'margin-bottom:6px;';
                div.innerHTML = '<div style="font-size:9px;color:#ccc;margin-bottom:2px;">' + info.emoji + ' ' + _escMtg(info.name) + '</div>' +
                    '<textarea class="mtg-textarea end-mtg-resp" data-agent="' + _escMtg(pKey) + '" rows="2" placeholder="' + _escMtg(_tr('contribution_placeholder', { name: info.name })) + '"></textarea>';
                respSection.appendChild(div);
            });
        }
    }

    document.getElementById('endMeetingModal').classList.remove('hidden');
}

function closeEndMeetingModal() {
    document.getElementById('endMeetingModal').classList.add('hidden');
}

async function endExecutableMeetingWithAI(meetingId) {
    var btn = document.getElementById('mtg-ai-end-' + meetingId);
    if (btn) {
        btn.disabled = true;
        btn.textContent = _mtgT('meeting_ai_ending', 'Moderator summarizing...');
    }
    try {
        var res = await fetch('/api/meetings/end', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ id: meetingId, endedBy: 'user' })
        });
        var data = await res.json();
        if (!res.ok || data.error) throw new Error(data.error || 'Failed to end meeting');
        await _mtgAfterMeetingRefresh();
        switchMtgTab('completed');
    } catch (e) {
        alert((_tr('failed_end_meeting') || 'Failed to end meeting') + ': ' + (e.message || String(e)));
    } finally {
        if (btn) {
            btn.disabled = false;
            btn.textContent = '✅ ' + _mtgT('meeting_ai_end', 'Ask moderator to end');
        }
    }
}

function _mtgFindActiveMeeting(meetingId) {
    return (_mtgData.active || []).find(function(m) { return m && m.id === meetingId; }) || null;
}

async function _mtgTransitionMeeting(meetingId, action, reason) {
    var meeting = _mtgFindActiveMeeting(meetingId);
    var body = {
        action: action,
        actorType: 'user',
        actorId: 'user',
        idempotencyKey: action + '-' + Date.now()
    };
    if (meeting && meeting.executionVersion !== undefined) body.expectedVersion = meeting.executionVersion;
    if (reason) body.reason = reason;
    var res = await fetch('/api/meetings/executable/' + encodeURIComponent(meetingId) + '/transition', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body)
    });
    var data = await res.json();
    if (!res.ok || data.error) throw new Error(data.error || 'Meeting control failed');
    await _mtgAfterMeetingRefresh();
    if (action === 'cancel') switchMtgTab('completed');
    return data;
}

async function _mtgConflictAction(meetingId, body) {
    body = body || {};
    body.actorType = body.actorType || 'user';
    body.actorId = body.actorId || 'user';
    body.idempotencyKey = body.idempotencyKey || ((body.action || 'conflict') + '-' + Date.now() + '-' + Math.random().toString(16).slice(2));
    var res = await fetch('/api/meetings/executable/' + encodeURIComponent(meetingId) + '/conflict', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body)
    });
    var data = await res.json();
    if (!res.ok || data.error) throw new Error(data.error || 'Conflict handling failed');
    await _mtgAfterMeetingRefresh();
    return data;
}

async function resolveMeetingConflict(meetingId, agentId, action) {
    try {
        await _mtgConflictAction(meetingId, { action: action || 'wait', agentId: agentId });
    } catch (e) {
        alert(_mtgT('meeting_conflict_failed', 'Conflict handling failed') + ': ' + (e.message || String(e)));
    }
}

async function reserveMeetingConflict(meetingId, agentId) {
    try {
        await _mtgConflictAction(meetingId, { action: 'reserve', agentId: agentId });
    } catch (e) {
        alert(_mtgT('meeting_conflict_failed', 'Conflict handling failed') + ': ' + (e.message || String(e)));
    }
}

async function replaceMeetingConflict(meetingId, agentId) {
    var replacement = prompt(_mtgT('meeting_conflict_replace_prompt', 'Replacement agent ID'), '');
    if (!replacement) return;
    try {
        await _mtgConflictAction(meetingId, { action: 'replace', agentId: agentId, replacement: replacement.trim() });
    } catch (e) {
        alert(_mtgT('meeting_conflict_failed', 'Conflict handling failed') + ': ' + (e.message || String(e)));
    }
}

async function forceJoinMeetingConflict(meetingId, agentId) {
    if (!confirm(_mtgT('meeting_conflict_force_confirm', 'Force join can interrupt current work. Continue?'))) return;
    try {
        await _mtgConflictAction(meetingId, { action: 'force_join', agentId: agentId, confirmForce: true });
    } catch (e) {
        alert(_mtgT('meeting_conflict_failed', 'Conflict handling failed') + ': ' + (e.message || String(e)));
    }
}

async function refreshMeetingConflicts(meetingId) {
    try {
        await _mtgConflictAction(meetingId, { action: 'refresh' });
    } catch (e) {
        alert(_mtgT('meeting_conflict_failed', 'Conflict handling failed') + ': ' + (e.message || String(e)));
    }
}

async function pauseExecutableMeeting(meetingId) {
    var btn = document.getElementById('mtg-pause-' + meetingId);
    if (btn) btn.disabled = true;
    try {
        await _mtgTransitionMeeting(meetingId, 'pause', 'Paused by user');
    } catch (e) {
        alert(_mtgT('meeting_control_failed', 'Meeting control failed') + ': ' + (e.message || String(e)));
    } finally {
        if (btn) btn.disabled = false;
    }
}

async function resumeExecutableMeeting(meetingId) {
    var btn = document.getElementById('mtg-resume-' + meetingId);
    if (btn) btn.disabled = true;
    var meeting = _mtgFindActiveMeeting(meetingId);
    var previous = meeting && meeting.executionPreviousStage;
    var action = previous === 'active_discussion' ? 'resume_discussion' : previous === 'preparing' ? 'resume_preparing' : 'resume_opening';
    try {
        await _mtgTransitionMeeting(meetingId, action, 'Resumed by user');
    } catch (e) {
        alert(_mtgT('meeting_control_failed', 'Meeting control failed') + ': ' + (e.message || String(e)));
    } finally {
        if (btn) btn.disabled = false;
    }
}

async function cancelExecutableMeeting(meetingId) {
    if (!confirm(_mtgT('meeting_cancel_confirm', 'Cancel this meeting?'))) return;
    var btn = document.getElementById('mtg-cancel-' + meetingId);
    if (btn) btn.disabled = true;
    try {
        await _mtgTransitionMeeting(meetingId, 'cancel', 'Cancelled by user');
    } catch (e) {
        alert(_mtgT('meeting_control_failed', 'Meeting control failed') + ': ' + (e.message || String(e)));
    } finally {
        if (btn) btn.disabled = false;
    }
}

async function submitEndMeeting() {
    var meetId = document.getElementById('end-mtg-id').value;
    var summary = document.getElementById('end-mtg-summary').value.trim();
    var resolution = document.getElementById('end-mtg-resolution').value.trim();
    var actionsRaw = document.getElementById('end-mtg-actions').value.trim();
    var actionItems = actionsRaw ? actionsRaw.split('\n').map(function(l) { return l.trim(); }).filter(Boolean) : [];

    // Collect per-agent responses
    var responses = {};
    document.querySelectorAll('.end-mtg-resp').forEach(function(el) {
        var key = el.dataset.agent;
        var val = el.value.trim();
        if (key && val) responses[key] = val;
    });

    if (!summary) {
        var errEl = document.getElementById('end-mtg-error');
        errEl.textContent = _tr('summary_required');
        errEl.style.display = 'block';
        return;
    }

    try {
        var res = await fetch('/api/meetings/end', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ id: meetId, summary: summary, resolution: resolution, actionItems: actionItems, responses: responses, endedBy: 'user' })
        });
        var data = await res.json();
        if (data.ok) {
            closeEndMeetingModal();
            _mtgRefresh();
        } else {
            var errEl = document.getElementById('end-mtg-error');
            errEl.textContent = data.error || _tr('failed_end_meeting');
            errEl.style.display = 'block';
        }
    } catch (e) {
        var errEl = document.getElementById('end-mtg-error');
        errEl.textContent = _tr('error') + ': ' + e.message;
        errEl.style.display = 'block';
    }
}

async function deleteMeetingHistory(meetingId) {
    if (!confirm(_tr('delete_meeting_confirm'))) return;
    try {
        var res = await fetch('/api/meetings/history/' + meetingId, { method: 'DELETE' });
        var data = await res.json();
        if (data.ok) _mtgRefresh();
        else alert(data.error || _tr('failed_delete'));
    } catch (e) {
        alert(_tr('error') + ': ' + e.message);
    }
}

// --- Sidebar meetings widget ---
function _updateSidebarMeetings() {
    var container = document.getElementById('sidebar-mtg-active');
    if (!container) return;
    var active = _mtgData.active || [];
    var pendingRequests = (_mtgData.requests || []).filter(function(r) { return r && r.status === 'pending'; });
    var requestHtml = '';
    if (pendingRequests.length) {
        requestHtml = '<div class="sidebar-mtg-request" onclick="openMeetingsDashboard();switchMtgTab(\'requests\')">' +
            '<div class="sidebar-mtg-item-title sidebar-mtg-request-title"><span><span class="sidebar-mtg-request-dot"></span>' + _escMtg(_mtgT('meeting_request_pending_prompt', 'AI meeting requests need confirmation')) + '</span><span class="sidebar-mtg-request-count">' + _escMtg(String(pendingRequests.length)) + '</span></div>' +
            '</div>';
    }
    if (!active.length) {
        container.innerHTML = requestHtml + '<div class="sidebar-mtg-none">' + _escMtg(_tr('no_active_meetings')) + '</div>';
        return;
    }
    container.innerHTML = requestHtml + active.map(function(m) {
        var participants = m.participants || m.agents || [];
        var pNames = participants.map(function(k) {
            var info = _mtgAgentMap[k];
            return info ? info.emoji + ' ' + info.name : k;
        }).join(', ');
        return '<div class="sidebar-mtg-item" onclick="openMeetingReference({ meetingId: ' + _escMtg(_mtgJsArg(m.id || '')) + ' })">' +
            '<div class="sidebar-mtg-item-title"><span class="sidebar-mtg-item-dot"></span>' + _escMtg(m.topic || _tr('untitled_meeting')) + '</div>' +
            '<div class="sidebar-mtg-item-meta">' + pNames + '</div>' +
            '</div>';
    }).join('');
}

// Refresh sidebar meetings periodically
setInterval(function() {
    Promise.all([
        fetch('/api/meetings/active').then(function(r) { return r.json(); }),
        fetch('/api/meetings/requests?status=pending').then(function(r) { return r.json(); })
    ]).then(function(results) {
        var data = results[0] || {};
        var requests = results[1] || {};
        _mtgData.active = data.meetings || [];
        _mtgSeedLiveMeetings(_mtgData.active);
        (_mtgData.active || []).forEach(_mtgMaybeAutoContinueDecisionMeeting);
        _mtgData.requests = _mtgSortRequestsByStatusThenTime(requests.requests || []);
        // Also refresh agent map if empty
        if (Object.keys(_mtgAgentMap).length === 0) {
            fetch('/agents-list').then(function(r) { return r.json(); }).then(function(d) {
                var list = d.agents || d || [];
                if (Array.isArray(list)) {
                    list.forEach(function(a) {
                        _mtgAgentMap[a.key || a.agentId || a.id] = { name: a.name || a.key, emoji: a.emoji || '🤖', role: a.role || '' };
                    });
                }
                _updateSidebarMeetings();
            }).catch(function() { _updateSidebarMeetings(); });
        } else {
            _updateSidebarMeetings();
        }
    }).catch(function() {});
}, 10000);

setInterval(_mtgUpdateDecisionCountdowns, 1000);

// Initial load
setTimeout(function() {
    fetch('/api/meetings/active').then(function(r) { return r.json(); }).then(function(data) {
        _mtgData.active = data.meetings || [];
        _mtgSeedLiveMeetings(_mtgData.active);
        fetch('/agents-list').then(function(r) { return r.json(); }).then(function(d) {
            var list = d.agents || d || [];
            if (Array.isArray(list)) {
                list.forEach(function(a) {
                    _mtgAgentMap[a.key || a.agentId || a.id] = { name: a.name || a.key, emoji: a.emoji || '🤖', role: a.role || '' };
                });
            }
            _updateSidebarMeetings();
        }).catch(function() { _updateSidebarMeetings(); });
    }).catch(function() {});
}, 2000);

// --- Meeting table click handler ---
// Override the existing furniture click to detect meetingTable clicks
var _origHandleFurnitureClick = typeof handleFurnitureClick === 'function' ? handleFurnitureClick : null;
function _meetingTableClickCheck(item) {
    if (item && item.type === 'meetingTable' && !editMode) {
        openMeetingsDashboard();
        return true;
    }
    return false;
}

// Close meetings modal on Escape
document.addEventListener('keydown', function(e) {
    if (e.key === 'Escape') {
        if (!document.getElementById('meetingRequestDetailModal').classList.contains('hidden')) {
            closeMeetingRequestDetailModal();
        } else if (!document.getElementById('meetingDetailModal').classList.contains('hidden')) {
            closeMeetingDetailModal();
        } else if (!document.getElementById('endMeetingModal').classList.contains('hidden')) {
            closeEndMeetingModal();
        } else if (!document.getElementById('meetingsModal').classList.contains('hidden')) {
            closeMeetingsModal();
        }
    }
});

// Close meetings modal on backdrop click
document.getElementById('meetingsModal').addEventListener('click', function(e) {
    if (e.target === this) closeMeetingsModal();
});
document.getElementById('endMeetingModal').addEventListener('click', function(e) {
    if (e.target === this) closeEndMeetingModal();
});
document.getElementById('meetingDetailModal').addEventListener('click', function(e) {
    if (e.target === this) closeMeetingDetailModal();
});
document.getElementById('meetingRequestDetailModal').addEventListener('click', function(e) {
    if (e.target === this) closeMeetingRequestDetailModal();
});

Object.assign(window, {
    openMeetingsDashboard,
    closeMeetingsModal,
    switchMtgTab,
    openMeetingDetailModal,
    closeMeetingDetailModal,
    openMeetingReference,
    openMeetingRequestDetailModal,
    closeMeetingRequestDetailModal,
    startExecutableMeeting,
    pauseExecutableMeeting,
    resumeExecutableMeeting,
    cancelExecutableMeeting,
    submitEndMeeting,
    deleteMeetingHistory,
    _mtgRefresh,
    _mtgAfterMeetingRefresh,
    _meetingForAgent,
    _meetingForSpace,
    _meetingRawActiveRecord,
    _meetingAgentMatchesKey
});
