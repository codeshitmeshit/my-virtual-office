const assert = require('assert');
const reasoning = require('../app/codex-reasoning.js');

const state = reasoning.createState();
let sequence = 1;
for (const sectionSize of [7, 7, 6]) {
  if (sequence > 1) reasoning.applyEvent(state, { id: `event-${sequence++}`, boundary: true });
  for (let index = 0; index < sectionSize; index += 1) {
    reasoning.applyEvent(state, { id: `event-${sequence++}`, text: `part-${index} ` });
  }
}

assert.strictEqual(state.text.split('\n\n').length, 3);
assert.strictEqual((state.text.match(/part-/g) || []).length, 20);
const beforeDuplicate = state.text;
reasoning.applyEvent(state, { id: 'event-2', text: 'duplicate ' });
assert.strictEqual(state.text, beforeDuplicate);

reasoning.applyEvent(state, {
  id: 'complete',
  replace: true,
  text: 'first section\n\nsecond section\n\nthird section'
});
assert.strictEqual(state.text, 'first section\n\nsecond section\n\nthird section');

const empty = reasoning.createState();
reasoning.applyEvent(empty, { id: 'empty', boundary: true, text: '' });
assert.strictEqual(empty.text, '');

console.log('ok');
