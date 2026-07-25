// ============================================================
// MAIN MENU
// ============================================================
var _mainMenuOpen = false;

var DEFAULT_BROWSER_CDP_URL = 'http://127.0.0.1:9224';
var DEFAULT_BROWSER_VIEWER_URL = 'https://localhost:6901';

function toggleMainMenu() {
    var panel = document.getElementById('main-menu-panel');
    if (!panel) return;
    _mainMenuOpen = !_mainMenuOpen;
    panel.classList.toggle('open', _mainMenuOpen);
    var btn = document.getElementById('btn-main-menu');
    if (btn) btn.classList.toggle('active-edit', _mainMenuOpen);
    if (_mainMenuOpen) _mmLoadCurrentSettings();
}

function _mmLoadCurrentSettings() {
    // Populate fields from current server config
    fetch('/vo-config').then(function(r){ return r.json(); }).then(function(cfg) {
        var gwInput = document.getElementById('mm-gateway-url');
        var nameInput = document.getElementById('mm-office-name');
        var weatherCityInput = document.getElementById('mm-weather-city');
        var weatherStateInput = document.getElementById('mm-weather-state');
        var pathInput = document.getElementById('mm-oc-path');
        var tokenInput = document.getElementById('mm-gateway-token');
        var hermesCb = document.getElementById('mm-hermes-enable');
        var hermesFields = document.getElementById('mm-hermes-fields');
        var hermesHome = document.getElementById('mm-hermes-home');
        var hermesBin = document.getElementById('mm-hermes-bin');
        var hermesApiEnabled = document.getElementById('mm-hermes-api-enable');
        var hermesApiUrl = document.getElementById('mm-hermes-api-url');
        var codexEnabled = document.getElementById('mm-codex-enable');
        var codexWorkspace = document.getElementById('mm-codex-workspace');
        var codexWorkspaceRoot = document.getElementById('mm-codex-workspace-root');
        var codexMainWorkspace = document.getElementById('mm-codex-main-workspace');
        var codexModel = document.getElementById('mm-codex-model');
        var codexBridgeUrl = document.getElementById('mm-codex-bridge-url');
        var codexIncludeMain = document.getElementById('mm-codex-include-main');
        var codexIncludeNative = document.getElementById('mm-codex-include-native');
        var claudeCodeEnabled = document.getElementById('mm-claude-code-enable');
        var claudeCodeHome = document.getElementById('mm-claude-code-home');
        var claudeCodeBin = document.getElementById('mm-claude-code-bin');
        var claudeCodeWorkspace = document.getElementById('mm-claude-code-workspace');
        var claudeCodeWorkspaceRoot = document.getElementById('mm-claude-code-workspace-root');
        var claudeCodeMainWorkspace = document.getElementById('mm-claude-code-main-workspace');
        var claudeCodeModel = document.getElementById('mm-claude-code-model');
        var claudeCodeIncludeMain = document.getElementById('mm-claude-code-include-main');
        var claudeCodeIncludeNative = document.getElementById('mm-claude-code-include-native');
        var claudeCodeRegisterNative = document.getElementById('mm-claude-code-register-native');
        var meetingPreparingTimeout = document.getElementById('mm-meeting-preparing-timeout');
        var feishuEnabled = document.getElementById('mm-feishu-enable');
        var feishuAppId = document.getElementById('mm-feishu-app-id');
        var feishuAppSecret = document.getElementById('mm-feishu-app-secret');
        var feishuReceiveIdType = document.getElementById('mm-feishu-receive-id-type');
        var feishuReceiveId = document.getElementById('mm-feishu-receive-id');
        if (gwInput) gwInput.value = (cfg.openclaw || {}).gatewayUrl || '';
        if (nameInput) nameInput.value = (cfg.office || {}).name || '';
        // Parse "City,State" or "City+Name,State" back into separate fields
        var _wloc = (cfg.weather || {}).location || '';
        var _wparts = _wloc.split(',');
        if (weatherCityInput) weatherCityInput.value = (_wparts[0] || '').replace(/\+/g, ' ');
        if (weatherStateInput) weatherStateInput.value = (_wparts[1] || '').replace(/\+/g, ' ');
        if (pathInput) pathInput.value = (cfg.openclaw || {}).homePath || '';
        var hermesCfg = cfg.hermes || {};
        var hermesEnabled = hermesCfg.enabled !== false;
        if (hermesCb) hermesCb.checked = hermesEnabled;
        if (hermesFields) hermesFields.style.display = hermesEnabled ? 'block' : 'none';
        if (hermesHome) hermesHome.value = hermesCfg.homePath || '';
        if (hermesBin) hermesBin.value = hermesCfg.binary || '';
        if (hermesApiEnabled) hermesApiEnabled.checked = hermesCfg.apiEnabled === true;
        if (hermesApiUrl) hermesApiUrl.value = hermesCfg.apiUrl || '';
        var codexCfg = cfg.codex || {};
        if (codexEnabled) codexEnabled.checked = codexCfg.enabled === true;
        if (codexWorkspace) codexWorkspace.value = codexCfg.workspace || '';
        if (codexWorkspaceRoot) codexWorkspaceRoot.value = codexCfg.workspaceRoot || '';
        if (codexMainWorkspace) codexMainWorkspace.value = codexCfg.mainWorkspace || '';
        if (codexModel) codexModel.value = codexCfg.model || '';
        if (codexBridgeUrl) codexBridgeUrl.value = codexCfg.bridgeUrl || '';
        if (codexIncludeMain) codexIncludeMain.checked = codexCfg.includeMain !== false;
        if (codexIncludeNative) codexIncludeNative.checked = codexCfg.includeNativeAgents !== false;
        var claudeCfg = cfg.claudeCode || {};
        if (claudeCodeEnabled) claudeCodeEnabled.checked = claudeCfg.enabled === true;
        if (claudeCodeHome) claudeCodeHome.value = claudeCfg.homePath || '';
        if (claudeCodeBin) claudeCodeBin.value = claudeCfg.binary || '';
        if (claudeCodeWorkspace) claudeCodeWorkspace.value = claudeCfg.workspace || '';
        if (claudeCodeWorkspaceRoot) claudeCodeWorkspaceRoot.value = claudeCfg.workspaceRoot || '';
        if (claudeCodeMainWorkspace) claudeCodeMainWorkspace.value = claudeCfg.mainWorkspace || '';
        if (claudeCodeModel) claudeCodeModel.value = claudeCfg.model || '';
        if (claudeCodeIncludeMain) claudeCodeIncludeMain.checked = claudeCfg.includeMain !== false;
        if (claudeCodeIncludeNative) claudeCodeIncludeNative.checked = claudeCfg.includeNativeAgents !== false;
        if (claudeCodeRegisterNative) claudeCodeRegisterNative.checked = claudeCfg.registerNativeAgents !== false;
        // Auto-populate token from /gateway-info (shows current effective token)
        if (tokenInput) {
            fetch('/gateway-info').then(function(r) { return r.json(); }).then(function(gi) {
                if (gi.token && !tokenInput.value) tokenInput.value = gi.token;
            }).catch(function(){});
        }
        // PC Metrics
        var pcmEnabled = ((cfg.features || {}).pcMetrics) || false;
        var pcmUrl = ((cfg.pcMetrics || {}).url) || "";
        var pcmCb = document.getElementById("mm-pcmetrics-enable");
        var pcmUrlEl = document.getElementById("mm-pcmetrics-url");
        var pcmFields = document.getElementById("mm-pcmetrics-fields");
        if (pcmCb) pcmCb.checked = pcmEnabled;
        if (pcmUrlEl) pcmUrlEl.value = pcmUrl;
        if (pcmFields) pcmFields.style.display = pcmEnabled ? "block" : "none";
        // API Usage
        var apiUsageCb = document.getElementById("mm-apiusage-enable");
        if (apiUsageCb) apiUsageCb.checked = (cfg.features || {}).apiUsage === true;
        // Browser
        var brEnabled = ((cfg.features || {}).browserPanel) || false;
        var brCdp = ((cfg.browser || {}).cdpUrl) || DEFAULT_BROWSER_CDP_URL;
        var brViewer = ((cfg.browser || {}).viewerUrl) || DEFAULT_BROWSER_VIEWER_URL;
        var brCb = document.getElementById("mm-browser-enable");
        var brCdpEl = document.getElementById("mm-cdp-url");
        var brViewerEl = document.getElementById("mm-viewer-url");
        var brFields = document.getElementById("mm-browser-fields");
        if (brCb) brCb.checked = brEnabled;
        if (brCdpEl) brCdpEl.value = brCdp;
        if (brViewerEl) brViewerEl.value = brViewer;
        if (brFields) brFields.style.display = brEnabled ? "block" : "none";
        if (meetingPreparingTimeout) {
            meetingPreparingTimeout.value = String(_mtgNormalizePreparingTimeoutSec((cfg.meetings || {}).preparingTimeoutSec));
        }
        var notificationCfg = cfg.notifications || {};
        if (feishuEnabled) feishuEnabled.checked = notificationCfg.feishuEnabled !== false;
        mmFillFeishuMaskedInputs(notificationCfg);
        mmRenderFeishuMask(notificationCfg);
    }).catch(function(){});
    // Load display prefs from localStorage
    var prefs = {};
    try { prefs = JSON.parse(localStorage.getItem('vo-display-prefs') || '{}'); } catch(e){}
    var cb1 = document.getElementById('mm-show-bubbles');
    var cb2 = document.getElementById('mm-show-weather');
    var cb3 = document.getElementById('mm-show-names');
    var timeoutInput = document.getElementById('mm-internal-bubble-timeout');
    var fontScaleInput = document.getElementById('mm-font-scale');
    if (cb1) cb1.checked = prefs.showBubbles !== false;
    if (cb2) cb2.checked = prefs.showWeather !== false;
    if (cb3) cb3.checked = prefs.showNames !== false;
    if (timeoutInput) {
        timeoutInput.value = typeof InternalBubbleSettings !== 'undefined'
            ? InternalBubbleSettings.normalizeTimeoutSec(prefs.internalBubbleTimeoutSec)
            : 60;
    }
    if (fontScaleInput) {
        fontScaleInput.value = typeof VOFontScale !== 'undefined'
            ? String(VOFontScale.normalizeFontScale(prefs.fontScale))
            : String(prefs.fontScale || 1);
    }
}

function mmApplyFontScaleSetting(value) {
    if (typeof VOFontScale === 'undefined') return 1;
    var scale = VOFontScale.setStoredFontScale(value);
    VOFontScale.applyFontScale(scale);
    _displayPrefs.fontScale = scale;
    var select = document.getElementById('mm-font-scale');
    if (select) select.value = String(scale);
    return scale;
}


// PC Metrics toggle in settings
(function() {
    var _pcmCb = document.getElementById('mm-pcmetrics-enable');
    if (_pcmCb) _pcmCb.addEventListener('change', function() {
        var f = document.getElementById('mm-pcmetrics-fields');
        if (f) f.style.display = this.checked ? 'block' : 'none';
    });
})();

// Browser toggle in settings
(function() {
    var _brCb = document.getElementById('mm-browser-enable');
    if (_brCb) _brCb.addEventListener('change', function() {
        var f = document.getElementById('mm-browser-fields');
        if (f) f.style.display = this.checked ? 'block' : 'none';
    });
})();

// Hermes toggle in settings
(function() {
    var _hCb = document.getElementById('mm-hermes-enable');
    if (_hCb) _hCb.addEventListener('change', function() {
        var f = document.getElementById('mm-hermes-fields');
        if (f) f.style.display = this.checked ? 'block' : 'none';
    });
})();

function mmTestHermes() {
    var statusEl = document.getElementById('mm-hermes-status');
    var enabled = !!(document.getElementById('mm-hermes-enable') || {}).checked;
    var homePath = (document.getElementById('mm-hermes-home') || {}).value || '';
    var binary = (document.getElementById('mm-hermes-bin') || {}).value || '';
    var apiEnabled = !!(document.getElementById('mm-hermes-api-enable') || {}).checked;
    var apiUrl = (document.getElementById('mm-hermes-api-url') || {}).value || '';
    var apiKey = (document.getElementById('mm-hermes-api-key') || {}).value || '';
    if (!enabled) {
        statusEl.innerHTML = '<div class="mm-status info">' + _tr('hermes_disabled') + '</div>';
        return;
    }
    statusEl.innerHTML = '<div class="mm-status info">' + _tr('testing_hermes') + '</div>';
    var hermesSave = { enabled: enabled, homePath: homePath || null, binary: binary || null, apiEnabled: apiEnabled, apiUrl: apiUrl || null };
    if (apiKey.trim()) hermesSave.apiKey = apiKey.trim();
    fetch('/setup/save', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ hermes: hermesSave })
    }).then(function() {
        return fetch('/api/hermes/test', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ homePath: homePath || null, binary: binary || null, apiEnabled: apiEnabled, apiUrl: apiUrl || null, apiKey: apiKey.trim() || undefined })
        });
    }).then(function(r) { return r.json().then(function(d){ d._httpOk = r.ok; return d; }); }).then(function(d) {
        if (d.ok) {
            var count = (d.agents || []).length;
            var names = (d.agents || []).slice(0, 5).map(function(a){ return (a.emoji || '⚕️') + ' ' + a.name + (a.model ? ' · ' + a.model : ''); }).join('<br>');
            var api = d.api || {};
            var apiLine = apiEnabled ? '<br>Native API: ' + (api.ok ? 'connected' : ('unavailable' + (api.error ? ' · ' + escHtml(api.error) : ''))) : '';
            statusEl.innerHTML = '<div class="mm-status ok">' + _tr('hermes_connected_profiles', { count: count }) + apiLine + (names ? '<br>' + names : '') + '</div>';
        } else {
            statusEl.innerHTML = '<div class="mm-status err">❌ ' + _tr('hermes_not_reachable') + ': ' + escHtml(d.error || _tr('unknown')) + '</div>';
        }
    }).catch(function(e) {
        statusEl.innerHTML = '<div class="mm-status err">❌ ' + _tr('hermes_test_failed') + ': ' + escHtml(e.message) + '</div>';
    });
}

function mmTestSse() {
    var statusEl = document.getElementById('mm-sse-status') || document.getElementById('mm-hermes-status');
    if (!statusEl) return;
    var startedAt = Date.now();
    var firstAt = 0;
    var events = [];
    var done = false;
    var source = null;
    var timeout = null;

    function render(cls, text) {
        statusEl.innerHTML = '<div class="mm-status ' + cls + '">' + text + '</div>';
    }
    function close() {
        if (timeout) clearTimeout(timeout);
        timeout = null;
        if (source) {
            try { source.close(); } catch (_) {}
            source = null;
        }
    }
    function record(eventName, evt) {
        var data = {};
        try { data = JSON.parse(evt.data || '{}'); } catch (e) {
            render('err', '❌ ' + _tr('sse_test_invalid_json') + ': ' + escHtml(e.message));
            close();
            done = true;
            return;
        }
        if (!firstAt) firstAt = Date.now();
        events.push({ event: eventName, data: data, at: Date.now() });
        render('info', _tr('sse_testing') + '<br>' + escHtml(_tr('sse_events_received', { count: events.length })));
        if (eventName === 'sse.test.done') {
            done = true;
            var firstMs = firstAt ? firstAt - startedAt : 0;
            var totalMs = Date.now() - startedAt;
            var serverMs = Number(data.serverElapsedMs || 0);
            var lagHint = firstMs > 2500 || totalMs > 4500
                ? '<br>' + escHtml(_tr('sse_test_slow_hint'))
                : '';
            render('ok', '✅ ' + _tr('sse_test_ok') + '<br>' + escHtml(_tr('sse_test_timing', {
                count: events.length,
                firstMs: firstMs,
                totalMs: totalMs,
                serverMs: serverMs
            })) + lagHint);
            close();
        }
    }

    render('info', _tr('sse_testing'));
    try {
        source = new EventSource('/api/sse/test?ts=' + encodeURIComponent(String(Date.now())));
        ['sse.test.start', 'sse.test.tick', 'sse.test.done'].forEach(function(name) {
            source.addEventListener(name, function(evt) { record(name, evt); });
        });
        source.onerror = function() {
            if (done) return;
            render('err', '❌ ' + _tr('sse_test_failed') + '<br>' + escHtml(_tr('sse_test_html_hint')));
            close();
            done = true;
        };
        timeout = setTimeout(function() {
            if (done) return;
            render('err', '❌ ' + _tr('sse_test_timeout') + '<br>' + escHtml(_tr('sse_test_proxy_hint')));
            close();
            done = true;
        }, 8000);
    } catch (e) {
        render('err', '❌ ' + _tr('sse_test_failed') + ': ' + escHtml(e.message));
        close();
    }
}

function mmTestCodex() {
    var statusEl = document.getElementById('mm-codex-status');
    if (!statusEl) return;
    statusEl.innerHTML = '<div class="mm-status info">' + _tr('saving_testing') + '</div>';
    var cfg = {
        enabled: !!(document.getElementById('mm-codex-enable') || {}).checked,
        workspace: ((document.getElementById('mm-codex-workspace') || {}).value || '').trim() || null,
        workspaceRoot: ((document.getElementById('mm-codex-workspace-root') || {}).value || '').trim() || null,
        mainWorkspace: ((document.getElementById('mm-codex-main-workspace') || {}).value || '').trim() || null,
        model: ((document.getElementById('mm-codex-model') || {}).value || '').trim() || null,
        bridgeUrl: ((document.getElementById('mm-codex-bridge-url') || {}).value || '').trim() || null,
        includeMain: !!(document.getElementById('mm-codex-include-main') || {}).checked,
        includeNativeAgents: !!(document.getElementById('mm-codex-include-native') || {}).checked
    };
    fetch('/setup/save', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ codex: cfg })
    }).then(function() {
        return fetch('/api/codex/test', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(cfg) });
    }).then(function(r) { return r.json(); }).then(function(d) {
        statusEl.innerHTML = '<div class="mm-status ' + (d.ok ? 'ok' : 'err') + '">' + (d.ok ? 'Connected' : ('❌ ' + escHtml(d.error || _tr('unknown')))) + '</div>';
    }).catch(function(e) {
        statusEl.innerHTML = '<div class="mm-status err">❌ ' + escHtml(e.message) + '</div>';
    });
}

function mmTestClaudeCode() {
    var statusEl = document.getElementById('mm-claude-code-status');
    if (!statusEl) return;
    statusEl.innerHTML = '<div class="mm-status info">' + _tr('saving_testing') + '</div>';
    var cfg = {
        enabled: !!(document.getElementById('mm-claude-code-enable') || {}).checked,
        homePath: ((document.getElementById('mm-claude-code-home') || {}).value || '').trim() || null,
        binary: ((document.getElementById('mm-claude-code-bin') || {}).value || '').trim() || null,
        workspace: ((document.getElementById('mm-claude-code-workspace') || {}).value || '').trim() || null,
        workspaceRoot: ((document.getElementById('mm-claude-code-workspace-root') || {}).value || '').trim() || null,
        mainWorkspace: ((document.getElementById('mm-claude-code-main-workspace') || {}).value || '').trim() || null,
        model: ((document.getElementById('mm-claude-code-model') || {}).value || '').trim() || null,
        includeMain: !!(document.getElementById('mm-claude-code-include-main') || {}).checked,
        includeNativeAgents: !!(document.getElementById('mm-claude-code-include-native') || {}).checked,
        registerNativeAgents: !!(document.getElementById('mm-claude-code-register-native') || {}).checked
    };
    fetch('/setup/save', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ claudeCode: cfg })
    }).then(function() {
        return fetch('/api/claude-code/test', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(cfg) });
    }).then(function(r) { return r.json(); }).then(function(d) {
        statusEl.innerHTML = '<div class="mm-status ' + (d.ok ? 'ok' : 'err') + '">' + (d.ok ? 'Connected' : ('❌ ' + escHtml(d.error || _tr('unknown')))) + '</div>';
    }).catch(function(e) {
        statusEl.innerHTML = '<div class="mm-status err">❌ ' + escHtml(e.message) + '</div>';
    });
}

function mmTestCdp() {
    var cdpUrl = document.getElementById('mm-cdp-url').value.trim();
    var viewerUrl = document.getElementById('mm-viewer-url').value.trim();
    var statusEl = document.getElementById('mm-cdp-status');
    if (!cdpUrl) { statusEl.innerHTML = '<div class="mm-status err">' + _tr('enter_cdp_first') + '</div>'; return; }
    statusEl.innerHTML = '<div class="mm-status">' + _tr('saving_testing') + '</div>';
    // Save first, then test
    fetch('/setup/save', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            features: { browserPanel: true },
            browser: { cdpUrl: cdpUrl, viewerUrl: viewerUrl || null }
        })
    }).then(function() {
        return fetch('/browser-status');
    }).then(function(r) { return r.json(); }).then(function(status) {
        if (status.cdpAvailable) {
            fetch('/browser-tabs').then(function(r) { return r.json(); }).then(function(tabs) {
                var count = Array.isArray(tabs) ? tabs.length : 0;
                statusEl.innerHTML = '<div class="mm-status ok">' + _tr('cdp_connected_tabs', { count: count }) + '</div>';
            }).catch(function() {
                statusEl.innerHTML = '<div class="mm-status ok">' + _tr('cdp_reachable') + '</div>';
            });
        } else {
            statusEl.innerHTML = '<div class="mm-status err">\u274c ' + _tr('cdp_check_hint') + '</div>';
        }
    }).catch(function(e) {
        statusEl.innerHTML = '<div class="mm-status err">\u274c ' + _tr('error') + ': ' + escHtml(e.message) + '</div>';
    });
}

function mmTestViewer() {
    var cdpUrl = document.getElementById('mm-cdp-url').value.trim();
    var viewerUrl = document.getElementById('mm-viewer-url').value.trim();
    var statusEl = document.getElementById('mm-viewer-status');
    if (!viewerUrl) { statusEl.innerHTML = '<div class="mm-status err">' + _tr('enter_viewer_first') + '</div>'; return; }
    statusEl.innerHTML = '<div class="mm-status">' + _tr('saving_testing') + '</div>';
    // Save first, then test
    fetch('/setup/save', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            features: { browserPanel: true },
            browser: { cdpUrl: cdpUrl || null, viewerUrl: viewerUrl }
        })
    }).then(function() {
        return fetch('/browser-viewer-status');
    }).then(function(r) { return r.json(); }).then(function(status) {
        if (!status.ok) {
            throw new Error(status.error || _tr('viewer_not_reachable'));
        }
            statusEl.innerHTML = '<div class="mm-status ok">' + _tr('viewer_reachable') + '</div>';
    }).catch(function(e) {
            statusEl.innerHTML = '<div class="mm-status err">\u274c ' + _tr('viewer_not_reachable') + ': ' + escHtml(e.message) + '</div>';
    });
}

function mmTestPcMetrics() {
    var url = document.getElementById('mm-pcmetrics-url').value.trim();
    var statusEl = document.getElementById('mm-pcmetrics-status');
    if (!url) { statusEl.innerHTML = '<div class="mm-status err">' + _tr('enter_metrics_url') + '</div>'; return; }
    statusEl.innerHTML = '<div class="mm-status info">' + _tr('saving_testing') + '</div>';
    fetch('/setup/save', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ features: { pcMetrics: true }, pcMetrics: { url: url } })
    }).then(function() { return fetch('/pc-metrics'); })
    .then(function(r) { return r.json(); })
    .then(function(data) {
        if (data.error) {
            statusEl.innerHTML = '<div class="mm-status err">❌ ' + data.error + '</div>';
        } else if (data.cpu) {
            var info = 'CPU: ' + (data.cpu.percent||0).toFixed(0) + '% (' + (data.cpu.threads||'?') + ' threads)';
            info += ' · RAM: ' + (data.memory.percent||0).toFixed(0) + '%';
            if (data.gpus && data.gpus.length > 0) info += ' · GPU: ' + data.gpus[0].name;
            statusEl.innerHTML = '<div class="mm-status ok">' + _tr('connected_label') + '<br>' + info + '</div>';
        } else {
            statusEl.innerHTML = '<div class="mm-status err">❌ ' + _tr('unexpected_response_format') + '</div>';
        }
    }).catch(function(e) {
        statusEl.innerHTML = '<div class="mm-status err">❌ ' + e.message + '</div>';
    });
}

function mmTestConnection() {
    var statusEl = document.getElementById('mm-conn-status');
    statusEl.innerHTML = '<div class="mm-status info">' + _tr('testing') + '</div>';
    // Save current settings first so the server tests with the new values
    var gwUrl = document.getElementById('mm-gateway-url').value;
    var ocPath = document.getElementById('mm-oc-path').value;
    var gwToken = (document.getElementById('mm-gateway-token') || {}).value || '';
    var saveBody = { openclaw: {} };
    if (gwUrl) {
        saveBody.openclaw.gatewayUrl = gwUrl;
        saveBody.openclaw.gatewayHttp = gwUrl.replace('ws://', 'http://').replace('wss://', 'https://').replace(/\/ws.*$/, '');
    }
    if (ocPath) saveBody.openclaw.homePath = ocPath;
    if (gwToken) saveBody.openclaw.gatewayToken = gwToken;

    fetch('/setup/save', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(saveBody) })
    .then(function() {
        // Test agents (OpenClaw path)
        return fetch('/api/agents').then(function(r){ return r.json(); });
    }).then(function(d) {
        var lines = [];
        if (d.agents && d.agents.length > 0) {
            lines.push('✅ OpenClaw: ' + d.agents.length + ' agent' + (d.agents.length === 1 ? '' : 's') + ' found');
        } else {
            lines.push('⚠️ OpenClaw: connected but no agents found');
        }
        // Test gateway WS
        return fetch('/api/gateway/test').then(function(r){ return r.json(); }).then(function(t) {
            if (t.gateway === 'reachable') {
                lines.push('✅ Gateway: reachable');
                if (t.token) lines.push('✅ Token: valid');
                else lines.push('⚠️ Token: not found or invalid');
            } else {
                lines.push('❌ Gateway: ' + (t.error || 'unreachable'));
            }
            var allOk = lines.every(function(l){ return l.indexOf('✅') === 0; });
            statusEl.innerHTML = '<div class="mm-status ' + (allOk ? 'ok' : 'err') + '">' + lines.join('<br>') + '</div>';
        });
    }).catch(function(e) {
        statusEl.innerHTML = '<div class="mm-status err">❌ ' + _tr('failed') + escHtml(e.message) + '</div>';
    });
}

function _buildWeatherLocation(city, state) {
    city = (city || '').trim();
    state = (state || '').trim();
    if (!city) return null;
    return state ? city.replace(/ /g, '+') + ',' + state.replace(/ /g, '+') : city.replace(/ /g, '+');
}

function mmTestWeather() {
    var statusEl = document.getElementById('mm-weather-status');
    if (!statusEl) return;
    var location = _buildWeatherLocation(
        (document.getElementById('mm-weather-city') || {}).value,
        (document.getElementById('mm-weather-state') || {}).value
    );
    if (!location) {
        statusEl.innerHTML = '<div class="mm-status err">' + _tr('weather_test_location_required') + '</div>';
        return;
    }
    statusEl.innerHTML = '<div class="mm-status info">' + _tr('testing_weather') + '</div>';
    fetch('/api/weather/test?location=' + encodeURIComponent(location))
        .then(function(r) { return r.json().then(function(d) { d._httpOk = r.ok; return d; }); })
        .then(function(d) {
            if (!d.ok) {
                statusEl.innerHTML = '<div class="mm-status err">❌ ' + _tr('weather_test_failed') + ': ' + escHtml(d.error || _tr('unknown')) + '</div>';
                return;
            }
            _applyWeatherTestResult(location, d);
            var details = escHtml(d.resolvedLocation || location) + ' · ' + escHtml(d.weather || '') + ' · ' + escHtml(String(d.tempF || '?')) + '°F / ' + escHtml(String(d.tempC || '?')) + '°C';
            statusEl.innerHTML = '<div class="mm-status ok">✅ ' + _tr('weather_test_ok') + '<br>' + details + '</div>';
        }).catch(function(e) {
            statusEl.innerHTML = '<div class="mm-status err">❌ ' + _tr('weather_test_failed') + ': ' + escHtml(e.message) + '</div>';
        });
}

function mmRenderFeishuMask(cfg) {
    var el = document.getElementById('mm-feishu-mask');
    if (!el) return;
    cfg = cfg || {};
    if (cfg.feishuAppConfigured) {
        el.textContent = _tr('feishu_configured_app', {
            appId: cfg.maskedFeishuAppId || '••••••••',
            receiveIdType: cfg.feishuReceiveIdType || 'chat_id',
            receiveId: cfg.maskedFeishuReceiveId || '••••••••'
        });
        el.style.color = '#81c784';
    } else {
        el.textContent = _tr('feishu_not_configured');
        el.style.color = '#888';
    }
}

function mmIsMaskedFeishuValue(value) {
    return String(value || '').indexOf('••••') >= 0;
}

function mmFillFeishuMaskedInputs(cfg) {
    cfg = cfg || {};
    var appIdEl = document.getElementById('mm-feishu-app-id');
    var appSecretEl = document.getElementById('mm-feishu-app-secret');
    var receiveIdEl = document.getElementById('mm-feishu-receive-id');
    var receiveIdTypeEl = document.getElementById('mm-feishu-receive-id-type');
    if (appIdEl) appIdEl.value = cfg.maskedFeishuAppId || '';
    if (appSecretEl) appSecretEl.value = cfg.feishuAppConfigured ? '••••••••' : '';
    if (receiveIdEl) receiveIdEl.value = cfg.maskedFeishuReceiveId || '';
    if (receiveIdTypeEl) receiveIdTypeEl.value = cfg.feishuReceiveIdType || 'chat_id';
    mmRenderFeishuLongConnectionStatus(cfg);
}

function mmRenderFeishuLongConnectionStatus(cfg) {
    var el = document.getElementById('mm-feishu-long-connection-status');
    if (!el) return;
    var lc = (cfg || {}).feishuLongConnection || {};
    var status = lc.status || 'not_started';
    el.textContent = _tr('feishu_long_connection_status', { status: status });
    el.style.color = lc.running ? '#81c784' : (status === 'error' ? '#ff8a80' : '#888');
}

function mmSaveFeishuWebhook() {
    var enabledEl = document.getElementById('mm-feishu-enable');
    var appIdEl = document.getElementById('mm-feishu-app-id');
    var appSecretEl = document.getElementById('mm-feishu-app-secret');
    var receiveIdTypeEl = document.getElementById('mm-feishu-receive-id-type');
    var receiveIdEl = document.getElementById('mm-feishu-receive-id');
    var statusEl = document.getElementById('mm-feishu-status');
    if (!statusEl) return;
    var enabled = enabledEl ? enabledEl.checked : true;
    var appId = (appIdEl ? appIdEl.value : '').trim();
    var appSecret = (appSecretEl ? appSecretEl.value : '').trim();
    var receiveId = (receiveIdEl ? receiveIdEl.value : '').trim();
    var receiveIdType = (receiveIdTypeEl ? receiveIdTypeEl.value : 'chat_id') || 'chat_id';
    var appConfigured = mmIsMaskedFeishuValue(appId) && mmIsMaskedFeishuValue(appSecret) && mmIsMaskedFeishuValue(receiveId);
    if (!(appConfigured || (appId && appSecret && receiveId))) {
        statusEl.innerHTML = '<div class="mm-status err">' + escHtml(_tr('feishu_save_requires_config')) + '</div>';
        return;
    }
    statusEl.innerHTML = '<div class="mm-status info">' + escHtml(_tr('feishu_saving_config')) + '</div>';
    fetch('/api/feishu-notification/config', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            feishuEnabled: enabled,
            feishuAppId: mmIsMaskedFeishuValue(appId) ? '' : appId,
            feishuAppSecret: mmIsMaskedFeishuValue(appSecret) ? '' : appSecret,
            feishuReceiveIdType: receiveIdType,
            feishuReceiveId: mmIsMaskedFeishuValue(receiveId) ? '' : receiveId,
            clearWebhook: true
        })
    }).then(function(r) {
        return r.json().then(function(d) { d._httpOk = r.ok; return d; });
        }).then(function(d) {
        if (!d.ok) {
            statusEl.innerHTML = '<div class="mm-status err">❌ ' + escHtml(d.error || _tr('feishu_save_failed')) + '</div>';
            return;
        }
        mmFillFeishuMaskedInputs(d);
        mmRenderFeishuMask(d);
        statusEl.innerHTML = '<div class="mm-status ok">✅ ' + escHtml(_tr('feishu_config_saved')) + '</div>';
    }).catch(function(e) {
        statusEl.innerHTML = '<div class="mm-status err">❌ ' + escHtml(e.message) + '</div>';
    });
}

function mmTestFeishuNotification() {
    var statusEl = document.getElementById('mm-feishu-status');
    if (!statusEl) return;
    statusEl.innerHTML = '<div class="mm-status info">' + escHtml(_tr('feishu_sending_test_cards')) + '</div>';
    fetch('/api/feishu-notification/test', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: '{}'
    }).then(function(r) {
        return r.json().then(function(d) { d._httpOk = r.ok; return d; });
        }).then(function(d) {
        if (!d.ok) {
            var detail = d.error || '';
            if (!detail && d.results && d.results.length) {
                var failed = d.results.find(function(r) { return !r.ok; }) || d.results[0];
                detail = failed.message || failed.error || failed.status || '';
                if (failed.code !== undefined && failed.code !== '') detail += ' (code: ' + failed.code + ')';
            }
            statusEl.innerHTML = '<div class="mm-status err">❌ ' + escHtml(detail || _tr('feishu_test_failed')) + '</div>';
            return;
        }
        statusEl.innerHTML = '<div class="mm-status ok">✅ ' + escHtml(_tr('feishu_test_cards_sent')) + '</div>';
    }).catch(function(e) {
        statusEl.innerHTML = '<div class="mm-status err">❌ ' + escHtml(e.message) + '</div>';
    });
}

function mmSaveSettings() {
    var gwUrl = document.getElementById('mm-gateway-url').value;
    var officeName = document.getElementById('mm-office-name').value;
    var weather = _buildWeatherLocation(
        document.getElementById('mm-weather-city').value,
        document.getElementById('mm-weather-state').value
    );

    // Save display prefs locally
    var _elBubbles = document.getElementById('mm-show-bubbles');
    var _elWeather = document.getElementById('mm-show-weather');
    var _elNames = document.getElementById('mm-show-names');
    var _elInternalTimeout = document.getElementById('mm-internal-bubble-timeout');
    var _elFontScale = document.getElementById('mm-font-scale');
    var fontScale = typeof VOFontScale !== 'undefined'
        ? VOFontScale.normalizeFontScale(_elFontScale ? _elFontScale.value : _displayPrefs.fontScale)
        : Number((_elFontScale || {}).value || 1);
    var displayPrefs = {
        showBubbles: _elBubbles ? _elBubbles.checked : true,
        showWeather: _elWeather ? _elWeather.checked : true,
        showNames: _elNames ? _elNames.checked : true,
        internalBubbleTimeoutSec: typeof InternalBubbleSettings !== 'undefined'
            ? InternalBubbleSettings.normalizeTimeoutSec(_elInternalTimeout ? _elInternalTimeout.value : 60)
            : 60,
        fontScale: fontScale,
    };
    localStorage.setItem('vo-display-prefs', JSON.stringify(displayPrefs));
    _displayPrefs = displayPrefs;
    if (typeof VOFontScale !== 'undefined') VOFontScale.applyFontScale(fontScale);

    // Build server config
    var ocPath = document.getElementById('mm-oc-path').value;
    var gwToken = (document.getElementById('mm-gateway-token') || {}).value || '';
    var config = {};
    config.openclaw = { gatewayUrl: gwUrl || 'ws://127.0.0.1:18789' };
    if (gwUrl) {
        config.openclaw.gatewayHttp = gwUrl.replace('ws://', 'http://').replace('wss://', 'https://').replace(/\/ws.*$/, '');
    }
    if (ocPath) config.openclaw.homePath = ocPath;
    if (gwToken) config.openclaw.gatewayToken = gwToken;
    var _hCb = document.getElementById('mm-hermes-enable');
    var _hHome = document.getElementById('mm-hermes-home');
    var _hBin = document.getElementById('mm-hermes-bin');
    var _hApiEnabled = document.getElementById('mm-hermes-api-enable');
    var _hApiUrl = document.getElementById('mm-hermes-api-url');
    var _hApiKey = document.getElementById('mm-hermes-api-key');
    if (_hCb) {
        var hermesSettings = {
            enabled: _hCb.checked,
            homePath: (_hHome ? _hHome.value.trim() : '') || null,
            binary: (_hBin ? _hBin.value.trim() : '') || null,
            apiEnabled: _hApiEnabled ? _hApiEnabled.checked : false,
            apiUrl: (_hApiUrl ? _hApiUrl.value.trim() : '') || null
        };
        if (_hApiKey && _hApiKey.value.trim()) config.hermes.apiKey = _hApiKey.value.trim();
    }
    var _codexCb = document.getElementById('mm-codex-enable');
    if (_codexCb) {
        config.codex = {
            enabled: _codexCb.checked,
            workspace: ((document.getElementById('mm-codex-workspace') || {}).value || '').trim() || null,
            workspaceRoot: ((document.getElementById('mm-codex-workspace-root') || {}).value || '').trim() || null,
            mainWorkspace: ((document.getElementById('mm-codex-main-workspace') || {}).value || '').trim() || null,
            model: ((document.getElementById('mm-codex-model') || {}).value || '').trim() || null,
            bridgeUrl: ((document.getElementById('mm-codex-bridge-url') || {}).value || '').trim() || null,
            includeMain: !!(document.getElementById('mm-codex-include-main') || {}).checked,
            includeNativeAgents: !!(document.getElementById('mm-codex-include-native') || {}).checked
        };
    }
    var _claudeCb = document.getElementById('mm-claude-code-enable');
    if (_claudeCb) {
        config.claudeCode = {
            enabled: _claudeCb.checked,
            homePath: ((document.getElementById('mm-claude-code-home') || {}).value || '').trim() || null,
            binary: ((document.getElementById('mm-claude-code-bin') || {}).value || '').trim() || null,
            workspace: ((document.getElementById('mm-claude-code-workspace') || {}).value || '').trim() || null,
            workspaceRoot: ((document.getElementById('mm-claude-code-workspace-root') || {}).value || '').trim() || null,
            mainWorkspace: ((document.getElementById('mm-claude-code-main-workspace') || {}).value || '').trim() || null,
            model: ((document.getElementById('mm-claude-code-model') || {}).value || '').trim() || null,
            includeMain: !!(document.getElementById('mm-claude-code-include-main') || {}).checked,
            includeNativeAgents: !!(document.getElementById('mm-claude-code-include-native') || {}).checked,
            registerNativeAgents: !!(document.getElementById('mm-claude-code-register-native') || {}).checked
        };
        var hermesApiKey = (_hApiKey ? _hApiKey.value.trim() : '');
        if (hermesApiKey) hermesSettings.apiKey = hermesApiKey;
        config.hermes = hermesSettings;
    }
    config.office = { name: officeName || 'Virtual Office' };
    config.weather = { location: weather || null };
    config.meetings = {
        preparingTimeoutSec: _mtgNormalizePreparingTimeoutSec((document.getElementById('mm-meeting-preparing-timeout') || {}).value)
    };
    // PC Metrics
    var _pcmCb = document.getElementById("mm-pcmetrics-enable");
    var _pcmUrl = document.getElementById("mm-pcmetrics-url");
    if (_pcmCb) {
        if (!config.features) config.features = {};
        config.features.pcMetrics = _pcmCb.checked;
        config.pcMetrics = { url: (_pcmUrl ? _pcmUrl.value.trim() : "") || null };
    }
    // API Usage
    var _apiCb = document.getElementById("mm-apiusage-enable");
    if (_apiCb) {
        if (!config.features) config.features = {};
        config.features.apiUsage = _apiCb.checked;
    }
    // Browser
    var _brCb = document.getElementById("mm-browser-enable");
    var _brCdp = document.getElementById("mm-cdp-url");
    var _brViewer = document.getElementById("mm-viewer-url");
    if (_brCb) {
        if (!config.features) config.features = {};
        config.features.browserPanel = _brCb.checked;
        config.browser = {
            cdpUrl: (_brCdp ? _brCdp.value.trim() : "") || null,
            viewerUrl: (_brViewer ? _brViewer.value.trim() : "") || null
        };
    }
    var _feishuCb = document.getElementById('mm-feishu-enable');
    if (_feishuCb) {
        config.notifications = {
            feishuEnabled: _feishuCb.checked,
            feishuReceiveIdType: ((document.getElementById('mm-feishu-receive-id-type') || {}).value || 'chat_id')
        };
        var _feishuAppIdValue = ((document.getElementById('mm-feishu-app-id') || {}).value || '').trim();
        var _feishuAppSecretValue = ((document.getElementById('mm-feishu-app-secret') || {}).value || '').trim();
        var _feishuReceiveIdValue = ((document.getElementById('mm-feishu-receive-id') || {}).value || '').trim();
        if (_feishuAppIdValue && !mmIsMaskedFeishuValue(_feishuAppIdValue)) config.notifications.feishuAppId = _feishuAppIdValue;
        if (_feishuAppSecretValue && !mmIsMaskedFeishuValue(_feishuAppSecretValue)) config.notifications.feishuAppSecret = _feishuAppSecretValue;
        if (_feishuReceiveIdValue && !mmIsMaskedFeishuValue(_feishuReceiveIdValue)) config.notifications.feishuReceiveId = _feishuReceiveIdValue;
    }

    fetch('/setup/save', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(config)
    }).then(function(r){ return r.json(); }).then(function(d) {
        if (d.ok) {
            _acpShowToast('💾 Settings saved! Hard refresh (Ctrl+Shift+R) to apply all changes.');
            _voWeatherLocation = (config.weather || {}).location || '';
            pollWeather();
            // Update brand title live
            var brandEl = document.getElementById('brand-title');
            if (brandEl && officeName) brandEl.textContent = officeName.toUpperCase();
            if (officeName) document.title = officeName;
            if (typeof window.setPcMonitorEnabled === 'function' && config.features && Object.prototype.hasOwnProperty.call(config.features, 'pcMetrics')) {
                window.setPcMonitorEnabled(config.features.pcMetrics === true);
            }
            if (typeof window.setApiUsageEnabled === 'function' && config.features && Object.prototype.hasOwnProperty.call(config.features, 'apiUsage')) {
                window.setApiUsageEnabled(config.features.apiUsage === true);
            }
        } else {
            _acpShowToast('❌ Save failed');
        }
    }).catch(function(e) {
        _acpShowToast('❌ Save failed: ' + e.message);
    });
}

function mmExportConfig() {
    var blob = new Blob([JSON.stringify(officeConfig, null, 2)], { type: 'application/json' });
    var url = URL.createObjectURL(blob);
    var a = document.createElement('a');
    a.href = url;
    a.download = 'virtual-office-config.json';
    a.click();
    URL.revokeObjectURL(url);
    _acpShowToast('📤 Config exported');
}

function mmImportConfig() {
    var fileInput = document.getElementById('mm-import-file');
    fileInput.onchange = function() {
        var file = fileInput.files[0];
        if (!file) return;
        var reader = new FileReader();
        reader.onload = function(e) {
            try {
                var imported = JSON.parse(e.target.result);
                if (!imported.canvasWidth && !imported.furniture) {
                    _acpShowToast('❌ Invalid config file');
                    return;
                }
    if (!confirm(_tr('import_config_confirm'))) return;
                // Merge imported config
                if (imported.canvasWidth) { W = imported.canvasWidth; officeConfig.canvasWidth = W; }
                if (imported.canvasHeight) { H = imported.canvasHeight; officeConfig.canvasHeight = H; }
                if (imported.walls) officeConfig.walls = imported.walls;
                if (imported.floor) officeConfig.floor = imported.floor;
                if (imported.furniture) officeConfig.furniture = imported.furniture;
                if (imported.agents) officeConfig.agents = imported.agents;
                if (imported.branches) officeConfig.branches = imported.branches;
                saveOfficeConfig();
                resizeCanvas(true);
                if (typeof buildCollisionGrid === 'function') buildCollisionGrid();
                if (typeof getInteractionSpots === 'function') getInteractionSpots();
                if (typeof _initAgentsFromDefs === 'function' && _rosterLoaded) _initAgentsFromDefs();
                _acpShowToast('📥 Config imported!');
            } catch (err) {
                _acpShowToast('❌ Invalid JSON: ' + err.message);
            }
        };
        reader.readAsText(file);
        fileInput.value = '';
    };
    fileInput.click();
}

function mmFullReset() {
    if (!confirm('⚠️ ' + _tr('full_reset_confirm'))) return;
    if (!confirm(_tr('reset_type_confirm'))) return;
    var input = prompt(_tr('type_reset'));
    if (input !== 'RESET') { _acpShowToast('Reset cancelled'); return; }

    // Clear everything
    localStorage.removeItem(OFFICE_CONFIG_KEY);
    fetch('/api/office-config', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: '{}'
    }).then(function() {
        _acpShowToast('🗑️ Office reset. Reloading...');
        setTimeout(function() { window.location.reload(); }, 1000);
    });
}


// Explicit compatibility exports for existing DOM handlers and external checks.
Object.assign(window, {
    toggleMainMenu: toggleMainMenu,
    _mmLoadCurrentSettings: _mmLoadCurrentSettings,
    mmApplyFontScaleSetting: mmApplyFontScaleSetting,
    mmTestHermes: mmTestHermes,
    mmTestSse: mmTestSse,
    mmTestCodex: mmTestCodex,
    mmTestClaudeCode: mmTestClaudeCode,
    mmTestCdp: mmTestCdp,
    mmTestViewer: mmTestViewer,
    mmTestPcMetrics: mmTestPcMetrics,
    mmTestConnection: mmTestConnection,
    mmTestWeather: mmTestWeather,
    mmRenderFeishuMask: mmRenderFeishuMask,
    mmIsMaskedFeishuValue: mmIsMaskedFeishuValue,
    mmFillFeishuMaskedInputs: mmFillFeishuMaskedInputs,
    mmRenderFeishuLongConnectionStatus: mmRenderFeishuLongConnectionStatus,
    mmSaveFeishuWebhook: mmSaveFeishuWebhook,
    mmTestFeishuNotification: mmTestFeishuNotification,
    mmSaveSettings: mmSaveSettings,
    mmExportConfig: mmExportConfig,
    mmImportConfig: mmImportConfig,
    mmFullReset: mmFullReset
});
