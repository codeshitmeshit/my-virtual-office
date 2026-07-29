// MCP registry panel for VO-managed MCP servers.

var _mcpServers = [];

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
    } catch (e) {
        _mcpServers = [];
        if (typeof _acpShowToast === 'function') _acpShowToast(_mcpTr('mcp_load_failed', { error: e.message }, 'MCP 注册表加载失败：{{error}}'));
    }
    renderMcpRegistry();
}

function renderMcpRegistry() {
    var list = document.getElementById('mcp-registry-list');
    if (!list) return;
    if (!_mcpServers.length) {
        list.innerHTML = '<div class="mcp-empty">' + _mcpEsc(_mcpTr('mcp_empty', null, 'VO 中暂无 MCP server。')) + '</div>';
        return;
    }
    list.innerHTML = _mcpServers.map(function(server) {
        var status = server.openclaw && server.openclaw.registered
            ? _mcpTr('mcp_status_openclaw', null, '已注册到 OpenClaw')
            : _mcpTr('mcp_status_vo_only', null, '仅在 VO 中保存');
        var detail = server.transport === 'stdio'
            ? [server.command || '', (server.args || []).join(' ')].join(' ').trim()
            : [server.transport || '', server.url || ''].join(' ').trim();
        var env = server.envKeys && server.envKeys.length ? ' ' + _mcpTr('mcp_env_keys', null, '环境变量') + ': ' + server.envKeys.join(', ') : '';
        return '<div class="mcp-card">' +
            '<div class="mcp-card-main">' +
                '<div class="mcp-card-title">' + _mcpEsc(server.name) + '</div>' +
                '<div class="mcp-card-desc">' + _mcpEsc(server.description || '') + '</div>' +
                '<code class="mcp-card-command">' + _mcpEsc(detail + env) + '</code>' +
                '<div class="mcp-card-status">' + _mcpEsc(status) + '</div>' +
            '</div>' +
            '<div class="mcp-card-actions">' +
                '<button type="button" title="' + _mcpEsc(_mcpTr('mcp_register_openclaw_title', null, '注册到 OpenClaw')) + '" data-mcp-action="openclaw" data-mcp-name="' + _mcpEsc(server.name) + '">' + _mcpEsc(_mcpTr('mcp_register_openclaw', null, '注册 OpenClaw')) + '</button>' +
                '<button type="button" title="' + _mcpEsc(_mcpTr('mcp_install_skill_title', null, '安装说明 skill')) + '" data-mcp-action="toggle-skill" data-mcp-name="' + _mcpEsc(server.name) + '">' + _mcpEsc(_mcpTr('mcp_install_skill', null, '安装 Skill')) + '</button>' +
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
        var res = await fetch('/api/mcp-registry', {
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
        var res = await fetch('/api/mcp-registry/templates/vibe-trading', { method: 'POST' });
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
    try {
        var res = await fetch('/api/mcp-registry/' + encodeURIComponent(name) + '/openclaw', { method: 'POST' });
        var data = await res.json();
        if (!res.ok || !data.ok) throw new Error(data.error || _mcpTr('mcp_openclaw_failed_plain', null, 'OpenClaw 注册失败'));
        if (typeof _acpShowToast === 'function') _acpShowToast(_mcpTr('mcp_openclaw_registered', { name: name }, '已注册到 OpenClaw：{{name}}'));
        refreshMcpRegistry();
    } catch (e) {
        if (typeof _acpShowToast === 'function') _acpShowToast(_mcpTr('mcp_openclaw_failed', { error: e.message }, 'OpenClaw 注册失败：{{error}}'));
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
        var res = await fetch('/api/agents', { cache: 'no-store' });
        var data = await res.json();
        var agents = (data.agents || []).filter(function(agent) {
            return String(agent.providerKind || 'openclaw').toLowerCase() === 'openclaw';
        });
        row.innerHTML = '<select id="mcp-agent-' + _mcpEsc(name) + '">' + agents.map(function(agent) {
            return '<option value="' + _mcpEsc(agent.id) + '">' + _mcpEsc((agent.emoji || '') + ' ' + (agent.name || agent.id)) + '</option>';
        }).join('') + '</select><button type="button" data-mcp-action="install-skill" data-mcp-name="' + _mcpEsc(name) + '">' + _mcpEsc(_mcpTr('install', null, '安装')) + '</button>';
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
        var res = await fetch('/api/mcp-registry/' + encodeURIComponent(name) + '/skill', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ agentId: agentId, overwrite: true })
        });
        var data = await res.json();
        if (!res.ok || !data.ok) throw new Error(data.error || _mcpTr('mcp_skill_failed_plain', null, 'Skill 安装失败'));
        if (typeof _acpShowToast === 'function') _acpShowToast(_mcpTr('mcp_skill_installed', { agent: agentId }, 'MCP skill 已安装到 {{agent}}'));
    } catch (e) {
        if (typeof _acpShowToast === 'function') _acpShowToast(_mcpTr('mcp_skill_failed', { error: e.message }, 'Skill 安装失败：{{error}}'));
    }
}

async function deleteMcpServer(name) {
    if (!confirm(_mcpTr('mcp_delete_confirm', { name: name }, '从 VO 注册表删除 MCP server "{{name}}"？'))) return;
    try {
        var res = await fetch('/api/mcp-registry/' + encodeURIComponent(name), { method: 'DELETE' });
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
    if (action === 'openclaw') registerMcpInOpenClaw(name);
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
    toggleMcpSkillInstall,
    installMcpSkill,
    deleteMcpServer
});
