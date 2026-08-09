(function initVOFeedback(global) {
    'use strict';

    var documentRef = global && global.document;
    var feedbackQueue = [];
    var nextId = 1;
    var DEFAULT_DURATION = 4500;
    var VALID_TONES = { info: true, success: true, warning: true, error: true };

    function normalizeTone(tone) {
        var value = String(tone || 'info').toLowerCase();
        if (value === 'danger' || value === 'failed' || value === 'failure') value = 'error';
        return VALID_TONES[value] ? value : 'info';
    }

    function inferLegacyTone(message, tone) {
        if (tone) return normalizeTone(tone);
        var value = String(message || '');
        if (/❌|failed|failure|error|失败|错误/i.test(value)) return 'error';
        if (/⚠|warning|警告/i.test(value)) return 'warning';
        if (/✅|saved|success|成功|已保存|已完成/i.test(value)) return 'success';
        return 'info';
    }

    function ensureRegion() {
        if (!documentRef) return null;
        var region = documentRef.getElementById('vo-feedback-region');
        if (region) return region;
        region = documentRef.createElement('section');
        region.id = 'vo-feedback-region';
        region.className = 'vo-feedback-region';
        region.setAttribute('aria-label', 'Notifications');
        documentRef.body.appendChild(region);
        return region;
    }

    function remove(id) {
        var index = feedbackQueue.findIndex(function(item) { return item.id === id; });
        if (index < 0) return false;
        var item = feedbackQueue[index];
        feedbackQueue.splice(index, 1);
        if (item.timer) global.clearTimeout(item.timer);
        if (item.element && item.element.parentNode) item.element.parentNode.removeChild(item.element);
        return true;
    }

    function createButton(className, label, handler) {
        var button = documentRef.createElement('button');
        button.type = 'button';
        button.className = className;
        button.textContent = label;
        button.addEventListener('click', handler);
        return button;
    }

    function toneIcon(tone) {
        if (tone === 'success') return '✓';
        if (tone === 'warning' || tone === 'error') return '!';
        return 'i';
    }

    function render(item) {
        var region = ensureRegion();
        if (!region) return null;
        var element = documentRef.createElement('article');
        element.className = 'vo-feedback-item';
        element.setAttribute('data-feedback-id', item.id);
        element.setAttribute('data-tone', item.tone);
        element.setAttribute('role', item.tone === 'error' ? 'alert' : 'status');
        element.setAttribute('aria-live', item.tone === 'error' ? 'assertive' : 'polite');
        element.setAttribute('aria-atomic', 'true');

        var icon = documentRef.createElement('span');
        icon.className = 'vo-feedback-icon';
        icon.setAttribute('aria-hidden', 'true');
        icon.textContent = toneIcon(item.tone);
        element.appendChild(icon);

        var content = documentRef.createElement('span');
        content.className = 'vo-feedback-content';
        if (item.title) {
            var title = documentRef.createElement('strong');
            title.className = 'vo-feedback-title';
            title.textContent = item.title;
            content.appendChild(title);
        }
        var message = documentRef.createElement('span');
        message.className = 'vo-feedback-message';
        message.textContent = item.message;
        content.appendChild(message);
        element.appendChild(content);

        var actions = documentRef.createElement('span');
        actions.className = 'vo-feedback-actions';
        if (item.action) {
            actions.appendChild(createButton('vo-feedback-action', item.action.label, function() {
                item.action.onClick();
                remove(item.id);
            }));
        }
        actions.appendChild(createButton('vo-feedback-dismiss', '×', function() { remove(item.id); }));
        actions.lastChild.setAttribute('aria-label', 'Dismiss notification');
        element.appendChild(actions);
        region.appendChild(element);
        return element;
    }

    function show(options) {
        if (typeof options === 'string') options = { message: options };
        options = options || {};
        var tone = normalizeTone(options.tone);
        var persistent = options.persistent == null ? tone === 'error' : Boolean(options.persistent);
        var duration = Number(options.duration);
        if (!Number.isFinite(duration) || duration < 0) duration = DEFAULT_DURATION;
        var action = options.action && typeof options.action.onClick === 'function'
            ? { label: String(options.action.label || 'Retry'), onClick: options.action.onClick }
            : null;
        var item = {
            id: 'vo-feedback-' + nextId++,
            title: String(options.title || ''),
            message: String(options.message || ''),
            tone: tone,
            persistent: persistent,
            duration: duration,
            action: action,
            element: null,
            timer: null,
        };
        feedbackQueue.push(item);
        item.element = render(item);
        if (!persistent && duration > 0) {
            item.timer = global.setTimeout(function() { remove(item.id); }, duration);
        }
        return item.id;
    }

    function clear() {
        feedbackQueue.slice().forEach(function(item) { remove(item.id); });
    }

    function snapshot() {
        return feedbackQueue.map(function(item) {
            return { id: item.id, title: item.title, message: item.message, tone: item.tone, persistent: item.persistent };
        });
    }

    // 旧入口只负责语义归一化；队列、计时器和可访问性由此模块唯一管理。
    function legacy(message, tone, options) {
        var config = options || {};
        config.message = message;
        config.tone = inferLegacyTone(message, tone);
        return show(config);
    }

    var api = { show: show, remove: remove, clear: clear, snapshot: snapshot, legacy: legacy };
    global.VOFeedback = api;
    if (typeof module !== 'undefined' && module.exports) module.exports = api;
})(typeof window !== 'undefined' ? window : globalThis);
