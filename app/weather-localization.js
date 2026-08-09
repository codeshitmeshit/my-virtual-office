(function initWeatherLocalization(root) {
    'use strict';

    var CONDITION_KEYS = {
        clear: 'weather_condition_clear',
        sunny: 'weather_condition_sunny',
        partly_cloudy: 'weather_condition_partly_cloudy',
        cloudy: 'weather_condition_cloudy',
        overcast: 'weather_condition_overcast',
        foggy: 'weather_condition_foggy',
        drizzle: 'weather_condition_drizzle',
        light_rain: 'weather_condition_light_rain',
        rain: 'weather_condition_rain',
        heavy_rain: 'weather_condition_heavy_rain',
        thunderstorm: 'weather_condition_thunderstorm',
        light_snow: 'weather_condition_light_snow',
        snow: 'weather_condition_snow',
        snow_storm: 'weather_condition_snow_storm',
        sleet: 'weather_condition_sleet'
    };

    var ZH_DESCRIPTION_RULES = [
        [/smoky\s+haze|smoke\s+haze/, '烟霾'],
        [/haze|smog/, '霾'],
        [/freezing\s+fog/, '冻雾'],
        [/mist/, '薄雾'],
        [/fog/, '雾'],
        [/blizzard|snowstorm/, '暴雪'],
        [/heavy\s+snow/, '大雪'],
        [/light\s+snow|snow\s+shower/, '小雪'],
        [/sleet|ice\s+pellets?/, '雨夹雪'],
        [/thundery\s+outbreaks?|thunderstorm/, '雷暴'],
        [/patchy\s+light\s+rain|light\s+rain|light\s+showers?/, '小雨'],
        [/heavy\s+rain|torrential\s+rain/, '大雨'],
        [/moderate\s+rain/, '中雨'],
        [/rain\s+shower|showers?/, '阵雨'],
        [/drizzle/, '毛毛雨'],
        [/rain/, '有雨'],
        [/overcast/, '阴天'],
        [/partly\s+cloudy|partly\s+cloud/, '局部多云'],
        [/cloudy|cloud/, '多云'],
        [/sunny|clear/, '晴天']
    ];

    function language(i18nApi) {
        var value = i18nApi && typeof i18nApi.getLanguage === 'function'
            ? i18nApi.getLanguage()
            : '';
        if (value) return String(value).toLowerCase();
        return String((root.navigator || {}).language || '').toLowerCase();
    }

    function translatedCondition(condition, i18nApi) {
        var key = CONDITION_KEYS[condition] || 'weather_condition_unknown';
        if (i18nApi && typeof i18nApi.t === 'function') {
            var value = i18nApi.t(key);
            if (value && value !== key) return value;
        }
        return String(condition || 'Unknown').replace(/_/g, ' ');
    }

    function containsChinese(value) {
        return /[\u3400-\u9fff]/.test(value);
    }

    function description(rawDescription, condition, i18nApi) {
        var raw = String(rawDescription || '').trim();
        if (language(i18nApi).indexOf('zh') !== 0) {
            return raw || translatedCondition(condition, i18nApi);
        }
        if (containsChinese(raw)) return raw;
        var normalized = raw.toLowerCase();
        for (var index = 0; index < ZH_DESCRIPTION_RULES.length; index += 1) {
            if (ZH_DESCRIPTION_RULES[index][0].test(normalized)) {
                return ZH_DESCRIPTION_RULES[index][1];
            }
        }
        return translatedCondition(condition, i18nApi);
    }

    root.VOWeatherLocalization = Object.freeze({
        description: description,
        translatedCondition: translatedCondition
    });
    if (typeof module !== 'undefined' && module.exports) module.exports = root.VOWeatherLocalization;
})(typeof window !== 'undefined' ? window : globalThis);
