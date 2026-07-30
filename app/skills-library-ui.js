// Reusable skills library modal and editor.
// ============================================================
// SKILLS LIBRARY
// ============================================================

var _sklSkills = [];
var _sklLibraryData = { skills: [], categories: [] };
var _sklEditingName = null; // null = new, string = editing existing

function _sklToast(message) {
    var toast = window._acpShowToast || window._showOfficeToast;
    if (typeof toast === 'function') {
        toast(message);
    }
}

function _sklMutationFetch(input, init) {
    if (window.i18n && typeof window.i18n.managementFetch === 'function') {
        return window.i18n.managementFetch(input, init || {});
    }
    return fetch(input, init || {});
}

function openSkillsLibrary() {
    document.getElementById('skillsLibraryModal').classList.remove('hidden');
    refreshSkillsList();
}

function closeSkillsLibrary() {
    document.getElementById('skillsLibraryModal').classList.add('hidden');
    if (window.SkillLibraryOrganizationUI) {
        window.SkillLibraryOrganizationUI.stopPolling();
    }
}

async function refreshSkillsList() {
    try {
        var res = await fetch('/api/skills-library');
        var data = await res.json();
        _sklSkills = Array.isArray(data) ? data : (data.skills || []);
        _sklLibraryData = Array.isArray(data) ? { skills: data, categories: [] } : data;
    } catch (e) {
        _sklSkills = [];
        _sklLibraryData = { skills: [], categories: [] };
    }
    renderSkillCards();
}

function renderSkillCards() {
    if (window.SkillLibraryOrganizationUI) {
        window.SkillLibraryOrganizationUI.update(_sklLibraryData);
        return;
    }
    var container = document.getElementById('skl-cards');
    if (!container) return;

    if (!_sklSkills.length) {
        container.innerHTML = '<div style="color:#666;font-size:11px;padding:20px;text-align:center;">' + _sklEsc(_tr('no_skills_library')) + '</div>';
        return;
    }

    var sorted = _sklSkills.slice().sort(function(a, b) { return (a.name || '').localeCompare(b.name || ''); });

    container.innerHTML = sorted.map(function(skill) {
        var safeName = _sklEsc(skill.name);
        return '<div class="skl-card" id="skl-card-' + safeName + '">' +
            '<div class="skl-card-top">' +
                '<div class="skl-card-name">' + safeName + '</div>' +
                '<div class="skl-card-actions">' +
                    '<button onclick="toggleSkillApply(\'' + safeName + '\')" title="' + _sklEsc(_tr('apply_to_agent')) + '">📋</button>' +
                    '<button onclick="openSkillEditor(\'' + safeName + '\')" title="' + _sklEsc(_tr('edit')) + '">✏️</button>' +
                    '<button onclick="deleteLibrarySkill(\'' + safeName + '\')" title="' + _sklEsc(_tr('delete')) + '">🗑️</button>' +
                '</div>' +
            '</div>' +
            '<div class="skl-apply-dropdown" id="skl-apply-' + safeName + '" style="display:none"></div>' +
        '</div>';
    }).join('');
}

function _sklEsc(str) {
    if (!str) return '';
    return str.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;').replace(/'/g, '&#039;');
}

async function toggleSkillApply(skillName) {
    var dropdown = document.getElementById('skl-apply-' + skillName);
    if (!dropdown) return;

    if (dropdown.style.display !== 'none') {
        dropdown.style.display = 'none';
        return;
    }

    try {
        var res = await fetch('/api/agents', { cache: 'no-store' });
        var data = await res.json();
        var agentList = Array.isArray(data) ? data : (data.agents || []);
        var translate = function(key, fallback) {
            var value = _tr(key);
            return !value || value === key ? fallback : value;
        };
        dropdown.innerHTML = AgentBranchSelector.render({
            agents: agentList,
            branches: typeof getBranchList === 'function' ? getBranchList() : [],
            selectedIds: [],
            branchTogglePlacement: 'group-title',
            branchInputClass: 'skl-branch-toggle',
            agentInputClass: 'skl-agent-toggle',
            scopeAttributes: ' data-skill-name="' + _sklEsc(skillName) + '"',
            quickSelectLabel: translate('meeting_branch_quick_select', '按部门快捷选择'),
            hintLabel: translate('meeting_branch_quick_select_hint', '先选择部门，再手动调整单个 Agent。'),
            emptyLabel: translate('skill_no_assignable_agents', '暂无可应用的 Agent'),
            escape: _sklEsc,
            translate: translate
        }) +
            '<div class="skl-apply-actions"><button type="button" data-skl-apply-selected data-skill-name="' + _sklEsc(skillName) + '">' +
                _sklEsc(translate('skill_apply_selected_agents', '应用到所选 Agent')) +
            '</button></div>';
        dropdown.style.display = 'flex';
        var applyButton = dropdown.querySelector('[data-skl-apply-selected]');
        if (applyButton && dropdown.querySelector('.branch-agent-selector-empty')) applyButton.disabled = true;
        AgentBranchSelector.syncBranches(dropdown, '.skl-branch-toggle', '.skl-agent-toggle');
    } catch (e) {
        _sklToast('❌ ' + _tr('failed_to_load'));
    }
}

async function _applySkillToAgentId(skillName, agentId) {
    if (!agentId) return;
    var res = await _sklMutationFetch('/api/skills-library/apply', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ skill: skillName, agentId: agentId })
    });
    var data = await res.json().catch(function() { return {}; });
    if (!res.ok) throw new Error(data.error || _tr('unknown'));
    return data;
}

async function applySkillToSelectedAgents(skillName, button) {
    var dropdown = document.getElementById('skl-apply-' + skillName);
    if (!dropdown) return;
    var agentIds = Array.prototype.slice.call(dropdown.querySelectorAll('.skl-agent-toggle:checked')).map(function(input) {
        return input.value;
    }).filter(Boolean);
    if (!agentIds.length) {
        _sklToast('⚠️ ' + (_tr('skill_select_agent_first') || '请先选择 Agent'));
        return;
    }
    if (button) button.disabled = true;
    var succeeded = [];
    var failed = [];
    var warnings = [];
    for (var i = 0; i < agentIds.length; i += 1) {
        try {
            var result = await _applySkillToAgentId(skillName, agentIds[i]);
            succeeded.push(agentIds[i]);
            if (result && result.warning) warnings.push(agentIds[i] + ': ' + result.warning);
        } catch (e) {
            failed.push(agentIds[i] + ': ' + e.message);
        }
    }
    if (button) button.disabled = false;
    if (failed.length) {
        refreshSkillsList();
        _sklToast('⚠️ ' + _tr('skill_apply_batch_partial', {
            success: succeeded.length,
            failed: failed.length
        }) + ' · ' + failed.join('; '));
        return;
    }
    _sklToast('✅ ' + _tr('skill_apply_batch_success', {
        skill: skillName,
        count: succeeded.length
    }) + (warnings.length ? ' · ⚠️ ' + warnings.join('; ') : ''));
    dropdown.style.display = 'none';
    refreshSkillsList();
}

async function applySkillToAgent(skillName) {
    return applySkillToSelectedAgents(skillName);
}

async function openSkillEditor(skillName) {
    _sklEditingName = skillName;
    var titleEl = document.getElementById('skl-editor-title');
    var nameInput = document.getElementById('skl-editor-name');
    var contentArea = document.getElementById('skl-editor-content');

    if (skillName) {
        // Edit existing: fetch content
        titleEl.textContent = _tr('edit_skill');
        nameInput.value = skillName;
        nameInput.disabled = true;
        try {
            var res = await fetch('/api/skills-library/' + encodeURIComponent(skillName));
            var data = await res.json();
            contentArea.value = data.content || '';
        } catch (e) {
            contentArea.value = '';
            _sklToast('❌ ' + _tr('failed_load_skill') + ': ' + e.message);
        }
    } else {
        // New skill
        titleEl.textContent = _tr('add_skill_title');
        nameInput.value = '';
        nameInput.disabled = false;
        contentArea.value = '---\nname: \ndescription: \n---\n\n# Skill Title\n\nInstructions here...\n';
    }

    document.getElementById('skillEditorModal').classList.remove('hidden');
}

function closeSkillEditor() {
    document.getElementById('skillEditorModal').classList.add('hidden');
    _sklEditingName = null;
}

async function saveSkill() {
    var nameInput = document.getElementById('skl-editor-name');
    var contentArea = document.getElementById('skl-editor-content');
    var name = (nameInput.value || '').trim();
    var content = contentArea.value || '';

    if (!name) {
        _sklToast('❌ ' + _tr('skill_name_required'));
        return;
    }

    try {
        var res = await _sklMutationFetch('/api/skills-library', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ name: name, content: content })
        });
        var data = await res.json();
        if (res.ok) {
            _sklToast('✅ ' + _tr('skill_saved', { name: name }));
            closeSkillEditor();
            refreshSkillsList();
        } else {
            _sklToast('❌ ' + _tr('save_failed') + ': ' + (data.error || _tr('unknown')));
        }
    } catch (e) {
        _sklToast('❌ ' + _tr('save_failed') + ': ' + e.message);
    }
}

async function deleteLibrarySkill(skillName) {
    if (!confirm(_tr('delete_library_skill_confirm', { name: skillName }))) return;

    try {
        var res = await _sklMutationFetch('/api/skills-library/' + encodeURIComponent(skillName), { method: 'DELETE' });
        if (res.ok) {
            _sklToast('🗑️ ' + _tr('skill_deleted', { name: skillName }));
            refreshSkillsList();
        } else {
            var data = await res.json().catch(function() { return {}; });
            _sklToast('❌ ' + _tr('failed_delete') + ': ' + (data.error || _tr('unknown')));
        }
    } catch (e) {
        _sklToast('❌ ' + _tr('failed_delete') + ': ' + e.message);
    }
}

async function handleSkillUpload(input) {
    if (!input.files || !input.files.length) return;
    var file = input.files[0];
    var name = file.name.replace(/\.md$/i, '').replace(/[^a-zA-Z0-9_-]/g, '-');

    try {
        var text = await file.text();
        var res = await _sklMutationFetch('/api/skills-library', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ name: name, content: text })
        });
        if (res.ok) {
            _sklToast('✅ ' + _tr('uploaded', { name: name }));
            refreshSkillsList();
        } else {
            var data = await res.json().catch(function() { return {}; });
            _sklToast('❌ ' + _tr('upload_failed') + ': ' + (data.error || _tr('unknown')));
        }
    } catch (e) {
        _sklToast('❌ ' + _tr('upload_failed') + ': ' + e.message);
    }

    // Reset input so same file can be re-uploaded
    input.value = '';
}

// Close skills modals on backdrop click
document.getElementById('skillsLibraryModal').addEventListener('click', function(e) {
    if (e.target === this) closeSkillsLibrary();
});
document.getElementById('skillEditorModal').addEventListener('click', function(e) {
    if (e.target === this) closeSkillEditor();
});

document.addEventListener('change', function(e) {
    var branch = e.target.closest && e.target.closest('.skl-branch-toggle');
    if (branch) {
        var dropdown = branch.closest('.skl-apply-dropdown');
        if (!dropdown) return;
        AgentBranchSelector.applyBranch(dropdown, branch, '.skl-agent-toggle');
        AgentBranchSelector.syncBranches(dropdown, '.skl-branch-toggle', '.skl-agent-toggle');
        return;
    }
    var agent = e.target.closest && e.target.closest('.skl-agent-toggle');
    if (agent) {
        var root = agent.closest('.skl-apply-dropdown');
        if (root) AgentBranchSelector.syncBranches(root, '.skl-branch-toggle', '.skl-agent-toggle');
    }
});

document.addEventListener('click', function(e) {
    var button = e.target.closest && e.target.closest('[data-skl-apply-selected]');
    if (!button) return;
    applySkillToSelectedAgents(button.getAttribute('data-skill-name') || '', button);
});

// Close skills modals on Escape (extend existing keydown)
var _origKeydownHandler = document.onkeydown;
document.addEventListener('keydown', function(e) {
    if (e.key === 'Escape') {
        if (!document.getElementById('skillEditorModal').classList.contains('hidden')) {
            closeSkillEditor();
            e.stopPropagation();
        } else if (!document.getElementById('skillsLibraryModal').classList.contains('hidden')) {
            closeSkillsLibrary();
            e.stopPropagation();
        }
    }
});

Object.assign(window, {
    openSkillsLibrary,
    closeSkillsLibrary,
    refreshSkillsList,
    toggleSkillApply,
    applySkillToAgent,
    applySkillToSelectedAgents,
    openSkillEditor,
    closeSkillEditor,
    saveSkill,
    deleteLibrarySkill,
    handleSkillUpload
});
