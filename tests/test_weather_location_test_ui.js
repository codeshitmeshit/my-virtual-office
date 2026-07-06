const assert = require('assert');
const fs = require('fs');
const path = require('path');

const root = path.resolve(__dirname, '..');
const indexHtml = fs.readFileSync(path.join(root, 'app', 'index.html'), 'utf8');
const setupHtml = fs.readFileSync(path.join(root, 'app', 'setup.html'), 'utf8');
const game = fs.readFileSync(path.join(root, 'app', 'game.js'), 'utf8');
const server = fs.readFileSync(path.join(root, 'app', 'server.py'), 'utf8');
const style = fs.readFileSync(path.join(root, 'app', 'style.css'), 'utf8');
const en = JSON.parse(fs.readFileSync(path.join(root, 'app', 'locales', 'en.json'), 'utf8'));
const zh = JSON.parse(fs.readFileSync(path.join(root, 'app', 'locales', 'zh.json'), 'utf8'));

assert.ok(indexHtml.includes('onclick="mmTestWeather()"'), 'main settings should expose a weather test button');
assert.ok(indexHtml.includes('id="mm-weather-status"'), 'main settings should have a weather test status container');
assert.ok(indexHtml.includes('class="mm-weather-row"'), 'main settings weather controls should use a stable grid row');
assert.ok(indexHtml.includes('class="mm-weather-actions"'), 'main settings weather test button should be on its own row');
assert.ok(/style\.css\?v=[^"]*weather-form-layout/.test(indexHtml), 'main settings should bust cached weather form CSS');
assert.ok(indexHtml.includes('data-i18n-placeholder="weather_city_placeholder"'), 'main settings city input should have a specific placeholder');
assert.ok(indexHtml.includes('data-i18n-placeholder="weather_region_placeholder"'), 'main settings region input should be clearly optional');
assert.ok(style.includes('.mm-weather-row') && style.includes('grid-template-columns: minmax(0, 1fr) 82px'), 'main settings weather row should preserve input widths');
assert.ok(style.includes('.mm-weather-actions'), 'main settings weather action row should be styled');
assert.ok(setupHtml.includes('onclick="testSetupWeather()"'), 'setup wizard should expose a weather test button');
assert.ok(setupHtml.includes('id="s-weather-status"'), 'setup wizard should have a weather test status container');
assert.ok(setupHtml.includes('class="weather-row"'), 'setup wizard weather controls should use a stable grid row');
assert.ok(setupHtml.includes('data-i18n-placeholder="weather_city_placeholder"'), 'setup city input should have a specific placeholder');
assert.ok(setupHtml.includes('data-i18n-placeholder="weather_region_placeholder"'), 'setup region input should be clearly optional');

assert.ok(game.includes('function mmTestWeather()'), 'main settings should implement weather test handler');
assert.ok(game.includes("fetch('/api/weather/test?location=' + encodeURIComponent(location))"), 'main settings weather test should call weather test API');
assert.ok(game.includes('var _voWeatherLocation =') && game.includes('function _refreshWeatherLocationFromConfig()'), 'floor window tooltip should read weather location from server config');
assert.ok(game.includes('function _applyWeatherTestResult(location, result)'), 'weather test should have an in-page apply helper');
assert.ok(game.includes('officeConfig.weather.location = location || result.location'), 'weather test should update current office weather location');
assert.ok(game.includes('weatherData.description = result.weather ||'), 'weather test should update current weather description');
assert.ok(game.includes('weatherData.updatedAt = parseInt(result.updatedAt, 10) || Date.now();'), 'weather test should store weather update time');
assert.ok(game.includes('updatedAt: Date.now()'), 'weather polling should store weather update time');
assert.ok(game.includes('_applyWeatherTestResult(location, d);'), 'successful main-menu weather test should immediately update hover data');
assert.ok(setupHtml.includes('function testSetupWeather()'), 'setup wizard should implement weather test handler');
assert.ok(setupHtml.includes("fetch('/api/weather/test?location=' + encodeURIComponent(location))"), 'setup wizard weather test should call weather test API');

assert.ok(server.includes('"/api/weather/test"'), 'server should expose weather test endpoint');
assert.ok(server.includes('wttr.in/{_wloc_encoded}?format=j1'), 'weather test endpoint should use existing wttr pipeline');
assert.ok(server.includes('"resolvedLocation"'), 'weather test endpoint should return resolved location');
assert.ok(server.includes('"tempF"') && server.includes('"tempC"'), 'weather test endpoint should return temperatures');
assert.ok(server.includes('"updatedAt": int(time.time() * 1000)'), 'weather test endpoint should return collection update time');

assert.strictEqual(en.test_weather, '🔍 Test');
assert.strictEqual(zh.test_weather, '🔍 检测');
assert.strictEqual(zh.weather_city_placeholder, '城市，例如 Beijing');
assert.strictEqual(zh.weather_region_placeholder, '地区，可选');
assert.strictEqual(zh.weather_test_ok, '天气位置可用');
assert.strictEqual(zh.weather_test_location_required, '请先输入天气位置');
assert.strictEqual(en.weather_updated_at, 'Updated at');
assert.strictEqual(zh.weather_updated_at, '更新时间');

console.log('weather location test UI checks passed');
