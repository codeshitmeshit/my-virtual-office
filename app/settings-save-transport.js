(function initSettingsSaveTransport(global) {
    'use strict';

    var DEFAULT_TIMEOUT_MS = 15000;

    function endpointFor(locationRef) {
        var location = locationRef || {};
        var protocol = String(location.protocol || '');
        var hostname = String(location.hostname || '').toLowerCase();
        var port = String(location.port || '');
        if (protocol === 'http:' && (hostname === '127.0.0.1' || hostname === 'localhost')) {
            // The office keeps several long-lived HTTP/1.x event streams open.
            // A dedicated loopback origin prevents those streams from starving
            // the user-initiated settings mutation in the browser connection pool.
            return 'http://0.0.0.0' + (port ? ':' + port : '') + '/setup/save';
        }
        return '/setup/save';
    }

    function request(payload, fetcher, options) {
        if (typeof fetcher !== 'function') return Promise.reject(new Error('Settings save transport is unavailable'));
        var opts = options || {};
        var timeoutMs = Number(opts.timeoutMs || DEFAULT_TIMEOUT_MS);
        var AbortControllerRef = global && global.AbortController;
        var controller = typeof AbortControllerRef === 'function' ? new AbortControllerRef() : null;
        var endpoint = endpointFor(opts.location || (global && global.location));
        var timer = null;
        var timeout = new Promise(function(_, reject) {
            timer = setTimeout(function() {
                if (controller) controller.abort();
                reject(new Error('Settings save timed out'));
            }, timeoutMs);
        });
        var requestPromise = Promise.resolve().then(function() {
            return fetcher(endpoint, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload || {}),
                signal: controller ? controller.signal : undefined,
            });
        });
        return Promise.race([requestPromise, timeout]).finally(function() {
            if (timer) clearTimeout(timer);
        });
    }

    var api = { endpointFor: endpointFor, request: request };
    if (global) global.VOSettingsSaveTransport = api;
    if (typeof module !== 'undefined' && module.exports) module.exports = api;
})(typeof window !== 'undefined' ? window : globalThis);
