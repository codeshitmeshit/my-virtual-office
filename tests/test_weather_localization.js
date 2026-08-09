const assert = require('assert');
const path = require('path');

const modulePath = path.resolve(__dirname, '..', 'app', 'weather-localization.js');
delete require.cache[modulePath];
const localization = require(modulePath);

function i18n(language) {
  const zh = {
    weather_condition_foggy: '有雾',
    weather_condition_cloudy: '多云',
    weather_condition_unknown: '未知',
  };
  return {
    getLanguage: () => language,
    t: (key) => language === 'zh' ? (zh[key] || key) : key,
  };
}

assert.strictEqual(localization.description('Smoky haze', 'foggy', i18n('zh')), '烟霾');
assert.strictEqual(localization.description('Partly cloudy', 'partly_cloudy', i18n('zh')), '局部多云');
assert.strictEqual(localization.description('小雨', 'light_rain', i18n('zh')), '小雨');
assert.strictEqual(localization.description('Unmapped provider phrase', 'cloudy', i18n('zh')), '多云');
assert.strictEqual(localization.description('Smoky haze', 'foggy', i18n('en')), 'Smoky haze');

console.log('weather localization checks passed');
