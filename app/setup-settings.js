var currentStep = 0;

function escapeHtml(value) {
    return String(value == null ? '' : value).replace(/[&<>"']/g, function(ch) {
        return ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'})[ch];
    });
}

function nextStep(n) {
    document.getElementById('step-' + currentStep).classList.remove('active');
    document.getElementById('step-' + n).classList.add('active');
    for (var i = 0; i <= 6; i++) {
        var dot = document.getElementById('dot-' + i);
        dot.className = 'dot';
        if (i < n) dot.className = 'dot done';
        if (i === n) dot.className = 'dot active';
    }
    currentStep = n;
    if (n === 0) checkExistingLicense();
    if (n === 2) discoverAgents();
}

function activateLicense() {
    var key = document.getElementById('s-license-key').value.trim();
    var statusEl = document.getElementById('license-status');
    if (!key) {
        statusEl.innerHTML = '<div class="status-box error">' + _t('setup_enter_license') + '</div>';
        return;
    }
    statusEl.innerHTML = '<div class="status-box info">' + _t('validating') + '</div>';
    fetch('/api/license/activate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ key: key })
    }).then(function(r) { return r.json(); }).then(function(d) {
        if (d.ok) {
            statusEl.innerHTML = '<div class="status-box success">' + _t('license_activated', { tier: d.tierName }) + '</div>';
        } else {
            statusEl.innerHTML = '<div class="status-box error">❌ ' + (d.error || _t('invalid_key')) + '</div>';
        }
    }).catch(function(e) {
        statusEl.innerHTML = '<div class="status-box error">' + _t('error') + ': ' + e.message + '</div>';
    });
}

function checkExistingLicense() {
    fetch('/api/license').then(function(r) { return r.json(); }).then(function(d) {
        if (d.licensed) {
            document.getElementById('license-status').innerHTML =
                '<div class="status-box success">' + _esc(_t('license_active', { tier: d.tierName })) + '</div>';
        }
    }).catch(function(){});
}
checkExistingLicense();
window.addEventListener('i18n:ready', checkExistingLicense);
window.addEventListener('i18n:changed', checkExistingLicense);

var DEFAULT_BROWSER_CDP_URL = 'http://127.0.0.1:9224';
var DEFAULT_BROWSER_VIEWER_URL = 'https://localhost:6901';

function populateDefaultBrowserUrls() {
    var cdpInput = document.getElementById('s-cdp-url');
    var viewerInput = document.getElementById('s-viewer-url');
    if (cdpInput && !cdpInput.value.trim()) cdpInput.value = DEFAULT_BROWSER_CDP_URL;
    if (viewerInput && !viewerInput.value.trim()) viewerInput.value = DEFAULT_BROWSER_VIEWER_URL;
}
populateDefaultBrowserUrls();

// Browser enable toggle
document.getElementById('s-browser-enable').addEventListener('change', function() {
    document.getElementById('browser-fields').style.display = this.checked ? 'block' : 'none';
    if (this.checked) populateDefaultBrowserUrls();
});

// SMS enable toggle
document.getElementById('s-sms-enable').addEventListener('change', function() {
    document.getElementById('sms-fields').style.display = this.checked ? 'block' : 'none';
    if (this.checked) populateSmsAgentSelect();
});

// PC Metrics enable toggle
document.getElementById('s-pcmetrics-enable').addEventListener('change', function() {
    document.getElementById('pcmetrics-fields').style.display = this.checked ? 'block' : 'none';
});

// Hermes enable toggle
document.getElementById('s-hermes-enable').addEventListener('change', function() {
    document.getElementById('hermes-fields').style.display = this.checked ? 'block' : 'none';
});
document.getElementById('s-codex-enable').addEventListener('change', function() {
    document.getElementById('codex-fields').style.display = this.checked ? 'block' : 'none';
});
document.getElementById('s-claude-enable').addEventListener('change', function() {
    document.getElementById('claude-fields').style.display = this.checked ? 'block' : 'none';
});

// Pre-populate provider fields from current config
fetch('/vo-config').then(function(r) { return r.json(); }).then(function(cfg) {
    var h = cfg.hermes || {};
    var hEnable = document.getElementById('s-hermes-enable');
    var hHome = document.getElementById('s-hermes-home');
    var hBin = document.getElementById('s-hermes-bin');
    var hApiEnable = document.getElementById('s-hermes-api-enable');
    var hApiUrl = document.getElementById('s-hermes-api-url');
    if (hEnable) hEnable.checked = h.enabled !== false;
    if (hHome && h.homePath) hHome.value = h.homePath;
    if (hBin && h.binary) hBin.value = h.binary;
    if (hApiEnable) hApiEnable.checked = h.apiEnabled === true || h.preferApi === true;
    if (hApiUrl && h.apiUrl) hApiUrl.value = h.apiUrl;
    var hFields = document.getElementById('hermes-fields');
    if (hFields && hEnable) hFields.style.display = hEnable.checked ? 'block' : 'none';
    var c = cfg.codex || {};
    var cEnable = document.getElementById('s-codex-enable');
    if (cEnable) cEnable.checked = c.enabled === true;
    if (document.getElementById('s-codex-home')) document.getElementById('s-codex-home').value = c.homePath || '';
    if (document.getElementById('s-codex-bin')) document.getElementById('s-codex-bin').value = c.binary || '';
    if (document.getElementById('s-codex-workspace-root')) document.getElementById('s-codex-workspace-root').value = c.workspaceRoot || '';
    if (document.getElementById('s-codex-main-workspace')) document.getElementById('s-codex-main-workspace').value = c.mainWorkspace || '';
    if (document.getElementById('s-codex-model')) document.getElementById('s-codex-model').value = c.model || '';
    if (document.getElementById('s-codex-sandbox')) document.getElementById('s-codex-sandbox').value = c.sandbox || 'workspace-write';
    if (document.getElementById('s-codex-approval')) document.getElementById('s-codex-approval').value = c.approvalPolicy || 'never';
    if (document.getElementById('s-codex-main')) document.getElementById('s-codex-main').checked = c.includeMain !== false;
    if (document.getElementById('s-codex-native')) document.getElementById('s-codex-native').checked = c.includeNativeAgents !== false;
    if (document.getElementById('s-codex-register')) document.getElementById('s-codex-register').checked = c.registerNativeAgents !== false;
    if (document.getElementById('s-codex-appserver')) document.getElementById('s-codex-appserver').checked = c.preferAppServer !== false;
    var cFields = document.getElementById('codex-fields');
    if (cFields && cEnable) cFields.style.display = cEnable.checked ? 'block' : 'none';
    var cc = cfg.claudeCode || {};
    var ccEnable = document.getElementById('s-claude-enable');
    if (ccEnable) ccEnable.checked = cc.enabled === true;
    if (document.getElementById('s-claude-home')) document.getElementById('s-claude-home').value = cc.homePath || '';
    if (document.getElementById('s-claude-bin')) document.getElementById('s-claude-bin').value = cc.binary || '';
    if (document.getElementById('s-claude-workspace-root')) document.getElementById('s-claude-workspace-root').value = cc.workspaceRoot || '';
    if (document.getElementById('s-claude-main-workspace')) document.getElementById('s-claude-main-workspace').value = cc.mainWorkspace || '';
    if (document.getElementById('s-claude-model')) document.getElementById('s-claude-model').value = cc.model || '';
    if (document.getElementById('s-claude-permission')) document.getElementById('s-claude-permission').value = cc.permissionMode || 'acceptEdits';
    if (document.getElementById('s-claude-main')) document.getElementById('s-claude-main').checked = cc.includeMain !== false;
    if (document.getElementById('s-claude-native')) document.getElementById('s-claude-native').checked = cc.includeNativeAgents !== false;
    if (document.getElementById('s-claude-register')) document.getElementById('s-claude-register').checked = cc.registerNativeAgents !== false;
    var ccFields = document.getElementById('claude-fields');
    if (ccFields && ccEnable) ccFields.style.display = ccEnable.checked ? 'block' : 'none';
    var n = cfg.notifications || {};
    var fEnable = document.getElementById('s-feishu-enable');
    if (fEnable) fEnable.checked = n.feishuEnabled !== false;
    fillFeishuMaskedInputs(n);
    renderFeishuWebhookMask(n);
}).catch(function(){});

function isMaskedFeishuValue(value) {
    return String(value || '').indexOf('••••') >= 0;
}

function fillFeishuMaskedInputs(cfg) {
    cfg = cfg || {};
    if (document.getElementById('s-feishu-app-id')) document.getElementById('s-feishu-app-id').value = cfg.maskedFeishuAppId || '';
    if (document.getElementById('s-feishu-app-secret')) document.getElementById('s-feishu-app-secret').value = cfg.feishuAppConfigured ? '••••••••' : '';
    if (document.getElementById('s-feishu-receive-id')) document.getElementById('s-feishu-receive-id').value = cfg.maskedFeishuReceiveId || '';
    if (document.getElementById('s-feishu-receive-id-type')) document.getElementById('s-feishu-receive-id-type').value = cfg.feishuReceiveIdType || 'chat_id';
    renderFeishuLongConnectionStatus(cfg);
}

function renderFeishuLongConnectionStatus(cfg) {
    var el = document.getElementById('s-feishu-long-connection-status');
    if (!el) return;
    var lc = (cfg || {}).feishuLongConnection || {};
    var status = lc.status || 'not_started';
    el.textContent = _t('feishu_long_connection_status', { status: status });
    el.style.color = lc.running ? '#81c784' : (status === 'error' ? '#ff8a80' : '#888');
}

function renderFeishuWebhookMask(cfg) {
    var el = document.getElementById('feishu-webhook-mask');
    if (!el) return;
    cfg = cfg || {};
    if (cfg.feishuAppConfigured) {
        el.textContent = _t('feishu_configured_app', {
            appId: cfg.maskedFeishuAppId || '••••••••',
            receiveIdType: cfg.feishuReceiveIdType || 'chat_id',
            receiveId: cfg.maskedFeishuReceiveId || '••••••••'
        });
        el.style.color = '#81c784';
    } else {
        el.textContent = _t('feishu_not_configured');
        el.style.color = '#888';
    }
}

function loadFeishuWebhookConfig() {
    fetch('/api/feishu-notification/config').then(function(r) { return r.json(); }).then(function(d) {
        if (document.getElementById('s-feishu-enable')) document.getElementById('s-feishu-enable').checked = d.feishuEnabled !== false;
        fillFeishuMaskedInputs(d);
        renderFeishuWebhookMask(d);
    }).catch(function(){});
}
loadFeishuWebhookConfig();

function saveFeishuWebhook() {
    var enabled = document.getElementById('s-feishu-enable').checked;
    var appId = document.getElementById('s-feishu-app-id').value.trim();
    var appSecret = document.getElementById('s-feishu-app-secret').value.trim();
    var receiveIdType = document.getElementById('s-feishu-receive-id-type').value || 'chat_id';
    var receiveId = document.getElementById('s-feishu-receive-id').value.trim();
    var statusEl = document.getElementById('feishu-test-status');
    var appConfigured = isMaskedFeishuValue(appId) && isMaskedFeishuValue(appSecret) && isMaskedFeishuValue(receiveId);
    if (!(appConfigured || (appId && appSecret && receiveId))) {
        statusEl.innerHTML = '<div class="status-box error">' + _esc(_t('feishu_save_requires_config')) + '</div>';
        return;
    }
    statusEl.innerHTML = '<div class="status-box info">' + _esc(_t('feishu_saving_config')) + '</div>';
    fetch('/api/feishu-notification/config', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            feishuEnabled: enabled,
            feishuAppId: isMaskedFeishuValue(appId) ? '' : appId,
            feishuAppSecret: isMaskedFeishuValue(appSecret) ? '' : appSecret,
            feishuReceiveIdType: receiveIdType,
            feishuReceiveId: isMaskedFeishuValue(receiveId) ? '' : receiveId,
            clearWebhook: true
        })
    }).then(function(r) { return r.json().then(function(d) { d._httpOk = r.ok; return d; }); }).then(function(d) {
        if (!d.ok) {
            statusEl.innerHTML = '<div class="status-box error">❌ ' + _esc(d.error || _t('feishu_save_failed')) + '</div>';
            return;
        }
        fillFeishuMaskedInputs(d);
        renderFeishuWebhookMask(d);
        statusEl.innerHTML = '<div class="status-box success">✅ ' + _esc(_t('feishu_config_saved')) + '</div>';
    }).catch(function(e) {
        statusEl.innerHTML = '<div class="status-box error">Error: ' + _esc(e.message) + '</div>';
    });
}

function testFeishuNotification() {
    var statusEl = document.getElementById('feishu-test-status');
    statusEl.innerHTML = '<div class="status-box info">' + _esc(_t('feishu_sending_test_cards')) + '</div>';
    fetch('/api/feishu-notification/test', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: '{}'
    }).then(function(r) { return r.json().then(function(d) { d._httpOk = r.ok; return d; }); }).then(function(d) {
        if (!d.ok) {
            var detail = d.error || '';
            if (!detail && d.results && d.results.length) {
                var failed = d.results.find(function(r) { return !r.ok; }) || d.results[0];
                detail = failed.message || failed.error || failed.status || '';
                if (failed.code !== undefined && failed.code !== '') detail += ' (code: ' + failed.code + ')';
            }
            statusEl.innerHTML = '<div class="status-box error">❌ ' + _esc(detail || _t('feishu_test_failed')) + '</div>';
            return;
        }
        statusEl.innerHTML = '<div class="status-box success">✅ ' + _esc(_t('feishu_test_cards_sent')) + '</div>';
    }).catch(function(e) {
        statusEl.innerHTML = '<div class="status-box error">Error: ' + _esc(e.message) + '</div>';
    });
}

function testPcMetrics() {
    var url = document.getElementById('s-pcmetrics-url').value.trim();
    var statusEl = document.getElementById('pcmetrics-test-status');
    if (!url) {
        statusEl.innerHTML = '<div class="status-box error">' + _t('enter_metrics_url') + '</div>';
        return;
    }
    statusEl.innerHTML = '<div class="status-box info">' + _t('saving_testing') + '</div>';
    // Save config so server can proxy
    fetch('/setup/save', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ features: { pcMetrics: true }, pcMetrics: { url: url } })
    }).then(function() {
        return fetch('/pc-metrics');
    }).then(function(r) { return r.json(); }).then(function(data) {
        if (data.error) {
            statusEl.innerHTML = '<div class="status-box error">❌ ' + data.error + '</div>';
        } else if (data.cpu) {
            var info = 'CPU: ' + (data.cpu.percent || 0).toFixed(0) + '% (' + (data.cpu.threads || '?') + ' threads)';
            info += ' · RAM: ' + (data.memory.percent || 0).toFixed(0) + '%';
            if (data.gpus && data.gpus.length > 0) info += ' · GPU: ' + _esc(data.gpus[0].name);
            statusEl.innerHTML = '<div class="status-box success">' + _t('connected_label') + '<br>' + info + '</div>';
        } else {
            statusEl.innerHTML = '<div class="status-box error">❌ ' + _t('unexpected_response') + '</div>';
        }
    }).catch(function(e) {
        statusEl.innerHTML = '<div class="status-box error">' + _t('error') + ': ' + e.message + '</div>';
    });
}

function testHermesConnection() {
    var enabled = document.getElementById('s-hermes-enable').checked;
    var homePath = document.getElementById('s-hermes-home').value.trim();
    var binary = document.getElementById('s-hermes-bin').value.trim();
    var apiEnabled = document.getElementById('s-hermes-api-enable').checked;
    var apiUrl = document.getElementById('s-hermes-api-url').value.trim();
    var apiKey = document.getElementById('s-hermes-api-key').value.trim();
    var statusEl = document.getElementById('hermes-test-status');
    if (!enabled) {
        statusEl.innerHTML = '<div class="status-box info">' + _t('hermes_disabled') + '</div>';
        return;
    }
    statusEl.innerHTML = '<div class="status-box info">' + _t('testing_hermes') + '</div>';
    var hermesSave = { enabled: enabled, homePath: homePath || null, binary: binary || null, apiEnabled: apiEnabled, preferApi: apiEnabled, apiUrl: apiUrl || null };
    if (apiKey) hermesSave.apiKey = apiKey;
    fetch('/setup/save', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ hermes: hermesSave })
    }).then(function() {
        return fetch('/api/hermes/test', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ homePath: homePath || null, binary: binary || null, apiEnabled: apiEnabled, preferApi: apiEnabled, apiUrl: apiUrl || null, apiKey: apiKey || undefined })
        });
    }).then(function(r) { return r.json(); }).then(function(d) {
        if (d.ok) {
            var agents = d.agents || [];
            var api = d.api || {};
            var apiLine = apiEnabled ? '<br>Native API: ' + (api.ok ? 'connected' : ('unavailable' + (api.error ? ' · ' + _esc(api.error) : ''))) : '';
            var html = '<div class="status-box success">' + _t('hermes_connected_profiles', { count: agents.length }) + apiLine + '</div>';
            if (agents.length) {
                html += '<div class="agent-list-preview">';
                agents.slice(0, 10).forEach(function(a) {
                    html += '<div class="agent-row"><span class="emoji">' + _esc(a.emoji || '⚕️') + '</span><span class="name">' + _esc(a.name) + '</span><span class="role">' + _esc(a.model || a.providerAgentId || 'Hermes') + '</span></div>';
                });
                html += '</div>';
            }
            statusEl.innerHTML = html;
        } else {
            statusEl.innerHTML = '<div class="status-box error">❌ ' + _t('hermes_not_reachable') + ': ' + (d.error || _t('unknown')) + '</div>';
        }
    }).catch(function(e) {
        statusEl.innerHTML = '<div class="status-box error">' + _t('error') + ': ' + e.message + '</div>';
    });
}

function codexPayloadFromSetup() {
    return {
        enabled: document.getElementById('s-codex-enable').checked,
        homePath: document.getElementById('s-codex-home').value.trim() || null,
        binary: document.getElementById('s-codex-bin').value.trim() || null,
        workspaceRoot: document.getElementById('s-codex-workspace-root').value.trim() || null,
        mainWorkspace: document.getElementById('s-codex-main-workspace').value.trim() || null,
        model: document.getElementById('s-codex-model').value.trim() || '',
        sandbox: document.getElementById('s-codex-sandbox').value || 'workspace-write',
        approvalPolicy: document.getElementById('s-codex-approval').value || 'never',
        preferAppServer: document.getElementById('s-codex-appserver').checked,
        includeMain: document.getElementById('s-codex-main').checked,
        includeNativeAgents: document.getElementById('s-codex-native').checked,
        registerNativeAgents: document.getElementById('s-codex-register').checked
    };
}

function claudeCodePayloadFromSetup() {
    return {
        enabled: document.getElementById('s-claude-enable').checked,
        homePath: document.getElementById('s-claude-home').value.trim() || null,
        binary: document.getElementById('s-claude-bin').value.trim() || null,
        workspaceRoot: document.getElementById('s-claude-workspace-root').value.trim() || null,
        mainWorkspace: document.getElementById('s-claude-main-workspace').value.trim() || null,
        model: document.getElementById('s-claude-model').value.trim() || '',
        permissionMode: document.getElementById('s-claude-permission').value || 'acceptEdits',
        includeMain: document.getElementById('s-claude-main').checked,
        includeNativeAgents: document.getElementById('s-claude-native').checked,
        registerNativeAgents: document.getElementById('s-claude-register').checked
    };
}

function testCodexConnection() {
    var payload = codexPayloadFromSetup();
    var statusEl = document.getElementById('codex-test-status');
    if (!payload.enabled) {
        statusEl.innerHTML = '<div class="status-box info">Codex auto-detect is disabled.</div>';
        return;
    }
    statusEl.innerHTML = '<div class="status-box info">Saving and testing Codex...</div>';
    fetch('/setup/save', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ codex: payload })
    }).then(function() {
        return fetch('/api/codex/test', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });
    }).then(function(r) { return r.json(); }).then(function(d) {
        if (d.ok) {
            var agents = d.agents || [];
            statusEl.innerHTML = '<div class="status-box success">✅ Codex connected — ' + _esc(d.protocol || 'codex') + ' · found ' + agents.length + ' agent' + (agents.length === 1 ? '' : 's') + '</div>';
        } else {
            statusEl.innerHTML = '<div class="status-box error">❌ Codex not reachable: ' + _esc(d.error || 'unknown error') + '</div>';
        }
    }).catch(function(e) {
        statusEl.innerHTML = '<div class="status-box error">Error: ' + _esc(e.message) + '</div>';
    });
}

function testClaudeCodeConnection() {
    var payload = claudeCodePayloadFromSetup();
    var statusEl = document.getElementById('claude-test-status');
    if (!payload.enabled) {
        statusEl.innerHTML = '<div class="status-box info">Claude Code auto-detect is disabled.</div>';
        return;
    }
    statusEl.innerHTML = '<div class="status-box info">Saving and testing Claude Code...</div>';
    fetch('/setup/save', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ claudeCode: payload })
    }).then(function() {
        return fetch('/api/claude-code/test', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });
    }).then(function(r) { return r.json(); }).then(function(d) {
        if (d.ok) {
            var agents = d.agents || [];
            statusEl.innerHTML = '<div class="status-box success">✅ Claude Code connected — found ' + agents.length + ' agent' + (agents.length === 1 ? '' : 's') + '</div>';
        } else {
            statusEl.innerHTML = '<div class="status-box error">❌ Claude Code not reachable: ' + _esc(d.error || 'unknown error') + '</div>';
        }
    }).catch(function(e) {
        statusEl.innerHTML = '<div class="status-box error">Error: ' + _esc(e.message) + '</div>';
    });
}

function populateSmsAgentSelect() {
    var sel = document.getElementById('s-sms-agent');
    if (sel.options.length > 1) return; // already populated
    fetch('/api/agents').then(function(r) { return r.json(); }).then(function(d) {
        (d.agents || []).forEach(function(a) {
            var opt = document.createElement('option');
            opt.value = a.key || a.agentId;
            opt.textContent = (a.emoji || '🤖') + ' ' + a.name;
            sel.appendChild(opt);
        });
    }).catch(function() {});
}

function testBrowserConnection() {
    var cdpUrl = document.getElementById('s-cdp-url').value.trim();
    var viewerUrl = document.getElementById('s-viewer-url').value.trim();
    var statusEl = document.getElementById('browser-test-status');
    if (!cdpUrl) {
        statusEl.innerHTML = '<div class="status-box error">' + _t('enter_cdp_url') + '</div>';
        return;
    }
    if (!viewerUrl) {
        statusEl.innerHTML = '<div class="status-box error">' + _t('enter_viewer_url') + '</div>';
        return;
    }
    statusEl.innerHTML = '<div class="status-box info">' + _t('saving_testing') + '</div>';
    // Save browser config first so server can test it
    fetch('/setup/save', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            features: { browserPanel: true },
            browser: { cdpUrl: cdpUrl, viewerUrl: viewerUrl || null }
        })
    }).then(function() {
        return fetch('/browser-status');
    }).then(function(r) { return r.json(); }).then(function(data) {
        if (data.cdpAvailable) {
            statusEl.innerHTML = '<div class="status-box success">' + _t('cdp_connected') + '</div>';
        } else {
            statusEl.innerHTML = '<div class="status-box error">❌ ' + _t('cdp_not_reachable') + ': ' + cdpUrl + '</div>';
        }
    }).catch(function(e) {
        statusEl.innerHTML = '<div class="status-box error">' + _t('error') + ': ' + e.message + '</div>';
    });
}

function savePathAndDetect() {
    var path = document.getElementById('s-ocpath').value.trim();
    if (!path) {
        document.getElementById('agent-status').innerHTML = '<div class="status-box error">' + _t('enter_path') + '</div>';
        return;
    }
    document.getElementById('agent-status').innerHTML = '<div class="status-box info">' + _t('saving_detecting') + '</div>';
    fetch('/setup/save', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ openclaw: { homePath: path } })
    }).then(function(r) { return r.json(); }).then(function() {
        // Now re-detect with the new path
        discoverAgents();
    }).catch(function(e) {
        document.getElementById('agent-status').innerHTML = '<div class="status-box error">' + _t('save_failed') + ': ' + _esc(e.message) + '</div>';
    });
}

function discoverAgents() {
    var statusEl = document.getElementById('agent-status');
    var previewEl = document.getElementById('agent-preview');
    var helpEl = document.getElementById('no-agents-help');
    var gwSection = document.getElementById('gateway-config-section');

    // Pre-populate path field from current config
    fetch('/vo-config').then(function(r) { return r.json(); }).then(function(cfg) {
        var pathInput = document.getElementById('s-ocpath');
        if (pathInput && !pathInput.value && cfg.openclaw && cfg.openclaw.homePath) {
            pathInput.value = cfg.openclaw.homePath;
        }
    }).catch(function(){});

    statusEl.innerHTML = '<div class="status-box info">' + _t('looking_for_agents') + '</div>';
    helpEl.style.display = 'none';
    if (gwSection) gwSection.style.display = 'none';

    fetch('/api/agents').then(function(r) { return r.json(); }).then(function(d) {
        var agents = d.agents || [];
        if (agents.length > 0) {
            statusEl.innerHTML = '<div class="status-box success">' + _t('agents_found', { count: agents.length }) + '</div>';
            helpEl.style.display = 'none';
            if (gwSection) gwSection.style.display = 'block';
            // Auto-populate gateway token
            fetch('/gateway-info').then(function(r) { return r.json(); }).then(function(gi) {
                var tokenInput = document.getElementById('s-gateway-token');
                if (tokenInput && !tokenInput.value && gi.token) tokenInput.value = gi.token;
            }).catch(function(){});
        } else {
            statusEl.innerHTML = '<div class="status-box error" style="border-color:#f4a236;background:rgba(244,162,54,0.1);color:#f4c36a;">⚠️ ' + _t('no_agents_path') + '</div>';
            helpEl.style.display = 'block';
        }
        previewEl.innerHTML = '';
        agents.forEach(function(a) {
            var row = document.createElement('div');
            row.className = 'agent-row';
            row.innerHTML = '<span class="emoji">' + _esc(a.emoji || '🤖') + '</span>' +
                '<span class="name">' + _esc(a.name) + '</span>' +
                '<span class="role">' + _esc(a.role || a.id) + '</span>';
            previewEl.appendChild(row);
        });
    }).catch(function(e) {
        statusEl.innerHTML = '<div class="status-box error">' + _t('server_unreachable') + ': ' + e.message + '</div>';
        helpEl.style.display = 'block';
    });
}

function configureGateway() {
    var statusEl = document.getElementById('gateway-config-status');
    var origin = location.protocol + '//' + location.hostname + (location.port ? ':' + location.port : '');
    statusEl.innerHTML = '<div class="status-box info">' + _t('configuring_gateway') + '</div>';

    fetch('/api/gateway/configure', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ origin: origin })
    }).then(function(r) { return r.json(); }).then(function(d) {
        if (!d.ok) {
            statusEl.innerHTML = '<div class="status-box error">❌ ' + _t('configure_failed') + ': ' + (d.error || _t('unknown')) + '</div>';
            return;
        }
        var addedMsg = d.added ? _t('gateway_origin_added') : _t('gateway_origin_exists');
        statusEl.innerHTML = '<div class="status-box info">✅ ' + addedMsg + ' ' + _t('testing_connection') + '</div>';

        return fetch('/api/gateway/test').then(function(r) { return r.json(); }).then(function(t) {
            var lines = [];
            if (t.gateway === 'reachable') {
                lines.push('✅ ' + _t('gateway_reachable'));
            } else {
                lines.push('❌ ' + _t('gateway_unreachable') + ': ' + _esc(t.gateway || 'unreachable'));
                lines.push('<div class="note" style="margin-top:10px;border-color:#f4a236;">' + _t('gateway_running_hint') + '</div>');
            }
            if (t.token === true) {
                lines.push('✅ ' + _t('gateway_token_found'));
            } else if (t.gateway === 'reachable') {
                lines.push('❌ ' + _t('gateway_token_failed') + ': ' + _esc(t.error || 'auth failed'));
            }
            if (typeof t.agents === 'number') {
                lines.push((t.agents > 0 ? '✅ ' : '⚠️ ') + _t('gateway_agents_connected', { count: t.agents }));
            }
            var boxClass = (t.gateway === 'reachable' && t.token) ? 'success' : 'error';
            statusEl.innerHTML = '<div class="status-box ' + boxClass + '">' + lines.join('<br>') + '</div>';
        });
    }).catch(function(e) {
        statusEl.innerHTML = '<div class="status-box error">' + _t('error') + ': ' + e.message + '</div>';
    });
}

function _buildWeatherLocation(city, state) {
    city = (city || '').trim();
    state = (state || '').trim();
    if (!city) return null;
    // Format: City,State (no spaces — wttr.in friendly)
    return state ? city.replace(/ /g, '+') + ',' + state.replace(/ /g, '+') : city.replace(/ /g, '+');
}

function testSetupWeather() {
    var statusEl = document.getElementById('s-weather-status');
    var location = _buildWeatherLocation(
        document.getElementById('s-weather-city').value,
        document.getElementById('s-weather-state').value
    );
    if (!location) {
        statusEl.innerHTML = '<div class="status-box error">' + _t('weather_test_location_required') + '</div>';
        return;
    }
    statusEl.innerHTML = '<div class="status-box info">' + _t('testing_weather') + '</div>';
    fetch('/api/weather/test?location=' + encodeURIComponent(location))
        .then(function(r) { return r.json().then(function(d) { d._httpOk = r.ok; return d; }); })
        .then(function(d) {
            if (!d.ok) {
                statusEl.innerHTML = '<div class="status-box error">❌ ' + _t('weather_test_failed') + ': ' + _esc(d.error || _t('unknown')) + '</div>';
                return;
            }
            var details = _esc(d.resolvedLocation || location) + ' · ' + _esc(d.weather || '') + ' · ' + _esc(String(d.tempF || '?')) + '°F / ' + _esc(String(d.tempC || '?')) + '°C';
            statusEl.innerHTML = '<div class="status-box success">✅ ' + _t('weather_test_ok') + '<br>' + details + '</div>';
        }).catch(function(e) {
            statusEl.innerHTML = '<div class="status-box error">❌ ' + _t('weather_test_failed') + ': ' + _esc(e.message) + '</div>';
        });
}

function finishSetup() {
    var browserEnabled = document.getElementById('s-browser-enable').checked;
    var smsEnabled = document.getElementById('s-sms-enable').checked;
    var pcMetricsEnabled = document.getElementById('s-pcmetrics-enable').checked;
    var hermesEnabled = document.getElementById('s-hermes-enable').checked;
    var gwToken = (document.getElementById('s-gateway-token') || {}).value || '';
    var feishuAppId = document.getElementById('s-feishu-app-id').value.trim();
    var feishuAppSecret = document.getElementById('s-feishu-app-secret').value.trim();
    var feishuReceiveId = document.getElementById('s-feishu-receive-id').value.trim();
    var config = {
        office: { name: document.getElementById('s-name').value || 'Virtual Office' },
        weather: { location: _buildWeatherLocation(document.getElementById('s-weather-city').value, document.getElementById('s-weather-state').value) },
        features: {
            browserPanel: browserEnabled,
            smsPanel: smsEnabled,
            pcMetrics: pcMetricsEnabled,
            apiUsage: false
        },
        browser: browserEnabled ? {
            cdpUrl: document.getElementById('s-cdp-url').value.trim() || null,
            viewerUrl: document.getElementById('s-viewer-url').value.trim() || null
        } : { cdpUrl: null, viewerUrl: null },
        sms: smsEnabled ? {
            ownerAgentId: document.getElementById('s-sms-agent').value || null,
            agentId: document.getElementById('s-sms-agent').value || null,
            twilioAccountSid: document.getElementById('s-twilio-sid').value.trim() || null,
            twilioAuthToken: document.getElementById('s-twilio-token').value.trim() || null,
            fromNumber: document.getElementById('s-twilio-from').value.trim() || null
        } : {},
        pcMetrics: pcMetricsEnabled ? {
            url: document.getElementById('s-pcmetrics-url').value.trim() || null
        } : {},
        notifications: (function() {
            var n = {
                feishuEnabled: document.getElementById('s-feishu-enable').checked,
                feishuReceiveIdType: document.getElementById('s-feishu-receive-id-type').value || 'chat_id'
            };
            if (feishuAppId && !isMaskedFeishuValue(feishuAppId)) n.feishuAppId = feishuAppId;
            if (feishuAppSecret && !isMaskedFeishuValue(feishuAppSecret)) n.feishuAppSecret = feishuAppSecret;
            if (feishuReceiveId && !isMaskedFeishuValue(feishuReceiveId)) n.feishuReceiveId = feishuReceiveId;
            return n;
        })(),
        hermes: (function() {
            var apiEnabled = document.getElementById('s-hermes-api-enable').checked;
            var h = {
                enabled: hermesEnabled,
                homePath: document.getElementById('s-hermes-home').value.trim() || null,
                binary: document.getElementById('s-hermes-bin').value.trim() || null,
                apiEnabled: apiEnabled,
                preferApi: apiEnabled,
                apiUrl: document.getElementById('s-hermes-api-url').value.trim() || null
            };
            var apiKey = document.getElementById('s-hermes-api-key').value.trim();
            if (apiKey) h.apiKey = apiKey;
            return h;
        })(),
        codex: codexPayloadFromSetup(),
        claudeCode: claudeCodePayloadFromSetup(),
        _setupComplete: true
    };

    var statusEl = document.getElementById('save-status');
    statusEl.innerHTML = '<div class="status-box info">' + _t('saving') + '</div>';

    fetch('/setup/save', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(config)
    }).then(function(r) { return r.json(); }).then(function(d) {
        if (d.ok) {
            statusEl.innerHTML = '<div class="status-box success">' + _t('launching_office') + '</div>';
            setTimeout(function() { window.location.href = '/'; }, 1000);
        } else {
            statusEl.innerHTML = '<div class="status-box error">' + _t('save_failed') + '</div>';
        }
    }).catch(function(e) {
        statusEl.innerHTML = '<div class="status-box error">' + _t('error') + ': ' + e.message + '</div>';
    });
}


// Explicit compatibility exports for existing inline handlers and external checks.
Object.assign(window, {
    nextStep: nextStep,
    activateLicense: activateLicense,
    checkExistingLicense: checkExistingLicense,
    saveFeishuWebhook: saveFeishuWebhook,
    testFeishuNotification: testFeishuNotification,
    testPcMetrics: testPcMetrics,
    testHermesConnection: testHermesConnection,
    testCodexConnection: testCodexConnection,
    testClaudeCodeConnection: testClaudeCodeConnection,
    testBrowserConnection: testBrowserConnection,
    savePathAndDetect: savePathAndDetect,
    discoverAgents: discoverAgents,
    configureGateway: configureGateway,
    testSetupWeather: testSetupWeather,
    finishSetup: finishSetup
});
