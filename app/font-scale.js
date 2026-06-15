(function(root, factory) {
    var api = factory(root);
    if (typeof module === 'object' && module.exports) module.exports = api;
    if (root) root.VOFontScale = api;
})(typeof globalThis !== 'undefined' ? globalThis : this, function(root) {
    'use strict';

    var STORAGE_KEY = 'vo-display-prefs';
    var DEFAULT_SCALE = 1;
    var ALLOWED_SCALES = [1, 1.1, 1.2, 1.3, 1.5];
    var DATA_ATTR = 'data-vo-base-font-size';
    var dynamicObserver = null;
    var observedRoot = null;

    function normalizeFontScale(value) {
        var parsed = Number(value);
        if (!Number.isFinite(parsed)) return DEFAULT_SCALE;
        var rounded = Math.round(parsed * 10) / 10;
        for (var i = 0; i < ALLOWED_SCALES.length; i++) {
            if (Math.abs(ALLOWED_SCALES[i] - rounded) < 0.001) return ALLOWED_SCALES[i];
        }
        return DEFAULT_SCALE;
    }

    function readPrefs(storage) {
        storage = storage || (root && root.localStorage);
        if (!storage) return {};
        try {
            return JSON.parse(storage.getItem(STORAGE_KEY) || '{}') || {};
        } catch (e) {
            return {};
        }
    }

    function writePrefs(prefs, storage) {
        storage = storage || (root && root.localStorage);
        if (!storage) return;
        storage.setItem(STORAGE_KEY, JSON.stringify(prefs || {}));
    }

    function getStoredFontScale(storage) {
        return normalizeFontScale(readPrefs(storage).fontScale);
    }

    function sanitizeStoredFontScale(storage) {
        storage = storage || (root && root.localStorage);
        var prefs = readPrefs(storage);
        var scale = normalizeFontScale(prefs.fontScale);
        if (prefs.fontScale !== undefined && Number(prefs.fontScale) !== scale) {
            prefs.fontScale = scale;
            writePrefs(prefs, storage);
        }
        return scale;
    }

    function setStoredFontScale(value, storage) {
        var prefs = readPrefs(storage);
        prefs.fontScale = normalizeFontScale(value);
        writePrefs(prefs, storage);
        return prefs.fontScale;
    }

    function shouldSkipElement(el) {
        if (!el || !el.tagName) return true;
        var tag = el.tagName.toLowerCase();
        if (tag === 'html' || tag === 'body') return true;
        if (tag === 'canvas' || tag === 'script' || tag === 'style' || tag === 'noscript') return true;
        if (el.closest && el.closest('[data-vo-font-scale-exempt], canvas')) return true;
        return false;
    }

    function rememberBaseFontSize(el, computed) {
        if (!el || !el.dataset || el.dataset.voBaseFontSize) return null;
        computed = computed || (root && root.getComputedStyle ? root.getComputedStyle(el) : null);
        if (!computed) return null;
        var size = parseFloat(computed.fontSize);
        if (!Number.isFinite(size) || size <= 0) return null;
        el.dataset.voBaseFontSize = String(size);
        return size;
    }

    function scaleElement(el, scale) {
        if (shouldSkipElement(el)) return;
        var computed = root && root.getComputedStyle ? root.getComputedStyle(el) : null;
        var base = el.dataset ? parseFloat(el.dataset.voBaseFontSize || '') : NaN;
        if (!Number.isFinite(base)) base = rememberBaseFontSize(el, computed);
        if (!Number.isFinite(base) || base <= 0) return;
        el.style.fontSize = (Math.round(base * scale * 1000) / 1000) + 'px';
    }

    function applyFontScale(value, options) {
        if (!root || !root.document) return normalizeFontScale(value);
        var scale = normalizeFontScale(value);
        var doc = root.document;
        doc.documentElement.style.setProperty('--vo-font-scale', String(scale));
        doc.documentElement.dataset.voFontScale = String(scale);
        var scope = options && options.scope ? options.scope : doc.body;
        if (!scope) return scale;
        if (scope.nodeType === 1) scaleElement(scope, scale);
        var nodes = scope.querySelectorAll ? scope.querySelectorAll('*') : [];
        for (var i = 0; i < nodes.length; i++) scaleElement(nodes[i], scale);
        return scale;
    }

    function applyStoredFontScale(storage) {
        return applyFontScale(sanitizeStoredFontScale(storage));
    }

    function observeDynamicFontScale() {
        if (!root || !root.document || !root.MutationObserver) return;
        var body = root.document.body;
        if (!body || observedRoot === body) return;
        if (dynamicObserver) dynamicObserver.disconnect();
        observedRoot = body;
        dynamicObserver = new root.MutationObserver(function(mutations) {
            var scale = normalizeFontScale(root.document.documentElement.dataset.voFontScale || getStoredFontScale());
            mutations.forEach(function(mutation) {
                mutation.addedNodes.forEach(function(node) {
                    if (node.nodeType === 1) applyFontScale(scale, { scope: node });
                });
            });
        });
        dynamicObserver.observe(body, { childList: true, subtree: true });
    }

    function init() {
        if (!root || !root.document) return DEFAULT_SCALE;
        var scale = applyStoredFontScale();
        observeDynamicFontScale();
        return scale;
    }

    if (root && root.document) {
        var early = sanitizeStoredFontScale();
        root.document.documentElement.style.setProperty('--vo-font-scale', String(early));
        root.document.documentElement.dataset.voFontScale = String(early);
        if (root.document.readyState === 'loading') {
            root.document.addEventListener('DOMContentLoaded', init);
        } else {
            setTimeout(init, 0);
        }
    }

    return {
        ALLOWED_SCALES: ALLOWED_SCALES.slice(),
        DEFAULT_SCALE: DEFAULT_SCALE,
        STORAGE_KEY: STORAGE_KEY,
        normalizeFontScale: normalizeFontScale,
        readPrefs: readPrefs,
        writePrefs: writePrefs,
        getStoredFontScale: getStoredFontScale,
        sanitizeStoredFontScale: sanitizeStoredFontScale,
        setStoredFontScale: setStoredFontScale,
        applyFontScale: applyFontScale,
        applyStoredFontScale: applyStoredFontScale,
        observeDynamicFontScale: observeDynamicFontScale,
        init: init
    };
});
