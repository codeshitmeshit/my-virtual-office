import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { createRequire } from 'node:module';
import { fileURLToPath } from 'node:url';
import vm from 'node:vm';

const require = createRequire(import.meta.url);
const here = path.dirname(fileURLToPath(import.meta.url));
const root = path.resolve(here, '..');
const UI = require(path.join(root, 'app', 'meeting-human-decision-ui.js'));
const game = fs.readFileSync(path.join(root, 'app', 'game.js'), 'utf8');
const extracted = fs.readFileSync(path.join(root, 'app', 'meetings-ui.js'), 'utf8');
const index = fs.readFileSync(path.join(root, 'app', 'index.html'), 'utf8');
const style = fs.readFileSync(path.join(root, 'app', 'style.css'), 'utf8');
const helperSource = fs.readFileSync(path.join(root, 'app', 'meeting-human-decision-ui.js'), 'utf8');

const webviewContext = { module: { exports: {} } };
webviewContext.globalThis = webviewContext;
vm.runInNewContext(helperSource, webviewContext);
assert.equal(
  typeof webviewContext.MeetingHumanDecisionUI?.render,
  'function',
  'helper must register on the browser global even when a WebView exposes CommonJS module',
);

const event = {
  type: 'human_decision_resolved',
  sequence: 9,
  createdAt: '2026-08-08T17:00:00+08:00',
  payload: {
    decisionId: 'decision-1',
    title: '确认发布策略',
    answer: '分阶段发布',
    customAnswer: '',
    stage: 'active_discussion',
    round: 2,
  },
};

const turn = UI.turnFromEvent(event);
assert.equal(turn.type, 'human_decision_resolved');
assert.equal(turn.stage, 'active_discussion');
assert.equal(turn.round, 2);
assert.equal(turn.decisionId, 'decision-1');

const html = UI.render(turn, {
  t: (_key, fallback) => fallback,
  escape: (value) => String(value),
  formatTime: (value) => value,
});
assert.match(html, /👤/);
assert.match(html, /确认发布策略/);
assert.match(html, /分阶段发布/);
assert.match(html, /decision-1/);
assert.doesNotMatch(html, /undefined/);

for (const source of [game, extracted]) {
  assert.match(source, /MeetingHumanDecisionUI\.turnFromEvent\(event\)/);
  assert.match(source, /MeetingHumanDecisionUI\.render\(turn/);
  assert.doesNotMatch(source, /_mtgFormatTime/, 'decision renderer must not call an undefined time helper');
}
assert.ok(
  index.indexOf('meeting-human-decision-ui.js') < index.indexOf('game.js'),
  'meeting decision helper must load before the active meeting UI',
);
assert.match(style, /\.mtg-turn-human-decision/);

console.log('meeting human decision discussion record checks passed');
