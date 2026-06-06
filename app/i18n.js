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
                locales[lang] = JSON.parse(el.textContent);
                callback(null, locales[lang]);
            } catch (e) {
                callback(e, null);
            }
            return;
        }
        // Fallback: fetch from locales/ directory
        var url = 'locales/' + lang + '.json';
        fetch(url).then(function (r) {
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
        initLanguage: initLanguage
    };
})();
