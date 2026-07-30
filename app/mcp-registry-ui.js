// MCP registry panel for VO-managed MCP servers.

var _mcpServers = [];
var _mcpAgentsById = {};

function _mcpMutationFetch(input, init) {
    if (window.i18n && typeof window.i18n.managementFetch === 'function') {
        return window.i18n.managementFetch(input, init || {});
    }
    return fetch(input, init || {});
}

function _mcpTr(key, params, fallback) {
    if (typeof _tr === 'function') {
        var translated = _tr(key, params);
        if (translated && translated !== key) return translated;
    }
    var text = fallback || key;
    if (params) {
        Object.keys(params).forEach(function(name) {
            text = text.replace(new RegExp('\\{\\{' + name + '\\}\\}', 'g'), params[name]);
        });
    }
    return text;
}

function _mcpEsc(value) {
    return String(value == null ? '' : value)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#039;');
}

function openMcpRegistry() {
    var modal = document.getElementById('mcpRegistryModal');
    if (!modal) return;
    modal.classList.remove('hidden');
    refreshMcpRegistry();
}

function closeMcpRegistry() {
    var modal = document.getElementById('mcpRegistryModal');
    if (modal) modal.classList.add('hidden');
}

async function refreshMcpRegistry() {
    var list = document.getElementById('mcp-registry-list');
    if (list) list.innerHTML = '<div class="mcp-empty">' + _mcpEsc(_mcpTr('mcp_loading', null, '加载中...')) + '</div>';
    try {
        var res = await fetch('/api/mcp-registry', { cache: 'no-store' });
        var data = await res.json();
        _mcpServers = Array.isArray(data.servers) ? data.servers : [];
        await loadMcpAgents();
    } catch (e) {
        _mcpServers = [];
        if (typeof _acpShowToast === 'function') _acpShowToast(_mcpTr('mcp_load_failed', { error: e.message }, 'MCP 注册表加载失败：{{error}}'));
    }
    renderMcpRegistry();
}

async function loadMcpAgents() {
    try {
        var res = await fetch('/api/agents', { cache: 'no-store' });
        var data = await res.json();
        _mcpAgentsById = {};
        (data.agents || []).forEach(function(agent) {
            _mcpAgentsById[agent.id] = agent;
        });
    } catch (e) {
        _mcpAgentsById = {};
    }
}

function _mcpAgentLabel(agentId) {
    var agent = _mcpAgentsById[agentId] || {};
    return ((agent.emoji || '') + ' ' + (agent.name || agentId)).trim();
}

function _mcpAclMarkup(server, assigned) {
    return AgentBranchSelector.render({
        agents: Object.keys(_mcpAgentsById).map(function(id) { return _mcpAgentsById[id]; }),
        branches: typeof getBranchList === 'function' ? getBranchList() : [],
        selectedIds: assigned,
        supportedProviders: ['openclaw', 'codex', 'claude', 'claude-code'],
        branchTogglePlacement: 'group-title',
        branchInputClass: 'mcp-branch-toggle',
        agentInputClass: 'mcp-assignment-toggle',
        scopeAttributes: ' data-mcp-name="' + _mcpEsc(server.name) + '"',
        quickSelectLabel: _mcpTr('meeting_branch_quick_select', null, '按部门快捷选择'),
        hintLabel: _mcpTr('meeting_branch_quick_select_hint', null, '先选择部门，再手动调整单个 Agent。'),
        emptyLabel: _mcpTr('mcp_no_assignable_agents', null, '暂无可分配 Agent'),
        escape: _mcpEsc,
        translate: function(key, fallback) { return _mcpTr(key, null, fallback); }
    });
}

function _mcpSyncBranchToggles() {
    document.querySelectorAll('.mcp-card').forEach(function(card) {
        AgentBranchSelector.syncBranches(card, '.mcp-branch-toggle', '.mcp-assignment-toggle');
    });
}

function _mcpWarningText(warning) {
    var code = warning && typeof warning === 'object' ? warning.code : '';
    var params = warning && typeof warning === 'object' ? (warning.params || {}) : {};
    var raw = typeof warning === 'string' ? warning : '';
    var legacyMatch = raw.match(/^(Codex|Claude) CLI does not persist the configured working directory$/);
    if (code === 'mcp_client_cwd_not_persisted' || legacyMatch) {
        var client = params.client || (legacyMatch && legacyMatch[1]) || '';
        return _mcpTr(
            'mcp_warning_cwd_not_persisted',
            { client: client },
            '{{client}} CLI 不会保存已配置的工作目录，启动时可能需要重新指定。'
        );
    }
    return raw || String((warning && warning.message) || '');
}

function _mcpClientWarnings(server, client) {
    var status = server[client] || {};
    var warningCodes = Array.isArray(status.warningCodes) ? status.warningCodes : [];
    var warnings = warningCodes.length ? warningCodes : (Array.isArray(status.warnings) ? status.warnings : []);
    return warnings.map(_mcpWarningText).filter(Boolean);
}

function _mcpClientMarkup(server, client, label) {
    var registered = Boolean(server[client] && server[client].registered);
    var name = _mcpEsc(server.name);
    return '<div class="mcp-client-item' + (registered ? ' is-connected' : '') + '">' +
        '<div class="mcp-client-identity">' +
            '<span class="mcp-client-dot" aria-hidden="true"></span>' +
            '<span>' + _mcpEsc(label) + '</span>' +
        '</div>' +
        (registered
            ? '<span class="mcp-client-state">' + _mcpEsc(_mcpTr('mcp_connected', null, '已连接')) + '</span>'
            : '<button type="button" class="mcp-client-connect" data-mcp-action="' + client + '" data-mcp-name="' + name + '">' +
                _mcpEsc(_mcpTr('mcp_connect', null, '连接')) +
              '</button>') +
    '</div>';
}

function renderMcpRegistry() {
    var list = document.getElementById('mcp-registry-list');
    var count = document.getElementById('mcp-registry-count');
    if (!list) return;
    if (count) count.textContent = String(_mcpServers.length);
    if (!_mcpServers.length) {
        list.innerHTML = '<div class="mcp-empty">' + _mcpEsc(_mcpTr('mcp_empty', null, 'VO 中暂无 MCP server。')) + '</div>';
        return;
    }
    list.innerHTML = _mcpServers.map(function(server) {
        var registeredClients = [
            server.openclaw && server.openclaw.registered ? 'OpenClaw' : '',
            server.codex && server.codex.registered ? 'Codex' : '',
            server.claude && server.claude.registered ? 'Claude' : ''
        ].filter(Boolean);
        var registrationWarnings = ['codex', 'claude'].reduce(function(items, client) {
            return items.concat(_mcpClientWarnings(server, client));
        }, []);
        var detail = server.transport === 'stdio'
            ? [server.command || '', (server.args || []).join(' ')].join(' ').trim()
            : [server.transport || '', server.url || ''].join(' ').trim();
        var env = server.envKeys && server.envKeys.length ? ' · ' + _mcpTr('mcp_env_keys', null, '环境变量') + ': ' + server.envKeys.join(', ') : '';
        var assigned = Array.isArray(server.assignedAgentIds) ? server.assignedAgentIds : [];
        var aclMarkup = _mcpAclMarkup(server, assigned);
        return '<article class="mcp-card">' +
            '<header class="mcp-card-header">' +
                '<div class="mcp-card-icon" aria-hidden="true">M</div>' +
                '<div class="mcp-card-heading">' +
                    '<div class="mcp-card-title-row">' +
                        '<div class="mcp-card-title">' + _mcpEsc(server.name) + '</div>' +
                        '<span class="mcp-transport-badge">' + _mcpEsc(String(server.transport || 'stdio').toUpperCase()) + '</span>' +
                    '</div>' +
                    '<div class="mcp-card-desc">' + _mcpEsc(server.description || _mcpTr('mcp_no_description', null, '暂无描述')) + '</div>' +
                '</div>' +
            '</header>' +
            '<div class="mcp-card-connection">' +
                '<div class="mcp-card-section-label">' + _mcpEsc(_mcpTr('mcp_connection', null, '连接信息')) + '</div>' +
                '<div class="mcp-command-row">' +
                    '<code class="mcp-card-command" title="' + _mcpEsc(detail + env) + '">' + _mcpEsc(detail + env) + '</code>' +
                    '<button type="button" class="mcp-copy-button" data-mcp-action="copy-command" data-mcp-detail="' + _mcpEsc(detail + env) + '" title="' + _mcpEsc(_mcpTr('mcp_copy_connection', null, '复制连接信息')) + '">' +
                        _mcpEsc(_mcpTr('copy', null, '复制')) +
                    '</button>' +
                '</div>' +
            '</div>' +
            '<div class="mcp-card-clients">' +
                '<div class="mcp-card-section-label">' + _mcpEsc(_mcpTr('mcp_clients', null, '客户端')) + '<span>' + registeredClients.length + '/3</span></div>' +
                '<div class="mcp-client-grid">' +
                    _mcpClientMarkup(server, 'openclaw', 'OpenClaw') +
                    _mcpClientMarkup(server, 'codex', 'Codex') +
                    _mcpClientMarkup(server, 'claude', 'Claude') +
                '</div>' +
            '</div>' +
            (registrationWarnings.length ? '<div class="mcp-card-warning"><span aria-hidden="true">!</span><div><strong>' + _mcpEsc(_mcpTr('mcp_attention', null, '需要注意')) + '</strong><p>' + _mcpEsc(registrationWarnings.join('; ')) + '</p></div></div>' : '') +
            '<div class="mcp-card-footer">' +
                '<div class="mcp-assignment-summary">' +
                    '<div class="mcp-agent-acl-copy"><span>' + _mcpEsc(_mcpTr('mcp_agent_acl', null, 'Agent 使用权限')) + '</span><div class="mcp-agent-acl">' + aclMarkup + '</div></div>' +
                '</div>' +
                '<div class="mcp-card-actions">' +
                    '<button type="button" class="mcp-save-access-button" data-mcp-action="save-access" data-mcp-name="' + _mcpEsc(server.name) + '" disabled>' + _mcpEsc(_mcpTr('mcp_save_settings', null, '保存设置')) + '</button>' +
                    '<button type="button" class="mcp-guide-button" data-mcp-action="toggle-guide" data-mcp-name="' + _mcpEsc(server.name) + '">' + _mcpEsc(_mcpTr('mcp_usage_guide', null, '使用说明')) + (server.hasUsageGuide ? ' ·' : '') + '</button>' +
                    '<button type="button" class="mcp-delete-button" title="' + _mcpEsc(_mcpTr('delete', null, '删除')) + '" aria-label="' + _mcpEsc(_mcpTr('delete', null, '删除')) + '" data-mcp-action="delete" data-mcp-name="' + _mcpEsc(server.name) + '">×</button>' +
                '</div>' +
            '</div>' +
            '<div class="mcp-guide-row" id="mcp-guide-' + _mcpEsc(server.name) + '" style="display:none"></div>' +
        '</article>';
    }).join('');
    _mcpSyncBranchToggles();
}

async function copyMcpConnection(detail) {
    try {
        await navigator.clipboard.writeText(detail || '');
        if (typeof _acpShowToast === 'function') _acpShowToast(_mcpTr('mcp_connection_copied', null, '连接信息已复制'));
    } catch (e) {
        if (typeof _acpShowToast === 'function') _acpShowToast(_mcpTr('mcp_copy_failed', null, '复制失败'));
    }
}

function _mcpFormPayload() {
    var args = (document.getElementById('mcp-args')?.value || '').trim();
    var include = (document.getElementById('mcp-include')?.value || '').trim();
    var envText = (document.getElementById('mcp-env')?.value || '').trim();
    var env = {};
    if (envText) {
        envText.split('\n').forEach(function(line) {
            var idx = line.indexOf('=');
            if (idx > 0) env[line.slice(0, idx).trim()] = line.slice(idx + 1);
        });
    }
    return {
        name: (document.getElementById('mcp-name')?.value || '').trim(),
        description: (document.getElementById('mcp-description')?.value || '').trim(),
        transport: (document.getElementById('mcp-transport')?.value || 'stdio').trim(),
        command: (document.getElementById('mcp-command')?.value || '').trim(),
        args: args ? args.split(/\s+/).filter(Boolean) : [],
        url: (document.getElementById('mcp-url')?.value || '').trim(),
        cwd: (document.getElementById('mcp-cwd')?.value || '').trim(),
        include: include ? include.split(',').map(function(x) { return x.trim(); }).filter(Boolean) : [],
        env: env
    };
}

async function saveMcpServer() {
    try {
        var res = await _mcpMutationFetch('/api/mcp-registry', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(_mcpFormPayload())
        });
        var data = await res.json();
        if (!res.ok || !data.ok) throw new Error(data.error || _mcpTr('mcp_save_failed_plain', null, '保存失败'));
        if (typeof _acpShowToast === 'function') _acpShowToast(_mcpTr('mcp_saved', { name: data.server.name }, 'MCP server 已保存：{{name}}'));
        refreshMcpRegistry();
    } catch (e) {
        if (typeof _acpShowToast === 'function') _acpShowToast(_mcpTr('mcp_save_failed', { error: e.message }, 'MCP 保存失败：{{error}}'));
    }
}

async function addVibeTradingMcpTemplate() {
    try {
        var res = await _mcpMutationFetch('/api/mcp-registry/templates/vibe-trading', { method: 'POST' });
        var data = await res.json();
        if (!res.ok || !data.ok) throw new Error(data.error || _mcpTr('mcp_template_failed_plain', null, '模板创建失败'));
        document.getElementById('mcp-name').value = data.server.name || 'vibe-trading';
        document.getElementById('mcp-description').value = data.server.description || '';
        document.getElementById('mcp-transport').value = 'stdio';
        document.getElementById('mcp-command').value = data.server.command || 'vibe-trading-mcp';
        document.getElementById('mcp-args').value = (data.server.args || []).join(' ');
        document.getElementById('mcp-include').value = (data.server.include || ['*']).join(',');
        if (typeof _acpShowToast === 'function') _acpShowToast(_mcpTr('mcp_vibe_template_saved', null, 'Vibe-Trading MCP 模板已保存到 VO'));
        refreshMcpRegistry();
    } catch (e) {
        if (typeof _acpShowToast === 'function') _acpShowToast(_mcpTr('mcp_template_failed', { error: e.message }, '模板创建失败：{{error}}'));
    }
}

async function registerMcpInOpenClaw(name) {
    return registerMcpInNativeClient(name, 'openclaw');
}

async function registerMcpInNativeClient(name, client) {
    var labels = { openclaw: 'OpenClaw', codex: 'Codex', claude: 'Claude' };
    var label = labels[client] || client;
    try {
        var res = await _mcpMutationFetch('/api/mcp-registry/' + encodeURIComponent(name) + '/' + encodeURIComponent(client), { method: 'POST' });
        var data = await res.json();
        if (!res.ok || !data.ok) {
            throw new Error(data.error || _mcpTr('mcp_client_failed_plain', { client: label }, '{{client}} 注册失败'));
        }
        if (typeof _acpShowToast === 'function') {
            var message = _mcpTr('mcp_client_registered', { client: label, name: name }, '已注册到 {{client}}：{{name}}');
            var warnings = _mcpClientWarnings(data, client);
            if (warnings.length) {
                message += ' · ' + _mcpTr('mcp_registration_warning', { warning: warnings.join('; ') }, '注意：{{warning}}');
            }
            _acpShowToast(message);
        }
        refreshMcpRegistry();
    } catch (e) {
        if (typeof _acpShowToast === 'function') {
            _acpShowToast(_mcpTr('mcp_client_failed', { client: label, error: e.message }, '{{client}} 注册失败：{{error}}'));
        }
    }
}

function _mcpMarkAccessDirty(card) {
    if (!card) return;
    card.classList.add('is-access-dirty');
    var button = card.querySelector('[data-mcp-action="save-access"]');
    if (button) button.disabled = false;
}

function setMcpAgentAccess(name, agentId, allowed, checkbox) {
    var card = checkbox && checkbox.closest('.mcp-card');
    if (card) AgentBranchSelector.syncBranches(card, '.mcp-branch-toggle', '.mcp-assignment-toggle');
    _mcpMarkAccessDirty(card);
}

function setMcpBranchAccess(name, branchId, allowed, branchToggle) {
    var card = branchToggle && branchToggle.closest('.mcp-card');
    if (!card) return;
    AgentBranchSelector.applyBranch(card, branchToggle, '.mcp-assignment-toggle');
    AgentBranchSelector.syncBranches(card, '.mcp-branch-toggle', '.mcp-assignment-toggle');
    _mcpMarkAccessDirty(card);
}

async function saveMcpAgentAccess(name, button) {
    var card = button && button.closest('.mcp-card');
    if (!card) return;
    var agentIds = Array.prototype.slice.call(card.querySelectorAll('.mcp-assignment-toggle:checked')).map(function(toggle) {
        return toggle.value;
    }).filter(Boolean);
    button.disabled = true;
    try {
        var endpoint = agentIds.length ? '/assign-agents' : '/assign';
        var res = await _mcpMutationFetch('/api/mcp-registry/' + encodeURIComponent(name) + endpoint, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ agentIds: agentIds, mode: 'replace' })
        });
        var data = await res.json();
        if (!res.ok || !data.ok) throw new Error(data.error || _mcpTr('mcp_assignment_failed_plain', null, 'MCP 分配失败'));
        if (typeof _acpShowToast === 'function') _acpShowToast(
            _mcpTr('mcp_settings_saved', { count: agentIds.length }, '已保存 {{count}} 个 Agent 的使用权限')
        );
        refreshMcpRegistry();
    } catch (e) {
        button.disabled = false;
        if (typeof _acpShowToast === 'function') _acpShowToast(_mcpTr('mcp_assignment_failed', { error: e.message }, 'MCP 分配失败：{{error}}'));
    }
}

async function toggleMcpGuide(name) {
    var row = document.getElementById('mcp-guide-' + name);
    if (!row) return;
    if (row.style.display !== 'none') {
        row.style.display = 'none';
        return;
    }
    row.innerHTML = '<span class="mcp-guide-loading">' + _mcpEsc(_mcpTr('mcp_usage_guide_loading', null, '正在加载使用说明...')) + '</span>';
    row.style.display = 'grid';
    try {
        var res = await fetch('/api/mcp-registry/' + encodeURIComponent(name) + '/guide');
        var data = await res.json();
        if (!res.ok || !data.ok) throw new Error(data.error || _mcpTr('mcp_usage_guide_load_failed_plain', null, '使用说明加载失败'));
        row.innerHTML = '<div class="mcp-guide-header">' +
                '<label for="mcp-guide-input-' + _mcpEsc(name) + '">' + _mcpEsc(_mcpTr('mcp_usage_guide_title', null, '可选使用说明')) + '</label>' +
                '<button type="button" class="mcp-guide-save" data-mcp-action="save-guide" data-mcp-name="' + _mcpEsc(name) + '">' + _mcpEsc(_mcpTr('save', null, '保存')) + '</button>' +
            '</div>' +
            '<textarea id="mcp-guide-input-' + _mcpEsc(name) + '" maxlength="20000" placeholder="' + _mcpEsc(_mcpTr('mcp_usage_guide_placeholder', null, '仅填写工具定义之外的流程、约束或注意事项。')) + '">' + _mcpEsc(data.guide || '') + '</textarea>' +
            '<div class="mcp-guide-hint">' + _mcpEsc(_mcpTr('mcp_usage_guide_hint', null, 'VO Agent 会在工具定义不足时按需读取。')) + '</div>';
    } catch (e) {
        row.innerHTML = '<span class="mcp-guide-error">' + _mcpEsc(_mcpTr('mcp_usage_guide_load_failed', { error: e.message }, '使用说明加载失败：{{error}}')) + '</span>';
    }
}

async function saveMcpGuide(name) {
    var input = document.getElementById('mcp-guide-input-' + name);
    if (!input) return;
    try {
        var res = await _mcpMutationFetch('/api/mcp-registry/' + encodeURIComponent(name) + '/guide', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ guide: input.value })
        });
        var data = await res.json();
        if (!res.ok || !data.ok) throw new Error(data.error || _mcpTr('mcp_usage_guide_save_failed_plain', null, '使用说明保存失败'));
        if (typeof _acpShowToast === 'function') _acpShowToast(_mcpTr('mcp_usage_guide_saved', null, '使用说明已保存'));
        refreshMcpRegistry();
    } catch (e) {
        if (typeof _acpShowToast === 'function') _acpShowToast(_mcpTr('mcp_usage_guide_save_failed', { error: e.message }, '使用说明保存失败：{{error}}'));
    }
}

async function deleteMcpServer(name) {
    if (!confirm(_mcpTr('mcp_delete_confirm', { name: name }, '从 VO 注册表删除 MCP server "{{name}}"？'))) return;
    try {
        var res = await _mcpMutationFetch('/api/mcp-registry/' + encodeURIComponent(name), { method: 'DELETE' });
        var data = await res.json();
        if (!res.ok || !data.ok) throw new Error(data.error || _mcpTr('delete_failed', null, '删除失败'));
        refreshMcpRegistry();
    } catch (e) {
        if (typeof _acpShowToast === 'function') _acpShowToast(_mcpTr('mcp_delete_failed', { error: e.message }, '删除失败：{{error}}'));
    }
}

document.addEventListener('click', function(e) {
    var modal = document.getElementById('mcpRegistryModal');
    if (modal && e.target === modal) closeMcpRegistry();
    var actionButton = e.target.closest && e.target.closest('[data-mcp-action]');
    if (!actionButton) return;
    var action = actionButton.getAttribute('data-mcp-action');
    var name = actionButton.getAttribute('data-mcp-name') || '';
    if (action === 'copy-command') copyMcpConnection(actionButton.getAttribute('data-mcp-detail') || '');
    if (action === 'openclaw' || action === 'codex' || action === 'claude') registerMcpInNativeClient(name, action);
    if (action === 'save-access') saveMcpAgentAccess(name, actionButton);
    if (action === 'toggle-guide') toggleMcpGuide(name);
    if (action === 'save-guide') saveMcpGuide(name);
    if (action === 'delete') deleteMcpServer(name);
});

document.addEventListener('change', function(e) {
    var branchToggle = e.target.closest && e.target.closest('.mcp-branch-toggle');
    if (branchToggle) {
        setMcpBranchAccess(
            branchToggle.getAttribute('data-mcp-name') || '',
            branchToggle.getAttribute('data-branch-id') || '',
            Boolean(branchToggle.checked),
            branchToggle
        );
        return;
    }
    var checkbox = e.target.closest && e.target.closest('.mcp-assignment-toggle');
    if (!checkbox) return;
    setMcpAgentAccess(
        checkbox.getAttribute('data-mcp-name') || '',
        checkbox.getAttribute('data-agent-id') || checkbox.value || '',
        Boolean(checkbox.checked),
        checkbox
    );
});

window.addEventListener('i18n:changed', function() {
    renderMcpRegistry();
});

Object.assign(window, {
    openMcpRegistry,
    closeMcpRegistry,
    refreshMcpRegistry,
    saveMcpServer,
    addVibeTradingMcpTemplate,
    registerMcpInOpenClaw,
    registerMcpInNativeClient,
    setMcpAgentAccess,
    setMcpBranchAccess,
    saveMcpAgentAccess,
    toggleMcpGuide,
    saveMcpGuide,
    copyMcpConnection,
    deleteMcpServer
});
