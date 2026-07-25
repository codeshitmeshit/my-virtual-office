// Canvas click interaction and agent detail modal.
// --- INTERACTION ---
// Track drag distance to distinguish clicks from pans
let _clickStartX = 0, _clickStartY = 0;
canvas.addEventListener('mouseup', function(e) {
    const dist = Math.abs(e.clientX - _clickStartX) + Math.abs(e.clientY - _clickStartY);
    if (dist > 5) return; // was a drag, not a click
    handleCanvasClick(e.clientX, e.clientY);
});

let _touchStartX2 = 0, _touchStartY2 = 0;
canvas.addEventListener('touchend', function(e) {
    if (e.changedTouches.length === 1) {
        const t = e.changedTouches[0];
        const dist = Math.abs(t.clientX - _touchStartX2) + Math.abs(t.clientY - _touchStartY2);
        if (dist > 10) return; // was a drag
        handleCanvasClick(t.clientX, t.clientY);
    }
});

function handleCanvasClick(clientX, clientY) {
    if (editMode) return; // edit mode handles clicks via click event
    const world = screenToWorld(clientX, clientY);
    const cx = world.x;
    const cy = world.y;
    // Check chat bubble scroll arrows
    for (var si = 0; si < renderedChatBubbles.length; si++) {
        var sb = renderedChatBubbles[si];
        var sr = sb.fullRect;
        if (cx >= sr.x && cx <= sr.x + sr.w && cy >= sr.y && cy <= sr.y + sr.h) {
            if (cy < sr.y + 15) continue;
            if (sb.canScrollUp && cy < sr.y + 28) {
                chatScrollOffset[sb.agentKey] = (chatScrollOffset[sb.agentKey] || 0) + 3;
                return;
            }
            if (sb.canScrollDown && cy > sr.y + sr.h - 18) {
                chatScrollOffset[sb.agentKey] = Math.max(0, (chatScrollOffset[sb.agentKey] || 0) - 3);
                return;
            }
        }
    }
    // Chat bubble close/minimize
    if (handleChatBubbleClick(cx, cy)) return;
    // Thought/speech bubble close/minimize
    if (handleBubbleClick(cx, cy)) return;
    var furnitureHit = _findFurnitureAt(cx, cy);
    if (furnitureHit && _handleFunctionalFurnitureClick(furnitureHit, clientX, clientY)) return;
    // Check gear icon click to open agent modal
    for (const agent of agents) {
        const g = agent.gearRect;
        if (g && cx >= g.x && cx <= g.x + g.w && cy >= g.y && cy <= g.y + g.h) {
            openModal(agent);
            return;
        }
    }
}

function _providerKindDisplay(providerKind) {
    var kind = String(providerKind || 'openclaw').toLowerCase();
    if (kind === 'hermes') return 'Hermes';
    if (kind === 'codex') return 'Codex CLI';
    if (kind === 'claude-code') return 'Claude Code';
    return 'OpenClaw';
}

function _providerAgentLabel(agent) {
    var provider = _providerKindDisplay(agent && agent.providerKind);
    var bits = [provider + ' Agent'];
    if (agent && agent.providerAgentId) bits.push('profile: ' + agent.providerAgentId);
    if (agent && agent.provider && agent.provider !== provider) bits.push(agent.provider);
    return bits.join(' · ');
}

function _isOpenClawAgent(agent) {
    return String((agent && agent.providerKind) || 'openclaw').toLowerCase() === 'openclaw';
}

function openModal(agent) {
    selectedAgent = agent;
    window.selectedAgent = agent;

    // Reset zoom to 1x on mobile so modal renders at normal size
    const vp = document.querySelector('meta[name="viewport"]');
    if (vp) {
        vp._origContent = vp.content;
        vp.content = 'width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no';
        // Force reflow
        setTimeout(() => { vp.content = 'width=device-width, initial-scale=1.0, user-scalable=yes'; }, 50);
    }

    // Clear notification on open
    if (agent.notify) {
        agent.notify = false;
        dismissedNotify.add(agent.statusKey);
        clearNotifyOnServer(agent.statusKey);
    }

    document.getElementById('modal-emoji').textContent = agent.emoji;
    document.getElementById('modal-name').textContent = agent.name;
    document.getElementById('modal-role').textContent = agent.role;
    document.getElementById('modal-status').textContent = agent.state.toUpperCase();
    document.getElementById('modal-task').textContent = agent.task || '—';
    document.getElementById('modal-branch').textContent = getBranchDisplayName(agent.branch);
    document.getElementById('modal-updated').textContent = timeStr();

    var providerLabel = agent.providerKind === 'hermes'
        ? ('Hermes Agent' + (agent.providerAgentId ? ' · profile: ' + agent.providerAgentId : '') + (agent.provider ? ' · ' + agent.provider : ''))
        : (agent.providerKind === 'codex'
            ? ('Codex Collaborator' + (agent.providerAgentId ? ' · profile: ' + agent.providerAgentId : '') + (agent.provider ? ' · ' + agent.provider : ''))
            : 'OpenClaw Agent');
    var roleEl = document.getElementById('modal-role');
    if (roleEl) roleEl.textContent = (agent.role || '') + (agent.role ? ' · ' : '') + providerLabel;

    var isOpenClaw = (agent.providerKind || 'openclaw') === 'openclaw';
    var modelSection = document.querySelector('#modal-model-select')?.closest('.modal-section');
    if (modelSection) modelSection.style.display = isOpenClaw ? '' : 'none';
    document.querySelectorAll('.bio-section').forEach(function(el) { el.style.display = isOpenClaw ? '' : 'none'; });

    // Task I/O
    const inputBox = document.getElementById('modal-input');
    if (agent.lastInput) {
        inputBox.innerHTML = `<div class="io-from">📥 ${escHtml(_tr('from_label'))}: <strong>${escHtml(agent.lastInput.from || _tr('unknown'))}</strong></div><div class="io-text">${escHtml(agent.lastInput.text || '—')}</div>`;
    } else {
        inputBox.innerHTML = '<div class="io-text">' + escHtml(_tr('no_recent_request')) + '</div>';
    }

    const outputBox = document.getElementById('modal-output');
    if (agent.lastOutput) {
        outputBox.innerHTML = `<div class="io-text">${escHtml(agent.lastOutput.text || '—')}</div>`;
    } else {
        outputBox.innerHTML = '<div class="io-text">' + escHtml(_tr('no_recent_response')) + '</div>';
    }

    const planBox = document.getElementById('modal-plan');
    planBox.innerHTML = '';
    agent.intentHistory.forEach(item => {
        const div = document.createElement('div'); div.className = 'log-entry'; div.textContent = item;
        planBox.appendChild(div);
    });
    planBox.scrollTop = planBox.scrollHeight;

    const logBox = document.getElementById('modal-logs');
    logBox.innerHTML = '';
    agent.logHistory.forEach(item => {
        const div = document.createElement('div'); div.className = 'log-entry'; div.textContent = item;
        logBox.appendChild(div);
    });
    logBox.scrollTop = logBox.scrollHeight;

    // Load OpenClaw-only editable files/skills for OpenClaw agents.
    if (isOpenClaw) loadAgentSkills(agent.statusKey || agent.id);

    document.getElementById('agentModal').classList.remove('hidden');
}

function escHtml(s) {
    return String(s == null ? '' : s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/\n/g,'<br>');
}
function escAttr(s) {
    return String(s == null ? '' : s).replace(/&/g,'&amp;').replace(/"/g,'&quot;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
}
function escTextarea(s) {
    return String(s == null ? '' : s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
}

Object.assign(window, {
    handleCanvasClick,
    openModal
});
