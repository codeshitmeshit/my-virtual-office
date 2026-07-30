(function(global) {
    'use strict';

    function normalize(value) {
        return String(value || '').trim().toLowerCase();
    }

    function agentKey(agent) {
        return String((agent && (agent.id || agent.agentId || agent.key || agent.statusKey)) || '');
    }

    function branchId(agent, branches, translate) {
        var raw = String((agent && (agent.branch || agent.branchId)) || '');
        var token = normalize(raw);
        var matched = branches.find(function(branch) {
            return branch.id === raw ||
                normalize(branch.id) === token ||
                normalize(branch.name) === token;
        });
        if (matched) return String(matched.id);
        var unassigned = normalize(translate('branch_unassigned', '未分配'));
        if (!token || token === 'unassigned' || token === unassigned) return 'UNASSIGNED';
        var provider = normalize(agent && agent.providerKind);
        var providerBranch = branches.find(function(branch) {
            return normalize(branch.id) === provider || normalize(branch.name) === provider;
        });
        return providerBranch ? String(providerBranch.id) : 'UNASSIGNED';
    }

    function branchLabel(branch, translate) {
        var name = branch.id === 'UNASSIGNED'
            ? translate('branch_unassigned', '未分配')
            : (branch.name || branch.id);
        if (String(name).indexOf('branch_') === 0) {
            name = translate(name, branch.id || name);
        }
        return (branch.emoji || (branch.id === 'UNASSIGNED' ? '❓' : '🏢')) + ' ' + name;
    }

    function assignable(agent, supportedProviders) {
        if (!agent || agent.assignable === false || agent.systemRole === 'archive_manager' || agent.archiveManager) {
            return false;
        }
        if (!supportedProviders || !supportedProviders.length) return true;
        return supportedProviders.indexOf(normalize(agent.providerKind || 'openclaw')) >= 0;
    }

    function render(options) {
        var escape = options.escape;
        var translate = options.translate;
        var branches = (options.branches || []).map(function(branch) {
            return {
                id: String(branch.id || 'UNASSIGNED'),
                name: branch.name,
                emoji: branch.emoji
            };
        });
        if (!branches.some(function(branch) { return branch.id === 'UNASSIGNED'; })) {
            branches.push({ id: 'UNASSIGNED', name: 'UNASSIGNED', emoji: '❓' });
        }
        var agents = (options.agents || []).filter(function(agent) {
            return assignable(agent, options.supportedProviders);
        });
        var selected = new Set((options.selectedIds || []).map(String));
        var byBranch = {};
        branches.forEach(function(branch) { byBranch[branch.id] = []; });
        agents.forEach(function(agent) {
            var id = branchId(agent, branches, translate);
            if (!byBranch[id]) byBranch[id] = [];
            byBranch[id].push(agent);
        });
        var branchInputs = branches.map(function(branch) {
            var branchAgents = byBranch[branch.id] || [];
            if (!branchAgents.length) return '';
            return '<label class="branch-agent-selector-option">' +
                '<input type="checkbox" class="' + escape(options.branchInputClass) + '" data-branch-id="' + escape(branch.id) + '"' + options.scopeAttributes + '> ' +
                escape(branchLabel(branch, translate)) +
            '</label>';
        }).join('');
        var agentGroups = branches.map(function(branch) {
            var branchAgents = byBranch[branch.id] || [];
            if (!branchAgents.length) return '';
            var inputs = branchAgents.map(function(agent) {
                var id = agentKey(agent);
                return '<label class="branch-agent-selector-option">' +
                    '<input type="checkbox" class="' + escape(options.agentInputClass) + '" data-branch-id="' + escape(branch.id) + '" value="' + escape(id) + '"' +
                        options.scopeAttributes + (selected.has(id) ? ' checked' : '') + '> ' +
                    escape((agent.emoji || '🤖') + ' ' + (agent.name || id)) +
                '</label>';
            }).join('');
            return '<div class="branch-agent-selector-group" data-branch-id="' + escape(branch.id) + '">' +
                '<div class="branch-agent-selector-group-title">' + escape(branchLabel(branch, translate)) + '</div>' +
                '<div class="branch-agent-selector-options">' + inputs + '</div>' +
            '</div>';
        }).join('');
        if (!agents.length) {
            return '<div class="branch-agent-selector-empty">' + escape(options.emptyLabel) + '</div>';
        }
        return '<div class="branch-agent-selector">' +
            '<div class="branch-agent-selector-label">' + escape(options.quickSelectLabel) + '</div>' +
            '<div class="branch-agent-selector-branches">' + branchInputs + '</div>' +
            '<div class="branch-agent-selector-hint">' + escape(options.hintLabel) + '</div>' +
            '<div class="branch-agent-selector-agents">' + agentGroups + '</div>' +
        '</div>';
    }

    function applyBranch(root, branchInput, agentSelector) {
        var branch = branchInput.getAttribute('data-branch-id') || '';
        root.querySelectorAll(agentSelector).forEach(function(input) {
            if ((input.getAttribute('data-branch-id') || '') === branch) {
                input.checked = branchInput.checked;
            }
        });
    }

    function syncBranches(root, branchSelector, agentSelector) {
        root.querySelectorAll(branchSelector).forEach(function(branchInput) {
            var branch = branchInput.getAttribute('data-branch-id') || '';
            var inputs = Array.prototype.slice.call(root.querySelectorAll(agentSelector)).filter(function(input) {
                return (input.getAttribute('data-branch-id') || '') === branch;
            });
            var checked = inputs.filter(function(input) { return input.checked; }).length;
            branchInput.checked = inputs.length > 0 && checked === inputs.length;
            branchInput.indeterminate = checked > 0 && checked < inputs.length;
        });
    }

    global.AgentBranchSelector = {
        render: render,
        applyBranch: applyBranch,
        syncBranches: syncBranches
    };
})(window);
