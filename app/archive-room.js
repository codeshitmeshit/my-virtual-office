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

    function formatDate(value) {
        if (!value) return '未知';
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
            throw new Error(`服务返回空响应，请确认系统已启动并刷新页面。HTTP ${response.status || 0}`);
        }
        try {
            return JSON.parse(text);
        } catch (e) {
            throw new Error(`服务返回了无法解析的数据，请刷新后重试。HTTP ${response.status || 0}`);
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
        el.innerHTML = '<div class="archive-room-loading">正在加载档案室...</div>';
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
            el.innerHTML = `<div class="archive-room-error">档案室加载失败：${escHtml(e.message || e)}</div>`;
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
            el.innerHTML = '<div class="archive-room-empty">暂无项目档案。创建项目后，档案室会显示项目概览。</div>';
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
                        <button class="archive-icon-btn" ${state.governanceBusy ? 'disabled' : ''} onclick="ArchiveRoom.closeGovernanceDialog()" aria-label="关闭">×</button>
                    </div>
                    <div class="archive-governance-dialog-body">
                        ${dialog.error ? `<div class="archive-governance-dialog-error">${escHtml(dialog.error)}</div>` : ''}
                        ${isEdit ? `
                            <label class="archive-governance-field">
                                <span>确认内容</span>
                                <textarea id="archive-governance-dialog-text" rows="7">${escHtml(dialog.text || '')}</textarea>
                            </label>` : `
                            <div class="archive-governance-review">
                                <span>${isConfirm ? '确认后，这条内容会作为人工确认档案保存。' : (isReject ? '拒绝后，这条建议不会作为有效档案上下文。' : '暂缓后，这条建议会保留在治理记录中，等待后续处理。')}</span>
                                <p>${escHtml(dialog.text || '')}</p>
                            </div>`}
                        ${(isReject || isDefer) ? `
                            <label class="archive-governance-field">
                                <span>${isReject ? '拒绝原因（可选）' : '暂缓原因（可选）'}</span>
                                <textarea id="archive-governance-dialog-reason" rows="3">${escHtml(dialog.reason || '')}</textarea>
                            </label>` : ''}
                    </div>
                    <div class="archive-governance-dialog-actions">
                        <button class="archive-secondary-btn" ${state.governanceBusy ? 'disabled' : ''} onclick="ArchiveRoom.closeGovernanceDialog()">取消</button>
                        <button class="${isReject ? 'archive-secondary-btn danger' : 'archive-primary-btn'}" ${state.governanceBusy ? 'disabled' : ''} onclick="ArchiveRoom.submitGovernanceDialog()">${state.governanceBusy ? '处理中...' : (isEdit ? '确认入档' : dialog.title)}</button>
                    </div>
                </section>
            </div>`;
    }

    function managerHeaderText(mgr) {
        if (!mgr) return '🗄️ 档案管理员：未接入';
        return `${mgr.emoji || '🗄️'} ${mgr.name || '档案管理员'}：${mgr.label || mgr.status || '未接入'}`;
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
        const created = mgr.autoCreated && mgr.createdAt ? `已自动创建 · ${formatDate(mgr.createdAt)}` : (mgr.autoCreated ? '已自动创建' : '全局档案管理员');
        return `
            <div class="archive-manager-panel ${managerStatusClass(mgr)}">
                <div class="archive-manager-main">
                    <div class="archive-manager-avatar">${escHtml(mgr.emoji || '🗄️')}</div>
                    <div class="archive-manager-copy">
                        <div class="archive-manager-title">${escHtml(mgr.name || '档案管理员')}</div>
                        <div class="archive-manager-meta">${escHtml(mgr.label || '未接入')} · ${escHtml(created)}</div>
                        ${error ? `<div class="archive-manager-error">${escHtml(error)}</div>` : ''}
                    </div>
                </div>
                <div class="archive-manager-actions">
                    <button class="archive-secondary-btn" ${state.managerBusy ? 'disabled' : ''} onclick="ArchiveRoom.auditArchiveCount()">${state.managerBusy ? '检查中...' : '检查档案数目'}</button>
                    <button class="archive-secondary-btn" onclick="ArchiveRoom.openManagerActivity()">查看动态${activity.length ? ` (${activity.length})` : ''}</button>
                    <button class="archive-secondary-btn" ${state.managerBusy ? 'disabled' : ''} onclick="ArchiveRoom.refresh()">刷新</button>
                    ${paused
                        ? `<button class="archive-primary-btn" ${state.managerBusy ? 'disabled' : ''} onclick="ArchiveRoom.setManagerPaused(false)">恢复</button>`
                        : `<button class="archive-secondary-btn" ${state.managerBusy ? 'disabled' : ''} onclick="ArchiveRoom.setManagerPaused(true)">暂停</button>`}
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
                        <div id="archive-manager-activity-title" class="archive-manager-activity-title">档案管理员动态</div>
                        <div class="archive-manager-activity-subtitle">全局活动记录，不限定当前档案。</div>
                    </div>
                    <button class="archive-icon-btn" onclick="ArchiveRoom.closeManagerActivity()" aria-label="关闭">×</button>
                </div>
                <div class="archive-manager-activity-list">
                    ${activity.length ? activity.map(renderManagerActivity).join('') : '<div class="archive-manager-activity-empty">暂无维护活动</div>'}
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
                    <div class="archive-room-title">项目关注列表</div>
                    <div class="archive-room-count">${projects.length} / ${state.projects.length} 个项目</div>
                </div>
                <div class="archive-list-controls">
                    <div class="archive-filter-group">
                        ${listFilterButton('all', '全部')}
                        ${listFilterButton('pending', '待确认')}
                        ${listFilterButton('risk', '风险')}
                    </div>
                    <div class="archive-sort-group" aria-label="项目排序">
                        <span>排序</span>
                        ${listSortButton('priority', '优先')}
                        ${listSortButton('recent', '最近')}
                    </div>
                </div>
                ${projects.map(renderProjectCard).join('') || '<div class="archive-room-empty compact">没有匹配项目。</div>'}
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
                <div class="archive-project-name">${escHtml(p.title || '未命名项目')}</div>
                <div class="archive-project-desc">${escHtml(p.description || '暂无项目描述。')}</div>
                <div class="archive-metrics">
                    <div class="archive-metric"><strong>${escHtml(m.riskCount || 0)}</strong><span>风险</span></div>
                    <div class="archive-metric"><strong>${escHtml(m.pendingConfirmationCount || 0)}</strong><span>待确认</span></div>
                    <div class="archive-metric"><strong>${escHtml(m.completionRate || 0)}%</strong><span>完成</span></div>
                    <div class="archive-metric"><strong>${escHtml(m.artifactCount || 0)}</strong><span>产物</span></div>
                </div>
                <div class="archive-artifact-meta">更新于 ${escHtml(formatDate(p.updatedAt))}</div>
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
            return '<div class="archive-room-detail"><div class="archive-room-loading">正在加载项目档案...</div></div>';
        }
        const p = state.detail;
        const m = p.metrics || {};
        const s = p.summary || {};
        const manager = state.archiveManager || p.archiveManager || {};
        const maintenance = p.archiveMaintenance || {};
        return `
            <div class="archive-room-detail">
                ${state.detailLoading ? '<div class="archive-detail-loading-mask">正在加载项目档案...</div>' : ''}
                <div class="archive-detail-head">
                    <div>
                        <h2 class="archive-detail-title">${escHtml(p.title || '未命名项目')}</h2>
                        <div class="archive-detail-subtitle">档案更新于 ${escHtml(formatDate(p.archiveUpdatedAt))}</div>
                    </div>
                    <div class="archive-detail-actions">
                        <div class="archive-status-pill">${escHtml(manager.label || '未接入')}</div>
                        <button class="archive-primary-btn" ${state.managerBusy ? 'disabled' : ''} onclick="ArchiveRoom.maintainCurrentProject()">${state.managerBusy ? '刷新中...' : '刷新当前档案'}</button>
                        <button class="archive-secondary-btn" ${state.managerBusy ? 'disabled' : ''} onclick="ArchiveRoom.refineCurrentProjectWithAi()">${state.managerBusy ? '处理中...' : 'AI 精整档案'}</button>
                    </div>
                </div>
                ${manager.paused ? '<div class="archive-paused-notice">档案管理员已暂停，档案不会主动更新；你仍可以手动整理当前项目。</div>' : ''}
                ${renderArchiveIntro(p)}
                ${renderProjectBasicInfo(p)}
                ${renderMaintenanceControl(p, maintenance)}
                ${renderGovernanceSection(p)}
                <section class="archive-section">
                    <h3>关键摘要</h3>
                    <div class="archive-section-body archive-summary-grid">
                        ${summaryItem('目标', s.goal || p.description || '暂无目标记录。')}
                        ${summaryItem('当前状态', s.currentState || `${m.taskDone || 0} / ${m.taskCount || 0} 个任务完成`)}
                        ${summaryItem('下一步', s.nextStep || '暂无下一步记录。')}
                    </div>
                </section>
                <section class="archive-section">
                    <h3>上下文目录</h3>
                    <div class="archive-section-body">
                        ${(p.entries || []).map(renderEntry).join('') || '<div class="archive-room-empty">暂无档案条目。</div>'}
                    </div>
                </section>
                <section class="archive-section">
                    <h3>AI 入场包</h3>
                    <div class="archive-section-body">
                        <textarea id="archive-onboarding-text" class="archive-onboarding" readonly>${escHtml((p.onboardingPackage || {}).copyText || '')}</textarea>
                        <button class="archive-copy-btn" onclick="ArchiveRoom.copyOnboarding()">复制 AI 入场包</button>
                    </div>
                </section>
                <section class="archive-section">
                    <h3>任务产物</h3>
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
                <div class="archive-hero-eyebrow">项目档案</div>
                <h3>${escHtml(intro.title || `${p.title || '项目'} 的项目档案`)}</h3>
                <p>${escHtml(intro.purpose || '这个档案用于沉淀项目长期上下文，帮助人类和 AI 快速理解项目。')}</p>
                <div class="archive-hero-actions">
                    <span>${escHtml(readiness.label || '可用')}</span>
                    <span>${escHtml(readiness.summary || '')}</span>
                    <button class="archive-hero-artifact-btn" ${artifactCount ? '' : 'disabled'} onclick="ArchiveRoom.openProjectArtifacts()">查看项目产物</button>
                </div>
            </div>
            <div class="archive-hero-side">
                <div class="archive-hero-side-title">这个档案里有什么</div>
                <div class="archive-mini-tags">${contains.slice(0, 8).map(x => `<span>${escHtml(x)}</span>`).join('') || '<span>暂无记录</span>'}</div>
                <div class="archive-hero-side-title muted">待补充</div>
                <div class="archive-mini-tags muted">${missing.slice(0, 6).map(x => `<span>${escHtml(x)}</span>`).join('') || '<span>暂无</span>'}</div>
            </div>
        </section>
        <section class="archive-section">
            <h3>档案索引</h3>
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
                </div>`).join('') || '<div class="archive-room-empty">暂无需要优先关注的档案信息。</div>'}
            </div>
            <div class="archive-index-grid">
                ${sections.map(renderArchiveIndexSection).join('')}
            </div>
            <div class="archive-index-footer">${escHtml(index.footer || '索引由当前项目档案实时派生。')}</div>
        </div>`;
    }

    function renderArchiveIndexSection(section) {
        const items = section.items || [];
        return `<div class="archive-index-section">
            <div class="archive-index-section-title">${escHtml(section.label || '')}</div>
            <div class="archive-index-items">
                ${items.map(renderArchiveIndexItem).join('') || `<div class="archive-index-empty">${escHtml(section.emptyText || '暂无记录')}</div>`}
            </div>
        </div>`;
    }

    function renderArchiveIndexItem(item) {
        const meta = [item.kind, item.confidence, item.status, item.assignee].filter(Boolean).join(' · ');
        return `<div class="archive-index-item">
            <strong>${escHtml(item.title || item.path || '未命名')}</strong>
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
                    <span>${escHtml(item.summary || (item.present === false || item.available === false ? '暂无记录' : '可用'))}</span>
                </div>`).join('') || '<div class="archive-room-empty">暂无信息地图。</div>'}
            </div>
        </div>`;
    }

    function renderProjectBasicInfo(p) {
        const info = p.projectBasicInfo || {};
        return `<section class="archive-section">
            <h3>项目基础信息</h3>
            <div class="archive-section-body archive-basic-grid">
                ${summaryItem('项目名称', info.name || p.title || '未命名项目')}
                ${summaryItem('项目描述', info.description || '未记录')}
                ${summaryItem('项目状态', info.status || p.status || 'active')}
                ${summaryItem('任务进度', `${info.taskProgress || '0 / 0'} · ${escHtml(String(info.completionRate || 0))}%`)}
                ${summaryItem('长期维护', info.maintenanceLabel || '未记录')}
                ${summaryItem('活跃 AI/参与者', info.participantsLabel || '暂无活跃 AI')}
                ${summaryItem('项目产物', `${info.artifactCount || 0} 个`)}
                ${summaryItem('待确认', `${info.pendingConfirmationCount || 0} 个`)}
                ${summaryItem('主要来源', info.sourceTypesLabel || '暂无来源记录')}
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
                <div class="archive-maintenance-title">${enabled ? '长期维护已开启' : '长期维护已关闭'}</div>
                <div class="archive-maintenance-copy">${enabled
                    ? '启动/每日巡检会补漏维护这个项目，高价值事件会自动归档。'
                    : '定时巡检和低价值事件会跳过，高价值事件仍会归档。'}</div>
                <div class="archive-maintenance-copy">默认：${maintenance.defaultEnabled ? '按当前状态开启' : '按当前状态关闭'} · 最近巡检：${escHtml(lastInspection ? formatDate(lastInspection) : '暂无')}</div>
                <div class="archive-maintenance-schedule ${enabled ? '' : 'disabled'}">
                    <div class="archive-maintenance-schedule-main">
                        <strong>${escHtml(maintenance.frequencyLabel || '事件触发 + 每日巡检')}</strong>
                        <span>下次计划：${escHtml(maintenance.nextScheduledAt ? formatDate(maintenance.nextScheduledAt) : '无')} · 上次计划：${escHtml(maintenance.lastScheduledAt ? formatDate(maintenance.lastScheduledAt) : '暂无')} · 上次事件：${escHtml(maintenance.lastEventTriggeredAt ? formatDate(maintenance.lastEventTriggeredAt) : '暂无')}</span>
                        ${maintenance.lastSkippedReason ? `<em>最近跳过：${escHtml(maintenance.lastSkippedReason)} ${maintenance.lastSkippedAt ? `· ${escHtml(formatDate(maintenance.lastSkippedAt))}` : ''}</em>` : ''}
                    </div>
                    <button type="button" class="archive-secondary-btn" ${state.managerBusy || !enabled ? 'disabled' : ''} onclick="ArchiveRoom.toggleSchedulePanel()">${state.schedulePanelOpen ? '收起调整' : '调整频率'}</button>
                </div>
                ${state.schedulePanelOpen ? renderSchedulePanel(p, maintenance, enabled) : ''}
                ${notices.length ? `<div class="archive-auto-governance">
                    <div class="archive-auto-governance-title">管理员自动治理</div>
                    ${notices.map(renderAutoGovernanceNotice).join('')}
                </div>` : ''}
            </div>
            <button type="button" class="archive-maintenance-toggle ${enabled ? 'archive-secondary-btn' : 'archive-primary-btn'}" ${state.managerBusy ? 'disabled' : ''} onclick="ArchiveRoom.setProjectMaintenance('${escHtml(p.projectId)}', ${enabled ? 'false' : 'true'})">${enabled ? '关闭长期维护' : '开启长期维护'}</button>
        </section>`;
    }

    function renderSchedulePanel(p, maintenance, enabled) {
        const mode = maintenance.scheduleMode || maintenance.frequency || 'daily';
        const options = [
            ['event_only', '仅事件触发', '只在任务、会议、重要消息等事件发生时整理。'],
            ['daily', '事件触发 + 每日巡检', '默认策略，每天补漏一次。'],
            ['weekly', '事件触发 + 每周巡检', '更轻量，适合变化较少的项目。'],
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
            <strong>${escHtml(item.title || item.action || '自动治理')}</strong>
            <span>${escHtml(item.summary || '')}</span>
            ${cmp.managerJudgment ? `<em>${escHtml(cmp.managerJudgment)}</em>` : ''}
            ${(cmp.oldSourceLabel || cmp.newSourceLabel) ? `<small>旧：${escHtml(cmp.oldSourceLabel || '无')} · 新：${escHtml(cmp.newSourceLabel || '无')}</small>` : ''}
        </div>`;
    }

    function renderMaintenanceHistory(p) {
        const history = (p.managerMaintenance || []).slice().reverse().slice(0, 8);
        if (!history.length) return '';
        return `<section class="archive-section">
            <h3>档案整理记录</h3>
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
            title: '档案管理员正在刷新当前档案',
            message: '已调派档案管理员根据当前项目、任务和产物记录刷新档案。',
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
                title: latest.status === 'error' ? '档案刷新失败' : '档案刷新完成',
                message: latest.summary || ((latest.output || {}).summary) || '当前项目档案已刷新。',
            };
        } catch (e) {
            state.managerNotice = {
                status: 'error',
                title: '档案刷新失败',
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
            title: '已委派档案管理员 AI 精整档案',
            message: '档案管理员正在阅读项目、任务、产物、待确认项和现有档案，并返回稳定 JSON 用于入档。',
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
                title: latest.status === 'error' ? 'AI 精整失败' : 'AI 精整完成',
                message: latest.summary || ((latest.output || {}).summary) || '档案管理员 AI 已完成精整并入档。',
            };
        } catch (e) {
            state.managerNotice = {
                status: 'error',
                title: 'AI 精整失败',
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
                ${entry.staleReason ? `<div class="archive-entry-stale">已过期：${escHtml(entry.staleReason)}</div>` : ''}
                ${renderSourceComparison(entry.sourceComparison)}
                <div class="archive-tags">${tags.map(t => `<span class="archive-tag">${escHtml(t)}</span>`).join('')}</div>
            </div>`;
    }

    function renderSourceComparison(cmp) {
        if (!cmp || (!cmp.oldSourceLabel && !cmp.newSourceLabel && !cmp.managerJudgment)) return '';
        return `<div class="archive-source-comparison">
            <div><label>旧来源</label><span>${escHtml(cmp.oldSourceLabel || cmp.oldTitle || '无')}</span></div>
            <div><label>新来源</label><span>${escHtml(cmp.newSourceLabel || cmp.newTitle || '无')}</span></div>
            ${cmp.managerJudgment ? `<p>${escHtml(cmp.managerJudgment)}</p>` : ''}
        </div>`;
    }

    function authorityLabel(value) {
        const map = {
            human_confirmed: '人工确认',
            system_confirmed: '系统确认',
            source_confirmed: '来源确认',
            archive_manager_confirmed: '管理员确认',
            pending_human_confirmation: '待人工确认',
            deferred: '已暂缓',
            rejected: '已拒绝',
            confirmed_fact: '已确认',
            ai_inference: 'AI整理',
            pending_confirmation_suggestion: '待确认',
        };
        return map[value] || value || '未知';
    }

    function renderGovernanceSection(p) {
        const pending = p.pendingConfirmations || [];
        const history = (p.processedGovernance || []).slice().reverse().slice(0, 8);
        return `<section class="archive-section archive-governance-section">
            <h3>档案治理</h3>
            <div class="archive-section-body">
                <div class="archive-governance-head">
                    <div>
                        <strong>${escHtml(pending.filter(x => (x.authority || x.status) !== 'deferred').length)} 个待人工确认</strong>
                        <span>长期规则、高影响建议和冲突会进入这里；客观事实和低风险管理员整理不会打扰人工队列。</span>
                    </div>
                    <div class="archive-authority-legend">
                        <span>系统/来源确认</span><span>管理员确认</span><span>人工确认</span>
                    </div>
                </div>
                <div class="archive-pending-list">
                    ${pending.map(renderPendingItem).join('') || '<div class="archive-room-empty compact">暂无待确认治理项。</div>'}
                </div>
                <div class="archive-history-block">
                    <div class="archive-history-title">处理历史</div>
                    ${history.map(renderGovernanceHistory).join('') || '<div class="archive-room-empty compact">暂无处理历史。</div>'}
                </div>
            </div>
        </section>`;
    }

    function renderPendingItem(item) {
        const authority = item.authority || item.status || 'pending_human_confirmation';
        const deferred = authority === 'deferred' || item.status === 'deferred';
        const sources = (item.sources || []).map(s => s.title || s.id || s.type || s.sourceType).filter(Boolean).slice(0, 3).join(' · ');
        const conflict = item.conflictSummary || (item.conflict && '与已确认内容冲突');
        const encodedId = encodeURIComponent(item.id || '');
        return `<div class="archive-pending-item ${deferred ? 'deferred' : ''} ${conflict ? 'conflict' : ''}">
            <div class="archive-pending-main">
                <div class="archive-pending-title-row">
                    <strong>${escHtml(item.title || '待确认项')}</strong>
                    <span class="archive-authority-pill">${escHtml(authorityLabel(authority))}</span>
                    ${item.impact ? `<span class="archive-impact-pill">${escHtml(item.impact)}</span>` : ''}
                </div>
                ${conflict ? `<div class="archive-conflict-summary">${escHtml(conflict)}</div>` : ''}
                <p>${escHtml(item.text || '')}</p>
                <div class="archive-pending-meta">
                    ${item.reason ? `<span>原因：${escHtml(item.reason)}</span>` : ''}
                    ${sources ? `<span>来源：${escHtml(sources)}</span>` : '<span>来源不可用</span>'}
                    <span>${escHtml(formatDate(item.createdAt))}</span>
                </div>
                ${renderConflictSides(item)}
            </div>
            <div class="archive-pending-actions">
                <button class="archive-primary-btn" ${state.governanceBusy ? 'disabled' : ''} onclick="ArchiveRoom.handleGovernance(decodeURIComponent('${encodedId}'), 'confirm')">确认</button>
                <button class="archive-secondary-btn" ${state.governanceBusy ? 'disabled' : ''} onclick="ArchiveRoom.handleGovernance(decodeURIComponent('${encodedId}'), 'edit_confirm')">编辑确认</button>
                <button class="archive-secondary-btn" ${state.governanceBusy ? 'disabled' : ''} onclick="ArchiveRoom.handleGovernance(decodeURIComponent('${encodedId}'), 'defer')">暂缓</button>
                <button class="archive-secondary-btn danger" ${state.governanceBusy ? 'disabled' : ''} onclick="ArchiveRoom.handleGovernance(decodeURIComponent('${encodedId}'), 'reject')">拒绝</button>
            </div>
        </div>`;
    }

    function renderConflictSides(item) {
        if (!item.conflict && !item.confirmedSide && !item.suggestedSide) return '';
        const confirmed = item.confirmedSide || {};
        const suggested = item.suggestedSide || {};
        return `<div class="archive-conflict-sides">
            <div><label>已确认</label><span>${escHtml(confirmed.text || confirmed.title || '未提供')}</span></div>
            <div><label>新建议</label><span>${escHtml(suggested.text || suggested.title || item.text || '')}</span></div>
        </div>`;
    }

    function renderGovernanceHistory(item) {
        const meta = [authorityLabel(item.status || item.action), item.actor || '', formatDate(item.at)].filter(Boolean).join(' · ');
        return `<div class="archive-history-item">
            <strong>${escHtml(item.title || item.pendingId || '治理记录')}</strong>
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
            itemTitle: item.title || '待确认项',
            text: item.text || '',
            reason: '',
            error: '',
        };
        render();
        restoreScrollState(scrollState);
    }

    function governanceActionTitle(action) {
        if (action === 'confirm') return '确认入档';
        if (action === 'edit_confirm') return '编辑后确认';
        if (action === 'defer') return '暂缓处理';
        if (action === 'reject') return '拒绝建议';
        return '处理档案治理项';
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
                state.governanceDialog = { ...dialog, error: '确认内容不能为空。' };
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
            const msg = p.artifactError || '暂无明确关联的任务产物。';
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
                    <div class="archive-artifact-launcher-title">${escHtml(artifacts.length)} 个项目产物</div>
                    <div class="archive-artifact-launcher-meta">${escHtml(kindText)}</div>
                </div>
                <button class="archive-primary-btn" onclick="ArchiveRoom.openProjectArtifacts()">查看项目产物</button>
            </div>`;
    }

    function renderArtifacts(p, mode) {
        const artifacts = p.artifacts || [];
        if (!artifacts.length) {
            const msg = p.artifactError || '暂无明确关联的任务产物。';
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
        const meta = a ? `${a.kind || 'file'} · ${formatBytes(a.size)} · ${a.path}` : '选择一个产物查看预览';
        const source = a ? artifactSourceText(a) : '';
        return `
            <div class="archive-artifact-browser">
                <aside class="archive-artifact-browser-sidebar">
                    <div class="archive-artifact-browser-label">
                        <span>产物目录</span>
                        <div class="archive-artifact-view-tabs">
                            ${artifactViewTab('source', '按来源')}
                            ${artifactViewTab('path', '按路径')}
                        </div>
                    </div>
                    ${renderArtifactDirectory(p)}
                </aside>
                <section class="archive-artifact-browser-preview">
                    <div class="archive-artifact-preview-head">
                        <div class="archive-artifact-preview-title">${escHtml((a && (a.name || a.path)) || '产物预览')}</div>
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
                    title: s.taskTitle || '来源不可用',
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
                    <div class="archive-artifact-group-meta">${escHtml(group.artifacts.length)} 个产物${group.meta ? ` · ${escHtml(group.meta)}` : ''}</div>
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
                ${source ? `<div class="archive-artifact-source">${escHtml(source)}</div>` : '<div class="archive-artifact-source muted">来源不可用</div>'}
                <div class="archive-artifact-meta">${escHtml(a.path)}</div>
            </button>`;
    }

    function artifactSourceText(a) {
        const sources = (a && Array.isArray(a.sources)) ? a.sources : [];
        const s = sources[0] || null;
        if (!s) return '';
        const parts = [];
        const task = s.taskTitle || s.taskId || '';
        if (task) parts.push(`来源任务：${task}`);
        const agent = s.agentId || s.providerKind || '';
        if (agent) parts.push(`AI：${agent}`);
        if (s.capturedAt) parts.push(`时间：${formatDate(s.capturedAt)}`);
        if (!parts.length && s.sourceType) parts.push(`来源：${s.sourceType}`);
        if (sources.length > 1) parts.push(`另有 ${sources.length - 1} 条来源`);
        return parts.join(' · ');
    }

    function setArtifactView(view) {
        state.artifactView = view === 'path' ? 'path' : 'source';
        if (state.artifactBrowserOpen) showProjectArtifactsModal();
    }

    function renderPreview(projectId) {
        const a = state.selectedArtifact;
        if (!a) return '<div class="archive-room-empty">选择一个产物查看预览。</div>';
        const url = `/api/projects/${encodeURIComponent(projectId)}/artifacts/file?path=${encodeURIComponent(a.path)}`;
        const kind = a.kind || '';
        if (kind === 'markdown' || kind === 'text') {
            return `<pre>${escHtml(state.selectedText || '正在加载...')}</pre><a class="archive-open-link" href="${escHtml(url)}" target="_blank" rel="noopener">打开文件</a>`;
        }
        if (kind === 'image') {
            return `<img src="${escHtml(url)}" alt="${escHtml(a.name || a.path)}"><a class="archive-open-link" href="${escHtml(url)}" target="_blank" rel="noopener">打开图片</a>`;
        }
        if (kind === 'video') {
            return `<video src="${escHtml(url)}" controls></video><a class="archive-open-link" href="${escHtml(url)}" target="_blank" rel="noopener">打开视频</a>`;
        }
        if (kind === 'audio') {
            return `<audio src="${escHtml(url)}" controls></audio><a class="archive-open-link" href="${escHtml(url)}" target="_blank" rel="noopener">打开音频</a>`;
        }
        return `<div class="archive-room-empty">这个产物暂不支持内嵌预览。</div><a class="archive-open-link" href="${escHtml(url)}" target="_blank" rel="noopener">打开或下载</a>`;
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
                state.selectedText = `无法读取产物：${e.message || e}`;
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
                state.selectedText = `无法读取产物：${e.message || e}`;
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
        title.textContent = '项目产物';
        const count = (detail.artifacts || []).length;
        meta.textContent = `${detail.title || '未命名项目'} · ${count} 个产物`;
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
        meta.textContent = `${a.kind || '文件'} · ${formatBytes(a.size)} · ${a.path}`;
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
