(function () {
    'use strict';

    var GET_PATH = '/api/settings/oss';
    var ACTIVATE_PATH = '/api/settings/oss/test-and-activate';
    var state = { loaded: false, configured: false, pending: false };

    function t(key) {
        return window.i18n && typeof window.i18n.t === 'function' ? window.i18n.t(key) : key;
    }

    function field(id) {
        return document.getElementById(id);
    }

    function renderStatus(kind, message) {
        var status = field('oss-settings-status');
        if (!status) return;
        if (!message) {
            status.textContent = '';
            status.className = '';
            status.hidden = true;
            return;
        }
        status.hidden = false;
        status.className = 'mm-status ' + (kind || 'info');
        // 后端只返回安全错误；仍使用 textContent，避免错误文本成为 HTML 注入入口。
        status.textContent = message || '';
    }

    function ensureOssSettingsSection() {
        var existing = field('oss-settings-section');
        if (existing) return existing;
        var host = document.querySelector('#main-menu-panel .main-menu-body');
        if (!host) return null;
        var section = document.createElement('div');
        section.id = 'oss-settings-section';
        section.className = 'mm-section';
        section.innerHTML = [
            '<div class="mm-section-title" data-i18n="oss_settings_title">Alibaba Cloud OSS</div>',
            '<label class="mm-label" for="oss-endpoint"><span data-i18n="oss_endpoint">Endpoint</span></label>',
            '<input class="mm-input" id="oss-endpoint" type="url" autocomplete="off">',
            '<label class="mm-label" for="oss-bucket"><span data-i18n="oss_bucket">Bucket</span></label>',
            '<input class="mm-input" id="oss-bucket" type="text" autocomplete="off">',
            '<label class="mm-label" for="oss-access-key-id"><span data-i18n="oss_access_key_id">AccessKey ID</span></label>',
            '<input class="mm-input" id="oss-access-key-id" type="text" autocomplete="off">',
            '<label class="mm-label" for="oss-access-key-secret"><span data-i18n="oss_access_key_secret">AccessKey Secret</span></label>',
            '<input class="mm-input" id="oss-access-key-secret" type="password" autocomplete="new-password">',
            '<div class="mm-help"><span id="oss-secret-state"></span></div>',
            '<button class="mm-btn mm-btn-primary" id="oss-settings-submit" type="button" data-i18n="oss_test_and_activate">Test and activate</button>',
            '<div class="mm-status info" id="oss-settings-status" hidden></div>'
        ].join('');
        var saveButton = host.querySelector('.mm-save-all');
        // OSS 是现有设置的一部分，应位于页面级保存动作之前并沿用相邻 section 间距。
        if (saveButton) host.insertBefore(section, saveButton);
        else host.appendChild(section);
        var submit = field('oss-settings-submit');
        if (submit) submit.addEventListener('click', function () { testAndActivateOssSettings(); });
        if (window.i18n && typeof window.i18n.applyTranslations === 'function') {
            window.i18n.applyTranslations();
        }
        return section;
    }

    function renderSafeState(settings) {
        settings = settings || {};
        var endpoint = field('oss-endpoint');
        var bucket = field('oss-bucket');
        var accessKeyId = field('oss-access-key-id');
        var secret = field('oss-access-key-secret');
        if (endpoint) endpoint.value = settings.endpoint || '';
        if (bucket) bucket.value = settings.bucket || '';
        if (accessKeyId) accessKeyId.value = settings.accessKeyId || '';
        // API 只给 secretConfigured；密码框永远不回填持久化 secret。
        if (secret) secret.value = '';
        state.configured = settings.configured === true && settings.secretConfigured === true;
        var secretState = field('oss-secret-state');
        if (secretState) secretState.textContent = state.configured ? t('oss_secret_configured') : '';
    }

    async function safePayload(response) {
        try {
            return await response.json();
        } catch (_) {
            return { ok: false, error: t('oss_settings_failed') };
        }
    }

    function payloadError(payload, fallbackKey) {
        var localizedCodes = {
            oss_endpoint_invalid: true,
            oss_region_unresolved: true,
            oss_bucket_invalid: true,
            oss_access_key_id_invalid: true,
            oss_access_key_secret_invalid: true
        };
        if (payload && localizedCodes[payload.code]) return t(payload.code);
        return (payload && payload.error) || t(fallbackKey || 'oss_settings_failed');
    }

    async function loadOssSettings() {
        if (state.loaded || state.pending) return;
        state.pending = true;
        renderStatus('info', t('oss_loading'));
        try {
            var response = await window.i18n.managementFetch(GET_PATH);
            var payload = await safePayload(response);
            if (!response.ok || !payload.ok) throw new Error(payloadError(payload, 'oss_settings_failed'));
            renderSafeState(payload.settings);
            state.loaded = true;
            renderStatus('info', state.configured ? t('oss_secret_configured') : '');
        } catch (error) {
            renderStatus('err', (error && error.message) || t('oss_settings_failed'));
        } finally {
            state.pending = false;
        }
    }

    function value(id) {
        var element = field(id);
        return element ? String(element.value || '').trim() : '';
    }

    async function testAndActivateOssSettings() {
        if (state.pending) return;
        var secretInput = field('oss-access-key-secret');
        var secret = value('oss-access-key-secret');
        var candidate = {
            endpoint: value('oss-endpoint'),
            bucket: value('oss-bucket'),
            accessKeyId: value('oss-access-key-id'),
            accessKeySecret: secret
        };
        if (!candidate.endpoint || !candidate.bucket || !candidate.accessKeyId) {
            renderStatus('err', t('oss_fields_required'));
            if (secretInput) secretInput.value = '';
            return;
        }
        if (!state.configured && !secret) {
            renderStatus('err', t('oss_secret_required'));
            return;
        }
        state.pending = true;
        var submit = field('oss-settings-submit');
        if (submit) submit.disabled = true;
        renderStatus('info', t('oss_testing'));
        try {
            var response = await window.i18n.managementFetch(ACTIVATE_PATH, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(candidate)
            });
            var payload = await safePayload(response);
            if (!response.ok || !payload.ok) throw new Error(payloadError(payload, 'oss_settings_failed'));
            renderSafeState(payload.settings);
            state.loaded = true;
            renderStatus('ok', t('oss_activated'));
        } catch (error) {
            renderStatus('err', (error && error.message) || t('oss_settings_failed'));
        } finally {
            // 候选 secret 只活到本次请求结束，不进入模块 state、storage 或 DOM 长期状态。
            candidate.accessKeySecret = '';
            if (secretInput) secretInput.value = '';
            state.pending = false;
            if (submit) submit.disabled = false;
        }
    }

    function observeSettingsPanel() {
        var panel = field('main-menu-panel');
        if (!panel || typeof MutationObserver === 'undefined') return;
        var observer = new MutationObserver(function () {
            if (panel.classList.contains('open')) loadOssSettings();
        });
        observer.observe(panel, { attributes: true, attributeFilter: ['class'] });
        // 延迟读取受保护配置，避免首页加载阶段无缘由地弹出管理令牌框。
        if (panel.classList.contains('open')) loadOssSettings();
    }

    ensureOssSettingsSection();
    observeSettingsPanel();
    window.VOOssSettings = {
        ensureSection: ensureOssSettingsSection,
        load: loadOssSettings,
        testAndActivate: testAndActivateOssSettings
    };
})();
