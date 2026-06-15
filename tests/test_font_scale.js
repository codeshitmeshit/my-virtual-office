const assert = require('assert');
const fontScale = require('../app/font-scale.js');

function storage(initial) {
  const data = new Map(Object.entries(initial || {}));
  return {
    getItem(key) {
      return data.has(key) ? data.get(key) : null;
    },
    setItem(key, value) {
      data.set(key, String(value));
    }
  };
}

assert.strictEqual(fontScale.normalizeFontScale(undefined), 1);
assert.strictEqual(fontScale.normalizeFontScale(''), 1);
assert.strictEqual(fontScale.normalizeFontScale('1'), 1);
assert.strictEqual(fontScale.normalizeFontScale(1.1), 1.1);
assert.strictEqual(fontScale.normalizeFontScale('1.2'), 1.2);
assert.strictEqual(fontScale.normalizeFontScale(1.3), 1.3);
assert.strictEqual(fontScale.normalizeFontScale('1.5'), 1.5);
assert.strictEqual(fontScale.normalizeFontScale(1.25), 1.3);
assert.strictEqual(fontScale.normalizeFontScale(1.45), 1.5);
assert.strictEqual(fontScale.normalizeFontScale(0), 1);
assert.strictEqual(fontScale.normalizeFontScale('abc'), 1);
assert.strictEqual(fontScale.normalizeFontScale(9), 1);

const s = storage({
  'vo-display-prefs': JSON.stringify({ showBubbles: false, fontScale: 1.2 })
});
assert.strictEqual(fontScale.getStoredFontScale(s), 1.2);
assert.strictEqual(fontScale.setStoredFontScale('1.3', s), 1.3);
assert.deepStrictEqual(JSON.parse(s.getItem('vo-display-prefs')), {
  showBubbles: false,
  fontScale: 1.3
});

const bad = storage({ 'vo-display-prefs': '{not json' });
assert.deepStrictEqual(fontScale.readPrefs(bad), {});
assert.strictEqual(fontScale.getStoredFontScale(bad), 1);

const invalidScale = storage({
  'vo-display-prefs': JSON.stringify({ fontScale: 9, showNames: true })
});
assert.strictEqual(fontScale.sanitizeStoredFontScale(invalidScale), 1);
assert.deepStrictEqual(JSON.parse(invalidScale.getItem('vo-display-prefs')), {
  fontScale: 1,
  showNames: true
});

console.log('font scale settings ok');
