const assert = require('assert');
const fs = require('fs');
const path = require('path');

const root = path.resolve(__dirname, '..');
const layout = fs.readFileSync(path.join(root, 'app', 'office-layout-editor.js'), 'utf8');
const rendering = fs.readFileSync(path.join(root, 'app', 'office-rendering.js'), 'utf8');
const weather = fs.readFileSync(path.join(root, 'app', 'weather-rendering.js'), 'utf8');
const loop = fs.readFileSync(path.join(root, 'app', 'office-loop.js'), 'utf8');
const game = fs.readFileSync(path.join(root, 'app', 'game.js'), 'utf8');
const source = [layout, rendering, weather, loop, game].join('\n');

assert.ok(
  layout.includes("'floorWindow':   { w: 80,  h: 80,  ox: 0,    oy: 0    }"),
  'floorWindow should have 2x2 tile furniture bounds'
);

const functionalCatalog = layout.match(/\{ key: 'catalog_functional', items: \[[\s\S]*?\]\}/);
assert.ok(functionalCatalog, 'catalog_functional should be present');
assert.ok(
  functionalCatalog[0].includes("{ type: 'floorWindow',   key: 'furniture_floor_window'"),
  'floorWindow should appear in Functional Furniture'
);

const structureCatalog = layout.match(/\{ key: 'catalog_structure', items: \[[\s\S]*?\]\}/);
assert.ok(structureCatalog, 'catalog_structure should be present');
assert.ok(
  !structureCatalog[0].includes("type: 'floorWindow'"),
  'floorWindow should not appear in Structure Furniture'
);

assert.ok(
  rendering.includes("case 'floorWindow':   drawFloorWindow(item); break;"),
  'drawFurnitureItem should dispatch floorWindow to drawFloorWindow'
);

const drawFloorWindow = rendering.match(/function drawFloorWindow\(item\) \{[\s\S]*?\n\}/);
assert.ok(drawFloorWindow, 'drawFloorWindow should be implemented');
assert.ok(
  rendering.includes('function _getConnectedFloorWindowRun(item)') &&
  rendering.includes("return f.type === 'floorWindow' && Math.abs(f.y - item.y) < 1;") &&
  rendering.includes('Math.abs(f.x + b.w - left) < 1') &&
  rendering.includes('Math.abs(f.x - right) < 1'),
  'floorWindow should detect horizontally connected adjacent panes'
);
assert.ok(
  drawFloorWindow[0].includes('drawWeatherOnWindow(sceneX, sceneY, sceneW, sceneH, showSun);'),
  'drawFloorWindow should reuse drawWeatherOnWindow across the connected scene'
);
assert.ok(
  drawFloorWindow[0].includes('var showWeather = item.weather !== false') &&
  drawFloorWindow[0].includes('var showSun = item.showSun !== false'),
  'floorWindow should default weather and sun effects on'
);
assert.ok(
  rendering.includes('function _drawFloorWindowSunMoon(sceneX, sceneY, sceneW, sceneH)') &&
  drawFloorWindow[0].includes('_drawFloorWindowSunMoon(sceneX, sceneY, sceneW, sceneH);') &&
  rendering.includes('ctx.arc(cx, cy, pulse, 0, Math.PI * 2);') &&
  rendering.includes('ctx.arc(cx, cy, 7, 0, Math.PI * 2);'),
  'floorWindow should draw its own visible sun or moon when enabled'
);
assert.ok(
  !drawFloorWindow[0].includes('Pane dividers') &&
  !drawFloorWindow[0].includes('Math.floor(ww / 3)') &&
  drawFloorWindow[0].includes('no window frame or pane dividers'),
  'floorWindow should render as a continuous frameless glass pane'
);
assert.ok(
  drawFloorWindow[0].includes('if (run.hasLeft) return;') &&
  drawFloorWindow[0].includes('var x = run.x, y = run.y;') &&
  drawFloorWindow[0].includes('var bw = run.w, bh = run.h;') &&
  drawFloorWindow[0].includes('var floorWindowWeatherTick = _weatherTick') &&
  drawFloorWindow[0].includes('_weatherTick = floorWindowWeatherTick'),
  'connected floorWindow panes should draw once as one scene and keep weather animation seamless'
);
assert.ok(
  !drawFloorWindow[0].includes("badges.push('🌧️')") &&
  !drawFloorWindow[0].includes("badges.push('☀️')"),
  'floorWindow should not draw duplicate weather/sun badges on the glass'
);

assert.ok(
  layout.includes("if (type === 'window' || type === 'interactiveWindow' || type === 'floorWindow')"),
  'placement should treat floorWindow as a top-wall window'
);
assert.ok(
  layout.includes("dragItem.type === 'window' || dragItem.type === 'interactiveWindow' || dragItem.type === 'floorWindow'"),
  'drag constraints should treat floorWindow as a top-wall window'
);
assert.ok(
  layout.includes("item.type !== 'interactiveWindow' && item.type !== 'floorWindow'") &&
  layout.includes("selItem.type === 'interactiveWindow' || selItem.type === 'floorWindow'"),
  'floating toolbar settings should support interactiveWindow and floorWindow'
);
assert.ok(
  rendering.includes("var titleKey = item.type === 'floorWindow' ? 'floor_window_settings' : 'weather_window_settings';") &&
  rendering.includes("i18n.t('weather_effects_label')") &&
  rendering.includes("i18n.t('weather_effects_desc')") &&
  rendering.includes("i18n.t('sun_moon_label')") &&
  rendering.includes("i18n.t('sun_moon_desc')") &&
  rendering.includes("i18n.t('weather_effects_on')") &&
  rendering.includes("i18n.t('sun_moon_off')"),
  'weather/floor window settings editor should use i18n strings'
);
assert.ok(
  weather.includes('var _floorWindowTooltip = null;') &&
  weather.includes('function _getFloorWindowWeatherTooltipLines()') &&
  weather.includes('function _getWeatherTemperatureC()') &&
  weather.includes("i18n.t('weather_location')") &&
  weather.includes("i18n.t('weather_label')") &&
  weather.includes("i18n.t('temperature')") &&
  weather.includes("_getWeatherTemperatureC() + '°C'") &&
  !source.includes("weatherData.temp + '°F'") &&
  game.includes("item.type !== 'floorWindow'") &&
  game.includes('_floorWindowTooltip = {') &&
  loop.includes('fwLines = _floorWindowTooltip.lines || []'),
  'floorWindow hover should show weather location, condition, and temperature tooltip'
);

const en = JSON.parse(fs.readFileSync(path.join(root, 'app', 'locales', 'en.json'), 'utf8'));
const zh = JSON.parse(fs.readFileSync(path.join(root, 'app', 'locales', 'zh.json'), 'utf8'));
assert.strictEqual(en.furniture_floor_window, 'Floor Window');
assert.strictEqual(zh.furniture_floor_window, '落地窗');
assert.strictEqual(en.floor_window_settings, 'Floor Window Settings');
assert.strictEqual(zh.floor_window_settings, '落地窗设置');
assert.strictEqual(zh.weather_effects_label, '显示天气效果');
assert.strictEqual(zh.sun_moon_off, '太阳/月亮关闭');
assert.strictEqual(en.weather_label, 'Weather');
assert.strictEqual(zh.weather_label, '天气');
assert.strictEqual(zh.weather_condition_heavy_rain, '大雨');
assert.strictEqual(zh.weather_location_unconfigured, '未配置');

console.log('floor window furniture tests passed');
