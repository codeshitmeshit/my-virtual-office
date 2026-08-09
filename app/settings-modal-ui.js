(function initSettingsModal(global) {
    'use strict';

    var documentRef = global && global.document;
    var FALLBACK_COPY = {
        settings_modal_connections_agents: 'Connections & Agents',
        settings_modal_office: 'Office',
        settings_modal_weather: 'Weather',
        settings_modal_display: 'Display',
        settings_modal_tools_browser: 'Tools & Browser',
        settings_modal_notifications: 'Notifications',
        settings_modal_storage: 'Storage',
        settings_modal_advanced: 'Advanced',
        settings_modal_subtitle: 'Manage connections, agents, display, notifications, and storage.',
    };

    var CATEGORY_DEFINITIONS = [
        {
            id: 'connections-agents',
            labelKey: 'settings_modal_connections_agents',
            selectors: ['#mm-oc-path', '#mm-hermes-enable', '#mm-codex-enable', '#mm-claude-code-enable'],
        },
        { id: 'office', labelKey: 'settings_modal_office', selectors: ['#mm-office-name', '#mm-weather-provider'] },
        { id: 'weather', labelKey: 'settings_modal_weather', selectors: ['#mm-show-weather'] },
        { id: 'display', labelKey: 'settings_modal_display', selectors: ['#mm-show-bubbles'] },
        {
            id: 'tools-browser',
            labelKey: 'settings_modal_tools_browser',
            selectors: ['#mm-apiusage-enable', '#mm-pcmetrics-enable', '#mm-browser-enable'],
        },
        {
            id: 'notifications',
            labelKey: 'settings_modal_notifications',
            selectors: ['#mm-feishu-enable', '#mm-feishu-chat-enable'],
        },
        { id: 'storage', labelKey: 'settings_modal_storage', selectors: ['#oss-settings-section'] },
        { id: 'advanced', labelKey: 'settings_modal_advanced', selectors: ['#mm-import-file', 'a[href="/setup"]'] },
    ];

    var settingsModalState = {
        mounted: false,
        activeCategory: 'connections-agents',
        labelsBound: false,
    };

    function translated(key) {
        var i18n = global && global.i18n;
        if (i18n && typeof i18n.t === 'function') {
            var value = i18n.t(key);
            if (value && value !== key) return value;
        }
        return FALLBACK_COPY[key] || key;
    }

    function sectionMatches(section, selectors) {
        return selectors.some(function(selector) {
            return (typeof section.matches === 'function' && section.matches(selector))
                || (typeof section.querySelector === 'function' && section.querySelector(selector));
        });
    }

    function matchedCategory(section) {
        for (var index = 0; index < CATEGORY_DEFINITIONS.length; index += 1) {
            var definition = CATEGORY_DEFINITIONS[index];
            if (sectionMatches(section, definition.selectors)) return definition;
        }
        return null;
    }

    function classifySection(section) {
        var definition = matchedCategory(section);
        return definition ? definition.id : 'advanced';
    }

    function categoryButton(panel, categoryId) {
        return panel.querySelector('[data-settings-category-button="' + categoryId + '"]');
    }

    function categoryPanel(panel, categoryId) {
        return panel.querySelector('[data-settings-category-panel="' + categoryId + '"]');
    }

    function activateCategory(categoryId) {
        if (!documentRef) return false;
        var panel = documentRef.getElementById('main-menu-panel');
        if (!panel || !CATEGORY_DEFINITIONS.some(function(item) { return item.id === categoryId; })) return false;

        CATEGORY_DEFINITIONS.forEach(function(definition) {
            var button = categoryButton(panel, definition.id);
            var content = categoryPanel(panel, definition.id);
            var active = definition.id === categoryId;
            if (button) {
                button.setAttribute('aria-selected', active ? 'true' : 'false');
                button.setAttribute('tabindex', active ? '0' : '-1');
                button.classList.toggle('active', active);
            }
            if (content) {
                content.hidden = !active;
                content.setAttribute('aria-hidden', active ? 'false' : 'true');
            }
        });
        settingsModalState.activeCategory = categoryId;
        return true;
    }

    function updateLabels() {
        if (!documentRef) return;
        var panel = documentRef.getElementById('main-menu-panel');
        if (!panel) return;
        CATEGORY_DEFINITIONS.forEach(function(definition) {
            var button = categoryButton(panel, definition.id);
            if (button) text(button, translated(definition.labelKey));
        });
        var subtitle = panel.querySelector('.settings-modal-subtitle');
        if (subtitle) text(subtitle, translated('settings_modal_subtitle'));
    }

    function text(node, value) {
        node.textContent = value;
    }

    function handleCategoryKeydown(event, index, buttons) {
        var targetIndex = index;
        if (event.key === 'ArrowDown' || event.key === 'ArrowRight') targetIndex = (index + 1) % buttons.length;
        else if (event.key === 'ArrowUp' || event.key === 'ArrowLeft') targetIndex = (index - 1 + buttons.length) % buttons.length;
        else if (event.key === 'Home') targetIndex = 0;
        else if (event.key === 'End') targetIndex = buttons.length - 1;
        else return;

        event.preventDefault();
        var target = buttons[targetIndex];
        activateCategory(target.getAttribute('data-settings-category-button'));
        if (typeof target.focus === 'function') target.focus();
    }

    function buildNavigation(panel) {
        var nav = documentRef.createElement('nav');
        nav.className = 'settings-modal-nav';
        nav.setAttribute('aria-label', 'Settings categories');

        var buttons = [];

        CATEGORY_DEFINITIONS.forEach(function(definition, index) {
            var button = documentRef.createElement('button');
            button.type = 'button';
            button.className = 'settings-modal-nav-button';
            button.setAttribute('role', 'tab');
            button.setAttribute('data-settings-category-button', definition.id);
            button.setAttribute('aria-controls', 'settings-modal-category-' + definition.id);
            text(button, translated(definition.labelKey));
            button.addEventListener('click', function() { activateCategory(definition.id); });
            button.addEventListener('keydown', function(event) { handleCategoryKeydown(event, index, buttons); });
            nav.appendChild(button);
            buttons.push(button);
        });
        return nav;
    }

    function buildCategoryPanels(content) {
        var panels = {};
        CATEGORY_DEFINITIONS.forEach(function(definition) {
            var category = documentRef.createElement('section');
            category.className = 'settings-modal-category-panel';
            category.id = 'settings-modal-category-' + definition.id;
            category.setAttribute('role', 'tabpanel');
            category.setAttribute('data-settings-category', definition.id);
            category.setAttribute('data-settings-category-panel', definition.id);
            content.appendChild(category);
            panels[definition.id] = category;
        });
        return panels;
    }

    function mountSettingsModal() {
        if (!documentRef) return null;
        var panel = documentRef.getElementById('main-menu-panel');
        if (!panel) return null;
        var existing = panel.querySelector('.settings-modal-dialog');
        if (existing) {
            settingsModalState.mounted = true;
            return existing;
        }

        var header = panel.querySelector('.main-menu-header');
        var body = panel.querySelector('.main-menu-body');
        if (!header || !body) return null;
        var sections = Array.prototype.slice.call(body.querySelectorAll('.mm-section'));
        var saveButton = body.querySelector('.mm-save-all');
        if (!sections.length || !saveButton) return null;

        var dialog = documentRef.createElement('div');
        dialog.className = 'settings-modal-dialog';
        dialog.setAttribute('role', 'dialog');
        dialog.setAttribute('aria-modal', 'true');

        header.classList.add('settings-modal-header');
        var title = header.querySelector('span');
        if (title) {
            title.id = 'settings-modal-title';
            dialog.setAttribute('aria-labelledby', title.id);
        }
        var subtitle = documentRef.createElement('p');
        subtitle.className = 'settings-modal-subtitle';
        text(subtitle, translated('settings_modal_subtitle'));
        var closeButton = header.querySelector('button');
        if (closeButton) closeButton.setAttribute('aria-label', 'Close settings');
        if (closeButton) header.insertBefore(subtitle, closeButton);
        else header.appendChild(subtitle);

        body.classList.add('settings-modal-body');
        var layout = documentRef.createElement('div');
        layout.className = 'settings-modal-layout';
        var nav = buildNavigation(panel);
        var content = documentRef.createElement('div');
        content.className = 'settings-modal-content';
        var categoryPanels = buildCategoryPanels(content);

        sections.forEach(function(section) {
            var definition = matchedCategory(section);
            var categoryId = definition ? definition.id : 'advanced';
            section.setAttribute('data-settings-category-owner', categoryId);
            if (!definition) section.setAttribute('data-settings-unclassified', 'true');
            categoryPanels[categoryId].appendChild(section);
        });

        layout.appendChild(nav);
        layout.appendChild(content);
        var footer = documentRef.createElement('div');
        footer.className = 'settings-modal-footer';
        footer.appendChild(saveButton);
        body.appendChild(layout);
        body.appendChild(footer);
        dialog.appendChild(header);
        dialog.appendChild(body);
        panel.appendChild(dialog);

        panel.classList.add('settings-modal-mounted');
        settingsModalState.mounted = true;
        activateCategory(settingsModalState.activeCategory);
        if (!settingsModalState.labelsBound && global && typeof global.addEventListener === 'function') {
            global.addEventListener('i18n:ready', updateLabels);
            global.addEventListener('i18n:changed', updateLabels);
            settingsModalState.labelsBound = true;
        }
        return dialog;
    }

    var api = {
        CATEGORY_DEFINITIONS: CATEGORY_DEFINITIONS,
        settingsModalState: settingsModalState,
        classifySection: classifySection,
        activateCategory: activateCategory,
        mountSettingsModal: mountSettingsModal,
        updateLabels: updateLabels,
    };
    global.VOSettingsModal = api;
    if (typeof module !== 'undefined' && module.exports) module.exports = api;

    if (documentRef) {
        if (documentRef.readyState === 'loading') {
            documentRef.addEventListener('DOMContentLoaded', mountSettingsModal);
        } else {
            mountSettingsModal();
        }
    }
})(typeof window !== 'undefined' ? window : globalThis);
