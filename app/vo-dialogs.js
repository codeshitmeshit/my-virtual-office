(function (root) {
    'use strict';

    var doc = root.document;
    var activeDialog = null;

    function tr(key, fallback) {
        try {
            if (root.i18n && typeof root.i18n.t === 'function') {
                return root.i18n.t(key) || fallback;
            }
        } catch (_e) {}
        return fallback;
    }

    function text(value) {
        return value == null ? '' : String(value);
    }

    function ensureStyles() {
        // 样式由 ui-dialogs.css 统一负责；这里保留函数边界，避免改变 show() 的调用时序。
    }

    function removeActive(result) {
        if (!activeDialog) return;
        var dialog = activeDialog;
        activeDialog = null;
        if (dialog.keydown) doc.removeEventListener('keydown', dialog.keydown);
        if (dialog.overlay && dialog.overlay.parentNode) dialog.overlay.parentNode.removeChild(dialog.overlay);
        dialog.resolve(result);
    }

    function show(options) {
        if (!doc || !doc.body) {
            return Promise.resolve(options.kind === 'confirm' ? false : options.kind === 'prompt' ? null : undefined);
        }
        ensureStyles();
        if (activeDialog) removeActive(activeDialog.kind === 'confirm' ? false : activeDialog.kind === 'prompt' ? null : undefined);
        return new Promise(function (resolve) {
            var kind = options.kind || 'alert';
            var overlay = doc.createElement('div');
            overlay.className = 'vo-dialog-overlay';
            overlay.setAttribute('role', 'presentation');

            var box = doc.createElement('section');
            box.className = 'vo-dialog-box';
            box.setAttribute('role', 'dialog');
            box.setAttribute('aria-modal', 'true');

            var title = doc.createElement('h2');
            title.className = 'vo-dialog-title';
            title.id = 'vo-dialog-title';
            title.textContent = options.title || (kind === 'confirm' ? tr('confirm', 'Confirm') : kind === 'prompt' ? tr('input', 'Input') : tr('notice', 'Notice'));
            box.appendChild(title);
            box.setAttribute('aria-labelledby', title.id);

            if (options.message) {
                var message = doc.createElement('div');
                message.className = 'vo-dialog-message';
                message.textContent = text(options.message);
                box.appendChild(message);
            }

            var input = null;
            if (kind === 'prompt') {
                input = doc.createElement(options.multiline ? 'textarea' : 'input');
                input.className = 'vo-dialog-input';
                input.value = text(options.defaultValue);
                input.placeholder = text(options.placeholder);
                input.addEventListener('keydown', function (event) {
                    if (event.key === 'Enter' && !options.multiline) {
                        event.preventDefault();
                        removeActive(input.value);
                    }
                });
                box.appendChild(input);
            }

            var actions = doc.createElement('div');
            actions.className = 'vo-dialog-actions';

            function button(label, className, value) {
                var btn = doc.createElement('button');
                btn.type = 'button';
                btn.className = className || '';
                btn.textContent = label;
                btn.addEventListener('click', function () {
                    if (kind === 'prompt' && value === true) removeActive(input ? input.value : '');
                    else removeActive(value);
                });
                actions.appendChild(btn);
                return btn;
            }

            if (kind !== 'alert') button(options.cancelText || tr('cancel', 'Cancel'), '', kind === 'prompt' ? null : false);
            var okButton = button(options.confirmText || tr('confirm', 'Confirm'), options.tone === 'danger' ? 'vo-dialog-danger' : 'vo-dialog-primary', kind === 'alert' ? undefined : true);
            box.appendChild(actions);
            overlay.appendChild(box);

            // 一个时刻只允许一个 Promise owner，removeActive() 负责 exactly-once resolve 与监听器清理。
            activeDialog = {
                kind: kind,
                overlay: overlay,
                resolve: resolve,
                keydown: function (event) {
                    if (event.key === 'Escape') {
                        event.preventDefault();
                        removeActive(kind === 'alert' ? undefined : kind === 'prompt' ? null : false);
                    } else if (event.key === 'Enter' && kind !== 'prompt') {
                        event.preventDefault();
                        removeActive(kind === 'alert' ? undefined : true);
                    }
                }
            };
            doc.addEventListener('keydown', activeDialog.keydown);
            doc.body.appendChild(overlay);
            (input || okButton).focus();
            if (input) input.select();
        });
    }

    root.VODialogs = {
        showAlert: function (message, options) {
            options = options || {};
            return show({ kind: 'alert', title: options.title, message: message, confirmText: options.confirmText });
        },
        showConfirm: function (message, options) {
            options = options || {};
            return show({ kind: 'confirm', title: options.title, message: message, confirmText: options.confirmText, cancelText: options.cancelText, tone: options.tone });
        },
        showPrompt: function (message, defaultValue, options) {
            options = options || {};
            return show({ kind: 'prompt', title: options.title, message: message, defaultValue: defaultValue, placeholder: options.placeholder, confirmText: options.confirmText, cancelText: options.cancelText, multiline: options.multiline, tone: options.tone });
        }
    };
    root.voAlert = function (message, options) { return root.VODialogs.showAlert(message, options); };
    root.voConfirm = function (message, options) { return root.VODialogs.showConfirm(message, options); };
    root.voPrompt = function (message, defaultValue, options) { return root.VODialogs.showPrompt(message, defaultValue, options); };
})(window);
