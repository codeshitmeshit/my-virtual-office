(function(root, factory) {
    var api = factory();
    if (typeof module === 'object' && module.exports) module.exports = api;
    if (root) root.InternalBubbleSettings = api;
})(typeof globalThis !== 'undefined' ? globalThis : this, function() {
    'use strict';

    function normalizeTimeoutSec(value) {
        if (typeof value === 'string' && value.trim() === '') return 60;
        var parsed = Number(value);
        if (!Number.isFinite(parsed) || parsed < 0) return 60;
        return Math.floor(parsed);
    }

    function shouldAutoCollapse(updatedAt, timeoutSec, now) {
        var timeout = normalizeTimeoutSec(timeoutSec);
        var updated = Number(updatedAt);
        var current = now == null ? Date.now() : Number(now);
        if (timeout === 0 || !Number.isFinite(updated) || updated <= 0 || !Number.isFinite(current)) return false;
        return current - updated >= timeout * 1000;
    }

    return {
        normalizeTimeoutSec: normalizeTimeoutSec,
        shouldAutoCollapse: shouldAutoCollapse
    };
});
