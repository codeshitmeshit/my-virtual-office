// --- AGENT CREATOR PANEL ---
var _agentPanel = null;
var _agentPanelSelectedId = null;
var _agentPanelPreviewCanvas = null;
var _agentPanelPreviewCtx = null;
var _agentPanelEditState = null; // working copy of appearance being edited
var _acpUndoStack = [];
var _acpUnsaved = false;

function toggleAgentPanel() {
    if (window._voLicense && window._voLicense.demo) {
        alert(_tr('premium_agent_editor'));
        return;
    }
    if (!_agentPanel) _buildAgentPanel();
    if (_agentPanel.classList.contains('visible')) {
        _agentPanel.classList.remove('visible');
    } else {
        _agentPanel.classList.add('visible');
        _acpRefreshList();
        if (!_agentPanelSelectedId && agents.length > 0) {
            _acpSelectAgent(agents[0].id);
        }
    }
}

function _buildAgentPanel() {
    if (_agentPanel) return;

    var panel = document.createElement('div');
    panel.id = 'agent-creator-panel';
    panel.className = 'agent-panel';

    // Header
    var header = document.createElement('div');
    header.className = 'agent-panel-header';
    var title = document.createElement('span');
    title.className = 'agent-panel-title';
    title.textContent = '👤 ' + (typeof i18n !== 'undefined' ? i18n.t('agents_title') : 'AGENTS');
    header.appendChild(title);
    var closeBtn = document.createElement('button');
    closeBtn.textContent = '✕ ' + (typeof i18n !== 'undefined' ? i18n.t('close_btn') : 'Close');
    closeBtn.className = 'catalog-close-btn';
    closeBtn.onclick = toggleAgentPanel;
    header.appendChild(closeBtn);
    panel.appendChild(header);

    // Scrollable body
    var body = document.createElement('div');
    body.className = 'agent-panel-body';

    var addBtn = document.createElement('button');
    addBtn.textContent = '➕ ' + (typeof i18n !== 'undefined' ? i18n.t('new_agent') : 'New Agent');
    addBtn.className = 'agent-add-btn';
    addBtn.onclick = _acpCreateNewAgent;
    body.appendChild(addBtn);

    var listEl = document.createElement('div');
    listEl.id = 'acp-agent-list';
    body.appendChild(listEl);

    var sep = document.createElement('div');
    sep.className = 'agent-panel-sep';
    body.appendChild(sep);

    var editorEl = document.createElement('div');
    editorEl.id = 'acp-editor';
    body.appendChild(editorEl);

    panel.appendChild(body);
    var _agentWrapper = document.querySelector('.game-wrapper');
    (_agentWrapper || document.body).appendChild(panel);
    _agentPanel = panel;
}

function _acpRefreshList() {
    var container = document.getElementById('acp-agent-list');
    if (!container) return;
    container.innerHTML = '';
    agents.forEach(function(agent) {
        var card = document.createElement('div');
        card.className = 'agent-card' + (agent.id === _agentPanelSelectedId ? ' selected' : '');
        card.innerHTML =
            '<span class="agent-card-emoji">' + agent.emoji + '</span>' +
            '<span class="agent-card-info">' +
                '<span class="agent-card-name">' + agent.name + '</span>' +
                '<span class="agent-card-role">' + agent.role + '</span>' +
            '</span>';
        card.onclick = function() { _acpSelectAgent(agent.id); };
        container.appendChild(card);
    });
}

function _acpSelectAgent(agentId) {
    _agentPanelSelectedId = agentId;
    _acpRefreshList();
    var agent = agents.find(function(a){ return a.id === agentId; });
    if (!agent) return;
    _agentPanelEditState = JSON.parse(JSON.stringify({
        id: agent.id,
        name: agent.name,
        role: agent.role,
        emoji: agent.emoji,
        color: agent.color,
        gender: agent.gender,
        branch: agent.branch || 'UNASSIGNED',
        statusKey: agent.statusKey || '',
        providerKind: agent.providerKind || '',
        providerAgentId: agent.providerAgentId || '',
        profile: agent.profile || '',
        appearance: agent.getAppearance()
    }));
    _acpBuildEditor(agent);
}

function _acpBuildEditor(agent) {
    var col = document.getElementById('acp-editor');
    if (!col) return;
    col.innerHTML = '';
    var es = _agentPanelEditState;

    // Preview area
    var previewWrap = document.createElement('div');
    previewWrap.className = 'agent-preview-wrap';
    var previewCanvas = document.createElement('canvas');
    previewCanvas.width = 80; previewCanvas.height = 100;
    previewCanvas.className = 'agent-preview-canvas';
    _agentPanelPreviewCanvas = previewCanvas;
    _agentPanelPreviewCtx = previewCanvas.getContext('2d');
    previewWrap.appendChild(previewCanvas);
    var previewInfo = document.createElement('div');
    previewInfo.className = 'agent-preview-info';
    previewInfo.innerHTML =
        '<div class="agent-preview-name" id="acp-preview-name">' + es.name + '</div>' +
        '<div class="agent-preview-role" id="acp-preview-role">' + es.role + '</div>' +
        '<div class="agent-preview-role" id="acp-preview-branch">' + _tr('branch_field') + ': ' + getBranchDisplayName(es.branch) + '</div>' +
        '<div class="agent-preview-emoji" id="acp-preview-emoji">' + es.emoji + '</div>';
    previewWrap.appendChild(previewInfo);
    col.appendChild(previewWrap);

    // Save / Undo bar for agent edits
    var editBar = document.createElement('div');
    editBar.style.cssText = 'display:flex;gap:6px;padding:4px 8px;justify-content:center;';
    var agentSaveBtn = document.createElement('button');
    agentSaveBtn.textContent = _tr('save_btn');
    agentSaveBtn.id = 'acp-save-btn';
    agentSaveBtn.style.cssText = 'padding:4px 12px;background:#1b5e20;color:#66bb6a;border:1px solid #66bb6a;border-radius:4px;cursor:pointer;font-size:11px;';
    agentSaveBtn.addEventListener('click', function() {
        _acpSave();
        _acpUnsaved = false;
        _acpShowToast('💾 Agent saved!');
    });
    var agentUndoBtn = document.createElement('button');
    agentUndoBtn.textContent = _tr('undo');
    agentUndoBtn.id = 'acp-undo-btn';
    agentUndoBtn.style.cssText = 'padding:4px 12px;background:#b71c1c;color:#ef5350;border:1px solid #ef5350;border-radius:4px;cursor:pointer;font-size:11px;';
    agentUndoBtn.addEventListener('click', function() {
        if (_acpUndoStack.length === 0) { _acpShowToast('Nothing to undo'); return; }
        var prev = _acpUndoStack.pop();
        // Restore agent appearance
        Object.assign(agent, JSON.parse(prev));
        agent.appearance = JSON.parse(prev).appearance;
        _acpSelectAgent(agent.id);
    });
    editBar.appendChild(agentSaveBtn);
    editBar.appendChild(agentUndoBtn);

    var sectionsWrap = document.createElement('div');
    sectionsWrap.className = 'agent-sections-wrap';

    function makeSection(title) {
        var s = document.createElement('div');
        s.className = 'agent-edit-section';
        var h = document.createElement('div');
        h.className = 'agent-section-header';
        h.textContent = '─── ' + title + ' ───';
        s.appendChild(h);
        return s;
    }
    function makeField(label, control) {
        var row = document.createElement('div');
        row.className = 'agent-field-row';
        var lbl = document.createElement('span');
        lbl.className = 'agent-field-label';
        lbl.textContent = label + ':';
        row.appendChild(lbl);
        row.appendChild(control);
        return row;
    }

    // --- Identity ---
    var idSec = makeSection(_tr('agent_identity'));
    idSec.appendChild(makeField(_tr('agent_name'), _acpText(es.name, function(v){ es.name=v; _acpUpdatePreviewInfo(); _acpAutoSave(); })));
    idSec.appendChild(makeField(_tr('agent_role'), _acpText(es.role, function(v){ es.role=v; _acpUpdatePreviewInfo(); _acpAutoSave(); })));
    idSec.appendChild(makeField(_tr('agent_emoji'), _acpText(es.emoji, function(v){ es.emoji=v; _acpUpdatePreviewInfo(); _acpAutoSave(); })));
    idSec.appendChild(makeField(_tr('agent_gender'), _acpToggle(['M','F'], es.gender, function(v){
        es.gender=v; _acpAutoSave(); _acpBuildEditor(agent);
    })));
    sectionsWrap.appendChild(idSec);

    // --- Colors ---
    var clrSec = makeSection(_tr('agent_colors'));
    clrSec.appendChild(makeField(_tr('agent_shirt'), _acpColor(es.color, function(v){ es.color=v; _acpAutoSave(); })));
    var skinPresets = ['#fddcb5','#ffcc80','#e8b88a','#d4a574','#c68642','#8d5524'];
    clrSec.appendChild(makeField(_tr('agent_skin'), _acpSwatchRow(skinPresets, es.appearance.skinTone, function(v){ es.appearance.skinTone=v; _acpAutoSave(); }, true)));
    sectionsWrap.appendChild(clrSec);

    // --- Hair ---
    var hairSec = makeSection(_tr('agent_hair'));
    var hairStyles = ['bald','buzz','short','medium','long','curly','wavy','spiky','bun','ponytail','mohawk'];
    hairSec.appendChild(makeField(_tr('agent_style'), _acpGridSelect(hairStyles, es.appearance.hairStyle, function(v){ es.appearance.hairStyle=v; _acpAutoSave(); })));
    var hairColorPresets = ['#1a1a1a','#3e2723','#5d4037','#8d6e63','#dcc282','#bf360c','#616161','#e0e0e0'];
    hairSec.appendChild(makeField(_tr('color_field'), _acpSwatchRow(hairColorPresets, es.appearance.hairColor, function(v){ es.appearance.hairColor=v; _acpAutoSave(); }, true)));
    hairSec.appendChild(makeField(_tr('agent_highlight'), _acpColorNullable(es.appearance.hairHighlight, function(v){ es.appearance.hairHighlight=v; _acpAutoSave(); })));
    sectionsWrap.appendChild(hairSec);

    // --- Face ---
    var faceSec = makeSection(_tr('agent_face'));
    var ebStyles = ['thin','thick','angular','arched'];
    faceSec.appendChild(makeField(_tr('agent_eyebrows'), _acpGridSelect(ebStyles, es.appearance.eyebrowStyle, function(v){ es.appearance.eyebrowStyle=v; _acpAutoSave(); })));
    var eyePresets = ['#212121','#1565c0','#2e7d32','#5d4037','#6a1b9a','#37474f'];
    faceSec.appendChild(makeField(_tr('agent_eye_color'), _acpSwatchRow(eyePresets, es.appearance.eyeColor, function(v){ es.appearance.eyeColor=v; _acpAutoSave(); }, true)));
    if (es.gender === 'M') {
        var fhStyles = ['none','stubble','beard','goatee','mustache'];
        faceSec.appendChild(makeField(_tr('agent_facial_hair'), _acpGridSelect(fhStyles, es.appearance.facialHair || 'none', function(v){ es.appearance.facialHair=v==='none'?null:v; _acpAutoSave(); })));
        faceSec.appendChild(makeField(_tr('agent_beard_color'), _acpColorNullable(es.appearance.facialHairColor, function(v){ es.appearance.facialHairColor=v; _acpAutoSave(); })));
    }
    sectionsWrap.appendChild(faceSec);

    // --- Costumes ---
    var costSec = makeSection(_tr('agent_costumes'));
    var costumeTypes = ['none','lobster','chicken'];
    costSec.appendChild(makeField(_tr('agent_costume'), _acpGridSelect(costumeTypes, es.appearance.costume||'none', function(v){ es.appearance.costume=v==='none'?null:v; if(v!=='none') { es.appearance.headwear=null; } _costumeCache={}; _acpAutoSave(); })));
    var costumeNote = document.createElement('div');
    costumeNote.style.cssText = 'font-size:10px;color:#888;margin-top:4px;padding:0 2px;';
    costumeNote.textContent = _tr('costume_note') + ' 🦞 ' + _tr('option_lobster') + '  🐔 ' + _tr('option_chicken');
    costSec.appendChild(costumeNote);
    sectionsWrap.appendChild(costSec);

    // --- Accessories ---
    var accSec = makeSection(_tr('agent_accessories'));
    var hwTypes = ['none','hardhat','cap','crown','tiara','headband','goggles','headset','beanie'];
    accSec.appendChild(makeField(_tr('agent_headwear'), _acpGridSelect(hwTypes, es.appearance.headwear||'none', function(v){ es.appearance.headwear=v==='none'?null:v; _acpAutoSave(); })));
    accSec.appendChild(makeField(_tr('agent_hat_color'), _acpColor(es.appearance.headwearColor||'#888888', function(v){ es.appearance.headwearColor=v; _acpAutoSave(); })));
    var glTypes = ['none','round','square','sunglasses'];
    accSec.appendChild(makeField(_tr('agent_glasses'), _acpGridSelect(glTypes, es.appearance.glasses||'none', function(v){ es.appearance.glasses=v==='none'?null:v; _acpAutoSave(); })));
    accSec.appendChild(makeField(_tr('agent_lens_color'), _acpColor(es.appearance.glassesColor||'#333333', function(v){ es.appearance.glassesColor=v; _acpAutoSave(); })));
    sectionsWrap.appendChild(accSec);

    // --- Items ---
    var itemSec = makeSection(_tr('agent_items'));
    var heldItems = ['none','tablet','wrench','coffee','clipboard','pen','hammer','testTube','book'];
    itemSec.appendChild(makeField(_tr('agent_held_item'), _acpGridSelect(heldItems, es.appearance.heldItem||'none', function(v){ es.appearance.heldItem=v==='none'?null:v; _acpAutoSave(); })));
    var deskItems = ['none','anvil','trophy','calendar','envelope','money','ruler','marker','chart','plans','checklist','microscope','shield','phone','files'];
    itemSec.appendChild(makeField(_tr('agent_desk_item'), _acpGridSelect(deskItems, es.appearance.deskItem||'none', function(v){ es.appearance.deskItem=v==='none'?null:v; _acpAutoSave(); })));
    sectionsWrap.appendChild(itemSec);

    // --- Assignment ---
    var asnSec = makeSection(_tr('agent_assignment'));
    var branchSelect = document.createElement('select');
    branchSelect.style.cssText = 'width:100%;padding:4px 6px;background:#2a2a4e;color:#ccc;border:1px solid #3a3a5e;border-radius:4px;font-size:12px;margin-top:4px;';
    getBranchList().forEach(function(branch) {
        var opt = document.createElement('option');
        opt.value = branch.id;
        opt.textContent = branch.emoji + ' ' + getBranchDisplayName(branch.id);
        branchSelect.appendChild(opt);
    });
    branchSelect.value = es.branch || 'UNASSIGNED';
    branchSelect.addEventListener('change', function() {
        es.branch = this.value;
        _acpUpdatePreviewInfo();
        _acpAutoSave();
    });
    asnSec.appendChild(makeField(_tr('branch_field'), branchSelect));
    var ocSelect = document.createElement('select');
    ocSelect.style.cssText = 'width:100%;padding:4px 6px;background:#2a2a4e;color:#ccc;border:1px solid #3a3a5e;border-radius:4px;font-size:12px;margin-top:4px;';
    // Default option
    var defOpt = document.createElement('option');
    defOpt.value = '';
    defOpt.textContent = _tr('none');
    ocSelect.appendChild(defOpt);
    // Loading placeholder
    var loadOpt = document.createElement('option');
    loadOpt.value = '_loading';
    loadOpt.textContent = _tr('loading_agents');
    loadOpt.disabled = true;
    ocSelect.appendChild(loadOpt);
    ocSelect.value = es.statusKey || '';
    // Fetch agent list from server
    fetch('/agents-list').then(function(res) { return res.json(); }).then(function(data) {
        // Remove loading placeholder
        if (loadOpt.parentNode) loadOpt.remove();
        // Get already-assigned agent IDs (exclude current agent)
        var assignedIds = {};
        agents.forEach(function(a) {
            if (a.statusKey && a.id !== agent.id) assignedIds[a.statusKey] = a.name;
        });
        (data.agents || []).forEach(function(oc) {
            var opt = document.createElement('option');
            opt.value = oc.key;
            var label = (oc.emoji || '') + ' ' + oc.name + ' (' + oc.agentId + ')';
            if (assignedIds[oc.key]) label += ' — ' + _tr('assigned_to_agent', { name: assignedIds[oc.key] });
            opt.textContent = label;
            if (assignedIds[oc.key]) { opt.style.color = '#666'; }
            ocSelect.appendChild(opt);
        });
        ocSelect.value = es.statusKey || '';
    }).catch(function() {
            if (loadOpt.parentNode) { loadOpt.textContent = _tr('failed_to_load'); }
    });
    ocSelect.addEventListener('change', function() {
        es.statusKey = ocSelect.value;
        // Also update the agent's statusKey for status polling
        agent.statusKey = ocSelect.value;
        _acpAutoSave();
    });
    asnSec.appendChild(makeField(_tr('openclaw_agent'), ocSelect));
    sectionsWrap.appendChild(asnSec);

    col.appendChild(sectionsWrap);

    // Delete button (any agent except main)
    if (agent.id !== 'main') {
        var delWrap = document.createElement('div');
        delWrap.className = 'agent-delete-wrap';
        var delBtn = document.createElement('button');
    delBtn.innerHTML = _tr('delete_agent');
        delBtn.className = 'agent-delete-btn';
        delBtn.onclick = function() { _acpDeleteAgent(agent.id); };
        delWrap.appendChild(delBtn);
        col.appendChild(delWrap);
    }

    // Save / Undo bar at the bottom
    col.appendChild(editBar);

    _acpUpdatePreview();
}


function _acpText(value, onChange) {
    var inp = document.createElement('input');
    inp.type = 'text';
    inp.value = value || '';
    inp.style.cssText = 'background:#1a1a3e;border:1px solid #2a2a4e;color:#e8e8f0;padding:4px 6px;font-size:11px;flex:1;border-radius:2px';
    inp.oninput = function(){ onChange(inp.value); };
    return inp;
}

function _acpColor(value, onChange) {
    var wrap = document.createElement('div');
    wrap.style.cssText = 'display:flex;align-items:center;gap:6px';
    var inp = document.createElement('input');
    inp.type = 'color';
    inp.value = value || '#888888';
    inp.style.cssText = 'width:36px;height:24px;border:1px solid #2a2a4e;background:none;cursor:pointer;padding:1px';
    inp.oninput = function(){ onChange(inp.value); };
    wrap.appendChild(inp);
    return wrap;
}

function _acpColorNullable(value, onChange) {
    var wrap = document.createElement('div');
    wrap.style.cssText = 'display:flex;align-items:center;gap:6px';
    var chk = document.createElement('input');
    chk.type = 'checkbox';
    chk.checked = !!value;
    chk.style.cssText = 'cursor:pointer';
    var inp = document.createElement('input');
    inp.type = 'color';
    inp.value = value || '#888888';
    inp.disabled = !value;
    inp.style.cssText = 'width:36px;height:24px;border:1px solid #2a2a4e;background:none;cursor:pointer;padding:1px;opacity:' + (value ? '1' : '0.3');
    chk.onchange = function(){
        inp.disabled = !chk.checked;
        inp.style.opacity = chk.checked ? '1' : '0.3';
        onChange(chk.checked ? inp.value : null);
    };
    inp.oninput = function(){ if (chk.checked) onChange(inp.value); };
    wrap.appendChild(chk);
    wrap.appendChild(inp);
    return wrap;
}

function _acpToggle(options, value, onChange) {
    var wrap = document.createElement('div');
    wrap.style.cssText = 'display:flex;gap:4px';
    options.forEach(function(opt) {
        var btn = document.createElement('button');
        btn.textContent = (opt === 'M' || opt === 'F') ? opt : _tr('option_' + opt);
        var active = opt === value;
        btn.style.cssText = 'padding:3px 10px;border:1px solid ' + (active ? '#ffd600' : '#2a2a4e') + ';background:' + (active ? '#3a3a10' : '#1a1a3e') + ';color:' + (active ? '#ffd600' : '#aaa') + ';cursor:pointer;font-size:11px;border-radius:2px';
        btn.onclick = function(){
            wrap.querySelectorAll('button').forEach(function(b){ b.style.borderColor='#2a2a4e'; b.style.background='#1a1a3e'; b.style.color='#aaa'; });
            btn.style.borderColor='#ffd600'; btn.style.background='#3a3a10'; btn.style.color='#ffd600';
            onChange(opt);
        };
        wrap.appendChild(btn);
    });
    return wrap;
}

function _acpSwatchRow(presets, value, onChange, allowCustom) {
    var wrap = document.createElement('div');
    wrap.style.cssText = 'display:flex;flex-wrap:wrap;gap:3px;align-items:center';
    presets.forEach(function(c) {
        var sw = document.createElement('div');
        var isSelected = c.toLowerCase() === (value||'').toLowerCase();
        sw.className = 'swatch' + (isSelected ? ' selected' : '');
        sw.style.background = c;
        sw.title = c;
        sw.onclick = function(){
            wrap.querySelectorAll('.swatch').forEach(function(s){ s.classList.remove('selected'); });
            sw.classList.add('selected');
            onChange(c);
        };
        wrap.appendChild(sw);
    });
    if (allowCustom) {
        var inp = document.createElement('input');
        inp.type = 'color';
        inp.value = value || '#888888';
            inp.title = _tr('custom_color');
        inp.style.cssText = 'width:22px;height:22px;border:1px solid #444;background:none;cursor:pointer;padding:1px';
        inp.oninput = function(){
            wrap.querySelectorAll('.swatch').forEach(function(s){ s.classList.remove('selected'); });
            onChange(inp.value);
        };
        wrap.appendChild(inp);
    }
    return wrap;
}

function _acpGridSelect(options, value, onChange) {
    var wrap = document.createElement('div');
    wrap.style.cssText = 'display:flex;flex-wrap:wrap;gap:3px';
    options.forEach(function(opt) {
        var btn = document.createElement('button');
        btn.textContent = _tr('option_' + opt);
        btn.className = 'option-btn' + (opt === (value || 'none') ? ' selected' : '');
        btn.onclick = function(){
            wrap.querySelectorAll('.option-btn').forEach(function(b){ b.classList.remove('selected'); });
            btn.classList.add('selected');
            onChange(opt);
        };
        wrap.appendChild(btn);
    });
    return wrap;
}

function _acpUpdatePreviewInfo() {
    var es = _agentPanelEditState;
    if (!es) return;
    var nameEl = document.getElementById('acp-preview-name');
    var roleEl = document.getElementById('acp-preview-role');
    var branchEl = document.getElementById('acp-preview-branch');
    var emojiEl = document.getElementById('acp-preview-emoji');
    if (nameEl) nameEl.textContent = es.name;
    if (roleEl) roleEl.textContent = es.role;
    if (branchEl) branchEl.textContent = _tr('branch_field') + ': ' + getBranchDisplayName(es.branch);
    if (emojiEl) emojiEl.textContent = es.emoji;
    _acpUpdatePreview();
}

function _acpUpdatePreview() {
    var pCtx = _agentPanelPreviewCtx;
    var pCanvas = _agentPanelPreviewCanvas;
    if (!pCtx || !pCanvas) return;
    var es = _agentPanelEditState;
    if (!es) return;

    // Clear
    pCtx.clearRect(0, 0, pCanvas.width, pCanvas.height);
    pCtx.fillStyle = '#1a1a2e';
    pCtx.fillRect(0, 0, pCanvas.width, pCanvas.height);

    // Draw mini agent at center
    pCtx.save();
    pCtx.translate(40, 75);
    pCtx.scale(1.5, 1.5);

    var app = es.appearance;
    var isFem = es.gender === 'F';

    // Shadow
    pCtx.fillStyle = 'rgba(0,0,0,0.2)';
    pCtx.beginPath(); pCtx.ellipse(0, 4, 12, 5, 0, 0, Math.PI * 2); pCtx.fill();

    // Legs
    pCtx.fillStyle = '#1a1a2e';
    pCtx.fillRect(-10, -2, 8, 8); pCtx.fillRect(2, -2, 8, 8);

    // Body
    pCtx.fillStyle = es.color || '#888';
    if (isFem) {
        pCtx.fillRect(-9, -22, 18, 6); pCtx.fillRect(-8, -16, 16, 9);
    } else {
        pCtx.fillRect(-10, -22, 20, 15);
    }

    // Arms
    pCtx.fillRect(isFem ? -11 : -12, -20, 3, 10);
    pCtx.fillRect(9, -20, 3, 10);

    // Head
    pCtx.fillStyle = app.skinTone || '#ffcc80';
    pCtx.fillRect(-12, -38, 24, 18);

    // Hair
    _drawHairByConfig(pCtx, app.hairStyle, app.hairColor, app.hairHighlight);

    // Eyebrows
    var ebStyle = app.eyebrowStyle || (isFem ? 'thin' : 'thick');
    if (ebStyle === 'thin' || ebStyle === 'arched') {
        pCtx.fillStyle = '#5d4037';
        pCtx.fillRect(-5, -33, 4, 1); pCtx.fillRect(4, -33, 4, 1);
        pCtx.fillRect(-6, -34, 2, 1); pCtx.fillRect(7, -34, 2, 1);
    } else {
        pCtx.fillStyle = '#3e2723';
        pCtx.fillRect(-5, -34, 5, 2); pCtx.fillRect(4, -34, 5, 2);
    }

    // Eyes
    pCtx.fillStyle = '#fff';
    pCtx.fillRect(-6, -31, 6, 5); pCtx.fillRect(3, -31, 6, 5);
    pCtx.fillStyle = app.eyeColor || '#212121';
    pCtx.fillRect(-4, -30, 3, 4); pCtx.fillRect(5, -30, 3, 4);
    pCtx.fillStyle = '#fff';
    pCtx.fillRect(-3, -30, 1, 1); pCtx.fillRect(6, -30, 1, 1);
    if (isFem) {
        pCtx.fillStyle = '#212121';
        pCtx.fillRect(-7, -32, 1, 2); pCtx.fillRect(-6, -33, 1, 2);
        pCtx.fillRect(8, -32, 1, 2); pCtx.fillRect(9, -33, 1, 2);
    }

    // Nose
    var skinVal = app.skinTone || '#ffcc80';
    pCtx.fillStyle = darken(skinVal, 0.15);
    pCtx.fillRect(0, -27, 2, 2);

    // Mouth
    if (isFem) {
        pCtx.fillStyle = '#c4626a'; pCtx.fillRect(-2, -24, 5, 2);
        pCtx.fillStyle = '#d47a82'; pCtx.fillRect(-1, -24, 3, 1);
    } else {
        pCtx.fillStyle = darken(skinVal, 0.25); pCtx.fillRect(-2, -24, 4, 1);
    }

    // Facial hair
    if (app.facialHair) {
        pCtx.fillStyle = app.facialHairColor || darken(skinVal, 0.4);
        if (app.facialHair === 'stubble') { pCtx.globalAlpha=0.4; pCtx.fillRect(-8,-26,16,4); pCtx.globalAlpha=1; }
        else if (app.facialHair === 'beard') { pCtx.fillRect(-8,-27,16,8); pCtx.fillStyle=skinVal; pCtx.fillRect(-3,-26,6,3); }
        else if (app.facialHair === 'goatee') { pCtx.fillRect(-4,-25,8,4); }
        else if (app.facialHair === 'mustache') { pCtx.fillRect(-5,-27,10,2); }
    }

    // Headwear
    _drawHeadwear(pCtx, app.headwear, app.headwearColor, false);

    // Glasses
    _drawGlasses(pCtx, app.glasses, app.glassesColor, 0);

    // Held item
    _drawHeldItem(pCtx, app.heldItem, false);

    // Emoji
    pCtx.font = '8px sans-serif';
    pCtx.textAlign = 'center';
    pCtx.fillText(es.emoji || '😊', 0, -12);

    pCtx.restore();
}

function _acpSave() {
    var es = _agentPanelEditState;
    if (!es) return;

    // Ensure agents array in officeConfig
    if (!officeConfig.agents) officeConfig.agents = [];

    // Find or create config entry
    var idx = officeConfig.agents.findIndex(function(a){ return _agentConfigMatches(a, es); });
    if (idx >= 0) {
        officeConfig.agents[idx].appearance = es.appearance;
        officeConfig.agents[idx].name = es.name;
        officeConfig.agents[idx].role = es.role;
        officeConfig.agents[idx].emoji = es.emoji;
        officeConfig.agents[idx].color = es.color;
        officeConfig.agents[idx].gender = es.gender;
        officeConfig.agents[idx].branch = es.branch;
        officeConfig.agents[idx].statusKey = es.statusKey;
        officeConfig.agents[idx].providerKind = es.providerKind;
        officeConfig.agents[idx].providerAgentId = es.providerAgentId;
        officeConfig.agents[idx].profile = es.profile;
    } else {
        officeConfig.agents.push({ id: es.id, name: es.name, role: es.role, emoji: es.emoji, color: es.color, gender: es.gender, branch: es.branch, statusKey: es.statusKey, providerKind: es.providerKind, providerAgentId: es.providerAgentId, profile: es.profile, appearance: es.appearance });
    }

    // Update live agent object
    var agent = agents.find(function(a){ return a.id === es.id; });
    if (agent) {
        agent.name = es.name;
        agent.role = es.role;
        agent.emoji = es.emoji;
        agent.color = es.color;
        agent.gender = es.gender;
        agent.branch = es.branch;
    }

    saveOfficeConfig();
    _acpRefreshList();

    // Show saved toast
    _acpShowToast('✅ Saved!');
}

function _acpAutoSave() {
    var es = _agentPanelEditState;
    if (!es) return;

    // Push undo state before applying
    var agent = agents.find(function(a){ return a.id === es.id; });
    if (agent) {
        _acpUndoStack.push(JSON.stringify({ name: agent.name, role: agent.role, emoji: agent.emoji, color: agent.color, gender: agent.gender, branch: agent.branch, statusKey: agent.statusKey, appearance: JSON.parse(JSON.stringify(agent.appearance || {})) }));
        if (_acpUndoStack.length > 20) _acpUndoStack.shift();
    }

    if (!officeConfig.agents) officeConfig.agents = [];
    var idx = officeConfig.agents.findIndex(function(a){ return _agentConfigMatches(a, es); });
    var agentData = { id: es.id, name: es.name, role: es.role, emoji: es.emoji, color: es.color, gender: es.gender, branch: es.branch, statusKey: es.statusKey, providerKind: es.providerKind, providerAgentId: es.providerAgentId, profile: es.profile, appearance: es.appearance };
    if (idx >= 0) {
        Object.assign(officeConfig.agents[idx], agentData);
    } else {
        officeConfig.agents.push(agentData);
    }
    if (agent) {
        agent.name = es.name;
        agent.role = es.role;
        agent.emoji = es.emoji;
        agent.color = es.color;
        agent.gender = es.gender;
        agent.branch = es.branch;
        agent.appearance = JSON.parse(JSON.stringify(es.appearance));
        if (es.statusKey) agent.statusKey = es.statusKey;
    }

    _acpUnsaved = true;
    // Update Save/Undo button states
    var saveBtn = document.getElementById('acp-save-btn');
    var undoBtn = document.getElementById('acp-undo-btn');
    if (saveBtn) { saveBtn.style.opacity = '1'; saveBtn.disabled = false; }
    if (undoBtn) { undoBtn.style.opacity = '1'; undoBtn.disabled = false; }

    _acpUpdatePreview();
    // Don't auto-save to localStorage — user must click Save
}

function _acpShowToast(msg) {
    var toast = document.createElement('div');
    toast.textContent = msg;
    toast.style.cssText = 'position:fixed;bottom:80px;left:50%;transform:translateX(-50%);background:#1e3a1e;border:1px solid #4caf50;color:#4caf50;padding:8px 20px;border-radius:4px;font-size:12px;z-index:9999;pointer-events:none';
    document.body.appendChild(toast);
    setTimeout(function(){ if (toast.parentNode) toast.parentNode.removeChild(toast); }, 4000);
}

function _acpLocalizeCreateAgentError(errorText) {
    var msg = String(errorText || '').trim();
    if (/["']?main["']?\s+is\s+reserved/i.test(msg)) return _tr('agent_error_main_reserved');
    return msg || _tr('unknown');
}

function _acpShowMessageDialog(title, message, kind) {
    var existing = document.getElementById('agent-message-dialog');
    if (existing) existing.remove();
    var modal = document.createElement('div');
    modal.id = 'agent-message-dialog';
    modal.className = 'modal';
    modal.innerHTML =
        '<div class="modal-content agent-message-modal agent-message-' + escAttr(kind || 'info') + '">' +
            '<div class="modal-header">' +
                '<span class="modal-emoji">' + (kind === 'error' ? '⚠️' : 'ℹ️') + '</span>' +
                '<h2>' + escHtml(title || _tr('error')) + '</h2>' +
                '<span class="close-btn" data-agent-message-close>&times;</span>' +
            '</div>' +
            '<div class="agent-message-body">' + escHtml(message || '') + '</div>' +
            '<div class="modal-controls">' +
                '<button type="button" class="mtg-btn mtg-btn-end" data-agent-message-close>' + escHtml(_tr('confirm')) + '</button>' +
            '</div>' +
        '</div>';
    modal.addEventListener('click', function(e) {
        if (e.target === modal || e.target.closest('[data-agent-message-close]')) modal.remove();
    });
    modal.addEventListener('keydown', function(e) {
        if (e.key === 'Escape' || e.key === 'Enter') modal.remove();
    });
    document.body.appendChild(modal);
    var close = modal.querySelector('[data-agent-message-close]');
    if (close) close.focus();
}

function _isCustomAgent(agentId) {
    // Built-in agents come from AGENT_DEFS
    return !AGENT_DEFS.find(function(d){ return d.id === agentId; });
}

function _acpPlatformDefaults(platform) {
    var id = platform && platform.id || 'openclaw';
    if (id === 'hermes') return { role: 'Hermes Agent', emoji: '⚕️' };
    if (id === 'codex') return { role: 'Codex Collaborator', emoji: '⚡' };
    if (id === 'claude-code') return { role: 'Claude Code Agent', emoji: '🧠' };
    return { role: _tr('ai_assistant'), emoji: '🤖' };
}

function _acpSlugAgentName(name) {
    var slug = String(name || '').trim().toLowerCase()
        .replace(/[^a-z0-9_.-]+/g, '-')
        .replace(/^[-._]+|[-._]+$/g, '')
        .slice(0, 64);
    return slug || 'agent';
}

function _acpShowCreateAgentDialog(platformsSource) {
    return new Promise(function(resolve) {
        var existing = document.getElementById('agent-create-dialog');
        if (existing) existing.remove();

        var platforms = [];
        var selectedPlatform = null;
        var defaults = _acpPlatformDefaults(null);
        var modal = document.createElement('div');
        modal.id = 'agent-create-dialog';
        modal.className = 'modal';
        modal.innerHTML =
            '<div class="modal-content agent-create-modal">' +
                '<div class="modal-header">' +
                    '<span class="modal-emoji">➕</span>' +
                    '<h2>' + escHtml(_tr('agent_create_title')) + '</h2>' +
                    '<span class="close-btn" data-acp-create-cancel>&times;</span>' +
                '</div>' +
                '<div class="agent-create-form">' +
                    '<div class="agent-create-label">' + escHtml(_tr('agent_platform_prompt')) + '</div>' +
                    '<div class="agent-platform-grid agent-platform-grid-loading">' + escHtml(_tr('loading')) + '</div>' +
                    '<label class="agent-create-field"><span>' + escHtml(_tr('agent_name_prompt')) + '</span><input id="agent-create-name" value="' + escAttr(_tr('new_agent_default')) + '"></label>' +
                    '<label class="agent-create-field"><span>' + escHtml(_tr('agent_role_prompt')) + '</span><input id="agent-create-role" value="' + escAttr(defaults.role) + '"></label>' +
                    '<label class="agent-create-field agent-create-emoji-field"><span>' + escHtml(_tr('emoji_prompt')) + '</span><input id="agent-create-emoji" value="' + escAttr(defaults.emoji) + '" maxlength="8"></label>' +
                '</div>' +
                '<div class="modal-controls">' +
                    '<button type="button" class="mtg-btn" data-acp-create-cancel>' + escHtml(_tr('cancel')) + '</button>' +
                    '<button type="button" class="mtg-btn mtg-btn-end" data-acp-create-submit disabled>' + escHtml(_tr('agent_create_submit')) + '</button>' +
                '</div>' +
            '</div>';

        function close(value) {
            modal.remove();
            resolve(value || null);
        }
        function renderPlatforms(nextPlatforms, errorText) {
            platforms = (nextPlatforms || []).filter(function(p){ return p && p.available && p.create; });
            var grid = modal.querySelector('.agent-platform-grid');
            var submit = modal.querySelector('[data-acp-create-submit]');
            if (!grid) return;
            grid.classList.remove('agent-platform-grid-loading');
            if (!platforms.length) {
                grid.classList.add('agent-platform-grid-loading');
                grid.textContent = errorText || _tr('no_agent_platforms');
                if (submit) submit.disabled = true;
                return;
            }
            selectedPlatform = platforms[0];
            grid.innerHTML = platforms.map(function(p, i) {
                return '<button type="button" class="agent-platform-card' + (i === 0 ? ' selected' : '') + '" data-platform-id="' + escAttr(p.id) + '">' +
                    '<span class="agent-platform-name">' + escHtml(p.label || p.id) + '</span>' +
                    '<span class="agent-platform-id">' + escHtml(p.id) + '</span>' +
                '</button>';
            }).join('');
            if (submit) submit.disabled = false;
            syncDefaults(selectedPlatform);
        }
        function syncDefaults(platform) {
            var d = _acpPlatformDefaults(platform);
            var role = document.getElementById('agent-create-role');
            var emoji = document.getElementById('agent-create-emoji');
            if (role && (!role.value.trim() || role.dataset.autofill === '1')) {
                role.value = d.role;
                role.dataset.autofill = '1';
            }
            if (emoji && (!emoji.value.trim() || emoji.dataset.autofill === '1')) {
                emoji.value = d.emoji;
                emoji.dataset.autofill = '1';
            }
        }

        modal.addEventListener('input', function(e) {
            if (e.target && (e.target.id === 'agent-create-role' || e.target.id === 'agent-create-emoji')) {
                e.target.dataset.autofill = '0';
            }
        });
        modal.addEventListener('click', function(e) {
            if (e.target === modal || e.target.closest('[data-acp-create-cancel]')) {
                close(null);
                return;
            }
            var platformBtn = e.target.closest('.agent-platform-card');
            if (platformBtn) {
                selectedPlatform = platforms.find(function(p) { return p.id === platformBtn.dataset.platformId; }) || selectedPlatform;
                modal.querySelectorAll('.agent-platform-card').forEach(function(btn) { btn.classList.toggle('selected', btn === platformBtn); });
                syncDefaults(selectedPlatform);
                return;
            }
            if (e.target.closest('[data-acp-create-submit]')) {
                if (!selectedPlatform) return;
                var name = (document.getElementById('agent-create-name').value || '').trim();
                var role = (document.getElementById('agent-create-role').value || '').trim();
                var emoji = (document.getElementById('agent-create-emoji').value || '').trim();
                var d = _acpPlatformDefaults(selectedPlatform);
                if (!name) {
                    var nameInput = document.getElementById('agent-create-name');
                    if (nameInput) nameInput.focus();
                    return;
                }
                close({ platform: selectedPlatform, name: name, role: role || d.role, emoji: emoji || d.emoji });
            }
        });
        modal.addEventListener('keydown', function(e) {
            if (e.key === 'Escape') close(null);
            if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') {
                var submit = modal.querySelector('[data-acp-create-submit]');
                if (submit) submit.click();
            }
        });
        document.body.appendChild(modal);
        var nameInput = document.getElementById('agent-create-name');
        var roleInput = document.getElementById('agent-create-role');
        var emojiInput = document.getElementById('agent-create-emoji');
        if (roleInput) roleInput.dataset.autofill = '1';
        if (emojiInput) emojiInput.dataset.autofill = '1';
        if (nameInput) {
            nameInput.focus();
            nameInput.select();
        }
        Promise.resolve(platformsSource).then(function(platformData) {
            var loaded = Array.isArray(platformData) ? platformData : (platformData && platformData.platforms) || [];
            renderPlatforms(loaded);
        }).catch(function() {
            renderPlatforms([{ id: 'openclaw', label: 'OpenClaw', available: true, create: true }]);
        });
    });
}

function _acpCreateNewAgent() {
    var platformsPromise = fetch('/api/agent-platforms').then(function(res) {
        return res.json();
    }).catch(function() {
        return { platforms: [{ id: 'openclaw', label: 'OpenClaw', available: true, create: true }] };
    });
    _acpShowCreateAgentDialog(platformsPromise).then(function(selection) {
        if (!selection) return null;
        var selectedPlatform = selection.platform;
        var agentName = selection.name;
        var agentRole = selection.role;
        var agentEmoji = selection.emoji;
        var agentProfile = _acpSlugAgentName(agentName);

        _acpShowToast(_tr('creating_agent_platform', { platform: selectedPlatform.label }));
        return fetch('/api/agent/create', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ platform: selectedPlatform.id, id: agentProfile, profile: agentProfile, name: agentName, role: agentRole, emoji: agentEmoji })
        }).then(function(res) { return res.json(); }).then(function(data) {
            return { data: data, platform: selectedPlatform, name: agentName, role: agentRole, emoji: agentEmoji, prompt: agentPrompt };
        });
    }).then(function(result) {
        if (!result) return;
        var data = result.data;
        if (data.error) {
            _acpShowMessageDialog(_tr('failed_create_agent'), _acpLocalizeCreateAgentError(data.error), 'error');
            return;
        }
        var newId = data.agentId;
        var newAgent = {
            id: newId,
            name: result.name,
            role: result.role,
            emoji: result.emoji,
            gender: 'M',
            color: '#607d8b',
            statusKey: newId,
            providerKind: data.providerKind || result.platform.id || 'openclaw',
            providerType: data.providerType || result.platform.providerType || 'runtime',
            providerAgentId: data.providerAgentId || data.profile || newId,
            profile: data.profile || data.providerAgentId || '',
            branch: 'UNASSIGNED',
            deskType: 'center',
        };

        var appearance = getDefaultAppearance(newId, 'M');
        if (!officeConfig.agents) officeConfig.agents = [];
        var savedAgent = Object.assign({}, newAgent, { appearance: appearance });
        var existingIdx = officeConfig.agents.findIndex(function(a) {
            return _agentConfigMatches(a, savedAgent);
        });
        if (existingIdx >= 0) officeConfig.agents[existingIdx] = Object.assign({}, officeConfig.agents[existingIdx], savedAgent);
        else officeConfig.agents.push(savedAgent);

        var startX = 500 + (agents.length * 20) % 100;
        var startY = 350;
        var agentInst = new Agent(newAgent);
        agentInst.desk = { x: startX, y: startY };
        agentInst.x = startX;
        agentInst.y = startY;
        agentInst.targetX = startX;
        agentInst.targetY = startY;
        agents.push(agentInst);
        agentMap[newId] = agentInst;

        saveOfficeConfig();
        _acpRefreshList();
        _acpSelectAgent(newId);
        _acpShowToast('✅ ' + _tr('agent_created_platform', { name: result.name, platform: result.platform.label }));
    }).catch(function(e) {
        _acpShowMessageDialog(_tr('error_create_agent'), _acpLocalizeCreateAgentError(e.message), 'error');
    });
}

function _acpDeleteAgent(agentId) {
    var agentName = agentId;
    var agentCfg = (officeConfig.agents || []).find(function(a) { return a.id === agentId; });
    if (agentCfg) agentName = agentCfg.name || agentId;

    var providerKind = (agentCfg && agentCfg.providerKind) || (agentId.indexOf('hermes-') === 0 ? 'Hermes' : (agentId.indexOf('codex-') === 0 ? 'Codex' : 'OpenClaw'));
    if (!confirm(_tr('delete_agent_confirm', { name: agentName, provider: providerKind }))) return;

    // Call server to delete from the backing agent platform.
    fetch('/api/agent/delete', {
        method: 'DELETE',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ id: agentId })
    }).then(function(res) { return res.json(); }).then(function(data) {
        if (data.error) {
        alert(_tr('failed_delete_agent') + ': ' + data.error);
            return;
        }

        // Remove from local state
        var idx = agents.findIndex(function(a){ return a.id === agentId; });
        if (idx >= 0) agents.splice(idx, 1);
        delete agentMap[agentId];

        if (officeConfig.agents) {
            var cidx = officeConfig.agents.findIndex(function(a){ return a.id === agentId; });
            if (cidx >= 0) officeConfig.agents.splice(cidx, 1);
        }

        saveOfficeConfig();
        _acpRefreshList();

        if (agents.length > 0) {
            _acpSelectAgent(agents[0].id);
        } else {
            var col = document.getElementById('acp-editor-col');
        if (col) col.innerHTML = '<div style="padding:20px;color:#666;font-size:11px">' + escHtml(_tr('no_agents_create')) + '</div>';
        }

        _acpShowToast('🗑️ ' + _tr('agent_deleted', { name: agentName }));
    }).catch(function(e) {
        alert(_tr('error_delete_agent') + ': ' + e.message);
    });
}

Object.assign(window, {
    toggleAgentPanel: toggleAgentPanel,
    _acpRefreshList: _acpRefreshList,
    _acpSelectAgent: _acpSelectAgent,
    _acpShowToast: _acpShowToast
});
