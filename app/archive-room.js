(function () {
    'use strict';

    const state = {
        projects: [],
        selectedId: '',
        detail: null,
        detailLoading: false,
        selectedArtifact: null,
        selectedText: '',
        artifactBrowserOpen: false,
        artifactView: 'source',
        archiveManager: null,
        managerBusy: false,
        managerNotice: null,
        managerActivityOpen: false,
        governanceBusy: false,
        governanceDialog: null,
        schedulePanelOpen: false,
        listFilter: 'all',
        listSort: 'priority',
        error: '',
    };

    function escHtml(value) {
        return String(value == null ? '' : value)
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;')
            .replace(/'/g, '&#39;');
    }

    function tr(key, fallback, params) {
        if (window.i18n && typeof window.i18n.t === 'function') {
            const translated = window.i18n.t(key, params);
            if (translated && translated !== key) return translated;
        }
        let msg = fallback;
        if (params) {
            Object.keys(params).forEach(k => {
                msg = String(msg).replace(new RegExp('\\{\\{' + k + '\\}\\}', 'g'), params[k]);
            });
        }
        return msg;
    }

    function trCount(key, fallback, count) {
        return tr(key, fallback, { count });
    }

    function noneText() {
        return tr('archive_room_none', 'None');
    }

    function noRecordText() {
        return tr('archive_room_no_record', 'No record');
    }

    function formatDate(value) {
        if (!value) return tr('unknown', 'Unknown');
        const d = new Date(value);
        if (isNaN(d.getTime())) return String(value);
        return d.toLocaleString();
    }

    function formatBytes(bytes) {
        bytes = Number(bytes || 0);
        if (!bytes) return '0 B';
        const units = ['B', 'KB', 'MB', 'GB'];
        let idx = 0;
        while (bytes >= 1024 && idx < units.length - 1) {
            bytes = bytes / 1024;
            idx += 1;
        }
        return `${bytes.toFixed(idx ? 1 : 0)} ${units[idx]}`;
    }

    function modal() { return document.getElementById('archiveRoomModal'); }
    function content() { return document.getElementById('archive-room-content'); }

    function captureScrollState() {
        const detail = document.querySelector('.archive-room-detail');
        const list = document.querySelector('.archive-room-list');
        const activity = document.querySelector('.archive-manager-activity');
        return {
            detailTop: detail ? detail.scrollTop : 0,
            listTop: list ? list.scrollTop : 0,
            activityTop: activity ? activity.scrollTop : 0,
        };
    }

    function restoreScrollState(scrollState) {
        if (!scrollState) return;
        requestAnimationFrame(() => {
            const detail = document.querySelector('.archive-room-detail');
            const list = document.querySelector('.archive-room-list');
            const activity = document.querySelector('.archive-manager-activity');
            if (detail) detail.scrollTop = scrollState.detailTop || 0;
            if (list) list.scrollTop = scrollState.listTop || 0;
            if (activity) activity.scrollTop = scrollState.activityTop || 0;
        });
    }

    async function fetchJson(url) {
        const r = await fetch(url);
        const d = await parseJsonResponse(r);
        if (!r.ok || d.error) throw new Error(d.error || r.statusText);
        return d;
    }

    async function postJson(url, body) {
        const r = await fetch(url, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(body || {}),
        });
        const d = await parseJsonResponse(r);
        if (!r.ok || d.error) throw new Error(d.error || r.statusText);
        return d;
    }

    async function parseJsonResponse(response) {
        const text = await response.text();
        if (!text.trim()) {
            throw new Error(tr('archive_room_empty_response_error', 'Service returned an empty response. Confirm the system is running and refresh the page. HTTP {{status}}', { status: response.status || 0 }));
        }
        try {
            return JSON.parse(text);
        } catch (e) {
            throw new Error(tr('archive_room_parse_response_error', 'Service returned data that could not be parsed. Refresh and try again. HTTP {{status}}', { status: response.status || 0 }));
        }
    }

    window.openArchiveRoom = function () {
        const m = modal();
        if (!m) return;
        m.classList.remove('hidden');
        loadOverview();
    };

    window.openArchiveRoomProject = function (projectId) {
        const m = modal();
        if (!m) return;
        state.selectedId = projectId || state.selectedId;
        m.classList.remove('hidden');
        loadOverview().then(() => {
            if (projectId) return loadProject(projectId);
        }).catch(() => {});
    };

    window.closeArchiveRoom = function () {
        const m = modal();
        if (m) m.classList.add('hidden');
    };

    async function loadOverview() {
        const el = content();
        if (!el) return;
        el.innerHTML = `<div class="archive-room-loading">${escHtml(tr('archive_room_loading', 'Loading archive room...'))}</div>`;
        try {
            const d = await fetchJson('/api/archive-room');
            state.projects = d.projects || [];
            state.archiveManager = d.archiveManager || null;
            const mgr = document.getElementById('archive-room-manager');
            if (mgr) mgr.textContent = managerHeaderText(state.archiveManager);
            if (!state.selectedId && state.projects[0]) state.selectedId = state.projects[0].id;
            render();
            if (state.selectedId) loadProject(state.selectedId);
        } catch (e) {
            el.innerHTML = `<div class="archive-room-error">${escHtml(tr('archive_room_load_failed', 'Failed to load archive room'))}: ${escHtml(e.message || e)}</div>`;
        }
    }

    async function loadProject(id) {
        if (id === state.selectedId && state.detail && state.detail.projectId === id) return;
        state.selectedId = id;
        state.error = '';
        state.detailLoading = true;
        state.selectedArtifact = null;
        state.selectedText = '';
        updateListActiveProject();
        renderDetailOnly();
        try {
            const d = await fetchJson(`/api/archive-room/projects/${encodeURIComponent(id)}`);
            state.detail = d.project || null;
            if (state.detail && state.detail.archiveManager) state.archiveManager = state.detail.archiveManager;
            state.detailLoading = false;
            renderDetailOnly();
        } catch (e) {
            state.error = e.message || String(e);
            state.detailLoading = false;
            renderDetailOnly();
        }
    }

    window.ArchiveRoom = {
        openProject: loadProject,
        openProjectArtifacts,
        closeProjectArtifacts,
        openArtifact,
        setArtifactView,
        closeArtifact,
        copyOnboarding,
        setManagerPaused,
        auditArchiveCount,
        openManagerActivity,
        closeManagerActivity,
        setProjectMaintenance,
        setProjectMaintenanceSchedule,
        toggleSchedulePanel,
        maintainCurrentProject,
        refineCurrentProjectWithAi,
        handleGovernance,
        submitGovernanceDialog,
        closeGovernanceDialog,
        setListFilter,
        setListSort,
        refresh: loadOverview,
    };

    function render() {
        const el = content();
        if (!el) return;
        if (!state.projects.length) {
            el.innerHTML = `<div class="archive-room-empty">${escHtml(tr('archive_room_empty_overview', 'No project archives yet. Create a project and the archive room will show the project overview.'))}</div>`;
            return;
        }
        el.innerHTML = `
            ${renderManagerBar()}
            <div class="archive-room-layout">
                ${renderList()}
                ${renderDetail()}
            </div>
            <div id="archive-manager-activity-host"></div>
            ${renderGovernanceDialog()}`;
    }

    function renderDetailOnly() {
        const detail = document.querySelector('.archive-room-detail');
        if (!detail) {
            render();
            return;
        }
        detail.outerHTML = renderDetail();
    }

    function renderGovernanceDialog() {
        const dialog = state.governanceDialog;
        if (!dialog) return '';
        const isEdit = dialog.action === 'edit_confirm';
        const isConfirm = dialog.action === 'confirm';
        const isReject = dialog.action === 'reject';
        const isDefer = dialog.action === 'defer';
        const tone = isReject ? 'danger' : (isDefer ? 'muted' : 'primary');
        return `
            <div class="archive-governance-dialog-backdrop" role="presentation">
                <section class="archive-governance-dialog ${tone}" role="dialog" aria-modal="true" aria-labelledby="archive-governance-dialog-title">
                    <div class="archive-governance-dialog-head">
                        <div>
                            <div id="archive-governance-dialog-title" class="archive-governance-dialog-title">${escHtml(dialog.title)}</div>
                            <div class="archive-governance-dialog-subtitle">${escHtml(dialog.itemTitle)}</div>
                        </div>
                        <button class="archive-icon-btn" ${state.governanceBusy ? 'disabled' : ''} onclick="ArchiveRoom.closeGovernanceDialog()" aria-label="${escHtml(tr('archive_artifact_close', 'Close'))}">×</button>
                    </div>
                    <div class="archive-governance-dialog-body">
                        ${dialog.error ? `<div class="archive-governance-dialog-error">${escHtml(dialog.error)}</div>` : ''}
                        ${isEdit ? `
                            <label class="archive-governance-field">
                                <span>${escHtml(tr('archive_governance_confirm_content', 'Content to confirm'))}</span>
                                <textarea id="archive-governance-dialog-text" rows="7">${escHtml(dialog.text || '')}</textarea>
                            </label>` : `
                            <div class="archive-governance-review">
                                <span>${escHtml(isConfirm ? tr('archive_governance_confirm_hint', 'After confirmation, this content will be saved as a human-confirmed archive entry.') : (isReject ? tr('archive_governance_reject_hint', 'After rejection, this suggestion will not be used as valid archive context.') : tr('archive_governance_defer_hint', 'After deferring, this suggestion will remain in governance history for later handling.')))}</span>
                                <p>${escHtml(dialog.text || '')}</p>
                            </div>`}
                        ${(isReject || isDefer) ? `
                            <label class="archive-governance-field">
                                <span>${escHtml(isReject ? tr('archive_governance_reject_reason_optional', 'Rejection reason (optional)') : tr('archive_governance_defer_reason_optional', 'Deferral reason (optional)'))}</span>
                                <textarea id="archive-governance-dialog-reason" rows="3">${escHtml(dialog.reason || '')}</textarea>
                            </label>` : ''}
                    </div>
                    <div class="archive-governance-dialog-actions">
                        <button class="archive-secondary-btn" ${state.governanceBusy ? 'disabled' : ''} onclick="ArchiveRoom.closeGovernanceDialog()">${escHtml(tr('cancel', 'Cancel'))}</button>
                        <button class="${isReject ? 'archive-secondary-btn danger' : 'archive-primary-btn'}" ${state.governanceBusy ? 'disabled' : ''} onclick="ArchiveRoom.submitGovernanceDialog()">${escHtml(state.governanceBusy ? tr('archive_processing', 'Processing...') : (isEdit ? tr('archive_governance_confirm_archive', 'Confirm into archive') : dialog.title))}</button>
                    </div>
                </section>
            </div>`;
    }

    function managerHeaderText(mgr) {
        const name = tr('archive_manager_default_name', 'Archive Manager');
        const unavailable = tr('archive_manager_not_connected', 'Not connected');
        if (!mgr) return `🗄️ ${name}: ${unavailable}`;
        return `${mgr.emoji || '🗄️'} ${mgr.name || name}: ${mgr.label || mgr.status || unavailable}`;
    }

    function managerStatusClass(mgr) {
        const status = (mgr && mgr.status) || 'missing';
        if (status === 'error') return 'error';
        if (status === 'paused') return 'paused';
        if (status === 'working') return 'working';
        return 'ready';
    }

    function renderManagerBar() {
        const mgr = state.archiveManager || {};
        const activity = (mgr.recentActivity || []).slice().reverse();
        const paused = !!mgr.paused;
        const error = mgr.lastError || '';
        const autoCreated = tr('archive_manager_auto_created', 'Auto-created');
        const created = mgr.autoCreated && mgr.createdAt ? `${autoCreated} · ${formatDate(mgr.createdAt)}` : (mgr.autoCreated ? autoCreated : tr('archive_manager_global', 'Global archive manager'));
        return `
            <div class="archive-manager-panel ${managerStatusClass(mgr)}">
                <div class="archive-manager-main">
                    <div class="archive-manager-avatar">${escHtml(mgr.emoji || '🗄️')}</div>
                    <div class="archive-manager-copy">
                        <div class="archive-manager-title">${escHtml(mgr.name || tr('archive_manager_default_name', 'Archive Manager'))}</div>
                        <div class="archive-manager-meta">${escHtml(mgr.label || tr('archive_manager_not_connected', 'Not connected'))} · ${escHtml(created)}</div>
                        ${error ? `<div class="archive-manager-error">${escHtml(error)}</div>` : ''}
                    </div>
                </div>
                <div class="archive-manager-actions">
                    <button class="archive-secondary-btn" ${state.managerBusy ? 'disabled' : ''} onclick="ArchiveRoom.auditArchiveCount()">${escHtml(state.managerBusy ? tr('archive_manager_checking', 'Checking...') : tr('archive_manager_check_count', 'Check archive count'))}</button>
                    <button class="archive-secondary-btn" onclick="ArchiveRoom.openManagerActivity()">${escHtml(tr('archive_manager_view_activity', 'View activity'))}${activity.length ? ` (${activity.length})` : ''}</button>
                    <button class="archive-secondary-btn" ${state.managerBusy ? 'disabled' : ''} onclick="ArchiveRoom.refresh()">${escHtml(tr('refresh', 'Refresh'))}</button>
                    ${paused
                        ? `<button class="archive-primary-btn" ${state.managerBusy ? 'disabled' : ''} onclick="ArchiveRoom.setManagerPaused(false)">${escHtml(tr('archive_manager_resume', 'Resume'))}</button>`
                        : `<button class="archive-secondary-btn" ${state.managerBusy ? 'disabled' : ''} onclick="ArchiveRoom.setManagerPaused(true)">${escHtml(tr('archive_manager_pause', 'Pause'))}</button>`}
                </div>
            </div>`;
    }

    function renderManagerActivityDialog() {
        if (!state.managerActivityOpen) return '';
        const mgr = state.archiveManager || {};
        const activity = (mgr.recentActivity || []).slice().reverse();
        return `<div class="archive-manager-activity-backdrop" role="presentation">
            <section class="archive-manager-activity-dialog" role="dialog" aria-modal="true" aria-labelledby="archive-manager-activity-title">
                <div class="archive-manager-activity-head">
                    <div>
                        <div id="archive-manager-activity-title" class="archive-manager-activity-title">${escHtml(tr('archive_manager_activity_title', 'Archive manager activity'))}</div>
                        <div class="archive-manager-activity-subtitle">${escHtml(tr('archive_manager_activity_subtitle', 'Global activity log, not limited to the current archive.'))}</div>
                    </div>
                    <button class="archive-icon-btn" onclick="ArchiveRoom.closeManagerActivity()" aria-label="${escHtml(tr('archive_artifact_close', 'Close'))}">×</button>
                </div>
                <div class="archive-manager-activity-list">
                    ${activity.length ? activity.map(renderManagerActivity).join('') : `<div class="archive-manager-activity-empty">${escHtml(tr('archive_manager_no_activity', 'No maintenance activity yet'))}</div>`}
                </div>
            </section>
        </div>`;
    }

    function renderManagerActivity(item) {
        const status = item.status || 'ok';
        const text = item.message || item.action || '';
        const err = item.error ? ` · ${item.error}` : '';
        return `<div class="archive-manager-activity-item ${escHtml(status)}">
            <span>${escHtml(status)}</span>
            <strong>${escHtml(text)}</strong>
            <em>${escHtml(formatDate(item.at))}${escHtml(err)}</em>
        </div>`;
    }

    function openManagerActivity() {
        state.managerActivityOpen = true;
        renderManagerActivityDialogOnly();
    }

    function closeManagerActivity() {
        state.managerActivityOpen = false;
        renderManagerActivityDialogOnly();
    }

    function renderManagerActivityDialogOnly() {
        let host = document.getElementById('archive-manager-activity-host');
        if (!host) {
            host = document.createElement('div');
            host.id = 'archive-manager-activity-host';
            const el = content();
            if (el) el.appendChild(host);
        }
        host.innerHTML = renderManagerActivityDialog();
    }

    async function setManagerPaused(paused) {
        if (state.managerBusy) return;
        state.managerBusy = true;
        render();
        try {
            const d = await postJson('/api/archive-room/manager', { action: paused ? 'pause' : 'resume' });
            state.archiveManager = d.archiveManager || state.archiveManager;
            if (state.detail) state.detail.archiveManager = state.archiveManager;
        } catch (e) {
            state.error = e.message || String(e);
        } finally {
            state.managerBusy = false;
            render();
        }
    }

    async function auditArchiveCount() {
        if (state.managerBusy) return;
        state.managerBusy = true;
        render();
        try {
            const d = await postJson('/api/archive-room/audit-count', {});
            state.archiveManager = d.archiveManager || state.archiveManager;
            state.projects = d.projects || state.projects;
            if (state.selectedId) {
                state.detail = null;
                await loadProject(state.selectedId);
            } else {
                render();
            }
        } catch (e) {
            state.error = e.message || String(e);
            render();
        } finally {
            state.managerBusy = false;
            render();
        }
    }

    function renderList() {
        const projects = filteredProjects();
        return `
            <div class="archive-room-list">
                <div class="archive-room-list-head">
                    <div class="archive-room-title">${escHtml(tr('archive_project_watchlist', 'Project watchlist'))}</div>
                    <div class="archive-room-count">${escHtml(tr('archive_project_count', '{{shown}} / {{total}} projects', { shown: projects.length, total: state.projects.length }))}</div>
                </div>
                <div class="archive-list-controls">
                    <div class="archive-filter-group">
                        ${listFilterButton('all', tr('archive_filter_all', 'All'))}
                        ${listFilterButton('pending', tr('archive_filter_pending', 'Pending'))}
                        ${listFilterButton('risk', tr('archive_filter_risk', 'Risk'))}
                    </div>
                    <div class="archive-sort-group" aria-label="${escHtml(tr('archive_project_sort', 'Project sort'))}">
                        <span>${escHtml(tr('archive_sort', 'Sort'))}</span>
                        ${listSortButton('priority', tr('archive_sort_priority', 'Priority'))}
                        ${listSortButton('recent', tr('archive_sort_recent', 'Recent'))}
                    </div>
                </div>
                ${projects.map(renderProjectCard).join('') || `<div class="archive-room-empty compact">${escHtml(tr('archive_no_matching_projects', 'No matching projects.'))}</div>`}
            </div>`;
    }

    function filteredProjects() {
        let items = (state.projects || []).slice();
        if (state.listFilter === 'pending') {
            items = items.filter(p => Number((p.metrics || {}).pendingConfirmationCount || p.pendingConfirmationCount || 0) > 0);
        } else if (state.listFilter === 'risk') {
            items = items.filter(p => Number((p.metrics || {}).riskCount || 0) > 0);
        }
        if (state.listSort === 'recent') {
            items.sort((a, b) => String(b.archiveUpdatedAt || b.updatedAt || '').localeCompare(String(a.archiveUpdatedAt || a.updatedAt || '')));
        }
        return items;
    }

    function listFilterButton(value, label) {
        const active = state.listFilter === value ? 'active' : '';
        return `<button class="archive-filter-btn ${active}" onclick="ArchiveRoom.setListFilter('${escHtml(value)}')">${escHtml(label)}</button>`;
    }

    function listSortButton(value, label) {
        const active = state.listSort === value ? 'active' : '';
        return `<button class="archive-filter-btn ${active}" onclick="ArchiveRoom.setListSort('${escHtml(value)}')">${escHtml(label)}</button>`;
    }

    function setListFilter(value) {
        state.listFilter = ['all', 'pending', 'risk'].includes(value) ? value : 'all';
        render();
    }

    function setListSort(value) {
        state.listSort = value === 'recent' ? 'recent' : 'priority';
        render();
    }

    function renderProjectCard(p) {
        const m = p.metrics || {};
        const active = p.id === state.selectedId ? 'active' : '';
        return `
            <button class="archive-project-card ${active}" data-project-id="${escHtml(p.id)}" onclick="ArchiveRoom.openProject('${escHtml(p.id)}')">
                <div class="archive-project-name">${escHtml(p.title || tr('archive_untitled_project', 'Untitled project'))}</div>
                <div class="archive-project-desc">${escHtml(p.description || tr('archive_no_project_description', 'No project description.'))}</div>
                <div class="archive-metrics">
                    <div class="archive-metric"><strong>${escHtml(m.riskCount || 0)}</strong><span>${escHtml(tr('archive_metric_risk', 'Risk'))}</span></div>
                    <div class="archive-metric"><strong>${escHtml(m.pendingConfirmationCount || 0)}</strong><span>${escHtml(tr('archive_metric_pending', 'Pending'))}</span></div>
                    <div class="archive-metric"><strong>${escHtml(m.completionRate || 0)}%</strong><span>${escHtml(tr('archive_metric_done', 'Done'))}</span></div>
                    <div class="archive-metric"><strong>${escHtml(m.artifactCount || 0)}</strong><span>${escHtml(tr('archive_metric_artifacts', 'Artifacts'))}</span></div>
                </div>
                <div class="archive-artifact-meta">${escHtml(tr('archive_updated_at', 'Updated at {{date}}', { date: formatDate(p.updatedAt) }))}</div>
            </button>`;
    }

    function updateListActiveProject() {
        document.querySelectorAll('.archive-project-card').forEach(card => {
            card.classList.toggle('active', card.getAttribute('data-project-id') === state.selectedId);
        });
    }

    function renderDetail() {
        if (state.error) {
            return `<div class="archive-room-detail"><div class="archive-room-error">${escHtml(state.error)}</div></div>`;
        }
        if (!state.detail) {
            return `<div class="archive-room-detail"><div class="archive-room-loading">${escHtml(tr('archive_project_loading', 'Loading project archive...'))}</div></div>`;
        }
        const p = state.detail;
        const m = p.metrics || {};
        const s = p.summary || {};
        const manager = state.archiveManager || p.archiveManager || {};
        const maintenance = p.archiveMaintenance || {};
        return `
            <div class="archive-room-detail">
                ${state.detailLoading ? `<div class="archive-detail-loading-mask">${escHtml(tr('archive_project_loading', 'Loading project archive...'))}</div>` : ''}
                <div class="archive-detail-head">
                    <div>
                        <h2 class="archive-detail-title">${escHtml(p.title || tr('archive_untitled_project', 'Untitled project'))}</h2>
                        <div class="archive-detail-subtitle">${escHtml(tr('archive_detail_updated_at', 'Archive updated at {{date}}', { date: formatDate(p.archiveUpdatedAt) }))}</div>
                    </div>
                    <div class="archive-detail-actions">
                        <div class="archive-status-pill">${escHtml(manager.label || tr('archive_manager_not_connected', 'Not connected'))}</div>
                        <button class="archive-primary-btn" ${state.managerBusy ? 'disabled' : ''} onclick="ArchiveRoom.maintainCurrentProject()">${escHtml(state.managerBusy ? tr('archive_refreshing', 'Refreshing...') : tr('archive_refresh_current', 'Refresh current archive'))}</button>
                        <button class="archive-secondary-btn" ${state.managerBusy ? 'disabled' : ''} onclick="ArchiveRoom.refineCurrentProjectWithAi()">${escHtml(state.managerBusy ? tr('archive_processing', 'Processing...') : tr('archive_ai_refine', 'AI refine archive'))}</button>
                    </div>
                </div>
                ${manager.paused ? `<div class="archive-paused-notice">${escHtml(tr('archive_manager_paused_notice', 'The archive manager is paused. Archives will not update automatically, but you can still maintain the current project manually.'))}</div>` : ''}
                ${renderArchiveIntro(p)}
                ${renderProjectBasicInfo(p)}
                ${renderMaintenanceControl(p, maintenance)}
                ${renderGovernanceSection(p)}
                <section class="archive-section">
                    <h3>${escHtml(tr('archive_key_summary', 'Key summary'))}</h3>
                    <div class="archive-section-body archive-summary-grid">
                        ${summaryItem(tr('archive_goal', 'Goal'), s.goal || p.description || tr('archive_no_goal', 'No goal recorded.'))}
                        ${summaryItem(tr('archive_current_state', 'Current state'), s.currentState || tr('archive_task_progress_done', '{{done}} / {{total}} tasks complete', { done: m.taskDone || 0, total: m.taskCount || 0 }))}
                        ${summaryItem(tr('archive_next_step', 'Next step'), s.nextStep || tr('archive_no_next_step', 'No next step recorded.'))}
                    </div>
                </section>
                <section class="archive-section">
                    <h3>${escHtml(tr('archive_context_catalog', 'Context catalog'))}</h3>
                    <div class="archive-section-body">
                        ${(p.entries || []).map(renderEntry).join('') || `<div class="archive-room-empty">${escHtml(tr('archive_no_entries', 'No archive entries yet.'))}</div>`}
                    </div>
                </section>
                <section class="archive-section">
                    <h3>${escHtml(tr('archive_onboarding_package', 'AI onboarding package'))}</h3>
                    <div class="archive-section-body">
                        <textarea id="archive-onboarding-text" class="archive-onboarding" readonly>${escHtml((p.onboardingPackage || {}).copyText || '')}</textarea>
                        <button class="archive-copy-btn" onclick="ArchiveRoom.copyOnboarding()">${escHtml(tr('archive_copy_onboarding', 'Copy AI onboarding package'))}</button>
                    </div>
                </section>
                <section class="archive-section">
                    <h3>${escHtml(tr('archive_task_artifacts', 'Task artifacts'))}</h3>
                    <div class="archive-section-body">
                        ${renderArtifactLauncher(p)}
                    </div>
                </section>
                ${renderMaintenanceHistory(p)}
            </div>`;
    }

    function renderArchiveIntro(p) {
        const intro = p.archiveIntroduction || {};
        const readiness = intro.readiness || {};
        const contains = intro.currentlyContains || [];
        const missing = intro.missingOrSparse || [];
        const artifactCount = (p.artifacts || []).length || Number((p.metrics || {}).artifactCount || 0);
        return `<section class="archive-hero">
            <div class="archive-hero-main">
                <div class="archive-hero-eyebrow">${escHtml(tr('archive_project_archive', 'Project archive'))}</div>
                <h3>${escHtml(intro.title || tr('archive_project_archive_title', '{{name}} project archive', { name: p.title || tr('project', 'Project') }))}</h3>
                <p class="archive-hero-brief">${escHtml(intro.brief || p.description || tr('archive_no_project_intro', 'No project introduction.'))}</p>
                <div class="archive-hero-actions">
                    <span>${escHtml(readiness.label || tr('archive_available', 'Available'))}</span>
                    <span>${escHtml(readiness.summary || '')}</span>
                    <button class="archive-hero-artifact-btn" ${artifactCount ? '' : 'disabled'} onclick="ArchiveRoom.openProjectArtifacts()">${escHtml(tr('archive_view_project_artifacts', 'View project artifacts'))}</button>
                </div>
            </div>
            <div class="archive-hero-side">
                <div class="archive-hero-side-title">${escHtml(tr('archive_contains_title', 'What this archive contains'))}</div>
                <div class="archive-mini-tags">${contains.slice(0, 8).map(x => `<span>${escHtml(x)}</span>`).join('') || `<span>${escHtml(noRecordText())}</span>`}</div>
                <div class="archive-hero-side-title muted">${escHtml(tr('archive_missing_title', 'To supplement'))}</div>
                <div class="archive-mini-tags muted">${missing.slice(0, 6).map(x => `<span>${escHtml(x)}</span>`).join('') || `<span>${escHtml(noneText())}</span>`}</div>
            </div>
        </section>
        <section class="archive-section">
            <h3>${escHtml(tr('archive_index', 'Archive index'))}</h3>
            <div class="archive-section-body">
                ${renderArchiveIndex(p)}
            </div>
        </section>`;
    }

    function renderArchiveIndex(p) {
        const index = p.archiveIndexHighlights || {};
        const attention = index.attention || [];
        const sections = index.sections || [];
        return `<div class="archive-index">
            <div class="archive-index-attention">
                ${attention.map(item => `<div class="archive-index-signal ${escHtml(item.level || '')}">
                    <strong>${escHtml(item.label || '')}</strong>
                    <span>${escHtml(item.text || '')}</span>
                </div>`).join('') || `<div class="archive-room-empty">${escHtml(tr('archive_no_priority_info', 'No archive information needs priority attention.'))}</div>`}
            </div>
            <div class="archive-index-grid">
                ${sections.map(renderArchiveIndexSection).join('')}
            </div>
            <div class="archive-index-footer">${escHtml(index.footer || tr('archive_index_footer', 'The index is derived live from the current project archive.'))}</div>
        </div>`;
    }

    function renderArchiveIndexSection(section) {
        const items = section.items || [];
        return `<div class="archive-index-section">
            <div class="archive-index-section-title">${escHtml(section.label || '')}</div>
            <div class="archive-index-items">
                ${items.map(renderArchiveIndexItem).join('') || `<div class="archive-index-empty">${escHtml(section.emptyText || noRecordText())}</div>`}
            </div>
        </div>`;
    }

    function renderArchiveIndexItem(item) {
        const meta = [item.kind, item.confidence, item.status, item.assignee].filter(Boolean).join(' · ');
        return `<div class="archive-index-item">
            <strong>${escHtml(item.title || item.path || tr('archive_untitled', 'Untitled'))}</strong>
            ${item.summary ? `<span>${escHtml(item.summary)}</span>` : ''}
            ${meta ? `<em>${escHtml(meta)}</em>` : ''}
        </div>`;
    }

    function renderArchiveMapItems(items, title) {
        return `<div class="archive-map-panel">
            <div class="archive-map-title">${escHtml(title)}</div>
            <div class="archive-map-items">
                ${(items || []).map(item => `<div class="archive-map-item ${item.present === false || item.available === false ? 'missing' : 'present'}">
                    <strong>${escHtml(item.label || item.key || '')}</strong>
                    <span>${escHtml(item.summary || (item.present === false || item.available === false ? noRecordText() : tr('archive_available', 'Available')))}</span>
                </div>`).join('') || `<div class="archive-room-empty">${escHtml(tr('archive_no_info_map', 'No information map yet.'))}</div>`}
            </div>
        </div>`;
    }

    function renderProjectBasicInfo(p) {
        const info = p.projectBasicInfo || {};
        return `<section class="archive-section">
            <h3>${escHtml(tr('archive_project_basic_info', 'Project basic information'))}</h3>
            <div class="archive-section-body archive-basic-grid">
                ${summaryItem(tr('archive_project_name', 'Project name'), info.name || p.title || tr('archive_untitled_project', 'Untitled project'))}
                ${summaryItem(tr('archive_project_description', 'Project description'), info.description || tr('archive_not_recorded', 'Not recorded'))}
                ${summaryItem(tr('archive_project_status', 'Project status'), info.status || p.status || 'active')}
                ${summaryItem(tr('archive_task_progress', 'Task progress'), `${info.taskProgress || '0 / 0'} · ${escHtml(String(info.completionRate || 0))}%`)}
                ${summaryItem(tr('archive_long_term_maintenance', 'Long-term maintenance'), info.maintenanceLabel || tr('archive_not_recorded', 'Not recorded'))}
                ${summaryItem(tr('archive_active_participants', 'Active AI / participants'), info.participantsLabel || tr('archive_no_active_ai', 'No active AI'))}
                ${summaryItem(tr('archive_project_artifacts_label', 'Project artifacts'), trCount('archive_artifact_count', '{{count}} artifacts', info.artifactCount || 0))}
                ${summaryItem(tr('archive_pending_label', 'Pending'), trCount('archive_pending_count', '{{count}} pending', info.pendingConfirmationCount || 0))}
                ${summaryItem(tr('archive_primary_sources', 'Primary sources'), info.sourceTypesLabel || tr('archive_no_source_record', 'No source record'))}
            </div>
        </section>`;
    }

    function renderMaintenanceControl(p, maintenance) {
        const enabled = maintenance.enabled !== false;
        const inspections = p.inspections || {};
        const lastInspection = inspections.lastDailyInspectionAt || inspections.lastStartupInspectionAt || '';
        const notices = (p.automaticGovernanceNotices || []).slice().reverse().slice(0, 5);
        return `<section class="archive-maintenance-control ${enabled ? 'enabled' : 'disabled'}">
            <div>
                <div class="archive-maintenance-title">${escHtml(enabled ? tr('archive_maintenance_enabled', 'Long-term maintenance enabled') : tr('archive_maintenance_disabled', 'Long-term maintenance disabled'))}</div>
                <div class="archive-maintenance-copy">${enabled
                    ? escHtml(tr('archive_maintenance_enabled_desc', 'Startup and scheduled inspections will maintain this project; high-value events are archived automatically.'))
                    : escHtml(tr('archive_maintenance_disabled_desc', 'Scheduled inspections and low-value events are skipped; high-value events are still archived.'))}</div>
                <div class="archive-maintenance-copy">${escHtml(tr('archive_maintenance_default_recent', 'Default: {{state}} · Recent inspection: {{date}}', { state: maintenance.defaultEnabled ? tr('archive_default_enabled', 'enabled for current status') : tr('archive_default_disabled', 'disabled for current status'), date: lastInspection ? formatDate(lastInspection) : noneText() }))}</div>
                <div class="archive-maintenance-schedule ${enabled ? '' : 'disabled'}">
                    <div class="archive-maintenance-schedule-main">
                        <strong>${escHtml(maintenance.frequencyLabel || tr('archive_schedule_daily_label', 'Event-triggered + daily inspection'))}</strong>
                        <span>${escHtml(tr('archive_schedule_times', 'Next: {{next}} · Last scheduled: {{last}} · Last event: {{event}}', { next: maintenance.nextScheduledAt ? formatDate(maintenance.nextScheduledAt) : noneText(), last: maintenance.lastScheduledAt ? formatDate(maintenance.lastScheduledAt) : noneText(), event: maintenance.lastEventTriggeredAt ? formatDate(maintenance.lastEventTriggeredAt) : noneText() }))}</span>
                        ${maintenance.lastSkippedReason ? `<em>${escHtml(tr('archive_recently_skipped', 'Recently skipped: {{reason}}', { reason: maintenance.lastSkippedReason }))}${maintenance.lastSkippedAt ? ` · ${escHtml(formatDate(maintenance.lastSkippedAt))}` : ''}</em>` : ''}
                    </div>
                    <button type="button" class="archive-secondary-btn" ${state.managerBusy || !enabled ? 'disabled' : ''} onclick="ArchiveRoom.toggleSchedulePanel()">${escHtml(state.schedulePanelOpen ? tr('archive_collapse_adjustment', 'Collapse adjustment') : tr('archive_adjust_frequency', 'Adjust frequency'))}</button>
                </div>
                ${state.schedulePanelOpen ? renderSchedulePanel(p, maintenance, enabled) : ''}
                ${notices.length ? `<div class="archive-auto-governance">
                    <div class="archive-auto-governance-title">${escHtml(tr('archive_auto_governance', 'Manager auto-governance'))}</div>
                    ${notices.map(renderAutoGovernanceNotice).join('')}
                </div>` : ''}
            </div>
            <button type="button" class="archive-maintenance-toggle ${enabled ? 'archive-secondary-btn' : 'archive-primary-btn'}" ${state.managerBusy ? 'disabled' : ''} onclick="ArchiveRoom.setProjectMaintenance('${escHtml(p.projectId)}', ${enabled ? 'false' : 'true'})">${escHtml(enabled ? tr('archive_disable_maintenance', 'Disable long-term maintenance') : tr('archive_enable_maintenance', 'Enable long-term maintenance'))}</button>
        </section>`;
    }

    function renderSchedulePanel(p, maintenance, enabled) {
        const mode = maintenance.scheduleMode || maintenance.frequency || 'daily';
        const options = [
            ['event_only', tr('archive_schedule_event_only_label', 'Event-triggered only'), tr('archive_schedule_event_only_desc', 'Maintain only when tasks, meetings, important messages, or other events occur.')],
            ['daily', tr('archive_schedule_daily_label', 'Event-triggered + daily inspection'), tr('archive_schedule_daily_desc', 'Default strategy, with one daily catch-up inspection.')],
            ['weekly', tr('archive_schedule_weekly_label', 'Event-triggered + weekly inspection'), tr('archive_schedule_weekly_desc', 'Lighter strategy for projects that change less often.')],
        ];
        return `<div class="archive-schedule-panel ${enabled ? '' : 'disabled'}">
            ${options.map(([value, label, desc]) => `<button type="button" class="archive-schedule-option ${mode === value ? 'active' : ''}" ${state.managerBusy || !enabled ? 'disabled' : ''} onclick="ArchiveRoom.setProjectMaintenanceSchedule('${escHtml(p.projectId)}', '${escHtml(value)}')">
                <strong>${escHtml(label)}</strong>
                <span>${escHtml(desc)}</span>
            </button>`).join('')}
        </div>`;
    }

    function renderAutoGovernanceNotice(item) {
        const cmp = item.sourceComparison || {};
        return `<div class="archive-auto-governance-item">
            <strong>${escHtml(item.title || item.action || tr('archive_auto_governance_item', 'Auto-governance'))}</strong>
            <span>${escHtml(item.summary || '')}</span>
            ${cmp.managerJudgment ? `<em>${escHtml(cmp.managerJudgment)}</em>` : ''}
            ${(cmp.oldSourceLabel || cmp.newSourceLabel) ? `<small>${escHtml(tr('archive_old_source', 'Old'))}: ${escHtml(cmp.oldSourceLabel || noneText())} · ${escHtml(tr('archive_new_source', 'New'))}: ${escHtml(cmp.newSourceLabel || noneText())}</small>` : ''}
        </div>`;
    }

    function renderMaintenanceHistory(p) {
        const history = (p.managerMaintenance || []).slice().reverse().slice(0, 8);
        if (!history.length) return '';
        return `<section class="archive-section">
            <h3>${escHtml(tr('archive_maintenance_history', 'Archive maintenance history'))}</h3>
            <div class="archive-section-body archive-maintenance-list">
                ${history.map(item => `<div class="archive-maintenance-item">
                    <div><strong>${escHtml(item.status || 'ok')}</strong><span>${escHtml(formatDate(item.at))}</span></div>
                    <p>${escHtml(item.summary || (item.output && item.output.summary) || '')}</p>
                </div>`).join('')}
            </div>
        </section>`;
    }

    async function maintainCurrentProject() {
        const detail = state.detail;
        if (!detail || !detail.projectId || state.managerBusy) return;
        const scrollState = captureScrollState();
        const startedAt = Date.now();
        state.managerBusy = true;
        state.managerNotice = {
            status: 'running',
            title: tr('archive_notice_refreshing_title', 'Archive manager is refreshing the current archive'),
            message: tr('archive_notice_refreshing_message', 'The archive manager is refreshing the archive from the current project, tasks, and artifact records.'),
        };
        renderDetailOnly();
        restoreScrollState(scrollState);
        try {
            const d = await postJson(`/api/archive-room/projects/${encodeURIComponent(detail.projectId)}/maintain`, {});
            const remaining = 400 - (Date.now() - startedAt);
            if (remaining > 0) await new Promise(resolve => setTimeout(resolve, remaining));
            state.detail = d.project || state.detail;
            state.archiveManager = d.archiveManager || state.archiveManager;
            if (state.detail && state.archiveManager) state.detail.archiveManager = state.archiveManager;
            state.projects = state.projects.map(p => p.id === detail.projectId ? { ...p, metrics: (state.detail || {}).metrics || p.metrics, archiveUpdatedAt: (state.detail || {}).archiveUpdatedAt || p.archiveUpdatedAt } : p);
            const latest = ((state.detail || {}).managerMaintenance || []).slice(-1)[0] || {};
            state.managerNotice = {
                status: latest.status === 'error' ? 'error' : 'ok',
                title: latest.status === 'error' ? tr('archive_notice_refresh_failed_title', 'Archive refresh failed') : tr('archive_notice_refresh_done_title', 'Archive refresh complete'),
                message: latest.summary || ((latest.output || {}).summary) || tr('archive_notice_refresh_done_message', 'The current project archive has been refreshed.'),
            };
        } catch (e) {
            state.managerNotice = {
                status: 'error',
                title: tr('archive_notice_refresh_failed_title', 'Archive refresh failed'),
                message: e.message || String(e),
            };
        } finally {
            state.managerBusy = false;
            renderDetailOnly();
            restoreScrollState(scrollState);
        }
    }

    async function refineCurrentProjectWithAi() {
        const detail = state.detail;
        if (!detail || !detail.projectId || state.managerBusy) return;
        const scrollState = captureScrollState();
        state.managerBusy = true;
        state.managerNotice = {
            status: 'running',
            title: tr('archive_notice_ai_refine_title', 'Archive manager AI refine requested'),
            message: tr('archive_notice_ai_refine_message', 'The archive manager is reading the project, tasks, artifacts, pending items, and existing archive, then returning stable JSON for archiving.'),
        };
        renderDetailOnly();
        restoreScrollState(scrollState);
        try {
            const d = await postJson(`/api/archive-room/projects/${encodeURIComponent(detail.projectId)}/ai-refine`, {});
            state.detail = d.project || state.detail;
            state.archiveManager = d.archiveManager || state.archiveManager;
            if (state.detail && state.archiveManager) state.detail.archiveManager = state.archiveManager;
            state.projects = state.projects.map(p => p.id === detail.projectId ? { ...p, metrics: (state.detail || {}).metrics || p.metrics, archiveUpdatedAt: (state.detail || {}).archiveUpdatedAt || p.archiveUpdatedAt } : p);
            const latest = d.maintenance || ((state.detail || {}).managerMaintenance || []).slice(-1)[0] || {};
            state.managerNotice = {
                status: latest.status === 'error' ? 'error' : 'ok',
                title: latest.status === 'error' ? tr('archive_notice_ai_refine_failed_title', 'AI refine failed') : tr('archive_notice_ai_refine_done_title', 'AI refine complete'),
                message: latest.summary || ((latest.output || {}).summary) || tr('archive_notice_ai_refine_done_message', 'Archive manager AI has refined and saved the archive.'),
            };
        } catch (e) {
            state.managerNotice = {
                status: 'error',
                title: tr('archive_notice_ai_refine_failed_title', 'AI refine failed'),
                message: e.message || String(e),
            };
        } finally {
            state.managerBusy = false;
            renderDetailOnly();
            restoreScrollState(scrollState);
        }
    }

    async function setProjectMaintenance(projectId, enabled) {
        if (!projectId || state.managerBusy) return;
        state.managerBusy = true;
        render();
        try {
            const d = await postJson(`/api/archive-room/projects/${encodeURIComponent(projectId)}/maintenance`, { enabled: !!enabled });
            if (state.detail && d.archive) {
                state.detail = d.archive;
                if (state.archiveManager) state.detail.archiveManager = state.archiveManager;
            }
            state.projects = state.projects.map(p => p.id === projectId ? { ...p, archiveMaintenance: d.maintenance || p.archiveMaintenance } : p);
        } catch (e) {
            state.error = e.message || String(e);
        } finally {
            state.managerBusy = false;
            render();
        }
    }

    function toggleSchedulePanel() {
        const scrollState = captureScrollState();
        state.schedulePanelOpen = !state.schedulePanelOpen;
        renderDetailOnly();
        restoreScrollState(scrollState);
    }

    async function setProjectMaintenanceSchedule(projectId, scheduleMode) {
        if (!projectId || state.managerBusy) return;
        const detail = state.detail;
        const scrollState = captureScrollState();
        state.managerBusy = true;
        render();
        restoreScrollState(scrollState);
        try {
            const d = await postJson(`/api/archive-room/projects/${encodeURIComponent(projectId)}/maintenance`, { scheduleMode });
            if (state.detail && d.archive) {
                state.detail = d.archive;
                if (state.archiveManager) state.detail.archiveManager = state.archiveManager;
            }
            state.projects = state.projects.map(p => p.id === projectId ? { ...p, archiveMaintenance: d.maintenance || p.archiveMaintenance } : p);
            if (detail && detail.projectId === projectId) state.schedulePanelOpen = true;
        } catch (e) {
            state.error = e.message || String(e);
        } finally {
            state.managerBusy = false;
            render();
            restoreScrollState(scrollState);
        }
    }

    function summaryItem(label, value) {
        return `<div class="archive-summary-item"><label>${escHtml(label)}</label>${escHtml(value)}</div>`;
    }

    function renderEntry(entry) {
        const authority = entry.authority || entry.status || entry.confidence || 'ai_inference';
        const tags = [
            authority,
            entry.confidence && entry.confidence !== authority ? entry.confidence : '',
            entry.stale ? 'stale' : '',
            ...(entry.sources || []).map(s => s.type || s.sourceType || 'source')
        ].filter(Boolean);
        return `
            <div class="archive-entry ${entry.stale ? 'stale' : ''}">
                <div class="archive-entry-title">${escHtml(entry.title || entry.id || 'Entry')}</div>
                <div class="archive-entry-text">${escHtml(entry.text || '')}</div>
                ${entry.staleReason ? `<div class="archive-entry-stale">${escHtml(tr('archive_stale_reason', 'Stale: {{reason}}', { reason: entry.staleReason }))}</div>` : ''}
                ${renderSourceComparison(entry.sourceComparison)}
                <div class="archive-tags">${tags.map(t => `<span class="archive-tag">${escHtml(t)}</span>`).join('')}</div>
            </div>`;
    }

    function renderSourceComparison(cmp) {
        if (!cmp || (!cmp.oldSourceLabel && !cmp.newSourceLabel && !cmp.managerJudgment)) return '';
        return `<div class="archive-source-comparison">
            <div><label>${escHtml(tr('archive_old_source', 'Old source'))}</label><span>${escHtml(cmp.oldSourceLabel || cmp.oldTitle || noneText())}</span></div>
            <div><label>${escHtml(tr('archive_new_source', 'New source'))}</label><span>${escHtml(cmp.newSourceLabel || cmp.newTitle || noneText())}</span></div>
            ${cmp.managerJudgment ? `<p>${escHtml(cmp.managerJudgment)}</p>` : ''}
        </div>`;
    }

    function authorityLabel(value) {
        const map = {
            human_confirmed: tr('archive_authority_human_confirmed', 'Human confirmed'),
            system_confirmed: tr('archive_authority_system_confirmed', 'System confirmed'),
            source_confirmed: tr('archive_authority_source_confirmed', 'Source confirmed'),
            archive_manager_confirmed: tr('archive_authority_manager_confirmed', 'Manager confirmed'),
            pending_human_confirmation: tr('archive_authority_pending_human', 'Pending human confirmation'),
            deferred: tr('archive_authority_deferred', 'Deferred'),
            rejected: tr('archive_authority_rejected', 'Rejected'),
            confirmed_fact: tr('archive_authority_confirmed_fact', 'Confirmed'),
            ai_inference: tr('archive_authority_ai_inference', 'AI organized'),
            pending_confirmation_suggestion: tr('archive_authority_pending_suggestion', 'Pending confirmation'),
        };
        return map[value] || value || tr('unknown', 'unknown');
    }

    function renderGovernanceSection(p) {
        const pending = p.pendingConfirmations || [];
        const history = (p.processedGovernance || []).slice().reverse().slice(0, 8);
        return `<section class="archive-section archive-governance-section">
            <h3>${escHtml(tr('archive_governance', 'Archive governance'))}</h3>
            <div class="archive-section-body">
                <div class="archive-governance-head">
                    <div>
                        <strong>${escHtml(tr('archive_pending_human_count', '{{count}} pending human confirmations', { count: pending.filter(x => (x.authority || x.status) !== 'deferred').length }))}</strong>
                        <span>${escHtml(tr('archive_governance_desc', 'Long-term rules, high-impact suggestions, and conflicts appear here; objective facts and low-risk manager organization will not interrupt the human queue.'))}</span>
                    </div>
                    <div class="archive-authority-legend">
                        <span>${escHtml(tr('archive_legend_system_source', 'System/source confirmed'))}</span><span>${escHtml(tr('archive_legend_manager', 'Manager confirmed'))}</span><span>${escHtml(tr('archive_legend_human', 'Human confirmed'))}</span>
                    </div>
                </div>
                <div class="archive-pending-list">
                    ${pending.map(renderPendingItem).join('') || `<div class="archive-room-empty compact">${escHtml(tr('archive_no_pending_governance', 'No pending governance items.'))}</div>`}
                </div>
                <div class="archive-history-block">
                    <div class="archive-history-title">${escHtml(tr('archive_processing_history', 'Processing history'))}</div>
                    ${history.map(renderGovernanceHistory).join('') || `<div class="archive-room-empty compact">${escHtml(tr('archive_no_processing_history', 'No processing history.'))}</div>`}
                </div>
            </div>
        </section>`;
    }

    function renderPendingItem(item) {
        const authority = item.authority || item.status || 'pending_human_confirmation';
        const deferred = authority === 'deferred' || item.status === 'deferred';
        const sources = (item.sources || []).map(s => s.title || s.id || s.type || s.sourceType).filter(Boolean).slice(0, 3).join(' · ');
        const conflict = item.conflictSummary || (item.conflict && tr('archive_conflict_with_confirmed', 'Conflicts with confirmed content'));
        const encodedId = encodeURIComponent(item.id || '');
        return `<div class="archive-pending-item ${deferred ? 'deferred' : ''} ${conflict ? 'conflict' : ''}">
            <div class="archive-pending-main">
                <div class="archive-pending-title-row">
                    <strong>${escHtml(item.title || tr('archive_pending_item', 'Pending item'))}</strong>
                    <span class="archive-authority-pill">${escHtml(authorityLabel(authority))}</span>
                    ${item.impact ? `<span class="archive-impact-pill">${escHtml(item.impact)}</span>` : ''}
                </div>
                ${conflict ? `<div class="archive-conflict-summary">${escHtml(conflict)}</div>` : ''}
                <p>${escHtml(item.text || '')}</p>
                <div class="archive-pending-meta">
                    ${item.reason ? `<span>${escHtml(tr('archive_reason_label', 'Reason'))}: ${escHtml(item.reason)}</span>` : ''}
                    ${sources ? `<span>${escHtml(tr('archive_source_label', 'Source'))}: ${escHtml(sources)}</span>` : `<span>${escHtml(tr('archive_source_unavailable', 'Source unavailable'))}</span>`}
                    <span>${escHtml(formatDate(item.createdAt))}</span>
                </div>
                ${renderConflictSides(item)}
            </div>
            <div class="archive-pending-actions">
                <button class="archive-primary-btn" ${state.governanceBusy ? 'disabled' : ''} onclick="ArchiveRoom.handleGovernance(decodeURIComponent('${encodedId}'), 'confirm')">${escHtml(tr('archive_confirm', 'Confirm'))}</button>
                <button class="archive-secondary-btn" ${state.governanceBusy ? 'disabled' : ''} onclick="ArchiveRoom.handleGovernance(decodeURIComponent('${encodedId}'), 'edit_confirm')">${escHtml(tr('archive_edit_confirm', 'Edit and confirm'))}</button>
                <button class="archive-secondary-btn" ${state.governanceBusy ? 'disabled' : ''} onclick="ArchiveRoom.handleGovernance(decodeURIComponent('${encodedId}'), 'defer')">${escHtml(tr('archive_defer', 'Defer'))}</button>
                <button class="archive-secondary-btn danger" ${state.governanceBusy ? 'disabled' : ''} onclick="ArchiveRoom.handleGovernance(decodeURIComponent('${encodedId}'), 'reject')">${escHtml(tr('archive_reject', 'Reject'))}</button>
            </div>
        </div>`;
    }

    function renderConflictSides(item) {
        if (!item.conflict && !item.confirmedSide && !item.suggestedSide) return '';
        const confirmed = item.confirmedSide || {};
        const suggested = item.suggestedSide || {};
        return `<div class="archive-conflict-sides">
            <div><label>${escHtml(tr('archive_confirmed', 'Confirmed'))}</label><span>${escHtml(confirmed.text || confirmed.title || tr('archive_not_provided', 'Not provided'))}</span></div>
            <div><label>${escHtml(tr('archive_new_suggestion', 'New suggestion'))}</label><span>${escHtml(suggested.text || suggested.title || item.text || '')}</span></div>
        </div>`;
    }

    function renderGovernanceHistory(item) {
        const meta = [authorityLabel(item.status || item.action), item.actor || '', formatDate(item.at)].filter(Boolean).join(' · ');
        return `<div class="archive-history-item">
            <strong>${escHtml(item.title || item.pendingId || tr('archive_governance_record', 'Governance record'))}</strong>
            <span>${escHtml(meta)}</span>
            ${item.reason ? `<p>${escHtml(item.reason)}</p>` : ''}
        </div>`;
    }

    async function handleGovernance(itemId, action) {
        const detail = state.detail;
        if (!detail || !detail.projectId || !itemId || state.governanceBusy) return;
        const scrollState = captureScrollState();
        const item = (detail.pendingConfirmations || []).find(x => x.id === itemId) || {};
        state.governanceDialog = {
            itemId,
            action,
            title: governanceActionTitle(action),
            itemTitle: item.title || tr('archive_pending_item', 'Pending item'),
            text: item.text || '',
            reason: '',
            error: '',
        };
        render();
        restoreScrollState(scrollState);
    }

    function governanceActionTitle(action) {
        if (action === 'confirm') return tr('archive_governance_confirm_archive', 'Confirm into archive');
        if (action === 'edit_confirm') return tr('archive_governance_edit_confirm', 'Edit then confirm');
        if (action === 'defer') return tr('archive_governance_defer', 'Defer handling');
        if (action === 'reject') return tr('archive_governance_reject', 'Reject suggestion');
        return tr('archive_governance_handle_item', 'Handle archive governance item');
    }

    function closeGovernanceDialog() {
        if (state.governanceBusy) return;
        const scrollState = captureScrollState();
        state.governanceDialog = null;
        render();
        restoreScrollState(scrollState);
    }

    async function submitGovernanceDialog() {
        const detail = state.detail;
        const dialog = state.governanceDialog;
        if (!detail || !detail.projectId || !dialog || state.governanceBusy) return;
        const scrollState = captureScrollState();
        const textEl = document.getElementById('archive-governance-dialog-text');
        const reasonEl = document.getElementById('archive-governance-dialog-reason');
        const body = { action: dialog.action };
        if (dialog.action === 'edit_confirm') {
            body.text = textEl ? textEl.value : dialog.text;
            if (!String(body.text || '').trim()) {
                state.governanceDialog = { ...dialog, error: tr('archive_governance_content_required', 'Confirmation content cannot be empty.') };
                render();
                restoreScrollState(scrollState);
                return;
            }
        }
        if (dialog.action === 'reject' || dialog.action === 'defer') {
            body.reason = reasonEl ? reasonEl.value : '';
        }
        state.governanceBusy = true;
        render();
        try {
            const d = await postJson(`/api/archive-room/projects/${encodeURIComponent(detail.projectId)}/governance/${encodeURIComponent(dialog.itemId)}`, body);
            state.detail = d.project || state.detail;
            state.projects = state.projects.map(p => p.id === detail.projectId ? { ...p, metrics: (state.detail || {}).metrics || p.metrics } : p);
            state.governanceDialog = null;
        } catch (e) {
            state.governanceDialog = { ...dialog, error: e.message || String(e) };
        } finally {
            state.governanceBusy = false;
            render();
            restoreScrollState(scrollState);
        }
    }

    function renderArtifactLauncher(p) {
        const artifacts = p.artifacts || [];
        if (!artifacts.length) {
            const msg = p.artifactError || tr('archive_no_explicit_artifacts', 'No explicitly associated task artifacts.');
            return `<div class="archive-room-empty">${escHtml(msg)}</div>`;
        }
        const byKind = artifacts.reduce((acc, item) => {
            const kind = item.kind || 'file';
            acc[kind] = (acc[kind] || 0) + 1;
            return acc;
        }, {});
        const kindText = Object.keys(byKind).sort().map(k => `${k} ${byKind[k]}`).join(' · ');
        return `
            <div class="archive-artifact-launcher">
                <div>
                    <div class="archive-artifact-launcher-title">${escHtml(trCount('archive_project_artifacts_count', '{{count}} project artifacts', artifacts.length))}</div>
                    <div class="archive-artifact-launcher-meta">${escHtml(kindText)}</div>
                </div>
                <button class="archive-primary-btn" onclick="ArchiveRoom.openProjectArtifacts()">${escHtml(tr('archive_view_project_artifacts', 'View project artifacts'))}</button>
            </div>`;
    }

    function renderArtifacts(p, mode) {
        const artifacts = p.artifacts || [];
        if (!artifacts.length) {
            const msg = p.artifactError || tr('archive_no_explicit_artifacts', 'No explicitly associated task artifacts.');
            return `<div class="archive-room-empty">${escHtml(msg)}</div>`;
        }
        const gridClass = mode === 'browser' ? '' : ' archive-artifact-list-grid';
        return `
            <div class="archive-artifact-list${gridClass}">
                ${artifacts.map(a => renderArtifactRow(p.projectId, a)).join('')}
            </div>`;
    }

    function renderArtifactBrowser(p) {
        const a = state.selectedArtifact;
        const meta = a ? `${a.kind || 'file'} · ${formatBytes(a.size)} · ${a.path}` : tr('archive_select_artifact_preview', 'Select an artifact to preview');
        const source = a ? artifactSourceText(a) : '';
        return `
            <div class="archive-artifact-browser">
                <aside class="archive-artifact-browser-sidebar">
                    <div class="archive-artifact-browser-label">
                        <span>${escHtml(tr('archive_artifact_directory', 'Artifact directory'))}</span>
                        <div class="archive-artifact-view-tabs">
                            ${artifactViewTab('source', tr('archive_artifact_by_source', 'By source'))}
                            ${artifactViewTab('path', tr('archive_artifact_by_path', 'By path'))}
                        </div>
                    </div>
                    ${renderArtifactDirectory(p)}
                </aside>
                <section class="archive-artifact-browser-preview">
                    <div class="archive-artifact-preview-head">
                        <div class="archive-artifact-preview-title">${escHtml((a && (a.name || a.path)) || tr('archive_artifact_preview', 'Artifact preview'))}</div>
                        <div class="archive-artifact-preview-meta">${escHtml(meta)}</div>
                        ${source ? `<div class="archive-artifact-source-line">${escHtml(source)}</div>` : ''}
                    </div>
                    <div class="archive-preview">${renderPreview(p.projectId)}</div>
                </section>
            </div>`;
    }

    function artifactViewTab(view, label) {
        const active = state.artifactView === view ? 'active' : '';
        return `<button class="archive-artifact-view-tab ${active}" onclick="ArchiveRoom.setArtifactView('${escHtml(view)}')">${escHtml(label)}</button>`;
    }

    function renderArtifactDirectory(p) {
        return state.artifactView === 'path' ? renderArtifactsByPath(p) : renderArtifactsBySource(p);
    }

    function renderArtifactsBySource(p) {
        const artifacts = p.artifacts || [];
        if (!artifacts.length) return renderArtifacts(p, 'browser');
        const groups = new Map();
        artifacts.forEach(a => {
            const s = ((a.sources || [])[0]) || {};
            const key = s.taskId || s.taskTitle || 'unknown-source';
            if (!groups.has(key)) {
                groups.set(key, {
                    title: s.taskTitle || tr('archive_source_unavailable', 'Source unavailable'),
                    meta: [s.agentId || s.providerKind || '', s.capturedAt ? formatDate(s.capturedAt) : ''].filter(Boolean).join(' · '),
                    artifacts: [],
                });
            }
            groups.get(key).artifacts.push(a);
        });
        return `<div class="archive-artifact-tree">${Array.from(groups.values()).map(group => `
            <div class="archive-artifact-group">
                <div class="archive-artifact-group-head">
                    <div class="archive-artifact-group-title">${escHtml(group.title)}</div>
                    <div class="archive-artifact-group-meta">${escHtml(trCount('archive_artifact_count', '{{count}} artifacts', group.artifacts.length))}${group.meta ? ` · ${escHtml(group.meta)}` : ''}</div>
                </div>
                <div class="archive-artifact-group-items">
                    ${group.artifacts.map(a => renderArtifactRow(p.projectId, a)).join('')}
                </div>
            </div>`).join('')}</div>`;
    }

    function renderArtifactsByPath(p) {
        const artifacts = p.artifacts || [];
        if (!artifacts.length) return renderArtifacts(p, 'browser');
        const root = { dirs: new Map(), files: [] };
        artifacts.forEach(a => {
            const parts = String(a.path || a.name || '').split('/').filter(Boolean);
            let node = root;
            parts.slice(0, -1).forEach(part => {
                if (!node.dirs.has(part)) node.dirs.set(part, { dirs: new Map(), files: [] });
                node = node.dirs.get(part);
            });
            node.files.push(a);
        });
        return `<div class="archive-artifact-tree">${renderPathNode(root, p.projectId, 0)}</div>`;
    }

    function renderPathNode(node, projectId, depth) {
        const dirs = Array.from(node.dirs.entries()).sort(([a], [b]) => a.localeCompare(b));
        const files = (node.files || []).slice().sort((a, b) => String(a.name || a.path).localeCompare(String(b.name || b.path)));
        return `
            ${dirs.map(([name, child]) => `
                <div class="archive-artifact-path-group" style="--archive-path-depth:${depth}">
                    <div class="archive-artifact-path-head">📁 ${escHtml(name)}</div>
                    ${renderPathNode(child, projectId, depth + 1)}
                </div>`).join('')}
            ${files.map(a => `<div class="archive-artifact-path-file" style="--archive-path-depth:${depth}">${renderArtifactRow(projectId, a)}</div>`).join('')}`;
    }

    function renderArtifactRow(projectId, a) {
        const active = state.selectedArtifact && state.selectedArtifact.path === a.path ? 'active' : '';
        const source = artifactSourceText(a);
        return `
            <button class="archive-artifact-row ${active}" onclick="ArchiveRoom.openArtifact('${escHtml(projectId)}', decodeURIComponent('${encodeURIComponent(a.path)}'))">
                <div class="archive-artifact-name">${escHtml(a.name || a.path)}</div>
                <div class="archive-artifact-meta">${escHtml(a.kind || 'file')} · ${escHtml(formatBytes(a.size))}</div>
                ${source ? `<div class="archive-artifact-source">${escHtml(source)}</div>` : `<div class="archive-artifact-source muted">${escHtml(tr('archive_source_unavailable', 'Source unavailable'))}</div>`}
                <div class="archive-artifact-meta">${escHtml(a.path)}</div>
            </button>`;
    }

    function artifactSourceText(a) {
        const sources = (a && Array.isArray(a.sources)) ? a.sources : [];
        const s = sources[0] || null;
        if (!s) return '';
        const parts = [];
        const task = s.taskTitle || s.taskId || '';
        if (task) parts.push(tr('archive_artifact_source_task', 'Source task: {{task}}', { task }));
        const agent = s.agentId || s.providerKind || '';
        if (agent) parts.push(tr('archive_artifact_ai', 'AI: {{agent}}', { agent }));
        if (s.capturedAt) parts.push(tr('archive_artifact_time', 'Time: {{time}}', { time: formatDate(s.capturedAt) }));
        if (!parts.length && s.sourceType) parts.push(tr('archive_source_label', 'Source') + `: ${s.sourceType}`);
        if (sources.length > 1) parts.push(tr('archive_additional_sources', '{{count}} more sources', { count: sources.length - 1 }));
        return parts.join(' · ');
    }

    function setArtifactView(view) {
        state.artifactView = view === 'path' ? 'path' : 'source';
        if (state.artifactBrowserOpen) showProjectArtifactsModal();
    }

    function renderPreview(projectId) {
        const a = state.selectedArtifact;
        if (!a) return `<div class="archive-room-empty">${escHtml(tr('archive_select_artifact_preview', 'Select an artifact to preview'))}</div>`;
        const url = `/api/projects/${encodeURIComponent(projectId)}/artifacts/file?path=${encodeURIComponent(a.path)}`;
        const kind = a.kind || '';
        if (kind === 'markdown' || kind === 'text') {
            return `<pre>${escHtml(state.selectedText || tr('loading', 'Loading...'))}</pre><a class="archive-open-link" href="${escHtml(url)}" target="_blank" rel="noopener">${escHtml(tr('archive_open_file', 'Open file'))}</a>`;
        }
        if (kind === 'image') {
            return `<img src="${escHtml(url)}" alt="${escHtml(a.name || a.path)}"><a class="archive-open-link" href="${escHtml(url)}" target="_blank" rel="noopener">${escHtml(tr('archive_open_image', 'Open image'))}</a>`;
        }
        if (kind === 'video') {
            return `<video src="${escHtml(url)}" controls></video><a class="archive-open-link" href="${escHtml(url)}" target="_blank" rel="noopener">${escHtml(tr('archive_open_video', 'Open video'))}</a>`;
        }
        if (kind === 'audio') {
            return `<audio src="${escHtml(url)}" controls></audio><a class="archive-open-link" href="${escHtml(url)}" target="_blank" rel="noopener">${escHtml(tr('archive_open_audio', 'Open audio'))}</a>`;
        }
        return `<div class="archive-room-empty">${escHtml(tr('archive_preview_unsupported', 'This artifact does not support inline preview yet.'))}</div><a class="archive-open-link" href="${escHtml(url)}" target="_blank" rel="noopener">${escHtml(tr('archive_open_or_download', 'Open or download'))}</a>`;
    }

    async function openArtifact(projectId, path) {
        const detail = state.detail;
        const artifact = ((detail && detail.artifacts) || []).find(a => a.path === path);
        if (!artifact) return;
        state.selectedArtifact = artifact;
        state.selectedText = '';
        if (state.artifactBrowserOpen) {
            showProjectArtifactsModal();
        } else {
            showArtifactModal(projectId);
        }
        if (artifact.kind === 'markdown' || artifact.kind === 'text') {
            try {
                const d = await fetchJson(`/api/projects/${encodeURIComponent(projectId)}/artifacts/read?archive=1&path=${encodeURIComponent(path)}`);
                state.selectedText = (d.artifact && d.artifact.content) || '';
                if (state.artifactBrowserOpen) {
                    showProjectArtifactsModal();
                } else {
                    showArtifactModal(projectId);
                }
            } catch (e) {
                state.selectedText = tr('archive_read_failed', 'Unable to read artifact: {{error}}', { error: e.message || e });
                if (state.artifactBrowserOpen) {
                    showProjectArtifactsModal();
                } else {
                    showArtifactModal(projectId);
                }
            }
        }
    }

    async function openProjectArtifacts() {
        const detail = state.detail;
        if (!detail) return;
        const artifacts = detail.artifacts || [];
        if (artifacts.length && !artifacts.some(a => state.selectedArtifact && a.path === state.selectedArtifact.path)) {
            state.selectedArtifact = artifacts[0];
            state.selectedText = '';
        }
        state.artifactBrowserOpen = true;
        showProjectArtifactsModal();
        const a = state.selectedArtifact;
        if (a && (a.kind === 'markdown' || a.kind === 'text')) {
            try {
                const d = await fetchJson(`/api/projects/${encodeURIComponent(detail.projectId)}/artifacts/read?archive=1&path=${encodeURIComponent(a.path)}`);
                state.selectedText = (d.artifact && d.artifact.content) || '';
                if (state.artifactBrowserOpen) showProjectArtifactsModal();
            } catch (e) {
                state.selectedText = tr('archive_read_failed', 'Unable to read artifact: {{error}}', { error: e.message || e });
                if (state.artifactBrowserOpen) showProjectArtifactsModal();
            }
        }
    }

    function showProjectArtifactsModal() {
        const detail = state.detail;
        if (!detail) return;
        const overlay = document.getElementById('archiveArtifactOverlay');
        const title = document.getElementById('archive-artifact-modal-title');
        const meta = document.getElementById('archive-artifact-modal-meta');
        const body = document.getElementById('archive-artifact-modal-body');
        const open = document.getElementById('archive-artifact-open-link');
        if (!overlay || !title || !meta || !body || !open) return;
        title.textContent = tr('archive_project_artifacts_title', 'Project artifacts');
        const count = (detail.artifacts || []).length;
        meta.textContent = `${detail.title || tr('archive_untitled_project', 'Untitled project')} · ${trCount('archive_artifact_count', '{{count}} artifacts', count)}`;
        const a = state.selectedArtifact;
        if (a) {
            open.href = `/api/projects/${encodeURIComponent(detail.projectId)}/artifacts/file?path=${encodeURIComponent(a.path)}`;
            open.style.display = '';
        } else {
            open.removeAttribute('href');
            open.style.display = 'none';
        }
        body.innerHTML = renderArtifactBrowser(detail);
        overlay.classList.add('archive-artifact-browser-mode');
        overlay.classList.remove('hidden');
    }

    function closeProjectArtifacts() {
        closeArtifact();
    }

    function showArtifactModal(projectId) {
        const overlay = document.getElementById('archiveArtifactOverlay');
        const title = document.getElementById('archive-artifact-modal-title');
        const meta = document.getElementById('archive-artifact-modal-meta');
        const body = document.getElementById('archive-artifact-modal-body');
        const open = document.getElementById('archive-artifact-open-link');
        const a = state.selectedArtifact;
        if (!overlay || !title || !meta || !body || !open || !a) return;
        state.artifactBrowserOpen = false;
        const url = `/api/projects/${encodeURIComponent(projectId)}/artifacts/file?path=${encodeURIComponent(a.path)}`;
        title.textContent = a.name || a.path;
        meta.textContent = `${a.kind || tr('archive_file_kind', 'file')} · ${formatBytes(a.size)} · ${a.path}`;
        open.href = url;
        open.style.display = '';
        body.innerHTML = renderPreview(projectId);
        overlay.classList.remove('archive-artifact-browser-mode');
        overlay.classList.remove('hidden');
    }

    function closeArtifact() {
        const overlay = document.getElementById('archiveArtifactOverlay');
        const open = document.getElementById('archive-artifact-open-link');
        if (overlay) {
            overlay.classList.add('hidden');
            overlay.classList.remove('archive-artifact-browser-mode');
        }
        state.artifactBrowserOpen = false;
        if (open) open.style.display = '';
    }

    function copyOnboarding() {
        const el = document.getElementById('archive-onboarding-text');
        const text = el ? el.value : '';
        if (!text) return;
        if (navigator.clipboard && navigator.clipboard.writeText) {
            navigator.clipboard.writeText(text).catch(() => {});
        } else {
            el.select();
            document.execCommand('copy');
        }
    }
})();
