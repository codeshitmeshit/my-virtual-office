// ================================================================
//  Virtual Office — Projects Feature
//  Self-contained: all state, rendering, API, drag-drop
// ================================================================
(function () {
    'use strict';

    // ── UUID ───────────────────────────────────────────────────────
    function genId() {
        if (typeof crypto !== 'undefined' && crypto.randomUUID) return crypto.randomUUID();
        return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, c => {
            const r = Math.random() * 16 | 0;
            return (c === 'x' ? r : (r & 0x3 | 0x8)).toString(16);
        });
    }

    // ── STATE ──────────────────────────────────────────────────────
    const state = {
        view: 'list',          // list | board | templates | report
        projects: [],
        templates: [],
        currentProject: null,  // full project object
        currentTask: null,     // task being edited in detail panel
        meetingRequestsByTask: {},
        expandedCommentTasks: {},
        agentRoster: [],
        dragState: null,       // {taskId, projectId, sourceColId, ghost}
        touchDrag: null,
        filters: { status: '', priority: '', tag: '', search: '', sort: 'updatedAt' },
        workflow: { active: false, autoMode: false, phase: 'idle', currentTaskId: null, pollTimer: null, startMode: 'continuous', flowStopReason: null },
        acceptanceDialog: null,
        pendingActions: new Map(),
        duplicateActionToastAt: {},
        _projectSummarySignature: '',
    };

    const _t = (key, params) => {
        const value = typeof i18n !== 'undefined' ? i18n.t(key, params) : key;
        return params ? formatTextTemplate(value, params) : value;
    };
    function currentLang() {
        return ((typeof i18n !== 'undefined' && i18n.getLanguage && i18n.getLanguage()) || document.documentElement.lang || 'en').toLowerCase();
    }
    function _tf(key, fallbackEn, fallbackZh, params) {
        const value = _t(key, params);
        if (value && value !== key) return value;
        return currentLang().startsWith('zh') ? fallbackZh : fallbackEn;
    }
    function formatTextTemplate(text, params) {
        return String(text || '').replace(/\{(\w+)\}/g, (_, key) => params && params[key] != null ? String(params[key]) : '');
    }

    function commentsToggleLabel(expanded, hiddenCount) {
        if (expanded) return _t('proj_comments_collapse');
        const label = _t('proj_comments_expand', { count: hiddenCount });
        if (label && label !== 'proj_comments_expand') return label;
        return currentLang().startsWith('zh') ? `展开全部（还有 ${hiddenCount} 条）` : `Show all (${hiddenCount} more)`;
    }

    function meetingActionStatusLabel(status) {
        const key = {
            pending: 'proj_meeting_action_status_pending',
            completed: 'proj_meeting_action_status_completed',
            external_task_created: 'proj_meeting_action_status_linked'
        }[status || 'pending'];
        return key ? _t(key) : (status || 'pending');
    }

    function meetingDiscussionKindLabel(kind) {
        const key = {
            decision: 'proj_meeting_record_kind_decision',
            risk: 'proj_meeting_record_kind_risk',
            note: 'proj_meeting_record_kind_note'
        }[kind || 'note'];
        return key ? _t(key) : (kind || _t('proj_meeting_record_kind_note'));
    }

    function meetingRecordStatusLabel(status) {
        const key = {
            approved: 'proj_meeting_record_status_approved',
            no_consensus: 'proj_meeting_record_status_no_consensus',
            rejected: 'proj_meeting_record_status_rejected',
            needs_user_decision: 'proj_meeting_record_status_needs_user_decision'
        }[status || ''];
        return key ? _t(key) : (status || _t('proj_meeting_record_status_unknown'));
    }

    function statusClassName(value, fallback = 'unknown') {
        return String(value || fallback)
            .toLowerCase()
            .replace(/[^a-z0-9_-]+/g, '-')
            .replace(/^-+|-+$/g, '') || fallback;
    }

    function taskMeetingRecords(task, discussionPoints, actionItems) {
        const explicit = Array.isArray(task && task.meetingRecords) ? task.meetingRecords : [];
        if (explicit.length) {
            return explicit.slice().sort((a, b) => String(a.appliedAt || a.createdAt || '').localeCompare(String(b.appliedAt || b.createdAt || '')));
        }
        const grouped = {};
        (discussionPoints || []).forEach(item => {
            const meetingId = item.meetingId || 'task-context';
            if (!grouped[meetingId]) {
                grouped[meetingId] = {
                    id: 'legacy-' + meetingId,
                    meetingId,
                    requestId: item.requestId || '',
                    outcome: item.kind === 'risk' ? 'needs_user_decision' : 'approved',
                    status: item.kind === 'risk' ? 'needs_user_decision' : 'approved',
                    decision: '',
                    summary: '',
                    risks: [],
                    actionItems: [],
                    createdAt: item.createdAt || '',
                    appliedAt: item.createdAt || ''
                };
            }
            if (item.kind === 'risk') grouped[meetingId].risks.push(item.text || '');
            else if (!grouped[meetingId].decision) grouped[meetingId].decision = item.text || '';
            if (item.createdAt && (!grouped[meetingId].appliedAt || item.createdAt < grouped[meetingId].appliedAt)) grouped[meetingId].appliedAt = item.createdAt;
        });
        (actionItems || []).forEach(item => {
            const meetingId = item.meetingId || 'task-context';
            if (!grouped[meetingId]) {
                grouped[meetingId] = {
                    id: 'legacy-' + meetingId,
                    meetingId,
                    requestId: item.requestId || '',
                    outcome: 'approved',
                    status: 'approved',
                    decision: '',
                    summary: '',
                    risks: [],
                    actionItems: [],
                    createdAt: item.createdAt || '',
                    appliedAt: item.createdAt || ''
                };
            }
            grouped[meetingId].actionItems.push({ title: item.title || '', owner: item.owner || '' });
        });
        return Object.values(grouped).sort((a, b) => String(a.appliedAt || a.createdAt || '').localeCompare(String(b.appliedAt || b.createdAt || '')));
    }

    // ── DEFAULT TEMPLATES ─────────────────────────────────────────
    const DEFAULT_TEMPLATES = [
        {
            id: 'tpl-blank',
            title: 'Blank Project',
            _titleKey: 'proj_blank_project',
            description: 'Start from scratch with 5 default columns',
            _descKey: 'proj_blank_project_desc',
            columns: [
                { title: 'Backlog', color: '#6c757d', _titleKey: 'proj_col_backlog' },
                { title: 'In Progress', color: '#ffc107', _titleKey: 'proj_col_in_progress' },
                { title: 'Review', color: '#fd7e14', _titleKey: 'proj_col_review' },
                { title: 'Done', color: '#198754', _titleKey: 'proj_col_done' },
            ],
            taskTemplates: [],
        },
        {
            id: 'tpl-software',
            title: 'Software Development',
            _titleKey: 'proj_software_dev',
            description: 'Standard software development workflow with sprint planning',
            _descKey: 'proj_software_dev_desc',
            columns: [
                { title: 'Backlog', color: '#6c757d', _titleKey: 'proj_col_backlog' },
                { title: 'Sprint', color: '#0d6efd', _titleKey: 'proj_col_sprint' },
                { title: 'In Progress', color: '#ffc107', _titleKey: 'proj_col_in_progress' },
                { title: 'Code Review', color: '#fd7e14', _titleKey: 'proj_col_code_review' },
                { title: 'QA', color: '#17a2b8', _titleKey: 'proj_col_qa' },
                { title: 'Done', color: '#198754', _titleKey: 'proj_col_done' },
            ],
            taskTemplates: [
                { title: 'Set up development environment', _titleKey: 'proj_task_setup_dev_env', columnIndex: 0, priority: 'high' },
                { title: 'Define acceptance criteria', _titleKey: 'proj_task_define_acceptance', columnIndex: 0, priority: 'medium' },
                { title: 'Write unit tests', _titleKey: 'proj_task_write_unit_tests', columnIndex: 0, priority: 'medium' },
            ],
        },
        {
            id: 'tpl-marketing',
            title: 'Marketing Campaign',
            _titleKey: 'proj_marketing_campaign',
            description: 'Plan and execute marketing campaigns',
            _descKey: 'proj_marketing_campaign_desc',
            columns: [
                { title: 'Ideas', color: '#6c757d', _titleKey: 'proj_col_ideas' },
                { title: 'Planning', color: '#0d6efd', _titleKey: 'proj_col_planning' },
                { title: 'Creating', color: '#ffc107', _titleKey: 'proj_col_creating' },
                { title: 'Review', color: '#fd7e14', _titleKey: 'proj_col_review' },
                { title: 'Published', color: '#198754', _titleKey: 'proj_col_published' },
            ],
            taskTemplates: [
                { title: 'Define target audience', _titleKey: 'proj_task_define_audience', columnIndex: 0, priority: 'high' },
                { title: 'Create content calendar', _titleKey: 'proj_task_content_calendar', columnIndex: 0, priority: 'medium' },
            ],
        },
        {
            id: 'tpl-bugs',
            title: 'Bug Tracking',
            _titleKey: 'proj_bug_tracking',
            description: 'Track and resolve bugs systematically',
            _descKey: 'proj_bug_tracking_desc',
            columns: [
                { title: 'Reported', color: '#dc3545', _titleKey: 'proj_col_reported' },
                { title: 'Confirmed', color: '#fd7e14', _titleKey: 'proj_col_confirmed' },
                { title: 'In Progress', color: '#ffc107', _titleKey: 'proj_col_in_progress' },
                { title: 'Fixed', color: '#0d6efd', _titleKey: 'proj_col_fixed' },
                { title: 'Verified', color: '#198754', _titleKey: 'proj_col_verified' },
            ],
            taskTemplates: [],
        },
        {
            id: 'tpl-content',
            title: 'Content Pipeline',
            _titleKey: 'proj_content_pipeline',
            description: 'Manage content creation workflow',
            _descKey: 'proj_content_pipeline_desc',
            columns: [
                { title: 'Backlog', color: '#6c757d', _titleKey: 'proj_col_backlog' },
                { title: 'Research', color: '#17a2b8', _titleKey: 'proj_col_research' },
                { title: 'Writing', color: '#ffc107', _titleKey: 'proj_col_writing' },
                { title: 'Editing', color: '#fd7e14', _titleKey: 'proj_col_editing' },
                { title: 'Published', color: '#198754', _titleKey: 'proj_col_published' },
            ],
            taskTemplates: [],
        },
    ];

    // ── API ────────────────────────────────────────────────────────
    const projectMutationFetch = (input, init) => window.i18n.managementFetch(input, init);
    const api = {
        async listProjects(status) {
            const qs = status ? `?status=${status}` : '';
            const r = await fetch(`/api/projects${qs}`);
            return r.json();
        },
        async getProject(id) {
            const r = await fetch(`/api/projects/${id}`);
            return r.json();
        },
        async createProject(body) {
            const r = await projectMutationFetch('/api/projects', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
            return r.json();
        },
        async updateProject(id, body) {
            const r = await projectMutationFetch(`/api/projects/${id}`, { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
            return r.json();
        },
        async deleteProject(id, opts = {}) {
            const qs = opts.deleteWorkspace ? '?deleteWorkspace=true' : '';
            const r = await projectMutationFetch(`/api/projects/${id}${qs}`, { method: 'DELETE' });
            return r.json();
        },
        async resetProject(id, body) {
            const r = await projectMutationFetch(`/api/projects/${id}/reset`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body || {}) });
            return r.json();
        },
        async createTask(projectId, body) {
            const r = await projectMutationFetch(`/api/projects/${projectId}/tasks`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
            return r.json();
        },
        async updateTask(projectId, taskId, body) {
            const r = await projectMutationFetch(`/api/projects/${projectId}/tasks/${taskId}`, { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
            return r.json();
        },
        async deleteTask(projectId, taskId) {
            const r = await projectMutationFetch(`/api/projects/${projectId}/tasks/${taskId}`, { method: 'DELETE' });
            return r.json();
        },
        async addComment(projectId, taskId, body) {
            const r = await projectMutationFetch(`/api/projects/${projectId}/tasks/${taskId}/comments`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
            return r.json();
        },
        async reorderTasks(projectId, updates) {
            const r = await projectMutationFetch(`/api/projects/${projectId}/tasks/reorder`, { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ updates }) });
            return r.json();
        },
        async updateColumns(projectId, columns) {
            const r = await projectMutationFetch(`/api/projects/${projectId}/columns`, { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ columns }) });
            return r.json();
        },
        async listTemplates() {
            const r = await fetch('/api/projects/templates');
            return r.json();
        },
        async saveTemplate(body) {
            const r = await projectMutationFetch('/api/projects/templates', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
            return r.json();
        },
        async deleteTemplate(id) {
            const r = await projectMutationFetch(`/api/projects/templates/${id}`, { method: 'DELETE' });
            return r.json();
        },
        async createFromTemplate(body) {
            const r = await projectMutationFetch('/api/projects/from-template', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
            return r.json();
        },
        async getReport(projectId) {
            const r = await fetch(`/api/projects/${projectId}/report`);
            return r.json();
        },
        async getAgents() {
            const r = await fetch('/agents-list');
            return r.json();
        },
        async getScores() {
            const r = await fetch('/api/projects/scores');
            return r.json();
        },
        // Workflow API
        async workflowStart(projectId, autoMode) {
            const r = await projectMutationFetch(`/api/projects/${projectId}/workflow/start`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ autoMode }) });
            return r.json();
        },
        async workflowStop(projectId) {
            const r = await projectMutationFetch(`/api/projects/${projectId}/workflow/stop`, { method: 'POST' });
            return r.json();
        },
        async workflowStatus(projectId) {
            const r = await fetch(`/api/projects/${projectId}/workflow/status`);
            return r.json();
        },
        async setAutoMode(projectId, autoMode) {
            const r = await projectMutationFetch(`/api/projects/${projectId}/workflow/auto-mode`, { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ autoMode }) });
            return r.json();
        },
        async updateReviewCheck(projectId, taskId, reviewCheck) {
            const r = await projectMutationFetch(`/api/projects/${projectId}/tasks/${taskId}/review-check`, { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ reviewCheck }) });
            return r.json();
        },
        async workflowChat(projectId) {
            const r = await fetch(`/api/projects/${projectId}/workflow/chat`);
            return r.json();
        },
        async projectExecutionValidateWorkspace(projectId, workspacePath) {
            const r = await projectMutationFetch(`/api/projects/${projectId}/project-execution/workspace/validate`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ workspacePath }) });
            return r.json();
        },
        async projectExecutionStart(projectId, taskId, dirtyFingerprint, opts = {}) {
            const r = await projectMutationFetch(`/api/projects/${projectId}/tasks/${taskId}/project-execution/start`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ dirtyFingerprint: dirtyFingerprint || '', skipReviewConfirmed: !!opts.skipReviewConfirmed, resetExecutionContext: opts.resetExecutionContext === true }) });
            return r.json();
        },
        async projectExecutionProjectStart(projectId, mode, dirtyFingerprint, opts = {}) {
            const r = await projectMutationFetch(`/api/projects/${projectId}/project-execution/start`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ mode: mode || 'continuous', dirtyFingerprint: dirtyFingerprint || '', skipReviewConfirmed: !!opts.skipReviewConfirmed, restartPipeline: !!opts.restartPipeline }) });
            return r.json();
        },
        async projectExecutionCancel(projectId, taskId, attemptId) {
            const r = await projectMutationFetch(`/api/projects/${projectId}/tasks/${taskId}/project-execution/cancel`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ attemptId }) });
            return r.json();
        },
        async projectExecutionReviewStart(projectId, taskId, attemptId) {
            const r = await projectMutationFetch(`/api/projects/${projectId}/tasks/${taskId}/project-execution/review/start`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ attemptId }) });
            return r.json();
        },
        async projectExecutionAccept(projectId, taskId, action, attemptId, feedback, opts = {}) {
            const r = await projectMutationFetch(`/api/projects/${projectId}/tasks/${taskId}/project-execution/accept`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ action, attemptId, feedback: feedback || '', allowEmptyChecklist: opts.allowEmptyChecklist === true }) });
            return r.json();
        },
        async projectExecutionMeetingBlocker(projectId, taskId, action, feedback) {
            const r = await projectMutationFetch(`/api/projects/${projectId}/tasks/${taskId}/project-execution/meeting-blocker`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ action, feedback: feedback || '' }) });
            return r.json();
        },
        async projectExecutionStatus(projectId, taskId) {
            const suffix = taskId ? `/tasks/${taskId}` : '';
            const r = await fetch(`/api/projects/${projectId}${suffix}/project-execution/status`);
            return r.json();
        },
        async listArtifacts(projectId) {
            const r = await fetch(`/api/projects/${projectId}/artifacts`);
            return r.json();
        },
        async readArtifact(projectId, path) {
            const r = await fetch(`/api/projects/${projectId}/artifacts/read?path=${encodeURIComponent(path)}`);
            return r.json();
        },
        async deleteArtifact(projectId, path) {
            const r = await projectMutationFetch(`/api/projects/${projectId}/artifacts?path=${encodeURIComponent(path)}`, { method: 'DELETE' });
            return r.json();
        },
        async deleteArtifactDir(projectId, dir) {
            const r = await projectMutationFetch(`/api/projects/${projectId}/artifacts?dir=${encodeURIComponent(dir || '')}`, { method: 'DELETE' });
            return r.json();
        },
        async listMeetingRequests(projectId, taskId) {
            const qs = taskId ? `?projectId=${encodeURIComponent(projectId)}&taskId=${encodeURIComponent(taskId)}` : `?projectId=${encodeURIComponent(projectId)}`;
            const r = await fetch(`/api/meetings/requests${qs}`);
            return r.json();
        },
        async listScheduledCron(projectId) {
            const r = await fetch(`/api/projects/${projectId}/scheduled-cron`);
            return r.json();
        },
        async createScheduledCron(projectId, body) {
            const r = await projectMutationFetch(`/api/projects/${projectId}/scheduled-cron`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
            return r.json();
        },
        async updateScheduledCron(projectId, cronId, body) {
            const r = await projectMutationFetch(`/api/projects/${projectId}/scheduled-cron/${cronId}`, { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
            return r.json();
        },
        async deleteScheduledCron(projectId, cronId) {
            const r = await projectMutationFetch(`/api/projects/${projectId}/scheduled-cron/${cronId}`, { method: 'DELETE' });
            return r.json();
        },
        async runScheduledCron(projectId, cronId) {
            const r = await projectMutationFetch(`/api/projects/${projectId}/scheduled-cron/${cronId}/run`, { method: 'POST' });
            return r.json();
        },
    };

    // ── GAMIFICATION ENGINE ───────────────────────────────────────

    /** Show floating +XP popup at a screen position */
    function showScorePopup(x, y, points, streak) {
        const el = document.createElement('div');
        el.className = 'proj-score-popup';
        el.style.left = x + 'px';
        el.style.top = y + 'px';
        let text = `+${points} XP`;
        if (streak > 1) text += ` 🔥${streak}`;
        el.textContent = text;
        document.body.appendChild(el);
        setTimeout(() => el.remove(), 1300);
    }

    /** Spawn confetti burst at a position */
    function spawnConfetti(x, y, count = 15) {
        const colors = ['#ffd700', '#4caf50', '#ff6b35', '#0d6efd', '#e91e63', '#00bcd4', '#ff9800'];
        for (let i = 0; i < count; i++) {
            const c = document.createElement('div');
            c.className = 'proj-confetti';
            c.style.left = (x + (Math.random() - 0.5) * 80) + 'px';
            c.style.top = (y + (Math.random() - 0.5) * 20) + 'px';
            c.style.backgroundColor = colors[Math.floor(Math.random() * colors.length)];
            c.style.width = (4 + Math.random() * 6) + 'px';
            c.style.height = (4 + Math.random() * 6) + 'px';
            c.style.animationDuration = (0.8 + Math.random() * 1) + 's';
            c.style.animationDelay = (Math.random() * 0.2) + 's';
            document.body.appendChild(c);
            setTimeout(() => c.remove(), 2000);
        }
    }

    /** Animate a task card spawn */
    function animateTaskSpawn(taskId) {
        requestAnimationFrame(() => {
            const card = document.getElementById(`task-${taskId}`);
            if (card) {
                card.classList.add('anim-spawn');
                card.addEventListener('animationend', () => card.classList.remove('anim-spawn'), { once: true });
            }
        });
    }

    /** Animate a task card deletion (returns promise that resolves when animation done) */
    function animateTaskDelete(taskId) {
        return new Promise(resolve => {
            const card = document.getElementById(`task-${taskId}`);
            if (card) {
                card.classList.add('anim-delete');
                card.addEventListener('animationend', () => resolve(), { once: true });
                // Fallback in case animationend doesn't fire
                setTimeout(resolve, 500);
            } else {
                resolve();
            }
        });
    }

    /** Animate a task completion (sparkle + confetti + score) */
    function animateTaskComplete(taskId, scoreResult) {
        requestAnimationFrame(() => {
            const card = document.getElementById(`task-${taskId}`);
            if (card) {
                card.classList.add('anim-complete');
                const rect = card.getBoundingClientRect();
                // Confetti burst from the card
                spawnConfetti(rect.left + rect.width / 2, rect.top);
                // Score popup
                if (scoreResult && scoreResult.pointsAwarded) {
                    showScorePopup(rect.right - 30, rect.top - 10, scoreResult.pointsAwarded, scoreResult.streak);
                }
                // Gamified toast
                if (scoreResult && scoreResult.pointsAwarded) {
                    const agentInfo = state.agentRoster.find(a => a.key === scoreResult.agent);
                    const name = agentInfo ? agentInfo.name : scoreResult.agent;
                    const emoji = agentInfo ? agentInfo.emoji : '🤖';
                    const streakText = scoreResult.streak > 1 ? '🔥 Streak x' + scoreResult.streak : '';
                    const msg = _t('proj_xp_earned').replace('{emoji}', emoji).replace('{name}', name).replace('{points}', scoreResult.pointsAwarded).replace('{streak}', streakText);
                    toast(msg, 'success');
                } else {
                    toast(_t('proj_task_completed'), 'success');
                }
                // Refresh leaderboard
                refreshLeaderboard();
            }
        });
    }

    /** Update the sidebar leaderboard */
    async function refreshLeaderboard() {
        try {
            const data = await api.getScores();
            const lb = data.leaderboard || [];
            const container = document.getElementById('sidebar-projects-lb');
            if (!container) return;
            if (lb.length === 0) {
                container.innerHTML = `<div class="proj-lb-empty">${_t('proj_leaderboard_empty')}</div>`;
                return;
            }
            const top5 = lb.slice(0, 5);
            container.innerHTML = top5.map((entry, i) => {
                const agent = state.agentRoster.find(a => a.key === entry.agent);
                const emoji = agent ? agent.emoji : '🤖';
                const name = agent ? agent.name : entry.agent;
                return `<div class="proj-lb-row">
                    <span class="proj-lb-rank rank-${i + 1}">${i === 0 ? '👑' : i === 1 ? '🥈' : i === 2 ? '🥉' : '#' + (i + 1)}</span>
                    <span class="proj-lb-emoji">${emoji}</span>
                    <span class="proj-lb-name">${escHtml(name)}</span>
                    <span class="proj-lb-score">${entry.score} XP</span>
                    ${entry.streak > 1 ? `<span class="proj-streak">🔥${entry.streak}</span>` : ''}
                </div>`;
            }).join('');
        } catch (e) { /* silent */ }
    }

    /** Render in-board mini scoreboard (top of board) */
    function renderBoardScoreboard() {
        if (!state.currentProject) return '';
        // Get assignees in this project
        const assignees = new Set();
        state.currentProject.tasks.forEach(t => { if (t.assignee) assignees.add(t.assignee); });
        if (assignees.size === 0) return '';
        // We'll populate async, return a container
        return `<div class="proj-scoreboard" id="proj-board-scoreboard"></div>`;
    }

    async function populateBoardScoreboard() {
        const el = document.getElementById('proj-board-scoreboard');
        if (!el) return;
        try {
            const data = await api.getScores();
            const lb = data.leaderboard || [];
            // Filter to agents in this project
            const assignees = new Set();
            state.currentProject.tasks.forEach(t => { if (t.assignee) assignees.add(t.assignee); });
            const relevant = lb.filter(e => assignees.has(e.agent));
            if (relevant.length === 0) { el.remove(); return; }
            el.innerHTML = relevant.slice(0, 5).map((entry, i) => {
                const agent = state.agentRoster.find(a => a.key === entry.agent);
                const emoji = agent ? agent.emoji : '🤖';
                const name = agent ? agent.name : entry.agent;
                return `<div class="proj-scoreboard-item ${i === 0 ? 'rank-1' : ''}">
                    <span class="sb-emoji">${emoji}</span>
                    <span>${escHtml(name)}</span>
                    <span class="sb-score">${entry.score} XP</span>
                    ${entry.streak > 1 ? `<span class="proj-streak">🔥${entry.streak}</span>` : ''}
                </div>`;
            }).join('');
        } catch (e) { el.remove(); }
    }

    // ── HELPERS ───────────────────────────────────────────────────
    function priorityColor(p) {
        return { critical: '#dc3545', high: '#fd7e14', medium: '#0d6efd', low: '#6c757d' }[p] || '#6c757d';
    }
    function formatDate(iso) {
        if (!iso) return '';
        try {
            const d = new Date(iso);
            return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' });
        } catch { return iso; }
    }
    function isOverdue(iso) {
        if (!iso) return false;
        return new Date(iso) < new Date();
    }
    function timeAgo(iso) {
        if (!iso) return '';
        const diff = Date.now() - new Date(iso).getTime();
        const s = Math.floor(diff / 1000);
        if (s < 60) return _t('just_now');
        if (s < 3600) return Math.floor(s / 60) + _t('m_ago');
        if (s < 86400) return Math.floor(s / 3600) + _t('h_ago');
        return Math.floor(s / 86400) + _t('d_ago');
    }
    function escHtml(s) {
        if (!s) return '';
        return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
    }
    function jsArg(value) {
        return JSON.stringify(value == null ? '' : String(value)).replace(/</g, '\\u003c');
    }
    function simpleMarkdown(text) {
        if (!text) return '';
        return escHtml(text)
            .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
            .replace(/\*(.+?)\*/g, '<em>$1</em>')
            .replace(/`(.+?)`/g, '<code>$1</code>')
            .replace(/\n/g, '<br>');
    }
    function toast(msg, type = 'info') {
        let el = document.getElementById('proj-toast');
        if (!el) {
            el = document.createElement('div');
            el.id = 'proj-toast';
            el.className = 'proj-toast';
            document.body.appendChild(el);
        }
        el.textContent = msg;
        el.className = `proj-toast ${type}`;
        el.classList.add('show');
        clearTimeout(el._timer);
        el._timer = setTimeout(() => el.classList.remove('show'), 3000);
    }

    function currentActionButton(opts = {}) {
        if (opts.button) return opts.button;
        if (opts.event && opts.event.currentTarget) return opts.event.currentTarget;
        const browserEvent = typeof window !== 'undefined' ? window.event : null;
        if (browserEvent && browserEvent.currentTarget) return browserEvent.currentTarget;
        const active = typeof document !== 'undefined' ? document.activeElement : null;
        return active && active.tagName === 'BUTTON' ? active : null;
    }

    function setButtonBusy(button, busy, label) {
        if (!button || button.nodeType !== 1) return;
        if (busy) {
            if (!button.dataset.projOriginalText) button.dataset.projOriginalText = button.textContent || '';
            button.disabled = true;
            button.setAttribute('aria-busy', 'true');
            if (label) button.textContent = label;
            return;
        }
        button.disabled = false;
        button.removeAttribute('aria-busy');
        if (button.dataset.projOriginalText) {
            button.textContent = button.dataset.projOriginalText;
            delete button.dataset.projOriginalText;
        }
    }

    function duplicateActionFeedback(key, opts = {}) {
        console.info(`[PROJECTS] duplicate action ignored key=${key}`);
        if (opts.silentDuplicate) return;
        const now = Date.now();
        if ((state.duplicateActionToastAt[key] || 0) + 1200 > now) return;
        state.duplicateActionToastAt[key] = now;
        toast(_tf('proj_action_in_progress', 'Already processing, please wait...', '处理中，请稍候...'), 'info');
    }

    async function runActionOnce(key, fn, opts = {}) {
        if (!key || typeof fn !== 'function') return undefined;
        if (state.pendingActions.has(key)) {
            duplicateActionFeedback(key, opts);
            return state.pendingActions.get(key).result;
        }
        const button = currentActionButton(opts);
        const busyText = opts.busyText || _tf('proj_processing', 'Processing...', '处理中...');
        const entry = { startedAt: Date.now(), button, result: null };
        state.pendingActions.set(key, entry);
        setButtonBusy(button, true, opts.showBusyText === false ? '' : busyText);
        entry.result = (async () => {
            try {
                return await fn();
            } finally {
                state.pendingActions.delete(key);
                setButtonBusy(button, false);
            }
        })();
        return entry.result;
    }

    function markDialogSubmitting(submitting, label) {
        const overlay = document.getElementById('proj-form-overlay');
        if (!overlay) return;
        const confirmButtons = overlay.querySelectorAll('.proj-form-actions .proj-btn-primary, .proj-form-actions .proj-btn-stop');
        confirmButtons.forEach(btn => setButtonBusy(btn, submitting, submitting ? (label || _tf('proj_processing', 'Processing...', '处理中...')) : ''));
    }

    // ── MODAL SCAFFOLD ────────────────────────────────────────────
    function getModal() { return document.getElementById('projectsModal'); }
    function getMainContent() { return document.getElementById('proj-main-content'); }

    // ── OPEN / CLOSE ──────────────────────────────────────────────
    window.openProjectsManager = function () {
        const modal = getModal();
        if (!modal) return;
        modal.classList.remove('hidden');
        loadAgentRoster();
        showListView();
        refreshLeaderboard();
    };

    window.closeProjectsModal = function () {
        const modal = getModal();
        if (modal) modal.classList.add('hidden');
        closeDetailPanel();
    };

    async function loadAgentRoster() {
        try {
            const d = await api.getAgents();
            state.agentRoster = (d.agents || []);
        } catch (e) { /* non-fatal */ }
    }

    // ── LIST VIEW ─────────────────────────────────────────────────
    async function showListView() {
        state.view = 'list';
        state.currentProject = null;
        closeDetailPanel();
        const mc = getMainContent();
        if (!mc) return;
        mc.innerHTML = renderListSkeleton();
        try {
            const d = await api.listProjects();
            state.projects = d.projects || [];
            state._projectSummarySignature = projectSummarySignature(state.projects);
            mc.innerHTML = renderListView();
            bindListEvents();
            updateSidebar();
        } catch (e) {
            mc.innerHTML = `<div class="proj-loading"><div>${_t('proj_failed_to_load')}</div><div style="font-size:10px;color:#555">${escHtml(String(e))}</div></div>`;
        }
    }

    function renderListSkeleton() {
        return `<div class="proj-loading"><div class="proj-spinner"></div><div>${_t('proj_loading_projects')}</div></div>`;
    }

    function renderListView() {
        const { filters } = state;
        let projects = [...state.projects];

        // Filter
        if (filters.status) projects = projects.filter(p => p.status === filters.status);
        if (filters.priority) projects = projects.filter(p => p.priority === filters.priority);
        if (filters.tag) projects = projects.filter(p => (p.tags || []).includes(filters.tag));
        if (filters.search) {
            const q = filters.search.toLowerCase();
            projects = projects.filter(p => p.title.toLowerCase().includes(q) || (p.description || '').toLowerCase().includes(q));
        }

        // Sort
        const sortKey = filters.sort || 'updatedAt';
        projects.sort((a, b) => {
            if (sortKey === 'title') return (a.title || '').localeCompare(b.title || '');
            if (sortKey === 'priority') {
                const pOrder = { critical: 0, high: 1, medium: 2, low: 3 };
                return (pOrder[a.priority] || 2) - (pOrder[b.priority] || 2);
            }
            const aDate = a[sortKey] || a.updatedAt || '';
            const bDate = b[sortKey] || b.updatedAt || '';
            return bDate.localeCompare(aDate);
        });

        // Collect all tags for filter
        const allTags = [...new Set(state.projects.flatMap(p => p.tags || []))];

        return `
        <div class="proj-toolbar">
            <span class="proj-toolbar-title">${_t('proj_title')}</span>
            <button class="proj-btn proj-btn-primary" onclick="ProjMgr.newProjectDialog()">${_t('proj_new_project')}</button>
            <button class="proj-btn" onclick="ProjMgr.showTemplatesView()">${_t('proj_templates')}</button>
            <button class="proj-btn" onclick="ProjectAuthoringReview.show()">${_tf('proj_agent_drafts', 'Agent drafts', 'Agent 草稿')}</button>
            <input class="proj-search" id="proj-search" type="text" placeholder="${_t('proj_search_placeholder')}" value="${escHtml(filters.search)}" oninput="ProjMgr.filterChange('search', this.value)">
            <div class="proj-filter-row">
                <select class="proj-select" onchange="ProjMgr.filterChange('status', this.value)">
                    <option value="" ${!filters.status ? 'selected' : ''}>${_t('proj_all_statuses')}</option>
                    <option value="active" ${filters.status === 'active' ? 'selected' : ''}>${_t('proj_status_active')}</option>
                    <option value="paused" ${filters.status === 'paused' ? 'selected' : ''}>${_t('proj_status_paused')}</option>
                    <option value="completed" ${filters.status === 'completed' ? 'selected' : ''}>${_t('proj_status_completed')}</option>
                    <option value="archived" ${filters.status === 'archived' ? 'selected' : ''}>${_t('proj_status_archived')}</option>
                </select>
                <select class="proj-select" onchange="ProjMgr.filterChange('priority', this.value)">
                    <option value="" ${!filters.priority ? 'selected' : ''}>${_t('proj_all_priorities')}</option>
                    <option value="critical" ${filters.priority === 'critical' ? 'selected' : ''}>${_t('proj_priority_critical')}</option>
                    <option value="high" ${filters.priority === 'high' ? 'selected' : ''}>${_t('proj_priority_high')}</option>
                    <option value="medium" ${filters.priority === 'medium' ? 'selected' : ''}>${_t('proj_priority_medium')}</option>
                    <option value="low" ${filters.priority === 'low' ? 'selected' : ''}>${_t('proj_priority_low')}</option>
                </select>
                ${allTags.length ? `
                <select class="proj-select" onchange="ProjMgr.filterChange('tag', this.value)">
                    <option value="">${_t('proj_all_tags')}</option>
                    ${allTags.map(t => `<option value="${escHtml(t)}" ${filters.tag === t ? 'selected' : ''}>${escHtml(t)}</option>`).join('')}
                </select>` : ''}
                <select class="proj-select" onchange="ProjMgr.filterChange('sort', this.value)">
                    <option value="updatedAt" ${filters.sort === 'updatedAt' ? 'selected' : ''}>${_t('proj_sort_recently_updated')}</option>
                    <option value="createdAt" ${filters.sort === 'createdAt' ? 'selected' : ''}>${_t('proj_sort_date_created')}</option>
                    <option value="dueDate" ${filters.sort === 'dueDate' ? 'selected' : ''}>${_t('proj_sort_due_date')}</option>
                    <option value="title" ${filters.sort === 'title' ? 'selected' : ''}>${_t('proj_sort_name')}</option>
                    <option value="priority" ${filters.sort === 'priority' ? 'selected' : ''}>${_t('proj_sort_priority')}</option>
                </select>
            </div>
        </div>
        <div class="proj-list-body">
            <div class="proj-grid">
                ${projects.length === 0 ? renderEmptyList() : projects.map(renderProjectCard).join('')}
            </div>
        </div>`;
    }

    function renderEmptyList() {
        return `
        <div class="proj-empty">
            <div class="proj-empty-icon">📋</div>
            <div class="proj-empty-title">${_t('proj_no_projects_yet')}</div>
            <div class="proj-empty-text">${_t('proj_no_projects_text')}</div>
            <br>
            <button class="proj-btn proj-btn-primary" style="margin: 10px auto;display:inline-block" onclick="ProjMgr.newProjectDialog()">${_t('proj_create_project')}</button>
        </div>`;
    }

    function renderProjectCard(p) {
        const done = p.taskDone || 0;
        const total = p.taskCount || 0;
        const pct = total > 0 ? Math.round(done / total * 100) : 0;
        const remaining = Math.max(0, total - done);
        const progressTitle = formatTextTemplate(
            _tf('proj_progress_remaining_title', 'Done {done}/{total}, {remaining} remaining', '已完成 {done}/{total}，剩余 {remaining} 个', { done, total, remaining }),
            { done, total, remaining }
        );
        const overdue = p.dueDate && isOverdue(p.dueDate);
        return `
        <div class="proj-card" onclick="ProjMgr.openProject('${p.id}')">
            <div class="proj-card-header">
                <div class="proj-card-title">${escHtml(p.title)}</div>
                <div class="proj-card-actions" onclick="event.stopPropagation()">
                    <button class="proj-btn proj-btn-sm proj-btn-icon" title="${_t('proj_report')}" onclick="ProjMgr.showReport('${p.id}')">📊</button>
                    <button class="proj-btn proj-btn-sm proj-btn-icon" title="${_t('proj_archive')}" onclick="ProjMgr.archiveProject('${p.id}', event)">📁</button>
                    <button class="proj-btn proj-btn-sm proj-btn-icon" title="${_t('proj_delete')}" onclick="ProjMgr.deleteProject('${p.id}', event)">🗑️</button>
                </div>
            </div>
            ${p.description ? `<div class="proj-card-desc">${escHtml(p.description)}</div>` : ''}
            <div class="proj-card-meta">
                <span class="proj-badge badge-${p.status || 'active'}">${p.status || _t('proj_status_active')}</span>
                <span class="proj-badge badge-${p.priority || 'medium'}">${p.priority || _t('proj_priority_medium')}</span>
                ${p.branch ? `<span class="proj-badge" style="background:rgba(255,215,0,0.1);border-color:#ffd700;color:#ffd700">🏢 ${escHtml(p.branch)}</span>` : ''}
                ${(p.tags || []).slice(0, 2).map(t => `<span class="proj-tag">${escHtml(t)}</span>`).join('')}
            </div>
            <div class="proj-progress-row">
                <div class="proj-progress-track"><div class="proj-progress-bar" style="width:${pct}%"></div></div>
                <span class="proj-progress-label" title="${escHtml(progressTitle)}">${done}/${total} · ${pct}%</span>
            </div>
            ${p.dueDate ? `<div style="font-size:10px;color:${overdue ? '#f87171' : '#888'}">📅 ${overdue ? '⚠️ ' + _t('proj_overdue') + ': ' : _t('proj_due') + ': '}${formatDate(p.dueDate)}</div>` : ''}
        </div>`;
    }

    function bindListEvents() { /* events bound via inline handlers */ }

    function projectSummarySignature(projects) {
        return JSON.stringify((projects || []).map(p => ({
            id: p && p.id,
            title: p && p.title,
            description: p && p.description,
            status: p && p.status,
            priority: p && p.priority,
            branch: p && p.branch,
            updatedAt: p && p.updatedAt,
            dueDate: p && p.dueDate,
            taskCount: p && p.taskCount,
            taskDone: p && p.taskDone,
            tags: p && p.tags
        })).sort((a, b) => String(a.id || '').localeCompare(String(b.id || ''))));
    }

    function applyProjectSummaries(projects) {
        if (!Array.isArray(projects)) return;
        const byId = {};
        state.projects.forEach(p => { if (p && p.id) byId[p.id] = p; });
        projects.forEach(summary => {
            if (!summary || !summary.id) return;
            byId[summary.id] = { ...(byId[summary.id] || {}), ...summary };
        });
        const nextProjects = Object.values(byId);
        const nextSignature = projectSummarySignature(nextProjects);
        if (nextSignature === state._projectSummarySignature) return;
        state._projectSummarySignature = nextSignature;
        state.projects = nextProjects;
        updateSidebar();
        if (state.view === 'list') {
            const mc = getMainContent();
            if (mc) {
                mc.innerHTML = renderListView();
                bindListEvents();
            }
        }
    }
    window.dashboardApplyProjectSummaries = applyProjectSummaries;

    // ── PROJECT BOARD ─────────────────────────────────────────────
    async function openProject(id) {
        state.view = 'board';
        const mc = getMainContent();
        if (!mc) return;
        mc.innerHTML = renderListSkeleton();
        try {
            const d = await api.getProject(id);
            if (!d.project) throw new Error('Not found');
            state.currentProject = d.project;
            state.currentProject.scheduledCronLoading = true;
            state.meetingRequestsByTask = {};
            state.workflow.active = !!state.currentProject.workflowActive;
            state.workflow.phase = state.currentProject.workflowPhase || 'idle';
            state.workflow.currentTaskId = state.currentProject.activeTaskId || null;
            state.workflow.startMode = state.currentProject.projectExecutionStartMode || state.workflow.startMode || 'continuous';
            state.workflow.flowStopReason = state.currentProject.projectExecutionFlowStopReason || null;
            mc.innerHTML = renderBoardView();
            bindBoardEvents();
            populateBoardScoreboard();
            loadProjectBoardAuxiliaryData(id);
        } catch (e) {
            mc.innerHTML = `<div class="proj-loading">${_t('proj_failed_to_load_project')}</div>`;
        }
    }

    async function loadProjectBoardAuxiliaryData(projectId) {
        const p = state.currentProject;
        if (!p || p.id !== projectId) return;
        const jobs = [
            loadScheduledCronForCurrentProject(projectId),
            loadProjectMeetingRequests(projectId),
            checkWorkflowOnOpen(projectId)
        ];
        await Promise.allSettled(jobs);
        if (!state.currentProject || state.currentProject.id !== projectId || state.view !== 'board') return;
        rerenderProjectBoard({ lightweight: true });
    }

    function rerenderProjectBoard(opts = {}) {
        const mc = getMainContent();
        if (!mc || state.view !== 'board' || !state.currentProject) return;
        const selectedTaskId = state.currentTask && state.currentTask.id;
        mc.innerHTML = renderBoardView();
        bindBoardEvents();
        populateBoardScoreboard();
        if (selectedTaskId) {
            state.currentTask = (state.currentProject.tasks || []).find(t => t.id === selectedTaskId) || null;
        }
        if (state.currentTask && !detailPanelActiveEditor()) renderDetailPanel(state.currentTask, { preserveScroll: opts.lightweight === true });
        updateWorkflowUI();
    }

    async function loadScheduledCronForCurrentProject(projectId) {
        const p = state.currentProject;
        if (!p || (projectId && p.id !== projectId)) return;
        p.scheduledCronLoading = true;
        try {
            const d = await api.listScheduledCron(p.id);
            if (!state.currentProject || state.currentProject.id !== p.id) return;
            p.scheduledCronJobs = d.jobs || [];
            p.scheduledCronLoadError = d.error || '';
        } catch (e) {
            if (!state.currentProject || state.currentProject.id !== p.id) return;
            p.scheduledCronJobs = [];
            p.scheduledCronLoadError = e.message || 'load failed';
        } finally {
            if (state.currentProject && state.currentProject.id === p.id) p.scheduledCronLoading = false;
        }
    }

    function renderBoardView() {
        const p = state.currentProject;
        if (!p) return '';
        const cols = (p.columns || []).slice().sort((a, b) => (a.order || 0) - (b.order || 0));
        const tasks = p.tasks || [];
        const canRestartProjectPipeline = tasks.length > 0 && tasks.every(t => t.scheduledRepeatEnabled === true);

        return `
        <div class="proj-toolbar proj-board-toolbar">
            <button class="proj-btn" onclick="ProjMgr.backToList()">${_t('proj_back')}</button>
            <span class="proj-toolbar-title proj-board-title">${escHtml(p.title)}</span>
            <span class="proj-badge badge-${p.status || 'active'}">${p.status || _t('proj_status_active')}</span>
            <span class="proj-badge badge-${p.priority || 'medium'}">${p.priority || _t('proj_priority_medium')}</span>
            <div class="proj-toolbar-spacer"></div>
            ${p.projectExecutionEnabled ? `<div class="proj-exec-project-state">
                <div class="proj-exec-mode-group">
                    <label class="proj-exec-mode"><input type="radio" name="proj-exec-start-mode" value="single" ${(p.projectExecutionStartMode || 'continuous') === 'single' ? 'checked' : ''} onchange="ProjMgr.setProjectExecutionStartMode(this.value)">启动下一个任务</label>
                    <label class="proj-exec-mode"><input type="radio" name="proj-exec-start-mode" value="continuous" ${(p.projectExecutionStartMode || 'continuous') !== 'single' ? 'checked' : ''} onchange="ProjMgr.setProjectExecutionStartMode(this.value)">连续启动任务</label>
                </div>
                <div class="proj-exec-primary-actions">
                    <button class="proj-btn proj-btn-sm proj-btn-start" id="proj-exec-start-btn" onclick="ProjMgr.projectExecutionProjectStart()">▶ 启动项目</button>
                    ${canRestartProjectPipeline ? `<button class="proj-btn proj-btn-sm" id="proj-exec-restart-btn" onclick="ProjMgr.projectExecutionProjectRestart()">重启流水线</button>` : ''}
                    <button class="proj-btn proj-btn-sm proj-btn-stop hidden" id="proj-exec-stop-btn" onclick="ProjMgr.projectExecutionCancelActive()">停止当前任务</button>
                </div>
                <span class="proj-wf-status ${p.workflowActive ? 'wf-active' : ''}" id="wf-status-badge">${escHtml(p.workflowPhase || '')}</span>
                ${p.workspacePath
                    ? `<button class="proj-exec-workspace" title="点击复制：${escHtml(p.workspacePath)}" onclick="ProjMgr.copyWorkspacePath(event, '${escHtml(p.workspacePath)}')"><span>${p.workspaceKind === 'git' ? 'Git' : 'DIR'} · </span><span class="proj-exec-workspace-path">${escHtml(p.workspacePath)}</span></button>`
                    : `<span class="proj-exec-workspace"><span>${p.workspaceKind === 'git' ? 'Git' : 'DIR'} · </span><span class="proj-exec-workspace-path">未配置工作区</span></span>`}
            </div>` : `<div class="proj-workflow-controls" id="proj-wf-controls">
                <button class="proj-btn proj-btn-sm proj-btn-start" id="wf-start-btn" onclick="ProjMgr.workflowStart()" title="${_t('proj_workflow_start')}">▶ ${_t('proj_workflow_start')}</button>
                <button class="proj-btn proj-btn-sm proj-btn-stop hidden" id="wf-stop-btn" onclick="ProjMgr.workflowStop()" title="${_t('proj_workflow_stop')}">⏹ ${_t('proj_workflow_stop')}</button>
                <div class="proj-auto-toggle" title="Auto Mode: automatically process next backlog task when current finishes">
                    <label class="proj-toggle-switch">
                        <input type="checkbox" id="wf-auto-toggle" ${p.autoMode ? 'checked' : ''} onchange="ProjMgr.toggleAutoMode(this.checked)">
                        <span class="proj-toggle-slider"></span>
                    </label>
                    <span class="proj-toggle-label">${_t('proj_workflow_auto')}</span>
                </div>
                <span class="proj-wf-status" id="wf-status-badge"></span>
            </div>`}
            <button class="proj-btn proj-btn-sm" onclick="ProjMgr.openProjectResetDialog()">${_t('proj_reset')}</button>
            <button class="proj-btn proj-btn-sm" onclick="ProjMgr.editProjectDialog('${p.id}')">${_t('proj_edit')}</button>
            ${p.projectExecutionEnabled ? `<button class="proj-btn proj-btn-sm" onclick="ProjMgr.showArtifacts('${p.id}')">产物</button>` : ''}
            <button class="proj-btn proj-btn-sm" onclick="ProjMgr.showReport('${p.id}')">${_t('proj_report')}</button>
            <button class="proj-btn proj-btn-sm" onclick="ProjMgr.saveAsTemplateDialog('${p.id}')">${_t('proj_template_btn')}</button>
        </div>
        ${p.description ? `
        <div class="proj-board-header">
            <span class="proj-board-desc-toggle" onclick="this.nextElementSibling.classList.toggle('expanded');this.textContent=this.nextElementSibling.classList.contains('expanded')?'▲ ${_t('proj_hide_description')}:${_t('proj_description')}':'▼ ${_t('proj_show_description')}:${_t('proj_description')}'">▼ ${_t('proj_show_description')}</span>
            <div class="proj-board-desc">${escHtml(p.description)}</div>
        </div>` : ''}
        ${renderScheduledCronPanel(p)}
        ${renderScheduledCronHistoryPanel(p)}
        ${renderBoardScoreboard()}
        <div class="proj-board-body" id="proj-board-cols">
            <div class="proj-col proj-chat-col" id="proj-wf-chat-col">
                <div class="proj-col-header" style="border-bottom-color:#4caf50">
                    <div class="proj-col-dot" style="background:#4caf50"></div>
                    <div class="proj-col-title">${_t('proj_chat')}</div>
                    <span class="proj-wf-chat-live" id="proj-chat-live-dot"></span>
                </div>
                <div class="proj-chat-messages" id="proj-wf-chat-messages">
                    <div class="proj-chat-empty">${_t('proj_workflow_chat_empty')}</div>
                </div>
            </div>
            ${cols.map(col => renderColumn(col, tasks)).join('')}
        </div>`;
    }

    function formatCronSchedule(schedule) {
        if (!schedule) return '未设置';
        if (schedule.kind === 'every') return `每 ${Math.round((schedule.everyMs || 0) / 60000)} 分钟`;
        if (schedule.kind === 'at') return `一次 · ${new Date(schedule.at).toLocaleString()}`;
        if (schedule.kind === 'cron') return `Cron · ${schedule.expr || ''}${schedule.tz ? ` · ${schedule.tz}` : ''}`;
        return JSON.stringify(schedule);
    }

    function scheduledCronTargetLabel(job, p) {
        if (job.targetType === 'projectTask') {
            const task = (p.tasks || []).find(t => t.id === job.taskId);
            return `${_t('proj_scheduled_cron_target_task')} · ${(task && task.title) || job.taskTitle || job.taskId || _t('proj_scheduled_cron_task_missing')}`;
        }
        return _t('proj_scheduled_cron_target_workflow');
    }

    function scheduledCronRepeatGate(job, p) {
        if (job.targetType !== 'projectTask') return null;
        const task = (p.tasks || []).find(t => t.id === job.taskId);
        if (!task) return { state: 'missing', label: _t('proj_scheduled_cron_repeat_gate_missing') };
        const isDone = !!task.completedAt || String(task.executionState || '').toLowerCase() === 'done';
        const repeatEnabled = task.scheduledRepeatEnabled === true;
        if (!isDone) return { state: 'open', label: _t('proj_scheduled_cron_repeat_gate_open') };
        if (repeatEnabled) return { state: 'enabled', label: _t('proj_scheduled_cron_repeat_gate_enabled') };
        return { state: 'blocked', label: _t('proj_scheduled_cron_repeat_gate_blocked') };
    }

    function scheduledCronStatusClass(status, hasError) {
        if (hasError) return 'error';
        const value = String(status || 'pending').toLowerCase();
        if (['started', 'running', 'success', 'ok', 'enabled', 'pending_gateway_registration'].includes(value)) return 'ok';
        if (['failed', 'error', 'stop_error', 'missing_project', 'missing_target'].includes(value)) return 'error';
        if (['skipped', 'paused', 'pending', 'disengaged_completed', 'skipped_confirmation_required'].includes(value)) return 'muted';
        return 'muted';
    }

    function scheduledCronStatusLabel(status) {
        const value = String(status || 'pending').toLowerCase();
        if (value === 'pending_gateway_registration') return _t('proj_scheduled_cron_status_enabled');
        if (value === 'enabled') return _t('proj_scheduled_cron_status_enabled');
        return status || _t('proj_scheduled_cron_history_unknown');
    }

    function scheduledCronErrorSummary(error) {
        const text = String(error || '').replace(/\s+/g, ' ').trim();
        if (!text) return '';
        if (/gateway token is not configured/i.test(text)) return '';
        if (/gateway cron add is unavailable/i.test(text)) return '';
        return text.length > 180 ? `${text.slice(0, 177)}...` : text;
    }

    function scheduledCronHistoryStatusLabel(status) {
        const labels = {
            started: _t('proj_scheduled_cron_history_started'),
            skipped: _t('proj_scheduled_cron_history_skipped'),
            paused: _t('proj_scheduled_cron_history_paused'),
            failed: _t('proj_scheduled_cron_history_failed'),
            intervention_required: _t('proj_scheduled_cron_history_intervention_required'),
        };
        return labels[status] || status || _t('proj_scheduled_cron_history_unknown');
    }

    function scheduledCronHistoryTargetLabel(item) {
        if ((item.targetType || '') === 'projectTask') {
            return `${_t('proj_scheduled_cron_target_task')} · ${item.taskTitle || item.taskId || _t('proj_scheduled_cron_task_missing')}`;
        }
        return _t('proj_scheduled_cron_target_workflow');
    }

    function renderScheduledCronHistoryPanel(p) {
        if (p.scheduledCronLoading) {
            return `<details class="proj-scheduled-history-panel">
                <summary class="proj-section-header proj-scheduled-history-summary">
                    <div>
                        <div class="proj-section-title">${_t('proj_scheduled_cron_history_title')}</div>
                        <div class="proj-scheduled-cron-subtitle">${_t('proj_loading_projects')}</div>
                    </div>
                    <span class="proj-scheduled-history-chevron" aria-hidden="true"></span>
                </summary>
                <div class="proj-scheduled-cron-empty">${_t('proj_loading_projects')}</div>
            </details>`;
        }
        const history = Array.isArray(p.scheduledCronHistory) ? p.scheduledCronHistory.slice() : [];
        history.sort((a, b) => String(b.createdAt || '').localeCompare(String(a.createdAt || '')));
        const recent = history.slice(0, 20);
        return `<details class="proj-scheduled-history-panel">
            <summary class="proj-section-header proj-scheduled-history-summary">
                <div>
                    <div class="proj-section-title">${_t('proj_scheduled_cron_history_title')}</div>
                    <div class="proj-scheduled-cron-subtitle">${_t('proj_scheduled_cron_history_subtitle', { count: recent.length })}</div>
                </div>
                <span class="proj-scheduled-history-chevron" aria-hidden="true"></span>
            </summary>
            ${recent.length ? `<div class="proj-scheduled-history-list">${recent.map(item => `
                <div class="proj-scheduled-history-item status-${escHtml(item.status || 'unknown')}">
                    <div class="proj-scheduled-history-main">
                        <span class="proj-scheduled-history-badge">${escHtml(scheduledCronHistoryStatusLabel(item.status))}</span>
                        <strong>${escHtml(item.cronName || item.cronId || _t('proj_scheduled_cron_default_name'))}</strong>
                        <span>${escHtml(scheduledCronHistoryTargetLabel(item))}</span>
                    </div>
                    <div class="proj-scheduled-history-reason">${escHtml(item.message || item.reason || item.error || _t('proj_scheduled_cron_no_extra_info'))}</div>
                    <div class="proj-scheduled-history-time">${escHtml(timeAgo(item.createdAt))}</div>
                </div>`).join('')}</div>` : `<div class="proj-scheduled-cron-empty">${_t('proj_scheduled_cron_history_empty')}</div>`}
        </details>`;
    }

    function renderScheduledCronPanel(p) {
        if (p.scheduledCronLoading) {
            return `<div class="proj-scheduled-cron-panel">
                <div class="proj-section-header">
                    <div>
                        <div class="proj-section-title">${_t('proj_scheduled_cron_title')}</div>
                        <div class="proj-scheduled-cron-subtitle">${_t('proj_loading_projects')}</div>
                    </div>
                </div>
                <div class="proj-scheduled-cron-empty">${_t('proj_loading_projects')}</div>
            </div>`;
        }
        const jobs = p.scheduledCronJobs || [];
        const paused = !!p.scheduledCronPaused;
        const showRecommendation = !!p.longTermProject && jobs.length === 0;
        return `<div class="proj-scheduled-cron-panel">
            <div class="proj-section-header">
                <div>
                    <div class="proj-section-title">${_t('proj_scheduled_cron_title')}</div>
                    <div class="proj-scheduled-cron-subtitle">${paused ? _t('proj_scheduled_cron_paused_subtitle') : _t('proj_scheduled_cron_subtitle')}</div>
                </div>
                <div class="proj-scheduled-cron-actions">
                    <button class="proj-btn proj-btn-sm" onclick="ProjMgr.toggleProjectCronPause()">${paused ? _t('proj_scheduled_cron_resume') : _t('proj_scheduled_cron_pause')}</button>
                    <button class="proj-btn proj-btn-sm proj-btn-primary" onclick="ProjMgr.createProjectCronPrompt()">${_t('proj_scheduled_cron_new')}</button>
                </div>
            </div>
            ${showRecommendation ? `<div class="proj-scheduled-cron-recommendation">
                <div>
                    <strong>${_t('proj_scheduled_cron_recommend_title')}</strong>
                    <span>${_t('proj_scheduled_cron_recommend_text')}</span>
                </div>
                <button class="proj-btn proj-btn-sm proj-btn-primary" onclick="ProjMgr.createProjectCronPrompt()">${_t('proj_scheduled_cron_recommend_action')}</button>
            </div>` : ''}
            ${jobs.length ? `<div class="proj-scheduled-cron-list">${jobs.map(j => {
                const repeatGate = scheduledCronRepeatGate(j, p);
                const cronState = j.state || {};
                const lastStatus = cronState.lastStatus || 'pending';
                const statusLabel = scheduledCronStatusLabel(lastStatus);
                const lastError = scheduledCronErrorSummary(cronState.lastError);
                const statusClass = scheduledCronStatusClass(lastStatus, !!lastError);
                return `
                <div class="proj-scheduled-cron-item ${j.enabled === false ? 'is-disabled' : ''}">
                    <div class="proj-scheduled-cron-main">
                        <strong>${escHtml(j.name || j.id)}</strong>
                        <span>${escHtml(scheduledCronTargetLabel(j, p))}</span>
                        ${repeatGate ? `<span class="proj-scheduled-repeat-gate is-${repeatGate.state}">${escHtml(repeatGate.label)}</span>` : ''}
                        <code>${escHtml(formatCronSchedule(j.schedule))}</code>
                    </div>
                    <div class="proj-scheduled-cron-meta">
                        <div class="proj-scheduled-cron-status-row">
                            <span>${j.enabled === false ? 'disabled' : 'enabled'}</span>
                            <span class="proj-scheduled-cron-status is-${statusClass}">${escHtml(statusLabel)}</span>
                        </div>
                        ${lastError ? `<div class="proj-scheduled-cron-error-detail" title="${escHtml(cronState.lastError)}">
                            <span>${_t('proj_scheduled_cron_error_detail')}</span>
                            <strong>${escHtml(lastError)}</strong>
                        </div>` : ''}
                    </div>
                    <div class="proj-scheduled-cron-buttons">
                        <button class="proj-btn proj-btn-sm" onclick="ProjMgr.runProjectCron('${escHtml(j.id)}')">${_t('proj_scheduled_cron_run_now')}</button>
                        <button class="proj-btn proj-btn-sm" onclick="ProjMgr.editProjectCron('${escHtml(j.id)}')">${_t('proj_scheduled_cron_edit')}</button>
                        <button class="proj-btn proj-btn-sm" onclick="ProjMgr.toggleProjectCron('${escHtml(j.id)}', ${j.enabled !== false})">${j.enabled !== false ? _t('proj_scheduled_cron_disable') : _t('proj_scheduled_cron_enable')}</button>
                        <button class="proj-btn proj-btn-sm proj-btn-danger" onclick="ProjMgr.deleteProjectCron('${escHtml(j.id)}')">${_t('proj_scheduled_cron_delete')}</button>
                    </div>
                </div>`;
            }).join('')}</div>` : `<div class="proj-scheduled-cron-empty">${_t('proj_scheduled_cron_empty')}</div>`}
        </div>`;
    }

    function isBacklogColumn(col) {
        const title = String((col && (col._titleKey ? _t(col._titleKey) : col.title)) || '').trim().toLowerCase();
        const id = String((col && col.id) || '').trim().toLowerCase();
        return id === 'backlog' || title === 'backlog' || title === '待办';
    }

    function renderColumn(col, allTasks) {
        const tasks = allTasks.filter(t => t.columnId === col.id).slice().sort((a, b) => (a.order || 0) - (b.order || 0));
        const colTitle = col._titleKey ? _t(col._titleKey) : col.title;
        const showExecutionOrder = isBacklogColumn(col);
        return `
        <div class="proj-col" id="col-${col.id}" data-col-id="${col.id}" style="--col-color:${col.color || '#6c757d'}">
            <div class="proj-col-header">
                <div class="proj-col-dot"></div>
                <div class="proj-col-title" ondblclick="ProjMgr.renameColumn('${col.id}')">${escHtml(colTitle)}</div>
                <span class="proj-col-count">${tasks.length}</span>
                <button class="proj-col-add-btn" onclick="ProjMgr.showQuickAdd('${col.id}')" title="${_t('proj_add')}">+</button>
            </div>
            <div class="proj-col-tasks" id="tasks-${col.id}"
                ondragover="ProjMgr.onDragOver(event, '${col.id}')"
                ondragleave="ProjMgr.onDragLeave(event, '${col.id}')"
                ondrop="ProjMgr.onDrop(event, '${col.id}')">
                ${tasks.map((t, index) => renderTaskCard(t, showExecutionOrder ? index + 1 : null)).join('')}
            </div>
            <div class="proj-quick-add hidden" id="quick-add-${col.id}">
                <input class="proj-quick-add-input" id="quick-input-${col.id}" type="text" placeholder="${_t('proj_task_title_placeholder')}">
                ${state.currentProject && state.currentProject.projectExecutionEnabled ? `<label style="display:flex;align-items:center;gap:4px;font-size:10px;color:#aaa;margin-top:6px"><input type="checkbox" id="quick-acceptance-${col.id}">需要人工验收</label>` : ''}
                <div class="proj-quick-add-actions">
                    <button class="proj-btn proj-btn-sm proj-btn-primary" onclick="ProjMgr.submitQuickAdd('${col.id}')">${_t('proj_add')}</button>
                    <button class="proj-btn proj-btn-sm" onclick="ProjMgr.hideQuickAdd('${col.id}')">${_t('proj_cancel')}</button>
                </div>
            </div>
        </div>`;
    }

    function renderTaskCard(task, executionOrder = null) {
        const pc = priorityColor(task.priority);
        const due = task.dueDate;
        const overdue = due && !task.completedAt && isOverdue(due);
        const checklist = (task.checklist || []).filter(c => c && c.source !== 'meeting_action_item' && c.source !== 'meeting_risk');
        const checkDone = checklist.filter(c => c.done).length;
        const hasCheck = checklist.length > 0;
        const comments = (task.comments || []).length;
        const assignee = task.assignee ? state.agentRoster.find(a => a.key === task.assignee || a.statusKey === task.assignee || a.agentId === task.assignee) : null;
        const priorityLabel = task.priority !== 'medium' ? _t('proj_priority_' + task.priority) : '';
        const projectExecutionState = task.executionState && task.executionState !== 'backlog' ? `<span class="proj-exec-state state-${escHtml(task.executionState)}">${escHtml(projectExecutionStateLabel(task))}</span>` : '';
        const mtgRequests = state.meetingRequestsByTask[task.id] || [];
        const pendingMtgRequests = mtgRequests.filter(r => r.status === 'pending').length;
        const orderBadge = Number.isFinite(executionOrder) ? `<span class="proj-task-exec-order" title="${escHtml(_tf('proj_task_execution_order_hint', 'Project execution order', '项目执行顺序'))}">${executionOrder}</span>` : '';
        const orderClass = orderBadge ? ' has-exec-order' : '';
        return `
        <div class="proj-task-card${orderClass}" id="task-${task.id}" data-task-id="${task.id}"
            style="--pri-color:${pc}"
            draggable="true"
            ondragstart="ProjMgr.onDragStart(event, '${task.id}')"
            ondragend="ProjMgr.onDragEnd(event)"
            ontouchstart="ProjMgr.onTouchStart(event, '${task.id}')">
            ${orderBadge}
            <div class="proj-task-body">
                <div class="proj-task-title">${escHtml(task.title)}</div>
                <div class="proj-task-meta">
                    ${task.priority !== 'medium' ? `<span class="proj-badge badge-${task.priority}" style="font-size:9px">${priorityLabel}</span>` : ''}
                    ${assignee ? `<span class="proj-task-assignee" title="${escHtml(assignee.name)}">${escHtml(assignee.emoji || '👤')}</span>` : ''}
                    ${due ? `<span class="proj-task-due ${overdue ? 'overdue' : ''}" title="${formatDate(due)}">${overdue ? '⚠️' : '📅'} ${formatDate(due)}</span>` : ''}
                    ${(task.tags || []).slice(0, 2).map(t => `<span class="proj-tag" style="font-size:9px">${escHtml(t)}</span>`).join('')}
                    ${comments > 0 ? `<span class="proj-task-comment-icon">💬 ${comments}</span>` : ''}
                    ${pendingMtgRequests > 0 ? `<span class="proj-task-comment-icon proj-task-mtg-request">📊 ${pendingMtgRequests}</span>` : ''}
                    ${projectExecutionState}
                </div>
                ${hasCheck ? `
                <div class="proj-checklist-mini">
                    <div class="proj-checklist-mini-bar"><div class="proj-checklist-mini-fill" style="width:${Math.round(checkDone/checklist.length*100)}%"></div></div>
                    <span>${checkDone}/${checklist.length}</span>
                </div>` : ''}
            </div>
        </div>`;
    }

    function bindBoardEvents() {
        // Quick add key handler
        document.addEventListener('keydown', handleGlobalKeys);
        const board = document.querySelector('.proj-board-body');
        if (board && board.dataset.taskClickBound !== '1') {
            board.dataset.taskClickBound = '1';
            board.addEventListener('click', (event) => {
                const card = event.target && event.target.closest ? event.target.closest('.proj-task-card') : null;
                if (!card || !board.contains(card)) return;
                if (Date.now() - Number(board.dataset.lastTaskDragAt || 0) < 250) return;
                const interactive = event.target.closest('button,input,select,textarea,a,[contenteditable="true"]');
                if (interactive) return;
                event.preventDefault();
                event.stopPropagation();
                openTaskDetail(card.dataset.taskId);
            });
        }
    }

    // ── DRAG & DROP (HTML5) ───────────────────────────────────────
    let _dragTaskId = null;
    let _dragSourceColId = null;
    let _dropTarget = null;

    function onDragStart(e, taskId) {
        _dragTaskId = taskId;
        const card = document.getElementById(`task-${taskId}`);
        const p = state.currentProject;
        const task = p && p.tasks.find(t => t.id === taskId);
        if (task) {
            _dragSourceColId = task.columnId;
        }
        if (card) card.classList.add('dragging');
        e.dataTransfer.effectAllowed = 'move';
        e.dataTransfer.setData('text/plain', taskId);
    }

    function onDragEnd(e) {
        const board = document.querySelector('.proj-board-body');
        if (board) board.dataset.lastTaskDragAt = String(Date.now());
        if (_dragTaskId) {
            const card = document.getElementById(`task-${_dragTaskId}`);
            if (card) card.classList.remove('dragging');
        }
        // Remove all col highlights
        document.querySelectorAll('.proj-col').forEach(c => c.classList.remove('drag-over'));
        document.querySelectorAll('.proj-drop-line.visible').forEach(l => l.classList.remove('visible'));
        _dragTaskId = null;
        _dragSourceColId = null;
    }

    function onDragOver(e, colId) {
        e.preventDefault();
        e.dataTransfer.dropEffect = 'move';
        const col = document.getElementById(`col-${colId}`);
        if (col) col.classList.add('drag-over');
        // Determine insert position
        const tasksEl = document.getElementById(`tasks-${colId}`);
        if (tasksEl) {
            insertDropIndicator(tasksEl, e.clientY);
        }
    }

    function onDragLeave(e, colId) {
        const col = document.getElementById(`col-${colId}`);
        if (col && !col.contains(e.relatedTarget)) {
            col.classList.remove('drag-over');
            const tasksEl = document.getElementById(`tasks-${colId}`);
            if (tasksEl) {
                tasksEl.querySelectorAll('.proj-drop-line').forEach(l => l.remove());
            }
        }
    }

    function insertDropIndicator(container, clientY) {
        container.querySelectorAll('.proj-drop-line').forEach(l => l.remove());
        const cards = Array.from(container.querySelectorAll('.proj-task-card'));
        let insertBefore = null;
        for (const card of cards) {
            if (card.id === `task-${_dragTaskId}`) continue;
            const rect = card.getBoundingClientRect();
            if (clientY < rect.top + rect.height / 2) {
                insertBefore = card;
                break;
            }
        }
        const line = document.createElement('div');
        line.className = 'proj-drop-line visible';
        if (insertBefore) container.insertBefore(line, insertBefore);
        else container.appendChild(line);
    }

    function onDrop(e, colId) {
        e.preventDefault();
        const taskId = e.dataTransfer.getData('text/plain') || _dragTaskId;
        if (!taskId) return;
        const col = document.getElementById(`col-${colId}`);
        if (col) col.classList.remove('drag-over');
        const p = state.currentProject;
        if (!p) return;
        const task = p.tasks.find(t => t.id === taskId);
        if (!task) return;
        if (isProjectExecutionColumnLocked(task) && task.columnId !== colId) {
            toast(_tf('proj_exec_column_locked_toast', 'Project Execution controls this task column until the current state finishes.', '项目执行状态机正在接管该任务的列位置，当前状态结束前不能拖动到其他列。'), 'warning');
            return;
        }
        // Determine new order
        const tasksEl = document.getElementById(`tasks-${colId}`);
        const line = tasksEl && tasksEl.querySelector('.proj-drop-line');
        let newOrder = 0;
        if (tasksEl) {
            const cards = Array.from(tasksEl.querySelectorAll('.proj-task-card'));
            if (line) {
                const idx = cards.indexOf(line.previousElementSibling);
                newOrder = idx + 1;
            } else {
                newOrder = cards.filter(c => c.id !== `task-${taskId}`).length;
            }
            tasksEl.querySelectorAll('.proj-drop-line').forEach(l => l.remove());
        }
        // Optimistic update
        const oldColId = task.columnId;
        task.columnId = colId;
        // Re-sort tasks in affected columns
        const colTasks = p.tasks.filter(t => t.columnId === colId && t.id !== taskId).sort((a, b) => (a.order || 0) - (b.order || 0));
        colTasks.splice(newOrder, 0, task);
        colTasks.forEach((t, i) => t.order = i);
        // Re-render board
        const mc = getMainContent();
        if (mc) {
            mc.innerHTML = renderBoardView();
            bindBoardEvents();
        }
        // Persist
        const updates = p.tasks.map(t => ({ id: t.id, columnId: t.columnId, order: t.order || 0 }));
        api.reorderTasks(p.id, updates).catch(() => toast(_t('proj_save_failed'), 'error'));
        // Also update task's columnId via task update for activity log
        if (oldColId !== colId) {
            api.updateTask(p.id, taskId, { columnId: colId, order: task.order }).then(result => {
                // Check if a score was awarded (task moved to Done)
                if (result && result.task && result.task._scoreAwarded) {
                    animateTaskComplete(taskId, result.task._scoreAwarded);
                    populateBoardScoreboard();
                }
            }).catch(() => {});
            // Check if target is a "done" column and show preview animation
            const targetCol = p.columns.find(c => c.id === colId);
            if (targetCol && ['done', 'completed', 'verified', 'published', 'fixed', 'closed'].includes(targetCol.title.toLowerCase())) {
                // Optimistic complete animation (full one triggers after API confirms score)
                const card = document.getElementById(`task-${taskId}`);
                if (card) card.classList.add('anim-complete');
            }
        }
    }

    // ── TOUCH DRAG ────────────────────────────────────────────────
    let _touchTask = null;
    let _touchGhost = null;
    let _touchLongPressTimer = null;
    let _touchActive = false;

    function onTouchStart(e, taskId) {
        _touchLongPressTimer = setTimeout(() => {
            _touchActive = true;
            _touchTask = taskId;
            const card = document.getElementById(`task-${taskId}`);
            if (!card) return;
            // Create ghost
            _touchGhost = card.cloneNode(true);
            _touchGhost.id = 'proj-touch-ghost';
            _touchGhost.className = card.className + ' drag-ghost';
            _touchGhost.style.cssText = `position:fixed;pointer-events:none;z-index:10000;width:${card.offsetWidth}px;opacity:0.85;transform:rotate(2deg);`;
            document.body.appendChild(_touchGhost);
            card.style.opacity = '0.3';
            e.preventDefault();
        }, 400);
        e.target.addEventListener('touchmove', onTouchMove, { passive: false });
        e.target.addEventListener('touchend', onTouchEnd);
    }

    function onTouchMove(e) {
        clearTimeout(_touchLongPressTimer);
        if (!_touchActive || !_touchGhost) return;
        e.preventDefault();
        const touch = e.touches[0];
        _touchGhost.style.left = (touch.clientX - 20) + 'px';
        _touchGhost.style.top = (touch.clientY - 20) + 'px';
        // Find column under finger
        _touchGhost.style.display = 'none';
        const el = document.elementFromPoint(touch.clientX, touch.clientY);
        _touchGhost.style.display = '';
        // Highlight target col
        document.querySelectorAll('.proj-col').forEach(c => c.classList.remove('drag-over'));
        const colEl = el && el.closest('[data-col-id]');
        if (colEl) colEl.classList.add('drag-over');
    }

    function onTouchEnd(e) {
        clearTimeout(_touchLongPressTimer);
        if (!_touchActive || !_touchTask) { _touchActive = false; return; }
        const touch = e.changedTouches[0];
        if (_touchGhost) { _touchGhost.remove(); _touchGhost = null; }
        document.querySelectorAll('.proj-col').forEach(c => c.classList.remove('drag-over'));
        const card = document.getElementById(`task-${_touchTask}`);
        if (card) card.style.opacity = '';
        // Find drop target
        const el = document.elementFromPoint(touch.clientX, touch.clientY);
        const colEl = el && el.closest('[data-col-id]');
        if (colEl) {
            const colId = colEl.dataset.colId;
            simulateDrop(_touchTask, colId);
        }
        _touchTask = null;
        _touchActive = false;
    }

    function simulateDrop(taskId, colId) {
        const p = state.currentProject;
        if (!p) return;
        const task = p.tasks.find(t => t.id === taskId);
        if (!task || task.columnId === colId) return;
        const oldColId = task.columnId;
        task.columnId = colId;
        const colTasks = p.tasks.filter(t => t.columnId === colId).sort((a, b) => (a.order || 0) - (b.order || 0));
        colTasks.forEach((t, i) => t.order = i);
        const mc = getMainContent();
        if (mc) { mc.innerHTML = renderBoardView(); bindBoardEvents(); }
        const updates = p.tasks.map(t => ({ id: t.id, columnId: t.columnId, order: t.order || 0 }));
        api.reorderTasks(p.id, updates).catch(() => {});
        if (oldColId !== colId) {
            api.updateTask(p.id, taskId, { columnId: colId }).then(result => {
                if (result && result.task && result.task._scoreAwarded) {
                    animateTaskComplete(taskId, result.task._scoreAwarded);
                    populateBoardScoreboard();
                }
            }).catch(() => {});
            // Optimistic complete animation for done columns
            const targetCol = p.columns.find(c => c.id === colId);
            if (targetCol && ['done', 'completed', 'verified', 'published', 'fixed', 'closed'].includes(targetCol.title.toLowerCase())) {
                const card = document.getElementById(`task-${taskId}`);
                if (card) card.classList.add('anim-complete');
            }
        }
    }

    // ── QUICK ADD ─────────────────────────────────────────────────
    function showQuickAdd(colId) {
        const qa = document.getElementById(`quick-add-${colId}`);
        if (!qa) return;
        qa.classList.remove('hidden');
        const inp = document.getElementById(`quick-input-${colId}`);
        if (inp) {
            inp.focus();
            inp.onkeydown = (e) => { if (e.key === 'Enter') submitQuickAdd(colId); if (e.key === 'Escape') hideQuickAdd(colId); };
        }
    }
    function hideQuickAdd(colId) {
        const qa = document.getElementById(`quick-add-${colId}`);
        if (qa) qa.classList.add('hidden');
    }
    async function submitQuickAdd(colId) {
        const inp = document.getElementById(`quick-input-${colId}`);
        const title = inp && inp.value.trim();
        if (!title) { hideQuickAdd(colId); return; }
        const p = state.currentProject;
        if (!p) return;
        try {
            const acceptance = document.getElementById(`quick-acceptance-${colId}`);
            const body = { title, columnId: colId };
            if (p.projectExecutionEnabled) body.requiresUserAcceptance = acceptance ? acceptance.checked : false;
            const d = await api.createTask(p.id, body);
            if (d.task) {
                p.tasks.push(d.task);
                const mc = getMainContent();
                if (mc) { mc.innerHTML = renderBoardView(); bindBoardEvents(); }
                animateTaskSpawn(d.task.id);
                toast(_t('proj_task_added'), 'success');
                populateBoardScoreboard();
            }
        } catch (e) { toast(_t('proj_failed_add_task'), 'error'); }
    }

    // ── COLUMN MANAGEMENT ─────────────────────────────────────────
    async function addColumn() {
        const p = state.currentProject;
        if (!p) return;
        const title = prompt(_t('proj_column_title_prompt'));
        if (!title) return;
        const colors = ['#6c757d', '#0d6efd', '#ffc107', '#fd7e14', '#198754', '#17a2b8', '#dc3545'];
        const color = colors[p.columns.length % colors.length];
        const newCol = { id: genId(), title, color, order: p.columns.length };
        p.columns.push(newCol);
        try {
            await api.updateColumns(p.id, p.columns);
            const mc = getMainContent();
            if (mc) { mc.innerHTML = renderBoardView(); bindBoardEvents(); }
        } catch (e) { toast(_t('proj_failed_add_column'), 'error'); }
    }

    function renameColumn(colId) {
        const p = state.currentProject;
        if (!p) return;
        const col = p.columns.find(c => c.id === colId);
        if (!col) return;
        const titleEl = document.querySelector(`#col-${colId} .proj-col-title`);
        if (!titleEl) return;
        const inp = document.createElement('input');
        inp.className = 'proj-col-title-input';
        inp.value = col.title;
        titleEl.replaceWith(inp);
        inp.focus();
        inp.select();
        async function save() {
            const newTitle = inp.value.trim() || col.title;
            col.title = newTitle;
            try { await api.updateColumns(p.id, p.columns); } catch (e) {}
            const mc = getMainContent();
            if (mc) { mc.innerHTML = renderBoardView(); bindBoardEvents(); }
        }
        inp.onblur = save;
        inp.onkeydown = (e) => { if (e.key === 'Enter') inp.blur(); if (e.key === 'Escape') { inp.value = col.title; inp.blur(); } };
    }

    // ── TASK DETAIL PANEL ─────────────────────────────────────────
    function openTaskDetail(taskId) {
        const p = state.currentProject;
        if (!p) return;
        const task = p.tasks.find(t => t.id === taskId);
        if (!task) return;
        state.currentTask = task;
        renderDetailPanel(task);
        loadTaskMeetingRequests(task.id);
        const panel = document.getElementById('proj-detail-panel');
        if (panel) panel.classList.add('open');
    }

    function closeDetailPanel() {
        state.currentTask = null;
        const panel = document.getElementById('proj-detail-panel');
        if (panel) panel.classList.remove('open');
    }

    function detailPanelActiveEditor() {
        const active = document.activeElement;
        return !!(active && active.closest && active.closest('#proj-detail-panel') && ['INPUT', 'TEXTAREA', 'SELECT'].includes(active.tagName));
    }

    function renderDetailPanel(task, opts = {}) {
        const panel = document.getElementById('proj-detail-panel');
        if (!panel) return;
        const existingBody = panel.querySelector('.proj-detail-body');
        const preserveScroll = opts.preserveScroll === true;
        const previousScrollTop = preserveScroll && existingBody ? existingBody.scrollTop : 0;
        const previousScrollHeight = preserveScroll && existingBody ? existingBody.scrollHeight : 0;
        const previousClientHeight = preserveScroll && existingBody ? existingBody.clientHeight : 0;
        const wasNearBottom = preserveScroll && existingBody
            ? previousScrollTop + previousClientHeight >= previousScrollHeight - 24
            : false;
        // Preserve unsaved description text from textarea before re-render
        const existingDescEl = document.getElementById('detail-desc');
        if (existingDescEl && task && existingDescEl.dataset.taskId === task.id) {
            task.description = existingDescEl.value;
        }
        const p = state.currentProject;
        const cols = (p && p.columns) || [];
        const agents = state.agentRoster;
        const checklist = visibleChecklistItems(task).map(entry => entry.item);
        const checkDone = checklist.filter(c => c.done).length;
        const comments = task.comments || [];
        const commentsExpanded = !!state.expandedCommentTasks[task.id];
        const visibleComments = commentsExpanded ? comments : comments.slice(-3);
        const hiddenCommentCount = Math.max(0, comments.length - visibleComments.length);
        const reviewItems = (task.reviewCheck && task.reviewCheck.length) ? task.reviewCheck : (task.lastReviewCheck || []);
        const reviewTitle = (task.reviewCheck && task.reviewCheck.length) ? '🔍 Review Check' : ((task.lastReviewCheck && task.lastReviewCheck.length) ? '🕘 Last Failed Review' : '🔍 Review Check');
        const activity = (p && p.activity || []).filter(a => a.taskId === task.id).slice().reverse().slice(0, 20);
        const meetingRequests = activeTaskMeetingRequests(task, state.meetingRequestsByTask[task.id] || []);
        const projectExecution = !!(p && p.projectExecutionEnabled);
        const meetingActionItems = Array.isArray(task.meetingActionItems) ? task.meetingActionItems : [];
        const meetingDiscussionPoints = Array.isArray(task.meetingDiscussionPoints) ? task.meetingDiscussionPoints : [];
        const meetingRecords = taskMeetingRecords(task, meetingDiscussionPoints, meetingActionItems);
        const evidence = task.evidence || {};
        const reviewResult = task.reviewResult || {};
        const attemptId = task.activeAttemptId || (task.attempts && task.attempts.length ? task.attempts[task.attempts.length - 1].id : '');
        const evidenceAttemptId = evidence.attemptId || attemptId;
        const projectExecutionReviewHtml = reviewResult.status ? `
            <div class="proj-exec-review state-${escHtml(reviewResult.status)}">
                <div><strong>${escHtml(_tf('proj_exec_reviewer', 'Reviewer', '审查人'))}</strong> ${escHtml(projectExecutionReviewStatusLabel(reviewResult.status))}</div>
                ${reviewResult.summary ? `<div class="proj-exec-summary">${escHtml(reviewResult.summary)}</div>` : ''}
                ${reviewResult.rationale ? `<div class="proj-exec-meta">${escHtml(reviewResult.rationale)}</div>` : ''}
                ${(reviewResult.items || []).slice(0, 12).map(item => `<code>${escHtml(typeof item === 'string' ? item : (item.text || item.summary || JSON.stringify(item)))}</code>`).join('')}
            </div>` : '';
        const projectExecutionActionsHtml = (() => {
            if (task.executionState === 'executing' || task.executionState === 'reworking') return `<button class="proj-btn proj-btn-sm proj-btn-stop" onclick="ProjMgr.projectExecutionCancel('${task.id}', '${escHtml(attemptId)}')">停止执行</button>`;
            if (task.executionState === 'reviewing') return `<button class="proj-btn proj-btn-sm" disabled>审查中</button>`;
            if (task.executionState === 'awaiting_meeting_resolution') return `<button class="proj-btn proj-btn-sm" disabled>${escHtml(projectExecutionStateLabel(task))}</button>`;
            if (task.executionState === 'execution_complete') return `
                <button class="proj-btn proj-btn-sm proj-btn-start" onclick="ProjMgr.projectExecutionReviewStart('${task.id}', '${escHtml(evidenceAttemptId)}')">${escHtml(_tf('proj_exec_start_review', 'Start review', '启动审查'))}</button>
                <button class="proj-btn proj-btn-sm" onclick="ProjMgr.projectExecutionStart('${task.id}', '', { resetExecutionContext: true })">${escHtml(_tf('proj_exec_rerun', 'Run again', '重新执行'))}</button>`;
            if (task.executionState === 'awaiting_user_acceptance') {
                const rejectLabel = reviewResult.status === 'skipped'
                    ? _tf('proj_exec_rework_skipped', 'Return for rework', '退回返工')
                    : _tf('proj_exec_rework_rejected', 'Reject for rework', '拒绝返工');
                return `
                <button class="proj-btn proj-btn-sm proj-btn-start" onclick="ProjMgr.projectExecutionAccept('${task.id}', 'accept', '${escHtml(reviewResult.attemptId || evidenceAttemptId)}')">${escHtml(_tf('proj_exec_accept', 'Accept', '验收通过'))}</button>
                <button class="proj-btn proj-btn-sm" onclick="ProjMgr.projectExecutionAccept('${task.id}', 'reject_and_rework', '${escHtml(reviewResult.attemptId || evidenceAttemptId)}')">${escHtml(rejectLabel)}</button>
                <button class="proj-btn proj-btn-sm proj-btn-stop" onclick="ProjMgr.projectExecutionAccept('${task.id}', 'mark_blocked', '${escHtml(reviewResult.attemptId || evidenceAttemptId)}')">${escHtml(_tf('proj_exec_mark_blocked', 'Mark blocked', '标记阻塞'))}</button>`;
            }
            return `<button class="proj-btn proj-btn-sm proj-btn-start" onclick="ProjMgr.projectExecutionStart('${task.id}', '', { resetExecutionContext: true })">${escHtml(_tf('proj_exec_start_task', 'Start this task', '启动此任务'))}</button>`;
        })();

        panel.innerHTML = `
        <div class="proj-detail-header">
            <span style="font-size:11px;color:#888">${_t('proj_task_detail')}</span>
            <div style="display:flex;gap:6px">
                <button class="proj-btn proj-btn-sm proj-btn-danger" onclick="ProjMgr.deleteCurrentTask()">${_t('proj_delete')}</button>
                <button class="proj-btn proj-btn-sm" onclick="ProjMgr.duplicateTask('${task.id}')">${_t('proj_edit')}</button>
                <button class="proj-detail-close" onclick="ProjMgr.closeDetailPanel()">✕</button>
            </div>
        </div>
        <div class="proj-detail-body">
            <input class="proj-detail-title-input" id="detail-title" value="${escHtml(task.title)}" placeholder="${_t('proj_task_title_input')}">

            <div class="proj-section">
                <div class="proj-field">
                    <label class="proj-field-label">${_t('proj_column_title')}</label>
                    <select class="proj-detail-select" id="detail-col" ${isProjectExecutionColumnLocked(task) ? 'disabled title="项目执行状态机正在接管列位置"' : ''} onchange="ProjMgr.updateTaskField('columnId', this.value)">
                        ${cols.map(c => `<option value="${c.id}" ${task.columnId === c.id ? 'selected' : ''}>${escHtml(c._titleKey ? _t(c._titleKey) : c.title)}</option>`).join('')}
                    </select>
                    ${isProjectExecutionColumnLocked(task) ? `<div class="proj-form-help">${escHtml(_tf('proj_exec_column_locked_hint', 'Column is controlled by Project Execution until this state finishes.', '当前列由项目执行状态机接管，状态结束前不能手动修改。'))}</div>` : ''}
                </div>
                <div style="display:flex;gap:8px">
                    <div class="proj-field" style="flex:1">
                        <label class="proj-field-label">${_t('proj_priority_label')}</label>
                        <select class="proj-detail-select" id="detail-pri" onchange="ProjMgr.updateTaskField('priority', this.value)">
                            <option value="critical" ${task.priority === 'critical' ? 'selected' : ''}>${_t('proj_priority_critical')}</option>
                            <option value="high" ${task.priority === 'high' ? 'selected' : ''}>${_t('proj_priority_high')}</option>
                            <option value="medium" ${task.priority === 'medium' ? 'selected' : ''}>${_t('proj_priority_medium')}</option>
                            <option value="low" ${task.priority === 'low' ? 'selected' : ''}>${_t('proj_priority_low')}</option>
                        </select>
                    </div>
                    <div class="proj-field" style="flex:1">
                        <label class="proj-field-label">${_t('proj_due_date')}</label>
                        <input class="proj-detail-input" type="date" id="detail-due" value="${task.dueDate ? task.dueDate.split('T')[0] : ''}" onchange="ProjMgr.updateTaskField('dueDate', this.value ? new Date(this.value).toISOString() : null)">
                    </div>
                </div>
                <div class="proj-field">
                    <label class="proj-field-label">${_t('proj_assignee')}</label>
                    <select class="proj-detail-select" id="detail-assignee" onchange="ProjMgr.updateTaskField('assignee', this.value || null)">
                        <option value="">— ${_t('proj_unassigned')} —</option>
                        ${agents.map(a => {
                            const id = a.key || a.statusKey || a.id;
                            const blocked = a.assignable === false || a.systemRole === 'archive_manager';
                            return `<option value="${id}" ${task.assignee === id ? 'selected' : ''} ${blocked ? 'disabled' : ''}>${escHtml((a.emoji || '👤') + ' ' + a.name + (blocked ? '（系统角色，不可分配）' : ''))}</option>`;
                        }).join('')}
                    </select>
                </div>
                ${projectExecution ? `<div style="display:flex;gap:8px">
                    <div class="proj-field" style="flex:1">
                        <label class="proj-field-label">${escHtml(_tf('proj_exec_executor_agent', 'Executor agent', '执行 Agent'))}</label>
                        <select class="proj-detail-select" id="detail-executor-agent" onchange="ProjMgr.updateTaskField('executorAgentId', this.value || null)">${projectExecutionAgentOptions(task.executorAgentId || task.assignee || '')}</select>
                    </div>
                    <div class="proj-field" style="flex:1">
                        <label class="proj-field-label">${escHtml(_tf('proj_exec_reviewer', 'Reviewer', '审查人'))}</label>
                        <select class="proj-detail-select" onchange="ProjMgr.updateTaskField('reviewerAgentId', this.value || null)">${projectExecutionAgentOptions(task.reviewerAgentId || '')}</select>
                    </div>
                </div>` : ''}
                ${projectExecution ? `<div class="proj-field">
                    <label class="proj-form-label" style="display:flex;align-items:center;gap:6px">
                        <input type="checkbox" ${task.requiresUserAcceptance === true ? 'checked' : ''} onchange="ProjMgr.updateTaskField('requiresUserAcceptance', this.checked)">
                        ${escHtml(_tf('proj_exec_requires_user_acceptance', 'Require user acceptance', '需要人工验收'))}
                    </label>
                    <div class="proj-exec-meta">${escHtml(_tf('proj_exec_requires_user_acceptance_hint', 'When disabled, a passed review completes the task directly and continuous mode moves to the next task.', '关闭后，审查通过会直接完成；连续启动任务模式会继续下一个任务。'))}</div>
                </div>` : ''}
                <div class="proj-field">
                    <label class="proj-form-label" style="display:flex;align-items:center;gap:6px">
                        <input type="checkbox" ${task.scheduledRepeatEnabled === true ? 'checked' : ''} onchange="ProjMgr.updateTaskField('scheduledRepeatEnabled', this.checked)">
                        ${_t('proj_task_scheduled_repeat_enabled')}
                    </label>
                    <div class="proj-exec-meta">${_t('proj_task_scheduled_repeat_hint')}</div>
                </div>
                ${projectExecution ? `<div class="proj-field">
                    <label class="proj-form-label" style="display:flex;align-items:center;gap:6px">
                        <input type="checkbox" ${task.allowReviewerlessExecution === true ? 'checked' : ''} onchange="ProjMgr.updateTaskField('allowReviewerlessExecution', this.checked)">
                        ${escHtml(_tf('proj_exec_allow_reviewerless', 'Allow skipping independent review when no reviewer is configured', '允许没有 Reviewer 时跳过独立审查'))}
                    </label>
                    <div class="proj-exec-meta">${escHtml(_tf('proj_exec_allow_reviewerless_hint', 'When enabled, tasks without a configured reviewer run without the skip-review confirmation.', '开启后，如果任务和项目都没有配置 Reviewer，启动任务或项目流水线时会直接执行，不再弹出跳过审查确认。'))}</div>
                </div>` : ''}
                <div class="proj-field">
                    <label class="proj-field-label">${_t('proj_tags')}</label>
                    <div class="proj-tag-input-wrap" id="detail-tags-wrap" onclick="document.getElementById('detail-tag-in').focus()">
                        ${(task.tags || []).map(t => `<span class="proj-tag">${escHtml(t)}<span class="tag-remove" onclick="ProjMgr.removeTag('${escHtml(t)}')">×</span></span>`).join('')}
                        <input class="proj-tag-input" id="detail-tag-in" placeholder="${_t('proj_add_tag')}" onkeydown="ProjMgr.handleTagKey(event)">
                    </div>
                </div>
            </div>

            ${projectExecution ? `<div class="proj-section proj-exec-panel">
                <div class="proj-section-header"><span class="proj-section-title">${escHtml(_tf('proj_exec_panel_title', 'Project Execution', '项目执行与审查'))}</span><span class="proj-exec-state state-${escHtml(task.executionState || 'backlog')}">${task.requiresUserAcceptance === true ? escHtml(_tf('proj_exec_user_acceptance_required_badge', 'User acceptance required', '需要人工验收')) + ' · ' : escHtml(_tf('proj_exec_user_acceptance_not_required_badge', 'No user acceptance', '无需人工验收')) + ' · '}${escHtml(projectExecutionStateLabel(task))}</span></div>
                <div class="proj-exec-actions">
                    ${projectExecutionActionsHtml}
                </div>
                ${renderMeetingBlocker(task)}
                ${renderProjectExecutionError(task)}
                ${renderProjectExecutionBlockedReason(task)}
                ${evidence.capturedAt ? `<div class="proj-exec-evidence">
                    <div><strong>${escHtml(_tf('proj_exec_summary_title', 'Execution summary', '执行总结'))}</strong></div><div class="proj-exec-summary">${escHtml(evidence.executorSummary || _tf('proj_none', 'None', '无'))}</div>
                    <div><strong>${escHtml(_tf('proj_exec_changed_files', 'Changed files', '修改文件'))}</strong> ${(evidence.changedFiles || []).length}</div>
                    ${(evidence.changedFiles || []).slice(0, 20).map(f => `<code>${escHtml(f)}</code>`).join('')}
                    ${renderProjectExecutionTestResults(evidence.testResults)}
                    <div class="proj-exec-meta">${escHtml(_tf('proj_exec_duration', 'Duration', '耗时'))} ${Math.round((evidence.durationMs || 0) / 1000)}s · ${escHtml(evidence.providerStatus || '')}</div>
                </div>` : `<div class="proj-exec-meta">${escHtml(_tf('proj_exec_evidence_pending', 'Execution evidence will appear after the task finishes. Completed execution requires independent review and user acceptance.', '执行证据将在任务结束后显示。执行完成后需要独立审查和用户验收。'))}</div>`}
                ${projectExecutionReviewHtml}
                ${task.reworkFeedback ? `<div class="proj-exec-meta">${escHtml(_tf('proj_exec_rework_feedback', 'Rework feedback', '返工反馈'))}：${escHtml(task.reworkFeedback)}</div>` : ''}
            </div>` : ''}

            ${meetingRecords.length ? `<div class="proj-section proj-meeting-discussion-panel">
                <div class="proj-section-header">
                    <span class="proj-section-title">${escHtml(_t('proj_meeting_records'))}</span>
                    <span style="font-size:10px;color:#888">${meetingRecords.length}</span>
                </div>
                <div class="proj-meeting-action-list">
                    ${meetingRecords.map(record => {
                        const risks = Array.isArray(record.risks) ? record.risks.filter(Boolean) : [];
                        const actions = Array.isArray(record.actionItems) ? record.actionItems.filter(a => a && (a.title || a.item)) : [];
                        const decisionText = record.decision || record.summary || '';
                        const statusClass = statusClassName(record.status || record.outcome || 'note');
                        return `
                    <div class="proj-meeting-action-item status-${escHtml(statusClass)}">
                        <div class="proj-meeting-action-top">
                            <span class="proj-meeting-action-title">${escHtml(decisionText || _t('proj_meeting_record_no_summary'))}</span>
                            <span class="proj-meeting-action-badge">${escHtml(meetingRecordStatusLabel(record.status || record.outcome))}</span>
                        </div>
                        ${record.summary && record.summary !== decisionText ? `<div class="proj-exec-meta">${escHtml(record.summary)}</div>` : ''}
                        ${risks.length ? `<div class="proj-exec-meta"><strong>${escHtml(_t('proj_meeting_record_risks'))}</strong> ${risks.map(r => escHtml(r)).join('；')}</div>` : ''}
                        ${actions.length ? `<div class="proj-exec-meta"><strong>${escHtml(_t('proj_meeting_record_actions'))}</strong> ${actions.map(a => escHtml(a.title || a.item || '') + (a.owner ? ` (${escHtml(a.owner)})` : '')).join('；')}</div>` : ''}
                        <div class="proj-exec-meta">
                            ${record.meetingId ? `${escHtml(_t('proj_meeting_record_meeting'))}: ${escHtml(record.meetingId)}` : ''}
                            ${record.requestId ? `${record.meetingId ? ' · ' : ''}${escHtml(_t('proj_meeting_record_request'))}: ${escHtml(record.requestId)}` : ''}
                            ${(record.appliedAt || record.createdAt) ? `${(record.meetingId || record.requestId) ? ' · ' : ''}${timeAgo(record.appliedAt || record.createdAt)}` : ''}
                        </div>
                    </div>`; }).join('')}
                </div>
            </div>` : ''}

            ${meetingActionItems.length ? `<div class="proj-section proj-meeting-action-panel">
                <div class="proj-section-header">
                    <span class="proj-section-title">${escHtml(_t('proj_meeting_action_items'))}</span>
                    <span style="font-size:10px;color:#888">${meetingActionItems.filter(a => a.status === 'completed').length}/${meetingActionItems.length}</span>
                </div>
                <div class="proj-meeting-action-list">
                    ${meetingActionItems.map(item => {
                        const statusClass = statusClassName(item.status || 'pending');
                        return `
                    <div class="proj-meeting-action-item status-${escHtml(statusClass)}">
                        <div class="proj-meeting-action-top">
                            <span class="proj-meeting-action-title">${escHtml(item.title || '')}</span>
                            <span class="proj-meeting-action-badge">${escHtml(meetingActionStatusLabel(item.status))}</span>
                        </div>
                        ${item.description ? `<div class="proj-exec-meta">${escHtml(item.description)}</div>` : ''}
                        <div class="proj-exec-meta">
                            ${escHtml(_t('proj_meeting_action_owner'))}: ${escHtml(item.owner || _t('proj_unassigned'))}
                            ${item.meetingId ? ` · ${escHtml(_t('proj_meeting_action_source'))}: ${escHtml(item.meetingId)}` : ''}
                        </div>
                    </div>`; }).join('')}
                </div>
            </div>` : ''}

            <div class="proj-section">
                <div class="proj-section-header"><span class="proj-section-title">AI 会议申请</span></div>
                <div class="proj-meeting-requests" id="detail-meeting-requests">
                    ${renderTaskMeetingRequests(meetingRequests)}
                </div>
            </div>

            <div class="proj-section">
                <div class="proj-section-header"><span class="proj-section-title">${_t('proj_description')}</span></div>
                <div class="proj-desc-tabs">
                    <button class="proj-desc-tab active" id="desc-tab-edit" onclick="ProjMgr.switchDescTab('edit')">${_t('proj_edit_desc')}</button>
                    <button class="proj-desc-tab" id="desc-tab-preview" onclick="ProjMgr.switchDescTab('preview')">${_t('proj_preview')}</button>
                </div>
                <textarea class="proj-detail-textarea" id="detail-desc" data-task-id="${escHtml(task.id)}" rows="4" placeholder="${_t('proj_description')} (Markdown supported)">${escHtml(task.description || '')}</textarea>
                <div class="proj-desc-preview hidden" id="detail-desc-preview">${simpleMarkdown(task.description || '')}</div>
                <div style="text-align:right;margin-top:4px">
                    <button class="proj-btn proj-btn-sm proj-btn-gold" onclick="ProjMgr.saveDescription()">${_t('proj_save')}</button>
                </div>
            </div>

            <div class="proj-section">
                <div class="proj-section-header">
                    <span class="proj-section-title">${_t('proj_checklist')}</span>
                    <span style="font-size:10px;color:#888">${checkDone}/${checklist.length}</span>
                </div>
                ${checklist.length ? `
                <div class="proj-checklist-progress">
                    <div class="proj-checklist-progress-track">
                        <div class="proj-checklist-progress-fill" style="width:${checklist.length ? Math.round(checkDone/checklist.length*100) : 0}%"></div>
                    </div>
                    <span style="font-size:10px;color:#888">${checklist.length ? Math.round(checkDone/checklist.length*100) : 0}%</span>
                </div>` : ''}
                <ul class="proj-checklist" id="detail-checklist">
                    ${checklist.map((c, i) => `
                    <li class="proj-checklist-item ${c.done ? 'done' : ''}">
                        <input type="checkbox" ${c.done ? 'checked' : ''} onchange="ProjMgr.toggleChecklistItem(${i}, this.checked)">
                        <span class="proj-checklist-item-text" ondblclick="ProjMgr.editChecklistItem(${i})" title="${_t('proj_edit')}">${escHtml(c.text)}</span>
                        <button class="proj-checklist-edit" onclick="ProjMgr.editChecklistItem(${i})" title="${_t('proj_edit')}">✏️</button>
                        <button class="proj-checklist-delete" onclick="ProjMgr.deleteChecklistItem(${i})">×</button>
                    </li>`).join('')}
                </ul>
                <div style="display:flex;gap:6px;margin-top:6px">
                    <input class="proj-detail-input" id="new-checklist-item" type="text" placeholder="${_t('proj_add_checklist_item')}" onkeydown="if(event.key==='Enter')ProjMgr.addChecklistItem()" style="flex:1">
                    <button class="proj-btn proj-btn-sm" onclick="ProjMgr.addChecklistItem()">${_t('proj_add')}</button>
                </div>
            </div>

            ${reviewItems.length ? `
            <div class="proj-section">
                <div class="proj-section-header"><span class="proj-section-title">${reviewTitle}</span></div>
                <div class="proj-review-check-list" id="detail-review-check">
                    ${reviewItems.map((rc, i) => {
                        const icon = {'pass':'✅','needs_more_work':'⚠️','did_not_pass':'❌','requires_user_review':'👤'}[rc.status] || '❓';
                        const statusClass = 'review-' + (rc.status || 'pending').replace(/_/g, '-');
                        const editable = !!(task.reviewCheck && task.reviewCheck.length);
                        return `
                        <div class="proj-review-item ${statusClass}">
                            <span class="proj-review-icon">${icon}</span>
                            <span class="proj-review-text">${escHtml(rc.text)}</span>
                            ${editable ? `
                            <select class="proj-review-select" onchange="ProjMgr.updateReviewItemStatus(${i}, this.value)">
                                <option value="pass" ${rc.status === 'pass' ? 'selected' : ''}>${_t('proj_review_pass')}</option>
                                <option value="needs_more_work" ${rc.status === 'needs_more_work' ? 'selected' : ''}>${_t('proj_review_needs_more_work')}</option>
                                <option value="did_not_pass" ${rc.status === 'did_not_pass' ? 'selected' : ''}>${_t('proj_review_did_not_pass')}</option>
                                <option value="requires_user_review" ${rc.status === 'requires_user_review' ? 'selected' : ''}>${_t('proj_review_requires_user')}</option>
                            </select>` : `<span style="font-size:11px;color:#777">${_t('proj_preserved_prior_review')}</span>`}
                        </div>`;
                    }).join('')}
                </div>
                ${(task.reviewCheck && task.reviewCheck.length) ? `
                <div style="text-align:right;margin-top:6px">
                    <button class="proj-btn proj-btn-sm proj-btn-gold" onclick="ProjMgr.saveReviewCheck()">${_t('proj_save_review')}</button>
                </div>` : ''}
            </div>` : ''}

            <div class="proj-section">
                <div class="proj-section-header">
                    <span class="proj-section-title">${_t('proj_comments')}</span>
                    ${comments.length > 3 ? `<button class="proj-link-btn" onclick="ProjMgr.toggleComments('${task.id}')">${commentsToggleLabel(commentsExpanded, hiddenCommentCount)}</button>` : ''}
                </div>
                <div class="proj-comments-list" id="detail-comments">
                    ${comments.length === 0 ? `<div style="font-size:11px;color:#555">${_t('proj_no_comments')}</div>` : ''}
                    ${visibleComments.map(c => `
                    <div class="proj-comment">
                        <div class="proj-comment-header">
                            <span class="proj-comment-author">${escHtml(c.author)}</span>
                            <span class="proj-comment-time">${timeAgo(c.createdAt)}</span>
                        </div>
                        <div class="proj-comment-text">${simpleMarkdown(c.text)}</div>
                    </div>`).join('')}
                </div>
                <textarea class="proj-detail-textarea" id="detail-comment-input" rows="2" placeholder="${_t('proj_add_comment_placeholder')}"></textarea>
                <div style="text-align:right;margin-top:4px">
                    <button class="proj-btn proj-btn-sm proj-btn-gold" onclick="ProjMgr.submitComment()">${_t('proj_post_comment')}</button>
                </div>
            </div>

            ${activity.length > 0 ? `
            <div class="proj-section">
                <div class="proj-section-header"><span class="proj-section-title">${_t('proj_activity')}</span></div>
                <div class="proj-activity-list">
                    ${activity.map(a => `
                    <div class="proj-activity-item">
                        <div class="proj-activity-dot"></div>
                        <span class="proj-activity-time">${timeAgo(a.at)}</span>
                        <span>${escHtml(a.detail)}</span>
                    </div>`).join('')}
                </div>
            </div>` : ''}
        </div>`;

        // Bind title auto-save
        const titleEl = document.getElementById('detail-title');
        if (titleEl) {
            let titleTimer;
            titleEl.oninput = () => {
                clearTimeout(titleTimer);
                titleTimer = setTimeout(() => {
                    if (titleEl.value.trim()) saveTaskField('title', titleEl.value.trim());
                }, 800);
            };
        }

        // Bind description auto-save (debounced)
        const descEl = document.getElementById('detail-desc');
        if (descEl) {
            descEl.oninput = () => {
                clearTimeout(state._descAutoSaveTimer);
                state._descAutoSaveTimer = setTimeout(() => {
                    saveDescription();
                }, 1500);
            };
        }
        // Save button: cancel debounce then save immediately
        const descSaveBtn = document.querySelector('.proj-btn-gold[onclick*="saveDescription"]');
        if (descSaveBtn) {
            descSaveBtn.onclick = (e) => {
                e.preventDefault();
                clearTimeout(state._descAutoSaveTimer);
                saveDescription();
            };
        }
        if (preserveScroll) {
            const nextBody = panel.querySelector('.proj-detail-body');
            if (nextBody) {
                nextBody.scrollTop = wasNearBottom
                    ? nextBody.scrollHeight
                    : Math.min(previousScrollTop, Math.max(0, nextBody.scrollHeight - nextBody.clientHeight));
            }
        }
    }

    function toggleCommentsAction(taskId) {
        if (!taskId) return;
        const body = document.querySelector('.proj-detail-body');
        const scrollTop = body ? body.scrollTop : 0;
        state.expandedCommentTasks[taskId] = !state.expandedCommentTasks[taskId];
        if (state.currentTask && state.currentTask.id === taskId) {
            renderDetailPanel(state.currentTask);
            const nextBody = document.querySelector('.proj-detail-body');
            if (nextBody) nextBody.scrollTop = scrollTop;
        }
    }

    function renderTaskMeetingRequests(requests) {
        requests = sortMeetingRequestsByStatusThenTime(requests);
        if (!requests.length) return `<div style="font-size:11px;color:#555">当前任务暂无 AI 会议申请</div>`;
        return requests.map(req => {
            const proposal = req.originalProposal || {};
            const status = req.status || 'pending';
            const statusText = status === 'confirmed' ? '已确认' : (status === 'rejected' ? '已拒绝' : '待确认');
            const rejectReason = req.review && req.review.rejectionReason ? `<div class="proj-exec-warning">${escHtml(req.review.rejectionReason)}</div>` : '';
            const autoConfirmReason = req.review && req.review.autoConfirmed
                ? `<div class="proj-exec-meta">${escHtml(req.review.autoConfirmLabel || req.review.autoConfirmReason || '已自动批准')}</div>`
                : '';
            return `
            <div class="proj-meeting-request state-${escHtml(status)}">
                <div class="proj-meeting-request-head">
                    <strong>${escHtml(proposal.topic || proposal.goal || 'AI 会议申请')}</strong>
                    <span class="proj-meeting-request-status state-${escHtml(status)}">${statusText}</span>
                </div>
                <div class="proj-exec-meta">请求 AI：${escHtml(req.requestingAgentId || '')}</div>
                <div class="proj-exec-summary">${escHtml(proposal.cannotCompleteAloneReason || '')}</div>
                ${autoConfirmReason}
                ${rejectReason}
            </div>`;
        }).join('');
    }

    function activeTaskMeetingRequests(task, requests) {
        const blocker = task && task.meetingBlocker;
        return sortMeetingRequestsByStatusThenTime((requests || []).filter(req => {
            if (!req || !req.blockingTask) return true;
            const taskBlocker = req.taskBlocker || {};
            if (taskBlocker.resolvedAt) return false;
            const status = taskBlocker.status || req.status || '';
            if (['resolved_continue', 'blocked', 'cleared'].includes(status)) return false;
            if (blocker && blocker.requestId === req.id && blocker.resolvedAt) return false;
            return ['pending', 'confirmed', 'rejected', 'needs_user_decision'].includes(status) || ['pending', 'confirmed', 'rejected'].includes(req.status || '');
        }));
    }

    function meetingRequestProcessed(req) {
        const status = req && req.status;
        if (status === 'confirmed' || status === 'rejected') return true;
        const review = req && req.review || {};
        const conversion = req && req.conversion || {};
        return !!(review.confirmedAt || review.rejectedAt || conversion.meetingId);
    }

    function meetingRequestTime(req) {
        const raw = req && (req.updatedAt || req.createdAt) || '';
        const ms = Date.parse(raw);
        return Number.isFinite(ms) ? ms : 0;
    }

    function sortMeetingRequestsByStatusThenTime(requests) {
        return (requests || []).slice().sort((a, b) => {
            const statusDelta = Number(meetingRequestProcessed(a)) - Number(meetingRequestProcessed(b));
            if (statusDelta) return statusDelta;
            return meetingRequestTime(b) - meetingRequestTime(a);
        });
    }

    function projectExecutionSummaryLabel(project) {
        const phase = String(project && (project.projectExecutionPhase || project.workflowPhase || '') || '').trim();
        const active = !!(project && project.projectExecutionActive);
        if (!active) return '';
        const labels = {
            validating: _tf('proj_exec_state_validating', 'Validating', '校验中'),
            executing: _tf('proj_exec_state_executing', 'Executing', '执行中'),
            retrying: _tf('proj_exec_state_retrying', 'Retrying', '重试中'),
            reworking: _tf('proj_exec_state_reworking', 'Reworking', '返工中'),
            reviewing: _tf('proj_exec_state_reviewing', 'Reviewing', '审查中'),
            execution_complete: _tf('proj_exec_state_execution_complete', 'Execution complete', '执行完成'),
            awaiting_user_acceptance: _tf('proj_exec_state_awaiting_user_acceptance', 'Awaiting user acceptance', '等待用户验收'),
            awaiting_meeting_resolution: _tf('proj_exec_state_awaiting_meeting_resolution', 'Awaiting meeting resolution', '等待会议结论'),
            blocked: _tf('proj_exec_state_blocked', 'Blocked', '阻塞'),
            done: _tf('proj_exec_state_done', 'Done', '已完成'),
        };
        if (labels[phase]) return labels[phase];
        if (active) return _tf('proj_workflow_in_progress', 'Agent working...', '代理工作中...');
        return phase;
    }

    function projectExecutionStateLabel(task) {
        const state = task && (task.executionState || 'backlog');
        const labels = {
            backlog: _tf('proj_exec_state_backlog', 'Backlog', '待办'),
            executing: _tf('proj_exec_state_executing', 'Executing', '执行中'),
            reworking: _tf('proj_exec_state_reworking', 'Reworking', '返工中'),
            execution_complete: _tf('proj_exec_state_execution_complete', 'Execution complete', '执行完成'),
            reviewing: _tf('proj_exec_state_reviewing', 'Reviewing', '审查中'),
            awaiting_user_acceptance: _tf('proj_exec_state_awaiting_user_acceptance', 'Awaiting user acceptance', '等待用户验收'),
            awaiting_meeting_resolution: _tf('proj_exec_state_awaiting_meeting_resolution', 'Awaiting meeting resolution', '等待会议结论'),
            retrying: _tf('proj_exec_state_retrying', 'Retrying', '重试中'),
            blocked: _tf('proj_exec_state_blocked', 'Blocked', '阻塞'),
            done: _tf('proj_exec_state_done', 'Done', '已完成'),
        };
        const label = labels[state] || state;
        return label;
    }

    function isProjectExecutionColumnLocked(task) {
        const stateValue = task && task.executionState;
        return ['executing', 'retrying', 'reworking', 'reviewing', 'execution_complete', 'awaiting_user_acceptance', 'awaiting_meeting_resolution'].includes(stateValue);
    }

    function projectExecutionHasRunningTask(project) {
        const runningStates = ['validating', 'executing', 'retrying', 'reworking', 'reviewing'];
        return ((project && project.tasks) || []).some(task => task.activeAttemptId && runningStates.includes(task.executionState));
    }

    function projectExecutionReviewStatusLabel(status) {
        const raw = String(status || '').trim();
        const labels = {
            pass: _tf('proj_exec_review_status_pass', 'Passed', '已通过'),
            skipped: _tf('proj_exec_review_status_skipped', 'Skipped', '已跳过'),
            needs_more_work: _tf('proj_exec_review_status_needs_more_work', 'Needs more work', '需要返工'),
            blocked: _tf('proj_exec_review_status_blocked', 'Blocked', '已阻塞'),
        };
        return labels[raw] || raw;
    }

    function compactProjectExecutionEvidenceLine(value, maxLen = 260) {
        let text = '';
        if (typeof value === 'string') {
            text = value;
        } else if (value && typeof value === 'object') {
            text = value.name || value.title || value.command || value.text || value.summary || value.status || '';
            const status = value.status || value.result || value.outcome || '';
            if (status && !String(text).includes(String(status))) text = `${text} · ${status}`;
            if (!text) text = '结构化结果';
        } else {
            text = String(value == null ? '' : value);
        }
        text = String(text || '').trim();
        if ((text.startsWith('{') && text.endsWith('}')) || (text.startsWith('[') && text.endsWith(']'))) {
            try {
                const parsed = JSON.parse(text);
                if (parsed && typeof parsed === 'object') {
                    text = parsed.finalAssistantVisibleText || parsed.summary || parsed.text || parsed.message || '';
                    const tests = Array.isArray(parsed.tests) ? parsed.tests : (Array.isArray(parsed.testResults) ? parsed.testResults : []);
                    if (!text && tests.length) text = `测试结果：${tests.length} 项`;
                    if (!text) text = '结构化执行结果';
                }
            } catch (e) { /* keep original text */ }
        }
        text = text.replace(/\s+/g, ' ').trim();
        if (text.length > maxLen) text = text.slice(0, maxLen).trimEnd() + '...[truncated]';
        return text;
    }

    function renderProjectExecutionTestResults(results) {
        const items = (Array.isArray(results) ? results : [])
            .map(item => compactProjectExecutionEvidenceLine(item))
            .filter(Boolean)
            .slice(0, 20);
        if (!items.length) return '';
        return `<div><strong>${escHtml(_tf('proj_exec_test_results', 'Test results', '测试结果'))}</strong></div>${items.map(t => `<code>${escHtml(t)}</code>`).join('')}`;
    }

    function renderMeetingBlocker(task) {
        const blocker = task && task.meetingBlocker;
        if (!blocker || task.executionState !== 'awaiting_meeting_resolution') return '';
        const status = blocker.status || 'pending';
        const rejected = status === 'rejected';
        const safeTitle = rejected
            ? _tf('proj_meeting_blocker_rejected_title', 'Meeting request rejected, waiting for user action', '会议申请已拒绝，等待用户处理')
            : _tf('proj_meeting_blocker_title', 'Awaiting meeting resolution', '等待会议结论');
        const safeMessage = rejected
            ? _tf('proj_meeting_blocker_rejected_body', 'The task will not continue automatically after a meeting request is rejected. Choose continue execution, mark blocked, or request a new meeting.', '会议申请被拒绝后，任务不会自动继续。请选择继续执行、标记阻塞或重新申请会议。')
            : _tf('proj_meeting_blocker_body', 'This task has an issue that must be aligned in a meeting. Project Execution will not continue this task until the meeting reaches explicit consensus.', '任务存在需要开会统一的问题。会议明确达成一致前，项目执行不会继续推进此任务。');
        return `
            <div class="proj-meeting-blocker state-${escHtml(status)}">
                <div class="proj-meeting-blocker-title">${escHtml(safeTitle)}</div>
                <div class="proj-exec-summary">${escHtml(safeMessage)}</div>
                <div class="proj-exec-meta">
                    ${blocker.requestId ? `<span>request ${escHtml(String(blocker.requestId).slice(0, 8))}</span>` : ''}
                    ${blocker.meetingId ? `<span>meeting ${escHtml(String(blocker.meetingId).slice(0, 8))}</span>` : ''}
                    ${blocker.rejectionReason ? `<span>${escHtml(blocker.rejectionReason)}</span>` : ''}
                </div>
                <div class="proj-exec-actions">
                    <button class="proj-btn proj-btn-sm" onclick="ProjMgr.viewMeetingBlocker(${jsArg(blocker.requestId || '')}, ${jsArg(blocker.meetingId || '')})">${escHtml(_tf('proj_meeting_blocker_view', 'View meeting', '查看会议'))}</button>
                    <button class="proj-btn proj-btn-sm proj-btn-start" onclick="ProjMgr.projectExecutionMeetingBlocker('${task.id}', 'continue_execution')">${escHtml(_tf('proj_meeting_blocker_continue', 'Continue execution', '继续执行'))}</button>
                    <button class="proj-btn proj-btn-sm proj-btn-stop" onclick="ProjMgr.projectExecutionMeetingBlocker('${task.id}', 'mark_blocked')">${escHtml(_tf('proj_meeting_blocker_mark_blocked', 'Mark blocked', '标记阻塞'))}</button>
                    <button class="proj-btn proj-btn-sm" onclick="ProjMgr.projectExecutionMeetingBlocker('${task.id}', 'reopen_meeting')">${escHtml(_tf('proj_meeting_blocker_reopen', 'Request new meeting', '重新申请会议'))}</button>
                </div>
            </div>`;
    }

    function renderProjectExecutionError(task) {
        const err = task && task.lastError ? String(task.lastError).trim() : '';
        if (!err) return '';
        const text = projectExecutionErrorText(err);
        return `
            <div class="proj-exec-warning">
                <strong>${escHtml(_tf('proj_exec_last_error_title', 'Task start failed', '任务启动失败'))}</strong>
                <div>${escHtml(text)}</div>
            </div>`;
    }

    function renderProjectExecutionBlockedReason(task) {
        const reason = task && task.blockedReason ? String(task.blockedReason).trim() : '';
        if (!reason) return '';
        const text = projectExecutionReasonText(reason);
        return `
            <div class="proj-exec-warning">
                <strong>${escHtml(_tf('proj_exec_blocked_reason_title', 'Blocked reason', '阻塞原因'))}</strong>
                <div>${escHtml(text)}</div>
            </div>`;
    }

    function projectExecutionErrorText(err) {
        return projectExecutionReasonText(err);
    }

    function projectExecutionReasonText(err) {
        const raw = String(err || '').trim();
        if (!raw) return '';
        const normalized = raw.toLowerCase();
        if (normalized === 'previous_execution_not_resumable' || normalized === 'the previous execution could not be resumed after service restart.') {
            return _tf(
                'proj_exec_error_previous_not_resumable',
                'The previous execution could not be resumed after the service restarted. Start the task again to create a new execution attempt.',
                '服务重启后无法恢复上一次执行。请重新启动任务，创建新的执行尝试。'
            );
        }
        if (normalized === 'checklist_incomplete' || normalized === 'checklist is incomplete; finish all acceptance checklist items before marking the task done.') {
            return _tf(
                'proj_exec_error_checklist_incomplete',
                'The acceptance checklist is incomplete. Continue working on the unfinished checklist items before marking the task done.',
                '验收清单尚未完成。请先继续处理未完成的清单项，再标记任务完成。'
            );
        }
        if (normalized === 'checklist_empty' || normalized === 'acceptance checklist is empty; create and complete acceptance checklist items before marking the task done.') {
            return _tf(
                'proj_exec_error_checklist_empty',
                'The task has no acceptance checklist. Create checklist items first, or explicitly skip the empty checklist if the task truly does not need one.',
                '当前任务还没有验收清单。请先创建 checklist；如果确实不需要 checklist，可以在验收确认中显式跳过空清单。'
            );
        }
        if (normalized === 'project_execution_column_locked') {
            return _tf(
                'proj_exec_error_column_locked',
                'Project Execution is controlling this task column. Wait for the state machine transition, or stop/reset execution before moving it manually.',
                '项目执行状态机正在接管该任务的列位置。请等待状态自动流转，或先停止/重置执行后再手动移动。'
            );
        }
        if (normalized.includes('llm request timed out') || normalized.includes('gatewayclientrequesterror') || normalized.includes('failovererror') || normalized.includes('cooldown')) {
            return _tf(
                'proj_exec_error_provider_timeout',
                'The model gateway timed out or entered cooldown. Virtual Office will retry transient failures once; if it remains blocked, wait briefly or switch to another available executor/provider and start the task again.',
                '模型网关超时或进入冷却。Virtual Office 会对临时失败自动重试一次；如果仍然阻塞，请稍后重试，或切换到可用的执行 Agent / provider 后重新启动任务。'
            );
        }
        if (normalized === 'executor_required' || normalized === 'a valid executor agent is required') {
            return _tf(
                'proj_exec_error_executor_required',
                'Set an Executor Agent on this task or configure a default executor for the project before starting Project Execution.',
                '请先在任务详情里设置“执行 Agent”，或在项目里配置默认执行 Agent，然后再启动任务。'
            );
        }
        return raw;
    }

    function projectExecutionApiErrorText(response) {
        const code = response && response.code ? String(response.code) : '';
        const raw = response && response.error ? String(response.error) : code;
        let text = projectExecutionReasonText(code || raw);
        const unfinished = response && Array.isArray(response.unfinishedChecklist) ? response.unfinishedChecklist : [];
        if ((code === 'checklist_incomplete' || code === 'checklist_empty') && unfinished.length) {
            text += '\n' + unfinished.slice(0, 8).map(item => `- ${item && item.text ? item.text : ''}`).filter(Boolean).join('\n');
        }
        return text;
    }

    async function loadProjectMeetingRequests(projectId) {
        const p = state.currentProject;
        if (!p || (projectId && p.id !== projectId)) return;
        try {
            const d = await api.listMeetingRequests(p.id);
            if (!state.currentProject || state.currentProject.id !== p.id) return;
            const grouped = {};
            (d.requests || []).forEach(req => {
                const taskId = req.source && req.source.taskId;
                if (!taskId) return;
                (grouped[taskId] = grouped[taskId] || []).push(req);
            });
            state.meetingRequestsByTask = grouped;
        } catch (e) {
            if (!state.currentProject || state.currentProject.id !== p.id) return;
            state.meetingRequestsByTask = {};
        }
    }

    async function loadTaskMeetingRequests(taskId) {
        const p = state.currentProject;
        if (!p || !taskId) return;
        try {
            const d = await api.listMeetingRequests(p.id, taskId);
            state.meetingRequestsByTask[taskId] = d.requests || [];
            const current = state.currentTask;
            if (current && current.id === taskId) {
                const el = document.getElementById('detail-meeting-requests');
                if (el) el.innerHTML = renderTaskMeetingRequests(activeTaskMeetingRequests(current, state.meetingRequestsByTask[taskId] || []));
            }
            const mc = getMainContent();
            if (mc && state.view === 'board') {
                mc.querySelectorAll('.proj-task-mtg-request').forEach(() => {});
            }
        } catch (e) { /* non-fatal */ }
    }

    function openMeetingRequestsQueue() {
        if (typeof openMeetingsDashboard === 'function') openMeetingsDashboard();
        if (typeof switchMtgTab === 'function') switchMtgTab('requests');
    }

    function viewMeetingBlocker(requestId, meetingId) {
        if (typeof openMeetingReference === 'function') {
            openMeetingReference({ requestId, meetingId });
            return;
        }
        openMeetingRequestsQueue();
    }

    function switchDescTab(tab) {
        const editArea = document.getElementById('detail-desc');
        const preview = document.getElementById('detail-desc-preview');
        const editTab = document.getElementById('desc-tab-edit');
        const prevTab = document.getElementById('desc-tab-preview');
        if (tab === 'preview') {
            if (editArea) editArea.classList.add('hidden');
            if (preview) { preview.classList.remove('hidden'); preview.innerHTML = simpleMarkdown(editArea && editArea.value || ''); }
            if (editTab) editTab.classList.remove('active');
            if (prevTab) prevTab.classList.add('active');
        } else {
            if (editArea) editArea.classList.remove('hidden');
            if (preview) preview.classList.add('hidden');
            if (editTab) editTab.classList.add('active');
            if (prevTab) prevTab.classList.remove('active');
        }
    }

    async function saveDescription() {
        const el = document.getElementById('detail-desc');
        if (!el) { toast(_t('proj_description_not_found'), 'error'); return; }
        if (!state.currentTask || !state.currentProject) { toast(_t('proj_no_task_selected'), 'error'); return; }
        const desc = el.value;
        // Ensure currentTask references the live project task (handles stale refs after poll refresh)
        const liveTask = state.currentProject.tasks.find(t => t.id === state.currentTask.id);
        if (liveTask && liveTask !== state.currentTask) {
            state.currentTask = liveTask;
        }
        const task = state.currentTask;
        const projId = state.currentProject.id;
        const taskId = task.id;
        task.description = desc;
        // Visual feedback: disable save button during save
        const saveBtn = el.parentElement && el.parentElement.querySelector('.proj-btn-gold');
        if (saveBtn) { saveBtn.disabled = true; saveBtn.textContent = '⏳ ' + _t('proj_saving'); }
        try {
            await api.updateTask(projId, taskId, { description: desc });
            // Also update the card on the board
            const cardEl = document.getElementById(`task-${taskId}`);
            if (cardEl) {
                const newCard = document.createElement('div');
                newCard.innerHTML = renderTaskCard(task);
                const rendered = newCard.firstElementChild;
                if (rendered) cardEl.replaceWith(rendered);
            }
            if (saveBtn) { saveBtn.textContent = '✅ ' + _t('proj_saved'); }
            toast(_t('proj_description_saved'), 'success');
            setTimeout(() => { if (saveBtn) { saveBtn.textContent = '💾 ' + _t('proj_save'); saveBtn.disabled = false; } }, 1500);
        } catch (e) {
            if (saveBtn) { saveBtn.textContent = '💾 ' + _t('proj_save'); saveBtn.disabled = false; }
            toast(_t('proj_failed_save_desc'), 'error');
        }
    }

    async function saveTaskField(field, value) {
        let task = state.currentTask;
        const p = state.currentProject;
        if (!task || !p) return;
        // Ensure we reference the live task object (handles stale refs after poll refresh)
        const liveTask = p.tasks.find(t => t.id === task.id);
        if (liveTask && liveTask !== task) {
            state.currentTask = liveTask;
            task = liveTask;
        }
        task[field] = value;
        try {
            const result = await api.updateTask(p.id, task.id, { [field]: value });
            if (result && result.task) {
                Object.assign(task, result.task);
            }
            // Re-render board card
            const cardEl = document.getElementById(`task-${task.id}`);
            if (cardEl) {
                const newCard = document.createElement('div');
                newCard.innerHTML = renderTaskCard(task);
                const rendered = newCard.firstElementChild;
                if (rendered) cardEl.replaceWith(rendered);
            }
        } catch (e) { toast(_t('proj_save_failed'), 'error'); }
    }

    async function updateTaskField(field, value) {
        await saveTaskField(field, value);
        if (field === 'assignee') {
            const executorSelect = document.getElementById('detail-executor-agent');
            if (executorSelect && state.currentTask && state.currentTask.executorAgentId) {
                executorSelect.value = state.currentTask.executorAgentId;
            }
        }
        if (field === 'columnId') {
            // Re-render board
            const mc = getMainContent();
            if (mc && state.currentProject) { mc.innerHTML = renderBoardView(); bindBoardEvents(); }
            // Re-open detail panel
            const task = state.currentTask;
            if (task) { openTaskDetail(task.id); }
        }
    }

    // Checklist
    function visibleChecklistItems(task) {
        return ((task && task.checklist) || [])
            .map((item, index) => ({ item, index }))
            .filter(entry => entry.item && entry.item.source !== 'meeting_action_item' && entry.item.source !== 'meeting_risk');
    }

    function visibleChecklistSourceIndexes(task) {
        return visibleChecklistItems(task).map(entry => entry.index);
    }

    async function toggleChecklistItem(idx, done) {
        const task = state.currentTask;
        if (!task || !task.checklist) return;
        const sourceIdx = visibleChecklistSourceIndexes(task)[idx];
        if (sourceIdx === undefined || !task.checklist[sourceIdx]) return;
        task.checklist[sourceIdx].done = done;
        const li = document.querySelectorAll('#detail-checklist .proj-checklist-item')[idx];
        if (li) li.classList.toggle('done', done);
        await saveTaskField('checklist', task.checklist);
        renderDetailPanel(task);
    }
    async function deleteChecklistItem(idx) {
        const task = state.currentTask;
        if (!task || !task.checklist) return;
        const sourceIdx = visibleChecklistSourceIndexes(task)[idx];
        if (sourceIdx === undefined) return;
        task.checklist.splice(sourceIdx, 1);
        await saveTaskField('checklist', task.checklist);
        renderDetailPanel(task);
    }
    async function addChecklistItem() {
        const inp = document.getElementById('new-checklist-item');
        const text = inp && inp.value.trim();
        if (!text) return;
        const task = state.currentTask;
        if (!task) return;
        if (!task.checklist) task.checklist = [];
        task.checklist.push({ id: genId(), text, done: false });
        if (inp) inp.value = '';
        await saveTaskField('checklist', task.checklist);
        renderDetailPanel(task);
    }

    function editChecklistItem(idx) {
        const task = state.currentTask;
        if (!task || !task.checklist) return;
        const sourceIdx = visibleChecklistSourceIndexes(task)[idx];
        if (sourceIdx === undefined || !task.checklist[sourceIdx]) return;
        const item = task.checklist[sourceIdx];
        const li = document.querySelectorAll('#detail-checklist .proj-checklist-item')[idx];
        if (!li) return;
        const textSpan = li.querySelector('.proj-checklist-item-text');
        if (!textSpan) return;
        // Replace text span with an input
        const inp = document.createElement('input');
        inp.type = 'text';
        inp.className = 'proj-checklist-edit-input';
        inp.value = item.text;
        textSpan.replaceWith(inp);
        inp.focus();
        inp.select();
        // Hide edit button while editing
        const editBtn = li.querySelector('.proj-checklist-edit');
        if (editBtn) editBtn.style.display = 'none';

        async function save() {
            const newText = inp.value.trim();
            if (newText && newText !== item.text) {
                item.text = newText;
                await saveTaskField('checklist', task.checklist);
            }
            renderDetailPanel(task);
        }
        inp.onblur = save;
        inp.onkeydown = (e) => {
            if (e.key === 'Enter') { e.preventDefault(); inp.blur(); }
            if (e.key === 'Escape') { inp.value = item.text; inp.blur(); }
        };
    }

    // Tags
    function handleTagKey(e) {
        if (e.key === 'Enter' || e.key === ',') {
            e.preventDefault();
            const val = e.target.value.trim().replace(/,$/, '');
            if (val) addTag(val);
        }
    }
    async function addTag(tag) {
        const task = state.currentTask;
        if (!task) return;
        if (!task.tags) task.tags = [];
        if (task.tags.includes(tag)) return;
        task.tags.push(tag);
        const inp = document.getElementById('detail-tag-in');
        if (inp) inp.value = '';
        await saveTaskField('tags', task.tags);
        renderDetailPanel(task);
    }
    async function removeTag(tag) {
        const task = state.currentTask;
        if (!task || !task.tags) return;
        task.tags = task.tags.filter(t => t !== tag);
        await saveTaskField('tags', task.tags);
        renderDetailPanel(task);
    }

    // Comments
    async function submitComment() {
        const inp = document.getElementById('detail-comment-input');
        const text = inp && inp.value.trim();
        if (!text) return;
        const task = state.currentTask;
        const p = state.currentProject;
        if (!task || !p) return;
        try {
            const d = await api.addComment(p.id, task.id, { text, author: 'user' });
            if (d.comment) {
                if (!task.comments) task.comments = [];
                task.comments.push(d.comment);
                if (inp) inp.value = '';
                renderDetailPanel(task);
                toast(_t('proj_comment_added'), 'success');
            }
        } catch (e) { toast(_t('proj_failed_add_comment'), 'error'); }
    }

    // Delete / Duplicate task
    async function deleteCurrentTask() {
        const task = state.currentTask;
        const p = state.currentProject;
        if (!task || !p) return;
        const confirmMsg = _t('proj_delete_task_confirm').replace('{title}', task.title);
        if (!confirm(confirmMsg)) return;
        try {
            closeDetailPanel();
            // Animate the deletion first
            await animateTaskDelete(task.id);
            await api.deleteTask(p.id, task.id);
            p.tasks = p.tasks.filter(t => t.id !== task.id);
            const mc = getMainContent();
            if (mc) { mc.innerHTML = renderBoardView(); bindBoardEvents(); }
            toast(_t('proj_task_deleted'), 'success');
            populateBoardScoreboard();
        } catch (e) { toast(_t('proj_failed_delete_task'), 'error'); }
    }
    async function duplicateTask(taskId) {
        const p = state.currentProject;
        if (!p) return;
        const src = p.tasks.find(t => t.id === taskId);
        if (!src) return;
        const copy = { title: src.title + ' (copy)', description: src.description, columnId: src.columnId, priority: src.priority, tags: [...(src.tags || [])], checklist: (src.checklist || []).map(c => ({ ...c, id: genId(), done: false })), requiresUserAcceptance: src.requiresUserAcceptance === true, allowReviewerlessExecution: src.allowReviewerlessExecution === true, scheduledRepeatEnabled: src.scheduledRepeatEnabled === true };
        try {
            const d = await api.createTask(p.id, copy);
            if (d.task) { p.tasks.push(d.task); const mc = getMainContent(); if (mc) { mc.innerHTML = renderBoardView(); bindBoardEvents(); } toast(_t('proj_task_duplicated'), 'success'); }
        } catch (e) { toast(_t('proj_failed_duplicate'), 'error'); }
    }

    // ── NEW PROJECT DIALOG ────────────────────────────────────────
    function newProjectDialog(templateId) {
        showFormModal('new-project', {}, templateId);
    }

    function editProjectDialog(id) {
        const p = state.currentProject || state.projects.find(x => x.id === id);
        if (!p) return;
        showFormModal('edit-project', p);
    }

    function projectExecutionAgentOptions(selected) {
        return `<option value="">— 请选择 —</option>` + state.agentRoster.map(a => {
            const id = a.key || a.statusKey || a.id;
            const blocked = a.assignable === false || a.systemRole === 'archive_manager';
            return `<option value="${escHtml(id)}" ${selected === id ? 'selected' : ''} ${blocked ? 'disabled' : ''}>${escHtml((a.emoji || 'Agent') + ' ' + a.name + (blocked ? '（系统角色，不可分配）' : ''))}</option>`;
        }).join('');
    }

    function showFormModal(type, data, extra) {
        const overlay = document.getElementById('proj-form-overlay');
        if (!overlay) return;
        overlay.classList.remove('hidden');

        if (type === 'new-project') {
            overlay.innerHTML = `
            <div class="proj-form-modal" style="position:static;padding:0;background:transparent" onclick="event.stopPropagation()">
            <div class="proj-form-box">
                <div class="proj-form-title">${_t('proj_new_project_title')}</div>
                <div class="proj-form-group">
                    <label class="proj-form-label">${_t('proj_new_project_title_placeholder')} *</label>
                    <input class="proj-form-input" id="pf-title" type="text" placeholder="${_t('proj_new_project_title_placeholder')}" autofocus>
                </div>
                <div class="proj-form-group">
                    <label class="proj-form-label">${_t('proj_description')}</label>
                    <textarea class="proj-form-textarea" id="pf-desc" placeholder="${_t('proj_new_project_desc_placeholder')}"></textarea>
                </div>
                <div class="proj-form-row">
                    <div class="proj-form-group">
                        <label class="proj-form-label">${_t('proj_status_active')}</label>
                        <select class="proj-form-select" id="pf-status">
                            <option value="active">${_t('proj_status_active')}</option>
                            <option value="paused">${_t('proj_status_paused')}</option>
                        </select>
                    </div>
                    <div class="proj-form-group">
                        <label class="proj-form-label">${_t('proj_priority_label')}</label>
                        <select class="proj-form-select" id="pf-priority">
                            <option value="critical">${_t('proj_priority_critical')}</option>
                            <option value="high">${_t('proj_priority_high')}</option>
                            <option value="medium" selected>${_t('proj_priority_medium')}</option>
                            <option value="low">${_t('proj_priority_low')}</option>
                        </select>
                    </div>
                </div>
                <div class="proj-form-group">
                    <label class="proj-form-label">
                        <input type="checkbox" id="pf-project-execution" checked onchange="ProjMgr.toggleProjectExecutionFields(this.checked)">
                        可执行项目
                    </label>
                    <div style="font-size:10px;color:#888;margin-top:4px">默认启用 Project Execution。留空时系统会自动创建“项目-时间戳”工作区。</div>
                </div>
                <div class="proj-form-group">
                    <label class="proj-form-label">
                        <input type="checkbox" id="pf-long-term-project">
                        ${_t('proj_long_term_project')}
                    </label>
                    <div style="font-size:10px;color:#888;margin-top:4px">${_t('proj_long_term_project_hint')}</div>
                </div>
                <div class="proj-form-group">
                    <label class="proj-form-label">
                        <input type="checkbox" id="pf-high-priority-ai-meeting-auto-approve">
                        ${_tf('proj_high_priority_ai_meeting_auto_approve', 'Require confirmation for high-priority project AI meeting requests', '高优项目 AI 会议申请需要确认')}
                    </label>
                    <div style="font-size:10px;color:#888;margin-top:4px">${_tf('proj_high_priority_ai_meeting_auto_approve_hint', 'When enabled, AI-originated meeting requests for this project require confirmation. Other projects are approved automatically.', '开启后该项目 AI 发起的会议申请需要确认；其他项目的 AI 会议申请会自动通过。')}</div>
                </div>
                <div class="proj-form-group" id="pf-workspace-group">
                    <label class="proj-form-label">Project Execution 工作区路径</label>
                    <input class="proj-form-input" id="pf-workspace" type="text" placeholder="留空自动创建项目工作区">
                </div>
                <div class="proj-form-row" id="pf-agent-row">
                    <div class="proj-form-group"><label class="proj-form-label">默认执行 Agent</label><select class="proj-form-select" id="pf-executor">${projectExecutionAgentOptions('')}</select></div>
                    <div class="proj-form-group"><label class="proj-form-label">默认 Reviewer</label><select class="proj-form-select" id="pf-reviewer">${projectExecutionAgentOptions('')}</select></div>
                </div>
                <div class="proj-form-row">
                    <div class="proj-form-group">
                        <label class="proj-form-label">${_t('proj_due_date')}</label>
                        <input class="proj-form-input" id="pf-due" type="date">
                    </div>
                    <div class="proj-form-group">
                        <label class="proj-form-label">${_t('proj_tags')} (${_t('proj_sort_priority')}-sep)</label>
                        <input class="proj-form-input" id="pf-tags" type="text" placeholder="${_t('proj_tags')}">
                    </div>
                </div>
                ${extra ? `<input type="hidden" id="pf-template-id" value="${escHtml(extra)}">` : ''}
                <div class="proj-form-actions">
                    <button class="proj-btn" onclick="ProjMgr.hideFormModal()">${_t('proj_cancel')}</button>
                    <button class="proj-btn proj-btn-primary" onclick="ProjMgr.submitNewProject()">${_t('proj_create_project_btn')}</button>
                </div>
            </div>
            </div>`;
            document.getElementById('pf-title').focus();

        } else if (type === 'edit-project') {
            overlay.innerHTML = `
            <div class="proj-form-modal" style="position:static;padding:0;background:transparent" onclick="event.stopPropagation()">
            <div class="proj-form-box">
                <div class="proj-form-title">${_t('proj_edit_project_title')}</div>
                <div class="proj-form-group">
                    <label class="proj-form-label">${_t('proj_new_project_title_placeholder')} *</label>
                    <input class="proj-form-input" id="pf-title" type="text" value="${escHtml(data.title || '')}">
                </div>
                <div class="proj-form-group">
                    <label class="proj-form-label">${_t('proj_description')}</label>
                    <textarea class="proj-form-textarea" id="pf-desc">${escHtml(data.description || '')}</textarea>
                </div>
                <div class="proj-form-row">
                    <div class="proj-form-group">
                        <label class="proj-form-label">${_t('proj_status_active')}</label>
                        <select class="proj-form-select" id="pf-status">
                            <option value="active" ${data.status === 'active' ? 'selected' : ''}>${_t('proj_status_active')}</option>
                            <option value="paused" ${data.status === 'paused' ? 'selected' : ''}>${_t('proj_status_paused')}</option>
                            <option value="completed" ${data.status === 'completed' ? 'selected' : ''}>${_t('proj_status_completed')}</option>
                            <option value="archived" ${data.status === 'archived' ? 'selected' : ''}>${_t('proj_status_archived')}</option>
                        </select>
                    </div>
                    <div class="proj-form-group">
                        <label class="proj-form-label">${_t('proj_priority_label')}</label>
                        <select class="proj-form-select" id="pf-priority">
                            <option value="critical" ${data.priority === 'critical' ? 'selected' : ''}>${_t('proj_priority_critical')}</option>
                            <option value="high" ${data.priority === 'high' ? 'selected' : ''}>${_t('proj_priority_high')}</option>
                            <option value="medium" ${data.priority === 'medium' ? 'selected' : ''}>${_t('proj_priority_medium')}</option>
                            <option value="low" ${data.priority === 'low' ? 'selected' : ''}>${_t('proj_priority_low')}</option>
                        </select>
                    </div>
                </div>
                <div class="proj-form-row">
                    <div class="proj-form-group">
                        <label class="proj-form-label">${_t('proj_due_date')}</label>
                        <input class="proj-form-input" id="pf-due" type="date" value="${data.dueDate ? data.dueDate.split('T')[0] : ''}">
                    </div>
                    <div class="proj-form-group">
                        <label class="proj-form-label">${_t('proj_tags')} (${_t('proj_sort_priority')}-sep)</label>
                        <input class="proj-form-input" id="pf-tags" type="text" value="${escHtml((data.tags || []).join(', '))}">
                    </div>
                </div>
                <div class="proj-form-group">
                    <label class="proj-form-label">
                        <input type="checkbox" id="pf-long-term-project" ${data.longTermProject ? 'checked' : ''}>
                        ${_t('proj_long_term_project')}
                    </label>
                    <div style="font-size:10px;color:#888;margin-top:4px">${_t('proj_long_term_project_hint')}</div>
                </div>
                <div class="proj-form-group">
                    <label class="proj-form-label">
                        <input type="checkbox" id="pf-high-priority-ai-meeting-auto-approve" ${data.highPriorityAiMeetingAutoApprove ? 'checked' : ''}>
                        ${_tf('proj_high_priority_ai_meeting_auto_approve', 'Require confirmation for high-priority project AI meeting requests', '高优项目 AI 会议申请需要确认')}
                    </label>
                    <div style="font-size:10px;color:#888;margin-top:4px">${_tf('proj_high_priority_ai_meeting_auto_approve_hint', 'When enabled, AI-originated meeting requests for this project require confirmation. Other projects are approved automatically.', '开启后该项目 AI 发起的会议申请需要确认；其他项目的 AI 会议申请会自动通过。')}</div>
                </div>
                <div class="proj-form-group">
                    <label class="proj-form-label">Project Execution 工作区路径</label>
                    <input class="proj-form-input" id="pf-workspace" type="text" value="${escHtml(data.workspacePath || '')}" placeholder="/path/to/project">
                </div>
                <div class="proj-form-row">
                    <div class="proj-form-group"><label class="proj-form-label">默认执行 Agent</label><select class="proj-form-select" id="pf-executor">${projectExecutionAgentOptions(data.defaultExecutorAgentId || '')}</select></div>
                    <div class="proj-form-group"><label class="proj-form-label">默认 Reviewer</label><select class="proj-form-select" id="pf-reviewer">${projectExecutionAgentOptions(data.defaultReviewerAgentId || '')}</select></div>
                </div>
                <input type="hidden" id="pf-edit-id" value="${data.id || ''}">
                <div class="proj-form-actions">
                    <button class="proj-btn" onclick="ProjMgr.hideFormModal()">${_t('proj_cancel')}</button>
                    <button class="proj-btn proj-btn-primary" onclick="ProjMgr.submitEditProject()">${_t('proj_save_changes')}</button>
                </div>
            </div>
            </div>`;

        } else if (type === 'save-template') {
            overlay.innerHTML = `
            <div class="proj-form-modal" style="position:static;padding:0;background:transparent" onclick="event.stopPropagation()">
            <div class="proj-form-box" style="max-width:400px">
                <div class="proj-form-title">${_t('proj_save_as_template')}</div>
                <div class="proj-form-group">
                    <label class="proj-form-label">${_t('proj_template_name')}</label>
                    <input class="proj-form-input" id="pf-tpl-title" type="text" value="${escHtml(data.title + ' Template')}" autofocus>
                </div>
                <div class="proj-form-group">
                    <label class="proj-form-label">${_t('proj_description')}</label>
                    <textarea class="proj-form-textarea" id="pf-tpl-desc" placeholder="${_t('proj_template_desc_placeholder')}">${escHtml(data.description || '')}</textarea>
                </div>
                <input type="hidden" id="pf-tpl-proj-id" value="${data.id || ''}">
                <div class="proj-form-actions">
                    <button class="proj-btn" onclick="ProjMgr.hideFormModal()">${_t('proj_cancel')}</button>
                    <button class="proj-btn proj-btn-primary" onclick="ProjMgr.submitSaveTemplate()">${_t('proj_save_template_btn')}</button>
                </div>
                </div>
            </div>`;
        } else if (type === 'project-cron') {
            const p = data || state.currentProject;
            const job = extra || null;
            const tasks = (p && p.tasks) || [];
            const isEdit = !!(job && job.id);
            const defaultName = (job && job.name) || _t('proj_scheduled_cron_default_project_name', { title: (p && p.title) || _t('project') });
            const targetType = (job && job.targetType) || 'projectWorkflow';
            const schedule = (job && job.schedule) || { kind: 'every', everyMs: 3600000 };
            const scheduleKind = schedule.kind || 'every';
            const everyMin = schedule.kind === 'every' ? Math.max(1, Math.round((schedule.everyMs || 3600000) / 60000)) : 60;
            const cronParts = schedule.kind === 'cron' ? String(schedule.expr || '0 9 * * *').split(/\s+/) : [];
            const cronMinute = cronParts[0] || '0';
            const cronHour = cronParts[1] || '9';
            const cronTime = `${String(cronHour).padStart(2, '0')}:${String(cronMinute).padStart(2, '0')}`;
            const cronDow = cronParts[4] || '*';
            const atDate = schedule.kind === 'at' && schedule.at ? new Date(schedule.at).toISOString().slice(0, 10) : '';
            const atTime = schedule.kind === 'at' && schedule.at ? new Date(schedule.at).toTimeString().slice(0, 5) : '';
            overlay.innerHTML = `
            <div class="proj-form-modal" style="position:static;padding:0;background:transparent" onclick="event.stopPropagation()">
            <div class="proj-form-box" style="max-width:620px">
                <div class="proj-form-title">${isEdit ? _t('proj_scheduled_cron_edit_title') : _t('proj_scheduled_cron_create_title')}</div>
                <input type="hidden" id="pf-cron-id" value="${escHtml((job && job.id) || '')}">
                <div class="proj-form-group">
                    <label class="proj-form-label">${_t('proj_scheduled_cron_name_label')} *</label>
                    <input class="proj-form-input" id="pf-cron-name" type="text" value="${escHtml(defaultName)}" autofocus>
                </div>
                <div class="proj-form-row">
                    <div class="proj-form-group">
                        <label class="proj-form-label">${_t('proj_scheduled_cron_target_label')}</label>
                        <select class="proj-form-select" id="pf-cron-target" onchange="ProjMgr.toggleProjectCronTaskField()">
                            <option value="projectWorkflow" ${targetType === 'projectWorkflow' ? 'selected' : ''}>${_t('proj_scheduled_cron_target_workflow')}</option>
                            <option value="projectTask" ${targetType === 'projectTask' ? 'selected' : ''}>${_t('proj_scheduled_cron_target_task')}</option>
                        </select>
                    </div>
                    <div class="proj-form-group" id="pf-cron-task-group" style="${targetType === 'projectTask' ? '' : 'display:none'}">
                        <label class="proj-form-label">${_t('proj_scheduled_cron_task_label')}</label>
                        <select class="proj-form-select" id="pf-cron-task">
                            ${tasks.map(t => `<option value="${escHtml(t.id)}" ${job && job.taskId === t.id ? 'selected' : ''}>${escHtml(t.title || t.id)}</option>`).join('')}
                        </select>
                    </div>
                </div>
                <div class="proj-form-group">
                    <label class="proj-form-label">${_t('proj_scheduled_cron_schedule_type')}</label>
                    <select class="proj-form-select" id="pf-cron-schedule-type" onchange="ProjMgr.toggleProjectCronScheduleFields()">
                        <option value="every" ${scheduleKind === 'every' ? 'selected' : ''}>${_t('proj_scheduled_cron_schedule_every')}</option>
                        <option value="cron" ${scheduleKind === 'cron' ? 'selected' : ''}>${_t('proj_scheduled_cron_schedule_cron')}</option>
                        <option value="at" ${scheduleKind === 'at' ? 'selected' : ''}>${_t('proj_scheduled_cron_schedule_at')}</option>
                    </select>
                </div>
                <div class="proj-form-row" id="pf-cron-every-fields" style="${scheduleKind === 'every' ? '' : 'display:none'}">
                    <div class="proj-form-group">
                        <label class="proj-form-label">${_t('proj_scheduled_cron_interval_minutes')}</label>
                        <input class="proj-form-input" id="pf-cron-every-min" type="number" min="1" value="${escHtml(String(everyMin))}">
                    </div>
                </div>
                <div id="pf-cron-cron-fields" style="${scheduleKind === 'cron' ? '' : 'display:none'}">
                    <div class="proj-form-row">
                        <div class="proj-form-group">
                            <label class="proj-form-label">${_t('proj_scheduled_cron_time_label')}</label>
                            <input class="proj-form-input" id="pf-cron-time" type="time" value="${escHtml(cronTime)}">
                        </div>
                        <div class="proj-form-group">
                            <label class="proj-form-label">${_t('proj_scheduled_cron_timezone_label')}</label>
                            <input class="proj-form-input" id="pf-cron-tz" type="text" value="${escHtml(schedule.tz || projectCronDefaultTimezone())}">
                        </div>
                    </div>
                    <div class="proj-form-group">
                        <label class="proj-form-label">${_t('proj_scheduled_cron_days_label')}</label>
                        <div class="proj-cron-days">
                            ${projectCronDayCheckbox('1', _t('weekday_mon'), cronDow)}
                            ${projectCronDayCheckbox('2', _t('weekday_tue'), cronDow)}
                            ${projectCronDayCheckbox('3', _t('weekday_wed'), cronDow)}
                            ${projectCronDayCheckbox('4', _t('weekday_thu'), cronDow)}
                            ${projectCronDayCheckbox('5', _t('weekday_fri'), cronDow)}
                            ${projectCronDayCheckbox('6', _t('weekday_sat'), cronDow)}
                            ${projectCronDayCheckbox('0', _t('weekday_sun'), cronDow)}
                        </div>
                    </div>
                </div>
                <div id="pf-cron-at-fields" style="${scheduleKind === 'at' ? '' : 'display:none'}">
                    <div class="proj-form-row">
                        <div class="proj-form-group">
                            <label class="proj-form-label">${_t('proj_scheduled_cron_date_label')}</label>
                            <input class="proj-form-input" id="pf-cron-at-date" type="date" value="${escHtml(atDate)}">
                        </div>
                        <div class="proj-form-group">
                            <label class="proj-form-label">${_t('proj_scheduled_cron_time_label')}</label>
                            <input class="proj-form-input" id="pf-cron-at-time" type="time" value="${escHtml(atTime)}">
                        </div>
                    </div>
                </div>
                <div class="proj-form-group">
                    <label class="proj-form-label"><input type="checkbox" id="pf-cron-enabled" ${!job || job.enabled !== false ? 'checked' : ''}> ${_t('proj_scheduled_cron_enabled_label')}</label>
                    <div style="font-size:10px;color:#888;margin-top:4px">${_t('proj_scheduled_cron_repeat_gate_hint')}</div>
                </div>
                <div class="proj-form-actions">
                    <button class="proj-btn" onclick="ProjMgr.hideFormModal()">${_t('proj_cancel')}</button>
                    <button class="proj-btn proj-btn-primary" onclick="ProjMgr.submitProjectCron()">${isEdit ? _t('proj_scheduled_cron_save') : _t('proj_scheduled_cron_create')}</button>
                </div>
            </div>
            </div>`;
        }
    }

    function hideFormModal() {
        const overlay = document.getElementById('proj-form-overlay');
        if (overlay) { overlay.innerHTML = ''; overlay.classList.add('hidden'); }
        state.acceptanceDialog = null;
    }

    function showConfirmDialog(opts = {}) {
        const overlay = document.getElementById('proj-form-overlay');
        if (!overlay) return Promise.resolve(false);
        return new Promise(resolve => {
            const cancelText = opts.cancelText || _tf('proj_cancel', 'Cancel', '取消');
            const confirmText = opts.confirmText || _tf('proj_confirm', 'Confirm', '确认');
            const showCancel = opts.cancelText !== null && opts.cancelText !== false;
            const tone = opts.tone === 'danger' ? ' proj-confirm-danger' : '';
            const done = confirmed => {
                hideFormModal();
                resolve(confirmed);
            };
            state.confirmDialog = { done };
            overlay.classList.remove('hidden');
            overlay.innerHTML = `
            <div class="proj-form-modal" style="position:static;padding:0;background:transparent" onclick="event.stopPropagation()">
                <div class="proj-form-box proj-confirm-dialog${tone}" role="dialog" aria-modal="true" aria-labelledby="proj-confirm-dialog-title">
                    <div class="proj-form-title" id="proj-confirm-dialog-title">${escHtml(opts.title || confirmText)}</div>
                    ${opts.message ? `<div class="proj-confirm-message">${escHtml(opts.message)}</div>` : ''}
                    ${opts.detail ? `<div class="proj-confirm-detail">${escHtml(opts.detail)}</div>` : ''}
                    <div class="proj-form-actions">
                        ${showCancel ? `<button class="proj-btn" onclick="ProjMgr.resolveConfirm(false)">${escHtml(cancelText)}</button>` : ''}
                        <button class="proj-btn ${opts.tone === 'danger' ? 'proj-btn-stop' : 'proj-btn-primary'}" onclick="ProjMgr.resolveConfirm(true)">${escHtml(confirmText)}</button>
                    </div>
                </div>
            </div>`;
        });
    }

    function showTextInputDialog(opts = {}) {
        const overlay = document.getElementById('proj-form-overlay');
        if (!overlay) return Promise.resolve({ confirmed: false, value: '' });
        return new Promise(resolve => {
            const cancelText = opts.cancelText || _tf('proj_cancel', 'Cancel', '取消');
            const confirmText = opts.confirmText || _tf('proj_confirm', 'Confirm', '确认');
            const done = result => {
                hideFormModal();
                resolve(result || { confirmed: false, value: '' });
            };
            state.textInputDialog = { done };
            overlay.classList.remove('hidden');
            overlay.innerHTML = `
            <div class="proj-form-modal" style="position:static;padding:0;background:transparent" onclick="event.stopPropagation()">
                <div class="proj-form-box proj-acceptance-dialog" role="dialog" aria-modal="true" aria-labelledby="proj-text-input-title">
                    <div class="proj-form-title" id="proj-text-input-title">${escHtml(opts.title || confirmText)}</div>
                    ${opts.message ? `<div class="proj-form-help">${escHtml(opts.message)}</div>` : ''}
                    ${opts.taskTitle ? `<div class="proj-acceptance-task">${escHtml(opts.taskTitle)}</div>` : ''}
                    <div class="proj-form-group">
                        <label class="proj-form-label">${escHtml(opts.label || '')}</label>
                        <textarea class="proj-form-textarea proj-acceptance-textarea" id="proj-text-input-value" placeholder="${escHtml(opts.placeholder || '')}" autofocus></textarea>
                    </div>
                    <div class="proj-form-actions">
                        <button class="proj-btn" onclick="ProjMgr.submitTextInputDialog(false)">${escHtml(cancelText)}</button>
                        <button class="proj-btn ${opts.tone === 'danger' ? 'proj-btn-stop' : 'proj-btn-primary'}" onclick="ProjMgr.submitTextInputDialog(true)">${escHtml(confirmText)}</button>
                    </div>
                </div>
            </div>`;
            const input = document.getElementById('proj-text-input-value');
            if (input) input.focus();
        });
    }

    function submitTextInputDialogAction(confirmed) {
        const dialog = state.textInputDialog;
        if (confirmed) markDialogSubmitting(true);
        const input = document.getElementById('proj-text-input-value');
        const value = confirmed ? ((input && input.value) || '').trim() : '';
        if (dialog && typeof dialog.done === 'function') dialog.done({ confirmed: !!confirmed, value });
        else hideFormModal();
        state.textInputDialog = null;
    }

    function projectResetModeTitle(mode) {
        return mode === 'project_flow' ? _t('proj_reset_project_flow_title') : _t('proj_reset_task_state_title');
    }

    function openProjectResetDialogAction() {
        const p = state.currentProject;
        const overlay = document.getElementById('proj-form-overlay');
        if (!p || !overlay) return;
        overlay.classList.remove('hidden');
        overlay.innerHTML = `
        <div class="proj-form-modal" style="position:static;padding:0;background:transparent" onclick="event.stopPropagation()">
            <div class="proj-form-box proj-reset-dialog" role="dialog" aria-modal="true" aria-labelledby="proj-reset-dialog-title">
                <div class="proj-form-title" id="proj-reset-dialog-title">${_t('proj_reset_dialog_title')}</div>
                <div class="proj-form-help">${_t('proj_reset_dialog_desc')}</div>
                <div class="proj-reset-options">
                    <button class="proj-reset-option" onclick="ProjMgr.projectReset('task_state')">
                        <strong>${_t('proj_reset_task_state_title')}</strong>
                        <span>${_t('proj_reset_task_state_desc')}</span>
                    </button>
                    <button class="proj-reset-option" onclick="ProjMgr.projectReset('project_flow')">
                        <strong>${_t('proj_reset_project_flow_title')}</strong>
                        <span>${_t('proj_reset_project_flow_desc')}</span>
                    </button>
                </div>
                <div class="proj-form-actions">
                    <button class="proj-btn" onclick="ProjMgr.hideFormModal()">${_t('proj_cancel')}</button>
                </div>
            </div>
        </div>`;
    }

    async function projectResetAction(mode, confirmed) {
        const p = state.currentProject;
        if (!p) return;
        hideFormModal();
        try {
            const d = await api.resetProject(p.id, { mode, confirmed: confirmed === true });
            if (d.confirmationRequired) {
                const taskTitles = (d.riskyTasks || []).map(t => t.title || t.id).filter(Boolean).slice(0, 5);
                const titleSeparator = currentLang().startsWith('zh') ? '、' : ', ';
                const extra = taskTitles.length ? `${_t('proj_reset_confirm_detail_prefix')} ${taskTitles.join(titleSeparator)}` : '';
                const ok = await showConfirmDialog({
                    tone: 'danger',
                    title: _t('proj_reset_confirm_title'),
                    message: formatTextTemplate(_t('proj_reset_confirm_message'), { count: d.riskyTaskCount || 0, mode: projectResetModeTitle(mode) }),
                    detail: extra || _t('proj_reset_confirm_detail'),
                    confirmText: _t('proj_reset_confirm_action'),
                    cancelText: _t('proj_cancel'),
                });
                if (ok) await projectResetAction(mode, true);
                return;
            }
            if (!d.ok) throw new Error(d.error || 'reset failed');
            stopWorkflowPolling();
            state.workflow.active = false;
            state.workflow.phase = 'idle';
            await refreshProjectScheduledCronPanel();
            toast(formatTextTemplate(_t('proj_reset_success'), { count: d.resetTaskCount || 0 }), 'success');
        } catch (e) {
            toast(formatTextTemplate(_t('proj_reset_failed'), { message: e.message || String(e) }), 'error');
        }
    }

    function resolveConfirmAction(confirmed) {
        const dialog = state.confirmDialog;
        if (confirmed) markDialogSubmitting(true);
        if (dialog && typeof dialog.done === 'function') dialog.done(!!confirmed);
        else hideFormModal();
        state.confirmDialog = null;
    }

    function toggleProjectExecutionFields(enabled) {
        const workspaceGroup = document.getElementById('pf-workspace-group');
        const agentRow = document.getElementById('pf-agent-row');
        if (workspaceGroup) workspaceGroup.style.display = enabled ? '' : 'none';
        if (agentRow) agentRow.style.display = enabled ? '' : 'none';
    }

    function projectCronDefaultTimezone() {
        try { return Intl.DateTimeFormat().resolvedOptions().timeZone || ''; } catch (e) { return ''; }
    }

    function projectCronDayCheckbox(value, label, dow = '*') {
        const selected = dow === '*' || String(dow).split(',').includes(String(value));
        return `<label class="proj-cron-day"><input type="checkbox" class="pf-cron-day" value="${value}" ${selected ? 'checked' : ''}> ${label}</label>`;
    }

    function toggleProjectCronTaskField() {
        const target = (document.getElementById('pf-cron-target') || {}).value || 'projectWorkflow';
        const group = document.getElementById('pf-cron-task-group');
        if (group) group.style.display = target === 'projectTask' ? '' : 'none';
    }

    function toggleProjectCronScheduleFields() {
        const type = (document.getElementById('pf-cron-schedule-type') || {}).value || 'every';
        const every = document.getElementById('pf-cron-every-fields');
        const cron = document.getElementById('pf-cron-cron-fields');
        const at = document.getElementById('pf-cron-at-fields');
        if (every) every.style.display = type === 'every' ? 'flex' : 'none';
        if (cron) cron.style.display = type === 'cron' ? 'block' : 'none';
        if (at) at.style.display = type === 'at' ? 'block' : 'none';
    }

    function buildProjectCronScheduleFromForm() {
        const type = (document.getElementById('pf-cron-schedule-type') || {}).value || 'every';
        if (type === 'every') {
            const min = parseInt((document.getElementById('pf-cron-every-min') || {}).value, 10);
            if (!min || min < 1) throw new Error(_t('proj_scheduled_cron_error_interval'));
            return { kind: 'every', everyMs: min * 60000 };
        }
        if (type === 'cron') {
            const time = (document.getElementById('pf-cron-time') || {}).value || '09:00';
            const parts = time.split(':').map(Number);
            const days = Array.from(document.querySelectorAll('.pf-cron-day:checked')).map(cb => parseInt(cb.value, 10));
            if (parts.length < 2 || Number.isNaN(parts[0]) || Number.isNaN(parts[1])) throw new Error(_t('proj_scheduled_cron_error_time'));
            if (!days.length) throw new Error(_t('proj_scheduled_cron_error_day'));
            const dow = days.length === 7 ? '*' : days.sort((a, b) => a - b).join(',');
            return { kind: 'cron', expr: `${parts[1]} ${parts[0]} * * ${dow}`, tz: ((document.getElementById('pf-cron-tz') || {}).value || '').trim() || undefined };
        }
        const date = (document.getElementById('pf-cron-at-date') || {}).value;
        const time = (document.getElementById('pf-cron-at-time') || {}).value;
        if (!date || !time) throw new Error(_t('proj_scheduled_cron_error_at'));
        return { kind: 'at', at: new Date(`${date}T${time}`).toISOString() };
    }

    async function submitProjectCron() {
        const p = state.currentProject;
        if (!p) return;
        const cronId = ((document.getElementById('pf-cron-id') || {}).value || '').trim();
        const actionKey = `cron-submit:${p.id}:${cronId || 'new'}`;
        return runActionOnce(actionKey, async () => {
        const name = ((document.getElementById('pf-cron-name') || {}).value || '').trim() || _t('proj_scheduled_cron_default_project_name', { title: p.title });
        const targetType = (document.getElementById('pf-cron-target') || {}).value || 'projectWorkflow';
        const taskId = (document.getElementById('pf-cron-task') || {}).value || '';
        try {
            markDialogSubmitting(true);
            if (targetType === 'projectTask' && !taskId) throw new Error(_t('proj_scheduled_cron_error_task'));
            const body = {
                name,
                schedule: buildProjectCronScheduleFromForm(),
                targetType,
                enabled: !!((document.getElementById('pf-cron-enabled') || {}).checked),
                message: `Scheduled project cron for ${p.title}`,
            };
            if (targetType === 'projectTask') body.taskId = taskId;
            const d = cronId
                ? await api.updateScheduledCron(p.id, cronId, body)
                : await api.createScheduledCron(p.id, body);
            if (!d.ok) throw new Error(d.error || (cronId ? 'update failed' : 'create failed'));
            hideFormModal();
            toast(cronId ? _t('proj_scheduled_cron_updated') : _t('proj_scheduled_cron_created'), 'success');
            await refreshProjectScheduledCronPanel();
        } catch (e) {
            markDialogSubmitting(false);
            toast(_t('proj_scheduled_cron_save_failed', { message: e.message }), 'error');
        }
        });
    }

    async function submitNewProject() {
        const title = (document.getElementById('pf-title') || {}).value.trim();
        if (!title) { toast(_t('proj_title_required'), 'error'); return; }
        const tplId = document.getElementById('pf-template-id');
        const execToggle = document.getElementById('pf-project-execution');
        const projectExecutionEnabled = execToggle ? execToggle.checked : true;
        const body = {
            title,
            description: (document.getElementById('pf-desc') || {}).value || '',
            status: (document.getElementById('pf-status') || {}).value || 'active',
            priority: (document.getElementById('pf-priority') || {}).value || 'medium',
            dueDate: (document.getElementById('pf-due') || {}).value ? new Date(document.getElementById('pf-due').value).toISOString() : null,
            tags: ((document.getElementById('pf-tags') || {}).value || '').split(',').map(t => t.trim()).filter(Boolean),
            longTermProject: !!((document.getElementById('pf-long-term-project') || {}).checked),
            highPriorityAiMeetingAutoApprove: !!((document.getElementById('pf-high-priority-ai-meeting-auto-approve') || {}).checked),
            projectExecutionEnabled,
            workspacePath: ((document.getElementById('pf-workspace') || {}).value || '').trim() || null,
            defaultExecutorAgentId: (document.getElementById('pf-executor') || {}).value || null,
            defaultReviewerAgentId: (document.getElementById('pf-reviewer') || {}).value || null,
        };
        try {
            let d;
            if (tplId && tplId.value) {
                d = await api.createFromTemplate({ ...body, templateId: tplId.value });
            } else {
                d = await api.createProject(body);
            }
            if (d.error) {
                toast(d.error, 'error');
                await refreshProjectExecutionProject((d.selectedTask || {}).id || d.taskId);
                return;
            }
            hideFormModal();
            if (d.project) {
                if (body.projectExecutionEnabled && body.workspacePath) {
                    const validation = await api.projectExecutionValidateWorkspace(d.project.id, body.workspacePath);
                    if (validation.error) { toast(validation.error, 'error'); return; }
                }
                toast(_t('proj_created'), 'success');
                await openProject(d.project.id);
            }
        } catch (e) { toast(_t('proj_failed_create'), 'error'); }
    }

    async function submitEditProject() {
        const id = (document.getElementById('pf-edit-id') || {}).value;
        const title = (document.getElementById('pf-title') || {}).value.trim();
        if (!title || !id) return;
        const body = {
            title,
            description: (document.getElementById('pf-desc') || {}).value || '',
            status: (document.getElementById('pf-status') || {}).value || 'active',
            priority: (document.getElementById('pf-priority') || {}).value || 'medium',
            dueDate: (document.getElementById('pf-due') || {}).value ? new Date(document.getElementById('pf-due').value).toISOString() : null,
            tags: ((document.getElementById('pf-tags') || {}).value || '').split(',').map(t => t.trim()).filter(Boolean),
            longTermProject: !!((document.getElementById('pf-long-term-project') || {}).checked),
            highPriorityAiMeetingAutoApprove: !!((document.getElementById('pf-high-priority-ai-meeting-auto-approve') || {}).checked),
            workspacePath: ((document.getElementById('pf-workspace') || {}).value || '').trim() || null,
            defaultExecutorAgentId: (document.getElementById('pf-executor') || {}).value || null,
            defaultReviewerAgentId: (document.getElementById('pf-reviewer') || {}).value || null,
        };
        try {
            const d = await api.updateProject(id, body);
            if (d.error) { toast(projectExecutionApiErrorText(d), 'error'); return; }
            if (body.projectExecutionEnabled) {
                const validation = await api.projectExecutionValidateWorkspace(id, body.workspacePath);
                if (validation.error) { toast(validation.error, 'error'); return; }
                body.workspaceKind = validation.workspace.kind;
                body.workspaceStatus = validation.workspace;
            }
            hideFormModal();
            if (state.currentProject && state.currentProject.id === id) Object.assign(state.currentProject, body);
            toast(_t('proj_updated'), 'success');
            if (state.view === 'board') { const mc = getMainContent(); if (mc) { mc.innerHTML = renderBoardView(); bindBoardEvents(); } }
            else { showListView(); }
        } catch (e) { toast(_t('proj_failed_update'), 'error'); }
    }

    // ── PROJECT CRUD ──────────────────────────────────────────────
    async function archiveProject(id, e) {
        if (e) e.stopPropagation();
        if (!confirm(_t('proj_archive_confirm'))) return;
        try {
            await api.updateProject(id, { status: 'archived' });
            toast(_t('proj_archived'), 'success');
            showListView();
        } catch (e) { toast(_t('proj_failed_archive'), 'error'); }
    }

    async function deleteProject(id, e) {
        if (e) e.stopPropagation();
        if (!confirm(_t('proj_delete_confirm'))) return;
        const project = (state.projects || []).find(p => p.id === id) || (state.currentProject && state.currentProject.id === id ? state.currentProject : null);
        let deleteWorkspace = false;
        if (project && project.workspaceManagedBy === 'system' && project.workspacePath) {
            deleteWorkspace = confirm(`是否一并删除自动创建的项目工作区？\n${project.workspacePath}`);
        }
        try {
            const d = await api.deleteProject(id, { deleteWorkspace });
            if (d.error) { toast(projectExecutionApiErrorText(d), 'error'); return; }
            if (d.workspaceDeleteError) toast(`项目已删除，但工作区删除失败：${d.workspaceDeleteError}`, 'error');
            toast(_t('proj_deleted'), 'success');
            showListView();
        } catch (e) { toast(_t('proj_failed_delete'), 'error'); }
    }

    function filterChange(key, value) {
        state.filters[key] = value;
        const mc = getMainContent();
        if (mc) mc.innerHTML = renderListView();
    }

    function backToList() { closeDetailPanel(); showListView(); }

    // ── TEMPLATES VIEW ────────────────────────────────────────────
    async function showTemplatesView() {
        state.view = 'templates';
        closeDetailPanel();
        const mc = getMainContent();
        if (!mc) return;
        mc.innerHTML = renderListSkeleton();
        try {
            const d = await api.listTemplates();
            state.templates = d.templates || [];
        } catch (e) { state.templates = []; }
        mc.innerHTML = renderTemplatesView();
    }

    function renderTemplatesView() {
        // Merge: start with client-side defaults, then add server templates not already present
        const seenIds = new Set(DEFAULT_TEMPLATES.map(t => t.id));
        const serverOnly = state.templates.filter(t => !seenIds.has(t.id));
        const all = [...DEFAULT_TEMPLATES, ...serverOnly];
        return `
        <div class="proj-toolbar">
            <button class="proj-btn" onclick="ProjMgr.backToList()">${_t('proj_back_to_projects')}</button>
            <span class="proj-toolbar-title">${_t('proj_templates')}</span>
        </div>
        <div class="proj-list-body">
            <div style="margin-bottom:16px;font-size:12px;color:#888">${_t('proj_template_choose')}</div>
            <div class="proj-tpl-grid">
                ${all.map(tpl => renderTemplateCard(tpl)).join('')}
            </div>
        </div>`;
    }

    function renderTemplateCard(tpl) {
        const isBuiltin = DEFAULT_TEMPLATES.some(t => t.id === tpl.id);
        const tplTitle = tpl._titleKey ? _t(tpl._titleKey) : tpl.title;
        return `
        <div class="proj-tpl-card">
            <div class="proj-tpl-title">${escHtml(tplTitle)}</div>
            <div class="proj-tpl-desc">${escHtml(tpl._descKey ? _t(tpl._descKey) : (tpl.description || ''))}</div>
            <div class="proj-tpl-cols">
                ${(tpl.columns || []).map(c => `<span class="proj-tpl-col-chip" style="background:${c.color}22;border-color:${c.color}55;color:${c.color}">${escHtml(c._titleKey ? _t(c._titleKey) : c.title)}</span>`).join('')}
            </div>
            <div class="proj-tpl-actions">
                <button class="proj-btn proj-btn-sm proj-btn-primary" onclick="ProjMgr.newProjectDialog('${tpl.id}')">${_t('proj_use_template')}</button>
                ${!isBuiltin ? `<button class="proj-btn proj-btn-sm proj-btn-danger" onclick="ProjMgr.deleteTemplate('${tpl.id}')">${_t('proj_delete')}</button>` : ''}
            </div>
        </div>`;
    }

    async function deleteTemplate(id) {
        if (!confirm(_t('proj_delete_template_confirm'))) return;
        try {
            await api.deleteTemplate(id);
            state.templates = state.templates.filter(t => t.id !== id);
            const mc = getMainContent();
            if (mc) mc.innerHTML = renderTemplatesView();
            toast(_t('proj_template_deleted'), 'success');
        } catch (e) { toast(_t('proj_failed_delete_template'), 'error'); }
    }

    function saveAsTemplateDialog(projectId) {
        const p = state.currentProject || state.projects.find(x => x.id === projectId);
        if (!p) return;
        showFormModal('save-template', p);
    }

    async function submitSaveTemplate() {
        const title = (document.getElementById('pf-tpl-title') || {}).value.trim();
        const projectId = (document.getElementById('pf-tpl-proj-id') || {}).value;
        const desc = (document.getElementById('pf-tpl-desc') || {}).value || '';
        if (!title) return;
        try {
            await api.saveTemplate({ title, description: desc, projectId });
            hideFormModal();
            toast(_t('proj_template_saved'), 'success');
        } catch (e) { toast(_t('proj_failed_save_template'), 'error'); }
    }

    // ── ARTIFACT VIEW ─────────────────────────────────────────────
    async function showArtifacts(id) {
        const mc = getMainContent();
        if (!mc) return;
        state.view = 'artifacts';
        closeDetailPanel();
        mc.innerHTML = renderListSkeleton();
        try {
            const d = await api.listArtifacts(id);
            if (d.error) throw new Error(d.error);
            state._artifactModel = {
                projectId: id,
                context: d.context || {},
                artifacts: d.artifacts || [],
                truncated: !!d.truncated,
                selected: null,
                selectedContent: '',
                sourceMode: 'preview',
            };
            mc.innerHTML = renderArtifactManager(state._artifactModel);
        } catch (e) {
            mc.innerHTML = renderArtifactManager({
                projectId: id,
                context: { title: state.currentProject && state.currentProject.title },
                artifacts: [],
                error: String(e.message || e),
            });
        }
    }

    function formatBytes(bytes) {
        const n = Number(bytes || 0);
        if (n < 1024) return `${n} B`;
        if (n < 1024 * 1024) return `${Math.round(n / 102.4) / 10} KB`;
        return `${Math.round(n / 1024 / 102.4) / 10} MB`;
    }

    function formatArtifactTime(value) {
        if (!value) return '';
        const d = new Date(value);
        return Number.isNaN(d.getTime()) ? String(value) : d.toLocaleString();
    }

    function renderSourceRecords(artifact, labels = {}) {
        const sources = artifact.sources || [];
        if (!sources.length) return `<div class="proj-artifact-source unassociated">${escHtml(labels.unassociated || '未关联到来源记录')}</div>`;
        return sources.slice(0, 3).map(src => `
            <div class="proj-artifact-source">
                <strong>${escHtml(src.taskTitle || src.title || src.taskId || src.sourceId || '来源')}</strong>
                ${src.taskId ? `<code title="taskId">${escHtml(src.taskId)}</code>` : ''}
                ${src.agentId ? `<span>${escHtml(src.agentId)}</span>` : ''}
                ${src.providerKind ? `<span>${escHtml(src.providerKind)}</span>` : ''}
                ${src.attemptId ? `<code>${escHtml(String(src.attemptId).slice(0, 8))}</code>` : ''}
                ${src.capturedAt || src.generatedAt ? `<time>${escHtml(formatArtifactTime(src.capturedAt || src.generatedAt))}</time>` : ''}
            </div>`).join('');
    }

    function buildArtifactTree(artifacts) {
        const root = { name: '', path: '', dirs: new Map(), files: [] };
        (artifacts || []).forEach(artifact => {
            const parts = String(artifact.path || artifact.name || '').split('/').filter(Boolean);
            if (!parts.length) return;
            let node = root;
            parts.slice(0, -1).forEach(part => {
                if (!node.dirs.has(part)) {
                    const path = node.path ? `${node.path}/${part}` : part;
                    node.dirs.set(part, { name: part, path, dirs: new Map(), files: [] });
                }
                node = node.dirs.get(part);
            });
            node.files.push(artifact);
        });
        return root;
    }

    function artifactDirFileCount(node) {
        let count = node.files.length;
        node.dirs.forEach(child => {
            count += artifactDirFileCount(child);
        });
        return count;
    }

    function renderArtifactTreeNode(node, model, selected, depth = 0) {
        const dirs = Array.from(node.dirs.values()).sort((a, b) => a.name.localeCompare(b.name));
        const files = node.files.slice().sort((a, b) => (b.modifiedAt || '').localeCompare(a.modifiedAt || '') || String(a.name || a.path).localeCompare(String(b.name || b.path)));
        const fileHtml = files.map(a => `
            <div class="proj-artifact-row ${selected && selected.path === a.path ? 'active' : ''}" style="--artifact-depth:${depth}" role="button" tabindex="0" onclick="ProjMgr.openArtifact('${model.projectId}', decodeURIComponent('${encodeURIComponent(a.path)}'))" onkeydown="if(event.key==='Enter'||event.key===' '){event.preventDefault();ProjMgr.openArtifact('${model.projectId}', decodeURIComponent('${encodeURIComponent(a.path)}'));}">
                <div class="proj-artifact-head">
                    <div>
                        <div class="proj-artifact-name">${escHtml(a.name || a.path)}</div>
                        <div class="proj-artifact-path">${escHtml(a.path)}</div>
                    </div>
                    <button class="proj-artifact-delete" title="${escHtml(_tf('proj_delete_artifact', 'Delete artifact', '删除产物'))}" onclick="ProjMgr.deleteArtifact('${model.projectId}', decodeURIComponent('${encodeURIComponent(a.path)}'), event)"><span>×</span>${escHtml(_tf('proj_delete', 'Delete', '删除'))}</button>
                </div>
                <div class="proj-artifact-meta">
                    <span>${formatBytes(a.size)}</span>
                    <span>${a.modifiedAt ? new Date(a.modifiedAt).toLocaleString() : ''}</span>
                </div>
                ${renderSourceRecords(a, model.labels || {})}
            </div>`).join('');
        const dirHtml = dirs.map(dir => {
            const containsSelected = !!(selected && selected.path && (selected.path === dir.path || selected.path.startsWith(dir.path + '/')));
            const fileCount = artifactDirFileCount(dir);
            return `
            <details class="proj-artifact-dir" style="--artifact-depth:${depth}" ${depth === 0 || containsSelected ? 'open' : ''}>
                <summary>
                    <span class="proj-artifact-dir-icon">▸</span>
                    <span class="proj-artifact-dir-name">${escHtml(dir.name)}</span>
                    <code>${fileCount}</code>
                    <button class="proj-artifact-dir-delete" title="${escHtml(_tf('proj_delete_artifact_dir', 'Delete directory artifacts', '删除目录产物'))}" onclick="ProjMgr.deleteArtifactDir('${model.projectId}', decodeURIComponent('${encodeURIComponent(dir.path)}'), event)"><span>×</span>${escHtml(_tf('proj_delete', 'Delete', '删除'))}</button>
                </summary>
                ${renderArtifactTreeNode(dir, model, selected, depth + 1)}
            </details>`;
        }).join('');
        return dirHtml + fileHtml;
    }

    function renderMarkdownPreview(content) {
        return simpleMarkdown(content || '');
    }

    function renderArtifactManager(model) {
        const artifacts = model.artifacts || [];
        const context = model.context || {};
        const selected = model.selected;
        const sourceMode = model.sourceMode || 'preview';
        const content = model.selectedContent || '';
        const labels = model.labels || {};
        const title = context.title || labels.contextFallback || 'Project';
        const itemLabel = labels.itemPlural || 'Markdown 产物';
        const artifactTree = buildArtifactTree(artifacts);
        const hasArtifacts = artifacts.length > 0;
        return `
        <div class="proj-toolbar">
            <button class="proj-btn" onclick="ProjMgr.openProject('${model.projectId}')">${_t('proj_back')}</button>
            <span class="proj-toolbar-title">${escHtml(labels.title || '产物')} · ${escHtml(title)}</span>
            <div style="flex:1"></div>
            ${context.root ? `<span class="proj-artifact-root" title="${escHtml(context.root)}">${escHtml(context.rootKind || 'dir')} · ${escHtml(context.root)}</span>` : ''}
        </div>
        <div class="proj-artifacts-body">
            ${model.error ? `<div class="proj-artifact-error">${escHtml(model.error)}</div>` : ''}
            <div class="proj-artifacts-list">
                <div class="proj-artifact-list-head">
                    <div class="proj-chart-title">${escHtml(itemLabel)} ${model.truncated ? '<span class="proj-artifact-warn">已截断</span>' : ''}</div>
                    ${hasArtifacts ? `
                    <div class="proj-artifact-tools">
                        <button class="proj-artifact-tool" onclick="ProjMgr.setArtifactDirs(true)">${escHtml(_tf('proj_expand_all_artifacts', 'Expand', '展开'))}</button>
                        <button class="proj-artifact-tool" onclick="ProjMgr.setArtifactDirs(false)">${escHtml(_tf('proj_collapse_all_artifacts', 'Collapse', '折叠'))}</button>
                        <button class="proj-artifact-tool danger" onclick="ProjMgr.deleteArtifactDir('${model.projectId}', '', event)">${escHtml(_tf('proj_delete_all_artifacts', 'Delete', '删除'))}</button>
                    </div>` : ''}
                </div>
                ${!model.error && artifacts.length === 0 ? `<div class="proj-artifact-empty">${escHtml(labels.empty || '当前上下文没有 Markdown 产物。')}</div>` : ''}
                ${renderArtifactTreeNode(artifactTree, model, selected)}
            </div>
            <div class="proj-artifact-viewer">
                ${selected ? `
                    <div class="proj-artifact-viewer-head">
                        <div>
                            <div class="proj-artifact-name">${escHtml(selected.path)}</div>
                            ${selected.truncated ? `<div class="proj-artifact-warn">文件较大，内容已截断。</div>` : ''}
                        </div>
                        <div class="proj-desc-tabs">
                            <button class="proj-desc-tab ${sourceMode === 'preview' ? 'active' : ''}" onclick="ProjMgr.switchArtifactMode('preview')">Preview</button>
                            <button class="proj-desc-tab ${sourceMode === 'source' ? 'active' : ''}" onclick="ProjMgr.switchArtifactMode('source')">Source</button>
                        </div>
                    </div>
                    <div class="proj-artifact-content ${sourceMode === 'source' ? 'source' : ''}">
                        ${sourceMode === 'source' ? `<pre>${escHtml(content)}</pre>` : renderMarkdownPreview(content)}
                    </div>
                ` : `<div class="proj-artifact-empty">${escHtml(labels.selectPrompt || '选择一个 Markdown 产物查看内容。')}</div>`}
            </div>
        </div>`;
    }

    async function openArtifact(projectId, path) {
        const mc = getMainContent();
        if (!mc) return;
        try {
            const list = await api.listArtifacts(projectId);
            const d = await api.readArtifact(projectId, path);
            if (d.error) throw new Error(d.error);
            const artifact = d.artifact || {};
            const selected = (list.artifacts || []).find(a => a.path === artifact.path) || artifact;
            state._artifactModel = {
                projectId,
                context: list.context || {},
                artifacts: list.artifacts || [],
                truncated: !!list.truncated,
                selected: { ...selected, truncated: artifact.truncated },
                selectedContent: artifact.content || '',
                sourceMode: 'preview',
            };
            mc.innerHTML = renderArtifactManager(state._artifactModel);
        } catch (e) {
            toast(String(e.message || e), 'error');
        }
    }

    function switchArtifactMode(mode) {
        const mc = getMainContent();
        if (!mc || !state._artifactModel) return;
        state._artifactModel.sourceMode = mode === 'source' ? 'source' : 'preview';
        mc.innerHTML = renderArtifactManager(state._artifactModel);
    }

    function setArtifactDirs(open) {
        const mc = getMainContent();
        if (!mc) return;
        mc.querySelectorAll('.proj-artifact-dir').forEach(detail => {
            detail.open = !!open;
        });
    }

    async function refreshArtifactModel(projectId, removedPathPrefix = '') {
        const list = await api.listArtifacts(projectId);
        const previous = state._artifactModel || {};
        const selectedPath = previous.selected && previous.selected.path;
        const removed = !selectedPath ? false : (
            !removedPathPrefix ||
            selectedPath === removedPathPrefix ||
            selectedPath.startsWith(removedPathPrefix + '/')
        );
        const selected = selectedPath && !removed ? (list.artifacts || []).find(a => a.path === selectedPath) : null;
        state._artifactModel = {
            projectId,
            context: list.context || {},
            artifacts: list.artifacts || [],
            truncated: !!list.truncated,
            selected,
            selectedContent: selected ? previous.selectedContent : '',
            sourceMode: previous.sourceMode || 'preview',
        };
        const mc = getMainContent();
        if (mc) mc.innerHTML = renderArtifactManager(state._artifactModel);
    }

    async function deleteArtifactAction(projectId, path, event) {
        if (event) {
            event.preventDefault();
            event.stopPropagation();
        }
        if (!path) return;
        const confirmed = await showConfirmDialog({
            title: _tf('proj_delete_artifact', 'Delete artifact', '删除产物'),
            message: _tf('proj_delete_artifact_confirm', 'This artifact will be deleted from the project workspace.', '这个产物将从项目工作区中删除。'),
            detail: path,
            confirmText: _tf('proj_delete', 'Delete', '删除'),
            cancelText: _tf('proj_cancel', 'Cancel', '取消'),
            tone: 'danger',
        });
        if (!confirmed) return;
        const mc = getMainContent();
        try {
            const d = await api.deleteArtifact(projectId, path);
            if (!d.ok) throw new Error(d.error || 'delete failed');
            await refreshArtifactModel(projectId, path);
            toast(_tf('proj_artifact_deleted', 'Artifact deleted', '产物已删除'), 'success');
        } catch (e) {
            toast(_tf('proj_failed_delete_artifact', `Failed to delete artifact: ${String(e.message || e)}`, `删除产物失败：${String(e.message || e)}`, { message: String(e.message || e) }), 'error');
        }
    }

    async function deleteArtifactDirAction(projectId, dir, event) {
        if (event) {
            event.preventDefault();
            event.stopPropagation();
        }
        const isRoot = !dir;
        const title = isRoot
            ? _tf('proj_delete_all_artifacts', 'Delete all artifacts', '删除全部产物')
            : _tf('proj_delete_artifact_dir', 'Delete directory artifacts', '删除目录产物');
        const message = isRoot
            ? _tf('proj_delete_all_artifacts_confirm', 'All artifacts under the project workspace will be deleted.', '项目工作区下的全部产物都会被删除。')
            : _tf('proj_delete_artifact_dir_confirm', 'All artifacts in this directory will be deleted.', '这个目录下的全部产物都会被删除。');
        const confirmed = await showConfirmDialog({
            title,
            message,
            detail: isRoot ? (state._artifactModel && state._artifactModel.context && state._artifactModel.context.root) || '' : dir,
            confirmText: _tf('proj_delete', 'Delete', '删除'),
            cancelText: _tf('proj_cancel', 'Cancel', '取消'),
            tone: 'danger',
        });
        if (!confirmed) return;
        try {
            const d = await api.deleteArtifactDir(projectId, dir || '');
            if (!d.ok) throw new Error(d.error || 'delete failed');
            await refreshArtifactModel(projectId, dir || '');
            toast(_tf('proj_artifact_dir_deleted', 'Artifacts deleted', '产物已删除'), 'success');
        } catch (e) {
            toast(_tf('proj_failed_delete_artifact', `Failed to delete artifact: ${String(e.message || e)}`, `删除产物失败：${String(e.message || e)}`, { message: String(e.message || e) }), 'error');
        }
    }

    // ── REPORT VIEW ───────────────────────────────────────────────
    async function showReport(id) {
        const mc = getMainContent();
        if (!mc) return;
        mc.innerHTML = renderListSkeleton();
        state.view = 'report';
        closeDetailPanel();
        try {
            const d = await api.getReport(id);
            if (!d.report) throw new Error('No report');
            mc.innerHTML = renderReportView(d.report);
        } catch (e) {
            mc.innerHTML = `<div class="proj-loading">${_t('proj_failed_to_load_project')}</div>`;
        }
    }

    function renderReportView(r) {
        const { stats, columns, agentWorkload, timeline, title } = r;
        const maxColCount = Math.max(...columns.map(c => c.count), 1);
        const maxAgentCount = Math.max(...Object.values(agentWorkload || {}), 1);

        return `
        <div class="proj-toolbar">
            <button class="proj-btn" onclick="ProjMgr.backToList()">${_t('proj_back')}</button>
            <span class="proj-toolbar-title">${_t('proj_report_title')}</span>
            <div style="flex:1"></div>
            <button class="proj-btn proj-btn-sm" onclick="ProjMgr.exportReport()">${_t('proj_export_markdown')}</button>
        </div>
        <div class="proj-report-body">
            <div class="proj-report-header">
                <div>
                    <div class="proj-report-title">${escHtml(title)}</div>
                    <div class="proj-report-subtitle">${_t('proj_generated_at')} ${new Date(r.generatedAt).toLocaleString()}</div>
                </div>
            </div>

            <div class="proj-stats-grid">
                <div class="proj-stat-card">
                    <div class="proj-stat-value">${stats.total}</div>
                    <div class="proj-stat-label">${_t('proj_total_tasks')}</div>
                </div>
                <div class="proj-stat-card">
                    <div class="proj-stat-value" style="color:#4caf50">${stats.done}</div>
                    <div class="proj-stat-label">${_t('proj_completed')}</div>
                </div>
                <div class="proj-stat-card">
                    <div class="proj-stat-value" style="color:#ffc107">${stats.inProgress}</div>
                    <div class="proj-stat-label">${_t('proj_in_progress')}</div>
                </div>
                <div class="proj-stat-card">
                    <div class="proj-stat-value" style="color:#f44336">${stats.overdue}</div>
                    <div class="proj-stat-label">${_t('proj_overdue_tasks')}</div>
                </div>
            </div>

            <div class="proj-chart-section">
                <div class="proj-chart-title">${_t('proj_tasks_by_column')}</div>
                <div class="proj-bar-chart">
                    ${columns.map(c => {
                        const colTitle = c._titleKey ? _t(c._titleKey) : c.title;
                        return `
                    <div class="proj-bar-row">
                        <div class="proj-bar-label" title="${escHtml(colTitle)}">${escHtml(colTitle)}</div>
                        <div class="proj-bar-track">
                            <div class="proj-bar-fill" style="width:${Math.round(c.count/maxColCount*100)}%;background:${c.color}">${c.count}</div>
                        </div>
                        <div class="proj-bar-count">${c.count}</div>
                    </div>`;
                    }).join('')}
                </div>
            </div>

            ${Object.keys(agentWorkload || {}).length ? `
            <div class="proj-chart-section">
                <div class="proj-chart-title">${_t('proj_agent_workload')}</div>
                <div class="proj-bar-chart">
                    ${Object.entries(agentWorkload).map(([agent, count]) => `
                    <div class="proj-bar-row">
                        <div class="proj-bar-label" title="${escHtml(agent)}">${escHtml(agent)}</div>
                        <div class="proj-bar-track">
                            <div class="proj-bar-fill" style="width:${Math.round(count/maxAgentCount*100)}%;background:#ffd700"></div>
                        </div>
                        <div class="proj-bar-count">${count}</div>
                    </div>`).join('')}
                </div>
            </div>` : ''}

            ${timeline.length ? `
            <div class="proj-chart-section">
                <div class="proj-chart-title">${_t('proj_timeline')}</div>
                <div class="proj-timeline">
                    ${timeline.map(t => {
                        const over = t.dueDate && !t.completedAt && isOverdue(t.dueDate);
                        const priorityLabel = _t('proj_priority_' + (t.priority || 'medium'));
                        return `
                        <div class="proj-tl-item ${t.completedAt ? 'completed' : over ? 'overdue' : ''}">
                            <div class="proj-tl-title">${escHtml(t.title)}</div>
                            <div class="proj-tl-meta">
                                <span>📅 ${formatDate(t.dueDate)}</span>
                                ${t.assignee ? `<span>👤 ${escHtml(t.assignee)}</span>` : ''}
                                <span class="proj-badge badge-${t.priority || 'medium'}" style="font-size:9px">${priorityLabel}</span>
                                ${t.completedAt ? `<span style="color:#4caf50">✅ ${_t('proj_done_label')}</span>` : over ? `<span style="color:#f87171">⚠️ ${_t('proj_overdue')}</span>` : ''}
                            </div>
                        </div>`;
                    }).join('')}
                </div>
            </div>` : ''}
        </div>`;
    }

    function exportReport() {
        const mc = getMainContent();
        if (!mc) return;
        // Build markdown from DOM
        const title = mc.querySelector('.proj-report-title');
        const stats = mc.querySelectorAll('.proj-stat-card');
        let md = `# ${title ? title.textContent : 'Project Report'}\n\n`;
        md += `*Generated: ${new Date().toLocaleString()}*\n\n`;
        md += `## Stats\n\n`;
        stats.forEach(s => {
            const val = s.querySelector('.proj-stat-value');
            const lbl = s.querySelector('.proj-stat-label');
            if (val && lbl) md += `- **${lbl.textContent}:** ${val.textContent}\n`;
        });
        // Copy to clipboard
        navigator.clipboard.writeText(md).then(() => toast(_t('proj_report_copied'), 'success')).catch(() => {
            const ta = document.createElement('textarea');
            ta.value = md;
            document.body.appendChild(ta);
            ta.select();
            document.execCommand('copy');
            ta.remove();
        toast(_t('proj_report_copied'), 'success');
        });
    }

    // ── SIDEBAR ───────────────────────────────────────────────────
    function updateSidebar() {
        const el = document.getElementById('sidebar-projects-list');
        if (!el) return;
        const projectSortTime = p => {
            const raw = (p && (p.updatedAt || p.createdAt)) || '';
            const value = Date.parse(raw);
            return Number.isFinite(value) ? value : 0;
        };
        const active = state.projects
            .filter(p => p.status === 'active')
            .sort((a, b) => projectSortTime(b) - projectSortTime(a))
            .slice(0, 5);
        if (active.length === 0) {
            el.innerHTML = `<div style="font-size:10px;color:#555;padding:4px">${_t('proj_no_active_projects')}</div>`;
            return;
        }
        el.innerHTML = active.map(p => {
            const done = p.taskDone || 0;
            const total = p.taskCount || 0;
            const pct = p.taskCount > 0 ? Math.round(p.taskDone / p.taskCount * 100) : 0;
            const remaining = Math.max(0, total - done);
            const alerts = Array.isArray(p.scheduledCronAlerts) ? p.scheduledCronAlerts : [];
            const latestAlert = alerts[0] || null;
            const execLabel = projectExecutionSummaryLabel(p);
            const progressLabel = `${done}/${total} ${pct}%`;
            const progressTitle = formatTextTemplate(
                _tf(
                    'proj_progress_remaining_title',
                    'Done {done}/{total}, {remaining} remaining',
                    '已完成 {done}/{total}，剩余 {remaining} 个',
                    { done, total, remaining }
                ),
                { done, total, remaining }
            );
            const execProgressLabel = execLabel ? `${execLabel} ${progressLabel}` : '';
            const execTitleParts = execLabel ? [execLabel, progressTitle] : [progressTitle];
            if (p.activeTaskTitle) execTitleParts.push(`${_tf('proj_active_task_title', 'Current task', '当前任务')}: ${p.activeTaskTitle}`);
            const execTitle = execTitleParts.join(' · ');
            return `
            <div class="sidebar-proj-item" onclick="ProjMgr.openProjectsManager();ProjMgr.openProject('${p.id}')">
                <div class="proj-dot" style="background:${priorityColor(p.priority)}"></div>
                <span class="proj-name">${escHtml(p.title)}</span>
                ${execLabel ? `<span class="sidebar-proj-exec" title="${escHtml(execTitle)}">${escHtml(execProgressLabel)}</span>` : `<span class="proj-progress-mini" title="${escHtml(progressTitle)}">${pct}%</span>`}
                ${latestAlert ? `<span class="sidebar-proj-cron-alert" title="${escHtml(latestAlert.message || latestAlert.reason || latestAlert.error || _t('proj_scheduled_cron_alert_title'))}">${_t('proj_scheduled_cron_alert_badge')}</span>` : ''}
            </div>`;
        }).join('');
    }

    // Init sidebar on load
    (async function initSidebar() {
        try {
            const d = await api.listProjects('active');
            state.projects = d.projects || [];
            updateSidebar();
            // Also load agent roster for leaderboard names
            await loadAgentRoster();
            refreshLeaderboard();
        } catch (e) { /* non-fatal */ }
    })();

    // ── GLOBAL KEYBOARD ───────────────────────────────────────────
    function handleGlobalKeys(e) {
        if (e.key === 'Escape') {
            if (state.currentTask) closeDetailPanel();
            const overlay = document.getElementById('proj-form-overlay');
            if (overlay && !overlay.classList.contains('hidden')) hideFormModal();
        }
    }

    // ── WORKFLOW CONTROLS ──────────────────────────────────────────

    async function projectExecutionStartAction(taskId, dirtyFingerprint, opts = {}) {
        const p = state.currentProject;
        if (!p) return;
        const actionKey = opts.actionKey || `project-exec-start:${p.id}:${taskId}`;
        if (!opts._guarded) {
            return runActionOnce(actionKey, () => projectExecutionStartAction(taskId, dirtyFingerprint, { ...opts, _guarded: true, actionKey }), opts);
        }
        const confirmedDirtyFingerprint = dirtyFingerprint || opts.dirtyFingerprint || '';
        try {
            const d = await api.projectExecutionStart(p.id, taskId, confirmedDirtyFingerprint, opts);
            if (d.confirmationRequired) {
                if (d.code === 'reviewer_skip_confirmation_required') {
                    const task = (p.tasks || []).find(t => t.id === taskId) || {};
                    const confirmed = await showConfirmDialog({
                        title: '确认跳过审查',
                        message: '当前项目/任务没有配置 Reviewer。是否确认跳过独立审查并继续执行？',
                        detail: task.title ? `任务：${task.title}` : '',
                        confirmText: '跳过审查并继续',
                    });
                    if (confirmed) {
                        return projectExecutionStartAction(taskId, confirmedDirtyFingerprint, { ...opts, dirtyFingerprint: confirmedDirtyFingerprint, skipReviewConfirmed: true, _guarded: true, actionKey });
                    }
                    await refreshProjectExecutionProject(taskId);
                    return;
                }
                const files = (d.dirtyFiles || []).slice(0, 12).join('\n');
                const confirmed = await showConfirmDialog({
                    title: '确认工作区变更',
                    message: '检测到项目工作区存在未提交变更，确认后会继续启动任务。',
                    detail: files + (d.truncated ? '\n...' : ''),
                    confirmText: '继续启动',
                });
                if (confirmed) {
                    return projectExecutionStartAction(taskId, d.dirtyFingerprint, { ...opts, dirtyFingerprint: d.dirtyFingerprint, _guarded: true, actionKey });
                }
                return;
            }
            if (d.error) {
                const text = projectExecutionApiErrorText(d);
                if (d.code === 'executor_required') {
                    await showConfirmDialog({
                        title: '需要设置执行 Agent',
                        message: text,
                        confirmText: '知道了',
                        cancelText: null,
                    });
                    await refreshProjectExecutionProject(taskId);
                } else {
                    toast(text, 'error');
                }
                return;
            }
        toast(_t('proj_task_execution_started'), 'success');
            state.workflow.active = true;
            state.workflow.phase = 'executing';
            state.workflow.currentTaskId = taskId;
            startProjectExecutionPolling();
            await refreshProjectExecutionProject(taskId);
    } catch (e) { toast(_t('proj_start_task_failed'), 'error'); }
    }

    function projectExecutionSelectedStartMode() {
        const checked = document.querySelector('input[name="proj-exec-start-mode"]:checked');
        return checked ? checked.value : ((state.currentProject && state.currentProject.projectExecutionStartMode) || 'continuous');
    }

    async function setProjectExecutionStartModeAction(mode) {
        const p = state.currentProject;
        if (!p) return;
        p.projectExecutionStartMode = mode === 'single' ? 'single' : 'continuous';
        try {
            await api.updateProject(p.id, { projectExecutionStartMode: p.projectExecutionStartMode });
        } catch (e) { toast(_t('proj_save_failed'), 'error'); }
    }

    async function projectExecutionProjectStartAction(dirtyFingerprint, opts = {}) {
        const p = state.currentProject;
        if (!p) return;
        const mode = projectExecutionSelectedStartMode();
        const restartPipeline = opts.restartPipeline === true;
        const actionKey = opts.actionKey || (restartPipeline ? `project-exec-project-restart:${p.id}` : `project-exec-project-start:${p.id}`);
        if (!opts._guarded) {
            return runActionOnce(actionKey, () => projectExecutionProjectStartAction(dirtyFingerprint, { ...opts, _guarded: true, actionKey }), opts);
        }
        const confirmedDirtyFingerprint = dirtyFingerprint || opts.dirtyFingerprint || '';
        try {
            const d = await api.projectExecutionProjectStart(p.id, mode, confirmedDirtyFingerprint, opts);
            if (d.confirmationRequired) {
                if (d.code === 'reviewer_skip_confirmation_required') {
                    const taskTitle = (d.selectedTask || {}).title || '';
                    const confirmed = await showConfirmDialog({
                        title: '确认跳过审查',
                        message: '当前项目/任务没有配置 Reviewer。是否确认跳过独立审查并继续执行？',
                        detail: taskTitle ? `任务：${taskTitle}` : '',
                        confirmText: '跳过审查并继续',
                    });
                    if (confirmed) {
                        return projectExecutionProjectStartAction(confirmedDirtyFingerprint, { ...opts, dirtyFingerprint: confirmedDirtyFingerprint, skipReviewConfirmed: true, _guarded: true, actionKey });
                    }
                    await refreshProjectExecutionProject((d.selectedTask || {}).id || d.taskId);
                    return;
                }
                const files = (d.dirtyFiles || []).slice(0, 12).join('\n');
                const confirmed = await showConfirmDialog({
                    title: '确认工作区变更',
                    message: '检测到项目工作区存在未提交变更，确认后会继续启动项目任务流。',
                    detail: files + (d.truncated ? '\n...' : ''),
                    confirmText: '继续启动',
                });
                if (confirmed) {
                    return projectExecutionProjectStartAction(d.dirtyFingerprint, { ...opts, dirtyFingerprint: d.dirtyFingerprint, _guarded: true, actionKey });
                }
                return;
            }
            if (d.error) {
                const text = projectExecutionApiErrorText(d);
                const selectedTaskId = (d.selectedTask || {}).id || d.taskId;
                if (d.code === 'executor_required') {
                    await showConfirmDialog({
                        title: '需要设置执行 Agent',
                        message: text,
                        confirmText: '知道了',
                        cancelText: null,
                    });
                    await refreshProjectExecutionProject(selectedTaskId);
                } else {
                    toast(text, 'error');
                }
                return;
            }
            toast(restartPipeline ? `项目流水线已重启，已重置 ${d.resetTaskCount || 0} 个任务` : (mode === 'continuous' ? '项目连续任务流已启动' : '项目任务已启动'), 'success');
            state.workflow.active = true;
            state.workflow.phase = 'executing';
            state.workflow.currentTaskId = d.taskId;
            state.workflow.startMode = mode;
            startProjectExecutionPolling();
            await refreshProjectExecutionProject(d.taskId);
        } catch (e) { toast(_t('proj_start_task_failed'), 'error'); }
    }

    async function projectExecutionProjectRestartAction(dirtyFingerprint, opts = {}) {
        const p = state.currentProject;
        if (!p) return;
        const actionKey = opts.actionKey || `project-exec-project-restart:${p.id}`;
        if (!opts._guarded) {
            return runActionOnce(actionKey, () => projectExecutionProjectRestartAction(dirtyFingerprint, { ...opts, _guarded: true, actionKey }), opts);
        }
        if (state.workflow.active || p.workflowActive) {
            toast('请先停止当前任务，再重启流水线', 'error');
            return;
        }
        const tasks = p.tasks || [];
        if (!tasks.length || !tasks.every(t => t.scheduledRepeatEnabled === true)) {
            toast('只有项目内所有任务都允许重新触发时，才能重启流水线', 'error');
            return;
        }
        const confirmed = opts.confirmed === true || await showConfirmDialog({
            title: '重启流水线',
            message: '重启流水线会把项目内所有任务恢复到待执行状态，然后重新启动项目。',
            detail: '任务历史会保留。',
            confirmText: '重启流水线',
        });
        if (!confirmed) return;
        return projectExecutionProjectStartAction(dirtyFingerprint, { ...opts, restartPipeline: true, confirmed: true, _guarded: true, actionKey });
    }

    async function projectExecutionCancelActiveAction() {
        const p = state.currentProject;
        if (!p) return;
        const taskId = state.workflow.currentTaskId || p.activeTaskId;
        const task = (p.tasks || []).find(t => t.id === taskId);
        if (!task) { toast('没有正在执行的任务', 'info'); return; }
        await projectExecutionCancelAction(task.id, task.activeAttemptId || '');
    }

    async function copyWorkspacePathAction(event, path) {
        if (event) event.stopPropagation();
        try {
            await navigator.clipboard.writeText(path || '');
        } catch (e) {
            const ta = document.createElement('textarea');
            ta.value = path || '';
            document.body.appendChild(ta);
            ta.select();
            document.execCommand('copy');
            ta.remove();
        }
        toast('工作区路径已复制', 'success');
    }

    async function projectExecutionCancelAction(taskId, attemptId) {
        const p = state.currentProject;
        if (!p) return;
        const actionKey = `project-exec-cancel:${p.id}:${taskId}:${attemptId || ''}`;
        return runActionOnce(actionKey, async () => {
            try {
                const d = await api.projectExecutionCancel(p.id, taskId, attemptId);
                if (d.error) { toast(d.error, 'error'); await refreshProjectExecutionProject(taskId); return; }
                toast(_t('proj_stopping_task'), 'info');
                await refreshProjectExecutionProject(taskId);
            } catch (e) { toast(_t('proj_stop_task_failed'), 'error'); }
        });
    }

    async function projectExecutionMeetingBlockerAction(taskId, action) {
        const p = state.currentProject;
        if (!p) return;
        const actionKey = `meeting-blocker:${p.id}:${taskId}:${action}`;
        return runActionOnce(actionKey, async () => {
            const task = (p.tasks || []).find(t => t.id === taskId);
            let feedback = '';
            let dialogResult = null;
            if (action === 'mark_blocked') {
                dialogResult = await showTextInputDialog({
                    title: _tf('proj_meeting_blocker_mark_blocked', 'Mark blocked', '标记阻塞'),
                    label: _tf('proj_meeting_blocker_block_reason', 'Explain why this should be marked blocked:', '说明为什么标记为阻塞：'),
                    placeholder: _tf('proj_meeting_blocker_block_placeholder', 'Describe why this task cannot continue...', '说明为什么无法继续推进...'),
                    confirmText: _tf('proj_confirm', 'Confirm', '确认'),
                    taskTitle: task && task.title,
                    tone: 'danger',
                });
                if (!dialogResult.confirmed) return;
                feedback = dialogResult.value || '';
                if (!feedback.trim()) return;
            } else if (action === 'continue_execution') {
                dialogResult = await showTextInputDialog({
                    title: _tf('proj_meeting_blocker_continue', 'Continue execution', '继续执行'),
                    label: _tf('proj_meeting_blocker_continue_reason_optional', 'Reason for continuing (optional):', '继续执行理由（可选）：'),
                    placeholder: _tf('proj_meeting_blocker_continue_placeholder', 'Describe why it is acceptable to continue...', '说明为什么可以继续执行...'),
                    confirmText: _tf('proj_meeting_blocker_continue', 'Continue execution', '继续执行'),
                    taskTitle: task && task.title,
                });
                if (!dialogResult.confirmed) return;
                feedback = dialogResult.value || '';
            } else if (action === 'reopen_meeting') {
                dialogResult = await showTextInputDialog({
                    title: _tf('proj_meeting_blocker_reopen', 'Request new meeting', '重新申请会议'),
                    label: _tf('proj_meeting_blocker_reopen_reason', 'Explain why a new meeting request is needed:', '说明重新申请会议的原因：'),
                    placeholder: _tf('proj_meeting_blocker_reopen_placeholder', 'Describe what the new meeting should resolve...', '说明新会议需要解决什么问题...'),
                    confirmText: _tf('proj_meeting_blocker_reopen', 'Request new meeting', '重新申请会议'),
                    taskTitle: task && task.title,
                });
                if (!dialogResult.confirmed) return;
                feedback = dialogResult.value || '';
                if (!feedback.trim()) return;
            }
            try {
                const d = await api.projectExecutionMeetingBlocker(p.id, taskId, action, feedback);
                if (d.error) {
                    if (action === 'continue_execution' && d.status === 'start_failed') {
                        toast(`${_tf('proj_meeting_blocker_continue_failed', 'Meeting wait was cleared, but task start failed', '已退出会议等待，但任务启动失败')}：${d.error}`, 'error');
                    } else {
                        toast(d.error, 'error');
                    }
                    await refreshProjectExecutionProject(taskId);
                    return;
                }
                const startResult = d.startResult || {};
                if (action === 'continue_execution' && startResult.ok) {
                    toast(_tf('proj_meeting_blocker_continue_started', 'Task execution restarted', '任务已继续执行'), 'success');
                } else {
                    toast(_tf('proj_meeting_blocker_updated', 'Meeting wait state updated', '会议等待状态已更新'), 'success');
                }
                await refreshProjectExecutionProject(taskId);
            } catch (e) {
                toast(String(e.message || e), 'error');
            }
        });
    }

    async function projectExecutionReviewStartAction(taskId, attemptId) {
        const p = state.currentProject;
        if (!p) return;
        const actionKey = `project-exec-review-start:${p.id}:${taskId}:${attemptId || ''}`;
        return runActionOnce(actionKey, async () => {
            try {
                const d = await api.projectExecutionReviewStart(p.id, taskId, attemptId);
                if (d.error) { toast(d.error, 'error'); await refreshProjectExecutionProject(taskId); return; }
                toast(_t('proj_review_started'), 'success');
                state.workflow.active = true;
                state.workflow.phase = 'reviewing';
                state.workflow.currentTaskId = taskId;
                startProjectExecutionPolling();
                await refreshProjectExecutionProject(taskId);
            } catch (e) { toast(_t('proj_start_review_failed'), 'error'); }
        });
    }

    async function projectExecutionAcceptAction(taskId, action, attemptId) {
        const p = state.currentProject;
        if (!p) return;
        if (action !== 'accept') {
            showProjectExecutionFeedbackDialog(taskId, action, attemptId);
            return;
        }
        showProjectExecutionAcceptDialog(taskId, attemptId);
    }

    function showProjectExecutionAcceptDialog(taskId, attemptId) {
        const overlay = document.getElementById('proj-form-overlay');
        if (!overlay) return;
        const task = state.currentProject && (state.currentProject.tasks || []).find(t => t.id === taskId);
        const acceptanceChecklist = ((task && task.checklist) || []).filter(item => item && item.source !== 'meeting_action_item' && item.source !== 'meeting_risk');
        const hasAcceptanceChecklist = acceptanceChecklist.length > 0;
        state.acceptanceDialog = { taskId, action: 'accept', attemptId, allowEmptyChecklist: !hasAcceptanceChecklist };
        overlay.classList.remove('hidden');
        overlay.innerHTML = `
        <div class="proj-form-modal" style="position:static;padding:0;background:transparent" onclick="event.stopPropagation()">
            <div class="proj-form-box proj-acceptance-dialog" role="dialog" aria-modal="true" aria-labelledby="proj-acceptance-dialog-title">
                <div class="proj-form-title" id="proj-acceptance-dialog-title">确认验收</div>
                <div class="proj-acceptance-task">${escHtml(task ? task.title : '')}</div>
                <div class="proj-form-help">${hasAcceptanceChecklist ? '确认验收通过，并将任务移动到 Done？' : '当前任务还没有验收清单。建议先创建并完成 checklist；如果这个任务确实不需要 checklist，可以跳过空清单并完成任务。'}</div>
                <div class="proj-form-actions">
                    <button class="proj-btn" onclick="ProjMgr.hideFormModal()">取消</button>
                    <button class="proj-btn proj-btn-primary" onclick="ProjMgr.submitProjectExecutionAcceptance()">${hasAcceptanceChecklist ? '确认通过' : '仍然跳过'}</button>
                </div>
            </div>
        </div>`;
    }

    function showProjectExecutionFeedbackDialog(taskId, action, attemptId) {
        const overlay = document.getElementById('proj-form-overlay');
        if (!overlay) return;
        const task = state.currentProject && (state.currentProject.tasks || []).find(t => t.id === taskId);
        const isRework = action === 'reject_and_rework';
        state.acceptanceDialog = { taskId, action, attemptId };
        overlay.classList.remove('hidden');
        overlay.innerHTML = `
        <div class="proj-form-modal" style="position:static;padding:0;background:transparent" onclick="event.stopPropagation()">
            <div class="proj-form-box proj-acceptance-dialog" role="dialog" aria-modal="true" aria-labelledby="proj-acceptance-dialog-title">
                <div class="proj-form-title" id="proj-acceptance-dialog-title">${isRework ? '退回返工' : '标记阻塞'}</div>
                <div class="proj-acceptance-task">${escHtml(task ? task.title : '')}</div>
                <div class="proj-form-group">
                    <label class="proj-form-label">${isRework ? '退回/返工原因' : '阻塞原因'} *</label>
                    <textarea class="proj-form-textarea proj-acceptance-textarea" id="proj-acceptance-feedback" placeholder="${isRework ? '说明需要补充或重做的内容...' : '说明为什么无法继续推进...'}" autofocus></textarea>
                </div>
                <div class="proj-form-actions">
                    <button class="proj-btn" onclick="ProjMgr.hideFormModal()">取消</button>
                    <button class="proj-btn ${isRework ? 'proj-btn-primary' : 'proj-btn-stop'}" onclick="ProjMgr.submitProjectExecutionFeedback()">${isRework ? '确认退回' : '确认阻塞'}</button>
                </div>
            </div>
        </div>`;
        const input = document.getElementById('proj-acceptance-feedback');
        if (input) input.focus();
    }

    async function submitProjectExecutionFeedbackAction() {
        const dialog = state.acceptanceDialog;
        if (!dialog) return;
        const input = document.getElementById('proj-acceptance-feedback');
        const feedback = input ? input.value : '';
        if (!feedback.trim()) { toast(_t('proj_feedback_required'), 'error'); return; }
        await submitProjectExecutionAcceptance(dialog.taskId, dialog.action, dialog.attemptId, feedback);
    }

    async function submitProjectExecutionAcceptanceAction() {
        const dialog = state.acceptanceDialog;
        if (!dialog) return;
        await submitProjectExecutionAcceptance(dialog.taskId, dialog.action, dialog.attemptId, '', { allowEmptyChecklist: dialog.allowEmptyChecklist === true });
    }

    async function submitProjectExecutionAcceptance(taskId, action, attemptId, feedback, opts = {}) {
        const p = state.currentProject;
        if (!p) return;
        const actionKey = `project-exec-accept:${p.id}:${taskId}:${attemptId || ''}:${action}`;
        return runActionOnce(actionKey, async () => {
            try {
                markDialogSubmitting(true);
                const d = await api.projectExecutionAccept(p.id, taskId, action, attemptId, feedback, opts);
                if (d.error) { toast(d.error, 'error'); markDialogSubmitting(false); await refreshProjectExecutionProject(taskId); return; }
                toast(action === 'accept' ? '任务已验收完成' : (d.status === 'reworking' ? '已退回并开始返工' : '验收状态已更新'), 'success');
                hideFormModal();
                if (d.status === 'reworking') {
                    state.workflow.active = true;
                    state.workflow.phase = 'reworking';
                    state.workflow.currentTaskId = taskId;
                    startProjectExecutionPolling();
                }
                await refreshProjectExecutionProject(taskId);
            } catch (e) {
                markDialogSubmitting(false);
                toast(_t('proj_accept_action_failed'), 'error');
            }
        }, { silentDuplicate: false });
    }

    function projectExecutionBoardSignature(project) {
        return JSON.stringify(((project && project.tasks) || []).map(t => [
            t.id,
            t.columnId,
            t.order || 0,
            t.executionState || '',
            t.activeAttemptId || '',
            t.completedAt || '',
            t.blockedReason || '',
            (t.reviewResult || {}).status || '',
        ]));
    }

    async function refreshProjectExecutionProject(selectedTaskId, opts = {}) {
        const p = state.currentProject;
        if (!p) return;
        const oldSignature = projectExecutionBoardSignature(p);
        const fresh = await api.getProject(p.id);
        if (!fresh.project) return;
        state.currentProject = {
            ...fresh.project,
            scheduledCronJobs: p.scheduledCronJobs,
            scheduledCronLoadError: p.scheduledCronLoadError,
            scheduledCronLoading: p.scheduledCronLoading,
        };
        const taskId = selectedTaskId || (state.currentTask && state.currentTask.id);
        if (taskId) state.currentTask = (state.currentProject.tasks || []).find(t => t.id === taskId) || null;
        const mc = getMainContent();
        const newSignature = projectExecutionBoardSignature(state.currentProject);
        if (mc && state.view === 'board' && (!opts.lightweight || oldSignature !== newSignature)) {
            rerenderProjectBoard({ lightweight: opts.lightweight === true });
        }
        if (state.currentTask && !detailPanelActiveEditor()) renderDetailPanel(state.currentTask, { preserveScroll: opts.lightweight === true });
        updateWorkflowUI();
        loadProjectMeetingRequests(state.currentProject.id).then(function () {
            if (state.currentProject && state.currentProject.id === p.id && state.view === 'board') {
                rerenderProjectBoard({ lightweight: true });
            }
        });
    }

    function startProjectExecutionPolling() {
        stopWorkflowPolling();
        state.workflow.pollTimer = setInterval(async () => {
            const p = state.currentProject;
            if (!p) return stopWorkflowPolling();
            try {
                const d = await api.projectExecutionStatus(p.id);
                state.workflow.active = d.active;
                state.workflow.phase = d.phase || 'idle';
                state.workflow.currentTaskId = d.currentTaskId;
                state.workflow.startMode = d.startMode || 'continuous';
                state.workflow.flowStopReason = d.flowStopReason || null;
                const openTaskId = state.currentTask && state.currentTask.id;
                await refreshProjectExecutionProject(openTaskId || null, { lightweight: true });
                pollWorkflowChat();
                if (!d.active && !projectExecutionHasRunningTask(state.currentProject)) stopWorkflowPolling();
            } catch (e) { /* keep the last visible state */ }
        }, 2500);
    }

    async function workflowStartAction() {
        const p = state.currentProject;
        if (!p) return;
        const actionKey = `workflow-start:${p.id}`;
        return runActionOnce(actionKey, async () => {
        const autoMode = document.getElementById('wf-auto-toggle');
        const isAuto = autoMode ? autoMode.checked : false;
        try {
            const d = await api.workflowStart(p.id, isAuto);
            if (d.error) { toast(d.error, 'error'); return; }
            toast(_t('proj_workflow_started'), 'success');
            state.workflow.active = true;
            state.workflow.autoMode = isAuto;
            updateWorkflowUI();
            startWorkflowPolling();
        } catch (e) { toast(_t('proj_failed_start_workflow'), 'error'); }
        });
    }

    async function workflowStopAction() {
        const p = state.currentProject;
        if (!p) return;
        const actionKey = `workflow-stop:${p.id}`;
        return runActionOnce(actionKey, async () => {
        try {
            await api.workflowStop(p.id);
            toast(_t('proj_workflow_stopped_msg'), 'info');
            state.workflow.active = false;
            state.workflow.phase = 'stopped';
            updateWorkflowUI();
            stopWorkflowPolling();
        } catch (e) { toast(_t('proj_failed_stop_workflow'), 'error'); }
        });
    }

    async function refreshProjectScheduledCronPanel() {
        const p = state.currentProject;
        if (!p) return;
        const fresh = await api.getProject(p.id);
        if (fresh.project) state.currentProject = fresh.project;
        await loadScheduledCronForCurrentProject();
        const mc = getMainContent();
        if (mc) {
            mc.innerHTML = renderBoardView();
            bindBoardEvents();
            populateBoardScoreboard();
        }
    }

    async function createProjectCronPromptAction() {
        const p = state.currentProject;
        if (!p) return;
        showFormModal('project-cron', p);
    }

    function editProjectCronAction(cronId) {
        const p = state.currentProject;
        if (!p) return;
        const job = (p.scheduledCronJobs || []).find(j => String(j.id) === String(cronId));
        if (!job) {
            toast(_t('proj_scheduled_cron_not_found'), 'error');
            return;
        }
        showFormModal('project-cron', p, job);
    }

    async function toggleProjectCronPauseAction() {
        const p = state.currentProject;
        if (!p) return;
        const actionKey = `cron-pause:${p.id}`;
        return runActionOnce(actionKey, async () => {
            try {
                const d = await api.updateProject(p.id, { scheduledCronPaused: !p.scheduledCronPaused });
                if (!d.ok) throw new Error(d.error || 'update failed');
                state.currentProject = d.project;
                await refreshProjectScheduledCronPanel();
                toast(state.currentProject.scheduledCronPaused ? _t('proj_scheduled_cron_paused') : _t('proj_scheduled_cron_resumed'), 'success');
            } catch (e) {
                toast(_t('proj_scheduled_cron_pause_failed', { message: e.message }), 'error');
            }
        });
    }

    async function runProjectCronAction(cronId) {
        const p = state.currentProject;
        if (!p) return;
        const actionKey = `cron-run:${p.id}:${cronId}`;
        return runActionOnce(actionKey, async () => {
            try {
                const d = await api.runScheduledCron(p.id, cronId);
                if (!d.ok) throw new Error(d.error || 'run failed');
                toast(_t('proj_scheduled_cron_triggered'), 'success');
                await refreshProjectScheduledCronPanel();
            } catch (e) {
                toast(_t('proj_scheduled_cron_run_failed', { message: e.message }), 'error');
            }
        });
    }

    async function toggleProjectCronAction(cronId, currentlyEnabled) {
        const p = state.currentProject;
        if (!p) return;
        const actionKey = `cron-toggle:${p.id}:${cronId}`;
        return runActionOnce(actionKey, async () => {
            try {
                const d = await api.updateScheduledCron(p.id, cronId, { enabled: !currentlyEnabled });
                if (!d.ok) throw new Error(d.error || 'update failed');
                toast(currentlyEnabled ? _t('proj_scheduled_cron_disabled') : _t('proj_scheduled_cron_enabled'), 'success');
                await refreshProjectScheduledCronPanel();
            } catch (e) {
                toast(_t('proj_scheduled_cron_update_failed', { message: e.message }), 'error');
            }
        });
    }

    async function deleteProjectCronAction(cronId) {
        const p = state.currentProject;
        if (!p) return;
        const actionKey = `cron-delete:${p.id}:${cronId}`;
        return runActionOnce(actionKey, async () => {
            if (!confirm(_t('proj_scheduled_cron_delete_confirm'))) return;
            try {
                const d = await api.deleteScheduledCron(p.id, cronId);
                if (!d.ok) throw new Error(d.error || 'delete failed');
                toast(_t('proj_scheduled_cron_deleted'), 'success');
                await refreshProjectScheduledCronPanel();
            } catch (e) {
                toast(_t('proj_scheduled_cron_delete_failed', { message: e.message }), 'error');
            }
        });
    }

    async function toggleAutoModeAction(enabled) {
        const p = state.currentProject;
        if (!p) return;
        try {
            await api.setAutoMode(p.id, enabled);
            state.workflow.autoMode = enabled;
            p.autoMode = enabled;
            toast(enabled ? _t('proj_auto_mode_on') : _t('proj_auto_mode_off'), 'info');
        } catch (e) { toast(_t('proj_failed_toggle_auto'), 'error'); }
    }

    function startWorkflowPolling() {
        stopWorkflowPolling();
        state.workflow.pollTimer = setInterval(pollWorkflowStatus, 3000);
    }

    function stopWorkflowPolling() {
        if (state.workflow.pollTimer) {
            clearInterval(state.workflow.pollTimer);
            state.workflow.pollTimer = null;
        }
    }

    async function pollWorkflowStatus() {
        const p = state.currentProject;
        if (!p) { stopWorkflowPolling(); return; }
        try {
            const d = await api.workflowStatus(p.id);
            const prevPhase = state.workflow.phase;
            const prevTaskId = state.workflow.currentTaskId;
            state.workflow.active = d.active;
            state.workflow.autoMode = d.autoMode;
            state.workflow.phase = d.phase;
            state.workflow.currentTaskId = d.currentTaskId;
            state.workflow.error = d.error;
            updateWorkflowUI();

            // If task moved or phase changed, refresh board
            if (d.active && (d.currentTaskId !== prevTaskId || d.phase !== prevPhase)) {
                const fresh = await api.getProject(p.id);
                if (fresh.project) {
                    state.currentProject = fresh.project;
                    if (state.currentTask && state.currentTask.id) {
                        const liveTask = fresh.project.tasks.find(t => t.id === state.currentTask.id);
                        if (liveTask) {
                            state.currentTask = liveTask;
                            if (!detailPanelActiveEditor()) renderDetailPanel(liveTask, { preserveScroll: true });
                        }
                    }
                    const mc = getMainContent();
                    if (mc && state.view === 'board') {
                        mc.innerHTML = renderBoardView();
                        bindBoardEvents();
                        populateBoardScoreboard();
                        updateActiveColumnIndicator();
                    }
                }
            }

            // Update active column indicator
            updateActiveColumnIndicator();

            // Poll workflow chat
            pollWorkflowChat();

            // Stop polling if workflow ended
            if (!d.active && d.phase !== 'awaiting_user_review') {
                stopWorkflowPolling();
                // Final board refresh
                const fresh = await api.getProject(p.id);
                if (fresh.project) {
                    state.currentProject = fresh.project;
                    const mc = getMainContent();
                    if (mc && state.view === 'board') {
                        mc.innerHTML = renderBoardView();
                        bindBoardEvents();
                        populateBoardScoreboard();
                    }
                }
                clearActiveColumnIndicator();
            }
        } catch (e) { /* silent */ }
    }

    async function pollWorkflowChat() {
        const p = state.currentProject;
        if (!p) return;
        try {
            const d = await api.workflowChat(p.id);
            renderWorkflowChat(d);
        } catch (e) { /* silent */ }
    }

    function renderWorkflowChat(data) {
        const container = document.getElementById('proj-wf-chat-messages');
        const liveDot = document.getElementById('proj-chat-live-dot');
        if (!container) return;

        const msgs = data.messages || [];
        const isActive = data.phase && data.phase !== 'idle' && data.phase !== 'stopped';

        if (liveDot) {
            liveDot.className = 'proj-wf-chat-live' + (isActive ? ' live' : '');
        }

        if (msgs.length === 0) {
            container.innerHTML = `<div class="proj-chat-empty">${_t('proj_workflow_chat_empty')}</div>`;
            return;
        }

        const wasAtBottom = container.scrollTop + container.clientHeight >= container.scrollHeight - 20;

        container.innerHTML = msgs.map(m => {
            const isAssistant = m.role === 'assistant';
            const isUser = m.role === 'user';
            const isTool = m.role === 'tool' || m.role === 'toolCall';
            let cls = 'proj-chat-msg';
            if (isAssistant) cls += ' msg-assistant';
            else if (isUser) cls += ' msg-user';
            else if (isTool) cls += ' msg-tool';

            let text = m.text || '';
            // Truncate very long messages
            if (text.length > 500) text = text.substring(0, 500) + '…';
            text = escHtml(text);
            let thinkingHtml = '';
            if (isAssistant && m.thinking) {
                let thinking = String(m.thinking || '');
                if (thinking.length > 8000) thinking = thinking.substring(0, 8000) + '…';
                const status = m.reasoningStatus === 'done' ? _t('complete') : _t('live');
                thinkingHtml = `<details class="proj-chat-thinking">
                    <summary><span>${_t('reasoning_summary')}</span><span class="proj-chat-thinking-state">${escHtml(status)}</span></summary>
                    <pre>${escHtml(thinking)}</pre>
                </details>`;
            }

            // Format timestamp in user's local timezone
            let timeStr = '';
            const timestamp = m.timestamp || m.epochMs || m.ts;
            if (timestamp) {
                const d = new Date(timestamp);
                if (!isNaN(d.getTime())) {
                    timeStr = d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
                }
            }
            const timeHtml = timeStr ? `<span class="proj-chat-msg-time">${timeStr}</span>` : '';

            // Show tool calls as activity indicators
            let toolHtml = '';
            if (m.tools && m.tools.length > 0) {
                const toolNames = m.tools.map(t => '🔧 ' + escHtml(t.name)).join(', ');
                toolHtml = `<div class="proj-chat-msg-tools">${toolNames}</div>`;
            }

            return `<div class="${cls}">
                ${timeHtml}
                ${thinkingHtml}
                <div class="proj-chat-msg-text">${text}</div>
                ${toolHtml}
            </div>`;
        }).join('');

        // Auto-scroll if was at bottom
        if (wasAtBottom) {
            container.scrollTop = container.scrollHeight;
        }
    }

    function updateActiveColumnIndicator() {
        // Clear all active indicators
        document.querySelectorAll('.proj-col-header').forEach(h => h.classList.remove('col-active-work'));

        if (!state.workflow.active || !state.workflow.currentTaskId || !state.currentProject) return;

        // Find which column the current task is in
        const task = state.currentProject.tasks.find(t => t.id === state.workflow.currentTaskId);
        if (!task) return;
        const colEl = document.getElementById(`col-${task.columnId}`);
        if (colEl) {
            const header = colEl.querySelector('.proj-col-header');
            if (header) header.classList.add('col-active-work');
        }
    }

    function clearActiveColumnIndicator() {
        document.querySelectorAll('.proj-col-header').forEach(h => h.classList.remove('col-active-work'));
    }

    function updateWorkflowUI() {
        const startBtn = document.getElementById('wf-start-btn');
        const execStartBtn = document.getElementById('proj-exec-start-btn');
        const execRestartBtn = document.getElementById('proj-exec-restart-btn');
        const execStopBtn = document.getElementById('proj-exec-stop-btn');
        const stopBtn = document.getElementById('wf-stop-btn');
        const badge = document.getElementById('wf-status-badge');
        const autoToggle = document.getElementById('wf-auto-toggle');

        if (execStartBtn) {
            if (state.workflow.active) { execStartBtn.classList.add('hidden'); }
            else { execStartBtn.classList.remove('hidden'); }
        }
        if (execRestartBtn) {
            if (state.workflow.active) { execRestartBtn.classList.add('hidden'); }
            else { execRestartBtn.classList.remove('hidden'); }
        }
        if (execStopBtn) {
            if (state.workflow.active) { execStopBtn.classList.remove('hidden'); }
            else { execStopBtn.classList.add('hidden'); }
        }
        if (startBtn) {
            if (state.workflow.active) { startBtn.classList.add('hidden'); }
            else { startBtn.classList.remove('hidden'); }
        }
        if (stopBtn) {
            if (state.workflow.active) { stopBtn.classList.remove('hidden'); }
            else { stopBtn.classList.add('hidden'); }
        }
        if (autoToggle) {
            autoToggle.checked = state.workflow.autoMode;
        }
        if (badge) {
            const phase = state.workflow.phase || 'idle';
            const phaseLabels = {
                'idle': '',
                'starting': _t('proj_workflow_starting'),
                'dispatching': _t('proj_workflow_dispatching'),
                'in_progress': _t('proj_workflow_in_progress'),
                'reviewing': _t('proj_workflow_reviewing'),
                'reworking': _t('proj_workflow_reworking'),
                'awaiting_user_review': _t('proj_workflow_awaiting_user'),
                'task_done': _t('proj_workflow_task_done'),
                'stopped': _t('proj_workflow_stopped'),
                'stalled': _t('proj_workflow_stalled'),
                'error': _t('proj_workflow_error'),
                'executing': '执行中',
                'execution_complete': '执行完成',
                'awaiting_user_acceptance': '等待用户验收',
                'blocked': '阻塞',
                'done': '已完成',
                'no_eligible_task': '没有可启动任务',
                'dirty_worktree_confirmation_required': '等待确认工作区变更',
                'executor_required': '缺少执行 Agent',
                'reviewer_required': '缺少 Reviewer',
                'reviewer_skip_confirmation_required': '确认跳过审查',
                'reviewer_not_independent': 'Reviewer 需独立',
                'workspace_required': '缺少工作区',
                'workspace_missing': '工作区不存在',
                'start_failed': '启动失败',
            };
            badge.textContent = phaseLabels[phase] || phase || '';
            badge.className = 'proj-wf-status' + (state.workflow.active ? ' wf-active' : '') + (phase === 'awaiting_user_review' ? ' wf-attention' : '') + (phase === 'error' ? ' wf-error' : '');
            if (state.workflow.error && phase === 'error') {
                badge.title = state.workflow.error;
            } else if (state.workflow.flowStopReason) {
                badge.title = state.workflow.flowStopReason;
            }
        }
    }

    // Review Check functions
    async function updateReviewItemStatusAction(index, newStatus) {
        const task = state.currentTask;
        const p = state.currentProject;
        if (!task || !p || !task.reviewCheck) return;
        task.reviewCheck[index].status = newStatus;
        renderDetailPanel(task);
    }

    async function saveReviewCheckAction() {
        const task = state.currentTask;
        const p = state.currentProject;
        if (!task || !p || !task.reviewCheck) return;
        try {
            await api.updateReviewCheck(p.id, task.id, task.reviewCheck);
            toast(_t('proj_review_saved'), 'success');
        } catch (e) { toast(_t('proj_failed_save_review'), 'error'); }
    }

    // Check workflow status when opening a board (handles page refresh)
    async function checkWorkflowOnOpen(projectId) {
        const p = state.currentProject;
        if (!p || (projectId && p.id !== projectId)) return;
        if (p.projectExecutionEnabled) {
            try {
                const d = await api.projectExecutionStatus(p.id);
                if (!state.currentProject || state.currentProject.id !== p.id) return;
                state.workflow.active = d.active;
                state.workflow.phase = d.phase || 'idle';
                state.workflow.currentTaskId = d.currentTaskId;
                state.workflow.startMode = d.startMode || 'continuous';
                state.workflow.flowStopReason = d.flowStopReason || null;
                p.projectExecutionStartMode = d.startMode || p.projectExecutionStartMode || 'continuous';
                updateWorkflowUI();
                pollWorkflowChat();
                if (d.active || projectExecutionHasRunningTask(p)) startProjectExecutionPolling();
            } catch (e) { /* non-fatal */ }
            return;
        }
        try {
            const d = await api.workflowStatus(p.id);
            if (!state.currentProject || state.currentProject.id !== p.id) return;
            state.workflow.active = d.active;
            state.workflow.autoMode = d.autoMode;
            state.workflow.phase = d.phase || 'idle';
            state.workflow.currentTaskId = d.currentTaskId;
            state.workflow.error = d.error;
            updateWorkflowUI();
            updateActiveColumnIndicator();

            // Start polling if workflow is active OR if there are tasks in progress
            // (handles page refresh — workflow thread is still running server-side)
            const needsPolling = d.active
                || d.phase === 'awaiting_user_review'
                || d.phase === 'in_progress'
                || d.phase === 'reviewing'
                || d.phase === 'reworking'
                || d.phase === 'dispatching';
            if (needsPolling) {
                startWorkflowPolling();
                pollWorkflowChat();
            } else {
                // Even if not actively running, fetch chat once to show last session
                pollWorkflowChat();
            }
        } catch (e) { /* silent */ }
    }

    // ── PUBLIC API ────────────────────────────────────────────────
    window.ProjMgr = {
        openProjectsManager,
        closeProjectsModal,
        showListView,
        openProject,
        backToList,
        newProjectDialog,
        editProjectDialog,
        deleteProject,
        archiveProject,
        filterChange,
        showTemplatesView,
        showReport,
        showArtifacts,
        openArtifact,
        switchArtifactMode,
        setArtifactDirs,
        deleteArtifact: deleteArtifactAction,
        deleteArtifactDir: deleteArtifactDirAction,
        exportReport,
        saveAsTemplateDialog,
        submitSaveTemplate,
        deleteTemplate,
        openTaskDetail,
        closeDetailPanel,
        updateTaskField,
        saveDescription,
        switchDescTab,
        toggleChecklistItem,
        deleteChecklistItem,
        addChecklistItem,
        editChecklistItem,
        handleTagKey,
        addTag,
        removeTag,
        submitComment,
        toggleComments: toggleCommentsAction,
        deleteCurrentTask,
        duplicateTask,
        addColumn,
        renameColumn,
        showQuickAdd,
        hideQuickAdd,
        submitQuickAdd,
        hideFormModal,
        submitTextInputDialog: submitTextInputDialogAction,
        toggleProjectExecutionFields,
        submitNewProject,
        submitEditProject,
        // Drag & drop
        onDragStart,
        onDragEnd,
        onDragOver,
        onDragLeave,
        onDrop,
        onTouchStart,
        // Gamification
        refreshLeaderboard,
        // Workflow
        workflowStart: workflowStartAction,
        workflowStop: workflowStopAction,
        toggleAutoMode: toggleAutoModeAction,
        createProjectCronPrompt: createProjectCronPromptAction,
        editProjectCron: editProjectCronAction,
        toggleProjectCronTaskField,
        toggleProjectCronScheduleFields,
        submitProjectCron,
        toggleProjectCronPause: toggleProjectCronPauseAction,
        runProjectCron: runProjectCronAction,
        toggleProjectCron: toggleProjectCronAction,
        deleteProjectCron: deleteProjectCronAction,
        openProjectResetDialog: openProjectResetDialogAction,
        projectReset: projectResetAction,
        updateReviewItemStatus: updateReviewItemStatusAction,
        saveReviewCheck: saveReviewCheckAction,
        projectExecutionStart: projectExecutionStartAction,
        projectExecutionProjectStart: projectExecutionProjectStartAction,
        projectExecutionProjectRestart: projectExecutionProjectRestartAction,
        setProjectExecutionStartMode: setProjectExecutionStartModeAction,
        projectExecutionCancelActive: projectExecutionCancelActiveAction,
        copyWorkspacePath: copyWorkspacePathAction,
        projectExecutionCancel: projectExecutionCancelAction,
        projectExecutionMeetingBlocker: projectExecutionMeetingBlockerAction,
        viewMeetingBlocker,
        projectExecutionReviewStart: projectExecutionReviewStartAction,
        projectExecutionAccept: projectExecutionAcceptAction,
        submitProjectExecutionFeedback: submitProjectExecutionFeedbackAction,
        submitProjectExecutionAcceptance: submitProjectExecutionAcceptanceAction,
        resolveConfirm: resolveConfirmAction,
        openMeetingRequestsQueue,
    };

})();
