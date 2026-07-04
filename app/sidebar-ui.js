// Sidebar, branch management, and sidebar counters.
// --- SIDEBAR ---
function _agentStateLabel(state) {
    var key = {
        moving: 'agent_state_moving',
        meeting: 'agent_state_meeting',
        lounge: 'agent_state_lounge',
        break: 'agent_state_break',
        chatting: 'agent_state_chatting',
        stretching: 'agent_state_stretching',
        walking: 'agent_state_walking',
        lounging: 'agent_state_lounging',
        reading: 'agent_state_reading',
        gazing: 'agent_state_gazing',
        browsing: 'agent_state_browsing',
        snacking: 'agent_state_snacking',
        cooking: 'agent_state_cooking',
        socializing: 'agent_state_socializing',
        playing_darts: 'agent_state_playing_darts',
        playing_ping_pong: 'agent_state_playing_ping_pong',
        at_ping_pong: 'agent_state_at_ping_pong',
        watching_ping_pong: 'agent_state_watching_ping_pong',
        coffee_break: 'agent_state_coffee_break',
        hydrating: 'agent_state_hydrating',
        watching_tv: 'agent_state_watching_tv',
        sipping: 'agent_state_sipping',
        eating: 'agent_state_eating'
    }[state];
    if (typeof i18n === 'undefined') return state;
    return key ? i18n.t(key) : i18n.t('agent_state_unknown', { state: state });
}

function updateSidebar() {
    const container = document.getElementById('branch-sections-container');
    if (!container) return;
    container.innerHTML = '';
    ensureValidAgentBranches();

    let counts = { working: 0, idle: 0, meeting: 0, break: 0 };
    const byBranch = {};
    getBranchList().forEach(function(branch) { byBranch[branch.id] = []; });

    agents.forEach(agent => {
        const isMoving = Math.abs(agent.targetX - agent.x) > agent.speed || Math.abs(agent.targetY - agent.y) > agent.speed;
        let displayState = isMoving ? 'moving' : agent.state;
        if (agent.state === 'visiting') displayState = 'meeting';
        if (agent.idleAction === 'lounge') displayState = 'lounge';
        if (agent.idleAction === 'break') displayState = 'break';
        if (agent.idleAction === 'visit') displayState = 'chatting';
        if (agent.idleAction === 'stretch') displayState = 'stretching';
        if (agent.idleAction === 'wander') displayState = 'walking';
        if (agent.idleAction === 'couch') displayState = 'lounging';
        if (agent.idleAction === 'read_book') displayState = 'reading';
        if (agent.idleAction === 'look_window') displayState = 'gazing';
        if (agent.idleAction === 'break_browse') displayState = 'browsing';
        if (agent.idleAction === 'object_queue_wait') displayState = 'queued';
        if (agent.idleAction === 'get_snack') displayState = 'snacking';
        if (agent.idleAction === 'make_food') displayState = 'cooking';
        if (agent.idleAction === 'gathering') displayState = 'socializing';
        if (agent.idleAction === 'darts') displayState = 'playing_darts';
        if (agent.idleAction === 'pong') displayState = 'playing_ping_pong';
        if (agent.idleAction === 'pong_wait') displayState = 'at_ping_pong';
        if (agent.idleAction === 'pong_spectator') displayState = 'watching_ping_pong';
        if (agent.idleAction === 'make_coffee') displayState = 'coffee_break';
        if (agent.idleAction === 'get_water') displayState = 'hydrating';
        if (agent.idleAction === 'watch_tv') displayState = 'watching_tv';
        if (agent.carryItem && !agent.idleAction) displayState = agent.carryItem === 'coffee' ? 'sipping' : agent.carryItem === 'water' ? 'hydrating' : agent.carryItem === 'food' ? 'eating' : 'snacking';

        if (agent.state === 'meeting' || agent.state === 'visiting') counts.meeting++;
        else if (agent.state === 'working') counts.working++;
        else if (agent.state === 'lounge' || agent.idleAction === 'lounge') counts.break++;
        else if (agent.state === 'break' || agent.idleAction === 'break') counts.break++;
        else counts.idle++;

        const div = document.createElement('div');
        div.className = 'agent-entry';
        div.innerHTML = `<span class="dot ${displayState}"></span><span class="name">${agent.emoji} ${agent.name}</span><span class="state">${_agentStateLabel(displayState)}</span>`;
        div.onclick = () => openModal(agent);
        const branchId = byBranch[agent.branch] ? agent.branch : 'UNASSIGNED';
        byBranch[branchId].push(div);
    });

    getBranchList().forEach(function(branch) {
        const section = document.createElement('div');
        section.className = 'branch-section collapsible ' + getBranchTheme(branch.id);
        if (branch.color) {
            section.style.borderColor = branch.color;
        }

        const header = document.createElement('h4');
        header.className = 'branch-header-row';
        if (branch.color) header.style.color = branch.color;
        header.innerHTML = `<span class="section-arrow">▼</span> ${branch.emoji} ${branch.name}`;
        header.onclick = function(e) { if (e.target.closest('.branch-actions')) return; toggleSection(header); };

        const actions = document.createElement('span');
        actions.className = 'branch-actions';
        if (branch.id !== 'UNASSIGNED') {
            const editBtn = document.createElement('button');
            editBtn.textContent = '✏️';
            editBtn.title = typeof i18n !== 'undefined' ? i18n.t('edit_branch') : 'Edit branch';
            editBtn.onclick = function(e) { e.stopPropagation(); branchEditPrompt(branch.id); };
            const delBtn = document.createElement('button');
            delBtn.textContent = '🗑️';
            delBtn.title = typeof i18n !== 'undefined' ? i18n.t('delete_branch') : 'Delete branch';
            delBtn.onclick = function(e) { e.stopPropagation(); branchDeletePrompt(branch.id); };
            actions.appendChild(editBtn);
            actions.appendChild(delBtn);
        }
        header.appendChild(actions);
        section.appendChild(header);

        const body = document.createElement('div');
        body.className = 'section-body';
        body.style.display = 'block';
        const list = document.createElement('div');
        list.className = 'agent-list';
        (byBranch[branch.id] || []).forEach(function(node) { list.appendChild(node); });
        body.appendChild(list);
        if (branch.id === 'UNASSIGNED') {
            const note = document.createElement('div');
            note.className = 'branch-unassigned-note';
            note.textContent = typeof i18n !== 'undefined' ? i18n.t('delete_branch_note') : 'Deleting a branch moves agents here.';
            body.appendChild(note);
        }
        section.appendChild(body);
        container.appendChild(section);
    });

    document.getElementById('count-working').textContent = counts.working;
    document.getElementById('count-idle').textContent = counts.idle;
    document.getElementById('count-meeting').textContent = counts.meeting;
    document.getElementById('count-break').textContent = counts.break;
}
setInterval(updateSidebar, 1000);

function branchCreatePrompt() {
    var name = prompt(typeof i18n !== 'undefined' ? i18n.t('new_branch_name_prompt') : 'New branch name:');
    if (!name) return;
    var emoji = prompt(typeof i18n !== 'undefined' ? i18n.t('branch_emoji_prompt') : 'Branch emoji:', '🏢') || '🏢';
    var idBase = name.toUpperCase().replace(/[^A-Z0-9]+/g, '_').replace(/^_+|_+$/g, '').slice(0, 24) || 'BRANCH';
    var id = idBase;
    var n = 2;
    while (officeConfig.branches.some(function(b){ return b.id === id; })) id = idBase + '_' + (n++);
    var defaultColors = ['#ffd700','#1565c0','#e65100','#00bcd4','#ff6d00','#9c27b0','#2e7d32'];
    var color = defaultColors[officeConfig.branches.length % defaultColors.length];
    officeConfig.branches.push({ id: id, name: name, emoji: emoji, color: color, theme: 'branch-gray' });
    _invalidateBranchCache();
    saveOfficeConfig();
    updateSidebar();
    // Immediately open the editor for the new branch
    branchEditPrompt(id);
}

function branchEditPrompt(branchId) {
    var branch = officeConfig.branches.find(function(b){ return b.id === branchId; });
    if (!branch) return;
    // Remove existing popup if any
    var existing = document.getElementById('branch-edit-popup');
    if (existing) existing.remove();

    var popup = document.createElement('div');
    popup.id = 'branch-edit-popup';
    popup.style.cssText = 'position:fixed;top:50%;left:50%;transform:translate(-50%,-50%);z-index:99999;background:#1a1a2e;border:2px solid #ffd700;border-radius:12px;padding:20px;min-width:320px;max-width:400px;box-shadow:0 8px 40px rgba(0,0,0,0.6);font-family:Arial,sans-serif;color:#e0e0e0;';

    // Get the current branch color
    var currentColor = branch.color || _getThemeColor(branch.theme) || '#888888';

    popup.innerHTML = '<div style="font-size:14px;font-weight:bold;color:#ffd700;margin-bottom:14px;">✏️ ' + (typeof i18n !== 'undefined' ? i18n.t('edit_branch_title_prefix') : 'Edit Branch') + ': ' + (branch.emoji || '') + ' ' + branch.name + '</div>' +
        '<label style="font-size:12px;color:#aaa;">' + (typeof i18n !== 'undefined' ? i18n.t('branch_name_label') : 'Branch Name') + '</label>' +
        '<input id="be-name" type="text" value="' + (branch.name || '') + '" style="width:100%;padding:8px;background:#0d0d1e;border:1px solid #2a2a4e;border-radius:6px;color:#e0e0e0;font-size:14px;margin:4px 0 10px;">' +
        '<label style="font-size:12px;color:#aaa;">' + (typeof i18n !== 'undefined' ? i18n.t('emoji_label') : 'Emoji') + '</label>' +
        '<input id="be-emoji" type="text" value="' + (branch.emoji || '🏢') + '" style="width:60px;padding:8px;background:#0d0d1e;border:1px solid #2a2a4e;border-radius:6px;color:#e0e0e0;font-size:14px;margin:4px 0 10px;">' +
        '<label style="font-size:12px;color:#aaa;">' + (typeof i18n !== 'undefined' ? i18n.t('branch_color_label') : 'Branch Color') + '</label>' +
        '<div style="display:flex;align-items:center;gap:8px;margin:4px 0 12px;">' +
        '<input id="be-color" type="color" value="' + currentColor + '" style="width:40px;height:32px;border:none;background:none;cursor:pointer;">' +
        '<span id="be-color-hex" style="font-size:12px;color:#888;">' + currentColor + '</span>' +
        '</div>' +
        '<label style="font-size:12px;color:#aaa;">Agents in Branch</label>' +
        '<div id="be-agents" style="max-height:180px;overflow-y:auto;margin:4px 0 12px;border:1px solid #2a2a4e;border-radius:6px;padding:6px;background:#0d0d1e;"></div>' +
        '<div style="display:flex;gap:8px;justify-content:flex-end;margin-top:10px;">' +
        '<button id="be-cancel" style="padding:6px 16px;background:#333;border:1px solid #555;border-radius:6px;color:#ccc;cursor:pointer;font-size:12px;">Cancel</button>' +
        '<button id="be-save" style="padding:6px 16px;background:#ffd700;border:none;border-radius:6px;color:#000;font-weight:bold;cursor:pointer;font-size:12px;">Save</button>' +
        '</div>';

    document.body.appendChild(popup);

    // Color picker live update
    document.getElementById('be-color').addEventListener('input', function() {
        document.getElementById('be-color-hex').textContent = this.value;
    });

    // Populate agent checkboxes
    var agentDiv = document.getElementById('be-agents');
    var allAgents = agents.slice().sort(function(a,b){ return a.name.localeCompare(b.name); });
    allAgents.forEach(function(a) {
        var row = document.createElement('label');
        row.style.cssText = 'display:flex;align-items:center;gap:6px;padding:3px 4px;cursor:pointer;font-size:12px;border-radius:4px;';
        row.onmouseenter = function(){ this.style.background='rgba(255,255,255,0.05)'; };
        row.onmouseleave = function(){ this.style.background=''; };
        var cb = document.createElement('input');
        cb.type = 'checkbox';
        cb.value = a.statusKey || a.id;
        cb.checked = (a.branch === branchId);
        row.appendChild(cb);
        row.appendChild(document.createTextNode(a.emoji + ' ' + a.name));
        agentDiv.appendChild(row);
    });

    // Cancel
    document.getElementById('be-cancel').onclick = function() { popup.remove(); };

    // Save
    document.getElementById('be-save').onclick = function() {
        branch.name = document.getElementById('be-name').value || branch.name;
        branch.emoji = document.getElementById('be-emoji').value || '🏢';
        branch.color = document.getElementById('be-color').value;
        // Update agent assignments
        var checkboxes = agentDiv.querySelectorAll('input[type=checkbox]');
        checkboxes.forEach(function(cb) {
            var agentKey = cb.value;
            var agent = agents.find(function(a){ return (a.statusKey || a.id) === agentKey; });
            if (!agent) return;
            if (cb.checked) {
                agent.branch = branchId;
            } else if (agent.branch === branchId) {
                agent.branch = 'UNASSIGNED';
            }
            // Also update officeConfig.agents
            if (officeConfig.agents) {
                var cfgAgent = officeConfig.agents.find(function(a){ return a.id === agentKey || a.statusKey === agentKey; });
                if (cfgAgent) cfgAgent.branch = agent.branch;
            }
        });
        _invalidateBranchCache();
        saveOfficeConfig();
        updateSidebar();
        if (_agentPanelSelectedId) _acpSelectAgent(_agentPanelSelectedId);
        popup.remove();
    };

    // Close on Escape
    var escHandler = function(e) { if (e.key === 'Escape') { popup.remove(); document.removeEventListener('keydown', escHandler); } };
    document.addEventListener('keydown', escHandler);
}

function _getThemeColor(theme) {
    var map = {'branch-gold':'#ffd700','branch-blue':'#1565c0','branch-orange':'#e65100','branch-cyan':'#00bcd4','branch-red':'#ff6d00','branch-gray':'#90a4ae'};
    return map[theme] || '#888888';
}

function branchDeletePrompt(branchId) {
    var branch = officeConfig.branches.find(function(b){ return b.id === branchId; });
    if (!branch) return;
    if (!confirm(_tr('delete_branch_confirm', { name: branch.name }))) return;
    officeConfig.branches = officeConfig.branches.filter(function(b){ return b.id !== branchId; });
    _invalidateBranchCache();
    agents.forEach(function(a){ if (a.branch === branchId) a.branch = 'UNASSIGNED'; });
    if (officeConfig.agents) officeConfig.agents.forEach(function(a){ if (a.branch === branchId) a.branch = 'UNASSIGNED'; });
    saveOfficeConfig();
    updateSidebar();
    if (_agentPanelSelectedId) _acpSelectAgent(_agentPanelSelectedId);
}

Object.assign(window, {
    updateSidebar,
    branchCreatePrompt,
    branchEditPrompt,
    branchDeletePrompt,
    _getThemeColor
});
