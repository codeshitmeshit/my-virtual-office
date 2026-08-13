(function initManagementSessionReadiness(root) {
    'use strict';

    var AUTHENTICATED_EVENT = 'management-session:authenticated';

    function isAuthenticated() {
        return !document.documentElement.classList.contains('management-session-pending');
    }

    function whenAuthenticated(callback) {
        if (typeof callback !== 'function') return function () {};
        if (isAuthenticated()) {
            callback();
            return function () {};
        }

        function handleAuthenticated() {
            callback();
        }

        root.addEventListener(AUTHENTICATED_EVENT, handleAuthenticated, { once: true });
        return function cancel() {
            root.removeEventListener(AUTHENTICATED_EVENT, handleAuthenticated);
        };
    }

    root.VOManagementSessionReadiness = Object.freeze({
        isAuthenticated: isAuthenticated,
        whenAuthenticated: whenAuthenticated
    });
})(window);
