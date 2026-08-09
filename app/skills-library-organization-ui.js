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
        tagFilter: '',
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

    function tr(key, params, fallback) {
        if (global.i18n && typeof global.i18n.t === 'function') {
            var translated = global.i18n.t(key, params);
            if (translated && translated !== key) return translated;
        }
        return fallback;
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
        var seededKeys = {
            'default': 'skill_category_default',
            'development-testing': 'skill_category_development_testing',
            'collaboration-docs': 'skill_category_collaboration_docs',
            'project-process': 'skill_category_project_process',
            'operations-diagnostics': 'skill_category_operations_diagnostics',
            'knowledge-content': 'skill_category_knowledge_content'
        };
        var fallback = category ? category.name : '默认标签';
        return seededKeys[categoryId]
            ? tr(seededKeys[categoryId], null, fallback)
            : fallback;
    }

    function categoryCount(categoryId) {
        if (categoryId === 'all') return skills().length;
        return skills().filter(function(skill) {
            return skillCategoryId(skill) === categoryId;
        }).length;
    }

    function skillCategoryId(skill) {
        if (!skill) return 'default';
        return skill.primaryCategoryId ||
            (skill.primaryCategory && skill.primaryCategory.id) ||
            'default';
    }

    function skillTags(skill) {
        return Array.isArray(skill && skill.tags) ? skill.tags.filter(Boolean) : [];
    }

    function tagOptions() {
        var counts = new Map();
        skills().forEach(function(skill) {
            if (state.categoryId !== 'all' && skillCategoryId(skill) !== state.categoryId) {
                return;
            }
            skillTags(skill).forEach(function(tag) {
                counts.set(tag, (counts.get(tag) || 0) + 1);
            });
        });
        return Array.from(counts.entries())
            .map(function(entry) { return { name: entry[0], count: entry[1] }; })
            .sort(function(left, right) {
                if (right.count !== left.count) return right.count - left.count;
                return String(left.name || '').localeCompare(String(right.name || ''));
            });
    }

    function skillSlug(value) {
        return String(value || '')
            .trim()
            .toLocaleLowerCase()
            .replace(/[^a-z0-9_-]+/g, '-')
            .replace(/^-+|-+$/g, '')
            .slice(0, 128);
    }

    function failureSlugs() {
        var organization = state.data.organization || {};
        return new Set((Array.isArray(organization.failures) ? organization.failures : [])
            .map(function(failure) {
                return skillSlug(failure.slug || failure.skillName || failure.name || '');
            })
            .filter(Boolean));
    }

    function failureForSkill(slug) {
        var organization = state.data.organization || {};
        var normalized = skillSlug(slug);
        return (Array.isArray(organization.failures) ? organization.failures : [])
            .find(function(failure) {
                return skillSlug(failure.slug || failure.skillName || failure.name || '') === normalized;
            }) || null;
    }

    function visibleSkills() {
        var query = state.search.trim().toLocaleLowerCase();
        var failed = failureSlugs();
        return skills().filter(function(skill) {
            var inCategory = state.categoryId === 'all' ||
                skillCategoryId(skill) === state.categoryId;
            if (!inCategory) return false;
            if (state.tagFilter && skillTags(skill).indexOf(state.tagFilter) < 0) return false;
            if (state.failureOnly && !failed.has(skillSlug(skill.name))) return false;
            if (!query) return true;
            return [skill.name, skill.description].concat(skillTags(skill))
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
        var items = [{
            id: 'all',
            name: tr('skill_library_all_skills', null, '全部技能')
        }].concat(categories().map(function(category) {
            return Object.assign({}, category, { name: categoryName(category.id) });
        }));
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
                state.tagFilter = '';
                state.failureOnly = false;
                state.selectedSlug = '';
                render();
            });
            container.appendChild(button);
        });
    }

    function renderTags() {
        var container = byId('skl-tag-filter-list');
        if (!container) return;
        container.replaceChildren();
        var tags = tagOptions();
        if (!tags.length) {
            var empty = document.createElement('div');
            empty.className = 'skl-tag-filter-empty';
            empty.textContent = tr('skill_library_no_tags', null, '暂无标签');
            container.appendChild(empty);
            return;
        }
        tags.forEach(function(tag) {
            var button = document.createElement('button');
            button.type = 'button';
            button.className = 'skl-tag-filter' +
                (state.tagFilter === tag.name ? ' is-active' : '');
            button.setAttribute('aria-pressed', state.tagFilter === tag.name ? 'true' : 'false');
            button.setAttribute('data-skill-tag', tag.name);
            var name = document.createElement('span');
            name.textContent = tag.name;
            var count = document.createElement('span');
            count.className = 'skl-category-count';
            count.textContent = String(tag.count);
            button.append(name, count);
            button.addEventListener('click', function() {
                state.tagFilter = state.tagFilter === tag.name ? '' : tag.name;
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
                ? tr('skill_library_failed_filter', null, '归类失败')
                : state.tagFilter
                ? tr('skill_library_tag_filter_title', { tag: state.tagFilter }, '标签：' + state.tagFilter)
                : state.categoryId === 'all'
                ? tr('skill_library_all_skills', null, '全部技能')
                : categoryName(state.categoryId);
        }
        if (count) count.textContent = String(visible.length);
        container.replaceChildren();
        if (!visible.length) {
            var empty = document.createElement('div');
            empty.className = 'skl-empty';
            empty.textContent = state.search
                ? tr('skill_library_no_matches', null, '没有匹配的技能')
                : tr('skill_library_empty_category', null, '这个分类中还没有技能');
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
            description.textContent = skill.description ||
                tr('skill_library_no_description', null, '暂无描述');
            var category = document.createElement('span');
            category.className = 'skl-card-category';
            category.textContent = categoryName(skillCategoryId(skill));
            card.append(name, description, category);
            var failure = failureForSkill(skill.name);
            if (failure) {
                var failureBadge = document.createElement('span');
                failureBadge.className = 'skl-failure-badge';
                failureBadge.textContent =
                    tr('skill_library_classification_failed', null, '归类失败');
                card.appendChild(failureBadge);
                var failureReason = document.createElement('div');
                failureReason.className = 'skl-failure-reason';
                failureReason.setAttribute(
                    'data-failure-code',
                    failure.code || 'classification_failed'
                );
                failureReason.textContent = failure.reason ||
                    tr('skill_library_failure_reason_unknown', null, '未提供具体原因');
                failureReason.setAttribute(
                    'aria-label',
                    tr(
                        'skill_library_failure_reason_aria',
                        { reason: failureReason.textContent },
                        '归类失败原因：' + failureReason.textContent
                    )
                );
                card.appendChild(failureReason);
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
            empty.textContent =
                tr('skill_library_select_detail', null, '选择一个技能查看详情');
            container.appendChild(empty);
            return;
        }
        var title = document.createElement('h3');
        title.className = 'skl-detail-title';
        title.textContent = skill.name || '';
        var description = document.createElement('p');
        description.className = 'skl-detail-description';
        description.textContent = skill.description ||
            tr('skill_library_no_description', null, '暂无描述');
        container.append(
            title,
            description,
            detailField(
                tr('skill_library_source', null, '来源'),
                tr('skill_library_local_source', null, '本地技能库')
            ),
            detailField(
                tr('skill_library_primary_category', null, '主分类'),
                categoryName(skillCategoryId(skill))
            )
        );
        var selectedFailure = failureForSkill(skill.name);
        if (selectedFailure) {
            var selectedFailureReason = selectedFailure.reason ||
                tr('skill_library_failure_reason_unknown', null, '未提供具体原因');
            var failureField = detailField(
                tr('skill_library_failure_reason', null, '归类失败原因'),
                selectedFailureReason
            );
            failureField.className += ' skl-detail-failure';
            failureField.setAttribute(
                'data-failure-code',
                selectedFailure.code || 'classification_failed'
            );
            failureField.setAttribute(
                'aria-label',
                tr(
                    'skill_library_failure_reason_aria',
                    { reason: selectedFailureReason },
                    '归类失败原因：' + selectedFailureReason
                )
            );
            container.appendChild(failureField);
        }
        var tagsField = document.createElement('div');
        tagsField.className = 'skl-detail-field';
        var tagsLabel = document.createElement('span');
        tagsLabel.className = 'skl-detail-label';
        tagsLabel.textContent = tr('skill_library_tags', null, '标签');
        var tagList = document.createElement('div');
        tagList.className = 'skl-tag-list';
        var tags = skillTags(skill);
        if (!tags.length) {
            tagList.className = 'skl-detail-value';
            tagList.textContent = tr('skill_library_no_tags', null, '暂无标签');
        } else {
            tags.forEach(function(tag) {
                var chip = document.createElement('button');
                chip.type = 'button';
                chip.className = 'skl-tag skl-tag-action';
                chip.setAttribute('data-skill-tag', tag);
                chip.textContent = tag;
                chip.addEventListener('click', function() {
                    state.tagFilter = tag;
                    state.failureOnly = false;
                    state.selectedSlug = '';
                    render();
                });
                tagList.appendChild(chip);
            });
        }
        tagsField.append(tagsLabel, tagList);
        container.appendChild(tagsField);
        if (global.SkillLibraryAgentUsageUI) {
            container.appendChild(global.SkillLibraryAgentUsageUI.createField(skill, {
                translate: tr
            }));
        }

        var categoryControl = document.createElement('div');
        categoryControl.className = 'skl-category-control';
        var categorySelect = document.createElement('select');
        categorySelect.id = 'skl-category-select';
        categorySelect.className = 'skl-category-select';
        categorySelect.setAttribute(
            'aria-label',
            tr('skill_library_adjust_category', null, '调整主分类')
        );
        categories().forEach(function(category) {
            var option = document.createElement('option');
            option.value = category.id;
            option.textContent = category.name;
            categorySelect.appendChild(option);
        });
        categorySelect.value = skillCategoryId(skill);
        var moveButton = document.createElement('button');
        moveButton.id = 'skl-category-move';
        moveButton.type = 'button';
        moveButton.className = 'skl-category-move';
        moveButton.textContent = state.moving
            ? tr('skill_library_moving', null, '移动中…')
            : tr('skill_library_move', null, '移动');
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
            [tr('skill_library_apply_to_ai', null, '应用到 AI'), false, function() { global.toggleSkillApply(skill.name); }],
            [tr('edit', null, '编辑'), true, function() { global.openSkillEditor(skill.name); }],
            [tr('delete', null, '删除'), true, function() { global.deleteLibrarySkill(skill.name); }]
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
        if (!state.data.organizationEnabled) {
            disabledReason = tr(
                'skill_organization_disabled',
                null,
                '智能整理当前未启用'
            );
        } else if (organization.status === 'running') {
            disabledReason = tr(
                'skill_organization_running',
                null,
                '档案管理员正在整理技能库'
            );
        } else if (manager.status === 'working' || manager.activeWork) {
            disabledReason = tr(
                'skill_organization_manager_busy',
                null,
                '档案管理员正在处理其他工作'
            );
        } else if (['missing', 'error', 'offline', 'unavailable', 'paused'].indexOf(manager.status) >= 0) {
            disabledReason = tr(
                'skill_organization_manager_unavailable',
                null,
                '档案管理员当前不可用'
            );
        } else if (!defaultCount) {
            disabledReason = tr(
                'skill_organization_default_empty',
                null,
                '默认标签中没有需要整理的技能'
            );
        }
        button.disabled = Boolean(disabledReason || state.starting);
        button.title = disabledReason;
        button.setAttribute('aria-disabled', button.disabled ? 'true' : 'false');
    }

    function markerCopy(organization) {
        var failures = Number(organization.failureCount || 0);
        if (organization.status === 'running') {
            return {
                tone: 'running',
                text: tr(
                    'skill_organization_marker_running',
                    null,
                    '档案管理员正在整理技能库…'
                ),
                dismissible: false
            };
        }
        if (organization.status === 'completed') {
            return {
                tone: 'completed',
                text: tr(
                    'skill_organization_marker_completed',
                    null,
                    '技能整理已完成'
                ),
                dismissible: true
            };
        }
        if (organization.status === 'resolved') {
            return {
                tone: 'resolved',
                text: tr(
                    'skill_organization_marker_resolved',
                    null,
                    '归类失败项已全部处理'
                ),
                dismissible: true
            };
        }
        if (organization.status === 'partial') {
            return {
                tone: 'partial',
                text: tr(
                    'skill_organization_marker_partial',
                    { count: failures },
                    '技能整理完成，' + failures + ' 个归类失败'
                ),
                dismissible: true,
                opensFailures: failures > 0
            };
        }
        if (organization.status === 'failed') {
            return {
                tone: 'partial',
                text: failures
                    ? tr(
                        'skill_organization_marker_failed_count',
                        { count: failures },
                        '技能整理未完成，' + failures + ' 个归类失败'
                    )
                    : tr(
                        'skill_organization_marker_failed',
                        null,
                        '技能整理未完成'
                    ),
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
            dismiss.textContent = tr('close', null, '关闭');
            dismiss.setAttribute(
                'aria-label',
                tr(
                    'skill_organization_dismiss_label',
                    null,
                    '关闭整理结果'
                )
            );
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
        renderTags();
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
        state.tagFilter = '';
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
            targetCategoryId === skillCategoryId(skill)
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
                throw new Error(result.error || tr(
                    'skill_organization_move_failed',
                    null,
                    '调整技能分类失败'
                ));
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
            if (toast) toast('❌ ' + error.message, 'error');
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
            if (!response.ok) throw new Error(result.error || tr(
                'skill_organization_start_failed',
                null,
                '智能整理启动失败'
            ));
            state.data.organization = result;
            render();
            if (typeof global.refreshSkillsList === 'function') {
                await global.refreshSkillsList();
            }
        } catch (error) {
            var toast = global._showOfficeToast || global._acpShowToast;
            if (toast) toast('❌ ' + error.message, 'error');
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
            if (!response.ok) throw new Error(result.error || tr(
                'skill_organization_dismiss_failed',
                null,
                '关闭整理结果失败'
            ));
            if (state.data.organization) {
                state.data.organization.dismissedAt =
                    (result.organization || {}).dismissedAt || new Date().toISOString();
            }
            render();
        } catch (error) {
            var toast = global._showOfficeToast || global._acpShowToast;
            if (toast) toast('❌ ' + error.message, 'error');
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
        if (typeof global.addEventListener === 'function') {
            global.addEventListener('i18n:changed', render);
            global.addEventListener('i18n:ready', render);
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
