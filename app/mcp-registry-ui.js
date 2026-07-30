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
        var assignedText = assigned.length
            ? assigned.map(_mcpAgentLabel).join(', ')
            : _mcpTr('mcp_unassigned', null, '暂未分配');
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
                    '<span class="mcp-assignment-icon" aria-hidden="true">A</span>' +
                    '<div><span>' + _mcpEsc(_mcpTr('mcp_assigned_to', null, '已安装指引 Skill')) + '</span><strong>' + _mcpEsc(assignedText) + '</strong></div>' +
                '</div>' +
                '<div class="mcp-card-actions">' +
                    '<button type="button" class="mcp-assign-button" title="' + _mcpEsc(_mcpTr('mcp_assign_agent_title', null, '注册到 Agent 所属客户端，并为该 Agent 安装 MCP 使用指引 Skill')) + '" data-mcp-action="toggle-skill" data-mcp-name="' + _mcpEsc(server.name) + '">' + _mcpEsc(_mcpTr('mcp_assign_agent', null, '安装指引')) + '</button>' +
                    '<button type="button" class="mcp-delete-button" title="' + _mcpEsc(_mcpTr('delete', null, '删除')) + '" aria-label="' + _mcpEsc(_mcpTr('delete', null, '删除')) + '" data-mcp-action="delete" data-mcp-name="' + _mcpEsc(server.name) + '">×</button>' +
                '</div>' +
            '</div>' +
            '<div class="mcp-install-row" id="mcp-install-' + _mcpEsc(server.name) + '" style="display:none"></div>' +
        '</article>';
    }).join('');
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

async function toggleMcpSkillInstall(name) {
    var row = document.getElementById('mcp-install-' + name);
    if (!row) return;
    if (row.style.display !== 'none') {
        row.style.display = 'none';
        return;
    }
    try {
        await loadMcpAgents();
        var agents = Object.keys(_mcpAgentsById).map(function(id) { return _mcpAgentsById[id]; }).filter(function(agent) {
            return ['openclaw', 'codex', 'claude', 'claude-code'].indexOf(String(agent.providerKind || 'openclaw').toLowerCase()) >= 0;
        });
        row.innerHTML = '<select id="mcp-agent-' + _mcpEsc(name) + '">' + agents.map(function(agent) {
            var provider = String(agent.providerKind || 'openclaw').toLowerCase();
            var providerLabel = provider === 'claude-code' || provider === 'claude' ? 'Claude' : (provider === 'codex' ? 'Codex' : 'OpenClaw');
            return '<option value="' + _mcpEsc(agent.id) + '">' + _mcpEsc((agent.emoji || '') + ' ' + (agent.name || agent.id) + ' · ' + providerLabel) + '</option>';
        }).join('') + '</select><button type="button" data-mcp-action="install-skill" data-mcp-name="' + _mcpEsc(name) + '"' + (agents.length ? '' : ' disabled') + '>' + _mcpEsc(_mcpTr('mcp_assign_and_install', null, '注册客户端并安装指引')) + '</button>';
        row.style.display = 'flex';
    } catch (e) {
        if (typeof _acpShowToast === 'function') _acpShowToast(_mcpTr('mcp_agent_list_failed', { error: e.message }, 'Agent 列表加载失败：{{error}}'));
    }
}

async function installMcpSkill(name) {
    var select = document.getElementById('mcp-agent-' + name);
    var agentId = select && select.value;
    if (!agentId) return;
    try {
        var res = await _mcpMutationFetch('/api/mcp-registry/' + encodeURIComponent(name) + '/skill', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ agentId: agentId, overwrite: true })
        });
        var data = await res.json();
        if (!res.ok || !data.ok) throw new Error(data.error || _mcpTr('mcp_assignment_failed_plain', null, 'MCP 分配失败'));
        if (typeof _acpShowToast === 'function') {
            var labels = { openclaw: 'OpenClaw', codex: 'Codex', claude: 'Claude' };
            _acpShowToast(_mcpTr('mcp_assigned', {
                agent: _mcpAgentLabel(agentId),
                client: labels[data.client] || data.client || ''
            }, '已注册到 {{client}}，并为 {{agent}} 安装指引 Skill'));
        }
        refreshMcpRegistry();
    } catch (e) {
        if (typeof _acpShowToast === 'function') _acpShowToast(_mcpTr('mcp_assignment_failed', { error: e.message }, 'MCP 分配失败：{{error}}'));
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
    if (action === 'toggle-skill') toggleMcpSkillInstall(name);
    if (action === 'install-skill') installMcpSkill(name);
    if (action === 'delete') deleteMcpServer(name);
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
    toggleMcpSkillInstall,
    installMcpSkill,
    copyMcpConnection,
    deleteMcpServer
});
