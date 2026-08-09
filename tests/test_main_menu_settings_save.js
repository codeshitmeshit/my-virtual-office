const assert = require('assert');
const fs = require('fs');
const path = require('path');
const vm = require('vm');

const gameSource = fs.readFileSync(path.resolve(__dirname, '..', 'app', 'game.js'), 'utf8');
const saveStart = gameSource.indexOf('function mmSaveSettings()');
const saveEnd = gameSource.indexOf('\nfunction mmExportConfig', saveStart);
assert(saveStart >= 0 && saveEnd > saveStart, 'authoritative mmSaveSettings function must be extractable');
const saveSource = gameSource.slice(saveStart, saveEnd);

function deferred() {
  let resolve;
  let reject;
  const promise = new Promise((res, rej) => { resolve = res; reject = rej; });
  return { promise, resolve, reject };
}

function createHarness() {
  const order = [];
  const requests = [];
  const feedback = [];
  const branding = [];
  const toasts = [];
  const elements = new Map();
  function element(id) {
    if (!elements.has(id)) elements.set(id, { id, value: '', checked: false, textContent: '', style: {} });
    return elements.get(id);
  }
  element('mm-gateway-url').value = 'ws://gateway.example/ws';
  element('mm-office-name').value = 'Test Office';
  element('mm-weather-city').value = 'Beijing';
  element('mm-weather-state').value = 'BJ';
  element('mm-oc-path').value = '/srv/openclaw';
  element('mm-show-bubbles').checked = true;
  element('mm-show-weather').checked = true;
  element('mm-show-names').checked = true;
  element('mm-font-scale').value = '1';
  element('mm-apiusage-enable').checked = true;
  element('mm-pcmetrics-enable').checked = true;
  element('mm-pcmetrics-url').value = 'http://metrics.example';

  const nextRequest = deferred();
  const document = { title: '', getElementById: element };
  const window = {
    VOSettingsSaveFeedback: {
      start() { feedback.push({ state: 'saving' }); order.push('feedback:saving'); },
      success() { feedback.push({ state: 'success' }); order.push('feedback:success'); },
      failure(message) { feedback.push({ state: 'error', message }); order.push('feedback:error'); },
    },
    setPcMonitorEnabled(value) { order.push(`pc:${value}`); },
    setApiUsageEnabled(value) { order.push(`api:${value}`); },
    setVoChatShiftEnterToSend(value) { order.push(`chat:${value}`); },
    VOOfficeBranding: {
      buildOfficePayload(name) { return { name, iconDataUrl: 'data:image/png;base64,aWNvbg==' }; },
      applySavedOffice(office) { branding.push(office); order.push('branding'); document.title = office.name; },
    },
  };
  const context = {
    window,
    document,
    localStorage: {
      setItem(key, value) { order.push('localStorage'); this[key] = value; },
    },
    i18n: {
      managementFetch(url, init) { order.push('request'); requests.push({ url, init }); return nextRequest.promise; },
    },
    _displayPrefs: { fontScale: 1 },
    _voWeatherLocation: '',
    _mmSaveSettingsRequest: null,
    _buildWeatherLocation(city, state) { return `${city},${state}`; },
    _mtgNormalizePreparingTimeoutSec() { return 300; },
    mmIsMaskedFeishuValue() { return false; },
    _showOfficeToast(message) { toasts.push(message); },
    pollWeather() { order.push('weather'); },
    console,
    Promise,
    Object,
    JSON,
  };
  vm.createContext(context);
  vm.runInContext(`${saveSource}\nthis.mmSaveSettings = mmSaveSettings;`, context);
  return { context, order, requests, feedback, branding, toasts, nextRequest, elements };
}

async function testSuccessAndDeduplication() {
  const env = createHarness();
  const first = env.context.mmSaveSettings();
  const second = env.context.mmSaveSettings();
  assert.strictEqual(first, second, 'pending saves should share one promise');
  assert.strictEqual(env.requests.length, 1, 'pending saves must send one request');
  assert.deepStrictEqual(env.order.slice(0, 3), ['localStorage', 'feedback:saving', 'request']);
  const payload = JSON.parse(env.requests[0].init.body);
  assert.strictEqual(env.requests[0].url, '/setup/save');
  assert.strictEqual(payload.openclaw.homePath, '/srv/openclaw');
  assert.strictEqual(payload.features.apiUsage, true);
  assert.strictEqual(payload.features.pcMetrics, true);
  assert.strictEqual(payload.office.name, 'Test Office');
  assert.strictEqual(payload.office.iconDataUrl, 'data:image/png;base64,aWNvbg==');

  env.nextRequest.resolve({ async json() { return { ok: true }; } });
  const result = await first;
  assert.strictEqual(result.ok, true);
  assert.strictEqual(env.feedback.at(-1).state, 'success');
  assert(env.order.includes('weather'), 'success should retain weather refresh');
  assert(env.order.includes('pc:true'), 'success should retain PC runtime update');
  assert(env.order.includes('api:true'), 'success should retain API usage runtime update');
  assert.strictEqual(env.context.document.title, 'Test Office');
  assert.deepStrictEqual(env.branding, [payload.office]);
  assert.strictEqual(env.context._mmSaveSettingsRequest, null, 'settled request should release the pending guard');
}

async function testBusinessFailure() {
  const env = createHarness();
  const pending = env.context.mmSaveSettings();
  env.nextRequest.resolve({ async json() { return { ok: false, error: 'invalid gateway' }; } });
  const result = await pending;
  assert.strictEqual(result.ok, false);
  assert.deepStrictEqual(env.feedback.at(-1), { state: 'error', message: 'invalid gateway' });
  assert.strictEqual(env.order.includes('weather'), false, 'failed save must not apply success runtime updates');
  assert.deepStrictEqual(env.branding, [], 'failed save must not apply draft branding');
}

async function testNetworkFailure() {
  const env = createHarness();
  const pending = env.context.mmSaveSettings();
  env.nextRequest.reject(new Error('network down'));
  const result = await pending;
  assert.strictEqual(result.ok, false);
  assert.strictEqual(result.error, 'network down');
  assert.deepStrictEqual(env.feedback.at(-1), { state: 'error', message: 'network down' });
  assert.strictEqual(env.order.includes('weather'), false, 'network failure must not apply success runtime updates');
  assert.deepStrictEqual(env.branding, [], 'network failure must not apply draft branding');
}

Promise.resolve()
  .then(testSuccessAndDeduplication)
  .then(testBusinessFailure)
  .then(testNetworkFailure)
  .then(() => console.log('main menu settings save outcomes ok'))
  .catch((error) => { console.error(error); process.exitCode = 1; });
