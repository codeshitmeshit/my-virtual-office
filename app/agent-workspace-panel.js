// Agent workspace panel and workspace CRUD UI.
// ─── AGENT WORKSPACE WINDOW ──────────────────────────────────
var _agentWorkspace = {
    agent: null,
    desk: null,
    data: null,
    activeTab: 'overview',
    loading: false,
    drag: null,
    resize: null,
    lastRect: null
};

function _worldToScreen(wx, wy) {
    var rect = canvas.getBoundingClientRect();
    var base = getBaseScale();
    var totalZoom = base * camera.zoom;
    var dx = (wx - W / 2 - camera.x) * totalZoom + displayW / 2;
    var dy = (wy - H / 2 - camera.y) * totalZoom + displayH / 2;
    return {
        x: dx * (rect.width / displayW) + rect.left,
        y: dy * (rect.height / displayH) + rect.top
    };
}

function _isDeskItem(item) {
    return !!(item && (item.type === 'desk' || item.type === 'bossDesk'));
}

function _findDeskAtScreen(clientX, clientY) {
    var world = screenToWorld(clientX, clientY);
    var item = _findFurnitureAt(world.x, world.y);
    return _isDeskItem(item) ? item : null;
}

function _agentWorkspaceKey(agent) {
    return (agent && (agent.statusKey || agent.id || agent.name)) || '';
}

function _hideAgentWorkspaceMenu() {
    var menu = document.getElementById('agent-workspace-menu');
    if (menu) menu.classList.add('hidden');
}

function _showAgentWorkspaceMenu(deskItem, clientX, clientY) {
    var agent = _getDeskAgent(deskItem);
    if (!agent) return false;
    var menu = document.getElementById('agent-workspace-menu');
    var btn = document.getElementById('agent-workspace-open-btn');
    if (!menu || !btn) return false;
    _agentWorkspace.agent = agent;
    _agentWorkspace.desk = deskItem;
    btn.textContent = (typeof i18n !== 'undefined' ? i18n.t('open_workspace') : 'Open workspace') + ': ' + (agent.name || 'agent');
    var pos = _worldToScreen(deskItem.x, deskItem.y);
    var left = clientX || pos.x;
    var top = clientY || pos.y;
    menu.classList.remove('hidden');
    var mw = menu.offsetWidth || 210;
    var mh = menu.offsetHeight || 42;
    left = Math.max(8, Math.min(window.innerWidth - mw - 8, left - mw / 2));
    top = Math.max(8, Math.min(window.innerHeight - mh - 8, top - mh - 10));
    menu.style.left = left + 'px';
    menu.style.top = top + 'px';
    return true;
}

function _formatAgentWorkspaceTime(value) {
    if (!value) return '';
    var d = new Date(typeof value === 'number' ? (value > 100000000000 ? value : value * 1000) : value);
    if (isNaN(d.getTime())) return String(value);
    return d.toLocaleString([], { month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit' });
}

function _agentWorkspaceItemList(items, emptyText, render) {
    if (!items || !items.length) return '<div class="agent-workspace-empty">' + escHtml(emptyText) + '</div>';
    return '<div class="agent-workspace-list">' + items.map(render).join('') + '</div>';
}

function _agentWorkspaceRecentActivity(data, limit) {
    var activity = (data.activity || []).filter(function(msg) {
        var text = msg && (msg.text || msg.content || msg.message || msg.task || '');
        return String(text || '').trim();
    }).slice(-limit).reverse();
    return _agentWorkspaceItemList(activity, 'No recent activity surfaced yet', function(msg) {
        var text = msg.text || msg.content || msg.message || msg.task || JSON.stringify(msg).slice(0, 320);
        return '<div class="agent-workspace-item agent-workspace-activity-item">' +
            '<div>' + escHtml(String(text).slice(0, 700)) + '</div>' +
            '<div class="agent-workspace-meta">' + escHtml(_formatAgentWorkspaceTime(msg.ts || msg.time || msg.createdAt || msg.updatedAt)) + '</div>' +
        '</div>';
    });
}

function _agentWorkspaceProjectMeta(t, compact) {
    var parts = [];
    if (t.projectTitle) parts.push(t.projectTitle);
    if (t.role) parts.push(t.role);
    if (t.priority) parts.push(t.priority);
    if (t.column) parts.push(t.column);
    if (t.executionState) parts.push(t.executionState);
    if (!compact && t.projectWorkflowPhase) parts.push('project ' + t.projectWorkflowPhase);
    if (!compact && t.activeAttemptStatus) parts.push('attempt ' + t.activeAttemptStatus);
    if (!compact && t.scheduledRepeatEnabled) parts.push('scheduled');
    return parts.join(' · ');
}

function _agentWorkspaceProjectBadges(t) {
    var badges = [];
    if (t.completed) badges.push('done');
    if (t.activeAttemptId) badges.push('active');
    if (t.meetingBlocker && t.meetingBlocker.status) badges.push('meeting ' + t.meetingBlocker.status);
    if (t.projectExecutionFlowActive) badges.push('flow active');
    if (t.projectExecutionFlowStopReason) badges.push(t.projectExecutionFlowStopReason);
    if (t.blockedReason) badges.push('blocked');
    return badges.length ? '<div class="agent-workspace-badges">' + badges.map(function(label) {
        return '<span>' + escHtml(label) + '</span>';
    }).join('') + '</div>' : '';
}

function _workspaceFolderOptions(current) {
    var notes = ((_agentWorkspace.data || {}).workspace || {}).notes || [];
    var folders = {};
    notes.forEach(function(n) { folders[n.folder || 'General'] = true; });
    folders.General = true;
    var value = current || 'General';
    return Object.keys(folders).sort().map(function(f) {
        return '<option value="' + escAttr(f) + '"' + (f === value ? ' selected' : '') + '>' + escHtml(f) + '</option>';
    }).join('');
}

function _renderAgentWorkspaceOverview(data) {
    var agent = data.agent || {};
    var presence = data.presence || {};
    var workspace = data.workspace || {};
    var tasks = (workspace.tasks || []).filter(function(t) { return !t.done; }).slice(0, 5);
    var bulletin = (workspace.bulletin || []).slice(0, 4);
    var projectTasks = (data.projectTasks || []).slice(0, 5);
    var score = data.score || {};
    return '<div class="agent-workspace-grid">' +
        '<div class="agent-workspace-card"><h3>Status</h3>' +
            '<div>' + escHtml((presence.state || 'idle').toUpperCase()) + '</div>' +
            '<div class="agent-workspace-meta">' + escHtml(presence.task || agent.role || 'No active task') + '</div>' +
            '<div class="agent-workspace-meta">' + escHtml(agent.providerKind || 'openclaw') + ' · ' + escHtml(agent.model || agent.provider || 'model not set') + '</div>' +
        '</div>' +
        '<div class="agent-workspace-card"><h3>Agent Info</h3>' +
            '<div class="agent-workspace-item">' + escHtml(agent.displayName || agent.name || agent.id) +
                '<div class="agent-workspace-meta">' + escHtml(agent.statusKey || agent.id || '') + ' · ' + escHtml(agent.branch || 'Unassigned') + '</div>' +
                '<div class="agent-workspace-meta">' + escHtml(agent.role || '') + '</div>' +
            '</div>' +
            '<div class="agent-workspace-item">' + escHtml(score.score || 0) + ' points<div class="agent-workspace-meta">' + escHtml(score.completed || 0) + ' completed · streak ' + escHtml(score.streak || 0) + '</div></div>' +
        '</div>' +
        '<div class="agent-workspace-card"><h3>Open Tasks</h3>' +
            _agentWorkspaceItemList(tasks, 'No workspace tasks', function(t) {
                return '<div class="agent-workspace-item">' + escHtml(t.text) + '<div class="agent-workspace-meta">' + escHtml(t.status || 'queued') + (t.due ? ' · Due ' + escHtml(t.due) : '') + '</div></div>';
            }) +
        '</div>' +
        '<div class="agent-workspace-card"><h3>Bulletin</h3>' +
            _agentWorkspaceItemList(bulletin, 'No pinned notes', function(n) {
                return '<div class="agent-workspace-item">' + escHtml(n.text) + '<div class="agent-workspace-meta">' + escHtml(n.createdBy || 'user') + ' · ' + escHtml(_formatAgentWorkspaceTime(n.createdAt)) + '</div></div>';
            }) +
        '</div>' +
        '<div class="agent-workspace-card"><h3>Project Work</h3>' +
            _agentWorkspaceItemList(projectTasks, 'No assigned project cards', function(t) {
                return '<div class="agent-workspace-item">' + escHtml(t.title) +
                    '<div class="agent-workspace-meta">' + escHtml(_agentWorkspaceProjectMeta(t, true)) + '</div>' +
                    _agentWorkspaceProjectBadges(t) +
                '</div>';
            }) +
        '</div>' +
        '<div class="agent-workspace-card agent-workspace-wide"><h3>Recent Activity</h3>' +
            _agentWorkspaceRecentActivity(data, 12) +
        '</div>' +
    '</div>';
}

function _renderAgentWorkspaceBulletin(data) {
    var items = (data.workspace && data.workspace.bulletin) || [];
    return '<form class="agent-workspace-form" data-aw-form="bulletin">' +
        '<input name="text" maxlength="5000" placeholder="Add note for this agent">' +
        '<button type="submit">Add</button>' +
    '</form>' +
    _agentWorkspaceItemList(items, 'No bulletin notes yet', function(n) {
        return '<div class="agent-workspace-item">' +
            '<div>' + escHtml(n.text) + '</div>' +
            '<div class="agent-workspace-meta">' + escHtml(n.createdBy || 'user') + ' · ' + escHtml(_formatAgentWorkspaceTime(n.createdAt)) + '</div>' +
            '<button type="button" data-aw-action="deleteBulletin" data-aw-id="' + escHtml(n.id) + '">Delete</button>' +
        '</div>';
    });
}

function _renderAgentWorkspaceTasks(data) {
    var items = (data.workspace && data.workspace.tasks) || [];
    var projectTasks = data.projectTasks || [];
    var settings = (data.workspace && data.workspace.settings) || {};
    var activeId = (data.workspace && data.workspace.activeTaskId) || '';
    return '<div class="agent-workspace-toolbar">' +
        '<label>Run mode <select data-aw-action="setTaskMode">' +
            '<option value="manual"' + ((settings.taskMode || 'manual') === 'manual' ? ' selected' : '') + '>Manual</option>' +
            '<option value="single"' + (settings.taskMode === 'single' ? ' selected' : '') + '>Single task</option>' +
            '<option value="auto"' + (settings.taskMode === 'auto' ? ' selected' : '') + '>Auto run queue</option>' +
        '</select></label>' +
        (activeId ? '<button type="button" data-aw-action="completeTask" data-aw-id="' + escAttr(activeId) + '">Complete Active</button>' : '') +
    '</div>' +
    '<form class="agent-workspace-form agent-workspace-form-stack" data-aw-form="task">' +
        '<input name="text" maxlength="1000" placeholder="Add workspace task">' +
        '<textarea name="detail" maxlength="5000" placeholder="Details or instructions"></textarea>' +
        '<div class="agent-workspace-row"><input name="due" maxlength="80" placeholder="Due"><select name="priority"><option>normal</option><option>high</option><option>low</option></select></div>' +
        '<button type="submit">Add</button>' +
    '</form>' +
    _agentWorkspaceItemList(items, 'No workspace tasks yet', function(t) {
        return '<div class="agent-workspace-item">' +
            '<label><input type="checkbox" data-aw-action="toggleTask" data-aw-id="' + escAttr(t.id) + '"' + (t.done ? ' checked' : '') + '> ' + escHtml(t.text) + '</label>' +
            (t.detail ? '<div class="agent-workspace-detail">' + escHtml(t.detail) + '</div>' : '') +
            '<div class="agent-workspace-meta">' + escHtml(t.status || (t.done ? 'done' : 'queued')) + ' · ' + escHtml(t.priority || 'normal') + (t.due ? ' · Due ' + escHtml(t.due) : '') + '</div>' +
            '<div class="agent-workspace-actions">' +
                (!t.done ? '<button type="button" data-aw-action="startTask" data-aw-id="' + escAttr(t.id) + '">Run</button>' : '') +
                '<button type="button" data-aw-edit-task="' + escAttr(t.id) + '">Edit</button>' +
                '<button type="button" data-aw-action="deleteTask" data-aw-id="' + escAttr(t.id) + '">Delete</button>' +
            '</div>' +
        '</div>';
    }) +
    '<div class="agent-workspace-card" style="margin-top:10px"><h3>Project Cards</h3>' +
    _agentWorkspaceItemList(projectTasks, 'No assigned project cards', function(t) {
        var blocker = t.meetingBlocker || {};
        return '<div class="agent-workspace-item agent-workspace-project-card">' +
            '<div><b>' + escHtml(t.title) + '</b></div>' +
            (t.description ? '<div class="agent-workspace-detail">' + escHtml(String(t.description).slice(0, 360)) + '</div>' : '') +
            '<div class="agent-workspace-meta">' + escHtml(_agentWorkspaceProjectMeta(t, false)) + '</div>' +
            _agentWorkspaceProjectBadges(t) +
            (blocker.status ? '<div class="agent-workspace-detail">Meeting blocker: ' + escHtml(blocker.status) + (blocker.requestId ? ' · ' + escHtml(blocker.requestId) : '') + '</div>' : '') +
            (t.lastError || t.blockedReason ? '<div class="agent-workspace-detail">' + escHtml(t.lastError || t.blockedReason) + '</div>' : '') +
        '</div>';
    }) + '</div>';
}

function _renderAgentWorkspaceFiles(data) {
    var canEdit = !data.settings || data.settings.filesApplicable !== false;
    var editor = data.fileEditor || null;
    var search = data.fileSearch || '';
    var files = data.files || [];
    if (search) {
        var q = search.toLowerCase();
        files = files.filter(function(f) {
            return String(f.path || f.name || '').toLowerCase().indexOf(q) >= 0 ||
                String(f.kind || '').toLowerCase().indexOf(q) >= 0;
        });
    }
    var html = canEdit ? '<div class="agent-workspace-files-shell">' +
        '<div class="agent-workspace-file-list-pane">' +
        '<form class="agent-workspace-form agent-workspace-file-tools" data-aw-form="file-create">' +
            '<input name="search" data-aw-file-search value="' + escAttr(search) + '" placeholder="Search files">' +
            '<input name="path" placeholder="notes/new-note.md">' +
            '<button type="submit">Create</button>' +
        '</form>' : '<div class="agent-workspace-empty">This platform does not expose editable workspace files through Virtual Office. Use Notes and Tasks for durable dashboard data.</div>';
    if (canEdit) {
        html += _agentWorkspaceItemList(files, 'No matching workspace files', function(f) {
            return '<div class="agent-workspace-item agent-workspace-file-row">' +
                '<button type="button" class="agent-workspace-file-open" data-aw-action="readFile" data-aw-path="' + escAttr(f.path || '') + '">' + escHtml(f.path || f.name) + '</button>' +
                '<div class="agent-workspace-meta">' + escHtml(f.kind || 'file') + ' · ' + escHtml(Math.ceil((f.size || 0) / 1024)) + ' KB · ' + escHtml(_formatAgentWorkspaceTime(f.modified)) + '</div>' +
                (f.path && f.kind !== 'large-text' ? '<div class="agent-workspace-actions"><button type="button" data-aw-action="readFile" data-aw-path="' + escAttr(f.path) + '">Open</button><button type="button" data-aw-action="deleteFile" data-aw-path="' + escAttr(f.path) + '">Delete</button></div>' : '') +
            '</div>';
        }) + '</div>';
    }
    if (editor) {
        html += '<form class="agent-workspace-editor agent-workspace-file-editor-pane" data-aw-form="file-save">' +
            '<div class="agent-workspace-editor-header"><input name="path" value="' + escAttr(editor.path || '') + '" readonly>' +
            '<div class="agent-workspace-actions"><button type="submit">Save</button><button type="button" data-aw-action="closeFile">Close</button></div></div>' +
            '<textarea name="content" spellcheck="false">' + escTextarea(editor.content || '') + '</textarea>' +
        '</form>';
    } else if (canEdit) {
        html += '<div class="agent-workspace-file-editor-pane agent-workspace-empty">Open a file to edit it here.</div>';
    }
    if (canEdit) html += '</div>';
    return html;
}

function _renderAgentWorkspaceSkills(data) {
    var skills = data.skills || [];
    var library = data.skillLibrary || [];
    var editor = data.skillEditor || null;
    var libraryEditor = data.librarySkillEditor || null;
    var agentSkillsAllowed = !data.settings || data.settings.agentSkillsApplicable !== false;
    return '<div class="agent-workspace-skills-shell">' +
        '<div class="agent-workspace-skill-column">' +
            '<div class="agent-workspace-panel-heading"><span>Agent Skills</span>' + (agentSkillsAllowed ? '<button type="button" data-aw-action="newAgentSkill">New</button>' : '') + '</div>' +
            (agentSkillsAllowed ? _agentWorkspaceItemList(skills, 'No skills installed for this agent', function(s) {
                return '<div class="agent-workspace-item">' +
                    '<div><b>' + escHtml(s.name) + '</b></div>' +
                    '<div class="agent-workspace-meta">' + escHtml(s.type || 'skill') + (s.description ? ' · ' + escHtml(s.description) : '') + '</div>' +
                    '<div class="agent-workspace-actions"><button type="button" data-aw-skill-edit="' + escAttr(s.name) + '">Open</button><button type="button" data-aw-action="saveAgentSkillToLibrary" data-aw-id="' + escAttr(s.name) + '">Save to Skill Library</button><button type="button" data-aw-action="deleteAgentSkill" data-aw-id="' + escAttr(s.name) + '">Delete</button></div>' +
                '</div>';
            }) : '<div class="agent-workspace-empty">This platform does not use OpenClaw workspace skills. You can still create and edit reusable skills in the library.</div>') +
        '</div>' +
        '<div class="agent-workspace-skill-column">' +
            '<div class="agent-workspace-panel-heading"><span>Skill Library</span><button type="button" data-aw-action="newLibrarySkill">New</button></div>' +
            _agentWorkspaceItemList(library, 'No library skills found', function(s) {
                return '<div class="agent-workspace-item">' +
                    '<div><b>' + escHtml(s.name) + '</b></div>' +
                    '<div class="agent-workspace-meta">' + escHtml(s.description || 'Reusable library skill') + '</div>' +
                    '<div class="agent-workspace-actions"><button type="button" data-aw-library-edit="' + escAttr(s.name) + '">Open</button>' + (agentSkillsAllowed ? '<button type="button" data-aw-action="applyLibrarySkill" data-aw-id="' + escAttr(s.name) + '">Install</button>' : '') + '</div>' +
                '</div>';
            }) +
        '</div>' +
        '<div class="agent-workspace-skill-editor">' +
            '<div class="agent-workspace-panel-heading"><span>Skill Workshop</span><button type="button" data-aw-action="refreshSkillWorkshop">Refresh</button></div>' +
            '<div id="agent-workspace-skill-workshop-list" class="skill-workshop-list agent-workspace-workshop-list"><span style="color:#666;font-size:11px;">Loading proposals...</span></div>' +
            (editor || libraryEditor ? '<form class="agent-workspace-editor" data-aw-form="' + (libraryEditor ? 'library-skill-save' : 'agent-skill-save') + '">' +
                '<div class="agent-workspace-editor-header"><input name="name" value="' + escAttr((editor || libraryEditor).name || '') + '" placeholder="skill-name">' +
                '<button type="submit">Save</button></div>' +
                '<textarea name="content" spellcheck="false">' + escTextarea((editor || libraryEditor).content || '') + '</textarea>' +
            '</form>' : '<div class="agent-workspace-empty">Open or create a skill to edit its SKILL.md here.</div>') +
        '</div>' +
    '</div>';
}

function _renderAgentWorkspaceNotes(data) {
    var notes = (data.workspace && data.workspace.notes) || [];
    var selectedId = data.selectedNoteId || (notes[0] && notes[0].id) || '';
    var selected = notes.find(function(n) { return n.id === selectedId; }) || null;
    var byFolder = {};
    notes.forEach(function(n) {
        var folder = n.folder || 'General';
        if (!byFolder[folder]) byFolder[folder] = [];
        byFolder[folder].push(n);
    });
    return '<div class="agent-workspace-notes-app">' +
        '<aside class="agent-workspace-notes-folders">' +
            '<button type="button" data-aw-action="newNote">New Note</button>' +
            (Object.keys(byFolder).length ? Object.keys(byFolder).sort().map(function(folder) {
                return '<div class="agent-workspace-note-folder"><div class="agent-workspace-note-folder-title">' + escHtml(folder) + '</div>' +
                    byFolder[folder].map(function(n) {
                        return '<button type="button" class="agent-workspace-note-link' + (n.id === selectedId ? ' active' : '') + '" data-aw-select-note="' + escAttr(n.id) + '">' +
                            '<span>' + escHtml(n.title || 'Untitled note') + '</span><small>' + escHtml(n.kind || 'note') + '</small></button>';
                    }).join('') +
                '</div>';
            }).join('') : '<div class="agent-workspace-empty">No notes yet</div>') +
        '</aside>' +
        '<section class="agent-workspace-note-editor">' +
            '<form data-aw-form="note-save">' +
                '<input type="hidden" name="id" value="' + escAttr(selected ? selected.id : '') + '">' +
                '<div class="agent-workspace-note-title-row"><input name="title" maxlength="160" value="' + escAttr(selected ? selected.title : '') + '" placeholder="Untitled note">' +
                '<button type="submit">Save</button>' +
                (selected ? '<button type="button" data-aw-action="deleteNote" data-aw-id="' + escAttr(selected.id) + '">Delete</button>' : '') + '</div>' +
                '<div class="agent-workspace-row"><select name="folder">' + _workspaceFolderOptions(selected ? selected.folder : 'General') + '</select><input name="newFolder" maxlength="120" placeholder="New folder"><select name="kind">' +
                    ['note','list','page','group'].map(function(k) { return '<option value="' + k + '"' + (selected && selected.kind === k ? ' selected' : '') + '>' + k[0].toUpperCase() + k.slice(1) + '</option>'; }).join('') +
                '</select></div>' +
                '<textarea name="content" maxlength="50000" placeholder="Write notes, lists, pages, or grouped context">' + escTextarea(selected ? selected.content : '') + '</textarea>' +
            '</form>' +
        '</section>' +
    '</div>';
}

function _renderAgentWorkspaceSettings(data) {
    var agent = data.agent || {};
    var provider = agent.providerKind === 'hermes' ? 'Hermes' : (agent.providerKind === 'codex' ? 'Codex' : 'OpenClaw');
    var workspace = data.workspace || {};
    var settings = workspace.settings || {};
    var score = data.score || {};
    var modelEditable = !data.settings || data.settings.modelEditable !== false;
    return '<form class="agent-workspace-settings agent-workspace-settings-polished" data-aw-form="settings">' +
        '<section class="agent-workspace-settings-section"><h3>Agent</h3>' +
            '<div class="agent-workspace-settings-grid">' +
                '<label>Name<input name="name" value="' + escAttr(agent.name || '') + '" placeholder="Name"></label>' +
                '<label>Display<input name="displayName" value="' + escAttr(agent.displayName || agent.name || '') + '" placeholder="Display name"></label>' +
                '<label>Emoji<input name="emoji" value="' + escAttr(agent.emoji || '') + '" placeholder="Emoji"></label>' +
                '<label>Branch<select name="branch">' + getBranchList().map(function(b) { return '<option value="' + escAttr(b.id) + '"' + ((agent.branch || 'UNASSIGNED') === b.id ? ' selected' : '') + '>' + escHtml((b.emoji || '') + ' ' + b.name) + '</option>'; }).join('') + '</select></label>' +
                '<label class="agent-workspace-settings-span">Role<input name="role" value="' + escAttr(agent.role || '') + '" placeholder="Role"></label>' +
                '<label>Points<input name="leaderboardPoints" type="number" value="' + escAttr(settings.leaderboardPoints || score.score || 0) + '"></label>' +
            '</div>' +
            '<div class="agent-workspace-meta">' + escHtml(agent.statusKey || agent.id || '') + ' · completed ' + escHtml(score.completed || 0) + ' · streak ' + escHtml(score.streak || 0) + '</div>' +
        '</section>' +
        '<section class="agent-workspace-settings-section"><h3>Runtime</h3>' +
            '<div class="agent-workspace-settings-grid">' +
                (modelEditable ? '<label class="agent-workspace-settings-span">Model<select name="model" id="agent-workspace-model-select"><option value="">Loading models...</option></select></label>' : '<label class="agent-workspace-settings-span">Model<input name="model" value="' + escAttr(agent.model || agent.provider || (provider + ' managed')) + '" readonly></label>') +
                '<label class="agent-workspace-checkbox"><input type="checkbox" name="cronEnabled"' + (settings.cronEnabled ? ' checked' : '') + (data.settings && data.settings.cronApplicable ? '' : ' disabled') + '> Cron enabled</label>' +
            '</div>' +
            '<div class="agent-workspace-meta">' + escHtml(provider) + ' · current ' + escHtml(agent.model || agent.provider || 'default') + ' · ' + (data.settings && data.settings.cronApplicable ? 'OpenClaw cron supported' : 'Cron not surfaced for this platform') + '</div>' +
        '</section>' +
        '<section class="agent-workspace-settings-section"><h3>Heartbeat</h3>' +
            (data.settings && data.settings.heartbeatApplicable ? '<textarea name="heartbeatContent" spellcheck="false">' + escTextarea(data.settings.heartbeatContent || '') + '</textarea>' : '<div class="agent-workspace-item">Not applicable<div class="agent-workspace-meta">This platform does not use OpenClaw HEARTBEAT.md.</div></div>') +
        '</section>' +
        '<div class="agent-workspace-settings-footer"><button class="agent-workspace-action" type="submit">Save Settings</button><span id="agent-workspace-settings-status" class="agent-workspace-meta"></span></div>' +
    '</form>';
}

function _renderAgentWorkspace() {
    var body = document.getElementById('agent-workspace-body');
    var data = _agentWorkspace.data;
    if (!body) return;
    document.querySelectorAll('.agent-workspace-tabs button').forEach(function(btn) {
        btn.classList.toggle('active', btn.dataset.awTab === _agentWorkspace.activeTab);
    });
    if (_agentWorkspace.loading) {
    body.innerHTML = '<div class="agent-workspace-empty">' + escHtml(_tr('loading_workspace')) + '</div>';
        return;
    }
    if (!data || !data.ok) {
            body.innerHTML = '<div class="agent-workspace-empty">' + escHtml((data && data.error) || _tr('workspace_unavailable')) + '</div>';
        return;
    }
    if (_agentWorkspace.activeTab === 'bulletin') body.innerHTML = _renderAgentWorkspaceBulletin(data);
    else if (_agentWorkspace.activeTab === 'tasks') body.innerHTML = _renderAgentWorkspaceTasks(data);
    else if (_agentWorkspace.activeTab === 'files') body.innerHTML = _renderAgentWorkspaceFiles(data);
    else if (_agentWorkspace.activeTab === 'skills') body.innerHTML = _renderAgentWorkspaceSkills(data);
    else if (_agentWorkspace.activeTab === 'notes') body.innerHTML = _renderAgentWorkspaceNotes(data);
    else if (_agentWorkspace.activeTab === 'settings') body.innerHTML = _renderAgentWorkspaceSettings(data);
    else body.innerHTML = _renderAgentWorkspaceOverview(data);
    if (_agentWorkspace.activeTab === 'settings' && (!data.settings || data.settings.modelEditable !== false)) _populateAgentWorkspaceModels(data);
    if (_agentWorkspace.activeTab === 'skills') {
        renderSkillWorkshopQueue();
        if (!_skillWorkshopLoaded && !_skillWorkshopLoading) refreshSkillWorkshopQueue();
    }
}

async function _loadAgentWorkspace(agent) {
    var key = _agentWorkspaceKey(agent);
    if (!key) return;
    _agentWorkspace.loading = true;
    _renderAgentWorkspace();
    try {
        var res = await fetch('/api/agent-workspace/' + encodeURIComponent(key), { cache: 'no-store' });
        _agentWorkspace.data = await res.json();
    } catch (e) {
        _agentWorkspace.data = { ok: false, error: e.message || String(e) };
    }
    _agentWorkspace.loading = false;
    _renderAgentWorkspace();
}

async function _populateAgentWorkspaceModels(data) {
    var select = document.getElementById('agent-workspace-model-select');
    if (!select || select.dataset.loaded === '1') return;
    try {
        var res = await fetch('/api/native-models', { cache: 'no-store' });
        var nativeModels = await res.json();
        var models = nativeModels.openclaw || {};
        var agentKey = data.agent && data.agent.statusKey;
        var current = (agentKey && models.agents && models.agents[agentKey] && models.agents[agentKey].model) || (data.agent && data.agent.model) || models.defaultModel || '';
        var html = '<option value="">Use default</option>';
        var grouped = {};
        (models.models || []).forEach(function(m) {
            if (m.missing) return;
            var provider = m.provider || (m.id && m.id.split('/')[0]) || 'Models';
            if (!grouped[provider]) grouped[provider] = [];
            grouped[provider].push(m);
        });
        Object.keys(grouped).sort().forEach(function(provider) {
            html += '<optgroup label="' + escAttr(provider) + '">';
            grouped[provider].sort(function(a, b) { return String(a.id || '').localeCompare(String(b.id || '')); }).forEach(function(m) {
                var label = (m.name && m.name !== m.id) ? (m.id + ' · ' + m.name) : m.id;
                html += '<option value="' + escAttr(m.id) + '"' + (m.id === current ? ' selected' : '') + '>' + escHtml(label) + '</option>';
            });
            html += '</optgroup>';
        });
        select.innerHTML = html;
        select.value = current || '';
        select.dataset.loaded = '1';
    } catch (e) {
        select.innerHTML = '<option value="">' + escHtml(_tr('model_list_unavailable')) + '</option>';
    }
}

async function _agentWorkspacePost(action, payload) {
    var agent = _agentWorkspace.agent;
    var key = _agentWorkspaceKey(agent);
    if (!key) return;
    var body = Object.assign({ action: action, actor: 'user' }, payload || {});
    var res = await fetch('/api/agent-workspace/' + encodeURIComponent(key), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body)
    });
    var json = await res.json();
    if (action === 'readFile' && json.ok && json.file) {
        if (_agentWorkspace.data) _agentWorkspace.data.fileEditor = json.file;
    } else {
        _agentWorkspace.data = json;
    }
    _renderAgentWorkspace();
    return json;
}

async function _agentWorkspaceSetModel(model) {
    var agent = _agentWorkspace.agent;
    var key = _agentWorkspaceKey(agent);
    if (!key) return { ok: false, error: 'No agent selected' };
    var res = await fetch('/api/native-models/openclaw/agent-model', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ agent: key, model: model || '' })
    });
    return await res.json();
}

function _findWorkspaceTask(id) {
    return (((_agentWorkspace.data || {}).workspace || {}).tasks || []).find(function(t) { return t.id === id; });
}

function _findWorkspaceNote(id) {
    return (((_agentWorkspace.data || {}).workspace || {}).notes || []).find(function(n) { return n.id === id; });
}

function _findAgentSkill(name) {
    return (((_agentWorkspace.data || {}).skills) || []).find(function(s) { return s.name === name; });
}

async function _openLibrarySkill(name) {
    try {
        var res = await fetch('/api/skills-library/' + encodeURIComponent(name), { cache: 'no-store' });
        var data = await res.json();
        if (!_agentWorkspace.data) return;
        _agentWorkspace.data.librarySkillEditor = { name: data.skill || data.name || name, content: data.content || '' };
        delete _agentWorkspace.data.skillEditor;
        _renderAgentWorkspace();
    } catch (e) {
        if (_agentWorkspace.data) _agentWorkspace.data.librarySkillEditor = { name: name, content: '' };
        _renderAgentWorkspace();
    }
}

function _openAgentWorkspace(agent, deskItem) {
    var panel = document.getElementById('agent-workspace-panel');
    if (!panel || !agent) return;
    _hideAgentWorkspaceMenu();
    _agentWorkspace.agent = agent;
    _agentWorkspace.desk = deskItem || null;
    document.getElementById('agent-workspace-emoji').textContent = agent.emoji || '🤖';
    document.getElementById('agent-workspace-name').textContent = agent.name || 'Agent Workspace';
    var provider = agent.providerKind === 'hermes' ? 'Hermes' : (agent.providerKind === 'codex' ? 'Codex' : 'OpenClaw');
    document.getElementById('agent-workspace-subtitle').textContent = provider + ' · ' + (agent.role || agent.statusKey || agent.id || 'Workspace');
    panel.classList.remove('hidden');
    if (!panel.style.left && !panel.style.right) {
        panel.style.right = '24px';
        panel.style.top = '48px';
    }
    _loadAgentWorkspace(agent);
}

function _clampAgentWorkspacePanel() {
    var panel = document.getElementById('agent-workspace-panel');
    if (!panel || panel.classList.contains('hidden') || panel.classList.contains('maximized')) return;
    var rect = panel.getBoundingClientRect();
    var left = Math.max(0, Math.min(window.innerWidth - Math.min(80, rect.width), rect.left));
    var top = Math.max(0, Math.min(window.innerHeight - Math.min(80, rect.height), rect.top));
    panel.style.left = left + 'px';
    panel.style.top = top + 'px';
    panel.style.right = 'auto';
}

function _initAgentWorkspaceUI() {
    var menuBtn = document.getElementById('agent-workspace-open-btn');
    var panel = document.getElementById('agent-workspace-panel');
    var closeBtn = document.getElementById('agent-workspace-close');
    var refreshBtn = document.getElementById('agent-workspace-refresh');
    var maxBtn = document.getElementById('agent-workspace-maximize');
    var header = document.getElementById('agent-workspace-drag-handle');
    var body = document.getElementById('agent-workspace-body');
    var resizeHandle = panel ? panel.querySelector('.agent-workspace-resize-handle') : null;

    if (menuBtn) menuBtn.addEventListener('click', function(e) {
        e.stopPropagation();
        _openAgentWorkspace(_agentWorkspace.agent, _agentWorkspace.desk);
    });
    if (closeBtn) closeBtn.addEventListener('click', function() { panel.classList.add('hidden'); });
    if (refreshBtn) refreshBtn.addEventListener('click', function() { if (_agentWorkspace.agent) _loadAgentWorkspace(_agentWorkspace.agent); });
    if (maxBtn) maxBtn.addEventListener('click', function() {
        if (!panel) return;
        panel.classList.toggle('maximized');
        maxBtn.textContent = panel.classList.contains('maximized') ? '▣' : '□';
    });
    document.querySelectorAll('.agent-workspace-tabs button').forEach(function(btn) {
        btn.addEventListener('click', function() {
            _agentWorkspace.activeTab = btn.dataset.awTab || 'overview';
            _renderAgentWorkspace();
        });
    });
    if (body) {
        body.addEventListener('submit', function(e) {
            var form = e.target.closest('[data-aw-form]');
            if (!form) return;
            e.preventDefault();
            if (form.dataset.awForm === 'bulletin') {
                var text = form.elements.text.value.trim();
                if (text) _agentWorkspacePost('addBulletin', { text: text });
            } else if (form.dataset.awForm === 'task') {
                var taskText = form.elements.text.value.trim();
                var due = form.elements.due.value.trim();
                var detail = form.elements.detail.value.trim();
                var priority = form.elements.priority.value;
                if (taskText) _agentWorkspacePost('addTask', { text: taskText, due: due, detail: detail, priority: priority });
            } else if (form.dataset.awForm === 'file-create') {
                var path = form.elements.path.value.trim();
                if (path) _agentWorkspacePost('createFile', { path: path, content: '# ' + path.split('/').pop().replace(/\.[^.]+$/, '') + '\n' });
            } else if (form.dataset.awForm === 'file-save') {
                _agentWorkspacePost('saveFile', { path: form.elements.path.value, content: form.elements.content.value });
            } else if (form.dataset.awForm === 'note') {
                var folder = form.elements.newFolder.value.trim() || form.elements.folder.value || 'General';
                var tags = [];
                if (form.elements.tags && form.elements.tags.value) tags = form.elements.tags.value.split(',');
                var title = form.elements.title.value.trim();
                if (title || form.elements.content.value.trim()) _agentWorkspacePost('addNote', { title: title || 'Untitled note', folder: folder, kind: form.elements.kind.value, content: form.elements.content.value, tags: tags });
            } else if (form.dataset.awForm === 'note-save') {
                var noteFolder = form.elements.newFolder.value.trim() || form.elements.folder.value || 'General';
                var notePayload = { title: form.elements.title.value || 'Untitled note', folder: noteFolder, kind: form.elements.kind.value, content: form.elements.content.value, tags: [] };
                if (form.elements.id.value) _agentWorkspacePost('updateNote', Object.assign({ id: form.elements.id.value }, notePayload));
                else _agentWorkspacePost('addNote', notePayload);
            } else if (form.dataset.awForm === 'agent-skill-save') {
                _agentWorkspacePost('saveAgentSkill', { name: form.elements.name.value, content: form.elements.content.value });
            } else if (form.dataset.awForm === 'library-skill-save') {
                _agentWorkspacePost('saveLibrarySkill', { name: form.elements.name.value, content: form.elements.content.value });
            } else if (form.dataset.awForm === 'settings') {
                var payload = {
                    name: form.elements.name.value,
                    displayName: form.elements.displayName.value,
                    role: form.elements.role.value,
                    branch: form.elements.branch.value,
                    emoji: form.elements.emoji.value,
                    leaderboardPoints: Number(form.elements.leaderboardPoints.value || 0),
                    cronEnabled: !!(form.elements.cronEnabled && form.elements.cronEnabled.checked)
                };
                if (form.elements.heartbeatContent) payload.heartbeatContent = form.elements.heartbeatContent.value;
                var currentData = _agentWorkspace.data || {};
                var canSetModel = currentData.settings && currentData.settings.modelEditable !== false;
                var selectedModel = canSetModel && form.elements.model ? form.elements.model.value : '';
                Promise.resolve(_agentWorkspacePost('updateSettings', payload)).then(function() {
                    return canSetModel ? _agentWorkspaceSetModel(selectedModel) : { ok: true };
                }).then(function(result) {
                    var status = document.getElementById('agent-workspace-settings-status');
                    if (status) status.textContent = result && result.ok === false ? (result.error || 'Model not changed') : 'Saved';
                    _fetchRoster();
                });
            }
        });
        body.addEventListener('click', function(e) {
            var target = e.target.closest('[data-aw-action]');
            var editTask = e.target.closest('[data-aw-edit-task]');
            var editNote = e.target.closest('[data-aw-edit-note]');
            var skillEdit = e.target.closest('[data-aw-skill-edit]');
            var libraryEdit = e.target.closest('[data-aw-library-edit]');
            var selectNote = e.target.closest('[data-aw-select-note]');
            if (selectNote) {
                if (_agentWorkspace.data) _agentWorkspace.data.selectedNoteId = selectNote.dataset.awSelectNote;
                _renderAgentWorkspace();
                return;
            }
            if (skillEdit) {
                var skill = _findAgentSkill(skillEdit.dataset.awSkillEdit);
                if (!_agentWorkspace.data || !skill) return;
                _agentWorkspace.data.skillEditor = { name: skill.name, content: skill.content || '' };
                delete _agentWorkspace.data.librarySkillEditor;
                _renderAgentWorkspace();
                return;
            }
            if (libraryEdit) {
                _openLibrarySkill(libraryEdit.dataset.awLibraryEdit);
                return;
            }
            if (editTask) {
                var task = _findWorkspaceTask(editTask.dataset.awEditTask);
                if (!task) return;
    var text = prompt(_tr('task_title_prompt'), task.text || '');
                if (text == null) return;
    var detail = prompt(_tr('task_details_prompt'), task.detail || '');
                if (detail == null) return;
                _agentWorkspacePost('updateTask', { id: task.id, text: text, detail: detail, due: task.due || '', priority: task.priority || 'normal' });
                return;
            }
            if (editNote) {
                var note = _findWorkspaceNote(editNote.dataset.awEditNote);
                if (!note) return;
    var title = prompt(_tr('note_title_prompt'), note.title || '');
                if (title == null) return;
    var content = prompt(_tr('note_content_prompt'), note.content || '');
                if (content == null) return;
                _agentWorkspacePost('updateNote', { id: note.id, title: title, content: content, folder: note.folder || 'General', kind: note.kind || 'note', tags: note.tags || [] });
                return;
            }
            if (!target) return;
            var action = target.dataset.awAction;
            var id = target.dataset.awId;
            if (action === 'deleteBulletin') _agentWorkspacePost('deleteBulletin', { id: id });
            if (action === 'deleteTask') _agentWorkspacePost('deleteTask', { id: id });
            if (action === 'startTask') _agentWorkspacePost('startTask', { id: id });
            if (action === 'completeTask') _agentWorkspacePost('completeTask', { id: id });
            if (action === 'deleteNote') _agentWorkspacePost('deleteNote', { id: id });
            if (action === 'readFile') {
                _agentWorkspacePost('readFile', { path: target.dataset.awPath }).then(function() {
                    if (_agentWorkspace.data && _agentWorkspace.data.file) _agentWorkspace.data.fileEditor = _agentWorkspace.data.file;
                    _renderAgentWorkspace();
                });
            }
            if (action === 'deleteFile') {
    if (confirm(_tr('delete_path_confirm', { path: target.dataset.awPath }))) _agentWorkspacePost('deleteFile', { path: target.dataset.awPath });
            }
            if (action === 'closeFile') {
                if (_agentWorkspace.data) delete _agentWorkspace.data.fileEditor;
                _renderAgentWorkspace();
            }
            if (action === 'newNote') {
                if (_agentWorkspace.data) _agentWorkspace.data.selectedNoteId = '';
                _renderAgentWorkspace();
            }
            if (action === 'newAgentSkill') {
                if (_agentWorkspace.data) {
                    _agentWorkspace.data.skillEditor = { name: 'new-skill', content: '---\\nname: new-skill\\ndescription: \"Agent workflow skill.\"\\n---\\n\\n# New Skill\\n\\nUse this skill when...\\n' };
                    delete _agentWorkspace.data.librarySkillEditor;
                }
                _renderAgentWorkspace();
            }
            if (action === 'newLibrarySkill') {
                if (_agentWorkspace.data) {
                    _agentWorkspace.data.librarySkillEditor = { name: 'new-library-skill', content: '---\\nname: new-library-skill\\ndescription: \"Reusable Virtual Office skill.\"\\n---\\n\\n# New Library Skill\\n\\nUse this skill when...\\n' };
                    delete _agentWorkspace.data.skillEditor;
                }
                _renderAgentWorkspace();
            }
            if (action === 'deleteAgentSkill') {
    if (confirm(_tr('delete_skill_confirm', { name: id }))) _agentWorkspacePost('deleteAgentSkill', { name: id });
            }
            if (action === 'applyLibrarySkill') {
                _agentWorkspacePost('applyLibrarySkill', { name: id, overwrite: true });
            }
            if (action === 'refreshSkillWorkshop') {
                refreshSkillWorkshopQueue();
            }
            if (action === 'saveAgentSkillToLibrary') {
                var workspaceAgent = (_agentWorkspace.data && _agentWorkspace.data.agent) || _agentWorkspace.agent || {};
                var workspaceAgentKey = _agentWorkspaceKey(workspaceAgent);
                saveAgentSkillToLibrary(workspaceAgentKey, id, function() {
                    if (_agentWorkspace.agent) _loadAgentWorkspace(_agentWorkspace.agent);
                });
            }
        });
        body.addEventListener('input', function(e) {
            var search = e.target.closest('[data-aw-file-search]');
            if (!search || !_agentWorkspace.data) return;
            _agentWorkspace.data.fileSearch = search.value;
            clearTimeout(_agentWorkspace.fileSearchTimer);
            _agentWorkspace.fileSearchTimer = setTimeout(_renderAgentWorkspace, 120);
        });
        body.addEventListener('change', function(e) {
            var target = e.target.closest('[data-aw-action="toggleTask"]');
            if (target) _agentWorkspacePost('toggleTask', { id: target.dataset.awId });
            var mode = e.target.closest('[data-aw-action="setTaskMode"]');
            if (mode) _agentWorkspacePost('setTaskMode', { mode: mode.value });
        });
    }
    if (header) {
        header.addEventListener('pointerdown', function(e) {
            if (!panel || panel.classList.contains('maximized') || e.target.closest('button')) return;
            var rect = panel.getBoundingClientRect();
            panel.style.left = rect.left + 'px';
            panel.style.top = rect.top + 'px';
            panel.style.right = 'auto';
            _agentWorkspace.drag = { id: e.pointerId, x: e.clientX, y: e.clientY, left: rect.left, top: rect.top };
            header.setPointerCapture(e.pointerId);
        });
    }
    if (resizeHandle) {
        resizeHandle.addEventListener('pointerdown', function(e) {
            if (!panel || panel.classList.contains('maximized')) return;
            e.preventDefault();
            var rect = panel.getBoundingClientRect();
            _agentWorkspace.resize = { id: e.pointerId, x: e.clientX, y: e.clientY, w: rect.width, h: rect.height };
            resizeHandle.setPointerCapture(e.pointerId);
        });
    }
    document.addEventListener('pointermove', function(e) {
        if (_agentWorkspace.drag && panel) {
            var d = _agentWorkspace.drag;
            panel.style.left = (d.left + e.clientX - d.x) + 'px';
            panel.style.top = (d.top + e.clientY - d.y) + 'px';
            _clampAgentWorkspacePanel();
        }
        if (_agentWorkspace.resize && panel) {
            var r = _agentWorkspace.resize;
            panel.style.width = Math.max(360, Math.min(window.innerWidth - 16, r.w + e.clientX - r.x)) + 'px';
            panel.style.height = Math.max(320, Math.min(window.innerHeight - 16, r.h + e.clientY - r.y)) + 'px';
        }
    });
    document.addEventListener('pointerup', function() {
        _agentWorkspace.drag = null;
        _agentWorkspace.resize = null;
    });
    document.addEventListener('click', function(e) {
        var menu = document.getElementById('agent-workspace-menu');
        if (menu && !menu.classList.contains('hidden') && !menu.contains(e.target)) _hideAgentWorkspaceMenu();
    });
    window.addEventListener('resize', _clampAgentWorkspacePanel);
}

_initAgentWorkspaceUI();

async function clearNotifyOnServer(statusKey) {
    try {
        await fetch('/clear-notify', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ agent: statusKey })
        });
    } catch(e) { /* best effort */ }
}

function closeModal() {
    document.getElementById('agentModal').classList.add('hidden');
    selectedAgent = null;
}

function overrideAgent(state) {
    if (selectedAgent) {
        selectedAgent.moveTo(state);
        addGlobalLog(`🎮 Override: ${selectedAgent.name} → ${state}`);
        closeModal();
    }
}

function setGlobalState(state) {
    agents.forEach(agent => agent.moveTo(state));
    addGlobalLog(`🎮 All agents → ${state}`);
}

Object.assign(window, {
    _openAgentWorkspace,
    _initAgentWorkspaceUI,
    _loadAgentWorkspace,
    _renderAgentWorkspace,
    _hideAgentWorkspaceMenu,
    clearNotifyOnServer,
    closeModal,
    overrideAgent,
    setGlobalState
});
