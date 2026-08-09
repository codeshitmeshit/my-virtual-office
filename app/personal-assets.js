(function (root) {
    'use strict';

    const state = {
        open: false,
        loading: false,
        revision: 0,
        entries: [],
        suggestions: [],
        view: 'overview',
        selectedEntryId: '',
        editorDraft: null,
        busyAction: '',
        notice: '',
        error: '',
        returnFocus: null,
        selectedCategory: 'basic-info',
        sync: {
            enabled: true,
            status: 'idle',
            operation: '',
            pendingRevision: 0,
            syncedRevision: 0,
            lastSyncedAt: '',
            retryAt: '',
            attempt: 0,
            lastErrorCode: '',
            hasConflict: false,
        },
        availability: {
            status: 'checking',
            checkedAt: '',
            code: '',
        },
        syncPollTimer: null,
    };

    function tr(key, fallback) {
        if (root.i18n && typeof root.i18n.t === 'function') {
            const translated = root.i18n.t(key);
            if (translated && translated !== key) return translated;
        }
        return fallback;
    }

    function esc(value) {
        return String(value == null ? '' : value)
            .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;').replace(/'/g, '&#39;');
    }

    function modal() { return document.getElementById('personalAssetsModal'); }
    function content() { return document.getElementById('personal-assets-content'); }
    function toggle() { return document.getElementById('personal-assets-toggle'); }

    async function managementJson(path, options) {
        if (!root.i18n || typeof root.i18n.managementFetch !== 'function') {
            throw new Error(tr('personal_assets_management_unavailable', 'Management access is unavailable'));
        }
        const response = await root.i18n.managementFetch(path, options || {});
        const data = await response.json();
        if (!response.ok || data.ok === false) throw new Error(data.code || 'personal_asset_request_failed');
        return data;
    }

    function setProfile(profile) {
        const value = profile && typeof profile === 'object' ? profile : {};
        state.revision = Number(value.revision || 0);
        state.entries = Array.isArray(value.entries) ? value.entries : [];
        state.suggestions = Array.isArray(value.suggestions) ? value.suggestions : [];
        ensureSelectedCategory();
    }

    function setSync(sync) {
        if (!sync || typeof sync !== 'object') return;
        state.sync = {
            ...state.sync,
            enabled: sync.enabled !== false,
            status: String(sync.status || 'idle'),
            operation: String(sync.operation || ''),
            pendingRevision: Number(sync.pendingRevision || 0),
            syncedRevision: Number(sync.syncedRevision || 0),
            lastSyncedAt: String(sync.lastSyncedAt || ''),
            retryAt: String(sync.retryAt || ''),
            attempt: Number(sync.attempt || 0),
            lastErrorCode: String(sync.lastErrorCode || ''),
            hasConflict: Boolean(sync.hasConflict),
        };
    }

    function setAvailability(availability) {
        const value = availability && typeof availability === 'object' ? availability : {};
        const status = String(value.status || 'unavailable');
        state.availability = {
            status: ['checking', 'available', 'unconfigured', 'unavailable'].includes(status) ? status : 'unavailable',
            checkedAt: String(value.checkedAt || ''),
            code: String(value.code || ''),
        };
    }

    function valueText(value) {
        if (typeof value === 'string') return value;
        try { return JSON.stringify(value, null, 2); } catch (_error) { return ''; }
    }

    const CATEGORY_GROUPS = [
        { id: 'basic-info', key: 'personal_assets_basic_info', fallback: 'Basic information', hintKey: 'personal_assets_basic_info_hint', hint: 'Name, language, region, and time preferences.', aliases: ['basic-info', 'basic', 'profile', 'basic-information', '基础信息', '基本信息'] },
        { id: 'career-direction', key: 'personal_assets_career_direction', fallback: 'Career & direction', hintKey: 'personal_assets_career_direction_hint', hint: 'Current role and future VO direction.', aliases: ['career-direction', 'career', 'profession', 'occupation', 'vo-direction', '职业与方向', '当前职业', '主攻方向'] },
        { id: 'interests', key: 'personal_assets_interests', fallback: 'Interests', hintKey: 'personal_assets_interests_hint', hint: 'Topics and activities you care about.', aliases: ['interests', 'interest', 'hobbies', 'hobby', '兴趣爱好', '兴趣'] },
        { id: 'chat-preferences', key: 'personal_assets_chat_preferences', fallback: 'Chat preferences', hintKey: 'personal_assets_chat_preferences_hint', hint: 'Preferred response style and collaboration rhythm.', aliases: ['chat-preferences', 'chat-preference', 'communication', '聊天偏好', '沟通偏好'] },
        { id: 'office-goals', key: 'personal_assets_office_goals', fallback: 'Office goals', hintKey: 'personal_assets_office_goals_hint', hint: 'The outcomes you want the virtual office to pursue.', aliases: ['office-goals', 'office-goal', 'goals', '目标', '办公室目标'] },
        { id: 'other', key: 'personal_assets_other', fallback: 'Other information', hintKey: 'personal_assets_other_hint', hint: 'Extensible information and optional sensitive fields.', aliases: [] },
    ];

    function normalizeToken(value) {
        return String(value || '').trim().toLowerCase().replace(/[\s_]+/g, '-');
    }

    function categoryGroupId(entry) {
        const category = normalizeToken(entry && entry.category);
        const label = normalizeToken(entry && entry.label);
        const matched = CATEGORY_GROUPS.find(group => group.id !== 'other' && group.aliases.some(alias => {
            const token = normalizeToken(alias);
            return category === token || category.includes(token) || label.includes(token);
        }));
        return matched ? matched.id : 'other';
    }

    function groupById(id) {
        return CATEGORY_GROUPS.find(group => group.id === id) || CATEGORY_GROUPS[CATEGORY_GROUPS.length - 1];
    }

    function groupLabel(group) {
        return tr(group.key, group.fallback);
    }

    function groupHint(group) {
        return tr(group.hintKey, group.hint);
    }

    function categoryCounts() {
        return state.entries.reduce((counts, entry) => {
            const id = categoryGroupId(entry);
            counts[id] = (counts[id] || 0) + 1;
            return counts;
        }, {});
    }

    function ensureSelectedCategory() {
        if (state.selectedCategory === 'all') return;
        const counts = categoryCounts();
        if (!counts[state.selectedCategory]) {
            state.selectedCategory = counts['basic-info'] ? 'basic-info' : 'all';
        }
    }

    function fieldDescription(item, group) {
        const label = normalizeToken(item && item.label);
        const category = normalizeToken(item && item.category);
        const value = label + ' ' + category;
        const matches = [
            { tokens: ['称呼', 'nickname', 'display-name', 'name'], key: 'personal_assets_field_name_hint', fallback: 'How Agents should address you in conversations.' },
            { tokens: ['常用语言', 'language'], key: 'personal_assets_field_language_hint', fallback: 'The default language for replies and generated content.' },
            { tokens: ['所在地区', 'region', 'location'], key: 'personal_assets_field_region_hint', fallback: 'Used for regional formats, services, and context.' },
            { tokens: ['所在时区', 'timezone', 'time-zone'], key: 'personal_assets_field_timezone_hint', fallback: 'Used for dates, reminders, and schedule conversion.' },
            { tokens: ['职业', 'profession', 'occupation', 'role'], key: 'personal_assets_field_career_hint', fallback: 'Your current role and working context.' },
            { tokens: ['主攻方向', 'vo-direction', 'direction'], key: 'personal_assets_field_direction_hint', fallback: 'The direction you want to prioritize in VO.' },
            { tokens: ['聊天偏好', 'chat-preference'], key: 'personal_assets_field_chat_hint', fallback: 'How Agents should communicate and structure responses.' },
            { tokens: ['办公室目标', 'office-goal'], key: 'personal_assets_field_goal_hint', fallback: 'The outcomes Agents should proactively work toward.' },
        ];
        const match = matches.find(candidate => candidate.tokens.some(token => value.includes(normalizeToken(token))));
        return match ? tr(match.key, match.fallback) : groupHint(group);
    }

    function activeSuggestions() {
        return state.suggestions.filter(item => item && item.status === 'pending');
    }

    function statusMessage() {
        if (!state.notice && !state.error) return '';
        return '<div class="personal-assets-message ' + (state.error ? 'is-error' : 'is-success') + '" role="' + (state.error ? 'alert' : 'status') + '">' +
            esc(state.error || state.notice) + '</div>';
    }

    function syncStatusLabel() {
        const labels = {
            idle: tr('personal_assets_sync_idle', 'Idle'),
            pending: tr('personal_assets_sync_pending', 'Pending'),
            syncing: tr('personal_assets_syncing', 'Syncing'),
            restoring: tr('personal_assets_sync_restoring', 'Restoring'),
            synced: tr('personal_assets_sync_synced', 'Synced'),
            failed: tr('personal_assets_sync_failed', 'Sync failed'),
            conflict: tr('personal_assets_sync_conflict', 'Conflict'),
        };
        return labels[state.sync.status] || labels.idle;
    }

    function availabilityStatusLabel() {
        const labels = {
            checking: tr('personal_assets_oss_checking', 'Checking'),
            available: tr('personal_assets_oss_available', 'Available'),
            unconfigured: tr('personal_assets_oss_unconfigured', 'Not configured'),
            unavailable: tr('personal_assets_oss_unavailable', 'Unavailable'),
        };
        return labels[state.availability.status] || labels.unavailable;
    }

    function visibleSyncStatusLabel() {
        if (['pending', 'syncing', 'restoring', 'failed', 'conflict'].includes(state.sync.status) || state.sync.hasConflict) {
            return syncStatusLabel();
        }
        return availabilityStatusLabel();
    }

    function visibleSyncStatusClass() {
        if (['pending', 'syncing', 'restoring', 'failed', 'conflict'].includes(state.sync.status) || state.sync.hasConflict) {
            return 'sync-' + state.sync.status;
        }
        return state.availability.status;
    }

    function renderSyncPanel() {
        const active = state.sync.enabled;
        const busy = Boolean(state.busyAction);
        const ossAvailable = state.availability.status === 'available';
        const failed = state.sync.status === 'failed';
        const conflict = state.sync.status === 'conflict' || state.sync.hasConflict;
        const lastSuccess = state.sync.lastSyncedAt || tr('personal_assets_sync_never', 'Not synced yet');
        const error = failed && state.sync.lastErrorCode
            ? '<span class="personal-assets-sync-error">' + esc(tr('personal_assets_sync_retry_hint', 'Local data is safe. Background retry will continue.')) + '</span>'
            : '';
        const availabilityHint = state.availability.status === 'unconfigured'
            ? '<span class="personal-assets-sync-availability-hint">' + esc(tr('personal_assets_oss_unconfigured_hint', 'VO OSS is not configured. Local profile features remain available.')) + '</span>'
            : state.availability.status === 'unavailable'
                ? '<span class="personal-assets-sync-availability-hint">' + esc(tr('personal_assets_oss_unavailable_hint', 'VO OSS is temporarily unavailable. Local profile features remain available.')) + '</span>'
                : '';
        const normalActions = conflict ? '' :
            '<button type="button" data-sync-now' + (busy || !active || !ossAvailable ? ' disabled' : '') + '>' +
            esc(failed ? tr('personal_assets_sync_retry', 'Retry') : tr('personal_assets_sync_now', 'Sync now')) + '</button>';
        const conflictActions = conflict ?
            '<button type="button" data-sync-resolution="remote"' + (busy ? ' disabled' : '') + '>' + esc(tr('personal_assets_use_cloud', 'Use cloud')) + '</button>' +
            '<button type="button" class="is-primary" data-sync-resolution="local"' + (busy ? ' disabled' : '') + '>' + esc(tr('personal_assets_keep_local', 'Keep local')) + '</button>' : '';
        return '<section class="personal-assets-sync is-' + esc(state.sync.status) + '" aria-label="' + esc(tr('personal_assets_sync_title', 'Cloud synchronization')) + '">' +
            '<div class="personal-assets-sync-copy"><div class="personal-assets-sync-heading"><strong>' + esc(tr('personal_assets_sync_title', 'Cloud synchronization')) + '</strong>' +
            '<span class="personal-assets-sync-status is-' + esc(visibleSyncStatusClass()) + '">' + esc(visibleSyncStatusLabel()) + '</span></div>' +
            '<p>' + esc(tr('personal_assets_sync_weak_hint', 'Local saves succeed first. VO OSS runs in the background and never blocks your profile.')) + '</p>' +
            '<small>' + esc(tr('personal_assets_sync_last', 'Last successful sync')) + ': ' + esc(lastSuccess) + '</small>' + error + availabilityHint + '</div>' +
            '<div class="personal-assets-sync-actions"><button type="button" class="personal-assets-sync-toggle" data-sync-toggle="' + (active ? 'false' : 'true') + '" aria-pressed="' + (active ? 'true' : 'false') + '"' + (busy ? ' disabled' : '') + '>' +
            '<span>' + esc(tr('personal_assets_auto_sync', 'Auto sync')) + '</span><i aria-hidden="true"></i></button>' + normalActions + conflictActions + '</div></section>';
    }

    function renderOverview() {
        ensureSelectedCategory();
        const counts = categoryCounts();
        const categories = [{ id: 'all', key: 'personal_assets_all', fallback: 'All information' }, ...CATEGORY_GROUPS];
        const categoryNav = categories.map(group => {
            const count = group.id === 'all' ? state.entries.length : (counts[group.id] || 0);
            const selected = state.selectedCategory === group.id;
            const hint = group.id === 'all'
                ? tr('personal_assets_all_hint', 'Browse every saved profile field.')
                : groupHint(group);
            return '<button type="button" class="personal-assets-category-item' + (selected ? ' is-active' : '') + '" data-category-id="' + esc(group.id) + '" aria-current="' + (selected ? 'true' : 'false') + '">' +
                '<strong>' + esc(group.id === 'all' ? tr(group.key, group.fallback) : groupLabel(group)) + '</strong>' +
                '<span>' + esc(String(count) + ' ' + tr('personal_assets_items', 'items')) + '</span>' +
                '<small>' + esc(hint) + '</small></button>';
        }).join('');

        function renderField(item, group) {
            const sensitive = item.sensitivity === 'sensitive';
            const savedLabel = sensitive
                ? tr('personal_assets_sensitive_saved_content', 'Sensitive content · reads require a decision')
                : tr('personal_assets_saved_content', 'Saved content');
            return '<article class="personal-assets-field-row' + (sensitive ? ' is-sensitive' : '') + '">' +
                '<div class="personal-assets-field-description"><h4>' + esc(item.label) + '</h4><p>' + esc(fieldDescription(item, group)) + '</p></div>' +
                '<div class="personal-assets-saved-value"><span>' + esc(savedLabel) + '</span><pre>' + esc(valueText(item.value)) + '</pre></div>' +
                '<button type="button" class="personal-assets-edit-action" data-edit-id="' + esc(item.id) + '" aria-label="' + esc(tr('personal_assets_edit_action', 'Edit this information')) + '" title="' + esc(tr('personal_assets_edit_action', 'Edit this information')) + '">' +
                '<span aria-hidden="true">✎</span><span class="personal-assets-visually-hidden">' + esc(tr('personal_assets_edit_action', 'Edit this information')) + '</span></button></article>';
        }

        function renderGroup(group) {
            const entries = state.entries.filter(entry => categoryGroupId(entry) === group.id);
            if (!entries.length) return '';
            return '<section class="personal-assets-entry-group" data-entry-group="' + esc(group.id) + '">' +
                '<div class="personal-assets-section-heading"><div><h3>' + esc(groupLabel(group)) + '</h3><p>' + esc(groupHint(group)) + '</p></div>' +
                '<span>' + esc(String(entries.length) + ' ' + tr('personal_assets_items', 'items')) + '</span></div>' +
                '<div class="personal-assets-field-guide"><span>' + esc(tr('personal_assets_field_and_purpose', 'Field and purpose')) + '</span><strong>' + esc(tr('personal_assets_saved_content', 'Saved content')) + '</strong><em>' + esc(tr('personal_assets_edit_action_short', 'Edit')) + '</em></div>' +
                entries.map(item => renderField(item, group)).join('') + '</section>';
        }

        const selectedGroup = state.selectedCategory === 'all' ? null : groupById(state.selectedCategory);
        const rows = selectedGroup ? renderGroup(selectedGroup) : CATEGORY_GROUPS.map(renderGroup).join('');
        const workspace = state.entries.length
            ? '<div class="personal-assets-overview-layout"><nav class="personal-assets-category-nav" aria-label="' + esc(tr('personal_assets_categories', 'Profile categories')) + '">' +
                '<div class="personal-assets-nav-heading">' + esc(tr('personal_assets_browse_by_type', 'Browse by type')) + '</div>' + categoryNav +
                '<aside class="personal-assets-sensitive-note"><strong>' + esc(tr('personal_assets_sensitive', 'Sensitive')) + '</strong><p>' + esc(tr('personal_assets_sensitive_decision_hint', 'This panel only marks sensitivity. Agent read requests are handled in HUMAN DECISIONS.')) + '</p></aside></nav>' +
                '<div class="personal-assets-profile-workspace">' + rows + '</div></div>'
            : '<div class="personal-assets-empty"><strong>' + esc(tr('personal_assets_empty', 'No personal information yet')) + '</strong><p>' + esc(tr('personal_assets_empty_hint', 'Add information here or manually invoke the onboarding Skill.')) + '</p></div>';

        return '<div class="personal-assets-toolbar"><div class="personal-assets-overview-copy"><h3>' + esc(tr('personal_assets_overview', 'Profile overview')) +
            '</h3><p>' + esc(tr('personal_assets_description', 'Information Agents may request when relevant to a task.')) + '</p></div>' +
            '<div class="personal-assets-overview-meta"><span class="personal-assets-total-count">' + esc(String(state.entries.length) + ' ' + tr('personal_assets_items', 'items')) + '</span>' +
            '<span class="personal-assets-availability-chip is-' + esc(state.availability.status) + '">' + esc(availabilityStatusLabel()) + '</span></div>' +
            '<div class="personal-assets-actions"><button type="button" data-view="suggestions">' + esc(tr('personal_assets_suggestions', 'Suggestions')) + ' <span class="personal-assets-count">' + activeSuggestions().length + '</span></button>' +
            '<button type="button" class="is-primary" data-view="editor">' + esc(tr('personal_assets_add', 'Add information')) + '</button></div></div>' +
            statusMessage() + workspace + renderSyncPanel();
    }

    function renderEditor() {
        // 敏感值只存在于当前草稿与受控表单，不进入 toast、日志或额外展示副本。
        const current = state.entries.find(item => item.id === state.selectedEntryId) ||
            (state.editorDraft && state.editorDraft.proposal) || {};
        return '<div class="personal-assets-subhead"><button type="button" class="personal-assets-back" data-view="overview">← ' + esc(tr('personal_assets_back', 'Back')) +
            '</button><div><h3>' + esc(current.id ? tr('personal_assets_edit', 'Edit information') : tr('personal_assets_add', 'Add information')) +
            '</h3><p>' + esc(tr('personal_assets_editor_hint', 'Sensitivity controls whether Agent reads require HUMAN DECISIONS.')) + '</p></div></div>' +
            statusMessage() + '<form id="personal-assets-editor" class="personal-assets-form">' +
            '<label><span>' + esc(tr('personal_assets_category', 'Category')) + '</span><input name="category" maxlength="80" required value="' + esc(current.category || '') + '"></label>' +
            '<label><span>' + esc(tr('personal_assets_label', 'Label')) + '</span><input name="label" maxlength="160" required value="' + esc(current.label || '') + '"></label>' +
            '<label class="is-wide"><span>' + esc(tr('personal_assets_value', 'Value')) + '</span><textarea name="value" rows="8" required>' + esc(valueText(current.value)) + '</textarea></label>' +
            '<label><span>' + esc(tr('personal_assets_classification', 'Classification')) + '</span><select name="sensitivity">' +
            '<option value="standard"' + (current.sensitivity !== 'sensitive' ? ' selected' : '') + '>' + esc(tr('personal_assets_standard', 'Standard')) + '</option>' +
            '<option value="sensitive"' + (current.sensitivity === 'sensitive' ? ' selected' : '') + '>' + esc(tr('personal_assets_sensitive', 'Sensitive')) + '</option></select></label>' +
            '<div class="personal-assets-form-actions is-wide">' + (current.id ? '<button type="button" class="is-danger" data-delete-id="' + esc(current.id) + '">' + esc(tr('personal_assets_delete', 'Delete')) + '</button>' : '<span></span>') +
            '<button type="submit" class="is-primary"' + (state.busyAction ? ' disabled' : '') + '>' + esc(tr('personal_assets_save', 'Save')) + '</button></div></form>';
    }

    function renderSuggestions() {
        const pending = activeSuggestions();
        const rows = pending.map(item => {
            const proposal = item.proposal || {};
            return '<article class="personal-assets-suggestion"><div><span class="personal-assets-category">' + esc(proposal.category || '') + '</span><h3>' +
                esc(proposal.label || '') + '</h3><pre>' + esc(valueText(proposal.value)) + '</pre></div><div class="personal-assets-actions">' +
                '<button type="button" data-reject-id="' + esc(item.id) + '">' + esc(tr('personal_assets_reject', 'Reject')) + '</button>' +
                '<button type="button" data-edit-suggestion="' + esc(item.id) + '">' + esc(tr('personal_assets_edit_accept', 'Edit')) + '</button>' +
                '<button type="button" class="is-primary" data-accept-id="' + esc(item.id) + '">' + esc(tr('personal_assets_accept', 'Accept')) + '</button></div></article>';
        }).join('');
        return '<div class="personal-assets-subhead"><button type="button" class="personal-assets-back" data-view="overview">← ' + esc(tr('personal_assets_back', 'Back')) +
            '</button><div><h3>' + esc(tr('personal_assets_suggestions', 'Suggestions')) + '</h3><p>' + esc(tr('personal_assets_suggestions_hint', 'Suggestions never change your profile until you accept them.')) +
            '</p></div></div>' + statusMessage() + (rows || '<div class="personal-assets-empty">' + esc(tr('personal_assets_no_suggestions', 'No pending suggestions')) + '</div>');
    }

    function render() {
        const host = content();
        if (!host) return;
        if (state.loading) {
            host.textContent = tr('personal_assets_loading', 'Loading personal assets…');
            return;
        }
        host.innerHTML = state.view === 'editor' ? renderEditor() : state.view === 'suggestions' ? renderSuggestions() : renderOverview();
    }

    function syncNeedsPolling() {
        return ['pending', 'syncing', 'restoring', 'failed'].includes(state.sync.status);
    }

    function clearSyncPoll() {
        if (state.syncPollTimer) root.clearTimeout(state.syncPollTimer);
        state.syncPollTimer = null;
    }

    function scheduleSyncPoll() {
        clearSyncPoll();
        if (!state.open || !syncNeedsPolling()) return;
        state.syncPollTimer = root.setTimeout(() => {
            state.syncPollTimer = null;
            loadSnapshot({ quiet: true }).catch(() => {});
        }, 1500);
    }

    async function loadSnapshot(options) {
        const quiet = Boolean(options && options.quiet);
        if (!quiet) { state.loading = true; state.error = ''; render(); }
        try {
            const data = await managementJson('/api/personal-assets');
            setProfile(data.profile); setSync(data.sync); state.loading = false; render(); scheduleSyncPoll();
        } catch (error) {
            state.loading = false;
            if (!quiet) state.error = String(error.message || error);
            render(); scheduleSyncPoll();
        }
    }

    async function refreshAvailability() {
        setAvailability({ status: 'checking' });
        render();
        try {
            const data = await managementJson('/api/personal-assets/sync/availability');
            setAvailability(data.availability);
        } catch (_error) {
            setAvailability({ status: 'unavailable', code: 'oss_runtime_unavailable' });
        }
        render();
        return state.availability;
    }

    async function post(path, body) {
        state.busyAction = path; state.error = ''; state.notice = ''; render();
        try {
            const result = await managementJson(path, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
            if (result.profile) setProfile(result.profile);
            if (result.sync) setSync(result.sync);
            state.busyAction = ''; state.notice = tr('personal_assets_saved', 'Saved'); return result;
        } catch (error) {
            state.busyAction = ''; state.error = String(error.message || error);
            if (state.error === 'personal_asset_revision_conflict') await loadSnapshot();
            throw error;
        } finally { render(); scheduleSyncPoll(); }
    }

    async function syncCommand(path, body) {
        state.busyAction = path; state.error = ''; render();
        try {
            const result = await managementJson(path, {
                method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body || {}),
            });
            setSync(result.sync); state.busyAction = ''; render(); scheduleSyncPoll(); return result;
        } catch (error) {
            state.busyAction = ''; state.error = String(error.message || error); render(); throw error;
        }
    }

    function setSyncEnabled(enabled) {
        return syncCommand('/api/personal-assets/sync/preferences', { enabled: Boolean(enabled) });
    }

    function queueSync() {
        return syncCommand('/api/personal-assets/sync/now', {});
    }

    async function resolveSyncConflict(resolution) {
        if (!root.VODialogs || typeof root.VODialogs.showConfirm !== 'function') return;
        const message = resolution === 'local'
            ? tr('personal_assets_keep_local_confirm', 'Keep local data and replace the cloud snapshot?')
            : tr('personal_assets_use_cloud_confirm', 'Replace local data with the cloud snapshot?');
        if (!await root.VODialogs.showConfirm(message)) return;
        await syncCommand('/api/personal-assets/sync/conflict', { resolution });
    }

    function parseEditorValue(raw) {
        const text = String(raw || '').trim();
        if (!text) return '';
        try { return JSON.parse(text); } catch (_error) { return text; }
    }

    async function saveEditor(form) {
        const data = new FormData(form);
        const entry = { category: data.get('category'), label: data.get('label'), value: parseEditorValue(data.get('value')), sensitivity: data.get('sensitivity') };
        if (state.editorDraft) {
            await resolveSuggestion(state.editorDraft.id, 'accept', entry);
        } else if (state.selectedEntryId) {
            await post('/api/personal-assets/entries/' + encodeURIComponent(state.selectedEntryId), { operation: 'update', expectedRevision: state.revision, patch: entry });
        } else {
            await post('/api/personal-assets/entries', { expectedRevision: state.revision, entry });
        }
        state.view = 'overview'; state.selectedEntryId = ''; state.editorDraft = null; render();
    }

    async function deleteEntry(id) {
        if (!root.VODialogs || typeof root.VODialogs.showConfirm !== 'function') return;
        const accepted = await root.VODialogs.showConfirm(tr('personal_assets_delete_confirm', 'Delete this information?'));
        if (!accepted) return;
        await post('/api/personal-assets/entries/' + encodeURIComponent(id), { operation: 'delete', expectedRevision: state.revision });
        state.view = 'overview'; state.selectedEntryId = ''; render();
    }

    async function resolveSuggestion(id, action, editedProposal) {
        await post('/api/personal-assets/suggestions/' + encodeURIComponent(id) + '/' + action, { expectedRevision: state.revision, editedProposal: editedProposal || undefined });
        state.view = 'suggestions'; render();
    }

    function handleClick(event) {
        const target = event.target.closest('button');
        if (!target) return;
        if (target.dataset.categoryId) { state.selectedCategory = target.dataset.categoryId; render(); return; }
        if (target.dataset.syncToggle) { setSyncEnabled(target.dataset.syncToggle === 'true').catch(() => {}); return; }
        if (target.hasAttribute('data-sync-now')) { queueSync().catch(() => {}); return; }
        if (target.dataset.syncResolution) { resolveSyncConflict(target.dataset.syncResolution).catch(() => {}); return; }
        if (target.dataset.view) { state.view = target.dataset.view; state.selectedEntryId = ''; state.editorDraft = null; state.error = ''; render(); return; }
        if (target.dataset.editId) { state.selectedEntryId = target.dataset.editId; state.editorDraft = null; state.view = 'editor'; render(); return; }
        if (target.dataset.deleteId) { deleteEntry(target.dataset.deleteId).catch(() => {}); return; }
        if (target.dataset.acceptId) { resolveSuggestion(target.dataset.acceptId, 'accept').catch(() => {}); return; }
        if (target.dataset.rejectId) { resolveSuggestion(target.dataset.rejectId, 'reject').catch(() => {}); return; }
        if (target.dataset.editSuggestion) {
            const suggestion = state.suggestions.find(item => item.id === target.dataset.editSuggestion);
            state.editorDraft = suggestion || null;
            state.selectedEntryId = '';
            state.view = 'editor';
            render();
        }
    }

    function handleSubmit(event) {
        if (event.target && event.target.id === 'personal-assets-editor') {
            event.preventDefault(); saveEditor(event.target).catch(() => {});
        }
    }

    root.openPersonalAssets = function () {
        const host = modal(); if (!host) return;
        state.returnFocus = document.activeElement;
        state.open = true; state.view = 'overview'; host.classList.remove('hidden');
        const button = toggle();
        if (button) { button.classList.add('is-active'); button.setAttribute('aria-current', 'page'); }
        loadSnapshot();
        refreshAvailability();
    };

    root.closePersonalAssets = function () {
        const host = modal(); if (host) host.classList.add('hidden');
        const button = toggle();
        if (button) { button.classList.remove('is-active'); button.removeAttribute('aria-current'); }
        state.open = false;
        clearSyncPoll();
        if (state.returnFocus && typeof state.returnFocus.focus === 'function') state.returnFocus.focus();
    };

    document.addEventListener('click', handleClick);
    document.addEventListener('submit', handleSubmit);
    root.addEventListener('i18n:ready', render);
    root.addEventListener('i18n:changed', render);
    root.PersonalAssets = { state, loadSnapshot, refreshAvailability, render, resolveSuggestion, queueSync, setSyncEnabled, resolveSyncConflict };
})(window);
