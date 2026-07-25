(function (root) {
    'use strict';

    const state = {
        context: null,
        profiles: new Map(),
        loading: new Set(),
        errors: new Map(),
        saveState: new Map(),
        undo: new Map(),
        debounce: new Map(),
        saveSequence: new Map(),
    };

    const APPEARANCE_OPTIONS = {
        gender: ['M', 'F'],
        hairStyle: ['bald', 'buzz', 'short', 'medium', 'long', 'curly', 'wavy', 'spiky', 'bun', 'ponytail', 'mohawk'],
        eyebrowStyle: ['thin', 'thick', 'angular', 'arched'],
        facialHair: ['none', 'stubble', 'beard', 'goatee', 'mustache'],
        costume: ['none', 'lobster', 'chicken'],
        headwear: ['none', 'hardhat', 'cap', 'crown', 'tiara', 'headband', 'goggles', 'headset', 'beanie'],
        glasses: ['none', 'round', 'square', 'sunglasses'],
        heldItem: ['none', 'tablet', 'wrench', 'coffee', 'clipboard', 'pen', 'hammer', 'testTube', 'book'],
        deskItem: ['none', 'anvil', 'trophy', 'calendar', 'envelope', 'money', 'ruler', 'marker', 'chart', 'plans', 'checklist', 'microscope', 'shield', 'phone', 'files'],
    };
    const APPEARANCE_COLORS = [
        'color', 'skinTone', 'hairColor', 'eyeColor',
        'headwearColor', 'glassesColor',
    ];

    function esc(value) {
        return String(value == null ? '' : value)
            .replace(/&/g, '&amp;').replace(/</g, '&lt;')
            .replace(/>/g, '&gt;').replace(/"/g, '&quot;')
            .replace(/'/g, '&#39;');
    }

    function tr(key, fallback) {
        if (root.i18n && typeof root.i18n.t === 'function') {
            const value = root.i18n.t(key);
            if (value && value !== key) return value;
        }
        return fallback;
    }

    function selectedAgent(context) {
        return (context.roster || []).find(function (item) {
            return item.aiId === context.selectedAiId;
        }) || { aiId: context.selectedAiId };
    }

    function canEdit(context) {
        if (!context || !context.selectedAiId) return false;
        return context.audience.kind === 'human' ||
            context.audience.aiId === context.selectedAiId;
    }

    function canSeeRestricted(context) {
        return Boolean(context && context.audience.kind === 'human');
    }

    function isContextActive(context) {
        return !context || typeof context.isActive !== 'function' || context.isActive();
    }

    function visibleSections(context) {
        const sections = ['identity', 'introduction', 'responsibilities', 'appearance'];
        if (canSeeRestricted(context)) {
            sections.push('assignment', 'provider', 'branch', 'workspace', 'binding');
        }
        return sections;
    }

    function normalizeProfile(payload, agent) {
        const profile = payload && (payload.profile || payload);
        return Object.assign({
            aiId: agent.aiId,
            revision: 0,
            name: agent.name || agent.displayName || agent.aiId,
            introduction: agent.introduction || '',
            responsibilities: agent.responsibilities || (agent.role ? [agent.role] : []),
            specialties: agent.specialties || [],
            appearance: agent.appearance || {},
        }, profile || {});
    }

    function previewProfile(agent, state) {
        return Object.assign(normalizeProfile(null, agent || {}), {
            __preview: true,
            __previewState: state || 'loading',
        });
    }

    async function requestProfile(context, aiId) {
        if (context.adapter && typeof context.adapter.getConfiguration === 'function') {
            return context.adapter.getConfiguration(aiId);
        }
        if (!root.i18n || typeof root.i18n.managementFetch !== 'function') {
            return null;
        }
        const response = await root.i18n.managementFetch(
            '/api/agent-management/profiles/' + encodeURIComponent(aiId)
        );
        const payload = await response.json();
        if (!response.ok || payload.ok === false) throw new Error(payload.code || 'agent_profile_load_failed');
        return payload;
    }

    function fieldStatus(field) {
        const entry = state.saveState.get(field);
        if (!entry) {
            return '<span class="ac-field-feedback"><span class="ac-field-status" data-field-status="' +
                esc(field) + '" role="status"></span></span>';
        }
        const label = {
            saving: tr('agent_save_saving', 'Saving…'),
            saved: tr('agent_save_saved', 'Saved'),
            conflict: tr('agent_save_conflict', 'Conflict'),
            denied: tr('agent_save_denied', 'Denied'),
            failed: tr('agent_save_failed', 'Save failed'),
            undone: tr('agent_save_undone', 'Undone'),
        }[entry.state] || entry.state;
        const undo = state.undo.get(field);
        return '<span class="ac-field-feedback"><span class="ac-field-status ' + esc(entry.state) +
            '" data-field-status="' + esc(field) + '" role="status">' + esc(label) + '</span>' +
            (undo ? '<button type="button" class="ac-undo" data-undo-field="' + esc(field) + '">' +
                esc(tr('undo', 'Undo')) + '</button>' : '') + '</span>';
    }

    function textField(label, field, value, editable, multiline) {
        const tag = multiline ? 'textarea' : 'input';
        const valueMarkup = multiline
            ? '>' + esc(value) + '</textarea>'
            : ' value="' + esc(value) + '">';
        if (!editable) {
            return '<div class="ac-field ac-readonly"><span>' + esc(label) +
                '</span><strong>' + esc(value || '—') + '</strong></div>';
        }
        return '<label class="ac-field"><span>' + esc(label) + '</span><' + tag +
            ' data-profile-field="' + esc(field) + '"' +
            (multiline ? ' rows="4"' : ' type="text"') + valueMarkup +
            fieldStatus(field) + '</label>';
    }

    function tagsField(label, field, values, editable) {
        const text = (Array.isArray(values) ? values : []).join(', ');
        return textField(label, field, text, editable, false);
    }

    function restrictedCard(title, field, value, disabled) {
        return '<section class="ac-restricted-card" data-restricted-field="' + esc(field) + '">' +
            '<span>' + esc(title) + '</span><strong>' + esc(value || '—') + '</strong>' +
            '<button type="button" data-high-risk-action="' + esc(field) + '"' +
            (disabled ? ' disabled' : '') + '>' +
            esc(tr('agent_change', 'Change')) + '</button></section>';
    }

    function appearanceLabel(field) {
        const labels = {
            gender: tr('agent_gender', 'Gender'),
            hairStyle: tr('agent_hair', 'Hair'),
            eyebrowStyle: tr('agent_eyebrows', 'Eyebrows'),
            facialHair: tr('agent_facial_hair', 'Facial hair'),
            costume: tr('agent_costume', 'Costume'),
            headwear: tr('agent_headwear', 'Headwear'),
            glasses: tr('agent_glasses', 'Glasses'),
            heldItem: tr('agent_held_item', 'Held item'),
            deskItem: tr('agent_desk_item', 'Desk item'),
            color: tr('agent_shirt', 'Clothing color'),
            skinTone: tr('agent_skin', 'Skin tone'),
            hairColor: tr('agent_hair_color', 'Hair color'),
            eyeColor: tr('agent_eye_color', 'Eye color'),
            headwearColor: tr('agent_hat_color', 'Headwear color'),
            glassesColor: tr('agent_lens_color', 'Glasses color'),
        };
        return labels[field] || field;
    }

    function appearanceOptionLabel(value) {
        const raw = String(value == null ? 'none' : value);
        const key = raw === 'M' ? 'option_male' :
            (raw === 'F' ? 'option_female' : 'option_' + raw);
        return tr(key, raw);
    }

    function appearanceSelector(field, value, editable) {
        const current = value == null ? 'none' : String(value);
        const options = APPEARANCE_OPTIONS[field] || [];
        if (!editable) {
            return '<div class="ac-appearance-readonly"><span>' + esc(appearanceLabel(field)) +
                '</span><strong>' + esc(appearanceOptionLabel(current)) + '</strong></div>';
        }
        return '<div class="ac-selector" data-appearance-selector="' + esc(field) + '">' +
            '<span class="ac-selector-label">' + esc(appearanceLabel(field)) + '</span>' +
            '<button type="button" class="ac-selector-current" aria-haspopup="listbox" aria-expanded="false">' +
                '<span class="ac-option-icon" aria-hidden="true">' + esc(current === 'none' ? '—' : current.slice(0, 2).toUpperCase()) + '</span>' +
                '<strong>' + esc(appearanceOptionLabel(current)) + '</strong><span aria-hidden="true">▾</span></button>' +
            '<div class="ac-option-popover hidden" role="listbox" aria-label="' + esc(appearanceLabel(field)) + '">' +
                options.map(function (option, index) {
                    return '<button type="button" role="option" tabindex="' + (index === 0 ? '0' : '-1') +
                        '" aria-selected="' + (option === current ? 'true' : 'false') +
                        '" data-appearance-option="' + esc(option) + '">' +
                        '<span class="ac-option-icon" aria-hidden="true">' + esc(option === 'none' ? '—' : option.slice(0, 2).toUpperCase()) +
                        '</span><span>' + esc(appearanceOptionLabel(option)) + '</span></button>';
                }).join('') + '</div>' + fieldStatus('appearance.' + field) + '</div>';
    }

    function appearanceColor(field, value, editable) {
        const fallback = {
            color: '#4a90e2', skinTone: '#f2c7a5', hairColor: '#4b3527',
            eyeColor: '#2f7bc1', headwearColor: '#888888', glassesColor: '#333333',
        }[field];
        const current = /^#[0-9a-f]{6}$/i.test(String(value || '')) ? value : fallback;
        if (!editable) {
            return '<div class="ac-color-field"><span>' + esc(appearanceLabel(field)) +
                '</span><i style="--swatch:' + esc(current) + '"></i><strong>' + esc(current) + '</strong></div>';
        }
        return '<label class="ac-color-field"><span>' + esc(appearanceLabel(field)) + '</span>' +
            '<input type="color" data-appearance-color="' + esc(field) + '" value="' + esc(current) + '">' +
            '<i style="--swatch:' + esc(current) + '"></i>' + fieldStatus('appearance.' + field) + '</label>';
    }

    function renderAppearance(profile, editable) {
        const appearance = profile.appearance || {};
        function selectorGroup(title, fields) {
            return '<section class="ac-appearance-group"><h5>' + esc(title) + '</h5>' +
                fields.map(function (field) {
                    return appearanceSelector(field, appearance[field], editable);
                }).join('') + '</section>';
        }
        return '<div class="ac-appearance-heading"><strong>' +
                esc(tr('agent_appearance_editor_title', 'Appearance, accessories & items')) +
                '</strong><span>' + esc(tr('agent_appearance_editor_hint', 'Dropdown selection · Live preview · Auto-save')) +
                '</span></div>' +
            '<section class="ac-appearance-group"><h5>' + esc(tr('agent_colors_bilingual', 'Colors / COLORS')) + '</h5>' +
                '<div class="ac-color-grid">' + APPEARANCE_COLORS.map(function (field) {
                    return appearanceColor(field, appearance[field], editable);
                }).join('') + '</div></section>' +
            selectorGroup(tr('agent_hair_face_bilingual', 'Hair + face / HAIR + FACE'), [
                'gender', 'hairStyle', 'eyebrowStyle', 'facialHair',
            ]) +
            selectorGroup(tr('agent_costume_accessories_bilingual', 'Costume + accessories / COSTUME + ACCESSORIES'), [
                'costume', 'headwear', 'glasses',
            ]) +
            selectorGroup(tr('agent_items_bilingual', 'Items / ITEMS'), ['heldItem', 'deskItem']);
    }

    function renderProfile(context, profile) {
        if (!isContextActive(context)) return false;
        const container = context.container;
        const agent = selectedAgent(context);
        const isPreview = Boolean(profile.__preview);
        const editable = !isPreview && canEdit(context);
        const restricted = canSeeRestricted(context);
        const appearance = profile.appearance || {};
        const role = agent.role || (profile.responsibilities || []).join(' / ') || '—';
        const provider = agent.providerKind || agent.provider || '—';
        const branch = agent.branchName || agent.branch || '—';
        const stateLabel = profile.__previewState === 'unregistered'
            ? tr('agent_basic_profile_short', 'BASIC')
            : tr('agent_loading_short', 'LOADING');
        container.innerHTML =
            '<div class="agent-configuration" data-audience="' + esc(context.audience.kind) + '">' +
                '<div class="ac-profile-columns">' +
                    '<section class="ac-profile-primary">' +
                        '<section class="ac-hero"><canvas class="ac-avatar" width="80" height="104" data-agent-appearance-preview></canvas>' +
                            '<div><span class="ac-eyebrow">' + esc(profile.aiId) + '</span>' +
                            '<h3>' + esc(profile.name || profile.aiId) + '</h3>' +
                            '<p>' + esc(profile.aiId + ' · ' + role) + '</p></div>' +
                            '<span class="ac-active">● ' + esc(isPreview ? stateLabel : tr('agent_active_short', 'ACTIVE')) + '</span></section>' +
                            '<span class="ac-active">● ' + esc(isPreview ? stateLabel : tr('agent_active_short', 'ACTIVE')) + '</span></section>' +
                        '<section class="ac-card ac-identity-card" data-section="identity"><h4>' +
                            esc(tr('agent_identity_bilingual', 'Identity / IDENTITY')) + '</h4>' +
                            textField(tr('agent_name', 'Name'), 'name', profile.name, editable, false) +
                            '<div class="ac-static-field"><span>' + esc(tr('agent_role', 'Role')) +
                            '</span><strong>' + esc(role) + '</strong></div>' +
                            '<div class="ac-static-field"><span>' + esc(tr('agent_gender', 'Gender')) +
                            '</span><strong>' + esc(appearanceOptionLabel(appearance.gender || 'none')) + '</strong></div></section>' +
                        (restricted ? '<section class="ac-restricted"><h4>' +
                            esc(tr('agent_assignment_bilingual', 'Assignment / ASSIGNMENT')) + '</h4>' +
                            restrictedCard(tr('agent_branch', 'Branch'), 'branch', branch, isPreview) +
                            restrictedCard(tr('agent_provider', 'Provider'), 'provider', provider, isPreview) +
                            restrictedCard(tr('agent_binding', 'Provider Agent'), 'binding', agent.providerAgentId || agent.profile, isPreview) +
                            restrictedCard(tr('agent_workspace', 'Workspace'), 'workspace', agent.workspace || agent.workspacePath, isPreview) +
                            restrictedCard(tr('agent_assignment', 'Assignment'), 'assignment', agent.assignment || agent.role, isPreview) +
                            '<div class="ac-lifecycle-actions"><button type="button" data-high-risk-action="create"' + (isPreview ? ' disabled' : '') + '>' +
                                esc(tr('new_agent', 'Create Agent')) + '</button><button type="button" class="danger" data-high-risk-action="delete"' + (isPreview ? ' disabled' : '') + '>' +
                                esc(tr('delete_agent', 'Delete Agent')) + '</button></div></section>' : '') +
                        '<div class="ac-work-copy">' +
                            '<section class="ac-card" data-section="introduction"><h4>' +
                                esc(tr('agent_introduction', 'Introduction')) + '</h4>' +
                                textField(tr('agent_introduction', 'Introduction'), 'introduction', profile.introduction, editable, true) + '</section>' +
                            '<section class="ac-card" data-section="responsibilities"><h4>' +
                                esc(tr('agent_responsibilities', 'Responsibilities & specialties')) + '</h4>' +
                                tagsField(tr('agent_responsibilities', 'Responsibilities'), 'responsibilities', profile.responsibilities, editable) +
                                tagsField(tr('agent_specialties', 'Specialties'), 'specialties', profile.specialties, editable) + '</section>' +
                        '</div>' +
                    '</section>' +
                    '<section class="ac-card ac-appearance-card" data-section="appearance">' +
                        '<div id="agent-appearance-editor" class="ac-appearance-editor" data-editable="' + (editable ? 'true' : 'false') + '">' +
                            renderAppearance(profile, editable) + '</div></section>' +
                '</div>' +
                '<div id="agent-high-risk-dialog"></div>' +
            '</div>';
        const preview = container.querySelector('[data-agent-appearance-preview]');
        if (preview && root.AgentAppearancePreview) {
            root.AgentAppearancePreview.render(preview, appearance, agent);
        }
        bindFieldEvents(context);
        return true;
    }

    function normalizeFieldValue(field, raw) {
        if (field === 'responsibilities' || field === 'specialties') {
            const seen = new Set();
            return String(raw || '').split(',').map(function (item) { return item.trim(); })
                .filter(function (item) {
                    const key = item.toLowerCase();
                    if (!item || seen.has(key)) return false;
                    seen.add(key);
                    return true;
                }).slice(0, 12);
        }
        return String(raw == null ? '' : raw).trim();
    }

    function classifySaveError(status, code) {
        if (status === 409 || /conflict/.test(String(code || ''))) return 'conflict';
        if (status === 401 || status === 403 || /denied|forbidden/.test(String(code || ''))) return 'denied';
        return 'failed';
    }

    function setSaveState(field, nextState, code) {
        state.saveState.set(field, { state: nextState, code: code || '' });
        const context = state.context;
        if (!context || !context.container) return;
        const status = context.container.querySelector('[data-field-status="' + field + '"]');
        if (status) {
            status.className = 'ac-field-status ' + nextState;
            status.textContent = {
                saving: tr('agent_save_saving', 'Saving…'),
                saved: tr('agent_save_saved', 'Saved'),
                conflict: tr('agent_save_conflict', 'Conflict'),
                denied: tr('agent_save_denied', 'Denied'),
                failed: tr('agent_save_failed', 'Save failed'),
                undone: tr('agent_save_undone', 'Undone'),
            }[nextState] || nextState;
        }
        if (context.reportMutation) {
            context.reportMutation({ field: field, state: nextState, code: code || '' });
        }
    }

    async function mutationRequest(context, path, body) {
        if (context.adapter && typeof context.adapter.mutateConfiguration === 'function') {
            return context.adapter.mutateConfiguration(path, body);
        }
        if (!root.i18n || typeof root.i18n.managementFetch !== 'function') {
            throw Object.assign(new Error('agent_management_adapter_unavailable'), { status: 503 });
        }
        const response = await root.i18n.managementFetch(path, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(body),
        });
        const payload = await response.json();
        if (!response.ok || payload.ok === false) {
            throw Object.assign(new Error(payload.code || 'agent_profile_mutation_failed'), {
                status: response.status,
                code: payload.code || '',
            });
        }
        return payload;
    }

    async function commitField(field, value) {
        const context = state.context;
        const profile = context && state.profiles.get(context.selectedAiId);
        if (!context || !profile || !canEdit(context) || !isContextActive(context)) return false;
        const sequence = (state.saveSequence.get(field) || 0) + 1;
        state.saveSequence.set(field, sequence);
        setSaveState(field, 'saving');
        try {
            const payload = await mutationRequest(
                context,
                context.audience.kind === 'agent'
                    ? '/api/agent-management/browser/profile/mutate'
                    : '/api/agent-management/profile/mutate',
                {
                    targetAiId: context.selectedAiId,
                    field: field,
                    value: normalizeFieldValue(field, value),
                    expectedRevision: profile.revision,
                }
            );
            if (state.saveSequence.get(field) !== sequence) return false;
            state.profiles.set(context.selectedAiId, normalizeProfile(payload, selectedAgent(context)));
            if (payload.undoToken) {
                state.undo.set(field, {
                    token: payload.undoToken,
                    revision: payload.revision,
                    expiresAt: payload.undoExpiresAt,
                });
            }
            setSaveState(field, 'saved');
            renderProfile(context, state.profiles.get(context.selectedAiId));
            return true;
        } catch (error) {
            if (state.saveSequence.get(field) !== sequence) return false;
            setSaveState(field, classifySaveError(error.status, error.code || error.message), error.code || error.message);
            return false;
        }
    }

    async function undoField(field) {
        const context = state.context;
        const undo = state.undo.get(field);
        if (!context || !undo || !isContextActive(context)) return false;
        try {
            const payload = await mutationRequest(
                context,
                context.audience.kind === 'agent'
                    ? '/api/agent-management/browser/profile/undo'
                    : '/api/agent-management/profile/undo',
                { undoToken: undo.token, expectedRevision: undo.revision }
            );
            state.undo.delete(field);
            state.profiles.set(context.selectedAiId, normalizeProfile(payload, selectedAgent(context)));
            setSaveState(field, 'undone');
            renderProfile(context, state.profiles.get(context.selectedAiId));
            return true;
        } catch (error) {
            state.undo.delete(field);
            setSaveState(field, classifySaveError(error.status, error.code || error.message), error.code || error.message);
            return false;
        }
    }

    function scheduleTextSave(field, value) {
        if (state.debounce.has(field) && typeof root.clearTimeout === 'function') {
            root.clearTimeout(state.debounce.get(field));
        }
        if (typeof root.setTimeout !== 'function') return commitField(field, value);
        const timer = root.setTimeout(function () {
            state.debounce.delete(field);
            commitField(field, value);
        }, 450);
        state.debounce.set(field, timer);
        return timer;
    }

    function bindFieldEvents(context) {
        if (!context.container || !canEdit(context)) return;
        context.container.querySelectorAll('[data-profile-field]').forEach(function (control) {
            const field = control.getAttribute('data-profile-field');
            control.addEventListener('input', function () {
                scheduleTextSave(field, control.value);
            });
            control.addEventListener('blur', function () {
                if (!state.debounce.has(field)) return;
                if (typeof root.clearTimeout === 'function') root.clearTimeout(state.debounce.get(field));
                state.debounce.delete(field);
                commitField(field, control.value);
            });
        });
        context.container.querySelectorAll('[data-undo-field]').forEach(function (button) {
            button.addEventListener('click', function () {
                undoField(button.getAttribute('data-undo-field'));
            });
        });
        context.container.querySelectorAll('[data-appearance-selector]').forEach(function (selector) {
            const field = selector.getAttribute('data-appearance-selector');
            const toggle = selector.querySelector('.ac-selector-current');
            const popover = selector.querySelector('.ac-option-popover');
            const options = Array.from(selector.querySelectorAll('[data-appearance-option]'));
            function closeSelector() {
                popover.classList.add('hidden');
                toggle.setAttribute('aria-expanded', 'false');
                if (root.AgentAppearanceDropdown) {
                    root.AgentAppearanceDropdown.reset(selector);
                }
            }
            toggle.addEventListener('click', function () {
                const opening = popover.classList.contains('hidden');
                context.container.querySelectorAll('.ac-option-popover').forEach(function (other) {
                    other.classList.add('hidden');
                    const otherToggle = other.closest('.ac-selector')?.querySelector('.ac-selector-current');
                    if (otherToggle) otherToggle.setAttribute('aria-expanded', 'false');
                });
                popover.classList.toggle('hidden', !opening);
                toggle.setAttribute('aria-expanded', opening ? 'true' : 'false');
                if (opening && root.AgentAppearanceDropdown) {
                    root.AgentAppearanceDropdown.place(selector, context.container);
                }
                if (opening && options[0]) options.find(function (option) {
                    return option.getAttribute('aria-selected') === 'true';
                })?.focus();
            });
            toggle.addEventListener('keydown', function (event) {
                if (event.key === 'Escape') {
                    event.preventDefault();
                    closeSelector();
                }
            });
            options.forEach(function (option, index) {
                option.addEventListener('click', function () {
                    closeSelector();
                    commitField('appearance.' + field, option.getAttribute('data-appearance-option'));
                });
                option.addEventListener('keydown', function (event) {
                    if (event.key === 'Escape') {
                        event.preventDefault();
                        event.stopPropagation();
                        closeSelector();
                        toggle.focus();
                        return;
                    }
                    const delta = event.key === 'ArrowRight' || event.key === 'ArrowDown' ? 1 :
                        (event.key === 'ArrowLeft' || event.key === 'ArrowUp' ? -1 : 0);
                    if (!delta) return;
                    event.preventDefault();
                    options[(index + delta + options.length) % options.length].focus();
                });
            });
        });
        context.container.querySelectorAll('[data-appearance-color]').forEach(function (input) {
            input.addEventListener('change', function () {
                commitField('appearance.' + input.getAttribute('data-appearance-color'), input.value);
            });
        });
        context.container.querySelectorAll('[data-high-risk-action]').forEach(function (button) {
            button.addEventListener('click', function () {
                openHighRiskDialog(button.getAttribute('data-high-risk-action'));
            });
        });
    }

    function highRiskField(action) {
        return {
            provider: 'providerKind',
            branch: 'branch',
            workspace: 'workspace',
            assignment: 'assignment',
            binding: 'providerAgentId',
        }[action] || action;
    }

    function openHighRiskDialog(action) {
        const context = state.context;
        if (!context || context.audience.kind !== 'human' || !isContextActive(context)) return false;
        const host = context.container.querySelector('#agent-high-risk-dialog');
        if (!host) return false;
        const returnFocus = root.document && root.document.activeElement;
        function closeConfirmation() {
            host.innerHTML = '';
            if (returnFocus && typeof returnFocus.focus === 'function') returnFocus.focus();
        }
        const agent = selectedAgent(context);
        const field = highRiskField(action);
        const beforeValue = action === 'create' ? null : (
            action === 'delete' ? { exists: true } : (agent[field] || agent[action] || '')
        );
        const requiresValue = action !== 'delete';
        host.innerHTML = '<div class="ac-confirm-backdrop"><section class="ac-confirm-dialog" role="alertdialog" aria-modal="true" aria-labelledby="ac-confirm-title" aria-describedby="ac-confirm-impact">' +
            '<h4 id="ac-confirm-title">' + esc(tr('agent_confirm_change', 'Confirm high-risk change')) + '</h4>' +
            '<dl id="ac-confirm-impact"><dt>' + esc(tr('agent_target', 'Agent')) + '</dt><dd>' + esc(action === 'create' ? tr('new_agent', 'New Agent') : context.selectedAiId) + '</dd>' +
            '<dt>' + esc(tr('agent_action', 'Action')) + '</dt><dd>' + esc(action) + '</dd>' +
            '<dt>' + esc(tr('agent_before', 'Before')) + '</dt><dd>' + esc(JSON.stringify(beforeValue)) + '</dd>' +
            '<dt>' + esc(tr('agent_after', 'After')) + '</dt><dd>' +
            (requiresValue ? '<input type="text" data-high-risk-value aria-label="' + esc(tr('agent_after', 'After')) + '" value="' +
                esc(action === 'create' ? '' : beforeValue) + '">' : esc(JSON.stringify(null))) + '</dd></dl>' +
            '<p class="ac-confirm-error" role="status"></p><footer><button type="button" data-confirm-cancel>' +
                esc(tr('cancel', 'Cancel')) + '</button><button type="button" class="danger" data-confirm-submit>' +
                esc(tr('confirm', 'Confirm')) + '</button></footer></section></div>';
        const cancel = host.querySelector('[data-confirm-cancel]');
        cancel.addEventListener('click', closeConfirmation);
        host.querySelector('.ac-confirm-backdrop').addEventListener('keydown', function (event) {
            if (event.key === 'Escape') {
                event.preventDefault();
                event.stopPropagation();
                closeConfirmation();
                return;
            }
            if (event.key !== 'Tab') return;
            const focusable = Array.from(host.querySelectorAll('button:not([disabled]), input:not([disabled])'));
            if (!focusable.length) return;
            const first = focusable[0];
            const last = focusable[focusable.length - 1];
            if (event.shiftKey && root.document.activeElement === first) {
                event.preventDefault();
                last.focus();
            } else if (!event.shiftKey && root.document.activeElement === last) {
                event.preventDefault();
                first.focus();
            }
        });
        host.querySelector('[data-confirm-submit]').addEventListener('click', async function (event) {
            const submit = event.currentTarget;
            const valueInput = host.querySelector('[data-high-risk-value]');
            const value = valueInput ? valueInput.value.trim() : '';
            let targetAiId = context.selectedAiId;
            let before = action === 'create' ? null : (
                action === 'delete' ? { exists: true } : { [field]: beforeValue }
            );
            let after;
            if (action === 'create') {
                targetAiId = value.toLowerCase().replace(/[^a-z0-9_-]+/g, '-').replace(/^-|-$/g, '');
                after = { id: targetAiId, name: value, providerKind: 'openclaw' };
            } else if (action === 'delete') {
                after = null;
            } else {
                after = { [field]: value };
            }
            const error = host.querySelector('.ac-confirm-error');
            if (!targetAiId || (requiresValue && !value)) {
                error.textContent = tr('agent_change_invalid', 'A new value is required');
                return;
            }
            submit.disabled = true;
            try {
                const adapter = context.adapter;
                if (!adapter || typeof adapter.applyHighRisk !== 'function') {
                    throw Object.assign(new Error('agent_management_command_unavailable'), { status: 503 });
                }
                await adapter.applyHighRisk({
                    targetAiId: targetAiId,
                    action: action,
                    before: before,
                    after: after,
                    revision: action === 'create' ? 0 : Number((state.profiles.get(context.selectedAiId) || {}).revision || 0),
                });
                closeConfirmation();
                state.profiles.delete(context.selectedAiId);
                if (context.reportMutation) context.reportMutation({ state: 'saved', action: action, message: tr('agent_change_applied', 'Change applied') });
                if (root.AgentManagement) root.AgentManagement.bootstrapAudience();
                load(context);
            } catch (failure) {
                submit.disabled = false;
                error.textContent = failure && failure.message || tr('agent_change_failed', 'Change failed');
            }
        });
        const input = host.querySelector('[data-high-risk-value]');
        (input || host.querySelector('[data-confirm-submit]')).focus();
        return true;
    }

    async function load(context) {
        const aiId = context.selectedAiId;
        if (!aiId) {
            if (!isContextActive(context)) return;
            context.container.innerHTML = '<div class="am-empty">' + esc(tr('agent_management_empty', 'No Agent selected')) + '</div>';
            return;
        }
        const agent = selectedAgent(context);
        if (state.profiles.has(aiId)) {
            renderProfile(context, state.profiles.get(aiId));
            return;
        }
        if (!isContextActive(context)) return;
        renderProfile(context, previewProfile(agent));
        state.loading.add(aiId);
        try {
            const payload = await requestProfile(context, aiId);
            const profile = normalizeProfile(payload, agent);
            state.profiles.set(aiId, profile);
            if (state.context && state.context.selectedAiId === aiId && isContextActive(state.context)) {
                renderProfile(state.context, profile);
            }
        } catch (error) {
            state.errors.set(aiId, String(error && error.message || 'agent_profile_load_failed'));
            if (state.context && state.context.selectedAiId === aiId && isContextActive(state.context)) {
                if (String(error && (error.code || error.message) || '') === 'agent_profile_not_found') {
                    renderProfile(state.context, previewProfile(agent, 'unregistered'));
                } else {
                    state.context.container.innerHTML = '<div class="am-empty ac-error">' +
                        esc(tr('agent_configuration_failed', 'Agent configuration could not be loaded')) + '</div>';
                }
            }
        } finally {
            state.loading.delete(aiId);
        }
    }

    function mount(context) {
        state.context = context;
        load(context);
    }

    const api = {
        state: state,
        mount: mount,
        reload: function (aiId) {
            state.profiles.delete(aiId || (state.context && state.context.selectedAiId));
            if (state.context) return load(state.context);
        },
        commitField: commitField,
        undoField: undoField,
        openHighRiskDialog: openHighRiskDialog,
        helpers: {
            canEdit: canEdit,
            canSeeRestricted: canSeeRestricted,
            visibleSections: visibleSections,
            normalizeProfile: normalizeProfile,
            previewProfile: previewProfile,
            normalizeFieldValue: normalizeFieldValue,
            classifySaveError: classifySaveError,
            fieldStatus: fieldStatus,
            isContextActive: isContextActive,
            appearanceOptionLabel: appearanceOptionLabel,
            appearanceOptions: APPEARANCE_OPTIONS,
            renderAppearance: renderAppearance,
            highRiskField: highRiskField,
        },
    };

    root.AgentConfiguration = api;
    if (root.AgentManagement) root.AgentManagement.mountTab('configuration', api);
    if (typeof module !== 'undefined' && module.exports) module.exports = api;
})(typeof window !== 'undefined' ? window : globalThis);
