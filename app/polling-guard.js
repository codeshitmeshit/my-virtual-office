(function () {
    'use strict';

    var inFlight = Object.create(null);

    function timeoutSignal(timeoutMs) {
        var controller = new AbortController();
        var timer = setTimeout(function () {
            try { controller.abort(); } catch (_) {}
        }, Math.max(1000, timeoutMs || 8000));
        return {
            signal: controller.signal,
            cleanup: function () { clearTimeout(timer); },
        };
    }

    window.voFetchJsonOnce = async function (key, url, options) {
        options = options || {};
        key = String(key || url || '');
        if (!key || inFlight[key]) return null;
        inFlight[key] = true;
        var timeout = timeoutSignal(options.timeoutMs || 8000);
        try {
            var fetchOptions = Object.assign({}, options.fetchOptions || {}, { signal: timeout.signal });
            var res = await fetch(url, fetchOptions);
            if (!res.ok) return null;
            return await res.json();
        } catch (_) {
            return null;
        } finally {
            timeout.cleanup();
            delete inFlight[key];
        }
    };
})();
