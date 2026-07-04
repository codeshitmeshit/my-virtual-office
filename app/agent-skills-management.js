// Per-agent skills management and skill workshop UI.
// ─── SKILLS MANAGEMENT ──────────────────────────────────────────────────────
var _currentSkillAgent = null; // statusKey of agent whose skills are shown
var _editingSkillName = null;
var _skillWorkshopProposals = [];
var _skillWorkshopErrors = [];
var _skillWorkshopLoaded = false;
var _skillWorkshopLoading = false;

function _showSkillLibraryVersionDialog(skillName, onUpdate) {
    var existing = document.getElementById('skill-library-version-dialog');
    if (existing) existing.remove();
    var modal = document.createElement('div');
    modal.id = 'skill-library-version-dialog';
    modal.className = 'modal';
    modal.innerHTML =
        '<div class="modal-content" style="max-width:420px;">' +
            '<div class="modal-header">' +
                '<span class="modal-emoji">📚</span>' +
                '<h2>Skill Library</h2>' +
                '<span class="close-btn" data-skl-version-cancel>&times;</span>' +
            '</div>' +
            '<div style="padding:14px;color:#ddd;font-size:13px;line-height:1.45;">' +
                '<p style="margin:0 0 12px 0;">Skill already exists in the Skill Library.</p>' +
                '<p style="margin:0;color:#aaa;">The agent version of <b>' + escHtml(skillName) + '</b> is different from the saved library version.</p>' +
            '</div>' +
            '<div class="skl-editor-actions" style="padding:0 14px 14px 14px;">' +
                '<button class="mtg-btn" data-skl-version-update>Update Skill Library Version</button>' +
                '<button class="mtg-btn" data-skl-version-cancel>Cancel</button>' +
            '</div>' +
        '</div>';
    modal.addEventListener('click', function(e) {
        if (e.target === modal || e.target.closest('[data-skl-version-cancel]')) {
            modal.remove();
            return;
        }
        if (e.target.closest('[data-skl-version-update]')) {
            modal.remove();
            if (typeof onUpdate === 'function') onUpdate();
        }
    });
    document.body.appendChild(modal);
}

async function saveAgentSkillToLibrary(agentId, skillName, onDone) {
    if (!agentId || !skillName) return;
    async function requestSave(overwrite) {
        var res = await fetch('/api/skills-library/save-from-agent', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ agentId: agentId, skill: skillName, overwrite: !!overwrite })
        });
        return await res.json();
    }
    try {
        var data = await requestSave(false);
        if (data.ok) {
            if (data.status === 'identical') {
        alert(_tr('skill_exists_library'));
            } else {
                _acpShowToast('✅ ' + (data.status === 'updated' ? 'Updated' : 'Saved') + ' "' + skillName + '" in Skill Library');
            }
            if (typeof refreshSkillsList === 'function') refreshSkillsList();
            if (typeof onDone === 'function') onDone(data);
            return;
        }
        if (data.exists && data.different) {
            _showSkillLibraryVersionDialog(skillName, async function() {
                var updated = await requestSave(true);
                if (updated.ok) {
                    _acpShowToast('✅ Updated Skill Library Version for "' + skillName + '"');
                    if (typeof refreshSkillsList === 'function') refreshSkillsList();
                    if (typeof onDone === 'function') onDone(updated);
                } else {
                    _acpShowToast('❌ ' + (updated.error || 'Could not update Skill Library version'));
                }
            });
            return;
        }
        _acpShowToast('❌ ' + (data.error || 'Could not save skill to library'));
    } catch (e) {
        _acpShowToast('❌ Could not save skill to library: ' + e.message);
    }
}

function _skillWorkshopProposalId(p) {
    return (p && (p.id || p.proposalId || p.proposal_id)) || '';
}

function _skillWorkshopTitle(p) {
    return (p && (p.skillName || p.skill || p.name || p.title || p.description || _skillWorkshopProposalId(p))) || 'Untitled proposal';
}

function _skillWorkshopStatus(p) {
    return (p && (p.status || p.state || p.reviewState || 'pending')) || 'pending';
}

function _skillWorkshopSummary(p) {
    var parts = [];
    if (p.agentName) parts.push((p.agentEmoji ? p.agentEmoji + ' ' : '') + p.agentName);
    if (p.kind || p.action || p.type) parts.push(p.kind || p.action || p.type);
    if (p.updatedAt || p.createdAt) parts.push(_formatAgentWorkspaceTime(p.updatedAt || p.createdAt));
    return parts.join(' · ');
}

async function refreshSkillWorkshopQueue() {
    if (_skillWorkshopLoading) return;
    _skillWorkshopLoading = true;
    var agentParam = '';
    try {
        var res = await fetch('/api/skills-workshop' + agentParam, { cache: 'no-store' });
        var data = await res.json();
        _skillWorkshopProposals = data.proposals || [];
        _skillWorkshopErrors = data.errors || [];
        _skillWorkshopLoaded = true;
    } catch (e) {
        _skillWorkshopProposals = [];
        _skillWorkshopErrors = [{ error: e.message || String(e) }];
        _skillWorkshopLoaded = true;
    } finally {
        _skillWorkshopLoading = false;
    }
    renderSkillWorkshopQueue();
}

function renderSkillWorkshopQueue() {
    var containers = [
        document.getElementById('skill-workshop-list'),
        document.getElementById('agent-workspace-skill-workshop-list')
    ].filter(Boolean);
    if (!containers.length) return;
    var proposals = (_skillWorkshopProposals || []).filter(function(p) {
        return _skillWorkshopStatus(p).toLowerCase() === 'pending';
    });
    var html = '';
    if (_skillWorkshopLoading && !_skillWorkshopLoaded) {
        html = '<span style="color:#666;font-size:11px;">Loading proposals...</span>';
    } else if (!proposals.length) {
        html = '<div class="skill-workshop-empty">No pending skill proposals.</div>';
    } else {
        html = proposals.map(function(p) {
            var proposalId = _skillWorkshopProposalId(p);
            var idx = _skillWorkshopProposals.indexOf(p);
            return '<div class="skill-workshop-row" data-skill-workshop-index="' + idx + '">' +
                '<div class="skill-workshop-main">' +
                    '<b>' + escHtml(_skillWorkshopTitle(p)) + '</b>' +
                    '<div class="skill-workshop-meta">' + escHtml(_skillWorkshopSummary(p)) + '</div>' +
                    '<div class="skill-workshop-status">' + escHtml(_skillWorkshopStatus(p)) + '</div>' +
                '</div>' +
                '<div class="skill-workshop-actions">' +
                    '<button type="button" data-skill-workshop-action="inspect" data-skill-workshop-index="' + idx + '">Review</button>' +
                    '<button type="button" data-skill-workshop-action="apply" data-skill-workshop-index="' + idx + '"' + (!proposalId ? ' disabled' : '') + '>Apply</button>' +
                    '<button type="button" data-skill-workshop-action="revise" data-skill-workshop-index="' + idx + '"' + (!proposalId ? ' disabled' : '') + '>Revise</button>' +
                    '<button type="button" data-skill-workshop-action="reject" data-skill-workshop-index="' + idx + '"' + (!proposalId ? ' disabled' : '') + '>Reject</button>' +
                    '<button type="button" data-skill-workshop-action="quarantine" data-skill-workshop-index="' + idx + '"' + (!proposalId ? ' disabled' : '') + '>Quarantine</button>' +
                '</div>' +
            '</div>';
        }).join('');
    }
    if (_skillWorkshopErrors.length) {
        html += '<div class="skill-workshop-error">Some agent queues could not load.</div>';
    }
    containers.forEach(function(el) { el.innerHTML = html; });
}

function _skillWorkshopProposalContent(detail) {
    if (!detail) return '';
    if (typeof detail.proposalContent === 'string') return detail.proposalContent;
    if (typeof detail.content === 'string') return detail.content;
    if (typeof detail.body === 'string') return detail.body;
    var proposal = detail.proposal || detail;
    if (typeof proposal.proposalContent === 'string') return proposal.proposalContent;
    if (typeof proposal.content === 'string') return proposal.content;
    if (typeof proposal.body === 'string') return proposal.body;
    if (Array.isArray(detail.files)) {
        var primary = detail.files.find(function(f) { return /PROPOSAL\\.md$/i.test(f.path || f.name || ''); }) || detail.files[0];
        if (primary && typeof primary.content === 'string') return primary.content;
    }
    return JSON.stringify(detail, null, 2);
}

async function inspectSkillWorkshopProposal(index, mode) {
    var proposal = _skillWorkshopProposals[index];
    if (!proposal) return;
    var proposalId = _skillWorkshopProposalId(proposal);
    if (!proposalId || !proposal.agentId) {
        _acpShowToast('❌ Proposal is missing agent or id');
        return;
    }
    try {
        var url = '/api/skills-workshop/inspect?agentId=' + encodeURIComponent(proposal.agentId) + '&proposalId=' + encodeURIComponent(proposalId);
        var detail = await fetch(url, { cache: 'no-store' }).then(function(r) { return r.json(); });
        _showSkillWorkshopReviewDialog(proposal, detail, mode === 'revise');
    } catch (e) {
        _acpShowToast('❌ Could not inspect proposal: ' + e.message);
    }
}

function _showSkillWorkshopReviewDialog(proposal, detail, startEditing) {
    var existing = document.getElementById('skill-workshop-review-dialog');
    if (existing) existing.remove();
    var proposalId = _skillWorkshopProposalId(proposal);
    var content = _skillWorkshopProposalContent(detail);
    var isEditing = !!startEditing;
    var modal = document.createElement('div');
    modal.id = 'skill-workshop-review-dialog';
    modal.className = 'modal';
    function renderDialogBody() {
        modal.innerHTML =
            '<div class="modal-content" style="max-width:760px;">' +
                '<div class="modal-header">' +
                    '<span class="modal-emoji">🧪</span>' +
                    '<h2>Skill Workshop</h2>' +
                    '<span class="close-btn" data-skill-workshop-close>&times;</span>' +
                '</div>' +
                '<div class="skill-workshop-review-head">' +
                    '<b>' + escHtml(_skillWorkshopTitle(proposal)) + '</b>' +
                    '<span>' + escHtml((proposal.agentEmoji ? proposal.agentEmoji + ' ' : '') + (proposal.agentName || proposal.agentId || '')) + '</span>' +
                    '<span>' + escHtml(_skillWorkshopStatus(proposal)) + '</span>' +
                    '<span class="skill-workshop-review-mode">' + (isEditing ? 'Editing revision' : 'Review only') + '</span>' +
                '</div>' +
                '<textarea class="skill-workshop-review-textarea' + (isEditing ? ' is-editing' : ' is-readonly') + '" spellcheck="false"' + (isEditing ? '' : ' readonly') + '>' + escTextarea(content) + '</textarea>' +
                '<div class="skl-editor-actions" style="padding:0 14px 14px 14px;">' +
                    (isEditing
                        ? '<button class="mtg-btn" data-skill-workshop-dialog-action="saveRevision">Save revision</button>' +
                            '<button class="mtg-btn" data-skill-workshop-dialog-action="cancelRevision">Cancel revision</button>'
                        : '<button class="mtg-btn" data-skill-workshop-dialog-action="apply">Apply</button>' +
                            '<button class="mtg-btn" data-skill-workshop-dialog-action="startRevision">Revise</button>' +
                            '<button class="mtg-btn" data-skill-workshop-dialog-action="reject">Reject</button>' +
                            '<button class="mtg-btn" data-skill-workshop-dialog-action="quarantine">Quarantine</button>' +
                            '<button class="mtg-btn" data-skill-workshop-close>Cancel</button>') +
                '</div>' +
            '</div>';
    }
    renderDialogBody();
    modal.addEventListener('click', function(e) {
        if (e.target === modal || e.target.closest('[data-skill-workshop-close]')) {
            modal.remove();
            return;
        }
        var actionBtn = e.target.closest('[data-skill-workshop-dialog-action]');
        if (!actionBtn) return;
        var action = actionBtn.dataset.skillWorkshopDialogAction;
        if (action === 'startRevision') {
            isEditing = true;
            renderDialogBody();
            var editor = modal.querySelector('.skill-workshop-review-textarea');
            if (editor) editor.focus();
            return;
        }
        if (action === 'cancelRevision') {
            isEditing = false;
            renderDialogBody();
            return;
        }
        if (action === 'saveRevision') {
            var revisedContent = modal.querySelector('.skill-workshop-review-textarea').value;
            runSkillWorkshopAction(proposal.agentId, proposalId, 'revise', revisedContent, function() { modal.remove(); });
            return;
        }
        runSkillWorkshopAction(proposal.agentId, proposalId, action, '', function() { modal.remove(); });
    });
    document.body.appendChild(modal);
}

async function runSkillWorkshopAction(agentId, proposalId, action, proposalContent, onDone) {
    var body = { agentId: agentId, proposalId: proposalId, action: action };
    if (action === 'reject' || action === 'quarantine') {
        var reason = prompt((action === 'reject' ? 'Reject' : 'Quarantine') + ' reason:', '');
        if (reason == null) return;
        body.reason = reason;
    }
    if (action === 'revise') {
        body.proposalContent = proposalContent || '';
        if (!body.proposalContent.trim()) {
            _acpShowToast('❌ Revision content is required');
            return;
        }
    }
    try {
        var res = await fetch('/api/skills-workshop/action', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(body)
        });
        var data = await res.json();
        if (!data.ok && data.error) {
            _acpShowToast('❌ ' + data.error);
            return;
        }
        _acpShowToast('✅ Skill Workshop proposal ' + action + ' complete');
        if (typeof onDone === 'function') onDone(data);
        refreshSkillWorkshopQueue();
        if (_agentWorkspace.agent && _agentWorkspace.activeTab === 'skills') _loadAgentWorkspace(_agentWorkspace.agent);
    } catch (e) {
        _acpShowToast('❌ Skill Workshop action failed: ' + e.message);
    }
}

document.addEventListener('click', function(e) {
    var btn = e.target.closest('[data-skill-workshop-action]');
    if (!btn) return;
    var idx = Number(btn.dataset.skillWorkshopIndex);
    var action = btn.dataset.skillWorkshopAction;
    var proposal = _skillWorkshopProposals[idx];
    if (!proposal) return;
    var proposalId = _skillWorkshopProposalId(proposal);
    if (action === 'inspect') {
        inspectSkillWorkshopProposal(idx, 'review');
    } else if (action === 'revise') {
        inspectSkillWorkshopProposal(idx, 'revise');
    } else {
        runSkillWorkshopAction(proposal.agentId, proposalId, action, '', null);
    }
});

function loadAgentSkills(agentKey) {
    _currentSkillAgent = agentKey;
    var listEl = document.getElementById('skills-list');
    if (!listEl) return;
    listEl.innerHTML = '<span style="color:#666;font-size:11px;">' + escHtml(_tr('loading_skills')) + '</span>';
    fetch('/api/agent/' + encodeURIComponent(agentKey) + '/skills')
        .then(function(r) { return r.json(); })
        .then(function(data) {
            listEl.innerHTML = '';
            if (!data.skills || data.skills.length === 0) {
            listEl.innerHTML = '<span style="color:#666;font-size:11px;">' + escHtml(_tr('no_skills_configured')) + '</span>';
                return;
            }
            data.skills.forEach(function(skill) {
                var row = document.createElement('div');
                row.className = 'skill-row';
                var info = document.createElement('div');
                info.className = 'skill-row-info';
                info.innerHTML = '<span style="font-weight:bold;">' + escHtml(skill.name) + '</span>' +
                    (skill.description ? '<br><span style="color:#888;font-size:10px;">' + escHtml(skill.description).substring(0, 80) + '</span>' : '');
                var btns = document.createElement('div');
                btns.className = 'skill-row-btns';
                var editBtn = document.createElement('button');
                editBtn.textContent = '✏️';
            editBtn.title = _tr('edit_skill_title');
                editBtn.onclick = (function(sName) { return function() { editSkill(sName); }; })(skill.name);
                var libraryBtn = document.createElement('button');
            libraryBtn.textContent = _tr('save_skill_library');
            libraryBtn.title = _tr('save_skill_library_hint');
                libraryBtn.onclick = (function(sName) {
                    return function() { saveAgentSkillToLibrary(_currentSkillAgent, sName, function() { loadAgentSkills(_currentSkillAgent); }); };
                })(skill.name);
                var delBtn = document.createElement('button');
                delBtn.textContent = '🗑️';
            delBtn.title = _tr('remove_skill');
                delBtn.onclick = (function(sName) { return function() { deleteSkill(sName); }; })(skill.name);
                btns.appendChild(editBtn);
                btns.appendChild(libraryBtn);
                btns.appendChild(delBtn);
                row.appendChild(info);
                row.appendChild(btns);
                listEl.appendChild(row);
            });
        })
        .catch(function(e) {
        listEl.innerHTML = '<span style="color:#f44336;font-size:11px;">' + escHtml(_tr('error_loading_skills')) + '</span>';
        });
    refreshSkillWorkshopQueue();
}

function showAddSkillForm() {
    document.getElementById('skill-add-form').style.display = 'block';
    document.getElementById('skill-edit-form').style.display = 'none';
    document.getElementById('skill-new-name').value = '';
    document.getElementById('skill-new-content').value = '';
    document.getElementById('skill-new-name').focus();
}

function hideAddSkillForm() {
    document.getElementById('skill-add-form').style.display = 'none';
}

async function showLibraryPicker() {
    var picker = document.getElementById('skill-library-picker');
    var select = document.getElementById('skill-library-select');
    document.getElementById('skill-add-form').style.display = 'none';
    document.getElementById('skill-edit-form').style.display = 'none';
    picker.style.display = 'block';
    select.innerHTML = '<option value="">' + escHtml(_tr('loading')) + '</option>';
    try {
        var res = await fetch('/api/skills-library');
        var data = await res.json();
        var skills = Array.isArray(data) ? data : (data.skills || []);
        if (skills.length === 0) {
            select.innerHTML = '<option value="">' + escHtml(_tr('no_skills_in_library')) + '</option>';
            return;
        }
        skills.sort(function(a, b) { return (a.name || '').localeCompare(b.name || ''); });
        select.innerHTML = skills.map(function(s) {
            return '<option value="' + escHtml(s.name) + '">' + escHtml(s.name) + (s.description ? ' — ' + escHtml(s.description).substring(0, 50) : '') + '</option>';
        }).join('');
    } catch (e) {
        select.innerHTML = '<option value="">' + escHtml(_tr('failed_load_library')) + '</option>';
    }
}

function hideLibraryPicker() {
    document.getElementById('skill-library-picker').style.display = 'none';
}

async function applyLibrarySkill() {
    if (!_currentSkillAgent) return;
    var select = document.getElementById('skill-library-select');
    var skillName = select.value;
    if (!skillName) return;
    try {
        var res = await fetch('/api/skills-library/apply', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ skill: skillName, agentId: _currentSkillAgent, overwrite: false })
        });
        var data = await res.json();
        if (data.ok) {
            if (typeof _acpShowToast === 'function') _acpShowToast('✅ Applied "' + skillName + '" to agent');
            hideLibraryPicker();
            loadAgentSkills(_currentSkillAgent);
        } else if (data.exists) {
        if (confirm(_tr('overwrite_skill_confirm', { name: skillName }))) {
                var res2 = await fetch('/api/skills-library/apply', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ skill: skillName, agentId: _currentSkillAgent, overwrite: true })
                });
                var data2 = await res2.json();
                if (data2.ok) {
                    if (typeof _acpShowToast === 'function') _acpShowToast('✅ Overwrote "' + skillName + '" on agent');
                    hideLibraryPicker();
                    loadAgentSkills(_currentSkillAgent);
                }
            }
        } else {
            if (typeof _acpShowToast === 'function') _acpShowToast('❌ ' + (data.error || 'Failed to apply'));
        }
    } catch (e) {
        if (typeof _acpShowToast === 'function') _acpShowToast('❌ Error: ' + e.message);
    }
}

function saveNewSkill() {
    if (!_currentSkillAgent) return;
    var name = document.getElementById('skill-new-name').value.trim();
    var content = document.getElementById('skill-new-content').value;
    if (!name) { alert(_tr('skill_name_required')); return; }
    fetch('/api/agent/' + encodeURIComponent(_currentSkillAgent) + '/skills', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name: name, content: content })
    }).then(function(r) { return r.json(); }).then(function(data) {
    if (data.error) { alert(_tr('error') + ': ' + data.error); return; }
        hideAddSkillForm();
        loadAgentSkills(_currentSkillAgent);
        _acpShowToast('✅ Skill "' + name + '" added');
    }).catch(function(e) { alert(_tr('error_saving_skill') + ': ' + e.message); });
}

function editSkill(skillName) {
    if (!_currentSkillAgent) return;
    _editingSkillName = skillName;
    document.getElementById('skill-add-form').style.display = 'none';
    document.getElementById('skill-edit-form').style.display = 'block';
    document.getElementById('skill-edit-title').textContent = _tr('editing_skill', { name: skillName });
    document.getElementById('skill-edit-content').value = 'Loading...';
    // Fetch skills list which includes content
    fetch('/api/agent/' + encodeURIComponent(_currentSkillAgent) + '/skills')
        .then(function(r) { return r.json(); })
        .then(function(data) {
            var skill = (data.skills || []).find(function(s) { return s.name === skillName; });
            document.getElementById('skill-edit-content').value = (skill && skill.content) || '# ' + skillName + '\n\n_No content yet._';
        })
        .catch(function(e) {
            document.getElementById('skill-edit-content').value = '# ' + skillName + '\n\n_Could not load content. Edit and save to create._';
        });
}

function hideEditSkillForm() {
    document.getElementById('skill-edit-form').style.display = 'none';
    _editingSkillName = null;
}

function saveEditedSkill() {
    if (!_currentSkillAgent || !_editingSkillName) return;
    var content = document.getElementById('skill-edit-content').value;
    fetch('/api/agent/' + encodeURIComponent(_currentSkillAgent) + '/skills', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name: _editingSkillName, content: content })
    }).then(function(r) { return r.json(); }).then(function(data) {
    if (data.error) { alert(_tr('error') + ': ' + data.error); return; }
        hideEditSkillForm();
        loadAgentSkills(_currentSkillAgent);
        _acpShowToast('✅ Skill "' + _editingSkillName + '" updated');
    }).catch(function(e) { alert(_tr('error_saving_skill') + ': ' + e.message); });
}

function deleteSkill(skillName) {
    if (!_currentSkillAgent) return;
    if (!confirm(_tr('remove_agent_skill_confirm', { name: skillName }))) return;
    fetch('/api/agent/' + encodeURIComponent(_currentSkillAgent) + '/skills/' + encodeURIComponent(skillName), {
        method: 'DELETE'
    }).then(function(r) { return r.json(); }).then(function(data) {
    if (data.error) { alert(_tr('error') + ': ' + data.error); return; }
        loadAgentSkills(_currentSkillAgent);
        _acpShowToast('🗑️ Skill "' + skillName + '" removed');
    }).catch(function(e) { alert(_tr('error_deleting_skill') + ': ' + e.message); });
}

Object.assign(window, {
    loadAgentSkills,
    saveAgentSkillToLibrary,
    renderSkillWorkshopQueue,
    refreshSkillWorkshopQueue,
    hideEditSkillForm,
    saveEditedSkill,
    deleteSkill
});
