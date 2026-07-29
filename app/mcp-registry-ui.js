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

function renderMcpRegistry() {
    var list = document.getElementById('mcp-registry-list');
    if (!list) return;
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
        var status = registeredClients.length
            ? _mcpTr('mcp_status_registered_clients', { clients: registeredClients.join(', ') }, '已注册到：{{clients}}')
            : _mcpTr('mcp_status_vo_only', null, '仅在 VO 中保存');
        var registrationWarnings = ['codex', 'claude'].reduce(function(items, client) {
            var warnings = server[client] && server[client].warnings;
            return items.concat(Array.isArray(warnings) ? warnings : []);
        }, []);
        var detail = server.transport === 'stdio'
            ? [server.command || '', (server.args || []).join(' ')].join(' ').trim()
            : [server.transport || '', server.url || ''].join(' ').trim();
        var env = server.envKeys && server.envKeys.length ? ' ' + _mcpTr('mcp_env_keys', null, '环境变量') + ': ' + server.envKeys.join(', ') : '';
        var assigned = Array.isArray(server.assignedAgentIds) ? server.assignedAgentIds : [];
        var assignedText = assigned.length
            ? assigned.map(_mcpAgentLabel).join(', ')
            : _mcpTr('mcp_unassigned', null, '暂未分配');
        return '<div class="mcp-card">' +
            '<div class="mcp-card-main">' +
                '<div class="mcp-card-title">' + _mcpEsc(server.name) + '</div>' +
                '<div class="mcp-card-desc">' + _mcpEsc(server.description || '') + '</div>' +
                '<code class="mcp-card-command">' + _mcpEsc(detail + env) + '</code>' +
                '<div class="mcp-card-status">' + _mcpEsc(status) + '</div>' +
                (registrationWarnings.length ? '<div class="mcp-card-warning">' + _mcpEsc(_mcpTr('mcp_registration_warning', { warning: registrationWarnings.join('; ') }, '注意：{{warning}}')) + '</div>' : '') +
                '<div class="mcp-card-assigned">' + _mcpEsc(_mcpTr('mcp_assigned_to', null, '分配给')) + ': ' + _mcpEsc(assignedText) + '</div>' +
            '</div>' +
            '<div class="mcp-card-actions">' +
                '<button type="button" title="' + _mcpEsc(_mcpTr('mcp_register_openclaw_title', null, '注册到 OpenClaw')) + '" data-mcp-action="openclaw" data-mcp-name="' + _mcpEsc(server.name) + '">' + _mcpEsc(_mcpTr('mcp_register_openclaw', null, '注册 OpenClaw')) + '</button>' +
                '<button type="button" title="' + _mcpEsc(_mcpTr('mcp_register_codex_title', null, '注册到 Codex')) + '" data-mcp-action="codex" data-mcp-name="' + _mcpEsc(server.name) + '">' + _mcpEsc(_mcpTr('mcp_register_codex', null, '注册 Codex')) + '</button>' +
                '<button type="button" title="' + _mcpEsc(_mcpTr('mcp_register_claude_title', null, '注册到 Claude')) + '" data-mcp-action="claude" data-mcp-name="' + _mcpEsc(server.name) + '">' + _mcpEsc(_mcpTr('mcp_register_claude', null, '注册 Claude')) + '</button>' +
                '<button type="button" title="' + _mcpEsc(_mcpTr('mcp_assign_agent_title', null, '分配给 Agent 并安装说明 skill')) + '" data-mcp-action="toggle-skill" data-mcp-name="' + _mcpEsc(server.name) + '">' + _mcpEsc(_mcpTr('mcp_assign_agent', null, '分配 Agent')) + '</button>' +
                '<button type="button" title="' + _mcpEsc(_mcpTr('delete', null, '删除')) + '" data-mcp-action="delete" data-mcp-name="' + _mcpEsc(server.name) + '">' + _mcpEsc(_mcpTr('delete', null, '删除')) + '</button>' +
            '</div>' +
            '<div class="mcp-install-row" id="mcp-install-' + _mcpEsc(server.name) + '" style="display:none"></div>' +
        '</div>';
    }).join('');
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
            var warnings = data[client] && data[client].warnings;
            if (Array.isArray(warnings) && warnings.length) {
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
        }).join('') + '</select><button type="button" data-mcp-action="install-skill" data-mcp-name="' + _mcpEsc(name) + '"' + (agents.length ? '' : ' disabled') + '>' + _mcpEsc(_mcpTr('mcp_assign_and_install', null, '分配并安装')) + '</button>';
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
            }, '已注册到 {{client}} 并分配给 {{agent}}'));
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
    deleteMcpServer
});
