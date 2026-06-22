const assert = require('assert');
const fs = require('fs');
const path = require('path');

const root = path.resolve(__dirname, '..');
const game = fs.readFileSync(path.join(root, 'app', 'game.js'), 'utf8');
const zh = JSON.parse(fs.readFileSync(path.join(root, 'app', 'locales', 'zh.json'), 'utf8'));
const en = JSON.parse(fs.readFileSync(path.join(root, 'app', 'locales', 'en.json'), 'utf8'));

const bubbleFn = game.slice(
  game.indexOf('function _meetingBubbleText(turn)'),
  game.indexOf('function _meetingLatestSpeakerKey(record)')
);

assert.ok(bubbleFn.includes("_mtgT('meeting_provider_calling', 'Preparing meeting response...')"));
assert.ok(!bubbleFn.includes('Calling provider...'));
assert.ok(bubbleFn.includes('turn.structured && turn.structured.position'));
assert.ok(bubbleFn.includes('turn.structured && turn.structured.summary'));

assert.ok(game.includes("kind: 'meeting_result'"));
assert.ok(game.includes("result.summary || result.resolution"));

const sourceFn = game.slice(
  game.indexOf('function _meetingChatSourceForSpeaker(agent)'),
  game.indexOf('function drawChatBubbles()')
);
assert.ok(!sourceFn.includes('_meetingLatestSpeakerKey(record)'));
assert.ok(sourceFn.includes("if (!turn || !_meetingAgentMatchesKey(agent, turn.speaker)) return;"));
assert.ok(sourceFn.includes("if (!speaker || !_meetingAgentMatchesKey(agent, speaker)) return;"));

const minimizeFn = game.slice(
  game.indexOf('function minimizeAllChat()'),
  game.indexOf('function expandAllChat()')
);
const expandFn = game.slice(
  game.indexOf('function expandAllChat()'),
  game.indexOf('function handleChatBubbleClick')
);
const drawChatFn = game.slice(
  game.indexOf('function drawChatBubbles()'),
  game.indexOf('// Compute visible world bounds')
);
assert.ok(minimizeFn.includes('agents.forEach(function(agent)'));
assert.ok(expandFn.includes('agents.forEach(function(agent)'));
assert.ok(!minimizeFn.includes("agent.state === 'meeting'"));
assert.ok(!expandFn.includes("agent.state === 'meeting'"));
assert.ok(drawChatFn.includes('if (chatMinimized[agent.statusKey])'));
assert.ok(!drawChatFn.includes('if (!isMeetingBubble && chatMinimized[agent.statusKey])'));

assert.strictEqual(zh.meeting_provider_calling, '正在准备会议回应');
assert.strictEqual(en.meeting_provider_calling, 'preparing meeting response');

console.log('meeting bubble output tests passed');
