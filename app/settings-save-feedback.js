(function initSettingsSaveFeedback(global) {
    'use strict';

    var documentRef = global && global.document;
    var COPY = {
        settings_save_saving: 'Saving settings…',
        settings_save_success: 'Settings saved',
        settings_save_failed: 'Save failed',
    };
    var currentState = { kind: 'idle', detail: '' };

    function translated(key) {
        var i18n = global && global.i18n;
        if (i18n && typeof i18n.t === 'function') {
            var value = i18n.t(key);
            if (value && value !== key) return value;
        }
        return COPY[key] || key;
    }

    function saveButton() {
        return documentRef && documentRef.querySelector('.settings-modal-footer .mm-save-all');
    }

    function mount() {
        if (!documentRef) return null;
        var existing = documentRef.getElementById('settings-save-status');
        if (existing) return existing;
        var footer = documentRef.querySelector('.settings-modal-footer');
        if (!footer) return null;
        var status = documentRef.createElement('div');
        status.id = 'settings-save-status';
        status.className = 'settings-save-status';
        status.hidden = true;
        status.setAttribute('role', 'status');
        status.setAttribute('aria-live', 'polite');
        status.setAttribute('aria-atomic', 'true');
        footer.insertBefore(status, saveButton() || null);
        return status;
    }

    function messageForState() {
        if (currentState.kind === 'saving') return translated('settings_save_saving');
        if (currentState.kind === 'success') return translated('settings_save_success');
        if (currentState.kind === 'error') {
            var base = translated('settings_save_failed');
            return currentState.detail ? base + ': ' + currentState.detail : base;
        }
        return '';
    }

    function render() {
        var status = mount();
        if (!status) return null;
        var button = saveButton();
        var busy = currentState.kind === 'saving';
        if (button) {
            button.disabled = busy;
            button.setAttribute('aria-busy', busy ? 'true' : 'false');
        }
        status.hidden = currentState.kind === 'idle';
        status.className = 'settings-save-status is-' + currentState.kind;
        status.setAttribute('data-state', currentState.kind);
        status.textContent = messageForState();
        return status;
    }

    function setState(kind, detail) {
        currentState = { kind: kind, detail: String(detail || '') };
        return render();
    }

    function start() { return setState('saving'); }
    function success() { return setState('success'); }
    function failure(message) { return setState('error', message); }
    function updateLabels() { return render(); }

    var api = { mount: mount, start: start, success: success, failure: failure, updateLabels: updateLabels };
    global.VOSettingsSaveFeedback = api;
    if (typeof module !== 'undefined' && module.exports) module.exports = api;

    if (global && typeof global.addEventListener === 'function') {
        global.addEventListener('i18n:ready', updateLabels);
        global.addEventListener('i18n:changed', updateLabels);
    }
    if (documentRef) {
        if (documentRef.readyState === 'loading') documentRef.addEventListener('DOMContentLoaded', mount);
        else mount();
    }
})(typeof window !== 'undefined' ? window : globalThis);
