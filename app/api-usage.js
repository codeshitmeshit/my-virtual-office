// API Usage Monitor — shows real quota data from API/OAuth providers
(function() {
    const _t = (key) => typeof i18n !== 'undefined' ? i18n.t(key) : key;
    const USAGE_URL = '/api-usage';
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

    window.toggleApiUsage = function() {
        _open = !_open;
        const body = document.getElementById('api-usage-body');
        const arrow = document.getElementById('api-toggle-arrow');
        body.style.display = _open ? 'block' : 'none';
        arrow.textContent = _open ? '▼' : '▶';
        if (_open && !_pollTimer) startPolling();
        if (!_open && _pollTimer) stopPolling();
    };

    function startPolling() { fetchUsage(); _pollTimer = setInterval(fetchUsage, POLL_INTERVAL); }
    function stopPolling() { if (_pollTimer) clearInterval(_pollTimer); _pollTimer = null; }

    async function fetchUsage() {
        try {
            const res = await fetch(USAGE_URL, { signal: AbortSignal.timeout(20000) });
            const data = await res.json();
            if (data.error && !data.providers?.length) { setDot(false); renderEmpty(data.error); return; }
            setDot(true);
            render(data);
        } catch(e) { setDot(false); renderEmpty(_t('api_usage_connection_error')); }
    }

    function setDot(ok) {
        const d = document.getElementById('api-status-dot');
        if (d) { d.className = 'pc-dot ' + (ok ? 'online' : 'offline'); }
    }

    function renderEmpty(msg) {
        const c = document.getElementById('api-usage-cards');
        if (c) c.innerHTML = `<div class="pc-detail" style="text-align:center;padding:10px;opacity:0.5">${msg || _t('api_usage_no_providers')}</div>`;
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
        if (cfg && cfg.features && cfg.features.apiUsage === true) {
            if (_open) startPolling();
        }
    }).catch(function() {
        // Leave API usage disabled when config cannot be loaded.
    });
})();
