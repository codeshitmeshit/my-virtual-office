// API Usage Monitor — shows real quota data from API/OAuth providers
(function() {
    const _t = (key) => typeof i18n !== 'undefined' ? i18n.t(key) : key;
    const USAGE_URL = '/api-usage';
    const VO_USAGE_URL = '/api/vo-usage';
    const POLL_INTERVAL = 30000;

    const PROVIDER_COLORS = {
        anthropic: '#d4a0ff',
        openai: '#74d680',
        'openai-codex': '#74d680',
        google: '#4fc3f7',
        'github-copilot': '#f0f0f0',
        deepseek: '#80deea',
        groq: '#ef9a9a',
        minimax: '#ffab91',
        'z.ai': '#ce93d8',
        antigravity: '#a5d6a7',
    };
    const DEFAULT_COLOR = '#aaa';

    let _open = true;
    let _pollTimer = null;
    let _enabled = false;
    let _activeTab = 'account';
    let _lastVoUsage = null;

    window.toggleApiUsage = function() {
        if (!_enabled) {
            stopPolling();
            return;
        }
        _open = !_open;
        const body = document.getElementById('api-usage-body');
        const arrow = document.getElementById('api-toggle-arrow');
        body.style.display = _open ? 'block' : 'none';
        arrow.textContent = _open ? '▼' : '▶';
        if (_open && !_pollTimer) startPolling();
        if (!_open && _pollTimer) stopPolling();
    };

    window.setApiUsageTab = function(tab) {
        _activeTab = ['account', 'agent', 'model', 'records'].includes(tab) ? tab : 'account';
        const account = document.getElementById('api-usage-cards');
        const vo = document.getElementById('vo-usage-cards');
        if (account) account.style.display = _activeTab === 'account' ? '' : 'none';
        if (vo) vo.style.display = _activeTab === 'account' ? 'none' : '';
        for (const item of [
            ['account', 'api-account-tab'],
            ['agent', 'api-agent-tab'],
            ['model', 'api-model-tab'],
            ['records', 'api-records-tab'],
        ]) {
            const el = document.getElementById(item[1]);
            if (el) el.classList.toggle('active', _activeTab === item[0]);
        }
        if (_activeTab !== 'account' && _lastVoUsage) renderVoUsage(_lastVoUsage);
    };

    window.setApiUsageEnabled = function(enabled) {
        _enabled = enabled === true;
        const root = document.getElementById('api-usage-monitor');
        const body = document.getElementById('api-usage-body');
        const arrow = document.getElementById('api-toggle-arrow');
        if (root) root.style.display = _enabled ? '' : 'none';
        if (!_enabled) {
            stopPolling();
            setDot(false);
            if (body) body.style.display = 'none';
            if (arrow) arrow.textContent = '▶';
            return;
        }
        window.setApiUsageTab(_activeTab);
        if (_open && !_pollTimer) startPolling();
    };

    function startPolling() {
        if (!_enabled) return;
        fetchUsage();
        _pollTimer = setInterval(fetchUsage, POLL_INTERVAL);
    }
    function stopPolling() { if (_pollTimer) clearInterval(_pollTimer); _pollTimer = null; }

    async function fetchUsage() {
        const [accountResult, voResult] = await Promise.allSettled([
            fetch(USAGE_URL, { signal: AbortSignal.timeout(20000) }).then(r => r.json()),
            fetch(VO_USAGE_URL, { signal: AbortSignal.timeout(20000) }).then(r => r.json()),
        ]);
        const accountOk = accountResult.status === 'fulfilled';
        const voOk = voResult.status === 'fulfilled';
        setDot(accountOk || voOk);
        if (accountOk) {
            const data = accountResult.value || {};
            if (data.error && !data.providers?.length) renderEmpty(data.error);
            else render(data);
        } else {
            renderEmpty(_t('api_usage_connection_error'));
        }
        if (voOk) {
            _lastVoUsage = voResult.value || {};
            renderVoUsage(_lastVoUsage);
        }
        else renderVoEmpty(_t('api_usage_connection_error'));
    }

    function setDot(ok) {
        const d = document.getElementById('api-status-dot');
        if (d) { d.className = 'pc-dot ' + (ok ? 'online' : 'offline'); }
    }

    function renderEmpty(msg) {
        const c = document.getElementById('api-usage-cards');
        if (c) c.innerHTML = `<div class="pc-detail" style="text-align:center;padding:10px;opacity:0.5">${msg || _t('api_usage_no_providers')}</div>`;
    }

    function renderVoEmpty(msg) {
        const c = document.getElementById('vo-usage-cards');
        if (c) c.innerHTML = `<div class="pc-detail" style="text-align:center;padding:10px;opacity:0.5">${escapeHtml(msg || _t('vo_usage_empty'))}</div>`;
    }

    function render(data) {
        const c = document.getElementById('api-usage-cards');
        if (!c) return;

        const providers = data.providers || [];
        if (!providers.length) { renderEmpty(_t('api_usage_no_providers_found')); return; }

        let html = '';
        for (const p of providers) {
            const provName = p.provider || p.name || 'unknown';
            const displayName = (p.displayName || provName).toUpperCase();
            const color = PROVIDER_COLORS[provName] || DEFAULT_COLOR;
            const hasUsage = p.usage != null && typeof p.usage === 'object';
            const hasError = !!p.error;

            // Determine auth type
            let authLabel = p.plan || p.type || '';
            if (authLabel === 'oauth') authLabel = _t('api_usage_oauth');
            else if (authLabel === 'api_key') authLabel = _t('api_usage_api_key');
            let authColor = color;

            html += `<div class="pc-metric-row">`;

            // Header: provider name + plan/type badge
            html += `<div class="pc-metric-header">
                <span class="pc-label" style="color:${color}">${displayName}</span>`;
            if (authLabel) {
                html += `<span class="api-auth-tag" style="border-color:${authColor}60; color:${authColor};font-size:8px">${authLabel}</span>`;
            }
            html += `</div>`;

            // Error display
            if (hasError) {
                html += `<div class="api-warning error" style="font-size:8px;margin:2px 0">${p.error}</div>`;
            }
            if (p.message) {
                html += `<div class="pc-detail" style="margin-top:4px;opacity:0.7">${escapeHtml(p.message)}</div>`;
            }

            if (hasUsage) {
                const u = p.usage;

                // Day/5h window
                if (u.dailyPctLeft != null) {
                    const used = 100 - u.dailyPctLeft;
                    html += buildBar(u.dailyWindow || _t('api_usage_day'), u.dailyPctLeft, used, color);
                    if (u.dailyTimeLeft) html += `<div class="pc-detail">${u.dailyTimeLeft} ${_t('api_usage_until_reset')}</div>`;
                }

                // Week window
                if (u.weeklyPctLeft != null) {
                    const used = 100 - u.weeklyPctLeft;
                    html += buildBar(_t('api_usage_week'), u.weeklyPctLeft, used, color);
                    if (u.weeklyTimeLeft) html += `<div class="pc-detail">${u.weeklyTimeLeft} ${_t('api_usage_until_reset')}</div>`;
                }

                // Month window
                if (u.monthlyPctLeft != null) {
                    const used = 100 - u.monthlyPctLeft;
                    html += buildBar(_t('api_usage_month'), u.monthlyPctLeft, used, color);
                    if (u.monthlyTimeLeft) html += `<div class="pc-detail">${u.monthlyTimeLeft} ${_t('api_usage_until_reset')}</div>`;
                }

                // Any other windows (generic)
                for (const key of Object.keys(u)) {
                    if (key.endsWith('PctLeft') && !['dailyPctLeft','weeklyPctLeft','monthlyPctLeft'].includes(key)) {
                        const label = key.replace('PctLeft','').toUpperCase();
                        const left = u[key];
                        const used = 100 - left;
                        const timeKey = key.replace('PctLeft','TimeLeft');
                        html += buildBar(label, left, used, color);
                        if (u[timeKey]) html += `<div class="pc-detail">${u[timeKey]} ${_t('api_usage_until_reset')}</div>`;
                    }
                }

                // Exhaustion warnings
                if (u.dailyPctLeft === 0) html += `<div class="api-warning exhausted">${_t('api_usage_daily_limit_reached')}</div>`;
                if (u.weeklyPctLeft === 0) html += `<div class="api-warning exhausted">${_t('api_usage_weekly_limit_reached')}</div>`;
            } else if (!hasError) {
                // API key provider with no usage windows
                html += `<div class="pc-detail" style="margin-top:4px;opacity:0.4">${_t('api_usage_configured_no_windows')}</div>`;
            }

            html += `</div>`;
        }

        // Source + freshness footer
        const age = data.ageSeconds;
        let freshLabel = '';
        if (age != null) {
            if (age < 60) freshLabel = _t('just_now');
            else if (age < 3600) freshLabel = Math.round(age / 60) + _t('m_ago');
            else freshLabel = Math.round(age / 3600) + _t('h_ago');
        }
        if (freshLabel) {
            html += `<div class="pc-detail" style="text-align:right;opacity:0.3;margin-top:6px;font-size:7px">${_t('api_usage_updated')} ${freshLabel}</div>`;
        }

        c.innerHTML = html || `<div class="pc-detail" style="text-align:center;padding:10px">${_t('api_usage_no_providers')}</div>`;
    }

    function renderVoUsage(data) {
        const c = document.getElementById('vo-usage-cards');
        if (!c) return;
        const totals = data.totals || {};
        const runs = Number(totals.runs || 0);
        if (!runs) { renderVoEmpty(_t('vo_usage_empty')); return; }
        const coverage = Number(totals.coveragePct || 0);
        let html = renderVoSummary(totals, runs, coverage);
        if (_activeTab === 'agent') html += renderUsageList(_t('vo_usage_by_agent'), data.byAgent || [], 'agentId');
        else if (_activeTab === 'model') html += renderUsageList(_t('vo_usage_by_model'), data.byModel || [], 'model');
        else if (_activeTab === 'records') html += renderRecentRuns(data.recent || []);
        c.innerHTML = html;
    }

    function renderVoSummary(totals, runs, coverage) {
        return `<div class="pc-metric-row vo-usage-summary">
            <div>
                <span class="pc-label">${escapeHtml(_t('vo_usage_today'))}</span>
                <span class="pc-value">${formatTokens(totals.totalTokens || 0)}</span>
            </div>
            <div class="pc-detail">${Number(totals.recordedRuns || 0)} / ${runs} · ${escapeHtml(_t('vo_usage_missing'))} ${Number(totals.missingRuns || 0)} · ${escapeHtml(_t('vo_usage_coverage'))} ${coverage.toFixed(1)}%</div>
        </div>`;
    }

    function renderUsageList(title, rows, labelKey) {
        let html = `<div class="pc-metric-row"><div class="pc-metric-header"><span class="pc-label">${escapeHtml(title)}</span><span class="pc-value">${rows.length}</span></div>`;
        const top = rows.slice(0, 5);
        if (!top.length) {
            html += `<div class="pc-detail" style="opacity:0.5">${_t('vo_usage_empty')}</div></div>`;
            return html;
        }
        const max = Math.max(...top.map(r => Number(r.totalTokens || 0)), 1);
        for (const row of top) {
            const label = row[labelKey] || 'unknown';
            const total = Number(row.totalTokens || 0);
            const pct = Math.max(2, Math.min(100, (total / max) * 100));
            html += `<div class="pc-metric-header" style="margin-top:5px">
                <span class="pc-label" title="${escapeHtml(label)}">${escapeHtml(shortLabel(label))}</span>
                <span class="pc-value">${formatTokens(total)}</span>
            </div>
            <div class="pc-bar-track"><div class="pc-bar" style="width:${pct}%;background:#74d680"></div></div>
            <div class="pc-detail">${Number(row.recordedRuns || 0)} ${_t('vo_usage_recorded')} · ${Number(row.missingRuns || 0)} ${_t('vo_usage_missing')}</div>`;
        }
        return html + '</div>';
    }

    function renderRecentRuns(rows) {
        let html = `<div class="pc-metric-row"><div class="pc-metric-header"><span class="pc-label">${_t('vo_usage_recent_runs')}</span><span class="pc-value">${rows.length}</span></div>`;
        for (const row of rows.slice(0, 8)) {
            const when = row.ts ? new Date(row.ts).toLocaleTimeString([], {hour: '2-digit', minute: '2-digit'}) : '--:--';
            const who = shortLabel(row.agentName || row.agentId || row.providerKind || 'unknown');
            const model = shortLabel(row.model || 'unknown');
            const value = row.usageStatus === 'recorded' ? formatTokens(row.totalTokens || 0) : _t('vo_usage_unavailable');
            html += `<div class="pc-detail" style="display:flex;justify-content:space-between;gap:6px;margin-top:4px">
                <span>${escapeHtml(when)} ${escapeHtml(who)} · ${escapeHtml(model)}</span>
                <span>${escapeHtml(value)}</span>
            </div>`;
        }
        return html + '</div>';
    }

    function formatTokens(value) {
        const n = Number(value || 0);
        const m = n / 1000000;
        return (m >= 1 ? m.toFixed(1) : m.toFixed(2)) + 'M';
    }

    function shortLabel(value) {
        const s = String(value || 'unknown');
        return s.length > 22 ? s.slice(0, 19) + '...' : s;
    }

    function buildBar(label, pctLeft, usedPct, color) {
        let html = `<div class="pc-metric-header" style="margin-top:4px">
            <span class="pc-label">${label}</span>
            <span class="pc-value" style="color:${getValColor(usedPct)}">${Math.round(pctLeft)}${_t('api_usage_pct_left')}</span>
        </div>`;
        html += `<div class="pc-bar-track"><div class="pc-bar" style="width:${usedPct}%;background:${getBarGrad(usedPct, color)}"></div></div>`;
        return html;
    }

    function escapeHtml(value) {
        return String(value || '').replace(/[&<>"']/g, function(ch) {
            return ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'})[ch];
        });
    }

    function getValColor(usedPct) {
        if (usedPct > 90) return '#f44336';
        if (usedPct > 70) return '#ff9800';
        return '#fff';
    }
    function getBarGrad(usedPct, baseColor) {
        if (usedPct > 90) return 'linear-gradient(90deg, #f44336, #e53935)';
        if (usedPct > 70) return 'linear-gradient(90deg, #ff9800, #f57c00)';
        return `linear-gradient(90deg, ${baseColor}, ${baseColor}cc)`;
    }

    fetch('/vo-config').then(function(r) { return r.json(); }).then(function(cfg) {
        window.setApiUsageEnabled(!!(cfg && cfg.features && cfg.features.apiUsage === true));
    }).catch(function() {
        window.setApiUsageEnabled(false);
        // Leave API usage disabled when config cannot be loaded.
    });
})();
