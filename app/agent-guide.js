(function () {
    'use strict';

    var activeCategory = 'all';
    var skills = [];
    var skillContentCache = {};
    var skillLoadPromise = null;
    var skillsLoading = false;
    var skillsLoadError = '';

    // Source boundary: discover only the VO-owned exposed catalog served by the
    // current local project. Category is UI grouping metadata; skill content
    // itself is parsed from the project SKILL.md files at runtime.
    var categoryById = {
        'vo-operating-guidelines': 'operations',
        'vo-agent-communication': 'communication',
        'vo-codex-communication': 'communication',
        'vo-browser-control': 'browser',
        'vo-agent-workspace': 'workspace',
        'vo-project-workflow': 'workflow',
        'vo-meeting-execution': 'meeting'
    };

    var fallbackSkillPaths = Object.keys(categoryById).map(function (id) {
        return '/skills/' + id + '/SKILL.md';
    });

    var categories = [
        { id: 'all', labelKey: 'agent_guide_cat_all' },
        { id: 'operations', labelKey: 'agent_guide_cat_operations' },
        { id: 'communication', labelKey: 'agent_guide_cat_communication' },
        { id: 'browser', labelKey: 'agent_guide_cat_browser' },
        { id: 'workspace', labelKey: 'agent_guide_cat_workspace' },
        { id: 'workflow', labelKey: 'agent_guide_cat_workflow' },
        { id: 'meeting', labelKey: 'agent_guide_cat_meeting' }
    ];

    function t(key) {
        if (window.i18n && typeof window.i18n.t === 'function') return window.i18n.t(key);
        return key;
    }

    function esc(value) {
        return String(value == null ? '' : value)
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;')
            .replace(/'/g, '&#39;');
    }

    function categoryLabel(categoryId) {
        var item = categories.find(function (cat) { return cat.id === categoryId; });
        return item ? t(item.labelKey) : categoryId;
    }

    function idFromPath(path) {
        var match = String(path || '').match(/\/skills\/([^/]+)\/SKILL\.md$/);
        return match ? match[1] : '';
    }

    function parseCatalog(content) {
        var paths = [];
        String(content || '').replace(/\/skills\/vo-[a-z0-9-]+\/SKILL\.md/g, function (path) {
            if (!paths.includes(path)) paths.push(path);
            return path;
        });
        return paths;
    }

    function parseFrontmatter(content) {
        var data = {};
        var match = String(content || '').match(/^---\n([\s\S]*?)\n---/);
        if (!match) return data;
        match[1].split('\n').forEach(function (line) {
            var idx = line.indexOf(':');
            if (idx <= 0) return;
            var key = line.slice(0, idx).trim();
            var value = line.slice(idx + 1).trim();
            data[key] = value.replace(/^["']|["']$/g, '');
        });
        return data;
    }

    function parseSkill(path, content) {
        var id = idFromPath(path);
        var frontmatter = parseFrontmatter(content);
        var titleMatch = String(content || '').match(/^#\s+(.+)$/m);
        var sections = [];
        String(content || '').replace(/^##\s+(.+)$/gm, function (_full, title) {
            var text = String(title || '').trim();
            if (text && !sections.includes(text)) sections.push(text);
            return _full;
        });
        return {
            id: id,
            category: categoryById[id] || 'operations',
            path: path,
            title: (titleMatch && titleMatch[1] ? titleMatch[1].trim() : '') || frontmatter.name || id,
            description: frontmatter.description || t('agent_guide_no_description'),
            sections: sections.slice(0, 8),
            content: content || ''
        };
    }

    async function fetchText(path) {
        var res = await fetch(path, { cache: 'no-store' });
        var text = await res.text();
        if (!res.ok) throw new Error(text || res.statusText || String(res.status));
        return text;
    }

    async function loadSkills() {
        if (skillLoadPromise) return skillLoadPromise;
        skillsLoading = true;
        skillsLoadError = '';
        renderCards();
        skillLoadPromise = (async function () {
            var catalogText = '';
            var paths = fallbackSkillPaths.slice();
            try {
                catalogText = await fetchText('/skills/catalog.md');
                paths = parseCatalog(catalogText);
                if (!paths.length) paths = fallbackSkillPaths.slice();
            } catch (_err) {
                paths = fallbackSkillPaths.slice();
            }

            var loaded = [];
            for (var i = 0; i < paths.length; i += 1) {
                var path = paths[i];
                var content = await fetchText(path);
                skillContentCache[path] = content;
                loaded.push(parseSkill(path, content));
            }
            skills = loaded;
            skillsLoading = false;
            render();
            return skills;
        })().catch(function (err) {
            skillsLoading = false;
            skillsLoadError = err && err.message ? err.message : String(err);
            renderCards();
            return [];
        });
        return skillLoadPromise;
    }

    function filteredSkills() {
        if (activeCategory === 'all') return skills.slice();
        return skills.filter(function (skill) { return skill.category === activeCategory; });
    }

    function findSkill(skillId) {
        return skills.find(function (skill) { return skill.id === skillId; }) || null;
    }

    function renderFilters() {
        var root = document.getElementById('agent-guide-filters');
        if (!root) return;
        root.innerHTML = categories.map(function (cat) {
            var active = cat.id === activeCategory ? ' active' : '';
            var selected = cat.id === activeCategory ? 'true' : 'false';
            return '<button type="button" class="agent-guide-filter' + active + '" role="tab" aria-selected="' + selected + '" data-agent-guide-category="' + esc(cat.id) + '">' + esc(t(cat.labelKey)) + '</button>';
        }).join('');
    }

    function renderCards() {
        var root = document.getElementById('agent-guide-cards');
        var empty = document.getElementById('agent-guide-empty');
        if (!root) return;

        if (skillsLoading) {
            root.innerHTML = '<div class="agent-guide-empty">' + esc(t('agent_guide_loading')) + '</div>';
            if (empty) empty.classList.add('hidden');
            return;
        }

        if (skillsLoadError) {
            root.innerHTML = '<div class="agent-guide-skill-detail-error">' + esc(t('agent_guide_skill_detail_error')) + ': ' + esc(skillsLoadError) + '</div>';
            if (empty) empty.classList.add('hidden');
            return;
        }

        var visible = filteredSkills();
        root.innerHTML = visible.map(function (skill) {
            var sections = (skill.sections || []).map(function (section) {
                return '<li>' + esc(section) + '</li>';
            }).join('');
            return [
                '<article class="agent-guide-card" data-agent-guide-skill="' + esc(skill.id) + '" data-agent-guide-category="' + esc(skill.category) + '" role="button" tabindex="0" aria-label="' + esc(t('agent_guide_open_skill')) + ' ' + esc(skill.title) + '">',
                '  <div class="agent-guide-card-head">',
                '    <div class="agent-guide-skill-name">' + esc(skill.title) + '</div>',
                '    <div class="agent-guide-category-badge">' + esc(categoryLabel(skill.category)) + '</div>',
                '  </div>',
                '  <div class="agent-guide-field">',
                '    <div class="agent-guide-field-label">' + esc(t('agent_guide_purpose_label')) + '</div>',
                '    <div class="agent-guide-field-text">' + esc(skill.description) + '</div>',
                '  </div>',
                '  <div class="agent-guide-field">',
                '    <div class="agent-guide-field-label">' + esc(t('agent_guide_source_label')) + '</div>',
                '    <div class="agent-guide-field-text agent-guide-source-path">' + esc(skill.path) + '</div>',
                '  </div>',
                sections ? [
                    '  <div class="agent-guide-details">',
                    '    <div class="agent-guide-field-label">' + esc(t('agent_guide_sections_label')) + '</div>',
                    '    <ul class="agent-guide-detail-list">' + sections + '</ul>',
                    '  </div>'
                ].join('') : '',
                '  <button type="button" class="agent-guide-open-skill" data-agent-guide-open-skill="' + esc(skill.id) + '">' + esc(t('agent_guide_open_skill')) + '</button>',
                '</article>'
            ].join('');
        }).join('');

        if (empty) empty.classList.toggle('hidden', visible.length > 0);
    }

    function render() {
        renderFilters();
        renderCards();
    }

    function openAgentGuide() {
        var modal = document.getElementById('agentGuideModal');
        if (!modal) return;
        modal.classList.remove('hidden');
        render();
        loadSkills();
    }

    function closeAgentGuide() {
        var modal = document.getElementById('agentGuideModal');
        if (modal) modal.classList.add('hidden');
        closeAgentGuideSkillDetail();
    }

    function closeAgentGuideSkillDetail() {
        var modal = document.getElementById('agentGuideSkillDetailModal');
        if (modal) modal.classList.add('hidden');
    }

    async function openAgentGuideSkillDetail(skillId) {
        if (!skills.length) await loadSkills();
        var skill = findSkill(skillId);
        var modal = document.getElementById('agentGuideSkillDetailModal');
        var title = document.getElementById('agent-guide-skill-detail-title');
        var path = document.getElementById('agent-guide-skill-detail-path');
        var content = document.getElementById('agent-guide-skill-detail-content');
        var error = document.getElementById('agent-guide-skill-detail-error');
        if (!skill || !modal || !title || !path || !content || !error) return;

        title.textContent = skill.title;
        path.textContent = skill.path;
        content.textContent = t('agent_guide_skill_detail_loading');
        error.textContent = '';
        error.classList.add('hidden');
        modal.classList.remove('hidden');

        try {
            var text = skillContentCache[skill.path] || await fetchText(skill.path);
            skillContentCache[skill.path] = text;
            content.textContent = text;
        } catch (err) {
            content.textContent = '';
            error.textContent = t('agent_guide_skill_detail_error') + ': ' + (err && err.message ? err.message : String(err));
            error.classList.remove('hidden');
        }
    }

    function setCategory(category) {
        if (!categories.some(function (cat) { return cat.id === category; })) return;
        activeCategory = category;
        render();
    }

    document.addEventListener('click', function (event) {
        var openTarget = event.target && event.target.closest ? event.target.closest('[data-agent-guide-open-skill], .agent-guide-card') : null;
        if (openTarget) {
            var skillId = openTarget.getAttribute('data-agent-guide-open-skill') || openTarget.getAttribute('data-agent-guide-skill');
            if (skillId) {
                event.preventDefault();
                openAgentGuideSkillDetail(skillId);
                return;
            }
        }

        var btn = event.target && event.target.closest ? event.target.closest('[data-agent-guide-category]') : null;
        if (!btn) return;
        setCategory(btn.getAttribute('data-agent-guide-category'));
    });

    document.addEventListener('keydown', function (event) {
        if (event.key !== 'Enter' && event.key !== ' ') return;
        var card = event.target && event.target.closest ? event.target.closest('.agent-guide-card') : null;
        if (!card || event.target !== card) return;
        var skillId = card.getAttribute('data-agent-guide-skill');
        if (!skillId) return;
        event.preventDefault();
        openAgentGuideSkillDetail(skillId);
    });

    window.addEventListener('i18n:ready', render);
    window.addEventListener('i18n:changed', render);

    window.openAgentGuide = openAgentGuide;
    window.closeAgentGuide = closeAgentGuide;
    window.closeAgentGuideSkillDetail = closeAgentGuideSkillDetail;
    window.AgentGuide = {
        getSkills: function () { return skills.slice(); },
        getCategories: function () { return categories.slice(); },
        loadSkills: loadSkills,
        openSkillDetail: openAgentGuideSkillDetail,
        render: render,
        setCategory: setCategory
    };
})();
