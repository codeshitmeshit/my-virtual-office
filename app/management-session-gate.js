(function (root) {
    'use strict';

    var STORAGE_KEY = 'voManagementToken';
    var PROBE_PATH = '/api/management/session';
    var PROBE_TIMEOUT_MS = 8000;
    var gatePromise = null;
    var gateResolve = null;
    var elements = null;
    var state = 'idle';

    var FALLBACK = {
        management_gate_checking_title: { en: 'Checking management access', zh: '正在检测管理权限' },
        management_gate_checking_body: { en: 'Verifying the login state for this tab...', zh: '正在验证当前标签页的登录状态…' },
        management_gate_login_title: { en: 'Management sign in', zh: '管理登录' },
        management_gate_login_prompt: { en: 'Enter the management token printed by the Virtual Office server to continue.', zh: '请输入 Virtual Office 服务端输出的管理令牌，验证后进入。' },
        management_gate_field_label: { en: 'Management token', zh: '管理令牌' },
        management_gate_retry: { en: 'Check again', zh: '重新检测' },
        management_gate_submit: { en: 'Verify and enter', zh: '验证并进入' },
        management_gate_validating: { en: 'Verifying...', zh: '正在验证…' },
        management_gate_invalid: { en: 'The management token is invalid.', zh: '管理令牌无效，请检查后重试。' },
        management_gate_timeout: { en: 'Verification timed out. Check the server connection and try again.', zh: '验证超时，请检查服务连接后重试。' },
        management_gate_network_error: { en: 'Could not verify access. Check the server connection and try again.', zh: '暂时无法验证权限，请检查服务连接后重试。' },
        management_token_placeholder: { en: 'Enter management token', zh: '请输入管理令牌' }
    };

    function language() {
        var current = root.i18n && typeof root.i18n.getLanguage === 'function'
            ? root.i18n.getLanguage()
            : '';
        if (current === 'zh' || current === 'en') return current;
        return String((root.navigator || {}).language || '').toLowerCase().indexOf('zh') >= 0 ? 'zh' : 'en';
    }

    function tr(key) {
        if (root.i18n && typeof root.i18n.t === 'function') {
            var translated = root.i18n.t(key);
            if (translated && translated !== key) return translated;
        }
        var fallback = FALLBACK[key];
        return fallback ? fallback[language()] : key;
    }

    function createElement(tag, className, text) {
        var node = document.createElement(tag);
        if (className) node.className = className;
        if (text) node.textContent = text;
        return node;
    }

    function mount() {
        if (elements) return elements;
        var gate = createElement('div', 'management-session-gate');
        gate.id = 'management-session-gate';
        gate.setAttribute('role', 'presentation');

        var card = createElement('section', 'management-session-card');
        card.tabIndex = -1;
        card.setAttribute('role', 'dialog');
        card.setAttribute('aria-modal', 'true');
        card.setAttribute('aria-labelledby', 'management-session-title');
        card.setAttribute('aria-describedby', 'management-session-description');

        var heading = createElement('div', 'management-session-heading');
        var icon = createElement('span', 'management-session-heading-icon', '🔒');
        icon.setAttribute('aria-hidden', 'true');
        var title = createElement('h1', 'management-session-title');
        title.id = 'management-session-title';
        heading.appendChild(icon);
        heading.appendChild(title);

        var description = createElement('p', 'management-session-description');
        description.id = 'management-session-description';

        var checking = createElement('div', 'management-session-checking');
        var spinner = createElement('span', 'management-session-spinner');
        spinner.setAttribute('aria-hidden', 'true');
        var checkingText = createElement('span', 'management-session-checking-text');
        checking.appendChild(spinner);
        checking.appendChild(checkingText);

        var form = createElement('form', 'management-session-form');
        form.hidden = true;
        var label = createElement('label', 'management-session-label');
        label.setAttribute('for', 'management-session-input');
        var input = createElement('input', 'management-session-input');
        input.id = 'management-session-input';
        input.type = 'password';
        input.autocomplete = 'current-password';
        input.spellcheck = false;
        var status = createElement('div', 'management-session-status');
        status.id = 'management-session-status';
        status.setAttribute('role', 'status');
        status.setAttribute('aria-live', 'polite');
        var actions = createElement('div', 'management-session-actions');
        var retry = createElement('button', 'mtg-btn');
        retry.type = 'button';
        var submit = createElement('button', 'mtg-btn mtg-btn-end');
        submit.type = 'submit';
        submit.disabled = true;
        actions.appendChild(retry);
        actions.appendChild(submit);
        form.appendChild(label);
        form.appendChild(input);
        form.appendChild(status);
        form.appendChild(actions);

        card.appendChild(heading);
        card.appendChild(description);
        card.appendChild(checking);
        card.appendChild(form);
        gate.appendChild(card);
        document.body.appendChild(gate);

        elements = { gate: gate, card: card, title: title, description: description, checking: checking, checkingText: checkingText, form: form, label: label, input: input, status: status, retry: retry, submit: submit };
        input.addEventListener('input', function () {
            submit.disabled = state === 'validating' || !input.value.trim();
            if (status.classList.contains('is-error')) setStatus('', false);
        });
        form.addEventListener('submit', function (event) {
            event.preventDefault();
            validateInput();
        });
        retry.addEventListener('click', function () {
            if (elements.input.value.trim()) validateInput();
            else checkStoredSession();
        });
        gate.addEventListener('click', function (event) {
            if (event.target === gate) elements.card.focus();
        });
        document.addEventListener('keydown', trapKeyboard, true);
        root.addEventListener('i18n:ready', updateCopy);
        root.addEventListener('i18n:changed', updateCopy);
        updateCopy();
        return elements;
    }

    function updateCopy() {
        if (!elements) return;
        var checking = state === 'checking';
        elements.title.textContent = tr(checking ? 'management_gate_checking_title' : 'management_gate_login_title');
        elements.description.textContent = tr(checking ? 'management_gate_checking_body' : 'management_gate_login_prompt');
        elements.checkingText.textContent = tr('management_gate_checking_body');
        elements.label.textContent = tr('management_gate_field_label');
        elements.input.placeholder = tr('management_token_placeholder');
        elements.retry.textContent = tr('management_gate_retry');
        elements.submit.textContent = state === 'validating' ? tr('management_gate_validating') : tr('management_gate_submit');
    }

    function setStatus(message, isError) {
        if (!elements) return;
        elements.status.textContent = message || '';
        elements.status.className = 'management-session-status' + (isError ? ' is-error' : '');
        elements.status.setAttribute('role', isError ? 'alert' : 'status');
    }

    function showChecking() {
        mount();
        state = 'checking';
        elements.checking.hidden = false;
        elements.form.hidden = true;
        updateCopy();
    }

    function showLogin(errorKey) {
        mount();
        state = 'login';
        elements.checking.hidden = true;
        elements.form.hidden = false;
        elements.retry.disabled = false;
        elements.submit.disabled = !elements.input.value.trim();
        setStatus(errorKey ? tr(errorKey) : '', Boolean(errorKey));
        updateCopy();
        setTimeout(function () { elements.input.focus(); }, 0);
    }

    function setValidating() {
        state = 'validating';
        elements.retry.disabled = true;
        elements.submit.disabled = true;
        setStatus(tr('management_gate_validating'), false);
        updateCopy();
    }

    async function probe(token) {
        var headers = new Headers();
        if (token) headers.set('X-VO-Management-Token', token);
        var controller = typeof AbortController === 'function' ? new AbortController() : null;
        var timeoutId = null;
        var timeout = new Promise(function (_resolve, reject) {
            timeoutId = setTimeout(function () {
                if (controller) controller.abort();
                var error = new Error('management_session_probe_timeout');
                error.code = 'management_session_probe_timeout';
                reject(error);
            }, PROBE_TIMEOUT_MS);
        });
        var requestOptions = {
            method: 'GET',
            headers: headers,
            cache: 'no-store',
            credentials: 'same-origin'
        };
        if (controller) requestOptions.signal = controller.signal;
        var response;
        try {
            response = await Promise.race([root.fetch(PROBE_PATH, requestOptions), timeout]);
        } finally {
            if (timeoutId !== null) clearTimeout(timeoutId);
        }
        if (response.ok) return { authenticated: true, response: response };
        var payload = null;
        try { payload = await response.clone().json(); } catch (_error) {}
        if (response.status === 403 && payload && payload.code === 'management_token_required') {
            return { authenticated: false, invalid: Boolean(token), response: response };
        }
        throw new Error('management_session_probe_failed');
    }

    function complete(token) {
        sessionStorage.setItem(STORAGE_KEY, token);
        state = 'authenticated';
        document.documentElement.classList.remove('management-session-pending');
        if (elements) {
            document.removeEventListener('keydown', trapKeyboard, true);
            elements.gate.remove();
            elements = null;
        }
        if (gateResolve) gateResolve(token);
        gateResolve = null;
        gatePromise = null;
        root.dispatchEvent(new CustomEvent('management-session:authenticated'));
        return token;
    }

    async function checkStoredSession() {
        showChecking();
        var token = sessionStorage.getItem(STORAGE_KEY) || '';
        try {
            var result = await probe(token);
            if (result.authenticated && token) return complete(token);
            if (token) sessionStorage.removeItem(STORAGE_KEY);
            showLogin(result.invalid ? 'management_gate_invalid' : '');
        } catch (error) {
            showLogin(error && error.code === 'management_session_probe_timeout'
                ? 'management_gate_timeout'
                : 'management_gate_network_error');
        }
        return '';
    }

    async function validateInput() {
        var token = elements ? elements.input.value.trim() : '';
        if (!token || state === 'validating') return;
        setValidating();
        try {
            var result = await probe(token);
            if (result.authenticated) {
                complete(token);
                return;
            }
            sessionStorage.removeItem(STORAGE_KEY);
            showLogin('management_gate_invalid');
        } catch (error) {
            showLogin(error && error.code === 'management_session_probe_timeout'
                ? 'management_gate_timeout'
                : 'management_gate_network_error');
        }
    }

    function trapKeyboard(event) {
        if (!elements) return;
        if (event.key === 'Escape') {
            event.preventDefault();
            event.stopPropagation();
            return;
        }
        if (event.key !== 'Tab') return;
        var focusable = [elements.input, elements.retry, elements.submit].filter(function (node) { return !node.disabled && !node.hidden; });
        if (!focusable.length) return;
        var first = focusable[0];
        var last = focusable[focusable.length - 1];
        if (event.shiftKey && document.activeElement === first) {
            event.preventDefault();
            last.focus();
        } else if (!event.shiftKey && document.activeElement === last) {
            event.preventDefault();
            first.focus();
        }
    }

    function requireAuthentication() {
        var stored = sessionStorage.getItem(STORAGE_KEY) || '';
        if (state === 'authenticated' && stored) return Promise.resolve(stored);
        if (!gatePromise) {
            gatePromise = new Promise(function (resolve) { gateResolve = resolve; });
        }
        document.documentElement.classList.add('management-session-pending');
        showLogin('');
        return gatePromise;
    }

    function init() {
        document.documentElement.classList.add('management-session-pending');
        mount();
        if (root.i18n && typeof root.i18n.setManagementAccessHandler === 'function') {
            root.i18n.setManagementAccessHandler(requireAuthentication);
        }
        checkStoredSession();
    }

    root.ManagementSessionGate = Object.freeze({
        init: init,
        probe: probe,
        requireAuthentication: requireAuthentication
    });

    if (document.body) init();
    else document.addEventListener('DOMContentLoaded', init, { once: true });
})(window);
