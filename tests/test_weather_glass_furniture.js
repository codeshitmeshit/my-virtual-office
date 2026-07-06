const assert = require('assert');
const fs = require('fs');
const path = require('path');

const root = path.resolve(__dirname, '..');
const game = fs.readFileSync(path.join(root, 'app', 'game.js'), 'utf8');

assert.ok(
  game.includes("'floorWindow':   { w: 80,  h: 80,  ox: 0,    oy: 0    }"),
  'floorWindow should have 2x2 tile furniture bounds'
);

const functionalCatalog = game.match(/\{ key: 'catalog_functional', items: \[[\s\S]*?\]\}/);
assert.ok(functionalCatalog, 'catalog_functional should be present');
assert.ok(
  functionalCatalog[0].includes("{ type: 'floorWindow',   key: 'furniture_floor_window'"),
  'floorWindow should appear in Functional Furniture'
);

const structureCatalog = game.match(/\{ key: 'catalog_structure', items: \[[\s\S]*?\]\}/);
assert.ok(structureCatalog, 'catalog_structure should be present');
assert.ok(
  !structureCatalog[0].includes("type: 'floorWindow'"),
  'floorWindow should not appear in Structure Furniture'
);

assert.ok(
  game.includes("case 'floorWindow':   drawFloorWindow(item); break;"),
  'drawFurnitureItem should dispatch floorWindow to drawFloorWindow'
);

const drawFloorWindow = game.match(/function drawFloorWindow\(item\) \{[\s\S]*?\n\}/);
assert.ok(drawFloorWindow, 'drawFloorWindow should be implemented');
assert.ok(
  game.includes('function _getConnectedFloorWindowRun(item)') &&
  game.includes("return f.type === 'floorWindow' && Math.abs(f.y - item.y) < 1;") &&
  game.includes('Math.abs(f.x + b.w - left) < 1') &&
  game.includes('Math.abs(f.x - right) < 1'),
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
  game.includes('function _drawFloorWindowSunMoon(sceneX, sceneY, sceneW, sceneH)') &&
  drawFloorWindow[0].includes('_drawFloorWindowSunMoon(sceneX, sceneY, sceneW, sceneH);') &&
  game.includes('ctx.arc(cx, cy, pulse, 0, Math.PI * 2);') &&
  game.includes('ctx.arc(cx, cy, 7, 0, Math.PI * 2);'),
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
  game.includes("if (type === 'window' || type === 'interactiveWindow' || type === 'floorWindow')"),
  'placement should treat floorWindow as a top-wall window'
);
assert.ok(
  game.includes("dragItem.type === 'window' || dragItem.type === 'interactiveWindow' || dragItem.type === 'floorWindow'"),
  'drag constraints should treat floorWindow as a top-wall window'
);
assert.ok(
  game.includes("item.type !== 'interactiveWindow' && item.type !== 'floorWindow'") &&
  game.includes("selItem.type === 'interactiveWindow' || selItem.type === 'floorWindow'"),
  'floating toolbar settings should support interactiveWindow and floorWindow'
);
assert.ok(
  game.includes("var titleKey = item.type === 'floorWindow' ? 'floor_window_settings' : 'weather_window_settings';") &&
  game.includes("i18n.t('weather_effects_label')") &&
  game.includes("i18n.t('weather_effects_desc')") &&
  game.includes("i18n.t('sun_moon_label')") &&
  game.includes("i18n.t('sun_moon_desc')") &&
  game.includes("i18n.t('weather_effects_on')") &&
  game.includes("i18n.t('sun_moon_off')"),
  'weather/floor window settings editor should use i18n strings'
);
assert.ok(
  game.includes('var _floorWindowTooltip = null;') &&
  game.includes('function _getFloorWindowWeatherTooltipLines()') &&
  game.includes('function _getWeatherTemperatureC()') &&
  game.includes('function _formatWeatherUpdatedAt()') &&
  game.includes("i18n.t('weather_location')") &&
  game.includes("i18n.t('weather_label')") &&
  game.includes("i18n.t('temperature')") &&
  game.includes("i18n.t('weather_updated_at')") &&
  game.includes("_getWeatherTemperatureC() + '°C'") &&
  game.includes('_formatWeatherUpdatedAt()') &&
  !game.includes("weatherData.temp + '°F'") &&
  game.includes("item.type !== 'floorWindow'") &&
  game.includes('_floorWindowTooltip = {') &&
  game.includes('fwLines = _floorWindowTooltip.lines || []'),
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
assert.strictEqual(en.weather_updated_at, 'Updated at');
assert.strictEqual(zh.weather_updated_at, '更新时间');
assert.strictEqual(zh.weather_updated_never, '未更新');
assert.strictEqual(zh.weather_condition_heavy_rain, '大雨');
assert.strictEqual(zh.weather_location_unconfigured, '未配置');

console.log('floor window furniture tests passed');
