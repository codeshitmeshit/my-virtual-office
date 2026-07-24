(function (root) {
    'use strict';

    function place(selector, boundary) {
        if (!selector) return false;
        const popover = selector.querySelector('.ac-option-popover');
        const toggle = selector.querySelector('.ac-selector-current');
        if (!popover || !toggle || !boundary) return false;

        selector.classList.remove('opens-upward');
        const boundaryRect = boundary.getBoundingClientRect();
        const toggleRect = toggle.getBoundingClientRect();
        const menuHeight = popover.scrollHeight;
        const roomBelow = boundaryRect.bottom - toggleRect.bottom - 8;
        const roomAbove = toggleRect.top - boundaryRect.top - 8;
        const opensUpward = roomBelow < menuHeight && roomAbove > roomBelow;
        selector.classList.toggle('opens-upward', opensUpward);
        return opensUpward;
    }

    function reset(selector) {
        if (selector) selector.classList.remove('opens-upward');
    }

    root.AgentAppearanceDropdown = {
        place: place,
        reset: reset,
    };

    if (typeof module !== 'undefined' && module.exports) {
        module.exports = root.AgentAppearanceDropdown;
    }
})(typeof window !== 'undefined' ? window : globalThis);
