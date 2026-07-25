// Reusable skills library modal and editor.
// ============================================================
// SKILLS LIBRARY
// ============================================================

var _sklSkills = [];
var _sklEditingName = null; // null = new, string = editing existing

function openSkillsLibrary() {
    document.getElementById('skillsLibraryModal').classList.remove('hidden');
    refreshSkillsList();
}

function closeSkillsLibrary() {
    document.getElementById('skillsLibraryModal').classList.add('hidden');
}

async function refreshSkillsList() {
    try {
        var res = await fetch('/api/skills-library');
        var data = await res.json();
        _sklSkills = Array.isArray(data) ? data : (data.skills || []);
    } catch (e) {
        _sklSkills = [];
    }
    renderSkillCards();
}

function renderSkillCards() {
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

    // Fetch agent list
    try {
        var res = await fetch('/agents-list');
        var data = await res.json();
        var agentList = Array.isArray(data) ? data : (data.agents || []);

        var options = agentList.map(function(a) {
            var id = a.id || a.agentId || a.name;
            var name = a.name || id;
            return '<option value="' + _sklEsc(id) + '">' + _sklEsc(name) + '</option>';
        }).join('');

        dropdown.innerHTML =
            '<select id="skl-agent-select-' + skillName + '">' + options + '</select>' +
            '<button onclick="applySkillToAgent(\'' + _sklEsc(skillName) + '\')">' + _sklEsc(_tr('apply')) + '</button>';
        dropdown.style.display = 'flex';
    } catch (e) {
        _acpShowToast('❌ ' + _tr('failed_to_load'));
    }
}

async function applySkillToAgent(skillName) {
    var select = document.getElementById('skl-agent-select-' + skillName);
    if (!select) return;
    var agentId = select.value;
    if (!agentId) return;

    try {
        var res = await fetch('/api/skills-library/apply', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ skill: skillName, agentId: agentId })
        });
        var data = await res.json();
        if (res.ok) {
            if (data.warning) {
                _acpShowToast('⚠️ ' + data.warning);
            } else {
                _acpShowToast('✅ ' + _tr('skill_applied', { skill: skillName, agent: agentId }));
            }
        } else {
            _acpShowToast('❌ ' + _tr('apply_failed') + ': ' + (data.error || _tr('unknown')));
        }
    } catch (e) {
        _acpShowToast('❌ ' + _tr('apply_failed') + ': ' + e.message);
    }

    // Hide dropdown after apply
    var dropdown = document.getElementById('skl-apply-' + skillName);
    if (dropdown) dropdown.style.display = 'none';
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
            _acpShowToast('❌ ' + _tr('failed_load_skill') + ': ' + e.message);
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
        _acpShowToast('❌ ' + _tr('skill_name_required'));
        return;
    }

    try {
        var res = await fetch('/api/skills-library', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ name: name, content: content })
        });
        var data = await res.json();
        if (res.ok) {
            _acpShowToast('✅ ' + _tr('skill_saved', { name: name }));
            closeSkillEditor();
            refreshSkillsList();
        } else {
            _acpShowToast('❌ ' + _tr('save_failed') + ': ' + (data.error || _tr('unknown')));
        }
    } catch (e) {
        _acpShowToast('❌ ' + _tr('save_failed') + ': ' + e.message);
    }
}

async function deleteLibrarySkill(skillName) {
    if (!confirm(_tr('delete_library_skill_confirm', { name: skillName }))) return;

    try {
        var res = await fetch('/api/skills-library/' + encodeURIComponent(skillName), { method: 'DELETE' });
        if (res.ok) {
            _acpShowToast('🗑️ ' + _tr('skill_deleted', { name: skillName }));
            refreshSkillsList();
        } else {
            var data = await res.json().catch(function() { return {}; });
            _acpShowToast('❌ ' + _tr('failed_delete') + ': ' + (data.error || _tr('unknown')));
        }
    } catch (e) {
        _acpShowToast('❌ ' + _tr('failed_delete') + ': ' + e.message);
    }
}

async function handleSkillUpload(input) {
    if (!input.files || !input.files.length) return;
    var file = input.files[0];
    var name = file.name.replace(/\.md$/i, '').replace(/[^a-zA-Z0-9_-]/g, '-');

    try {
        var text = await file.text();
        var res = await fetch('/api/skills-library', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ name: name, content: text })
        });
        if (res.ok) {
            _acpShowToast('✅ ' + _tr('uploaded', { name: name }));
            refreshSkillsList();
        } else {
            var data = await res.json().catch(function() { return {}; });
            _acpShowToast('❌ ' + _tr('upload_failed') + ': ' + (data.error || _tr('unknown')));
        }
    } catch (e) {
        _acpShowToast('❌ ' + _tr('upload_failed') + ': ' + e.message);
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
    openSkillEditor,
    closeSkillEditor,
    saveSkill,
    deleteLibrarySkill,
    handleSkillUpload
});
