// Trusted browser review surface for Agent-authored project drafts.
(function () {
    'use strict';

    const state = {
        requests: [],
        selectedId: '',
        detail: null,
        loading: false,
        error: '',
        actionMessage: '',
        createdProject: null,
        pendingActions: new Set(),
        confirmationKeys: {},
    };

    const esc = value => String(value == null ? '' : value)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#39;');
    const pretty = value => JSON.stringify(value == null ? {} : value, null, 2);
    const zh = () => String(document.documentElement.lang || '').toLowerCase().startsWith('zh');
    const text = (english, chinese) => zh() ? chinese : english;
    const requestFetch = (input, init) => window.i18n.managementFetch(input, init);

    async function listRequests() {
        const response = await requestFetch(
            '/api/project-authoring/requests?state=pending,failed,materializing&limit=100',
        );
        const payload = await response.json();
        if (!response.ok || payload.ok === false) throw new Error(payload.error || 'Unable to load drafts');
        return payload.requests || [];
    }

    async function getRequest(id) {
        const response = await requestFetch(`/api/project-authoring/requests/${encodeURIComponent(id)}`);
        const payload = await response.json();
        if (!response.ok || payload.ok === false) throw new Error(payload.error || 'Unable to load draft');
        return payload.request;
    }

    async function requestJson(input, init) {
        const response = await requestFetch(input, init);
        const payload = await response.json();
        if (!response.ok || payload.ok === false) {
            const error = new Error(payload.error || text('Review action failed', '评审操作失败'));
            error.payload = payload;
            throw error;
        }
        return payload;
    }

    async function editRequest(id, revision, draft) {
        return requestJson(`/api/project-authoring/requests/${encodeURIComponent(id)}`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ expectedRevision: revision, draft }),
        });
    }

    async function confirmRequest(id, revision, confirmationKey) {
        return requestJson(`/api/project-authoring/requests/${encodeURIComponent(id)}/confirm`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ expectedRevision: revision, confirmationKey }),
        });
    }

    async function rejectRequest(id, revision, reason) {
        return requestJson(`/api/project-authoring/requests/${encodeURIComponent(id)}/reject`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ expectedRevision: revision, reason }),
        });
    }

    function container() {
        return document.getElementById('proj-main-content');
    }

    function stateLabel(value) {
        return {
            pending: text('Pending review', '待评审'),
            failed: text('Needs attention', '需要处理'),
            materializing: text('Creating project', '正在创建项目'),
            confirmed: text('Confirmed', '已确认'),
            rejected: text('Rejected', '已拒绝'),
        }[value] || value || text('Unknown', '未知');
    }

    function reviewerRecommendations(draft) {
        return (draft && Array.isArray(draft.tasks) ? draft.tasks : [])
            .map((task, index) => ({ task, index, recommendation: task.reviewerRecommendation }))
            .filter(item => item.recommendation && (
                item.recommendation.recommended
                || item.recommendation.rationale
                || (item.recommendation.triggers || []).length
            ));
    }

    function renderRequestList() {
        if (!state.requests.length) {
            return `<div class="par-empty">${text('No Agent project drafts need review.', '当前没有需要评审的 Agent 项目草稿。')}</div>`;
        }
        return state.requests.map(request => `
            <button class="par-request ${request.id === state.selectedId ? 'is-selected' : ''}"
                onclick="ProjectAuthoringReview.select('${esc(request.id)}')">
                <span class="par-request-title">${esc(request.title || request.id)}</span>
                <span class="par-request-meta">${esc(request.requestingAgentId || '')} · ${esc(stateLabel(request.state))} · r${esc(request.revision)}</span>
                <span class="par-request-count">${esc(request.taskCount || 0)} ${text('tasks', '个任务')}</span>
            </button>
        `).join('');
    }

    function renderIssues(request) {
        const issues = Array.isArray(request.issues) ? request.issues : [];
        if (!request.error && !request.code && !issues.length) return '';
        return `
            <section class="par-panel par-error-panel" data-project-authoring-errors>
                <h3>${text('Validation and failure details', '校验与失败信息')}</h3>
                ${request.code ? `<div class="par-error-code">${esc(request.code)}</div>` : ''}
                ${request.error ? `<div>${esc(request.error)}</div>` : ''}
                ${issues.length ? `<ul>${issues.map(issue => `<li><code>${esc(issue.path || '')}</code> ${esc(issue.message || issue.error || '')}</li>`).join('')}</ul>` : ''}
            </section>`;
    }

    function renderDetail() {
        const request = state.detail;
        if (!request) {
            return `<div class="par-empty">${text('Select a draft to inspect its complete proposal.', '请选择一个草稿查看完整提案。')}</div>`;
        }
        const original = request.originalDraft || {};
        const working = request.workingDraft || request.approvedSnapshot || {};
        const recommendations = reviewerRecommendations(working);
        const mutable = request.state === 'pending' || request.state === 'failed';
        const busy = state.pendingActions.has(request.id);
        return `
            <div class="par-detail" data-request-id="${esc(request.id)}" data-request-revision="${esc(request.revision)}">
                <header class="par-detail-header">
                    <div>
                        <h2>${esc(working.title || original.title || request.id)}</h2>
                        <div>${esc(stateLabel(request.state))} · ${text('Revision', '版本')} ${esc(request.revision)} · ${esc(request.requestingAgentId || '')}</div>
                    </div>
                    <span class="par-state par-state-${esc(request.state)}">${esc(stateLabel(request.state))}</span>
                </header>
                ${renderIssues(request)}
                ${state.actionMessage ? `<div class="par-action-message">${esc(state.actionMessage)}</div>` : ''}
                ${state.createdProject ? `
                    <div class="par-created-project">
                        <span>${text('Project created successfully.', '项目已成功创建。')}</span>
                        <button class="proj-btn proj-btn-primary" onclick="ProjectAuthoringReview.openCreatedProject()">
                            ${text('Open project', '进入项目')} · ${esc(state.createdProject.title || state.createdProject.id)}
                        </button>
                    </div>` : ''}
                <div class="par-two-column">
                    <section class="par-panel">
                        <h3>${text('Original Agent proposal', 'Agent 原始提案')}</h3>
                        <pre id="project-authoring-original-draft">${esc(pretty(original))}</pre>
                    </section>
                    <section class="par-panel">
                        <h3>${text('Approved configuration (editable)', '待确认配置（可编辑）')}</h3>
                        <textarea id="project-authoring-approved-draft" spellcheck="false">${esc(pretty(working))}</textarea>
                        <div class="par-help">${text(
                            'Edits are local until saved in the review actions.',
                            '当前编辑仅保留在页面中，需通过评审操作保存。',
                        )}</div>
                    </section>
                </div>
                <div class="par-two-column">
                    <section class="par-panel" data-project-authoring-reviewers>
                        <h3>${text('Reviewer recommendations', 'Reviewer 推荐')}</h3>
                        ${recommendations.length ? recommendations.map(item => `
                            <article class="par-reviewer-item">
                                <strong>${esc(item.task.title || `${text('Task', '任务')} ${item.index + 1}`)}</strong>
                                <div>${esc(item.recommendation.rationale || text('No rationale supplied', '未提供推荐理由'))}</div>
                                <div class="par-chip-row">${(item.recommendation.triggers || []).map(trigger => `<span>${esc(trigger)}</span>`).join('')}</div>
                                <code>${esc(pretty(item.recommendation.candidate || {}))}</code>
                            </article>
                        `).join('') : `<div class="par-empty-inline">${text('No reviewer was recommended.', '未推荐 Reviewer。')}</div>`}
                    </section>
                    <section class="par-panel" data-project-authoring-scheduling>
                        <h3>${text('Template and recurrence', '模板与周期设置')}</h3>
                        <h4>${text('Template', '模板')}</h4>
                        <pre>${esc(pretty(working.template || {}))}</pre>
                        <h4>${text('Recurrence', '周期')}</h4>
                        <pre>${esc(pretty(working.recurrence || {}))}</pre>
                        <h4>${text('Maintenance mode', '维护模式')}</h4>
                        <code>${esc(working.agentMaintenanceMode || '')}</code>
                    </section>
                </div>
                ${mutable ? `
                    <div class="par-actions" data-project-authoring-actions>
                        <button class="proj-btn" ${busy ? 'disabled' : ''} onclick="ProjectAuthoringReview.saveEdit()">
                            ${busy ? text('Processing…', '处理中…') : text('Save edits', '保存编辑')}
                        </button>
                        <button class="proj-btn proj-btn-danger" ${busy ? 'disabled' : ''} onclick="ProjectAuthoringReview.reject()">
                            ${text('Reject draft', '拒绝草稿')}
                        </button>
                        <button class="proj-btn proj-btn-primary" ${busy ? 'disabled' : ''} onclick="ProjectAuthoringReview.confirm()">
                            ${text('Confirm and create project', '确认并创建项目')}
                        </button>
                    </div>` : ''}
            </div>`;
    }

    function editedDraft() {
        const field = document.getElementById('project-authoring-approved-draft');
        if (!field) throw new Error(text('Editable configuration was not found.', '未找到可编辑配置。'));
        try {
            return JSON.parse(field.value);
        } catch (error) {
            throw new Error(text('Approved configuration must be valid JSON.', '待确认配置必须是有效 JSON。'));
        }
    }

    function draftChanged(request, draft) {
        return JSON.stringify(draft) !== JSON.stringify(request.workingDraft || request.approvedSnapshot || {});
    }

    async function runAction(action, callback) {
        const request = state.detail;
        if (!request) return;
        const key = `${request.id}:${action}`;
        if (state.pendingActions.has(request.id)) {
            state.actionMessage = text('This draft already has an action in progress.', '该草稿已有操作正在进行。');
            render();
            return;
        }
        state.pendingActions.add(request.id);
        state.actionMessage = '';
        state.error = '';
        render();
        try {
            await callback(request, key);
        } catch (error) {
            const payload = error.payload || {};
            state.error = String(error.message || error);
            if (Array.isArray(payload.issues) && state.detail) state.detail.issues = payload.issues;
            if (payload.code && state.detail) state.detail.code = payload.code;
        } finally {
            state.pendingActions.delete(request.id);
            render();
        }
    }

    async function saveEdit() {
        let draft;
        try {
            draft = editedDraft();
        } catch (error) {
            state.error = String(error.message || error);
            render();
            return;
        }
        return runAction('edit', async request => {
            if (!draftChanged(request, draft)) {
                state.actionMessage = text('No edits to save.', '没有需要保存的修改。');
                return;
            }
            const payload = await editRequest(request.id, request.revision, draft);
            state.detail = payload.request;
            state.actionMessage = text('Edits saved.', '编辑已保存。');
            await reloadSummary(request.id);
        });
    }

    function confirmationKey(requestId) {
        if (!state.confirmationKeys[requestId]) {
            const suffix = typeof crypto !== 'undefined' && crypto.randomUUID
                ? crypto.randomUUID()
                : `${Date.now()}-${Math.random().toString(16).slice(2)}`;
            state.confirmationKeys[requestId] = `review:${suffix}`;
        }
        return state.confirmationKeys[requestId];
    }

    async function confirmDraft() {
        if (!window.confirm(text(
            'Create this complete project from the approved configuration?',
            '确认按当前配置创建完整项目吗？',
        ))) return;
        let draft;
        try {
            draft = editedDraft();
        } catch (error) {
            state.error = String(error.message || error);
            render();
            return;
        }
        return runAction('confirm', async request => {
            let current = request;
            if (draftChanged(current, draft)) {
                const edited = await editRequest(current.id, current.revision, draft);
                current = edited.request;
                state.detail = current;
            }
            const payload = await confirmRequest(
                current.id,
                current.revision,
                confirmationKey(current.id),
            );
            state.detail = payload.request || current;
            state.createdProject = payload.project || null;
            state.actionMessage = text('Draft confirmed and project created.', '草稿已确认，项目已创建。');
            await reloadSummary(current.id);
        });
    }

    async function rejectDraft() {
        return runAction('reject', async request => {
            const reason = window.prompt(text('Why are you rejecting this draft?', '请输入拒绝该草稿的原因：'), '');
            if (reason == null) return;
            if (!String(reason).trim()) throw new Error(text('A rejection reason is required.', '必须填写拒绝原因。'));
            const payload = await rejectRequest(request.id, request.revision, String(reason).trim());
            state.detail = payload.request;
            state.actionMessage = text('Draft rejected.', '草稿已拒绝。');
            await reloadSummary(request.id);
        });
    }

    async function reloadSummary(selectedId) {
        state.requests = await listRequests();
        state.selectedId = selectedId;
    }

    function openCreatedProject() {
        if (state.createdProject && window.ProjMgr && window.ProjMgr.openProject) {
            window.ProjMgr.openProject(state.createdProject.id);
        }
    }

    function render() {
        const root = container();
        if (!root) return;
        root.innerHTML = `
            <div class="par-root">
                <div class="proj-toolbar par-toolbar">
                    <button class="proj-btn" onclick="ProjMgr.backToList()">${text('Back to projects', '返回项目')}</button>
                    <span class="proj-toolbar-title">${text('Agent project drafts', 'Agent 项目草稿')}</span>
                    <button class="proj-btn" onclick="ProjectAuthoringReview.refresh()">${text('Refresh', '刷新')}</button>
                </div>
                ${state.error ? `<div class="par-load-error">${esc(state.error)}</div>` : ''}
                <div class="par-layout">
                    <aside class="par-list">${renderRequestList()}</aside>
                    <main class="par-main">${state.loading ? `<div class="proj-loading">${text('Loading…', '加载中…')}</div>` : renderDetail()}</main>
                </div>
            </div>`;
    }

    async function select(id) {
        state.selectedId = id;
        state.loading = true;
        state.error = '';
        state.actionMessage = '';
        state.createdProject = null;
        render();
        try {
            state.detail = await getRequest(id);
        } catch (error) {
            state.detail = null;
            state.error = String(error.message || error);
        } finally {
            state.loading = false;
            render();
        }
    }

    async function refresh() {
        state.loading = true;
        state.error = '';
        render();
        try {
            state.requests = await listRequests();
            if (!state.requests.some(request => request.id === state.selectedId)) {
                state.selectedId = state.requests[0] ? state.requests[0].id : '';
            }
            state.detail = state.selectedId ? await getRequest(state.selectedId) : null;
        } catch (error) {
            state.requests = [];
            state.detail = null;
            state.error = String(error.message || error);
        } finally {
            state.loading = false;
            render();
        }
    }

    async function show() {
        state.selectedId = '';
        state.detail = null;
        state.actionMessage = '';
        state.createdProject = null;
        await refresh();
    }

    window.ProjectAuthoringReview = {
        show,
        refresh,
        select,
        saveEdit,
        confirm: confirmDraft,
        reject: rejectDraft,
        openCreatedProject,
    };
}());
