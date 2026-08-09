const assert = require('assert');
const fs = require('fs');
const path = require('path');
const vm = require('vm');

const source = fs.readFileSync(path.join(__dirname, '..', 'app', 'weather-settings.js'), 'utf8');

function createElement(value = '') {
    return {
        value,
        textContent: '',
        className: '',
        disabled: false,
        attributes: {},
        events: [],
        setAttribute(name, value) { this.attributes[name] = value; },
        removeAttribute(name) { delete this.attributes[name]; },
        dispatchEvent(event) { this.events.push(event.type); }
    };
}

function loadModule(geolocation, withFeedback = false) {
    const elements = {
        'mm-weather-locate': createElement(),
        'mm-weather-location-status': createElement(),
        'mm-weather-latitude': createElement(),
        'mm-weather-longitude': createElement()
    };
    elements['mm-weather-locate'].textContent = '⌖ Use current location';
    const window = {
        navigator: { geolocation },
        Event: function Event(type) { this.type = type; },
        feedbackCalls: []
    };
    if (withFeedback) window.VOFeedback = { show(options) { window.feedbackCalls.push(options); } };
    const context = {
        window,
        document: { getElementById(id) { return elements[id] || null; } },
        Promise,
        Number,
        Math,
        String
    };
    vm.runInNewContext(source, context);
    return { api: window.VOWeatherSettings, elements, feedbackCalls: window.feedbackCalls };
}

(async function () {
    let options;
    const success = loadModule({
        getCurrentPosition(onSuccess, _onError, nextOptions) {
            options = nextOptions;
            onSuccess({ coords: { latitude: 39.98765449, longitude: 116.12345649 } });
        }
    });
    const result = await success.api.locateCurrentPosition((key) => key);
    assert.strictEqual(result.ok, true);
    assert.strictEqual(success.elements['mm-weather-latitude'].value, '39.987654');
    assert.strictEqual(success.elements['mm-weather-longitude'].value, '116.123456');
    assert.deepStrictEqual(success.elements['mm-weather-latitude'].events, ['input', 'change']);
    assert.strictEqual(success.elements['mm-weather-location-status'].className, 'weather-location-status ok');
    assert.strictEqual(JSON.stringify(options), JSON.stringify({ enableHighAccuracy: true, timeout: 10000, maximumAge: 60000 }));

    const notified = loadModule({
        getCurrentPosition(onSuccess) { onSuccess({ coords: { latitude: 40.027617, longitude: 116.337103 } }); }
    }, true);
    await notified.api.locateCurrentPosition((key) => key);
    assert.strictEqual(notified.elements['mm-weather-location-status'].textContent, '');
    assert.strictEqual(notified.elements['mm-weather-longitude'].value, '116.337103');
    assert.deepStrictEqual(JSON.parse(JSON.stringify(notified.feedbackCalls)), [{
        title: 'weather_location_success_title',
        message: 'weather_location_acquired',
        tone: 'success',
        persistent: false,
        duration: 4500
    }]);

    const denied = loadModule({
        getCurrentPosition(_onSuccess, onError) { onError({ code: 1 }); }
    });
    const deniedResult = await denied.api.locateCurrentPosition((key) => key);
    assert.strictEqual(deniedResult.code, 'denied');
    assert.strictEqual(denied.elements['mm-weather-location-status'].textContent, 'weather_location_denied');
    assert.strictEqual(denied.elements['mm-weather-locate'].disabled, false);

    const unavailable = loadModule(null);
    const unavailableResult = await unavailable.api.locateCurrentPosition((key) => key);
    assert.strictEqual(unavailableResult.code, 'unavailable');

    console.log('weather settings geolocation checks passed');
})().catch((error) => {
    console.error(error);
    process.exitCode = 1;
});
