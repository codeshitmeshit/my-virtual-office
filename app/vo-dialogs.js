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
        if (!doc || doc.getElementById('vo-dialog-styles')) return;
        var style = doc.createElement('style');
        style.id = 'vo-dialog-styles';
        style.textContent = [
            '.vo-dialog-overlay{position:fixed;inset:0;z-index:15000;display:flex;align-items:center;justify-content:center;padding:18px;background:rgba(5,6,18,.72);backdrop-filter:blur(2px)}',
            '.vo-dialog-box{width:min(460px,calc(100vw - 28px));max-height:min(86vh,560px);overflow:auto;border:2px solid var(--gold,var(--accent,#ffd700));border-radius:8px;background:var(--ui-surface,var(--surface,#141428));box-shadow:0 18px 60px rgba(0,0,0,.5);color:var(--ui-text,var(--text,#d8d8e8));font-family:inherit;padding:18px}',
            '.vo-dialog-title{margin:0 0 12px;color:var(--gold,var(--accent,#ffd700));font-size:12px;line-height:1.55}',
            '.vo-dialog-message{white-space:pre-wrap;word-break:break-word;font-size:11px;line-height:1.75;color:var(--ui-text,var(--text,#d8d8e8))}',
            '.vo-dialog-input{display:block;width:100%;box-sizing:border-box;margin-top:14px;border:1px solid var(--ui-border,var(--border,#2a2a4a));border-radius:4px;background:rgba(0,0,0,.42);color:var(--ui-text,var(--text,#d8d8e8));font:inherit;font-size:11px;line-height:1.5;padding:10px;outline:none}',
            '.vo-dialog-input:focus{border-color:var(--gold,var(--accent,#ffd700));box-shadow:0 0 0 2px rgba(255,215,0,.14)}',
            '.vo-dialog-actions{display:flex;justify-content:flex-end;gap:8px;flex-wrap:wrap;margin-top:18px}',
            '.vo-dialog-actions button{border:1px solid var(--ui-border,var(--border,#2a2a4a));border-radius:6px;background:var(--surface2,#202040);color:var(--ui-text,var(--text,#d8d8e8));font:inherit;font-size:9px;line-height:1.4;padding:8px 12px;cursor:pointer;min-width:84px}',
            '.vo-dialog-actions .vo-dialog-primary{border-color:var(--gold,var(--accent,#ffd700));background:var(--gold,var(--accent,#ffd700));color:#111}',
            '.vo-dialog-actions .vo-dialog-danger{border-color:#f44336;background:#f44336;color:#fff}'
        ].join('');
        doc.head.appendChild(style);
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
            title.textContent = options.title || (kind === 'confirm' ? tr('confirm', 'Confirm') : kind === 'prompt' ? tr('input', 'Input') : tr('notice', 'Notice'));
            box.appendChild(title);

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
