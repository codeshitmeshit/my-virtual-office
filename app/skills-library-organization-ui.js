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
        failureOnly: false,
        starting: false,
        dismissing: false,
        moving: false,
        pollTimer: null
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

    function failureSlugs() {
        var organization = state.data.organization || {};
        return new Set((Array.isArray(organization.failures) ? organization.failures : [])
            .map(function(failure) { return failure.slug || failure.skillName || failure.name || ''; })
            .filter(Boolean));
    }

    function visibleSkills() {
        var query = state.search.trim().toLocaleLowerCase();
        var failed = failureSlugs();
        return skills().filter(function(skill) {
            var inCategory = state.categoryId === 'all' ||
                (skill.primaryCategoryId || 'default') === state.categoryId;
            if (!inCategory) return false;
            if (state.failureOnly && !failed.has(skill.name)) return false;
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
                state.failureOnly = false;
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
            title.textContent = state.failureOnly
                ? '归类失败'
                : state.categoryId === 'all'
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
            if (failureSlugs().has(skill.name)) {
                var failureBadge = document.createElement('span');
                failureBadge.className = 'skl-failure-badge';
                failureBadge.textContent = '归类失败';
                card.appendChild(failureBadge);
            }
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

        var categoryControl = document.createElement('div');
        categoryControl.className = 'skl-category-control';
        var categorySelect = document.createElement('select');
        categorySelect.id = 'skl-category-select';
        categorySelect.className = 'skl-category-select';
        categorySelect.setAttribute('aria-label', '调整主分类');
        categories().forEach(function(category) {
            var option = document.createElement('option');
            option.value = category.id;
            option.textContent = category.name;
            categorySelect.appendChild(option);
        });
        categorySelect.value = skill.primaryCategoryId || 'default';
        var moveButton = document.createElement('button');
        moveButton.id = 'skl-category-move';
        moveButton.type = 'button';
        moveButton.className = 'skl-category-move';
        moveButton.textContent = state.moving ? '移动中…' : '移动';
        var organizationRunning =
            (state.data.organization || {}).status === 'running';
        categorySelect.disabled = organizationRunning || state.moving;
        moveButton.disabled = organizationRunning || state.moving;
        moveButton.addEventListener('click', function() {
            moveSelectedSkill(categorySelect.value);
        });
        categoryControl.append(categorySelect, moveButton);
        container.appendChild(categoryControl);

        var actions = document.createElement('div');
        actions.className = 'skl-detail-actions';
        [
            ['应用到 AI', false, function() { global.toggleSkillApply(skill.name); }],
            ['编辑', true, function() { global.openSkillEditor(skill.name); }],
            ['删除', true, function() { global.deleteLibrarySkill(skill.name); }]
        ].forEach(function(action) {
            var button = document.createElement('button');
            button.type = 'button';
            button.textContent = action[0];
            button.disabled = organizationRunning && action[1];
            button.addEventListener('click', action[2]);
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
        var organization = state.data.organization || {};
        if (!state.data.organizationEnabled) disabledReason = '智能整理当前未启用';
        else if (organization.status === 'running') disabledReason = '档案管理员正在整理技能库';
        else if (manager.status === 'working' || manager.activeWork) disabledReason = '档案管理员正在处理其他工作';
        else if (['missing', 'error', 'offline', 'unavailable', 'paused'].indexOf(manager.status) >= 0) disabledReason = '档案管理员当前不可用';
        else if (!defaultCount) disabledReason = '默认标签中没有需要整理的技能';
        button.disabled = Boolean(disabledReason || state.starting);
        button.title = disabledReason;
        button.setAttribute('aria-disabled', button.disabled ? 'true' : 'false');
    }

    function markerCopy(organization) {
        var failures = Number(organization.failureCount || 0);
        if (organization.status === 'running') {
            return { tone: 'running', text: '档案管理员正在整理技能库…', dismissible: false };
        }
        if (organization.status === 'completed') {
            return { tone: 'completed', text: '技能整理已完成', dismissible: true };
        }
        if (organization.status === 'resolved') {
            return { tone: 'resolved', text: '归类失败项已全部处理', dismissible: true };
        }
        if (organization.status === 'partial') {
            return {
                tone: 'partial',
                text: '技能整理完成，' + failures + ' 个归类失败',
                dismissible: true,
                opensFailures: failures > 0
            };
        }
        if (organization.status === 'failed') {
            return {
                tone: 'partial',
                text: failures ? '技能整理未完成，' + failures + ' 个归类失败' : '技能整理未完成',
                dismissible: true,
                opensFailures: failures > 0
            };
        }
        return null;
    }

    function renderMarker() {
        var marker = byId('skl-organization-marker');
        if (!marker) return;
        var organization = state.data.organization;
        var copy = organization && !organization.dismissedAt ? markerCopy(organization) : null;
        marker.replaceChildren();
        marker.className = 'skl-organization-marker';
        if (!copy) {
            marker.classList.add('hidden');
            return;
        }
        marker.classList.add('is-' + copy.tone);
        var text = document.createElement(copy.opensFailures ? 'button' : 'span');
        text.className = 'skl-marker-text';
        text.textContent = copy.text;
        if (copy.opensFailures) {
            text.type = 'button';
            text.className += ' skl-marker-open';
            text.addEventListener('click', openFailures);
        }
        marker.appendChild(text);
        if (copy.dismissible) {
            var dismiss = document.createElement('button');
            dismiss.type = 'button';
            dismiss.className = 'skl-marker-dismiss';
            dismiss.textContent = '关闭';
            dismiss.setAttribute('aria-label', '关闭整理结果');
            dismiss.disabled = state.dismissing;
            dismiss.addEventListener('click', dismissMarker);
            marker.appendChild(dismiss);
        }
    }

    function stopPolling() {
        if (state.pollTimer !== null) {
            global.clearTimeout(state.pollTimer);
            state.pollTimer = null;
        }
    }

    function modalIsOpen() {
        var modal = byId('skillsLibraryModal');
        return Boolean(modal && !modal.classList.contains('hidden'));
    }

    function syncPolling() {
        stopPolling();
        var organization = state.data.organization || {};
        if (organization.status !== 'running' || !modalIsOpen()) return;
        state.pollTimer = global.setTimeout(async function() {
            state.pollTimer = null;
            if (typeof global.refreshSkillsList === 'function') {
                await global.refreshSkillsList();
            }
            if ((state.data.organization || {}).status === 'running') {
                syncPolling();
            }
        }, 2000);
    }

    function render() {
        renderMarker();
        renderCategories();
        renderCards();
        renderDetail();
        updateOrganizeButton();
        syncPolling();
    }

    function update(data) {
        state.data = data || {};
        if (!failureSlugs().size) state.failureOnly = false;
        render();
    }

    function openFailures() {
        state.categoryId = 'default';
        state.failureOnly = true;
        state.selectedSlug = '';
        render();
    }

    async function moveSelectedSkill(targetCategoryId) {
        var skill = skills().find(function(item) {
            return item.name === state.selectedSlug;
        });
        var organization = state.data.organization || {};
        if (
            state.moving ||
            !skill ||
            organization.status === 'running' ||
            !targetCategoryId ||
            targetCategoryId === (skill.primaryCategoryId || 'default')
        ) return;
        state.moving = true;
        renderDetail();
        try {
            var request = global.i18n && global.i18n.managementFetch
                ? global.i18n.managementFetch.bind(global.i18n)
                : global.fetch.bind(global);
            var response = await request(
                '/api/skills-library/' + encodeURIComponent(skill.name) + '/category',
                {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        categoryId: targetCategoryId,
                        expectedRevision: state.data.catalogRevision
                    })
                }
            );
            var result = await response.json();
            if (!response.ok) {
                if (
                    result.code === 'catalog_revision_conflict' &&
                    typeof global.refreshSkillsList === 'function'
                ) {
                    await global.refreshSkillsList();
                }
                throw new Error(result.error || '调整技能分类失败');
            }
            skill.primaryCategoryId =
                (result.metadata || {}).primaryCategoryId || targetCategoryId;
            if (Array.isArray((result.metadata || {}).tags)) {
                skill.tags = result.metadata.tags;
            }
            if (result.catalogRevision !== undefined) {
                state.data.catalogRevision = result.catalogRevision;
            }
            if (result.organization) {
                state.data.organization = result.organization;
            }
            if (!failureSlugs().size) state.failureOnly = false;
            render();
            if (typeof global.refreshSkillsList === 'function') {
                await global.refreshSkillsList();
            }
        } catch (error) {
            var toast = global._showOfficeToast || global._acpShowToast;
            if (toast) toast('❌ ' + error.message);
        } finally {
            state.moving = false;
            render();
        }
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
            state.data.organization = result;
            render();
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

    async function dismissMarker() {
        if (state.dismissing) return;
        state.dismissing = true;
        renderMarker();
        try {
            var request = global.i18n && global.i18n.managementFetch
                ? global.i18n.managementFetch.bind(global.i18n)
                : global.fetch.bind(global);
            var response = await request('/api/skills-library/organization/dismiss', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: '{}'
            });
            var result = await response.json();
            if (!response.ok) throw new Error(result.error || '关闭整理结果失败');
            if (state.data.organization) {
                state.data.organization.dismissedAt =
                    (result.organization || {}).dismissedAt || new Date().toISOString();
            }
            render();
        } catch (error) {
            var toast = global._showOfficeToast || global._acpShowToast;
            if (toast) toast('❌ ' + error.message);
        } finally {
            state.dismissing = false;
            renderMarker();
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
        openFailures: openFailures,
        moveSelectedSkill: moveSelectedSkill,
        startOrganization: startOrganization,
        dismissMarker: dismissMarker,
        stopPolling: stopPolling
    };
    init();
})(window);
