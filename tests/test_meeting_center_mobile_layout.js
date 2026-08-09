const assert = require('assert');
const fs = require('fs');
const path = require('path');

const root = path.resolve(__dirname, '..');
const css = fs.readFileSync(path.join(root, 'app', 'meeting-center.css'), 'utf8');
const mobileStart = css.indexOf('@media (max-width: 720px)');

assert.notStrictEqual(mobileStart, -1, 'meeting center should define a narrow-screen layout');

const mobileCss = css.slice(mobileStart);
const workspaceRule = mobileCss.match(/\.meeting-center-workspace\s*\{([^}]*)\}/);

assert.ok(workspaceRule, 'narrow-screen layout should configure the meeting workspace');
assert.match(
    workspaceRule[1],
    /grid-auto-rows:\s*max-content/,
    'single-column meeting panes must keep content-sized rows so long details cannot overlap the following pane'
);

console.log('meeting center mobile layout checks passed');
