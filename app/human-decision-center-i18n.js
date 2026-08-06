(function (root, factory) {
    if (typeof module === 'object' && module.exports) module.exports = factory();
    else root.HumanDecisionI18n = factory();
})(typeof globalThis !== 'undefined' ? globalThis : this, function () {
    'use strict';

    function interpolate(value, params) {
        var result = String(value == null ? '' : value);
        Object.keys(params || {}).forEach(function (key) {
            result = result.replace(new RegExp('\\{\\{' + key + '\\}\\}', 'g'), String(params[key]));
        });
        return result;
    }

    function create(root) {
        var host = root || {};
        return {
            t: function (key, params, fallback) {
                var api = host.i18n;
                if (api && typeof api.t === 'function') {
                    var translated = api.t(key, params || {});
                    if (translated && translated !== key) return translated;
                }
                return interpolate(fallback == null ? key : fallback, params);
            },
            locale: function () {
                var api = host.i18n;
                return api && typeof api.getLanguage === 'function' && api.getLanguage() === 'zh' ? 'zh-CN' : 'en-US';
            },
            subscribe: function (listener) {
                if (typeof host.addEventListener !== 'function') return function () {};
                host.addEventListener('i18n:ready', listener);
                host.addEventListener('i18n:changed', listener);
                return function () {
                    if (typeof host.removeEventListener === 'function') {
                        host.removeEventListener('i18n:ready', listener);
                        host.removeEventListener('i18n:changed', listener);
                    }
                };
            },
        };
    }

    return { create: create };
});
