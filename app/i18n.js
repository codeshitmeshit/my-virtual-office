/**
 * Lightweight i18n engine for My Virtual Office
 * - t(key, params) — translate a key, optional {{param}} interpolation
 * - setLanguage(lang) — switch language, persist to localStorage
 * - initLanguage() — called on page load, reads preference or falls back to browser language
 * - scan DOM for data-i18n and data-i18n-* attributes and apply translations
 */
(function () {
    'use strict';

    var STORAGE_KEY = 'vo-i18n-lang';
    var DEFAULT_LANG = 'en';
    var currentLang = DEFAULT_LANG;
    var locales = {};
    var initialized = false;

    /**
     * Load locale JSON from inline data or fetch.
     * Pages should include <script id="locale-en" type="application/json">{...}</script>
     */
    function loadLocale(lang, callback) {
        if (locales[lang]) {
            callback(null, locales[lang]);
            return;
        }
        // Try inline script tag first
        var el = document.getElementById('locale-' + lang);
        if (el) {
            try {
                var inlineLocale = JSON.parse(el.textContent);
                if (inlineLocale && Object.keys(inlineLocale).length > 0) {
                    locales[lang] = inlineLocale;
                    callback(null, locales[lang]);
                    return;
                }
            } catch (e) {
                // Fall through to the locale file when inline data is not ready.
            }
        }
        // Fallback: fetch from locales/ directory
        var script = document.querySelector('script[src$="i18n.js"]');
        var base = script && script.src ? script.src : window.location.href;
        var version = (window.APP_VERSION || document.querySelector('meta[name="app-version"]')?.content || Date.now());
        var url = new URL('locales/' + lang + '.json?v=' + encodeURIComponent(version), base).toString();
        fetch(url, { cache: 'no-store' }).then(function (r) {
            if (!r.ok) throw new Error('Failed to load ' + url);
            return r.json();
        }).then(function (data) {
            locales[lang] = data;
            callback(null, data);
        }).catch(function (e) {
            callback(e, null);
        });
    }

    /**
     * Detect browser language, return 'zh' if contains 'zh', else 'en'.
     */
    function detectBrowserLang() {
        var nav = navigator.language || navigator.userLanguage || '';
        return nav.toLowerCase().indexOf('zh') >= 0 ? 'zh' : DEFAULT_LANG;
    }

    /**
     * Initialize language on page load.
     */
    function initLanguage() {
        if (initialized) return;
        initialized = true;

        // Read stored preference
        try {
            var stored = localStorage.getItem(STORAGE_KEY);
            if (stored === 'zh' || stored === 'en') {
                currentLang = stored;
            } else {
                currentLang = detectBrowserLang();
            }
        } catch (e) {
            currentLang = detectBrowserLang();
        }

        // Load locale and apply
        loadLocale(currentLang, function (err) {
            if (err) {
                console.warn('[i18n] Failed to load locale:', err);
                if (currentLang !== DEFAULT_LANG) {
                    currentLang = DEFAULT_LANG;
                    document.documentElement.lang = DEFAULT_LANG;
                    loadLocale(DEFAULT_LANG, function (fallbackErr) {
                        if (fallbackErr) {
                            console.warn('[i18n] Failed to load fallback locale:', fallbackErr);
                            return;
                        }
                        applyTranslations();
                        window.dispatchEvent(new CustomEvent('i18n:ready', { detail: { lang: currentLang, fallback: true } }));
                    });
                }
                return;
            }
            applyTranslations();
            // Update HTML lang attribute
            document.documentElement.lang = currentLang;
            // Dispatch event for components that need to react
            window.dispatchEvent(new CustomEvent('i18n:ready', { detail: { lang: currentLang } }));
        });

        // Also preload English as fallback
        if (currentLang !== 'en') {
            loadLocale('en', function () {});
        }
    }

    /**
     * Translate a key. Falls back to English, then to the key itself.
     * Supports {{param}} interpolation via optional params object.
     */
    function t(key, params) {
        var msg = '';
        if (locales[currentLang] && locales[currentLang][key]) {
            msg = locales[currentLang][key];
        } else if (locales['en'] && locales['en'][key]) {
            msg = locales['en'][key];
        } else {
            // Fallback: return key as-is (for debugging)
            return key;
        }
        // Interpolate {{param}}
        if (params) {
            Object.keys(params).forEach(function (k) {
                msg = msg.replace(new RegExp('\\{\\{' + k + '\\}\\}', 'g'), params[k]);
            });
        }
        return msg;
    }

    /**
     * Switch to a language. Persists to localStorage, reapplies translations.
     */
    function setLanguage(lang) {
        if (lang !== 'zh' && lang !== 'en') return;
        currentLang = lang;
        try {
            localStorage.setItem(STORAGE_KEY, lang);
        } catch (e) {}
        document.documentElement.lang = lang;

        // Load locale if not cached
        if (!locales[lang]) {
            loadLocale(lang, function (err) {
                if (err) return;
                applyTranslations();
                window.dispatchEvent(new CustomEvent('i18n:changed', { detail: { lang: lang } }));
            });
        } else {
            applyTranslations();
            window.dispatchEvent(new CustomEvent('i18n:changed', { detail: { lang: lang } }));
        }
    }

    /**
     * Get current language code.
     */
    function getLanguage() {
        return currentLang;
    }

    /**
     * Scan DOM for data-i18n attributes and apply translations.
     * - data-i18n="key" — replaces textContent
     * - data-i18n-title="key" — replaces title attribute
     * - data-i18n-placeholder="key" — replaces placeholder attribute
     * - data-i18n-aria-label="key" — replaces aria-label attribute
     * - data-i18n-html="key" — replaces innerHTML
     */
    function applyTranslations() {
        // data-i18n: text content
        var els = document.querySelectorAll('[data-i18n]');
        for (var i = 0; i < els.length; i++) {
            var key = els[i].getAttribute('data-i18n');
            els[i].textContent = t(key);
        }
        // data-i18n-html: innerHTML
        els = document.querySelectorAll('[data-i18n-html]');
        for (var i = 0; i < els.length; i++) {
            var key = els[i].getAttribute('data-i18n-html');
            els[i].innerHTML = t(key);
        }
        // data-i18n-title: title attribute
        els = document.querySelectorAll('[data-i18n-title]');
        for (var i = 0; i < els.length; i++) {
            var key = els[i].getAttribute('data-i18n-title');
            els[i].setAttribute('title', t(key));
        }
        // data-i18n-placeholder: placeholder attribute
        els = document.querySelectorAll('[data-i18n-placeholder]');
        for (var i = 0; i < els.length; i++) {
            var key = els[i].getAttribute('data-i18n-placeholder');
            els[i].setAttribute('placeholder', t(key));
        }

        // data-i18n-aria-label: aria-label attribute
        els = document.querySelectorAll('[data-i18n-aria-label]');
        for (i = 0; i < els.length; i++) {
            var key = els[i].getAttribute('data-i18n-aria-label');
            els[i].setAttribute('aria-label', t(key));
        }
    }

    var managementTokenPromptPromise = null;

    function requestManagementToken() {
        if (managementTokenPromptPromise) return managementTokenPromptPromise;

        managementTokenPromptPromise = new Promise(function (resolve) {
            var existing = document.getElementById('management-token-dialog');
            if (existing) existing.remove();

            var previouslyFocused = document.activeElement;
            var modal = document.createElement('div');
            modal.id = 'management-token-dialog';
            modal.className = 'modal management-token-dialog';
            modal.setAttribute('role', 'presentation');

            var content = document.createElement('section');
            content.className = 'modal-content management-token-modal';
            content.setAttribute('role', 'dialog');
            content.setAttribute('aria-modal', 'true');
            content.setAttribute('aria-labelledby', 'management-token-title');

            var header = document.createElement('div');
            header.className = 'modal-header';
            var emoji = document.createElement('span');
            emoji.className = 'modal-emoji';
            emoji.textContent = '🔐';
            var title = document.createElement('h2');
            title.id = 'management-token-title';
            title.textContent = t('management_token_title');
            var close = document.createElement('button');
            close.type = 'button';
            close.className = 'close-btn management-token-close';
            close.setAttribute('aria-label', t('management_token_cancel'));
            close.textContent = '×';
            close.setAttribute('data-management-token-cancel', '');
            header.appendChild(emoji);
            header.appendChild(title);
            header.appendChild(close);

            var body = document.createElement('div');
            body.className = 'management-token-body';
            var help = document.createElement('p');
            help.className = 'management-token-help';
            help.textContent = t('management_token_prompt');
            var label = document.createElement('label');
            label.className = 'management-token-label';
            label.setAttribute('for', 'management-token-input');
            label.textContent = t('management_token_title');
            var input = document.createElement('input');
            input.id = 'management-token-input';
            input.className = 'management-token-input';
            input.type = 'password';
            input.autocomplete = 'current-password';
            input.placeholder = t('management_token_placeholder');
            body.appendChild(help);
            body.appendChild(label);
            body.appendChild(input);

            var controls = document.createElement('div');
            controls.className = 'modal-controls management-token-actions';
            var cancel = document.createElement('button');
            cancel.type = 'button';
            cancel.className = 'mtg-btn';
            cancel.textContent = t('management_token_cancel');
            cancel.setAttribute('data-management-token-cancel', '');
            var confirm = document.createElement('button');
            confirm.type = 'button';
            confirm.className = 'mtg-btn mtg-btn-end';
            confirm.textContent = t('management_token_confirm');
            confirm.setAttribute('data-management-token-confirm', '');
            confirm.disabled = true;
            controls.appendChild(cancel);
            controls.appendChild(confirm);

            content.appendChild(header);
            content.appendChild(body);
            content.appendChild(controls);
            modal.appendChild(content);

            var settled = false;
            function finish(value) {
                if (settled) return;
                settled = true;
                document.removeEventListener('keydown', onKeydown, true);
                modal.remove();
                if (previouslyFocused && typeof previouslyFocused.focus === 'function') previouslyFocused.focus();
                resolve(value);
            }
            function submit() {
                var value = input.value.trim();
                if (value) finish(value);
            }
            function onKeydown(event) {
                if (event.key === 'Escape') {
                    event.preventDefault();
                    finish('');
                } else if (event.key === 'Enter') {
                    event.preventDefault();
                    submit();
                }
            }

            input.addEventListener('input', function () {
                confirm.disabled = !input.value.trim();
            });
            modal.addEventListener('click', function (event) {
                if (event.target === modal || event.target.closest('[data-management-token-cancel]')) finish('');
                if (event.target.closest('[data-management-token-confirm]')) submit();
            });
            document.addEventListener('keydown', onKeydown, true);
            document.body.appendChild(modal);
            input.focus();
        });
        managementTokenPromptPromise.then(
            function () { managementTokenPromptPromise = null; },
            function () { managementTokenPromptPromise = null; }
        );
        return managementTokenPromptPromise;
    }

    async function managementFetch(input, init) {
        init = Object.assign({}, init || {});
        init.headers = new Headers(init.headers || {});
        var token = sessionStorage.getItem('voManagementToken') || '';
        if (token) init.headers.set('X-VO-Management-Token', token);
        var response = await fetch(input, init);
        if (!(await isManagementTokenChallenge(response))) return response;
        token = await requestManagementToken();
        if (!token) throw new Error(t('management_token_required'));
        sessionStorage.setItem('voManagementToken', token);
        init.headers.set('X-VO-Management-Token', token);
        response = await fetch(input, init);
        if (await isManagementTokenChallenge(response)) {
            sessionStorage.removeItem('voManagementToken');
            throw new Error(t('management_token_invalid'));
        }
        return response;
    }

    async function isManagementTokenChallenge(response) {
        if (!response || response.status !== 403) return false;
        try {
            var payload = await response.clone().json();
            return payload && payload.code === 'management_token_required';
        } catch (_) {
            return false;
        }
    }

    // Auto-init on DOMContentLoaded
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', initLanguage);
    } else {
        initLanguage();
    }

    // Expose API
    window.i18n = {
        t: t,
        setLanguage: setLanguage,
        getLanguage: getLanguage,
        initLanguage: initLanguage,
        applyTranslations: applyTranslations,
        requestManagementToken: requestManagementToken,
        managementFetch: managementFetch
    };
})();
