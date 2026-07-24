const assert = require('node:assert/strict');
const preview = require('../app/agent-appearance-preview.js');

const operations = [];
const context = {
    fillStyle: '',
    imageSmoothingEnabled: true,
    clearRect(...args) { operations.push(['clearRect', ...args]); },
    fillRect(...args) { operations.push(['fillRect', this.fillStyle, ...args]); },
};
const canvas = {
    width: 80,
    height: 104,
    getContext() { return context; },
};

assert.equal(preview.render(canvas, {
    skinTone: '#e8b88a',
    color: '#ffd600',
    hairStyle: 'short',
    hairColor: '#1a1a1a',
    eyeColor: '#38bdf8',
    headwear: 'headset',
    headwearColor: '#a78bfa',
    heldItem: 'tablet',
}, {}), true);
assert.equal(context.imageSmoothingEnabled, false);
for (const expectedColor of ['#e8b88a', '#ffd600', '#1a1a1a', '#38bdf8', '#a78bfa', '#2e73a6']) {
    assert(operations.some(operation => operation[1] === expectedColor), `missing ${expectedColor}`);
}
console.log('agent appearance preview contract ok');
