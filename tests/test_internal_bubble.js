const assert = require('assert');
const fs = require('fs');
const path = require('path');
const settings = require('../app/internal-bubble.js');

assert.strictEqual(settings.normalizeTimeoutSec(undefined), 60);
assert.strictEqual(settings.normalizeTimeoutSec(''), 60);
assert.strictEqual(settings.normalizeTimeoutSec('5.9'), 5);
assert.strictEqual(settings.normalizeTimeoutSec(0), 0);
assert.strictEqual(settings.normalizeTimeoutSec(-1), 60);
assert.strictEqual(settings.normalizeTimeoutSec('invalid'), 60);
assert.strictEqual(settings.normalizeTimeoutSec(Infinity), 60);

assert.strictEqual(settings.shouldAutoCollapse(1000, 2, 2999), false);
assert.strictEqual(settings.shouldAutoCollapse(1000, 2, 3000), true);
assert.strictEqual(settings.shouldAutoCollapse(1000, 0, 999999), false);
assert.strictEqual(settings.shouldAutoCollapse(0, 2, 3000), false);

const root = path.resolve(__dirname, '..');
const html = fs.readFileSync(path.join(root, 'app', 'index.html'), 'utf8');
const game = fs.readFileSync(path.join(root, 'app', 'game.js'), 'utf8');
const server = fs.readFileSync(path.join(root, 'app', 'server.py'), 'utf8');
const e2e = fs.readFileSync(path.join(root, 'tests', 'e2e_internal_bubble.js'), 'utf8');

assert.ok(html.indexOf('internal-bubble.js') < html.indexOf('game.js'));
assert.ok(html.includes('id="mm-internal-bubble-timeout"'));
assert.ok(game.includes('internalBubbleTimeoutSec'));
assert.ok(game.includes('thoughtUpdatedAt'));
assert.ok(game.includes('THOUGHT_BUBBLE_W = 132'));
assert.ok(game.includes('InternalBubbleSettings.shouldAutoCollapse'));
assert.ok(server.includes('for field in ("thought", "speech", "speechTarget")'));
assert.ok(server.includes('target[field] = entry.get(field, "")'));
assert.ok(e2e.includes('process.env.VO_CDP_URL'));
assert.ok(!e2e.includes('127.0.0.1:9223'));
assert.ok(!e2e.includes("require('puppeteer-core')"));
assert.ok(e2e.includes('CDP is unavailable'));

console.log('internal bubble integration tests passed');
