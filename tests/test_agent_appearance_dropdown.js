#!/usr/bin/env node
const assert = require('node:assert/strict');
const dropdown = require('../app/agent-appearance-dropdown.js');

function selectorFixture({ boundaryBottom, toggleTop, toggleBottom, menuHeight }) {
    const classes = new Set();
    const popover = { scrollHeight: menuHeight };
    const toggle = {
        getBoundingClientRect() {
            return { top: toggleTop, bottom: toggleBottom };
        },
    };
    return {
        selector: {
            classList: {
                add(name) { classes.add(name); },
                remove(name) { classes.delete(name); },
                toggle(name, enabled) {
                    if (enabled) classes.add(name);
                    else classes.delete(name);
                },
                contains(name) { return classes.has(name); },
            },
            querySelector(query) {
                return query === '.ac-option-popover' ? popover : toggle;
            },
        },
        boundary: {
            getBoundingClientRect() {
                return { top: 100, bottom: boundaryBottom };
            },
        },
    };
}

const bottom = selectorFixture({
    boundaryBottom: 800,
    toggleTop: 300,
    toggleBottom: 325,
    menuHeight: 180,
});
assert.equal(dropdown.place(bottom.selector, bottom.boundary), false);
assert.equal(bottom.selector.classList.contains('opens-upward'), false);

const top = selectorFixture({
    boundaryBottom: 600,
    toggleTop: 510,
    toggleBottom: 535,
    menuHeight: 180,
});
assert.equal(dropdown.place(top.selector, top.boundary), true);
assert.equal(top.selector.classList.contains('opens-upward'), true);
dropdown.reset(top.selector);
assert.equal(top.selector.classList.contains('opens-upward'), false);

console.log('agent appearance dropdown placement contract ok');
