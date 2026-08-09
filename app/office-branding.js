(function initOfficeBranding(global) {
    'use strict';

    var documentRef = global && global.document;
    var DEFAULT_TITLE = 'My Virtual Office';
    var MAX_SOURCE_BYTES = 2 * 1024 * 1024;
    var MAX_STORED_BYTES = 32 * 1024;
    var SUPPORTED_TYPES = ['image/png', 'image/jpeg', 'image/webp', 'image/x-icon', 'image/vnd.microsoft.icon'];
    var state = { savedIcon: null, draftIcon: null, processing: false };

    function translated(key, fallback) {
        var i18n = global && global.i18n;
        if (i18n && typeof i18n.t === 'function') {
            var value = i18n.t(key);
            if (value && value !== key) return value;
        }
        return fallback;
    }

    function normalizeName(value) {
        return String(value || '').trim().slice(0, 80) || 'Virtual Office';
    }

    function iconLinks() {
        return documentRef ? Array.prototype.slice.call(documentRef.querySelectorAll('link[rel~="icon"]')) : [];
    }

    function setFavicon(iconDataUrl) {
        iconLinks().forEach(function(link) {
            if (!link.getAttribute('data-office-branding-default')) {
                link.setAttribute('data-office-branding-default', link.getAttribute('href') || 'favicon.png');
            }
            link.setAttribute('href', iconDataUrl || link.getAttribute('data-office-branding-default'));
        });
    }

    function applyBranding(office) {
        office = office || {};
        var name = normalizeName(office.name);
        if (documentRef) {
            documentRef.title = name || DEFAULT_TITLE;
            var brand = documentRef.getElementById('brand-title');
            if (brand) brand.textContent = name.toUpperCase();
        }
        setFavicon(office.iconDataUrl || null);
    }

    function status(kind, message) {
        if (!documentRef) return;
        var element = documentRef.getElementById('mm-office-icon-status');
        if (!element) return;
        element.className = 'mm-help office-branding-status is-' + kind;
        element.textContent = message || '';
    }

    function preview(iconDataUrl) {
        if (!documentRef) return;
        var image = documentRef.getElementById('mm-office-icon-preview');
        if (!image) return;
        image.src = iconDataUrl || image.getAttribute('data-default-src') || 'favicon.png';
        image.classList.toggle('is-default', !iconDataUrl);
    }

    function setProcessing(processing) {
        state.processing = !!processing;
        if (!documentRef) return;
        var save = documentRef.querySelector('.settings-modal-footer .mm-save-all');
        if (save) save.disabled = state.processing;
        var input = documentRef.getElementById('mm-office-icon-file');
        if (input) input.disabled = state.processing;
    }

    function estimateDataBytes(dataUrl) {
        var encoded = String(dataUrl || '').split(',')[1] || '';
        return Math.ceil(encoded.length * 3 / 4);
    }

    function readFileAsDataUrl(file) {
        return new Promise(function(resolve, reject) {
            var reader = new global.FileReader();
            reader.onload = function() { resolve(reader.result); };
            reader.onerror = function() { reject(new Error(translated('office_icon_read_failed', 'Could not read this image.'))); };
            reader.readAsDataURL(file);
        });
    }

    function resizeDataUrl(dataUrl, size) {
        return new Promise(function(resolve, reject) {
            var image = new global.Image();
            image.onload = function() {
                var scale = Math.min(1, size / Math.max(image.naturalWidth || image.width, image.naturalHeight || image.height));
                var width = Math.max(1, Math.round((image.naturalWidth || image.width) * scale));
                var height = Math.max(1, Math.round((image.naturalHeight || image.height) * scale));
                var canvas = documentRef.createElement('canvas');
                canvas.width = width;
                canvas.height = height;
                var context = canvas.getContext('2d');
                context.clearRect(0, 0, width, height);
                context.drawImage(image, 0, 0, width, height);
                resolve(canvas.toDataURL('image/png'));
            };
            image.onerror = function() { reject(new Error(translated('office_icon_invalid', 'The selected file is not a valid image.'))); };
            image.src = dataUrl;
        });
    }

    function selectFile(file) {
        if (!file) return Promise.resolve(null);
        if (SUPPORTED_TYPES.indexOf(String(file.type || '').toLowerCase()) < 0) {
            status('error', translated('office_icon_format_error', 'Choose a PNG, JPG, WebP, or ICO image.'));
            return Promise.resolve(null);
        }
        if (Number(file.size || 0) > MAX_SOURCE_BYTES) {
            status('error', translated('office_icon_size_error', 'Choose an image smaller than 2 MB.'));
            return Promise.resolve(null);
        }
        setProcessing(true);
        status('processing', translated('office_icon_processing', 'Processing icon…'));
        return readFileAsDataUrl(file)
            .then(function(dataUrl) { return resizeDataUrl(dataUrl, 128); })
            .then(function(icon) {
                if (estimateDataBytes(icon) <= MAX_STORED_BYTES) return icon;
                return resizeDataUrl(icon, 64);
            })
            .then(function(icon) {
                if (estimateDataBytes(icon) > MAX_STORED_BYTES) throw new Error(translated('office_icon_processed_too_large', 'This image is still too large after processing.'));
                state.draftIcon = icon;
                preview(icon);
                status('ready', translated('office_icon_ready', 'Icon ready. Save settings to apply it.'));
                return icon;
            })
            .catch(function(error) {
                status('error', error.message || String(error));
                return null;
            })
            .finally(function() { setProcessing(false); });
    }

    function clearDraftIcon() {
        state.draftIcon = null;
        preview(null);
        status('ready', translated('office_icon_removed_draft', 'Icon will be removed after you save settings.'));
    }

    function loadFromConfig(office) {
        office = office || {};
        state.savedIcon = office.iconDataUrl || null;
        state.draftIcon = state.savedIcon;
        preview(state.draftIcon);
        applyBranding(office);
    }

    function buildOfficePayload(name) {
        return { name: normalizeName(name), iconDataUrl: state.draftIcon || null };
    }

    function applySavedOffice(office) {
        state.savedIcon = (office || {}).iconDataUrl || null;
        state.draftIcon = state.savedIcon;
        applyBranding(office);
        preview(state.savedIcon);
    }

    function bind() {
        if (!documentRef) return;
        var input = documentRef.getElementById('mm-office-icon-file');
        if (input && !input.getAttribute('data-office-branding-bound')) {
            input.setAttribute('data-office-branding-bound', 'true');
            input.addEventListener('change', function() { selectFile((input.files || [])[0]); });
        }
        var clear = documentRef.getElementById('mm-office-icon-clear');
        if (clear && !clear.getAttribute('data-office-branding-bound')) {
            clear.setAttribute('data-office-branding-bound', 'true');
            clear.addEventListener('click', clearDraftIcon);
        }
    }

    function initialize() {
        bind();
        if (typeof global.fetch !== 'function') return;
        global.fetch('/vo-config').then(function(response) { return response.json(); }).then(function(config) {
            loadFromConfig((config || {}).office || {});
        }).catch(function() {});
    }

    var api = {
        applyBranding: applyBranding,
        applySavedOffice: applySavedOffice,
        buildOfficePayload: buildOfficePayload,
        clearDraftIcon: clearDraftIcon,
        loadFromConfig: loadFromConfig,
        selectFile: selectFile,
        state: state,
    };
    global.VOOfficeBranding = api;
    if (typeof module !== 'undefined' && module.exports) module.exports = api;
    if (documentRef) {
        if (documentRef.readyState === 'loading') documentRef.addEventListener('DOMContentLoaded', initialize);
        else initialize();
    }
})(typeof window !== 'undefined' ? window : globalThis);
