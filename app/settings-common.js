(function() {
    'use strict';

    var DEFAULT_BROWSER_CDP_URL = 'http://127.0.0.1:9224';
    var DEFAULT_BROWSER_VIEWER_URL = 'https://localhost:6901';

    function escapeHtml(value) {
        return String(value == null ? '' : value).replace(/[&<>"']/g, function(ch) {
            return ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'})[ch];
        });
    }

    function isMaskedSecretValue(value) {
        return String(value || '').indexOf('••••') >= 0;
    }

    function buildWeatherLocation(city, state) {
        city = (city || '').trim();
        state = (state || '').trim();
        if (!city) return null;
        return state ? city.replace(/ /g, '+') + ',' + state.replace(/ /g, '+') : city.replace(/ /g, '+');
    }

    function fetchJson(url, options) {
        return fetch(url, options).then(function(response) {
            return response.json().then(function(data) {
                data._httpOk = response.ok;
                data._status = response.status;
                return data;
            });
        });
    }

    window.VOSettingsCommon = {
        DEFAULT_BROWSER_CDP_URL: DEFAULT_BROWSER_CDP_URL,
        DEFAULT_BROWSER_VIEWER_URL: DEFAULT_BROWSER_VIEWER_URL,
        escapeHtml: escapeHtml,
        isMaskedSecretValue: isMaskedSecretValue,
        buildWeatherLocation: buildWeatherLocation,
        fetchJson: fetchJson
    };
})();
