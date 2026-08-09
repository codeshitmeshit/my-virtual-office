(function (global) {
    'use strict';

    var MASK = '••••••••••••';

    function value(id) {
        var el = document.getElementById(id);
        return el ? String(el.value || '').trim() : '';
    }

    function numberOrNull(id) {
        var raw = value(id);
        if (!raw) return null;
        var parsed = Number(raw);
        return Number.isFinite(parsed) ? parsed : null;
    }

    function setValue(id, next) {
        var el = document.getElementById(id);
        if (el) el.value = next === null || next === undefined ? '' : String(next);
    }

    function translated(translate, key, fallback) {
        var fn = typeof translate === 'function' ? translate : global._tr;
        if (typeof fn !== 'function') return fallback;
        try {
            return fn(key) || fallback;
        } catch (_error) {
            return fallback;
        }
    }

    function setLocationStatus(kind, message) {
        var status = document.getElementById('mm-weather-location-status');
        if (!status) return;
        status.className = 'weather-location-status' + (kind ? ' ' + kind : '');
        status.textContent = message || '';
    }

    function showLocationResult(kind, title, message) {
        var feedback = global.VOFeedback;
        if (feedback && typeof feedback.show === 'function') {
            setLocationStatus('', '');
            feedback.show({
                title: title,
                message: message,
                tone: kind === 'ok' ? 'success' : 'error',
                persistent: false,
                duration: kind === 'ok' ? 4500 : 7000
            });
            return;
        }
        setLocationStatus(kind, message);
    }

    function coordinate(value) {
        return String(Math.round(Number(value) * 1000000) / 1000000);
    }

    function dispatchDraftEvent(input) {
        if (!input || typeof global.Event !== 'function') return;
        input.dispatchEvent(new global.Event('input', { bubbles: true }));
        input.dispatchEvent(new global.Event('change', { bubbles: true }));
    }

    function locateCurrentPosition(translate, geolocation) {
        var button = document.getElementById('mm-weather-locate');
        var originalLabel = button ? button.textContent : '';
        var locator = geolocation || ((global.navigator || {}).geolocation);
        if (!locator || typeof locator.getCurrentPosition !== 'function') {
            showLocationResult('err', translated(translate, 'weather_location_failed_title', 'Location failed'), translated(translate, 'weather_location_unavailable', 'Location is unavailable in this browser.'));
            return Promise.resolve({ ok: false, code: 'unavailable' });
        }
        if (button) {
            button.disabled = true;
            button.setAttribute('aria-busy', 'true');
            button.textContent = translated(translate, 'weather_locating', 'Locating...');
        }
        setLocationStatus('', translated(translate, 'weather_locating', 'Locating...'));
        return new Promise(function (resolve) {
            function finish(result) {
                if (button) {
                    button.disabled = false;
                    button.removeAttribute('aria-busy');
                    button.textContent = originalLabel;
                }
                resolve(result);
            }
            try {
                locator.getCurrentPosition(function (position) {
                    var coords = (position || {}).coords || {};
                    var latitude = Number(coords.latitude);
                    var longitude = Number(coords.longitude);
                    if (!Number.isFinite(latitude) || !Number.isFinite(longitude) || Math.abs(latitude) > 90 || Math.abs(longitude) > 180) {
                        showLocationResult('err', translated(translate, 'weather_location_failed_title', 'Location failed'), translated(translate, 'weather_location_unavailable', 'Location is unavailable in this browser.'));
                        finish({ ok: false, code: 'invalid_position' });
                        return;
                    }
                    var latitudeInput = document.getElementById('mm-weather-latitude');
                    var longitudeInput = document.getElementById('mm-weather-longitude');
                    setValue('mm-weather-latitude', coordinate(latitude));
                    setValue('mm-weather-longitude', coordinate(longitude));
                    dispatchDraftEvent(latitudeInput);
                    dispatchDraftEvent(longitudeInput);
                    showLocationResult('ok', translated(translate, 'weather_location_success_title', 'Location updated'), translated(translate, 'weather_location_acquired', 'Current coordinates added to the draft.'));
                    finish({ ok: true, latitude: latitude, longitude: longitude });
                }, function (error) {
                    var code = Number((error || {}).code);
                    var key = code === 1 ? 'weather_location_denied' : (code === 3 ? 'weather_location_timeout' : 'weather_location_unavailable');
                    var fallback = code === 1 ? 'Location permission was denied.' : (code === 3 ? 'Location request timed out.' : 'Location is unavailable in this browser.');
                    showLocationResult('err', translated(translate, 'weather_location_failed_title', 'Location failed'), translated(translate, key, fallback));
                    finish({ ok: false, code: code === 1 ? 'denied' : (code === 3 ? 'timeout' : 'unavailable') });
                }, {
                    enableHighAccuracy: true,
                    timeout: 10000,
                    maximumAge: 60000
                });
            } catch (_error) {
                showLocationResult('err', translated(translate, 'weather_location_failed_title', 'Location failed'), translated(translate, 'weather_location_unavailable', 'Location is unavailable in this browser.'));
                finish({ ok: false, code: 'unavailable' });
            }
        });
    }

    function toggleProviderFields() {
        var provider = value('mm-weather-provider') || 'qweather';
        var fields = document.getElementById('mm-qweather-fields');
        if (fields) fields.hidden = provider !== 'qweather';
    }

    function fill(config) {
        config = config || {};
        var location = String(config.location || '');
        var parts = location.split(',');
        setValue('mm-weather-city', (parts[0] || '').replace(/\+/g, ' '));
        setValue('mm-weather-state', (parts[1] || '').replace(/\+/g, ' '));
        setValue('mm-weather-provider', config.provider || 'qweather');
        setValue('mm-weather-latitude', config.latitude);
        setValue('mm-weather-longitude', config.longitude);
        var qweather = config.qweather || {};
        setValue('mm-qweather-api-host', qweather.apiHost || '');
        setValue('mm-qweather-api-key', qweather.apiKeyConfigured ? (qweather.maskedApiKey || MASK) : '');
        var fallback = document.getElementById('mm-weather-fallback');
        if (fallback) fallback.checked = config.fallbackEnabled !== false;
        toggleProviderFields();
    }

    function read(buildLocation) {
        var location = buildLocation(
            value('mm-weather-city'),
            value('mm-weather-state')
        );
        var apiKey = value('mm-qweather-api-key');
        var config = {
            provider: value('mm-weather-provider') || 'qweather',
            location: location || null,
            latitude: numberOrNull('mm-weather-latitude'),
            longitude: numberOrNull('mm-weather-longitude'),
            fallbackEnabled: !!((document.getElementById('mm-weather-fallback') || {}).checked),
            qweather: {
                apiHost: value('mm-qweather-api-host') || null
            }
        };
        if (apiKey && apiKey.indexOf('••') < 0) config.qweather.apiKey = apiKey;
        return config;
    }

    function requestTest(config, managementFetch) {
        var request = typeof managementFetch === 'function' ? managementFetch : fetch;
        return request('/api/weather/test', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ weather: config })
        });
    }

    global.VOWeatherSettings = Object.freeze({
        fill: fill,
        locateCurrentPosition: locateCurrentPosition,
        read: read,
        requestTest: requestTest,
        toggleProviderFields: toggleProviderFields
    });
})(window);
