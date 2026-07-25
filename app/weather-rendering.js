// Weather, display preferences, ambient light, and render-time environment helpers.
// ============================================================
// REAL WEATHER SYSTEM — fetches weather for configured location, renders on windows
// ============================================================
var weatherData = { condition: 'clear', description: '', code: 113, temp: 0, tempC: null, wind: 0, humidity: 0, feelsLike: 0, uvIndex: 0, visibility: 0, precipMM: 0, cloudcover: 0 };
var _displayPrefs = { showBubbles: true, showWeather: true, showNames: true, internalBubbleTimeoutSec: 60, fontScale: 1 };
try {
    var _dp = JSON.parse(localStorage.getItem("vo-display-prefs") || "{}");
    if (_dp.showBubbles !== undefined) _displayPrefs.showBubbles = _dp.showBubbles;
    if (_dp.showWeather !== undefined) _displayPrefs.showWeather = _dp.showWeather;
    if (_dp.showNames !== undefined) _displayPrefs.showNames = _dp.showNames;
    if (typeof VOFontScale !== 'undefined') {
        _displayPrefs.fontScale = VOFontScale.sanitizeStoredFontScale();
        VOFontScale.applyFontScale(_displayPrefs.fontScale);
    }
    if (typeof InternalBubbleSettings !== 'undefined') {
        _displayPrefs.internalBubbleTimeoutSec = InternalBubbleSettings.normalizeTimeoutSec(_dp.internalBubbleTimeoutSec);
    }
} catch(e) {}
if (typeof document !== 'undefined') {
    document.addEventListener('DOMContentLoaded', function() {
        var fontScaleInput = document.getElementById('mm-font-scale');
        if (fontScaleInput && typeof VOFontScale !== 'undefined') {
            fontScaleInput.value = String(VOFontScale.normalizeFontScale(_displayPrefs.fontScale));
        }
    });
}
var lastWeatherPoll = 0;
var weatherParticles = []; // rain/snow particles
var _weatherTick = 0;
var _floorWindowTooltip = null;
var _voWeatherLocation = '';
var _tod = { sky: "#2196f3", upper: "#42a5f5", top: "#bbdefb", cloud: "rgba(255,255,255,0.5)", glow: "rgba(255,255,240,0.08)", stars: false }; // global time-of-day sky
var _lastLightningFlash = 0;
var _nextLightningAt = 0;
var _lightningBoltX = 0;
var _rainDroplets = []; // persistent rain droplets on glass
var _snowAccum = []; // snow accumulation on window sill

function pollWeather() {
    var now = Date.now();
    if (now - lastWeatherPoll < 600000) return; // every 10 minutes
    lastWeatherPoll = now;
    fetch('/weather-proxy').then(function(res) {
        if (!res.ok) throw new Error('Weather proxy error');
        return res;
    }).catch(function() {
        // No fallback — weather requires server-side config
        return null;
    }).then(function(res) {
        if (!res) return null;
        if (!res || !res.ok) return null;
        return res.json();
    }).then(function(data) {
        if (!data || !data.current_condition) return;
        var c = data.current_condition[0];
        var code = parseInt(c.weatherCode);
        var cond = 'clear';
        // Map weather codes to conditions — expanded categories
        if ([113].includes(code)) cond = 'sunny';
        else if ([116].includes(code)) cond = 'partly_cloudy';
        else if ([119, 122].includes(code)) cond = 'overcast';
        else if ([143, 248, 260].includes(code)) cond = 'foggy';
        else if ([176, 263, 266].includes(code)) cond = 'drizzle';
        else if ([293, 296].includes(code)) cond = 'light_rain';
        else if ([299, 302, 353, 356].includes(code)) cond = 'rain';
        else if ([305, 308, 359].includes(code)) cond = 'heavy_rain';
        else if ([200, 386, 389].includes(code)) cond = 'thunderstorm';
        else if ([392, 395].includes(code)) cond = 'snow_storm';
        else if ([179, 323, 326].includes(code)) cond = 'light_snow';
        else if ([227, 230, 329, 332, 335, 338, 368, 371].includes(code)) cond = 'snow';
        else if ([182, 185, 281, 284, 311, 314, 317, 320, 362, 365, 374, 377].includes(code)) cond = 'sleet';
        else cond = 'cloudy';
        weatherData = {
            condition: cond,
            description: ((c.weatherDesc || [{}])[0] || {}).value || '',
            code: code,
            temp: parseInt(c.temp_F) || 0,
            tempC: Number.isFinite(parseInt(c.temp_C)) ? parseInt(c.temp_C) : null,
            wind: parseInt(c.windspeedMiles) || 0,
            humidity: parseInt(c.humidity) || 0,
            feelsLike: parseInt(c.FeelsLikeF) || 0,
            uvIndex: parseInt(c.uvIndex) || 0,
            visibility: parseInt(c.visibility) || 10,
            precipMM: parseFloat(c.precipMM) || 0,
            cloudcover: parseInt(c.cloudcover) || 0
        };
        // Reset droplets/accumulation on condition change
        _rainDroplets = [];
        _snowAccum = [];
    }).catch(function() {});
}

function _refreshWeatherLocationFromConfig() {
    fetch('/vo-config').then(function(r) { return r.json(); }).then(function(cfg) {
        _voWeatherLocation = (((cfg || {}).weather || {}).location || '').trim();
    }).catch(function() {});
}

// Initialize weather on load
_refreshWeatherLocationFromConfig();
pollWeather();
setInterval(pollWeather, 600000);

function _formatWeatherConditionLabel(condition) {
    var labels = {
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
    var key = labels[condition] || 'weather_condition_unknown';
    return typeof i18n !== 'undefined' ? i18n.t(key) : (condition || 'Unknown').replace(/_/g, ' ');
}

function _getWeatherLocationLabel() {
    var loc = (_voWeatherLocation || (((officeConfig || {}).weather || {}).location || '')).trim();
    return loc || (typeof i18n !== 'undefined' ? i18n.t('weather_location_unconfigured') : 'Not configured');
}

function _getWeatherTemperatureC() {
    if (Number.isFinite(weatherData.tempC)) return weatherData.tempC;
    if (Number.isFinite(weatherData.temp)) return Math.round((weatherData.temp - 32) * 5 / 9);
    return 0;
}

function _getFloorWindowWeatherTooltipLines() {
    return [
        (typeof i18n !== 'undefined' ? i18n.t('weather_location') : 'Weather Location') + ': ' + _getWeatherLocationLabel(),
        (typeof i18n !== 'undefined' ? i18n.t('weather_label') : 'Weather') + ': ' + (weatherData.description || _formatWeatherConditionLabel(weatherData.condition)),
        (typeof i18n !== 'undefined' ? i18n.t('temperature') : 'Temperature') + ': ' + _getWeatherTemperatureC() + '°C'
    ];
}

function _conditionFromWeatherDescription(desc) {
    var text = String(desc || '').toLowerCase();
    if (text.indexOf('thunder') >= 0) return 'thunderstorm';
    if (text.indexOf('snow') >= 0 || text.indexOf('blizzard') >= 0) return text.indexOf('light') >= 0 ? 'light_snow' : 'snow';
    if (text.indexOf('sleet') >= 0 || text.indexOf('ice') >= 0) return 'sleet';
    if (text.indexOf('drizzle') >= 0) return 'drizzle';
    if (text.indexOf('rain') >= 0 || text.indexOf('shower') >= 0) {
        if (text.indexOf('heavy') >= 0) return 'heavy_rain';
        if (text.indexOf('light') >= 0 || text.indexOf('patchy') >= 0) return 'light_rain';
        return 'rain';
    }
    if (text.indexOf('fog') >= 0 || text.indexOf('mist') >= 0) return 'foggy';
    if (text.indexOf('overcast') >= 0) return 'overcast';
    if (text.indexOf('cloud') >= 0) return text.indexOf('partly') >= 0 ? 'partly_cloudy' : 'cloudy';
    if (text.indexOf('sun') >= 0 || text.indexOf('clear') >= 0) return 'sunny';
    return 'clear';
}

function _applyWeatherTestResult(location, result) {
    if (!officeConfig.weather) officeConfig.weather = {};
    officeConfig.weather.location = location || result.location || officeConfig.weather.location || null;
    weatherData.condition = _conditionFromWeatherDescription(result.weather);
    weatherData.description = result.weather || '';
    weatherData.temp = parseInt(result.tempF) || weatherData.temp || 0;
    weatherData.tempC = Number.isFinite(parseInt(result.tempC)) ? parseInt(result.tempC) : weatherData.tempC;
}

// --- Helper: pseudo-random from seed ---
function _wRand(seed) {
    var x = Math.sin(seed * 127.1 + 311.7) * 43758.5453;
    return x - Math.floor(x);
}

// --- Helper: draw a rounded cloud shape ---
function _drawCloud(cx, cy, w, h, alpha) {
    ctx.fillStyle = 'rgba(180,180,185,' + alpha + ')';
    ctx.beginPath();
    ctx.arc(cx, cy, h * 0.6, 0, Math.PI * 2);
    ctx.arc(cx - w * 0.25, cy + h * 0.15, h * 0.45, 0, Math.PI * 2);
    ctx.arc(cx + w * 0.25, cy + h * 0.15, h * 0.5, 0, Math.PI * 2);
    ctx.arc(cx - w * 0.4, cy + h * 0.3, h * 0.3, 0, Math.PI * 2);
    ctx.arc(cx + w * 0.4, cy + h * 0.3, h * 0.35, 0, Math.PI * 2);
    ctx.fill();
}

// --- Helper: draw a lightning bolt ---
function _drawLightningBolt(x, y, len, branches) {
    ctx.strokeStyle = 'rgba(255,255,220,0.9)';
    ctx.lineWidth = 1.5;
    ctx.shadowColor = 'rgba(255,255,200,0.8)';
    ctx.shadowBlur = 6;
    ctx.beginPath();
    ctx.moveTo(x, y);
    var bx = x, by = y;
    var segs = 4 + Math.floor(Math.random() * 3);
    for (var i = 0; i < segs; i++) {
        bx += (Math.random() - 0.5) * 8;
        by += len / segs;
        ctx.lineTo(bx, by);
        // Branch
        if (branches && Math.random() > 0.6) {
            var ex = bx + (Math.random() - 0.5) * 12;
            var ey = by + len / segs * 0.6;
            ctx.moveTo(bx, by);
            ctx.lineTo(ex, ey);
            ctx.moveTo(bx, by);
        }
    }
    ctx.stroke();
    ctx.shadowBlur = 0;
}

function drawWeatherOnWindow(wx, wy, ww, wh, isLeft) {
    _weatherTick++;
    var cond = weatherData.condition;
    var wind = weatherData.wind;
    var t = _getTimeHour();
    var sun = _getSunTimes();
    var isDaytime = (t >= sun.sunrise && t < sun.sunset);

    // ─── SUNNY ───
    if (cond === 'sunny') {
        if (isDaytime) {
            ctx.save();
            ctx.beginPath(); ctx.rect(wx, wy, ww, wh); ctx.clip();
            // Warm golden wash
            ctx.fillStyle = 'rgba(255,235,59,0.5)';
            ctx.fillRect(wx, wy, ww, wh);
            if (isLeft) {
                var sunX = wx + 8, sunY = wy + 8;
                var rayAngle = (_weatherTick * 0.003);
                // Outer glow
                var grad = ctx.createRadialGradient(sunX, sunY, 2, sunX, sunY, 32);
                grad.addColorStop(0, 'rgba(255,245,157,0.92)');
                grad.addColorStop(0.5, 'rgba(255,235,59,0.65)');
                grad.addColorStop(1, 'rgba(255,235,59,0)');
                ctx.fillStyle = grad;
                ctx.fillRect(wx, wy, ww, wh);
                // Rotating rays with varying lengths
                ctx.lineWidth = 2;
                for (var ri = 0; ri < 12; ri++) {
                    var a = rayAngle + ri * (Math.PI / 6);
                    var rayLen = 24 + Math.sin(_weatherTick * 0.02 + ri * 0.7) * 10;
                    var rayAlpha = 0.55 + Math.sin(_weatherTick * 0.015 + ri) * 0.15;
                    ctx.strokeStyle = 'rgba(255,245,157,' + rayAlpha + ')';
                    ctx.beginPath();
                    ctx.moveTo(sunX + Math.cos(a) * 5, sunY + Math.sin(a) * 5);
                    ctx.lineTo(sunX + Math.cos(a) * rayLen, sunY + Math.sin(a) * rayLen);
                    ctx.stroke();
                }
                // Sun core with pulsing
                var pulse = 8 + Math.sin(_weatherTick * 0.02) * 2.5;
                ctx.fillStyle = 'rgba(255,235,59,0.95)';
                ctx.beginPath(); ctx.arc(sunX, sunY, pulse, 0, Math.PI * 2); ctx.fill();
                ctx.fillStyle = 'rgba(255,250,200,1.0)';
                ctx.beginPath(); ctx.arc(sunX, sunY, 3.5, 0, Math.PI * 2); ctx.fill();
                // Lens flare streak
                var flareAlpha = 0.22 + Math.sin(_weatherTick * 0.01) * 0.08;
                ctx.fillStyle = 'rgba(255,255,200,' + flareAlpha + ')';
                ctx.fillRect(wx, sunY - 1, ww, 2);
            }
            // Heat shimmer effect near bottom of window (hot day)
            if (weatherData.temp > 85) {
                var shimmer = Math.sin(_weatherTick * 0.08) * 0.04;
                ctx.fillStyle = 'rgba(255,200,50,' + (0.08 + shimmer) + ')';
                ctx.fillRect(wx, wy + wh - 8, ww, 8);
            }
            ctx.restore();
        }

    // ─── PARTLY CLOUDY ───
    } else if (cond === 'partly_cloudy') {
        ctx.save();
        ctx.beginPath(); ctx.rect(wx, wy, ww, wh); ctx.clip();
        if (isDaytime) {
            // Soft sunlight filtering through
            ctx.fillStyle = 'rgba(255,235,59,0.18)';
            ctx.fillRect(wx, wy, ww, wh);
            // Sun peeks through if left window
            if (isLeft) {
                var pcSunX = wx + 6, pcSunY = wy + 6;
                ctx.fillStyle = 'rgba(255,235,59,0.22)';
                ctx.beginPath(); ctx.arc(pcSunX, pcSunY, 5, 0, Math.PI * 2); ctx.fill();
            }
        }
        // Drifting clouds
        var drift = (_weatherTick * 0.04);
        _drawCloud(wx + (drift + 5) % (ww + 10) - 5, wy + 7, 14, 5, 0.55);
        _drawCloud(wx + (drift * 0.7 + ww * 0.6) % (ww + 10) - 5, wy + 12, 10, 4, 0.48);
        // Moving cloud shadows on floor area
        var shadowX = wx + (drift * 1.5) % ww;
        ctx.fillStyle = 'rgba(0,0,0,0.04)';
        ctx.fillRect(shadowX - 6, wy + wh - 5, 12, 5);
        ctx.restore();

    // ─── OVERCAST ───
    } else if (cond === 'overcast' || cond === 'cloudy') {
        ctx.save();
        ctx.beginPath(); ctx.rect(wx, wy, ww, wh); ctx.clip();
        // Grey blanket
        ctx.fillStyle = 'rgba(120,120,125,0.35)';
        ctx.fillRect(wx, wy, ww, wh);
        // Multiple cloud layers at different speeds
        var drift1 = (_weatherTick * 0.025);
        var drift2 = (_weatherTick * 0.015);
        // Upper layer — darker, slower
        ctx.fillStyle = 'rgba(140,140,145,0.6)';
        ctx.fillRect(wx + (drift2) % ww - 5, wy + 3, 16, 5);
        ctx.fillRect(wx + (drift2 + 20) % ww - 5, wy + 5, 12, 4);
        // Lower layer — lighter, faster
        _drawCloud(wx + (drift1 + 8) % (ww + 10) - 5, wy + 10, 14, 5, 0.48);
        _drawCloud(wx + (drift1 * 0.8 + ww * 0.5) % (ww + 10) - 5, wy + 16, 11, 4, 0.44);
        _drawCloud(wx + (drift1 * 1.2 + ww * 0.3) % (ww + 10) - 5, wy + 22, 9, 3, 0.4);
        // Dim the whole window slightly
        ctx.fillStyle = 'rgba(80,80,85,0.18)';
        ctx.fillRect(wx, wy, ww, wh);
        ctx.restore();

    // ─── DRIZZLE ───
    } else if (cond === 'drizzle') {
        ctx.save();
        ctx.beginPath(); ctx.rect(wx, wy, ww, wh); ctx.clip();
        // Slight grey tint
        ctx.fillStyle = 'rgba(130,130,135,0.26)';
        ctx.fillRect(wx, wy, ww, wh);
        // Tiny thin rain lines — sparse, slow
        ctx.strokeStyle = 'rgba(160,195,220,0.8)';
        ctx.lineWidth = 0.5;
        for (var dr = 0; dr < 5; dr++) {
            var dSeed = _wRand(dr * 7 + wx);
            var dx = wx + (dSeed * ww + _weatherTick * 0.3) % ww;
            var dy = wy + (_weatherTick * 1.2 + dr * 17) % wh;
            ctx.beginPath();
            ctx.moveTo(dx, dy);
            ctx.lineTo(dx - 0.3, dy + 3);
            ctx.stroke();
        }
        // Water droplets slowly forming on glass
        ctx.fillStyle = 'rgba(170,210,240,0.65)';
        for (var wd = 0; wd < 8; wd++) {
            var ws = _wRand(wd * 13 + wx + 99);
            var wdx = wx + 2 + ws * (ww - 4);
            var wdy = wy + 2 + _wRand(wd * 17 + 55) * (wh - 4);
            // Droplets slowly grow and drip
            var dropPhase = (_weatherTick * 0.005 + wd * 1.3) % 3;
            var dropR = dropPhase < 2 ? 0.8 + dropPhase * 0.4 : 0.8;
            ctx.beginPath(); ctx.arc(wdx, wdy + (dropPhase > 2 ? (dropPhase - 2) * 3 : 0), dropR, 0, Math.PI * 2); ctx.fill();
        }
        ctx.restore();

    // ─── LIGHT RAIN ───
    } else if (cond === 'light_rain') {
        ctx.save();
        ctx.beginPath(); ctx.rect(wx, wy, ww, wh); ctx.clip();
        ctx.fillStyle = 'rgba(100,105,110,0.3)';
        ctx.fillRect(wx, wy, ww, wh);
        // Rain streaks — medium density, angled by wind
        var windAngle = Math.min(wind * 0.02, 0.4);
        ctx.strokeStyle = 'rgba(140,185,220,0.85)';
        ctx.lineWidth = 0.8;
        for (var lr = 0; lr < 10; lr++) {
            var lSeed = _wRand(lr * 11 + wx);
            var lx = wx + (lSeed * ww + _weatherTick * (0.4 + windAngle)) % ww;
            var ly = wy + (_weatherTick * 1.8 + lr * 11) % wh;
            ctx.beginPath();
            ctx.moveTo(lx, ly);
            ctx.lineTo(lx - windAngle * 6, ly + 5);
            ctx.stroke();
        }
        // Droplets on glass — more than drizzle
        ctx.fillStyle = 'rgba(150,200,240,0.7)';
        for (var ld = 0; ld < 10; ld++) {
            var ls = _wRand(ld * 19 + wx + 77);
            var ldx = wx + 2 + ls * (ww - 4);
            var ldy = wy + 2 + _wRand(ld * 23 + 33) * (wh - 4);
            var ldPhase = (_weatherTick * 0.008 + ld * 0.9) % 4;
            var ldR = ldPhase < 2.5 ? 1 + ldPhase * 0.3 : 1;
            ctx.beginPath(); ctx.arc(ldx, ldy, ldR, 0, Math.PI * 2); ctx.fill();
            // Drip trail
            if (ldPhase > 2) {
                ctx.fillStyle = 'rgba(150,200,240,0.2)';
                ctx.fillRect(ldx - 0.3, ldy + ldR, 0.6, (ldPhase - 2) * 5);
                ctx.fillStyle = 'rgba(150,200,240,0.7)';
            }
        }
        ctx.restore();

    // ─── RAIN ───
    } else if (cond === 'rain') {
        ctx.save();
        ctx.beginPath(); ctx.rect(wx, wy, ww, wh); ctx.clip();
        ctx.fillStyle = 'rgba(80,85,95,0.38)';
        ctx.fillRect(wx, wy, ww, wh);
        // Dense rain streaks
        var rWindAngle = Math.min(wind * 0.025, 0.5);
        ctx.strokeStyle = 'rgba(130,180,220,0.9)';
        ctx.lineWidth = 1;
        for (var rr = 0; rr < 14; rr++) {
            var rSeed = _wRand(rr * 7 + wx);
            var rx = wx + (rSeed * ww + _weatherTick * (0.5 + rWindAngle)) % ww;
            var ry = wy + (_weatherTick * 2.2 + rr * 9) % wh;
            ctx.beginPath();
            ctx.moveTo(rx, ry);
            ctx.lineTo(rx - rWindAngle * 8, ry + 6);
            ctx.stroke();
        }
        // Splashes at bottom of window
        for (var sp = 0; sp < 4; sp++) {
            var sps = _wRand(sp * 31 + wx + 17);
            var spx = wx + 3 + sps * (ww - 6);
            var spy = wy + wh - 3;
            var spPhase = (_weatherTick * 0.06 + sp * 2.1) % 2;
            if (spPhase < 0.5) {
                ctx.fillStyle = 'rgba(150,200,240,' + (0.4 - spPhase * 0.8) + ')';
                var spR = 1 + spPhase * 4;
                ctx.beginPath(); ctx.arc(spx, spy, spR, Math.PI, 0); ctx.fill();
            }
        }
        // Water droplets + running streams on glass
        ctx.fillStyle = 'rgba(150,200,240,0.75)';
        for (var rd = 0; rd < 12; rd++) {
            var rs = _wRand(rd * 11 + wx + 44);
            var rdx = wx + 2 + rs * (ww - 4);
            var rdy = wy + 2 + _wRand(rd * 7 + 88) * (wh - 8);
            ctx.beginPath(); ctx.arc(rdx, rdy, 1.5, 0, Math.PI * 2); ctx.fill();
            // Running water trail
            ctx.fillStyle = 'rgba(150,200,240,0.2)';
            var trailLen = 3 + _wRand(rd * 3) * 8;
            ctx.fillRect(rdx - 0.4, rdy + 1.5, 0.8, trailLen);
            ctx.fillStyle = 'rgba(150,200,240,0.75)';
        }
        // Clouds
        _drawCloud(wx + (_weatherTick * 0.03 + 5) % (ww + 10) - 5, wy + 5, 14, 5, 0.65);
        ctx.restore();

    // ─── HEAVY RAIN ───
    } else if (cond === 'heavy_rain') {
        ctx.save();
        ctx.beginPath(); ctx.rect(wx, wy, ww, wh); ctx.clip();
        // Very dark overlay
        ctx.fillStyle = 'rgba(50,55,65,0.5)';
        ctx.fillRect(wx, wy, ww, wh);
        // Torrential rain — dense, fast, wind-driven
        var hrWind = Math.min(wind * 0.03, 0.6);
        ctx.strokeStyle = 'rgba(120,170,210,0.92)';
        ctx.lineWidth = 1.2;
        for (var hr = 0; hr < 20; hr++) {
            var hSeed = _wRand(hr * 7 + wx);
            var hx = wx + (hSeed * ww + _weatherTick * (0.7 + hrWind)) % ww;
            var hy = wy + (_weatherTick * 3 + hr * 7) % wh;
            ctx.beginPath();
            ctx.moveTo(hx, hy);
            ctx.lineTo(hx - hrWind * 10, hy + 8);
            ctx.stroke();
        }
        // Heavy splashes
        for (var hs = 0; hs < 6; hs++) {
            var hss = _wRand(hs * 23 + wx + 9);
            var hsx = wx + 3 + hss * (ww - 6);
            var hsy = wy + wh - 3;
            var hsPhase = (_weatherTick * 0.08 + hs * 1.7) % 2;
            if (hsPhase < 0.6) {
                ctx.fillStyle = 'rgba(150,200,240,' + (0.5 - hsPhase * 0.8) + ')';
                ctx.beginPath(); ctx.arc(hsx, hsy, 1.5 + hsPhase * 5, Math.PI, 0); ctx.fill();
            }
        }
        // Water streaming down window — thick rivulets
        ctx.strokeStyle = 'rgba(140,190,230,0.7)';
        ctx.lineWidth = 1.5;
        for (var rv = 0; rv < 4; rv++) {
            var rvx = wx + 4 + _wRand(rv * 41 + wx) * (ww - 8);
            ctx.beginPath();
            ctx.moveTo(rvx, wy);
            for (var rvs = 0; rvs < 6; rvs++) {
                rvx += Math.sin(_weatherTick * 0.03 + rv + rvs) * 2;
                ctx.lineTo(rvx, wy + (rvs + 1) * (wh / 6));
            }
            ctx.stroke();
        }
        // Mist/spray at bottom
        ctx.fillStyle = 'rgba(180,200,220,0.28)';
        ctx.fillRect(wx, wy + wh - 10, ww, 10);
        ctx.restore();

    // ─── THUNDERSTORM ───
    } else if (cond === 'thunderstorm') {
        ctx.save();
        ctx.beginPath(); ctx.rect(wx, wy, ww, wh); ctx.clip();
        // Very dark sky
        ctx.fillStyle = 'rgba(30,30,40,0.6)';
        ctx.fillRect(wx, wy, ww, wh);
        // Heavy wind-driven rain
        var stWind = Math.min(wind * 0.035, 0.7);
        ctx.strokeStyle = 'rgba(120,165,200,0.9)';
        ctx.lineWidth = 1;
        for (var sr = 0; sr < 18; sr++) {
            var sSeed = _wRand(sr * 7 + wx);
            var sx = wx + (sSeed * ww + _weatherTick * (0.8 + stWind)) % ww;
            var sy = wy + (_weatherTick * 3.5 + sr * 8) % wh;
            ctx.beginPath();
            ctx.moveTo(sx, sy);
            ctx.lineTo(sx - stWind * 12, sy + 7);
            ctx.stroke();
        }
        // Lightning — irregular timing with multiple bolt types
        if (_weatherTick > _nextLightningAt) {
            _lastLightningFlash = _weatherTick;
            _lightningBoltX = wx + 3 + Math.random() * (ww - 6);
            _nextLightningAt = _weatherTick + 120 + Math.floor(Math.random() * 300);
        }
        var flashAge = _weatherTick - _lastLightningFlash;
        // Flash illumination (fades over ~8 frames)
        if (flashAge < 8) {
            var flashAlpha = 0.5 * Math.pow(0.7, flashAge);
            ctx.fillStyle = 'rgba(255,255,240,' + flashAlpha + ')';
            ctx.fillRect(wx, wy, ww, wh);
        }
        // Lightning bolt visible for a few frames
        if (flashAge < 4 && isLeft) {
            _drawLightningBolt(_lightningBoltX, wy + 2, wh * 0.7, true);
        }
        // Double-flash effect (flickers)
        if (flashAge >= 6 && flashAge < 9) {
            ctx.fillStyle = 'rgba(255,255,240,0.15)';
            ctx.fillRect(wx, wy, ww, wh);
        }
        // Dark roiling clouds
        var stDrift = _weatherTick * 0.04;
        ctx.fillStyle = 'rgba(50,50,60,0.35)';
        _drawCloud(wx + (stDrift + 3) % (ww + 10) - 5, wy + 5, 16, 6, 0.72);
        _drawCloud(wx + (stDrift * 0.6 + ww * 0.5) % (ww + 10) - 5, wy + 10, 12, 5, 0.65);
        // Splashes
        for (var tsp = 0; tsp < 5; tsp++) {
            var tsps = _wRand(tsp * 19 + wx);
            var tspx = wx + 3 + tsps * (ww - 6);
            var tspy = wy + wh - 3;
            var tspPhase = (_weatherTick * 0.09 + tsp * 1.5) % 2;
            if (tspPhase < 0.5) {
                ctx.fillStyle = 'rgba(180,210,240,' + (0.4 - tspPhase * 0.8) + ')';
                ctx.beginPath(); ctx.arc(tspx, tspy, 1.5 + tspPhase * 4, Math.PI, 0); ctx.fill();
            }
        }
        ctx.restore();

    // ─── FOGGY ───
    } else if (cond === 'foggy') {
        ctx.save();
        ctx.beginPath(); ctx.rect(wx, wy, ww, wh); ctx.clip();
        // Multi-layer fog with parallax drifting
        var fogPhase = _weatherTick * 0.008;
        // Background haze
        ctx.fillStyle = 'rgba(195,195,200,0.48)';
        ctx.fillRect(wx, wy, ww, wh);
        // Fog bands — three layers at different speeds and heights
        for (var fb = 0; fb < 3; fb++) {
            var bandY = wy + 6 + fb * 10 + Math.sin(fogPhase * (0.8 + fb * 0.3) + fb * 2) * 3;
            var bandAlpha = 0.12 - fb * 0.02;
            var bandW = ww * (0.7 + _wRand(fb * 7) * 0.5);
            var bandX = wx + Math.sin(fogPhase * (0.5 + fb * 0.2)) * 5;
            ctx.fillStyle = 'rgba(210,212,215,' + bandAlpha + ')';
            ctx.fillRect(bandX, bandY, bandW, 6 - fb);
        }
        // Misty particles drifting
        ctx.fillStyle = 'rgba(220,220,225,0.4)';
        for (var mp = 0; mp < 6; mp++) {
            var mpx = wx + (_wRand(mp * 17) * ww + _weatherTick * 0.15) % ww;
            var mpy = wy + _wRand(mp * 29 + 7) * wh;
            ctx.beginPath(); ctx.arc(mpx, mpy, 2 + _wRand(mp) * 2, 0, Math.PI * 2); ctx.fill();
        }
        // Condensation on glass
        ctx.fillStyle = 'rgba(200,210,220,0.2)';
        for (var fc = 0; fc < 6; fc++) {
            var fcx = wx + 2 + _wRand(fc * 11 + wx) * (ww - 4);
            var fcy = wy + 2 + _wRand(fc * 23 + 5) * (wh - 4);
            ctx.beginPath(); ctx.arc(fcx, fcy, 1, 0, Math.PI * 2); ctx.fill();
        }
        ctx.restore();

    // ─── LIGHT SNOW ───
    } else if (cond === 'light_snow') {
        ctx.save();
        ctx.beginPath(); ctx.rect(wx, wy, ww, wh); ctx.clip();
        ctx.fillStyle = 'rgba(210,215,225,0.25)';
        ctx.fillRect(wx, wy, ww, wh);
        // Gentle floating snowflakes — slow, drifting
        for (var ls = 0; ls < 5; ls++) {
            var lsSeed = _wRand(ls * 13 + wx);
            var lsx = wx + (lsSeed * ww + _weatherTick * 0.12 + Math.sin(_weatherTick * 0.03 + ls * 1.8) * 5) % ww;
            var lsy = wy + (_weatherTick * 0.3 + ls * 13) % wh;
            var lsSize = 1 + _wRand(ls * 7) * 1.5;
            // Snowflake sparkle
            var sparkle = 0.6 + Math.sin(_weatherTick * 0.05 + ls * 2.3) * 0.3;
            ctx.fillStyle = 'rgba(255,255,255,' + sparkle + ')';
            ctx.beginPath(); ctx.arc(lsx, lsy, lsSize, 0, Math.PI * 2); ctx.fill();
        }
        // Light frost on corners
        ctx.fillStyle = 'rgba(230,235,245,0.3)';
        ctx.fillRect(wx, wy, 4, 4);
        ctx.fillRect(wx + ww - 4, wy, 4, 4);
        ctx.restore();

    // ─── SNOW ───
    } else if (cond === 'snow') {
        ctx.save();
        ctx.beginPath(); ctx.rect(wx, wy, ww, wh); ctx.clip();
        // Cold blue-grey tint
        ctx.fillStyle = 'rgba(200,205,220,0.32)';
        ctx.fillRect(wx, wy, ww, wh);
        // Dense snowflakes with varied sizes and wobble
        for (var sf = 0; sf < 10; sf++) {
            var fSeed = _wRand(sf * 13 + wx);
            var wobble = Math.sin(_weatherTick * 0.04 + sf * 1.7) * 4;
            var fx = wx + (fSeed * ww + _weatherTick * 0.18 + wobble) % ww;
            var fy = wy + (_weatherTick * 0.6 + sf * 9) % wh;
            var fSize = 1 + _wRand(sf * 3 + 5) * 2;
            var fAlpha = 0.5 + _wRand(sf * 19) * 0.4;
            ctx.fillStyle = 'rgba(255,255,255,' + fAlpha + ')';
            ctx.beginPath(); ctx.arc(fx, fy, fSize, 0, Math.PI * 2); ctx.fill();
            // Some flakes have a tiny cross shape (larger ones)
            if (fSize > 2) {
                ctx.strokeStyle = 'rgba(255,255,255,' + (fAlpha * 0.5) + ')';
                ctx.lineWidth = 0.5;
                ctx.beginPath(); ctx.moveTo(fx - fSize, fy); ctx.lineTo(fx + fSize, fy); ctx.stroke();
                ctx.beginPath(); ctx.moveTo(fx, fy - fSize); ctx.lineTo(fx, fy + fSize); ctx.stroke();
            }
        }
        // Snow accumulation on window sill
        ctx.fillStyle = 'rgba(240,242,248,0.75)';
        ctx.fillRect(wx, wy + wh - 3, ww, 3);
        ctx.fillStyle = 'rgba(250,250,255,0.3)';
        for (var sa = 0; sa < 5; sa++) {
            var sax = wx + sa * (ww / 5) + 2;
            var saH = 2 + _wRand(sa * 7 + wx) * 2;
            ctx.beginPath(); ctx.arc(sax + ww / 10, wy + wh - 2, saH, Math.PI, 0); ctx.fill();
        }
        // Frost on edges
        ctx.fillStyle = 'rgba(220,225,240,0.2)';
        ctx.fillRect(wx, wy, ww, 2);
        ctx.fillRect(wx, wy, 2, wh);
        ctx.fillRect(wx + ww - 2, wy, 2, wh);
        ctx.restore();

    // ─── SNOW STORM ───
    } else if (cond === 'snow_storm') {
        ctx.save();
        ctx.beginPath(); ctx.rect(wx, wy, ww, wh); ctx.clip();
        // Whiteout conditions
        ctx.fillStyle = 'rgba(200,205,215,0.2)';
        ctx.fillRect(wx, wy, ww, wh);
        // Blowing snow — fast, wind-driven, dense
        var snWind = Math.min(wind * 0.04, 0.8);
        for (var bs = 0; bs < 16; bs++) {
            var bSeed = _wRand(bs * 11 + wx);
            var bx = wx + (bSeed * ww + _weatherTick * (0.4 + snWind * 2)) % ww;
            var by = wy + (_weatherTick * 1.2 + bs * 7) % wh;
            var bSize = 1 + _wRand(bs * 3) * 2.5;
            var bAlpha = 0.4 + _wRand(bs * 17) * 0.5;
            ctx.fillStyle = 'rgba(255,255,255,' + bAlpha + ')';
            ctx.beginPath(); ctx.arc(bx, by, bSize, 0, Math.PI * 2); ctx.fill();
        }
        // Gusts — periodic horizontal snow streaks
        if ((_weatherTick % 120) < 30) {
            ctx.strokeStyle = 'rgba(255,255,255,0.3)';
            ctx.lineWidth = 0.8;
            for (var gs = 0; gs < 6; gs++) {
                var gsy = wy + 3 + _wRand(gs * 7 + _weatherTick) * (wh - 6);
                ctx.beginPath();
                ctx.moveTo(wx, gsy);
                ctx.lineTo(wx + ww * 0.6, gsy + (Math.random() - 0.5) * 3);
                ctx.stroke();
            }
        }
        // Heavy sill accumulation
        ctx.fillStyle = 'rgba(240,242,248,0.5)';
        ctx.fillRect(wx, wy + wh - 5, ww, 5);
        // Frost covering edges heavily
        ctx.fillStyle = 'rgba(215,220,235,0.25)';
        ctx.fillRect(wx, wy, ww, 3);
        ctx.fillRect(wx, wy, 3, wh);
        ctx.fillRect(wx + ww - 3, wy, 3, wh);
        // Ice crystals in corners
        ctx.strokeStyle = 'rgba(200,210,230,0.2)';
        ctx.lineWidth = 0.5;
        for (var ic = 0; ic < 3; ic++) {
            var icx = wx + 2 + ic * 2, icy = wy + 2 + ic * 2;
            ctx.beginPath(); ctx.moveTo(icx, icy); ctx.lineTo(icx + 4, icy + 4); ctx.stroke();
            ctx.beginPath(); ctx.moveTo(icx + 4, icy); ctx.lineTo(icx, icy + 4); ctx.stroke();
        }
        ctx.restore();

    // ─── SLEET ───
    } else if (cond === 'sleet') {
        ctx.save();
        ctx.beginPath(); ctx.rect(wx, wy, ww, wh); ctx.clip();
        ctx.fillStyle = 'rgba(100,105,115,0.15)';
        ctx.fillRect(wx, wy, ww, wh);
        // Mix of rain streaks and ice pellets
        var slWind = Math.min(wind * 0.025, 0.5);
        // Rain component
        ctx.strokeStyle = 'rgba(130,175,210,0.5)';
        ctx.lineWidth = 0.8;
        for (var sl = 0; sl < 8; sl++) {
            var slSeed = _wRand(sl * 7 + wx);
            var slx = wx + (slSeed * ww + _weatherTick * (0.5 + slWind)) % ww;
            var sly = wy + (_weatherTick * 2 + sl * 11) % wh;
            ctx.beginPath(); ctx.moveTo(slx, sly); ctx.lineTo(slx - slWind * 6, sly + 5); ctx.stroke();
        }
        // Ice pellet component — small bright dots falling faster
        ctx.fillStyle = 'rgba(220,230,240,0.7)';
        for (var ip = 0; ip < 6; ip++) {
            var ipSeed = _wRand(ip * 17 + wx + 33);
            var ipx = wx + (ipSeed * ww + _weatherTick * 0.6) % ww;
            var ipy = wy + (_weatherTick * 2.5 + ip * 12) % wh;
            ctx.fillRect(ipx, ipy, 1.5, 1.5);
        }
        // Ice buildup on glass
        ctx.fillStyle = 'rgba(200,215,230,0.15)';
        ctx.fillRect(wx, wy + wh - 3, ww, 3);
        ctx.restore();
    }
}

// ============================================================
// AMBIENT LIGHTING — day/night cycle for the whole office
// ============================================================
// Debug: set _timeLapse=true to cycle 24h in 60 seconds
var _timeLapse = false;
var _timeLapseStart = 0;

// Time override: null = real time, or fixed hour (0-23)
var _timeOverride = null;
var _timeOverrideModes = [
    null,        // real time
    12,          // noon (full daylight)
    21,          // 9 PM (night)
    6,           // 6 AM (dawn)
    17.5,        // 5:30 PM (sunset)
    'lapse'      // time-lapse
];
var _timeOverrideIdx = 0;

function cycleTimeOverride() {
    _timeOverrideIdx = (_timeOverrideIdx + 1) % _timeOverrideModes.length;
    var mode = _timeOverrideModes[_timeOverrideIdx];
    var btn = document.getElementById('btn-time-override');
    if (mode === null) {
        _timeOverride = null;
        _timeLapse = false;
        if (btn) { btn.textContent = '☀️'; btn.title = typeof i18n !== 'undefined' ? i18n.t('time_real') : 'Time: Real time'; }
        console.log('Time override OFF — real time');
    } else if (mode === 'lapse') {
        _timeOverride = null;
        _timeLapse = true;
        _timeLapseStart = Date.now();
        if (btn) { btn.textContent = '⏩'; btn.title = typeof i18n !== 'undefined' ? i18n.t('time_lapse') : 'Time: Lapse (24h in 60s)'; }
        console.log('Time-lapse ON — 24h in 60s');
    } else {
        _timeOverride = mode;
        _timeLapse = false;
        var labels = { 12: '🌞 Noon', 21: '🌙 Night', 6: '🌅 Dawn', 17.5: '🌇 Sunset' };
        if (btn) { btn.textContent = labels[mode] || '⏰'; btn.title = 'Time: ' + (labels[mode] || mode + 'h'); }
        console.log('Time override: ' + mode + 'h');
    }
}

function _getTimeHour() {
    if (_timeOverride !== null) return _timeOverride;
    if (_timeLapse) {
        var elapsed = (Date.now() - _timeLapseStart) / 1000;
        return (elapsed / 60 * 24) % 24;
    }
    var h = new Date().getHours();
    var m = new Date().getMinutes();
    return h + m / 60;
}

function toggleTimeLapse() {
    _timeLapse = !_timeLapse;
    _timeLapseStart = Date.now();
    console.log(_timeLapse ? 'Time-lapse ON — 24h in 60s' : 'Time-lapse OFF — real time');
}

// Solar calculator for Florida (~27.5°N latitude)
function _calcSunTimes() {
    var now = new Date();
    var start = new Date(now.getFullYear(), 0, 0);
    var diff = now - start;
    var dayOfYear = Math.floor(diff / 86400000);
    var lat = 27.5; // Central Florida latitude
    var latRad = lat * Math.PI / 180;

    // Solar declination
    var decl = -23.45 * Math.cos(2 * Math.PI / 365 * (dayOfYear + 10));
    var declRad = decl * Math.PI / 180;

    // Hour angle for sunrise/sunset (when sun crosses horizon)
    var cosHA = -Math.tan(latRad) * Math.tan(declRad);
    cosHA = Math.max(-1, Math.min(1, cosHA));
    var haHours = Math.acos(cosHA) * 180 / Math.PI / 15;

    // Solar noon (approximate — 12:00 + small correction)
    var noon = 12.0;

    var sunrise = noon - haHours;
    var sunset = noon + haHours;

    // Civil twilight (~30 min before sunrise / after sunset)
    var dawn = sunrise - 0.5;
    var dusk = sunset + 0.5;

    return { dawn: dawn, sunrise: sunrise, sunset: sunset, dusk: dusk };
}

var _sunTimes = _calcSunTimes(); // recalculate once on load
var _sunTimesLastDay = new Date().getDate();

function _getSunTimes() {
    var today = new Date().getDate();
    if (today !== _sunTimesLastDay) {
        _sunTimes = _calcSunTimes();
        _sunTimesLastDay = today;
    }
    return _sunTimes;
}

// --- FPS counter + perf profiling ---
var _fpsFrames = 0, _fpsLast = Date.now(), _fpsDisplay = 0;
var _perfTimes = {};

function _perfStart(label) { _perfTimes[label] = performance.now(); }
function _perfEnd(label) {
    var elapsed = performance.now() - (_perfTimes[label] || 0);
    if (!_perfTimes._totals) _perfTimes._totals = {};
    if (!_perfTimes._counts) _perfTimes._counts = {};
    _perfTimes._totals[label] = (_perfTimes._totals[label] || 0) + elapsed;
    _perfTimes._counts[label] = (_perfTimes._counts[label] || 0) + 1;
    // Log every 120 frames
    if (_perfTimes._counts[label] === 120) {
        var avg = _perfTimes._totals[label] / 120;
        if (avg > 0.5) console.log('[perf] ' + label + ': ' + avg.toFixed(2) + 'ms avg');
        _perfTimes._totals[label] = 0;
        _perfTimes._counts[label] = 0;
    }
}

// --- Rim light cache (Option D: throttled to every 5 frames) ---
var _rimCache = new Map();
var _rimFrame = 0;
var _RIM_INTERVAL = 5;

// Cached ambient light — computed once per frame via _updateAmbientCache()
var _ambientCache = { dark: 0, tint: '0,0,0' };
function _updateAmbientCache() {
    var t = _getTimeHour();
    var sun = _getSunTimes();

    // Phase boundaries based on real sun times
    var nightEnd = sun.dawn;              // civil twilight begins
    var dawnEnd = sun.sunrise;            // sun rises
    var morningEnd = sun.sunrise + 1.5;   // golden hour ends ~1.5h after sunrise
    var afternoonStart = sun.sunset - 2;  // late afternoon begins 2h before sunset
    var sunsetStart = sun.sunset - 0.5;   // sunset glow starts 30min before
    var sunsetEnd = sun.sunset + 0.3;     // sun dips below
    var duskEnd = sun.dusk;               // civil twilight ends — full night

    if (t < nightEnd)         _ambientCache = { dark: 0.25, tint: '0,10,40' };       // deep night
    else if (t < dawnEnd)     _ambientCache = { dark: 0.12, tint: '60,20,0' };       // dawn
    else if (t < morningEnd)  _ambientCache = { dark: 0.05, tint: '40,20,0' };       // morning golden
    else if (t < afternoonStart) _ambientCache = { dark: 0,    tint: '0,0,0' };      // full daylight
    else if (t < sunsetStart) _ambientCache = { dark: 0.03, tint: '40,15,0' };       // late afternoon
    else if (t < sunsetEnd)   _ambientCache = { dark: 0.08, tint: '50,20,0' };       // sunset
    else if (t < duskEnd)     _ambientCache = { dark: 0.15, tint: '20,10,30' };      // dusk
    else                      _ambientCache = { dark: 0.25, tint: '0,10,40' };       // night
}
function getAmbientLight() { return _ambientCache; }

function drawAmbientOverlay() {
    var amb = getAmbientLight();
    if (amb.dark <= 0) return; // full daylight, no overlay needed

    // Dark overlay on entire scene
    ctx.save();
    ctx.globalCompositeOperation = 'source-over';
    ctx.fillStyle = 'rgba(' + amb.tint + ',' + amb.dark + ')';
    ctx.fillRect(0, 0, W, H);
    ctx.restore();
}

// Option G helper: check if a world-space point is visible in current viewport
function _isInView(wx, wy, margin) {
    var base = Math.max(displayW / W, displayH / H);
    var totalZoom = base * camera.zoom;
    var viewW = displayW / totalZoom;
    var viewH = displayH / totalZoom;
    var camLeft = W / 2 + camera.x - viewW / 2 - margin;
    var camTop = H / 2 + camera.y - viewH / 2 - margin;
    return wx >= camLeft && wx <= camLeft + viewW + margin * 2 &&
           wy >= camTop && wy <= camTop + viewH + margin * 2;
}

// Rim light — calculated per agent, cached every _RIM_INTERVAL frames
function getRimLight(agent) {
    var key = agent.id || agent.name;
    if (_rimFrame % _RIM_INTERVAL !== 0) {
        var cached = _rimCache.get(key);
        if (cached !== undefined) return cached;
    }
    var result = _getRimLightInner(agent);
    _rimCache.set(key, result);
    return result;
}
function _getRimLightInner(agent) {
    // Hardcoded light sources removed — rim lighting will be driven by dynamic light system
    return null;
}

// Helper: set warm lamp shadow for furniture near a light source
function _setFurnitureLampShadow(objX, objY) {
    // Hardcoded light sources removed — no-op until dynamic light system
}
function _clearFurnitureShadow() {
    ctx.shadowColor = 'transparent';
    ctx.shadowBlur = 0;
    ctx.shadowOffsetX = 0;
    ctx.shadowOffsetY = 0;
}

// Neon signs (drawn after ambient overlay so they glow through darkness)
// Option B: layered text glow instead of shadowBlur
// Neon sign colors mapped by theme
var _NEON_COLORS = {
    'branch-gold':   '#ffeb3b',
    'branch-blue':   '#00e5ff',
    'branch-orange': '#ff9100',
    'branch-cyan':   '#00e5ff',
    'branch-red':    '#ff6d00',
    'branch-gray':   '#90a4ae',
};

// Cached desk position lookup — rebuilt when furniture changes
var _deskPosCache = null;
var _deskPosCacheKey = '';
function _getDeskPositions() {
    // Simple cache key: furniture count + last item id
    var fLen = officeConfig.furniture.length;
    var key = fLen + ':' + (fLen > 0 ? officeConfig.furniture[fLen - 1].id : '');
    if (_deskPosCache && _deskPosCacheKey === key) return _deskPosCache;
    _deskPosCache = {};
    officeConfig.furniture.forEach(function(f) {
        if (f.type === 'desk' || f.type === 'bossDesk') _deskPosCache[f.x + ',' + f.y] = true;
    });
    _deskPosCacheKey = key;
    return _deskPosCache;
}

Object.assign(window, {
    pollWeather,
    drawWeatherOnWindow,
    cycleTimeOverride,
    toggleTimeLapse,
    _getTimeHour,
    _getSunTimes,
    getAmbientLight,
    drawAmbientOverlay,
    _isInView,
    getRimLight,
    _setFurnitureLampShadow,
    _clearFurnitureShadow,
    _applyWeatherTestResult,
    _formatWeatherConditionLabel,
    _getWeatherLocationLabel,
    _getFloorWindowWeatherTooltipLines
});
