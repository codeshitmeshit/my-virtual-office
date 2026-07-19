(function (root) {
    'use strict';

    const state = {
        open: false,
        selectedAgentId: '',
    };

    function modal() {
        return root.document ? root.document.getElementById('humanResourcesModal') : null;
    }

    function detail() {
        return root.document ? root.document.querySelector('.hr-agent-detail') : null;
    }

    function open() {
        const element = modal();
        if (!element) return false;
        state.open = true;
        element.classList.remove('hidden');
        const target = detail();
        if (target && typeof target.focus === 'function') target.focus();
        return true;
    }

    function close() {
        const element = modal();
        if (!element) return false;
        state.open = false;
        element.classList.add('hidden');
        return true;
    }

    const api = { state, open, close };
    root.HumanResources = api;
    root.openHumanResources = open;
    root.closeHumanResources = close;

    if (typeof module !== 'undefined' && module.exports) module.exports = api;
})(typeof window !== 'undefined' ? window : globalThis);
