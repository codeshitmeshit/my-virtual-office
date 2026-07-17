// Trusted browser review surface for Agent-authored project drafts.
(function () {
    'use strict';

    const state = {
        requests: [],
        selectedId: '',
        detail: null,
        loading: false,
        error: '',
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
            </div>`;
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
        await refresh();
    }

    window.ProjectAuthoringReview = { show, refresh, select };
}());
