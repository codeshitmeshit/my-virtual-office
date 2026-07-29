(function(global) {
    'use strict';

    var state = {
        data: {
            skills: [],
            categories: [],
            organization: null,
            archiveManager: {},
            organizationEnabled: false
        },
        categoryId: 'all',
        selectedSlug: '',
        search: '',
        starting: false
    };

    function byId(id) {
        return document.getElementById(id);
    }

    function skills() {
        return Array.isArray(state.data.skills) ? state.data.skills : [];
    }

    function categories() {
        return Array.isArray(state.data.categories) ? state.data.categories : [];
    }

    function categoryName(categoryId) {
        var category = categories().find(function(item) {
            return item.id === categoryId;
        });
        return category ? category.name : '默认标签';
    }

    function categoryCount(categoryId) {
        if (categoryId === 'all') return skills().length;
        return skills().filter(function(skill) {
            return (skill.primaryCategoryId || 'default') === categoryId;
        }).length;
    }

    function visibleSkills() {
        var query = state.search.trim().toLocaleLowerCase();
        return skills().filter(function(skill) {
            var inCategory = state.categoryId === 'all' ||
                (skill.primaryCategoryId || 'default') === state.categoryId;
            if (!inCategory) return false;
            if (!query) return true;
            return [skill.name, skill.description]
                .join(' ')
                .toLocaleLowerCase()
                .indexOf(query) >= 0;
        }).sort(function(left, right) {
            return String(left.name || '').localeCompare(String(right.name || ''));
        });
    }

    function renderCategories() {
        var container = byId('skl-category-list');
        if (!container) return;
        container.replaceChildren();
        var items = [{ id: 'all', name: '全部技能' }].concat(categories());
        items.forEach(function(category) {
            var button = document.createElement('button');
            button.type = 'button';
            button.className = 'skl-category-item' +
                (state.categoryId === category.id ? ' is-active' : '');
            button.setAttribute('aria-pressed', state.categoryId === category.id ? 'true' : 'false');
            var name = document.createElement('span');
            name.textContent = category.name;
            var count = document.createElement('span');
            count.className = 'skl-category-count';
            count.textContent = String(categoryCount(category.id));
            button.append(name, count);
            button.addEventListener('click', function() {
                state.categoryId = category.id;
                state.selectedSlug = '';
                render();
            });
            container.appendChild(button);
        });
    }

    function renderCards() {
        var container = byId('skl-cards');
        if (!container) return;
        var visible = visibleSkills();
        var title = byId('skl-list-title');
        var count = byId('skl-list-count');
        if (title) {
            title.textContent = state.categoryId === 'all'
                ? '全部技能'
                : categoryName(state.categoryId);
        }
        if (count) count.textContent = String(visible.length);
        container.replaceChildren();
        if (!visible.length) {
            var empty = document.createElement('div');
            empty.className = 'skl-empty';
            empty.textContent = state.search ? '没有匹配的技能' : '这个分类中还没有技能';
            container.appendChild(empty);
            return;
        }
        if (!visible.some(function(skill) { return skill.name === state.selectedSlug; })) {
            state.selectedSlug = visible[0].name || '';
        }
        visible.forEach(function(skill) {
            var card = document.createElement('button');
            card.type = 'button';
            card.className = 'skl-card' +
                (skill.name === state.selectedSlug ? ' is-selected' : '');
            card.setAttribute('data-skill-slug', skill.name || '');
            var name = document.createElement('div');
            name.className = 'skl-card-name';
            name.textContent = skill.name || '';
            var description = document.createElement('div');
            description.className = 'skl-card-desc';
            description.textContent = skill.description || '暂无描述';
            var category = document.createElement('span');
            category.className = 'skl-card-category';
            category.textContent = categoryName(skill.primaryCategoryId || 'default');
            card.append(name, description, category);
            card.addEventListener('click', function() {
                state.selectedSlug = skill.name || '';
                renderCards();
                renderDetail();
            });
            container.appendChild(card);
        });
    }

    function detailField(label, value) {
        var field = document.createElement('div');
        field.className = 'skl-detail-field';
        var name = document.createElement('span');
        name.className = 'skl-detail-label';
        name.textContent = label;
        var content = document.createElement('div');
        content.className = 'skl-detail-value';
        content.textContent = value;
        field.append(name, content);
        return field;
    }

    function renderDetail() {
        var container = byId('skl-detail');
        if (!container) return;
        var skill = skills().find(function(item) {
            return item.name === state.selectedSlug;
        });
        container.replaceChildren();
        if (!skill) {
            var empty = document.createElement('div');
            empty.className = 'skl-detail-empty';
            empty.textContent = '选择一个技能查看详情';
            container.appendChild(empty);
            return;
        }
        var title = document.createElement('h3');
        title.className = 'skl-detail-title';
        title.textContent = skill.name || '';
        var description = document.createElement('p');
        description.className = 'skl-detail-description';
        description.textContent = skill.description || '暂无描述';
        container.append(
            title,
            description,
            detailField('来源', '本地技能库'),
            detailField('主分类', categoryName(skill.primaryCategoryId || 'default'))
        );
        var tagsField = document.createElement('div');
        tagsField.className = 'skl-detail-field';
        var tagsLabel = document.createElement('span');
        tagsLabel.className = 'skl-detail-label';
        tagsLabel.textContent = '标签';
        var tagList = document.createElement('div');
        tagList.className = 'skl-tag-list';
        var tags = Array.isArray(skill.tags) ? skill.tags : [];
        if (!tags.length) {
            tagList.className = 'skl-detail-value';
            tagList.textContent = '暂无标签';
        } else {
            tags.forEach(function(tag) {
                var chip = document.createElement('span');
                chip.className = 'skl-tag';
                chip.textContent = tag;
                tagList.appendChild(chip);
            });
        }
        tagsField.append(tagsLabel, tagList);
        container.appendChild(tagsField);

        var actions = document.createElement('div');
        actions.className = 'skl-detail-actions';
        [
            ['应用到 AI', function() { global.toggleSkillApply(skill.name); }],
            ['编辑', function() { global.openSkillEditor(skill.name); }],
            ['删除', function() { global.deleteLibrarySkill(skill.name); }]
        ].forEach(function(action) {
            var button = document.createElement('button');
            button.type = 'button';
            button.textContent = action[0];
            button.addEventListener('click', action[1]);
            actions.appendChild(button);
        });
        var apply = document.createElement('div');
        apply.className = 'skl-apply-dropdown';
        apply.id = 'skl-apply-' + skill.name;
        apply.style.display = 'none';
        container.append(actions, apply);
    }

    function updateOrganizeButton() {
        var button = byId('skl-organize-btn');
        if (!button) return;
        var manager = state.data.archiveManager || {};
        var defaultCount = categoryCount('default');
        var disabledReason = '';
        if (!state.data.organizationEnabled) disabledReason = '智能整理当前未启用';
        else if (manager.status === 'working' || manager.activeWork) disabledReason = '档案管理员正在处理其他工作';
        else if (['missing', 'error', 'offline', 'unavailable', 'paused'].indexOf(manager.status) >= 0) disabledReason = '档案管理员当前不可用';
        else if (!defaultCount) disabledReason = '默认标签中没有需要整理的技能';
        button.disabled = Boolean(disabledReason || state.starting);
        button.title = disabledReason;
        button.setAttribute('aria-disabled', button.disabled ? 'true' : 'false');
    }

    function render() {
        renderCategories();
        renderCards();
        renderDetail();
        updateOrganizeButton();
    }

    function update(data) {
        state.data = data || {};
        render();
    }

    async function startOrganization() {
        if (state.starting) return;
        var button = byId('skl-organize-btn');
        if (button && button.disabled) return;
        state.starting = true;
        updateOrganizeButton();
        try {
            var request = global.i18n && global.i18n.managementFetch
                ? global.i18n.managementFetch.bind(global.i18n)
                : global.fetch.bind(global);
            var response = await request('/api/skills-library/organization/runs', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: '{}'
            });
            var result = await response.json();
            if (!response.ok) throw new Error(result.error || '智能整理启动失败');
            if (typeof global.refreshSkillsList === 'function') {
                await global.refreshSkillsList();
            }
        } catch (error) {
            var toast = global._showOfficeToast || global._acpShowToast;
            if (toast) toast('❌ ' + error.message);
        } finally {
            state.starting = false;
            updateOrganizeButton();
        }
    }

    function init() {
        var input = byId('skl-search-input');
        if (input) {
            input.addEventListener('input', function() {
                state.search = input.value || '';
                state.selectedSlug = '';
                render();
            });
        }
    }

    global.SkillLibraryOrganizationUI = {
        state: state,
        init: init,
        update: update,
        render: render,
        startOrganization: startOrganization
    };
    init();
})(window);
