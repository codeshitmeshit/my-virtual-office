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
const agentModel = fs.readFileSync(path.join(root, 'app', 'agent-model.js'), 'utf8');
const weatherRendering = fs.readFileSync(path.join(root, 'app', 'weather-rendering.js'), 'utf8');
const server = fs.readFileSync(path.join(root, 'app', 'server.py'), 'utf8');

assert.ok(html.indexOf('internal-bubble.js') < html.indexOf('game.js'));
assert.ok(html.includes('id="mm-internal-bubble-timeout"'));
assert.ok(weatherRendering.includes('internalBubbleTimeoutSec'));
assert.ok(agentModel.includes('thoughtUpdatedAt'));
assert.ok(agentModel.includes('THOUGHT_BUBBLE_W = 132'));
assert.ok(agentModel.includes('InternalBubbleSettings.shouldAutoCollapse'));
assert.ok(server.includes('for field in ("thought", "speech", "speechTarget")'));
assert.ok(server.includes('target[field] = entry.get(field, "")'));

console.log('internal bubble integration tests passed');
