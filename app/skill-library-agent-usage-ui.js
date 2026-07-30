(function(global) {
    'use strict';

    function createAgentUsageField(skill, options) {
        var tr = options.translate;
        var agents = Array.isArray(skill && skill.loadedAgents)
            ? skill.loadedAgents
            : [];
        var field = document.createElement('div');
        field.className = 'skl-detail-field skl-agent-usage';

        var label = document.createElement('span');
        label.className = 'skl-detail-label';
        label.textContent = tr(
            'skill_library_loaded_agents',
            { count: agents.length },
            '已加载 Agent（' + agents.length + '）'
        );
        field.appendChild(label);

        if (!agents.length) {
            var empty = document.createElement('div');
            empty.className = 'skl-detail-value skl-agent-usage-empty';
            empty.textContent = tr(
                'skill_library_no_loaded_agents',
                null,
                '暂未被任何 Agent 加载'
            );
            field.appendChild(empty);
            return field;
        }

        var groups = new Map();
        agents.forEach(function(agent) {
            var branch = String(agent.branch || '').trim() ||
                tr('branch_unassigned', null, '未分配');
            if (!groups.has(branch)) groups.set(branch, []);
            groups.get(branch).push(agent);
        });

        var groupList = document.createElement('div');
        groupList.className = 'skl-agent-usage-groups';
        groups.forEach(function(branchAgents, branch) {
            var group = document.createElement('div');
            group.className = 'skl-agent-usage-group';
            var groupTitle = document.createElement('div');
            groupTitle.className = 'skl-agent-usage-branch';
            groupTitle.textContent = branch;
            var chips = document.createElement('div');
            chips.className = 'skl-agent-usage-chips';
            branchAgents.forEach(function(agent) {
                var chip = document.createElement('span');
                chip.className = 'skl-agent-usage-chip';
                chip.textContent = (agent.emoji || '🤖') + ' ' +
                    (agent.name || agent.id || '');
                chip.title = agent.providerKind || '';
                chips.appendChild(chip);
            });
            group.append(groupTitle, chips);
            groupList.appendChild(group);
        });
        field.appendChild(groupList);
        return field;
    }

    global.SkillLibraryAgentUsageUI = {
        createField: createAgentUsageField
    };
})(window);
